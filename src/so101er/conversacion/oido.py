"""Oído: micrófono, barra espaciadora para hablar y ElevenLabs Scribe Realtime.

Adaptado del prototipo robot-guia-bot. El micrófono queda abierto toda la sesión (abrirlo en
cada turno tarda), pero el audio solo se envía mientras la barra está pulsada.
"""
from __future__ import annotations

import base64
import collections
import json
import queue
import sys
import threading
from typing import Callable
from urllib.parse import urlencode

SR = 16_000
BLOQUE = 800                     # 50 ms
PREROLL_S = 0.25                 # para no perder la primera sílaba
STT_MODELO = "scribe_v3_live"
STT_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
MAX_MENSAJE = SR * 2
ESPERA_FINAL_S = 6.0


class ErrorOido(RuntimeError):
    pass


class Micro:
    """Micrófono abierto toda la sesión. empezar() reenvía cada bloque a un destino."""

    def __init__(self, dispositivo: int | None = None) -> None:
        try:
            import sounddevice as sd
            self._lock = threading.Lock()
            self._previo: collections.deque[bytes] = collections.deque(maxlen=round(PREROLL_S * SR / BLOQUE))
            self._destino: Callable[[bytes], None] | None = None
            self.nivel = 0
            self.stream = sd.InputStream(device=dispositivo, samplerate=SR, channels=1, dtype="int16",
                                         blocksize=BLOQUE, callback=self._callback)
            self.stream.start()
        except Exception as e:
            raise ErrorOido(f"No se pudo abrir el micrófono: {e}") from None

    def _callback(self, indata, frames, t, status) -> None:
        datos = indata.tobytes()
        with self._lock:
            self.nivel = int(abs(indata).max())
            if self._destino is None:
                self._previo.append(datos)
            else:
                self._destino(datos)

    def empezar(self, destino: Callable[[bytes], None]) -> None:
        with self._lock:
            for datos in self._previo:
                destino(datos)
            self._previo.clear()
            self._destino = destino

    def parar(self) -> None:
        with self._lock:
            self._destino = None

    def cerrar(self) -> None:
        self.stream.abort()         # abort, no stop: stop() puede colgarse con algunos drivers de Windows
        self.stream.close()


_COMMIT, _CANCELAR = object(), object()
_ERRORES_SIN_VOZ = {"insufficient_audio_activity"}


class Transcriptor:
    """Una sesión de Scribe Realtime para un turno. Se conecta mientras la persona habla."""

    def __init__(self, clave: str, idioma: str = "es") -> None:
        self.error: str | None = None
        self.parcial = ""
        self._cola: queue.Queue = queue.Queue()
        self._final: list[str] = []
        self._commit_enviado = threading.Event()
        self._listo = threading.Event()
        params = [("model_id", STT_MODELO), ("audio_format", f"pcm_{SR}"), ("language_code", idioma),
                  ("commit_strategy", "manual")]
        self._url = f"{STT_URL}?{urlencode(params)}"
        self._clave = clave
        threading.Thread(target=self._sesion, daemon=True).start()

    def enviar_audio(self, pcm: bytes) -> None:
        self._cola.put(pcm)

    def confirmar(self) -> str:
        """Cierra el turno y devuelve lo que se ha dicho ("" si no se ha entendido nada)."""
        self._cola.put(_COMMIT)
        if not self._listo.wait(ESPERA_FINAL_S):
            self.error = self.error or f"el reconocimiento de voz no ha respondido en {ESPERA_FINAL_S:g} s"
            self._cola.put(_CANCELAR)
            return self.parcial.strip()
        return " ".join(t for t in self._final if t).strip() or self.parcial.strip()

    def cancelar(self) -> None:
        self._cola.put(_CANCELAR)

    def _sesion(self) -> None:
        from websockets.exceptions import WebSocketException
        from websockets.sync.client import connect
        try:
            with connect(self._url, additional_headers={"xi-api-key": self._clave},
                         open_timeout=8, max_size=None) as ws:
                inicio = json.loads(ws.recv(timeout=8))
                if inicio.get("message_type") != "session_started":
                    raise RuntimeError(f"{inicio.get('message_type')}: {inicio.get('error', inicio)}")
                threading.Thread(target=self._recibir, args=(ws,), daemon=True).start()
                self._enviar(ws)
        except (OSError, TimeoutError, WebSocketException, RuntimeError, ValueError) as e:
            self.error = f"reconocimiento de voz: {type(e).__name__}: {e}"
            self._listo.set()

    def _enviar(self, ws) -> None:
        while True:
            item = self._cola.get()
            datos = b""
            while isinstance(item, bytes):
                datos += item
                if len(datos) >= MAX_MENSAJE:
                    break
                try:
                    item = self._cola.get_nowait()
                except queue.Empty:
                    item = None
            if datos:
                ws.send(json.dumps({"message_type": "input_audio_chunk", "sample_rate": SR, "commit": False,
                                    "audio_base_64": base64.b64encode(datos).decode()}))
            if item is _CANCELAR:
                return
            if item is _COMMIT:
                self._commit_enviado.set()
                ws.send(json.dumps({"message_type": "input_audio_chunk", "sample_rate": SR, "commit": True,
                                    "audio_base_64": ""}))
                self._listo.wait(ESPERA_FINAL_S)
                return

    def _recibir(self, ws) -> None:
        from websockets.exceptions import WebSocketException
        try:
            for mensaje in ws:
                d = json.loads(mensaje)
                tipo = d.get("message_type", "")
                if tipo == "partial_transcript":
                    self.parcial = d.get("text", "")
                elif tipo == "committed_transcript":
                    self._final.append(d.get("text", "").strip())
                    if self._commit_enviado.is_set():
                        self._listo.set()
                elif "error" in d:
                    if tipo not in _ERRORES_SIN_VOZ:
                        self.error = f"reconocimiento de voz {tipo}: {d['error']}"
                    self._listo.set()
        except WebSocketException as e:
            if not self._listo.is_set():
                self.error = f"reconocimiento de voz: conexión cerrada ({e})"
        finally:
            self._listo.set()


def ventana_activa() -> str:
    """Título de la ventana que tiene el foco (solo Windows; "" en otros sistemas)."""
    if sys.platform != "win32":
        return ""
    import ctypes
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(h, buf, 256)
    return buf.value


class BarraEspaciadora:
    """Pulsar para hablar: mantener la barra espaciadora. Escucha global (pynput).

    Solo cuenta si la ventana con el foco es una de las del programa (su título contiene alguno
    de `titulos`): así no graba cuando se escribe un espacio en otra aplicación.
    """

    def __init__(self, al_pulsar: Callable[[], None], al_soltar: Callable[[], None],
                 titulos: tuple[str, ...] = ("MuJoCo", "so101er")) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            raise ErrorOido("Falta el paquete pynput. Instálalo con: pip install -e \".[conversacion]\"") from None
        self._espacio = keyboard.Key.space
        self._al_pulsar, self._al_soltar, self._titulos = al_pulsar, al_soltar, titulos
        self.pulsada = False
        self._listener = keyboard.Listener(on_press=self._pulsar, on_release=self._soltar)
        self._listener.daemon = True
        self._listener.start()

    def _en_foco(self) -> bool:
        titulo = ventana_activa()
        return not titulo or any(x.lower() in titulo.lower() for x in self._titulos)

    def _pulsar(self, tecla) -> None:
        if tecla == self._espacio and not self.pulsada and self._en_foco():     # ignora la autorrepetición
            self.pulsada = True
            threading.Thread(target=self._al_pulsar, daemon=True).start()

    def _soltar(self, tecla) -> None:
        if tecla == self._espacio and self.pulsada:
            self.pulsada = False
            threading.Thread(target=self._al_soltar, daemon=True).start()

    def cerrar(self) -> None:
        self._listener.stop()
