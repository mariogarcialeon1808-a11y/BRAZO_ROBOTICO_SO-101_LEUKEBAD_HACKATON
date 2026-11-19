"""Voz de ElevenLabs por WebSocket (stream-input, eleven_flash_v2_5), en español o inglés.

Adaptada del prototipo robot-guia-bot. El texto se envía según lo escribe el chatbot y el
audio empieza a sonar mientras el resto aún se está generando. Con cada trozo de audio llega
la alineación letra a letra, de la que sale el momento exacto de cada palabra: con eso se
anclan los gestos. La reproducción la hace el altavoz del programa, así que la posición de
la voz se conoce siempre y se puede cortar al instante.
"""
from __future__ import annotations

import base64
import json
import sys
import threading
import time
from contextlib import ExitStack
from typing import Callable

import numpy as np

from ..sincronia.voz_sintetizada import realzar

FRECUENCIA = 24_000
INACTIVIDAD_S = 180
MANTENER_S = 60
ATASCO_S = 4.0                  # sin audio nuevo en este tiempo, el turno se da por acabado
COLCHON_S = 0.15                # audio acumulado antes de empezar a sonar (evita cortes)
LETRAS_POR_SEGUNDO = 15.0       # ritmo de la voz para estimar tiempos antes de recibir el audio


def _letras(texto: str) -> int:
    return sum(1 for c in texto if not c.isspace())


class VozEleven:
    frecuencia = FRECUENCIA

    def __init__(self, clave: str, voice_id: str, idioma: str = "es", volumen: float = 1.0,
                 modelo: str = "eleven_flash_v2_5", al_error: Callable[[str], None] | None = None) -> None:
        self._clave, self._voice, self._modelo = clave, voice_id, modelo
        self.idioma = idioma
        self.volumen = volumen
        self.al_error = al_error or (lambda texto: print(f"[voz] {texto}", file=sys.stderr))
        self.al_palabra: Callable[[str, float], None] | None = None
        self.latencia_salida = 0.0
        self.estado = "inactiva"            # inactiva | esperando | hablando | pausada | terminada
        self.palabras: list[tuple[str, float]] = []     # (palabra, segundos desde el inicio del turno)
        self._pos_palabras: list[int] = []              # posición de cada palabra en el texto del turno
        self._lock = threading.Lock()       # conexión y envíos
        self._ws = None
        self._pila: ExitStack | None = None
        self._buf = bytearray()
        self._buf_lock = threading.Lock()
        self._turno = 0
        self._enviadas = self._recibidas = 0
        self._fin_texto = False
        self._actividad = time.monotonic()
        self._ultimo_envio = time.monotonic()
        self._reproducidas = 0
        self._base_al = 0.0                 # reloj de la alineación (s) al empezar el trozo actual
        self._texto, self._alineados = "", 0
        self._parcial: tuple[str, float] | None = None
        self.t_primer_audio: float | None = None
        threading.Thread(target=self._mantener, daemon=True).start()

    # ------------------------------------------------------------------ conexión
    def _url(self) -> str:
        return (f"wss://api.elevenlabs.io/v1/text-to-speech/{self._voice}/stream-input"
                f"?model_id={self._modelo}&output_format=pcm_{FRECUENCIA}&language_code={self.idioma}"
                f"&inactivity_timeout={INACTIVIDAD_S}")

    def _conectar(self) -> None:
        """Con self._lock tomado."""
        if self._ws is not None:
            return
        from websockets.sync.client import connect
        pila = ExitStack()
        try:
            ws = pila.enter_context(connect(self._url(), additional_headers={"xi-api-key": self._clave},
                                            open_timeout=8, max_size=None))
            ws.send(json.dumps({"text": " ", "generation_config": {"chunk_length_schedule": [50, 120, 160, 250]}}))
        except BaseException:
            pila.close()
            raise
        self._ws, self._pila = ws, pila
        self._ultimo_envio = time.monotonic()
        threading.Thread(target=self._recibir, args=(ws, self._turno), daemon=True).start()

    def _descartar(self) -> None:
        """Con self._lock tomado."""
        pila, self._ws, self._pila = self._pila, None, None
        if pila is not None:
            try:
                pila.close()
            except Exception:
                pass

    def conectar_en_segundo_plano(self) -> None:
        def tarea() -> None:
            try:
                with self._lock:
                    self._conectar()
            except Exception as e:
                self.al_error(f"no puedo conectar con la voz: {e}")
        threading.Thread(target=tarea, daemon=True).start()

    def cambiar_idioma(self, idioma: str) -> None:
        with self._lock:
            self.idioma = idioma
            self._descartar()
        self.conectar_en_segundo_plano()

    def cerrar(self) -> None:
        with self._lock:
            self._descartar()

    # ------------------------------------------------------------------ turno
    def empezar_turno(self) -> None:
        """Deja todo listo para una respuesta nueva."""
        with self._buf_lock:
            self._turno += 1
            self._buf.clear()
            self.palabras = []
            self._pos_palabras = []
            self._enviadas = self._recibidas = self._reproducidas = 0
            self._fin_texto = False
            self._base_al, self._parcial = 0.0, None
            self._texto = ""                # todo el texto enviado en el turno
            self._alineados = 0             # caracteres del texto cuyo tiempo exacto ya se conoce
            self.t_primer_audio = None
            self.estado = "esperando"
            self._actividad = time.monotonic()

    def enviar(self, texto: str, flush: bool = False) -> None:
        """Manda un trozo de texto (acabado en espacio). Con flush, obliga a generar ya."""
        if not texto.strip() and not flush:
            return
        mensaje = {"text": texto, "flush": True} if flush else {"text": texto}
        with self._lock:
            for intento in (1, 2):
                try:
                    self._conectar()
                    self._ws.send(json.dumps(mensaje))
                    break
                except Exception as e:
                    self._descartar()
                    if intento == 2:
                        self.al_error(f"error al enviar texto a la voz: {e}")
                        return
            self._ultimo_envio = time.monotonic()
        with self._buf_lock:
            self._enviadas += _letras(texto)
            self._texto += texto
            self._actividad = time.monotonic()

    @property
    def letras_enviadas(self) -> int:
        """Caracteres de texto enviados en este turno (sirve para delimitar cada frase)."""
        return len(self._texto)

    def _ritmo(self) -> float:
        return max(self._alineados / self._base_al if self._base_al > 1.0 else LETRAS_POR_SEGUNDO, 5.0)

    def cuando(self, palabra: str, desde: float, normalizar: Callable[[str], str],
               rango: tuple[int, int] | None = None) -> tuple[float, bool] | None:
        """Instante del turno (s) en que sonará `palabra` a partir de `desde`, y si es exacto.

        `rango` limita la búsqueda a un tramo del texto (los caracteres de una frase), para no
        anclar un gesto a la misma palabra dicha mucho después. Si el audio de esa parte ya ha
        llegado, el tiempo es el real; si no, se estima por la posición de la palabra en el texto
        y el ritmo de la voz: así el gesto se prepara antes de que llegue el audio de su palabra."""
        c0, c1 = rango or (0, 10**9)
        if not palabra:
            return None
        with self._buf_lock:
            for (texto, inicio), p in zip(self.palabras, self._pos_palabras):
                if c0 <= p < c1 and inicio >= desde and palabra in normalizar(texto):
                    return inicio, True
            pos = 0
            for trozo in self._texto.split(" "):
                if c0 <= pos < c1 and pos >= self._alineados and palabra in normalizar(trozo):
                    t = self._base_al + (pos - self._alineados) / self._ritmo()
                    if t >= desde:
                        return t, False
                pos += len(trozo) + 1
        return None

    def tiempo_de(self, caracter: int) -> float:
        """Instante del turno (s) en que suena la posición `caracter` del texto (real o estimado)."""
        with self._buf_lock:
            if caracter >= self._alineados:
                return self._base_al + (caracter - self._alineados) / self._ritmo()
            anterior = 0.0
            for (_, inicio), p in zip(self.palabras, self._pos_palabras):
                if p > caracter:
                    break
                anterior = inicio
            return anterior

    def fin_texto(self) -> None:
        """No habrá más texto en este turno."""
        self.enviar(" ", flush=True)
        with self._buf_lock:
            self._fin_texto = True
            self._actividad = time.monotonic()

    def interrumpir(self) -> None:
        """Corta la voz al instante: descarta lo que quedaba por sonar y por generar."""
        with self._buf_lock:
            self._turno += 1
            self._buf.clear()
            self._fin_texto = True
            self.estado = "inactiva"
        with self._lock:
            self._descartar()               # el servidor deja de generar; se reabre sola
        self.conectar_en_segundo_plano()

    # ------------------------------------------------------------------ reproducción
    def leer(self, muestras: int, t: float) -> bytes:
        """Audio para el altavoz. Lo entregado marca la posición de la voz."""
        pedido = muestras * 2
        with self._buf_lock:
            if self.estado == "esperando":
                if len(self._buf) >= int(COLCHON_S * FRECUENCIA) * 2 or (self._fin_texto and self._buf):
                    self.estado = "hablando"
                    self.t_primer_audio = time.perf_counter()
            elif self.estado == "pausada" and (len(self._buf) >= int(0.2 * FRECUENCIA) * 2
                                               or self._recibidas >= self._enviadas):
                self.estado = "hablando"
            if self.estado != "hablando":
                self._comprobar_fin()
                return bytes(pedido)
            n = min(pedido, len(self._buf))
            n -= n % 2
            datos = bytes(self._buf[:n])
            del self._buf[:n]
            self._reproducidas += n // 2
            if not self._buf:
                self._comprobar_fin()
                if self.estado == "hablando":
                    self.estado = "pausada"         # la red va más lenta que la voz: se espera
            return datos + bytes(pedido - n)

    def _comprobar_fin(self) -> None:
        """Con self._buf_lock tomado."""
        if self.estado in ("hablando", "pausada", "esperando") and self._fin_texto and not self._buf and (
                self._recibidas >= self._enviadas or time.monotonic() - self._actividad > ATASCO_S):
            self.estado = "terminada"

    def posicion(self, t: float) -> float:
        """Segundos del turno que ya han sonado (descontando el retraso del altavoz)."""
        return max(self._reproducidas / FRECUENCIA - self.latencia_salida, 0.0)

    def pendiente(self) -> bool:
        return self.estado in ("esperando", "hablando", "pausada")

    @property
    def sonando(self) -> bool:
        return self.estado in ("hablando", "pausada")

    # ------------------------------------------------------------------ hilos
    def _recibir(self, ws, turno_al_abrir: int) -> None:
        try:
            for mensaje in ws:
                d = json.loads(mensaje)
                if d.get("error") or d.get("message"):
                    self.al_error(str(d.get("error") or d.get("message")))
                pcm = base64.b64decode(d["audio"]) if d.get("audio") else b""
                al = d.get("alignment") or {}
                chars, inicios, duraciones = (al.get("chars") or [], al.get("charStartTimesMs") or [],
                                              al.get("charDurationsMs") or [])
                if pcm and self.volumen != 1.0:
                    pcm = realzar(np.frombuffer(pcm[:len(pcm) // 2 * 2], dtype=np.int16), self.volumen).tobytes()
                nuevas: list[tuple[str, float]] = []
                with self._buf_lock:
                    if self.estado == "inactiva":       # turno interrumpido: se ignora lo que llegue
                        continue
                    self._buf += pcm
                    for j, (c, ini) in enumerate(zip(chars, inicios)):
                        if c.isspace():
                            if self._parcial is not None:
                                nuevas.append(self._parcial)
                                self._parcial = None
                        elif self._parcial is None:
                            self._parcial = (c, self._base_al + ini / 1000.0)
                            self._pos_parcial = self._alineados + j
                            self._pos_palabras.append(self._pos_parcial)
                        else:
                            self._parcial = (self._parcial[0] + c, self._parcial[1])
                    if inicios:
                        self._base_al += (inicios[-1] + (duraciones[-1] if duraciones else 0)) / 1000.0
                    self._recibidas += _letras("".join(chars))
                    self._alineados += len(chars)
                    if self._fin_texto and self._recibidas >= self._enviadas and self._parcial is not None:
                        nuevas.append(self._parcial)
                        self._parcial = None
                    self.palabras.extend(nuevas)
                    self._actividad = time.monotonic()
                if self.al_palabra:
                    for texto, inicio in nuevas:
                        self.al_palabra(texto, inicio)
        except Exception:
            pass
        finally:
            with self._lock:
                if self._ws is ws:
                    self._descartar()

    def _mantener(self) -> None:
        while True:
            time.sleep(5)
            with self._lock:
                if self._ws is not None and time.monotonic() - self._ultimo_envio > MANTENER_S:
                    try:
                        self._ws.send(json.dumps({"text": " "}))
                        self._ultimo_envio = time.monotonic()
                    except Exception:
                        self._descartar()
