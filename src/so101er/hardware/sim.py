"""Brazo simulado: misma interfaz que el real, con una dinámica de servo sencilla."""
from __future__ import annotations

import threading

import numpy as np


class BrazoSim:
    def __init__(self, nombre: str, q_inicial: np.ndarray, omega: float = 45.0) -> None:
        self.nombre = nombre
        self._q = np.asarray(q_inicial, float).copy()
        self._v = np.zeros(6)
        self._a = np.zeros(6)
        self._objetivo = self._q.copy()
        self._par = False
        self._omega = omega
        self._cerrojo = threading.Lock()
        self.temperatura = np.full(6, 31.0)
        self.carga_extra = np.zeros(6)      # para pruebas: simular un bloqueo

    def conectar(self) -> None:
        self._par = True

    def desconectar(self) -> None:
        self._par = False

    def activar_par(self) -> None:
        with self._cerrojo:
            self._objetivo = self._q.copy()
            self._par = True

    def desactivar_par(self) -> None:
        self._par = False

    def leer_articulaciones(self) -> np.ndarray:
        with self._cerrojo:
            return self._q.copy()

    def enviar_objetivo(self, q: np.ndarray) -> None:
        with self._cerrojo:
            self._objetivo = np.asarray(q, float).copy()

    def leer_carga(self) -> np.ndarray:
        with self._cerrojo:
            return np.clip(np.abs(self._a) / 4000.0 + 0.08 + self.carga_extra, 0.0, 1.0)

    def leer_temperatura(self) -> np.ndarray:
        return self.temperatura.copy()

    def avanzar(self, dt: float) -> None:
        """Integra el servo: 2.º orden críticamente amortiguado hacia el objetivo."""
        with self._cerrojo:
            if not self._par:
                self._v *= 0.9
                self._a[:] = 0.0
            else:
                w = self._omega
                self._a = w * w * (self._objetivo - self._q) - 2.0 * w * self._v
                self._v += self._a * dt
            self._q += self._v * dt
