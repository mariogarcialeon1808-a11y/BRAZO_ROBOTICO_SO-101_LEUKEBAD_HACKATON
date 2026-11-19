"""Consignas espaciales a partir de referencias visuales y calibración nominal.

El llamante debe aportar píxeles de una imagen rectificada al plano configurado.
Este módulo no recupera profundidad de una foto ni consulta geometría del simulador.
"""
import numpy as np
from ..geometria import validar_punto
from ..cinematica.modelo import FueraDeAlcance
from .semantico import Intencion, unidad, vector


def senalar_plano(motor, punto_yx, brazo, encoders):
    """Señala un píxel del plano calibrado. Apertura de pinza no implica rigidez."""
    punto = validar_punto(punto_yx)
    if brazo not in motor.marcos: raise ValueError("brazo no disponible")
    marco = motor.marcos[brazo]
    target = motor.cuadro.punto_mundo(punto)
    direction = unidad(marco.a_base(target)-motor.modelo.hombro)
    # Encuentra una postura de señalamiento coherente. Compilar comprueba después
    # preparación, separación y límite de ambas cadenas; esto no autoriza motores.
    for alcance in (250.,235.,270.,220.,285.):
        pos = motor.modelo.hombro+alcance*direction
        try:
            motor.inversa_eje(pos,direction,vector(encoders[brazo],6,"encoders")[:5])
        except FueraDeAlcance:
            continue
        p,e = tuple(marco.a_mundo(pos)),tuple(marco.dir_a_mundo(direction))
        return Intencion('senalar',brazo,(p,p),(e,e),pinza=12.,referencia='plano_calibrado')
    raise FueraDeAlcance("no hay postura de señalamiento para ese punto")


def recorrer_mundo(puntos_mm, eje, brazo):
    """Posición y orientación independientes. El eje no se deduce de píxeles."""
    points=tuple(tuple(vector(p,3,"punto")) for p in puntos_mm)
    if not 2<=len(points)<=128: raise ValueError("se requieren 2–128 puntos")
    direction=tuple(unidad(eje))
    return Intencion('recorrer',brazo,points,tuple(direction for _ in points))


def barrer_region(motor, region_yx, brazo, encoders):
    """Barrido que apunta a una región rectangular del plano, no contacto con ella."""
    region=np.array([validar_punto(p) for p in region_yx])
    if region.shape!=(2,2) or np.any(region[1]<=region[0]):
        raise ValueError("región: esquina superior izquierda e inferior derecha")
    y=float(region[:,0].mean())
    refs=[senalar_plano(motor,[y,x],brazo,encoders)
          for x in np.linspace(region[0,1],region[1,1],25)]
    return Intencion('extension',brazo,tuple(g.puntos_mm[0] for g in refs),
                     tuple(g.ejes[0] for g in refs),pinza=55.,referencia='plano_calibrado')
