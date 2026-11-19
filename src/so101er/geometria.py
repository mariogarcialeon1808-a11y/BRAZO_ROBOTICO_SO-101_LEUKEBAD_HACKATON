"""Geometría de la escena: la obra como plano, los marcos de los brazos y distancias."""
from __future__ import annotations

import math

import numpy as np


class ErrorPunto(ValueError):
    """Un punto de imagen no es válido."""


def validar_punto(p) -> np.ndarray:
    """Comprueba un punto [y, x] en coordenadas de imagen 0–1000 (formato de ER 2)."""
    try:
        v = np.array(p, dtype=float)
    except (TypeError, ValueError):
        raise ErrorPunto(f"punto no válido: {p!r}. Se espera [y, x] con valores de 0 a 1000") from None
    if v.shape != (2,) or not np.all(np.isfinite(v)):
        raise ErrorPunto(f"punto no válido: {p!r}. Se espera [y, x] con valores de 0 a 1000")
    if np.any(v < 0) or np.any(v > 1000):
        raise ErrorPunto(f"punto fuera de la imagen: {p!r}. Los valores [y, x] van de 0 a 1000")
    return v


class Cuadro:
    """La obra: un plano en el mundo. Convierte puntos de imagen [y, x] en puntos 3D."""

    def __init__(self, sup_izq, sup_der, inf_izq, homografia: np.ndarray | None = None,
                 lado_brazos: np.ndarray | None = None) -> None:
        self.origen = np.asarray(sup_izq, float)
        self.u = np.asarray(sup_der, float) - self.origen     # borde superior (izq → der)
        self.v = np.asarray(inf_izq, float) - self.origen     # borde izquierdo (arriba → abajo)
        self.ancho = float(np.linalg.norm(self.u))
        self.alto = float(np.linalg.norm(self.v))
        n = np.cross(self.u, self.v)
        self.normal = n / np.linalg.norm(n)
        if lado_brazos is not None and self.distancia(lado_brazos) < 0:
            self.normal = -self.normal
        # Imagen (x, y en 0–1000) → obra normalizada (0–1). Identidad si la cámara ve justo la obra.
        self.homografia = np.diag([1e-3, 1e-3, 1.0]) if homografia is None else np.asarray(homografia, float)

    def imagen_a_obra(self, punto_yx) -> tuple[float, float]:
        """[y, x] de imagen (0–1000) → (s, t) en la obra: s de izq a der, t de arriba abajo."""
        y, x = validar_punto(punto_yx)
        h = self.homografia @ np.array([x, y, 1.0])
        return float(h[0] / h[2]), float(h[1] / h[2])

    def obra_a_imagen(self, s: float, t: float) -> np.ndarray:
        h = np.linalg.solve(self.homografia, np.array([s, t, 1.0]))
        return np.array([h[1] / h[2], h[0] / h[2]])    # [y, x]

    def punto_mundo(self, punto_yx) -> np.ndarray:
        s, t = self.imagen_a_obra(punto_yx)
        return self.origen + s * self.u + t * self.v

    def distancia(self, p: np.ndarray) -> float:
        """Distancia con signo al plano (positiva en el lado de los brazos)."""
        return float(np.dot(np.asarray(p, float) - self.origen, self.normal))

    def interseccion(self, origen: np.ndarray, direccion: np.ndarray) -> tuple[float, float] | None:
        """Punto (s, t) de la obra al que apunta un rayo, o None si no la mira."""
        den = float(np.dot(direccion, self.normal))
        if den > -1e-6:
            return None
        k = -self.distancia(origen) / den
        if k <= 0:
            return None
        p = origen + k * direccion - self.origen
        return float(np.dot(p, self.u) / self.ancho**2), float(np.dot(p, self.v) / self.alto**2)


class Marco:
    """Posición de la base de un brazo en el mundo."""

    def __init__(self, base_mm: np.ndarray, orientacion_grados: float) -> None:
        a = math.radians(orientacion_grados)
        c, s = math.cos(a), math.sin(a)
        self.rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        self.pos = np.asarray(base_mm, float)

    def a_mundo(self, p: np.ndarray) -> np.ndarray:
        return np.asarray(p) @ self.rot.T + self.pos

    def a_base(self, p: np.ndarray) -> np.ndarray:
        return (np.asarray(p) - self.pos) @ self.rot

    def dir_a_mundo(self, d: np.ndarray) -> np.ndarray:
        return np.asarray(d) @ self.rot.T

    def dir_a_base(self, d: np.ndarray) -> np.ndarray:
        return np.asarray(d) @ self.rot


def distancia_segmentos(p1, q1, p2, q2) -> float:
    """Distancia mínima entre los segmentos p1–q1 y p2–q2."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    if a < 1e-12 and e < 1e-12:
        return float(np.linalg.norm(r))
    if a < 1e-12:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = float(d1 @ r)
        if e < 1e-12:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = float(d1 @ d2)
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > 1e-12 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    return float(np.linalg.norm(p1 + d1 * s - (p2 + d2 * t)))


def distancia_cadenas(a: np.ndarray, b: np.ndarray) -> float:
    """Distancia mínima entre dos cadenas de puntos (los eslabones de dos brazos)."""
    mejor = float("inf")
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            mejor = min(mejor, distancia_segmentos(a[i], a[i + 1], b[j], b[j + 1]))
    return mejor
