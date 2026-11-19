"""Altavoz y micrófono (paquete sounddevice). Solo se usan con la voz en flujo."""
from __future__ import annotations

import asyncio
from typing import Any


class ErrorAudio(RuntimeError):
    pass


def _sd() -> Any:
    try:
        import sounddevice
        return sounddevice
    except (ImportError, OSError) as e:
        raise ErrorAudio(f"No se puede usar el audio ({e}). Instala el paquete con: pip install -e \".[voz]\"") from None


class Altavoz:
    """Reproduce lo que entrega `VozFlujo.leer`. La reproducción marca el reloj de la voz."""

    def __init__(self, voz: Any, sistema: Any) -> None:
        self.voz, self.s = voz, sistema
        self._flujo: Any = None

    def iniciar(self) -> None:
        sd = _sd()

        def llenar(salida: Any, muestras: int, tiempo: Any, estado: Any) -> None:
            salida[:] = self.voz.leer(muestras, self.s.ahora())

        try:
            self._flujo = sd.RawOutputStream(samplerate=self.voz.frecuencia, channels=1, dtype="int16",
                                             blocksize=480, callback=llenar, latency="low")
            self._flujo.start()
            if hasattr(self.voz, "latencia_salida"):
                self.voz.latencia_salida = float(self._flujo.latency)
        except Exception as e:
            raise ErrorAudio(f"No se pudo abrir el altavoz: {e}") from None

    def cerrar(self) -> None:
        if self._flujo is not None:
            self._flujo.stop()
            self._flujo.close()


class Microfono:
    """Captura a 16 kHz y deja los trozos en una cola asyncio."""

    def __init__(self, bucle: asyncio.AbstractEventLoop) -> None:
        self.cola: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._bucle = bucle
        self._flujo: Any = None

    def _poner(self, datos: bytes) -> None:
        if not self.cola.full():
            self.cola.put_nowait(datos)

    def iniciar(self) -> None:
        sd = _sd()

        def recoger(entrada: Any, muestras: int, tiempo: Any, estado: Any) -> None:
            self._bucle.call_soon_threadsafe(self._poner, bytes(entrada))

        try:
            self._flujo = sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1600,
                                            callback=recoger)
            self._flujo.start()
        except Exception as e:
            raise ErrorAudio(f"No se pudo abrir el micrófono: {e}") from None

    def cerrar(self) -> None:
        if self._flujo is not None:
            self._flujo.stop()
            self._flujo.close()
