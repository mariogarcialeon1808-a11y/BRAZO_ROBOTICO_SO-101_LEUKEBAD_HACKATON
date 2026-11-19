"""Seguridad local: validación de poses y de planes completos antes de aceptarlos."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..cinematica.modelo import Cinematica
from ..config import Limites
from ..geometria import Cuadro, Marco, distancia_cadenas
from .linea import Linea, limite_blando


@dataclass
class BrazoSeguro:
    modelo: Cinematica
    marco: Marco


class Seguridad:
    def __init__(self, limites: Limites, cuadro: Cuadro, separacion_obra_mm: float,
                 brazos: dict[str, BrazoSeguro], zona_compartida: dict) -> None:
        self.lim = limites
        self.cuadro = cuadro
        self.separacion = separacion_obra_mm
        self.brazos = brazos
        self.zona = zona_compartida

    def cadena_mundo(self, nombre: str, q: np.ndarray) -> np.ndarray:
        b = self.brazos[nombre]
        return b.marco.a_mundo(b.modelo.puntos(q[:5]))

    def problema_pose(self, nombre: str, q: np.ndarray, cadena: np.ndarray | None = None,
                      margen: float = 0.0, margen_articular: float = 0.5) -> str | None:
        """Devuelve una descripción del problema de una pose, o None si es segura."""
        m = self.brazos[nombre].modelo
        if np.any(q[:5] < m.lim_inf - margen_articular) or np.any(q[:5] > m.lim_sup + margen_articular):
            return "una articulación saldría de su rango"
        cadena = self.cadena_mundo(nombre, q) if cadena is None else cadena
        movil = cadena[4:]       # muñeca, giro y punta
        if float(np.min(movil[:, 2])) < self.lim.altura_min_mm - margen:
            return f"la pinza bajaría de la altura mínima sobre la mesa ({self.lim.altura_min_mm:.0f} mm)"
        if float(np.min(cadena[3:, 2])) < 5.0 - margen:
            return "el codo tocaría la mesa"
        dist_obra = min(self.cuadro.distancia(p) for p in cadena[3:])
        if dist_obra < self.separacion - margen:
            return f"el brazo se acercaría a {max(dist_obra, 0):.0f} mm de la obra (mínimo {self.separacion:.0f})"
        return None

    def problema_par(self, cadenas: dict[str, np.ndarray], margen: float = 0.0) -> str | None:
        if len(cadenas) < 2:
            return None
        a, b = list(cadenas.values())[:2]
        d = distancia_cadenas(a[2:], b[2:])
        if d < self.lim.distancia_min_brazos_mm - margen:
            return (f"los brazos se acercarían a {d:.0f} mm "
                    f"(mínimo {self.lim.distancia_min_brazos_mm:.0f})")
        if self.zona.get("activa"):
            x0, x1 = float(self.zona["x_min_mm"]), float(self.zona["x_max_mm"])
            dentro = [x0 <= c[-1][0] <= x1 or x0 <= c[-2][0] <= x1 for c in (a, b)]
            if all(dentro):
                return "los dos brazos estarían a la vez en la zona compartida"
        return None

    def verificar(self, lineas: dict[str, Linea], desde: float, hasta: float,
                  paso: float = 0.05) -> str | None:
        """Simula las líneas de todos los brazos y devuelve el primer problema, o None."""
        if hasta <= desde:
            hasta = desde + paso
        n = int(min(max((hasta - desde) / paso, 2), 1200))
        for tau in np.linspace(desde, hasta, n + 1):
            cadenas = {}
            for nombre, linea in lineas.items():
                m = self.brazos[nombre].modelo
                # Se verifica lo que de verdad se mandará: con el límite blando de las articulaciones.
                q = limite_blando(linea.valor(float(tau)), np.append(m.lim_inf, 0.0), np.append(m.lim_sup, 100.0))
                cadenas[nombre] = self.cadena_mundo(nombre, q)
                problema = self.problema_pose(nombre, q, cadenas[nombre])
                if problema:
                    return f"brazo {nombre}: {problema}"
            problema = self.problema_par(cadenas)
            if problema:
                return problema
        return None
