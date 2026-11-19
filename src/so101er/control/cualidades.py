"""Cualidades expresivas del movimiento (esfuerzos de Laban) y su traducción a dinámica."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace

import numpy as np

from .perfiles import c_de_asimetria


@dataclass(frozen=True)
class Cualidades:
    amplitud: float = 0.7    # 0 pequeño … 1 amplio
    peso: float = 0.0        # −1 ligero … +1 firme
    tiempo: float = -0.3     # −1 sostenido … +1 súbito
    espacio: float = 0.0     # −1 indirecto … +1 directo
    flujo: float = -0.3      # −1 libre … +1 contenido
    curvatura: float = 0.4   # 0 recto … 1 muy curvo
    tension: float = 0.3     # 0 relajado … 1 tenso

    def con(self, **cambios: float) -> "Cualidades":
        return replace(self, **cambios).validada()

    def validada(self) -> "Cualidades":
        rangos = {"amplitud": (0.0, 1.0), "curvatura": (0.0, 1.0), "tension": (0.0, 1.0)}
        valores = {}
        for f in fields(self):
            lo, hi = rangos.get(f.name, (-1.0, 1.0))
            valores[f.name] = float(min(max(float(getattr(self, f.name)), lo), hi))
        return Cualidades(**valores)

    @staticmethod
    def nombres() -> list[str]:
        return [f.name for f in fields(Cualidades)]


@dataclass(frozen=True)
class Dinamica:
    """Parámetros concretos del motor de movimiento derivados de unas cualidades."""
    factor_duracion: float
    c: float                  # asimetría del ritmo
    retardos: np.ndarray      # sucesión hombro → pinza (s)
    anticipacion: float       # fracción del recorrido, en sentido contrario, antes de salir
    rebase: float             # fracción del recorrido que se pasa y recupera al llegar
    arco: float               # altura del arco como fracción de la cuerda
    arrastre: float           # ganancia del arrastre de muñeca
    respiracion: float        # factor de la respiración
    acento: float             # tamaño de los acentos


def dinamica(q: Cualidades) -> Dinamica:
    sostenido = (1.0 - q.tiempo) / 2.0     # 1 = sostenido, 0 = súbito
    libre = (1.0 - q.flujo) / 2.0          # 1 = libre, 0 = contenido
    indirecto = (1.0 - q.espacio) / 2.0    # 1 = indirecto, 0 = directo
    firme = (1.0 + q.peso) / 2.0           # 1 = firme, 0 = ligero
    etapa = 0.02 + 0.07 * libre + 0.04 * indirecto      # retardo por etapa de la sucesión
    return Dinamica(
        factor_duracion=0.75 + 0.65 * sostenido,
        c=c_de_asimetria(0.36 + 0.14 * sostenido),
        retardos=np.array([0.0, 0.0, 1.0, 2.0, 2.0, 3.0]) * etapa,
        anticipacion=0.03 + 0.05 * firme * (1.0 - sostenido),
        rebase=0.07 * libre * (1.0 - 0.5 * firme),
        arco=q.curvatura * (0.12 + 0.2 * indirecto),
        arrastre=(0.25 + 0.75 * libre) * (1.0 - 0.6 * q.tension),
        respiracion=1.0 - 0.7 * q.tension,
        acento=0.6 + 0.8 * firme,
    )


ESTILOS_BASE: dict[str, Cualidades] = {
    "neutro": Cualidades(),
    "solemne": Cualidades(amplitud=0.6, peso=0.5, tiempo=-0.9, espacio=0.5, flujo=0.3, curvatura=0.3, tension=0.4),
    "entusiasta": Cualidades(amplitud=0.95, peso=0.2, tiempo=0.4, espacio=0.2, flujo=-0.7, curvatura=0.5, tension=0.3),
    "misterioso": Cualidades(amplitud=0.5, peso=-0.6, tiempo=-0.8, espacio=-0.8, flujo=-0.2, curvatura=0.9, tension=0.5),
    "didactico": Cualidades(amplitud=0.65, peso=0.3, tiempo=0.0, espacio=0.9, flujo=0.4, curvatura=0.2, tension=0.4),
    "tierno": Cualidades(amplitud=0.45, peso=-0.8, tiempo=-0.6, espacio=-0.3, flujo=-0.6, curvatura=0.7, tension=0.1),
    "dramatico": Cualidades(amplitud=1.0, peso=0.9, tiempo=0.3, espacio=0.4, flujo=-0.4, curvatura=0.5, tension=0.7),
}
