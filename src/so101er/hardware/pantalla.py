"""Pantalla de exhibición: una ventana aparte con la escena de MuJoCo, la imagen del cuadro y la cara.

Solo dibujo. No lee el estado de ninguna simulación, no decide acciones y, si falla o se cierra,
la sesión sigue igual. La escena es propia (los brazos se colocan según los encoders que se le
pasan) y se dibuja con un `Renderer` de MuJoCo en un hilo aparte; la ventana es de OpenCV.

No se usa el visor pasivo de MuJoCo a propósito: si el usuario cierra su ventana mientras otro
hilo le está enviando una imagen, el proceso entero se cae (comprobado el 15-11-2026), y con
los brazos con par eso no es aceptable. Aquí cerrar con la X es un final ordenado del hilo.
"""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from ..interfaz.cara import Cara

ANCHO, ALTO = 1280, 800      # tamaño al que se dibuja; la ventana lo escala
HZ = 25.0
CUADRO_HZ = 12.0             # como mucho, cambios de imagen del cuadro por segundo
MARGEN = 14                  # píxeles entre la cara y el borde
TITULO = "SO-101 - Pantalla"


def recuadro_cara(ancho: int, alto: int) -> tuple[int, int, int] | None:
    """(izquierda, arriba, lado) de la cara en una imagen de `ancho` × `alto`: esquina superior derecha."""
    lado = int(min(max(0.22 * alto, 110), 240, ancho - 2 * MARGEN, alto - 2 * MARGEN))
    if lado < 60:
        return None
    return ancho - lado - MARGEN, MARGEN, lado


def poner_cara(imagen: np.ndarray, cara: Cara) -> np.ndarray:
    """Dibuja la cara en la esquina de una imagen RGB (la modifica y la devuelve)."""
    r = recuadro_cara(imagen.shape[1], imagen.shape[0])
    if r is not None:
        x, y, lado = r
        imagen[y:y + lado, x:x + lado] = cara.imagen(lado)
    return imagen


class MundoDeExhibicion:
    """La escena que se enseña, ya compilada: los brazos y el cuadro.

    Compilarla ocupa el programa entero durante unas décimas de segundo, y el bucle USB de los
    brazos se queda sin atender mientras tanto («pico de latencia»). Por eso se prepara **antes
    de activar los motores** y luego solo se dibuja; abrir o cerrar la ventana no la vuelve a compilar.
    """

    def __init__(self, cfg, nombres, imagen: np.ndarray) -> None:
        from .mujoco_sim import MundoMuJoCo
        self.mundo = MundoMuJoCo(cfg, list(nombres), imagen)

    def cerrar(self) -> None:
        self.mundo.cerrar()


class Escena:
    """Los brazos, el cuadro y la cara, dibujados fuera de pantalla. Debe usarse siempre desde un mismo hilo.

    Con `exhibicion` se dibuja una escena ya preparada en vez de compilar otra; esa no se cierra al cerrar esta.
    """

    def __init__(self, cfg, nombres, imagen: np.ndarray, ancho: int = ANCHO, alto: int = ALTO,
                 exhibicion: MundoDeExhibicion | None = None) -> None:
        import mujoco as mj
        self.mj = mj
        self._propia = exhibicion is None
        self.exhibicion = exhibicion or MundoDeExhibicion(cfg, nombres, imagen)
        self.mundo = self.exhibicion.mundo
        m = self.mundo.modelo
        if not self._propia:
            self.mundo.cambiar_imagen(imagen)                     # pudo prepararse con otra imagen
            mj.mj_forward(m, self.mundo.datos)
        m.vis.global_.offwidth, m.vis.global_.offheight = max(ancho, int(m.vis.global_.offwidth)), max(alto, int(m.vis.global_.offheight))
        self.renderer = mj.Renderer(m, alto, ancho)
        self.camara = mj.MjvCamera()
        self.camara.lookat[:] = [0.0, 0.27, 0.30]
        self.camara.distance, self.camara.azimuth, self.camara.elevation = 1.55, 100.0, -14.0
        self.cara = Cara()
        self._subida = id(imagen)
        self._siguiente = 0.0

    def colocar(self, poses: dict) -> None:
        for nombre, q in poses.items():
            if q is not None:
                self.mundo.colocar(nombre, q)

    def cuadro(self, clave, imagen: np.ndarray, ahora: float | None = None) -> bool:
        """Pone `imagen` en el cuadro si su `clave` es nueva y ha pasado el intervalo mínimo."""
        ahora = time.perf_counter() if ahora is None else ahora
        if clave == self._subida or imagen is None or ahora < self._siguiente:
            return False
        from .mujoco_sim import subir_textura
        subir_textura(self.mj, self.renderer, self.mundo.modelo, self.mundo.cambiar_imagen(imagen))
        self._subida, self._siguiente = clave, ahora + 1.0 / CUADRO_HZ
        return True

    def girar(self, dx: float, dy: float) -> None:
        self.camara.azimuth = (self.camara.azimuth - 0.3 * dx) % 360.0
        self.camara.elevation = float(np.clip(self.camara.elevation - 0.3 * dy, -89.0, 20.0))

    def acercar(self, pasos: float) -> None:
        self.camara.distance = float(np.clip(self.camara.distance * (0.9 ** pasos), 0.5, 4.0))

    def fotograma(self, nivel: float | None, ahora: float | None = None, expresion=None) -> np.ndarray:
        """La imagen completa (BGR): escena con la cara en la esquina. `nivel` es el volumen de la voz o None.

        `expresion` es (estado, mirada) de la cara de la página, para que la de la esquina haga lo mismo.
        """
        estado, gesto = expresion if expresion else (None, None)
        self.cara.paso(time.perf_counter() if ahora is None else ahora, nivel, estado, gesto)
        self.renderer.update_scene(self.mundo.datos, camera=self.camara)
        return cv2.cvtColor(poner_cara(self.renderer.render(), self.cara), cv2.COLOR_RGB2BGR)

    def cerrar(self) -> None:
        self.renderer.close()
        if self._propia:
            self.exhibicion.cerrar()


class PantallaAparte:
    """Ventana de exhibición en su propio hilo.

    `poses()` → {brazo: articulaciones} según los encoders (un brazo que no se puede leer va como
    None y conserva su última postura). `imagen_cuadro()` → (clave, imagen BGR con la proporción
    del cuadro). `nivel_voz()` → volumen 0–1 o None si no habla. Arrastrar con el ratón gira la
    vista y la rueda acerca. `cerrada` se activa cuando el hilo termina, por la X o por `cerrar()`.
    """

    def __init__(self, cfg, nombres, poses, imagen_cuadro, nivel_voz, titulo: str = TITULO,
                 exhibicion: MundoDeExhibicion | None = None, expresion=None) -> None:
        self.cfg, self.nombres, self.poses, self.imagen_cuadro, self.nivel_voz, self.titulo = cfg, list(nombres), poses, imagen_cuadro, nivel_voz, titulo
        self.expresion = expresion       # () -> (estado, mirada) de la cara de la página, o None
        self.exhibicion = exhibicion
        self.error: str | None = None
        self.cerrada = threading.Event()
        self._lista, self._fin = threading.Event(), threading.Event()
        self._hilo = threading.Thread(target=self._bucle, name="pantalla-de-exhibicion", daemon=True)
        self._hilo.start()
        self._lista.wait(20.0)
        if self.error:
            raise RuntimeError(self.error)

    def _raton(self, evento, x, y, marcas, _):
        if evento == cv2.EVENT_LBUTTONDOWN:
            self._arrastre = (x, y)
        elif evento == cv2.EVENT_MOUSEMOVE and self._arrastre is not None and marcas & cv2.EVENT_FLAG_LBUTTON:
            self._escena.girar(x - self._arrastre[0], y - self._arrastre[1])
            self._arrastre = (x, y)
        elif evento == cv2.EVENT_LBUTTONUP:
            self._arrastre = None
        elif evento == cv2.EVENT_MOUSEWHEEL:
            self._escena.acercar(1.0 if marcas > 0 else -1.0)

    def _bucle(self) -> None:
        escena = None
        try:
            clave, imagen = self.imagen_cuadro()
            self._escena = escena = Escena(self.cfg, self.nombres, imagen, exhibicion=self.exhibicion)
            escena._subida = clave
            self._arrastre = None
            cv2.namedWindow(self.titulo, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
            cv2.resizeWindow(self.titulo, ANCHO * 3 // 4, ALTO * 3 // 4)
            cv2.setMouseCallback(self.titulo, self._raton)
            self._lista.set()
            while not self._fin.is_set():
                inicio = time.perf_counter()
                try:
                    escena.colocar(self.poses())
                except Exception:
                    pass                                          # sin lectura: se queda con la última postura
                escena.cuadro(*self.imagen_cuadro(), ahora=inicio)
                try:
                    expresion = self.expresion() if self.expresion else None
                except Exception:
                    expresion = None
                cv2.imshow(self.titulo, escena.fotograma(self.nivel_voz(), inicio, expresion))
                cv2.waitKey(max(1, int(1000 * (1.0 / HZ - (time.perf_counter() - inicio)))))
                if cv2.getWindowProperty(self.titulo, cv2.WND_PROP_VISIBLE) < 1:      # la han cerrado con la X
                    break
        except Exception as e:                                    # un fallo de dibujo no es un fallo de la sesión
            self.error = str(e) or type(e).__name__
        finally:
            try:
                cv2.destroyWindow(self.titulo)
                cv2.waitKey(1)
            except Exception:
                pass
            if escena is not None:
                try:
                    escena.cerrar()
                except Exception:
                    pass
            self.cerrada.set()
            self._lista.set()

    def cerrar(self) -> None:
        self._fin.set()
        if threading.current_thread() is not self._hilo:
            self._hilo.join(timeout=4.0)
