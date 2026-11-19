"""Contrato de la voz y voz muda.

Cualquier voz (muda, sintetizada o una IA externa) cumple el mismo contrato:
prepara una frase, la reproduce y va diciendo por dónde va. La posición se da
siempre en **segundos de partitura**: el tiempo que la frase lleva dicho según
los tiempos de palabra devueltos por `preparar`. Así el sistema de gestos no
depende de cómo de rápida o irregular sea la voz real.
"""
from __future__ import annotations

from typing import Callable, Protocol

from .partitura import Frase, Palabra, estimar_tiempos

ESTADOS = ("inactiva", "hablando", "pausada", "terminada", "interrumpida")


class Voz(Protocol):
    estado: str

    def preparar(self, frase: Frase) -> tuple[list[Palabra], float]:
        """Devuelve los tiempos de las palabras y la duración total (s de partitura)."""
        ...

    def iniciar(self, t: float) -> None: ...
    def posicion(self, t: float) -> float: ...
    def pausar(self, t: float) -> None: ...
    def reanudar(self, t: float) -> None: ...
    def interrumpir(self, t: float) -> None: ...


class VozMuda:
    """Voz sin sonido: muestra subtítulos y avanza según los tiempos estimados por sílabas."""

    def __init__(self, silabas_por_segundo: float = 4.6,
                 al_subtitulo: Callable[[str], None] | None = None, velocidad: float = 1.0) -> None:
        self.silabas_por_segundo = silabas_por_segundo
        self.al_subtitulo = al_subtitulo
        self.velocidad = velocidad        # 1 = según lo estimado; <1 = la voz real va más lenta
        self.estado = "inactiva"
        self.texto = ""
        self._duracion = 0.0
        self._t_ref = 0.0
        self._pos_ref = 0.0

    def preparar(self, frase: Frase) -> tuple[list[Palabra], float]:
        palabras, duracion = estimar_tiempos(frase.texto, self.silabas_por_segundo)
        self.texto = frase.texto
        self._duracion = duracion
        self.estado = "inactiva"
        self._pos_ref = 0.0
        return palabras, duracion

    def iniciar(self, t: float) -> None:
        self._t_ref, self._pos_ref = t, 0.0
        self.estado = "hablando"
        if self.al_subtitulo:
            self.al_subtitulo(self.texto)

    def posicion(self, t: float) -> float:
        if self.estado == "hablando":
            pos = self._pos_ref + (t - self._t_ref) * self.velocidad
            if pos >= self._duracion:
                self._pos_ref, self.estado = self._duracion, "terminada"
                return self._duracion
            return pos
        return self._pos_ref

    def pausar(self, t: float) -> None:
        if self.estado == "hablando":
            self._pos_ref = self.posicion(t)
            if self.estado == "hablando":
                self.estado = "pausada"

    def reanudar(self, t: float) -> None:
        if self.estado == "pausada":
            self._t_ref = t
            self.estado = "hablando"

    def interrumpir(self, t: float) -> None:
        if self.estado in ("hablando", "pausada"):
            self._pos_ref = self.posicion(t)
            self.estado = "interrumpida"
