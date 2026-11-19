"""La obra que se explica: una foto que se deja en la carpeta `obra/`.

Se usa la imagen más reciente de la carpeta. El rectángulo de la obra en la
escena se ajusta a la proporción de la foto, centrado en el configurado.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .config import Config

EXTENSIONES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
CARPETA = Path("obra")


def buscar_imagen(carpeta: Path = CARPETA) -> Path | None:
    if not carpeta.is_dir():
        return None
    fotos = [p for p in carpeta.iterdir() if p.suffix.lower() in EXTENSIONES and not p.name.startswith("_")]
    return max(fotos, key=lambda p: p.stat().st_mtime) if fotos else None


def preparar_adaptada(cfg: Config, carpeta: Path = CARPETA) -> tuple[np.ndarray, str | None]:
    """Imagen de la obra para la aplicación integrada, adaptada al rectángulo configurado.

    A diferencia de `preparar`, no cambia el rectángulo: recorta la imagen o le añade bandas
    hasta que tiene su proporción. Así se puede cambiar de imagen con la sesión abierta sin
    tocar la geometría con la que se planifican los gestos. Devuelve (imagen BGR, nombre en la
    galería o None si es el cuadro de ejemplo o una ruta suelta).
    """
    from .galeria import ErrorImagen, Galeria, adaptar, ejemplo, leer, proporcion
    objetivo = proporcion(cfg)
    galeria = Galeria(carpeta)
    try:
        if cfg.cuadro.imagen:                               # ruta dada a mano (configuración o --imagen)
            return adaptar(leer(Path(cfg.cuadro.imagen)), objetivo)[0], None
        nombre = galeria.seleccion()
        if nombre is not None:
            cfg.cuadro.imagen = str(galeria.carpeta / nombre)
            return galeria.imagen(nombre, objetivo)[0], nombre
    except ErrorImagen as e:
        print(f"Aviso: {e}; se usa el cuadro de ejemplo.")
        cfg.cuadro.imagen = ""
    return adaptar(ejemplo(), objetivo)[0], None


def preparar(cfg: Config, carpeta: Path = CARPETA) -> np.ndarray:
    """Elige la imagen de la obra, ajusta el rectángulo a su proporción y devuelve la imagen (BGR)."""
    from .interfaz.visor import cuadro_sintetico
    ruta = Path(cfg.cuadro.imagen) if cfg.cuadro.imagen else buscar_imagen(carpeta)
    img = cv2.imread(str(ruta)) if ruta else None
    if img is None:
        if ruta:
            print(f"Aviso: no se puede leer la imagen {ruta}; se usa el cuadro de ejemplo.")
        return cuadro_sintetico()
    cfg.cuadro.imagen = str(ruta)
    c = cfg.cuadro
    u, v = c.sup_der - c.sup_izq, c.inf_izq - c.sup_izq
    ancho, alto = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    proporcion = img.shape[0] / img.shape[1]            # alto / ancho de la foto
    if alto / ancho > proporcion:                       # sobra altura
        nuevo_ancho, nuevo_alto = ancho, ancho * proporcion
    else:
        nuevo_ancho, nuevo_alto = alto / proporcion, alto
    centro = c.sup_izq + 0.5 * u + 0.5 * v
    eu, ev = u / ancho, v / alto
    c.sup_izq = centro - 0.5 * nuevo_ancho * eu - 0.5 * nuevo_alto * ev
    c.sup_der = c.sup_izq + nuevo_ancho * eu
    c.inf_izq = c.sup_izq + nuevo_alto * ev
    return img
