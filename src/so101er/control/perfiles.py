"""Funciones de forma del movimiento: escalón suave, bulto y deformación temporal."""
from __future__ import annotations

import numpy as np


def escalon(u):
    """Escalón de 7.º grado: 0→1 con velocidad, aceleración y tirón nulos en los extremos."""
    u = np.clip(u, 0.0, 1.0)
    return u**4 * (35.0 - 84.0 * u + 70.0 * u**2 - 20.0 * u**3)


def bulto(u):
    """Sale y vuelve: 0→1→0, con velocidad, aceleración y tirón nulos en los extremos."""
    u = np.clip(u, 0.0, 1.0)
    return 256.0 * u**4 * (1.0 - u) ** 4


def deformar(u, c: float):
    """Desplaza el pico de velocidad. c<1: ataque temprano y llegada larga; c=1: simétrico."""
    u = np.clip(u, 0.0, 1.0)
    return u / (u + c * (1.0 - u))


def c_de_asimetria(alfa: float) -> float:
    """Parámetro c para que la mitad del recorrido se alcance en la fracción `alfa` del tiempo."""
    alfa = float(np.clip(alfa, 0.2, 0.8))
    return alfa / (1.0 - alfa)


def fraccion_inversa(w: float, c: float) -> float:
    """Fracción de tiempo u en la que la deformación vale w."""
    return c * w / (1.0 - w + c * w)


_CACHE: dict[tuple[float, bool], tuple[float, float, float]] = {}


def picos(c: float, es_bulto: bool = False) -> tuple[float, float, float]:
    """Picos de |velocidad|, |aceleración| y |tirón| de un escalón (o bulto) deformado,
    para duración 1 y recorrido 1."""
    clave = (round(c, 3), es_bulto)
    if clave not in _CACHE:
        u = np.linspace(0.0, 1.0, 4001)
        w = deformar(u, c)
        f = bulto(w) if es_bulto else escalon(w)
        v = np.gradient(f, u)
        a = np.gradient(v, u)
        j = np.gradient(a, u)
        _CACHE[clave] = (float(np.max(np.abs(v))), float(np.max(np.abs(a))), float(np.max(np.abs(j))))
    return _CACHE[clave]


def duracion_minima(d: np.ndarray, c: float, es_bulto: bool, v_max: np.ndarray, a_max: np.ndarray,
                    j_max: np.ndarray, margen: tuple[float, float, float] = (0.6, 0.45, 0.3)) -> float:
    """Duración mínima para que un submovimiento de recorrido `d` quepa en los límites.

    Los márgenes dejan sitio para que el reloj del brazo acelere (hasta 1,4×) y para
    que se sumen otros submovimientos.
    """
    kv, ka, kj = picos(c, es_bulto)
    d = np.abs(np.asarray(d, float))
    return float(max(np.max(d * kv / (margen[0] * v_max)),
                     np.sqrt(np.max(d * ka / (margen[1] * a_max))),
                     np.cbrt(np.max(d * kj / (margen[2] * j_max)))))
