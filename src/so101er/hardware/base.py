"""Interfaz mínima de un brazo. El resto del sistema no depende de LeRobot."""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Brazo(Protocol):
    """Un brazo SO-101. Vector de 6 valores: 5 articulaciones en grados + pinza en %."""

    nombre: str

    def conectar(self) -> None: ...
    def desconectar(self) -> None: ...
    def leer_articulaciones(self) -> np.ndarray: ...
    def enviar_objetivo(self, q: np.ndarray) -> None: ...
    def activar_par(self) -> None: ...
    def desactivar_par(self) -> None: ...
    def leer_carga(self) -> np.ndarray: ...          # fracción de la carga máxima, por motor
    def leer_temperatura(self) -> np.ndarray: ...    # °C, por motor
