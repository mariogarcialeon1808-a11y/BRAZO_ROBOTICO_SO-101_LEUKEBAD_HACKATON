"""Tiempo del sistema: compás maestro y reloj suave de cada brazo."""
from __future__ import annotations

import threading
from typing import Any


class Compas:
    """Reloj maestro. Libre (avanza a tiempo real) o siguiendo la posición de una voz."""

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._m_ref = 0.0
        self._t_ref = 0.0
        self._voz: Any = None
        self._m_voz = 0.0

    def posicion(self, t: float) -> tuple[float, bool]:
        """Devuelve (posición del compás, ¿está avanzando?)."""
        with self._cerrojo:
            if self._voz is not None:
                return self._m_voz + self._voz.posicion(t), self._voz.estado == "hablando"
            return self._m_ref + (t - self._t_ref), True

    def seguir(self, voz: Any, m_inicio_voz: float) -> None:
        with self._cerrojo:
            self._voz = voz
            self._m_voz = m_inicio_voz

    def liberar(self, t: float) -> None:
        """Vuelve al modo libre, continuando desde la posición actual."""
        with self._cerrojo:
            if self._voz is not None:
                self._m_ref = self._m_voz + self._voz.posicion(t)
                self._t_ref = t
                self._voz = None


class RelojBrazo:
    """Tiempo gestual τ de un brazo. Persigue al compás con ritmo suave y acotado."""

    def __init__(self, ritmo_max: float = 1.4, ganancia: float = 4.0, omega: float = 10.0) -> None:
        self.tau = 0.0
        self.ritmo = 1.0
        self._dritmo = 0.0
        self.ritmo_max = ritmo_max
        self.ganancia = ganancia
        self.omega = omega
        self._m_prev: float | None = None
        self._ritmo_compas = 1.0      # estimación del ritmo al que avanza el compás

    def sincronizar(self, m: float, ritmo: float = 1.0) -> None:
        self.tau = m
        self.ritmo = ritmo
        self._dritmo = 0.0
        self._m_prev = m
        self._ritmo_compas = ritmo

    def paso(self, dt: float, m: float, corriendo: bool, bloqueado: bool = False,
             rapido: bool = False) -> float:
        # Ritmo del compás: medido y filtrado, para seguir sin desfase a una voz que
        # va más lenta o más rápida de lo estimado. Los saltos (jitter) se recortan.
        if self._m_prev is not None and dt > 0:
            medido = min(max((m - self._m_prev) / dt, 0.0), 2.0) if corriendo else 0.0
            self._ritmo_compas += (medido - self._ritmo_compas) * min(1.0, dt / 0.25)
        self._m_prev = m
        if bloqueado:
            objetivo = 0.0
        else:
            objetivo = self._ritmo_compas + self.ganancia * (m - self.tau)
            objetivo = min(max(objetivo, 0.0), self.ritmo_max)
        w = self.omega * (3.0 if rapido else 1.0)
        # Filtro de 2.º orden críticamente amortiguado (integración semi-implícita).
        self._dritmo += (w * w * (objetivo - self.ritmo) - 2.0 * w * self._dritmo) * dt
        self.ritmo += self._dritmo * dt
        if self.ritmo < 0.0:
            self.ritmo = 0.0
            self._dritmo = max(self._dritmo, 0.0)
        self.tau += self.ritmo * dt
        return self.tau

    @property
    def parado(self) -> bool:
        return self.ritmo < 2e-3 and abs(self._dritmo) < 2e-2
