"""Línea de movimiento de un brazo: superposición de submovimientos suaves.

q(τ) = base + Σ dₖ · f(w((τ − t0ₖ − retardoₖ) / durₖ))

Cada submovimiento es suave por sí mismo, así que la suma lo es siempre,
aunque se solapen o se añadan a mitad de movimiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .perfiles import bulto, deformar, escalon

N = 6  # 5 articulaciones + pinza


@dataclass
class Sub:
    t0: float                 # inicio, en tiempo gestual (s)
    dur: float                # duración (s)
    d: np.ndarray             # desplazamiento (grados; pinza en %)
    retardo: np.ndarray = field(default_factory=lambda: np.zeros(N))
    c: float = 1.0            # asimetría del ritmo
    es_bulto: bool = False    # True: sale y vuelve; False: desplazamiento permanente

    def valor(self, tau: float) -> np.ndarray:
        u = (tau - self.t0 - self.retardo) / self.dur
        w = deformar(u, self.c)
        return self.d * (bulto(w) if self.es_bulto else escalon(w))

    @property
    def fin(self) -> float:
        return self.t0 + self.dur + float(np.max(self.retardo))


class Linea:
    def __init__(self, base: np.ndarray) -> None:
        self.base = np.asarray(base, float).copy()
        self.subs: list[Sub] = []

    def copia(self) -> "Linea":
        otra = Linea(self.base)
        otra.subs = list(self.subs)
        return otra

    def valor(self, tau: float) -> np.ndarray:
        q = self.base.copy()
        for s in self.subs:
            q += s.valor(tau)
        return q

    def destino(self) -> np.ndarray:
        """Pose en la que quedará el brazo cuando acaben todos los submovimientos."""
        q = self.base.copy()
        for s in self.subs:
            if not s.es_bulto:
                q += s.d
        return q

    def fin(self) -> float:
        return max((s.fin for s in self.subs), default=float("-inf"))

    def activa(self, tau: float) -> bool:
        return any(s.fin > tau for s in self.subs)

    def podar(self, tau: float) -> None:
        """Absorbe en la base los submovimientos ya terminados."""
        vivos = []
        for s in self.subs:
            if s.fin <= tau:
                if not s.es_bulto:
                    self.base += s.d
            else:
                vivos.append(s)
        self.subs = vivos

    def cancelar_pendientes(self, tau: float) -> None:
        """Quita los que aún no han empezado (no aportan nada todavía: no hay salto)."""
        self.subs = [s for s in self.subs if s.t0 <= tau]

    def congelar(self, tau: float) -> None:
        """Fija la pose actual como base. Solo es suave si el ritmo del reloj es cero."""
        self.base = self.valor(tau)
        self.subs = []


MARGEN_TOPE = np.array([5.0, 5.0, 5.0, 5.0, 5.0, 8.0])     # zona de frenado junto a cada tope


def limite_blando(q: np.ndarray, q_min: np.ndarray, q_max: np.ndarray, margen: np.ndarray = MARGEN_TOPE) -> np.ndarray:
    """Comprime con suavidad lo que se acerca al tope de una articulación, en vez de recortarlo en seco."""
    alto, bajo = q_max - margen, q_min + margen
    q = np.where(q > alto, alto + margen * np.tanh((q - alto) / margen), q)
    return np.where(q < bajo, bajo - margen * np.tanh((bajo - q) / margen), q)
