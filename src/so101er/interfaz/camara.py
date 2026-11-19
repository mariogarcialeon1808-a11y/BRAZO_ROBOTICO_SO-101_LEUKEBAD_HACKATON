"""Cámara. En simulación dibuja la obra con la marca de adónde apunta cada brazo."""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .visor import COLORES, cuadro_sintetico


class CamaraSim:
    """Cámara sintética: ve exactamente la obra (la homografía es la identidad)."""

    def __init__(self, sistema: Any, ancho: int = 768) -> None:
        self.s = sistema
        proporcion = sistema.cuadro.alto / sistema.cuadro.ancho
        alto = int(ancho * proporcion)
        ruta = sistema.cfg.cuadro.imagen
        obra = cv2.imread(ruta) if ruta else None
        self.obra = cv2.resize(obra, (ancho, alto)) if obra is not None else cuadro_sintetico(ancho, alto)

    def fotograma(self) -> np.ndarray:
        img = self.obra.copy()
        alto, ancho = img.shape[:2]
        for n in self.s.nombres:
            p = self.s.apunta(n, self.s.coreos[n].cmd)
            if p is not None and 0 <= p[0] <= 1000 and 0 <= p[1] <= 1000:
                c = (int(p[1] / 1000 * ancho), int(p[0] / 1000 * alto))
                cv2.circle(img, c, 14, COLORES[n], 3, cv2.LINE_AA)
                cv2.putText(img, n, (c[0] + 16, c[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORES[n], 2, cv2.LINE_AA)
        return img

    def imagenes(self) -> list[tuple[str, bytes]]:
        return [("Cámara frente a la obra. Los puntos [y, x] se dan sobre esta imagen. Los círculos marcan "
                 "adónde apunta cada brazo.", self.jpeg())]

    def jpeg(self, calidad: int = 80) -> bytes:
        ok, datos = cv2.imencode(".jpg", self.fotograma(), [cv2.IMWRITE_JPEG_QUALITY, calidad])
        if not ok:
            raise RuntimeError("no se pudo codificar el fotograma")
        return datos.tobytes()
