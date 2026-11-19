"""Filtro de seguridad: limita velocidad, aceleración y tirón de cada articulación.

Sigue la referencia exactamente mientras esta respeta los límites; si no,
la alcanza con tirón limitado. Es la última red antes de los motores.
"""
from __future__ import annotations

import numpy as np


class FiltroTiron:
    def __init__(self, q0: np.ndarray, v_max: np.ndarray, a_max: np.ndarray, j_max: np.ndarray,
                 q_min: np.ndarray, q_max: np.ndarray, omega: float = 12.0) -> None:
        self.p = np.asarray(q0, float).copy()
        self.v = np.zeros_like(self.p)
        self.a = np.zeros_like(self.p)
        self.v_max, self.a_max, self.j_max = (np.asarray(x, float) for x in (v_max, a_max, j_max))
        self.q_min, self.q_max = np.asarray(q_min, float), np.asarray(q_max, float)
        self.omega = omega
        self._r1 = self.p.copy()   # referencias anteriores
        self._r2 = self.p.copy()
        self.saturado = False

    def reiniciar(self, q: np.ndarray) -> None:
        self.p = np.asarray(q, float).copy()
        self.v[:] = 0.0
        self.a[:] = 0.0
        self._r1 = self.p.copy()
        self._r2 = self.p.copy()

    def paso(self, ref: np.ndarray, dt: float) -> np.ndarray:
        ref = np.clip(ref, self.q_min, self.q_max)
        v_ant = (self._r1 - self._r2) / dt
        a_ref = np.clip((ref - 2.0 * self._r1 + self._r2) / (dt * dt), -self.a_max, self.a_max)
        w = self.omega
        # Seguimiento con anticipación: con error nulo, a_des = a_ref y el seguimiento es exacto.
        a_des = a_ref + 2.0 * w * (np.clip(v_ant, -self.v_max, self.v_max) - self.v) + w * w * (self._r1 - self.p)
        a_des = np.clip(a_des, -self.a_max, self.a_max)
        # Acercamiento suave al límite de velocidad (frenar la aceleración con tirón limitado).
        margen = 0.8 * self.j_max
        a_sup = np.sqrt(2.0 * margen * np.maximum(self.v_max - self.v, 0.0))
        a_inf = -np.sqrt(2.0 * margen * np.maximum(self.v_max + self.v, 0.0))
        a_des = np.clip(a_des, a_inf, a_sup)
        tiron_pedido = (a_des - self.a) / dt
        tiron = np.clip(tiron_pedido, -self.j_max, self.j_max)
        self.saturado = bool(np.any(np.abs(tiron_pedido) > self.j_max * 1.001))
        self.a = self.a + tiron * dt
        v = self.v + self.a * dt
        tope = np.abs(v) > self.v_max
        if np.any(tope):
            v = np.clip(v, -self.v_max, self.v_max)
            self.a = np.where(tope, 0.0, self.a)
            self.saturado = True
        self.v = v
        self.p = self.p + self.v * dt
        fuera = (self.p < self.q_min) | (self.p > self.q_max)
        if np.any(fuera):
            self.p = np.clip(self.p, self.q_min, self.q_max)
            self.v = np.where(fuera, 0.0, self.v)
            self.a = np.where(fuera, 0.0, self.a)
        self._r2, self._r1 = self._r1, ref.copy()
        return self.p.copy()
