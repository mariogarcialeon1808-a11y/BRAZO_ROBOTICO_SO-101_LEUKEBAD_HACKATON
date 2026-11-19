"""Capas que se suman a la línea de gestos: respiración y arrastre de muñeca."""
from __future__ import annotations

import math

import numpy as np


class Suave:
    """Valor que persigue un objetivo sin saltos ni esquinas (2.º orden, amortiguado)."""

    def __init__(self, valor: float, omega: float = 3.0) -> None:
        self.valor = valor
        self.objetivo = valor
        self._d = 0.0
        self.omega = omega

    def paso(self, dt: float) -> float:
        w = self.omega
        self._d += (w * w * (self.objetivo - self.valor) - 2.0 * w * self._d) * dt
        self.valor += self._d * dt
        return self.valor


class Respiracion:
    """Oscilación lenta y deriva suave para que el brazo nunca quede rígido."""

    def __init__(self, amplitud_grados: float, periodo_s: float, fase: float = 0.0) -> None:
        self.amplitud = amplitud_grados
        self.periodo = periodo_s
        self.fase = fase

    def valor(self, t: float) -> np.ndarray:
        a = self.amplitud
        x = 2.0 * math.pi * t / self.periodo + self.fase
        return np.array([
            0.5 * a * math.sin(x * 0.37 + 1.3) + 0.25 * a * math.sin(x * 0.23 + 0.4),  # deriva lateral
            a * math.sin(x),                                                            # hombro
            -0.7 * a * math.sin(x - 0.5),                                               # codo
            0.9 * a * math.sin(x - 1.0),                                                # muñeca
            1.4 * a * math.sin(x * 0.61 + 2.1),                                         # giro
            1.5 * a * math.sin(x - 1.4),                                                # pinza (%)
        ])


class Arrastre:
    """La muñeca se retrasa respecto al movimiento del brazo, como una cinta."""

    def __init__(self, constante_s: float = 0.12, maximo_grados: float = 14.0) -> None:
        self.tc = constante_s
        self.maximo = maximo_grados
        self._f1 = np.zeros(2)
        self._f2 = np.zeros(2)

    def paso(self, velocidad: np.ndarray, ganancia: float, dt: float) -> np.ndarray:
        # Entradas: movimiento vertical (hombro + codo) y lateral (pan), en grados/s.
        x = np.array([velocidad[1] + velocidad[2], velocidad[0]])
        k = dt / (self.tc + dt)
        self._f1 += k * (x - self._f1)
        self._f2 += k * (self._f1 - self._f2)
        m = self.maximo
        # Saturación suave (tanh): evita esquinas en la aceleración.
        salida = np.zeros(6)
        salida[3] = m * math.tanh(-0.09 * ganancia * self._f2[0] / m)
        salida[4] = 1.5 * m * math.tanh(0.12 * ganancia * self._f2[1] / m)
        return salida
