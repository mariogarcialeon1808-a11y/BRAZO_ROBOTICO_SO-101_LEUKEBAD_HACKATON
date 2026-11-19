"""Voz sintetizada: ER 2 escribe la frase y una voz la lee. El texto se conoce de antemano,
así que los gestos se anclan con exactitud al audio que se va a reproducir.

Dos sintetizadores:
- `SintetizadorWindows`: voz instalada en Windows (local, sin red, inmediata). Da el momento
  exacto de cada palabra.
- `SintetizadorGemini`: Gemini TTS (en la nube, voz más natural, pero tarda segundos). Los
  tiempos de palabra se estiman por sílabas dentro de la duración real.

`VozSintetizada` cumple el contrato de voz del director y entrega el audio al altavoz; la
posición de la reproducción es el reloj de la frase.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import threading
import wave
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .partitura import Frase, Palabra, contar_silabas, estimar_tiempos

FRECUENCIA = 24000
GUION_WINDOWS = Path(__file__).with_name("voz_windows.ps1")


class ErrorVoz(RuntimeError):
    pass


def _de_wav(datos: bytes) -> np.ndarray:
    """WAV (o PCM crudo de 16 bits) → muestras int16 mono a 24 kHz."""
    if datos[:4] != b"RIFF":
        return np.frombuffer(datos[:len(datos) // 2 * 2], dtype=np.int16).copy()
    with wave.open(io.BytesIO(datos)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1).astype(np.int16)
        if w.getframerate() != FRECUENCIA:
            n = int(len(x) * FRECUENCIA / w.getframerate())
            x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.int16)
    return x.copy()


class SintetizadorWindows:
    """Voz instalada en Windows (System.Speech). Local, rápida y con tiempos exactos por palabra.

    Mantiene abierto un proceso con la voz ya cargada, así cada frase sale en décimas de segundo."""

    nombre = "voz local de Windows"

    def __init__(self, voz: str = "", ritmo: int = 0) -> None:
        if sys.platform != "win32":
            raise ErrorVoz("la voz local de Windows solo existe en Windows")
        self.voz, self.ritmo = voz, int(ritmo)
        self._proceso: subprocess.Popen | None = None
        self._cerrojo = threading.Lock()
        self._carpeta = tempfile.TemporaryDirectory(prefix="so101er_voz_")
        self._n = 0

    def _orden(self) -> list[str]:
        orden = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                 str(GUION_WINDOWS), "-Ritmo", str(self.ritmo)]
        return orden + (["-Voz", self.voz] if self.voz else [])

    def _servidor(self) -> subprocess.Popen:
        if self._proceso is None or self._proceso.poll() is not None:
            try:
                self._proceso = subprocess.Popen(
                    self._orden() + ["-Servidor"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if self._proceso.stdout.readline().strip() != "LISTO":
                    raise OSError("la voz no ha arrancado")
            except OSError as e:
                self._proceso = None
                raise ErrorVoz(f"no se pudo usar la voz de Windows: {e}") from None
        return self._proceso

    def sintetizar(self, texto: str) -> tuple[np.ndarray, list[tuple[int, float]] | None]:
        with self._cerrojo:
            self._n += 1
            entrada = Path(self._carpeta.name) / f"frase_{self._n}.txt"
            salida = Path(self._carpeta.name) / f"frase_{self._n}.wav"
            entrada.write_text(texto, encoding="utf-8")
            try:
                proceso = self._servidor()
                proceso.stdin.write(f"{entrada}|{salida}\n")
                proceso.stdin.flush()
                respuesta = proceso.stdout.readline()
            except (OSError, ValueError) as e:
                self._proceso = None
                raise ErrorVoz(f"la voz de Windows ha fallado: {e}") from None
            if not salida.exists() or salida.stat().st_size < 100:
                raise ErrorVoz("la voz de Windows no ha generado audio")
            crudo = salida.read_bytes()
            for ruta in (entrada, salida):
                ruta.unlink(missing_ok=True)
        audio = _de_wav(crudo)
        try:
            datos = json.loads(respuesta.strip())
            # El motor cuenta el tiempo como bytes / 32000 (su formato interno, 16 kHz y 16 bits),
            # no según el formato del archivo: se corrige con los bytes por segundo de la cabecera.
            escala = 32000.0 / int.from_bytes(crudo[28:32], "little")
            marcas = [(int(x["c"]), float(x["t"]) * escala) for x in datos.get("palabras", [])]
        except (ValueError, KeyError, TypeError, ZeroDivisionError):
            marcas = None
        if marcas and not self._cuadran(audio, marcas):
            marcas = None
        return audio, marcas or None

    @staticmethod
    def _cuadran(audio: np.ndarray, marcas: list[tuple[int, float]]) -> bool:
        """Comprueba las marcas contra el audio: en cada marca debe empezar a sonar algo."""
        ventana = FRECUENCIA // 50
        n = len(audio) // ventana
        if n == 0 or marcas[-1][1] > len(audio) / FRECUENCIA:
            return False
        sonido = np.abs(audio[:n * ventana]).reshape(n, ventana).max(axis=1) > 350
        aciertos = sum(bool(sonido[int(t * 50):int(t * 50) + 8].any()) for _, t in marcas)
        return aciertos >= 0.8 * len(marcas)

    def cerrar(self) -> None:
        if self._proceso is not None and self._proceso.poll() is None:
            try:
                self._proceso.stdin.close()
                self._proceso.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self._proceso.kill()
        self._carpeta.cleanup()


def realzar(audio: np.ndarray, volumen: float) -> np.ndarray:
    """Sube el volumen sin distorsionar: ganancia con un limitador suave en los picos."""
    if volumen == 1.0 or len(audio) == 0:
        return audio
    x = audio.astype(np.float64) / 32768.0 * volumen
    return (np.tanh(x) / np.tanh(max(volumen, 1.0)) * 32000.0).astype(np.int16) if volumen > 1.0 \
        else (x * 32768.0).astype(np.int16)


class SintetizadorGemini:
    """Gemini TTS. Voz más natural, pero en la nube y con varios segundos de espera por frase."""

    nombre = "Gemini TTS"

    def __init__(self, cliente: Any, modelo: str, voz: str) -> None:
        self.cliente, self.modelo, self.voz = cliente, modelo, voz

    def sintetizar(self, texto: str) -> tuple[np.ndarray, None]:
        from google.genai import types
        r = self.cliente.models.generate_content(
            model=self.modelo, contents=texto,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz)))))
        return _de_wav(r.candidates[0].content.parts[0].inline_data.data), None


def tiempos_de_palabras(texto: str, audio: np.ndarray, marcas: list[tuple[int, float]] | None,
                        silabas_por_segundo: float) -> tuple[list[Palabra], float]:
    """Momento de cada palabra en el audio: exacto si el sintetizador lo da; si no, estimado."""
    duracion = len(audio) / FRECUENCIA
    palabras, estimada = estimar_tiempos(texto, silabas_por_segundo)
    if not palabras:
        return palabras, duracion
    if marcas:
        # Posición en el texto de cada palabra nuestra → marca del sintetizador más cercana.
        pos, inicios = 0, []
        for p in palabras:
            i = texto.find(p.texto, pos)
            i = pos if i < 0 else i
            pos = i + len(p.texto)
            dentro = [t for c, t in marcas if i <= c < pos]
            inicios.append(dentro[0] if dentro else None)
        conocidos = [(k, t) for k, t in enumerate(inicios) if t is not None]
        if conocidos:
            ks, ts = [k for k, _ in conocidos], [t for _, t in conocidos]
            inicios = [float(np.interp(k, ks, ts)) for k in range(len(palabras))]
            for k, p in enumerate(palabras):
                fin = inicios[k + 1] if k + 1 < len(palabras) else min(duracion, inicios[k] + p.silabas / silabas_por_segundo)
                palabras[k] = Palabra(p.texto, inicios[k], max(fin, inicios[k]), p.silabas)
            return palabras, duracion
    # Sin marcas: reparto por sílabas dentro del tramo con voz (sin los silencios de los extremos).
    con_voz = np.flatnonzero(np.abs(audio) > 500)
    ini, fin = (con_voz[0] / FRECUENCIA, con_voz[-1] / FRECUENCIA) if len(con_voz) else (0.0, duracion)
    escala = (fin - ini) / estimada if estimada > 0 else 1.0
    return [Palabra(p.texto, ini + p.inicio * escala, ini + p.fin * escala, p.silabas) for p in palabras], duracion


class VozSintetizada:
    """Voz con audio real y texto conocido de antemano. Cumple el contrato de voz del director."""

    frecuencia = FRECUENCIA

    def __init__(self, sintetizador: Any, silabas_por_segundo: float = 4.6,
                 al_subtitulo: Callable[[str], None] | None = None,
                 al_error: Callable[[str], None] | None = None, volumen: float = 1.0) -> None:
        self.sintetizador = sintetizador
        self.volumen = volumen
        self.latencia_salida = 0.0      # retraso del altavoz (s): lo fija el altavoz al abrirse
        self.silabas_por_segundo = silabas_por_segundo
        self.al_subtitulo, self.al_error = al_subtitulo, al_error or (lambda texto: None)
        self.estado = "inactiva"
        self.texto = ""
        self._audio = np.zeros(0, np.int16)
        self._pos = 0
        self._cerrojo = threading.Lock()
        self._hilos = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voz")    # de una en una
        self._futuros: dict[str, Future] = {}
        self.t_sintesis = 0.0

    # ------------------------------------------------------------ preparación
    def precalentar(self, texto: str) -> None:
        """Empieza a sintetizar una frase en segundo plano, en cuanto se conoce."""
        if texto not in self._futuros:
            self._futuros[texto] = self._hilos.submit(self._sintetizar, texto)

    def _sintetizar(self, texto: str) -> tuple[np.ndarray, list[tuple[int, float]] | None, float]:
        import time
        t0 = time.perf_counter()
        audio, marcas = self.sintetizador.sintetizar(texto)
        return realzar(audio, self.volumen), marcas, time.perf_counter() - t0

    def preparar(self, frase: Frase) -> tuple[list[Palabra], float]:
        self.precalentar(frase.texto)
        self.texto = frase.texto
        try:
            audio, marcas, self.t_sintesis = self._futuros.pop(frase.texto).result(timeout=90)
        except Exception as e:            # sin voz, la frase sale en subtítulos con tiempos estimados
            self.al_error(f"no se pudo sintetizar la voz ({type(e).__name__}: {e}); la frase va sin sonido")
            palabras, duracion = estimar_tiempos(frase.texto, self.silabas_por_segundo)
            audio, marcas = np.zeros(int(duracion * FRECUENCIA), np.int16), None
            with self._cerrojo:
                self._audio, self._pos, self.estado = audio, 0, "inactiva"
            return palabras, duracion
        palabras, duracion = tiempos_de_palabras(frase.texto, audio, marcas, self.silabas_por_segundo)
        with self._cerrojo:
            self._audio, self._pos, self.estado = audio, 0, "inactiva"
        return palabras, duracion

    # ------------------------------------------------------------ reproducción
    def iniciar(self, t: float) -> None:
        with self._cerrojo:
            self._pos, self.estado = 0, "hablando"
        if self.al_subtitulo:
            self.al_subtitulo(self.texto)

    def leer(self, muestras: int, t: float) -> bytes:
        """Audio para el altavoz. La cantidad entregada marca la posición de la voz."""
        with self._cerrojo:
            if self.estado != "hablando":
                return bytes(muestras * 2)
            trozo = self._audio[self._pos:self._pos + muestras]
            self._pos += len(trozo)
            if self._pos >= len(self._audio):
                self.estado = "terminada"
            return trozo.tobytes() + bytes((muestras - len(trozo)) * 2)

    def posicion(self, t: float) -> float:
        # Lo entregado al altavoz suena un poco después: se descuenta ese retraso.
        return max(self._pos / FRECUENCIA - self.latencia_salida, 0.0)

    def pendiente(self) -> bool:
        return self.estado in ("hablando", "pausada")

    def pausar(self, t: float) -> None:
        with self._cerrojo:
            if self.estado == "hablando":
                self.estado = "pausada"

    def reanudar(self, t: float) -> None:
        with self._cerrojo:
            if self.estado == "pausada":
                self.estado = "hablando"

    def interrumpir(self, t: float) -> None:
        with self._cerrojo:
            if self.estado in ("hablando", "pausada"):
                self.estado = "interrumpida"
        self._futuros.clear()

    def cerrar(self) -> None:
        self._hilos.shutdown(wait=False, cancel_futures=True)
        if hasattr(self.sintetizador, "cerrar"):
            self.sintetizador.cerrar()
