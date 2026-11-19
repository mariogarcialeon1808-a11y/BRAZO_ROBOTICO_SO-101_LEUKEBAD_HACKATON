"""Visor de la simulación: la obra con los puntos señalados, los brazos y su velocidad."""
from __future__ import annotations

import unicodedata
from collections import deque
from typing import Any, Callable

import cv2
import numpy as np

COLORES = {"izq": (80, 170, 255), "der": (120, 220, 120)}    # BGR
FONDO = (28, 26, 24)
GRIS = (150, 150, 150)


def _ascii(texto: str) -> str:
    """Las fuentes de OpenCV no tienen tildes: se quitan solo para dibujar."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def cuadro_sintetico(ancho: int = 760, alto: int = 478) -> np.ndarray:
    """Un paisaje sencillo para la simulación: cielo, sol, montañas, lago, árbol y casa."""
    img = np.zeros((alto, ancho, 3), np.uint8)
    for y in range(alto):
        k = y / alto
        img[y, :] = (int(215 - 70 * k), int(170 + 20 * k), int(120 + 90 * k))
    cv2.circle(img, (int(0.78 * ancho), int(0.2 * alto)), int(0.07 * ancho), (120, 225, 250), -1)
    montes = np.array([[0, 0.62], [0.18, 0.36], [0.33, 0.55], [0.5, 0.3], [0.7, 0.58], [0.86, 0.42], [1, 0.6],
                       [1, 1], [0, 1]]) * [ancho, alto]
    cv2.fillPoly(img, [montes.astype(np.int32)], (110, 100, 90))
    cv2.rectangle(img, (0, int(0.62 * alto)), (ancho, alto), (70, 130, 80), -1)
    cv2.ellipse(img, (int(0.5 * ancho), int(0.84 * alto)), (int(0.3 * ancho), int(0.09 * alto)), 0, 0, 360,
                (190, 140, 70), -1)
    cv2.rectangle(img, (int(0.19 * ancho), int(0.5 * alto)), (int(0.21 * ancho), int(0.68 * alto)), (40, 70, 100), -1)
    cv2.circle(img, (int(0.2 * ancho), int(0.46 * alto)), int(0.07 * ancho), (50, 120, 40), -1)
    x0, y0, x1, y1 = int(0.62 * ancho), int(0.56 * alto), int(0.74 * ancho), int(0.7 * alto)
    cv2.rectangle(img, (x0, y0), (x1, y1), (180, 200, 225), -1)
    cv2.fillPoly(img, [np.array([[x0 - 8, y0], [(x0 + x1) // 2, y0 - 34], [x1 + 8, y0]], np.int32)], (50, 60, 160))
    cv2.rectangle(img, (0, 0), (ancho - 1, alto - 1), (40, 80, 130), 6)
    return img


class Visor:
    def __init__(self, sistema: Any, ancho: int = 1280, alto: int = 720) -> None:
        self.s = sistema
        self.ancho, self.alto = ancho, alto
        cfg = sistema.cfg.cuadro
        proporcion = sistema.cuadro.alto / sistema.cuadro.ancho
        self.obra_w = 760
        self.obra_h = int(min(self.obra_w * proporcion, 500))
        obra = cv2.imread(cfg.imagen) if cfg.imagen else None
        self.obra = cv2.resize(obra, (self.obra_w, self.obra_h)) if obra is not None \
            else cuadro_sintetico(self.obra_w, self.obra_h)
        self.rastro: dict[str, deque] = {n: deque(maxlen=160) for n in sistema.nombres}
        self.velocidad: dict[str, deque] = {n: deque(maxlen=420) for n in sistema.nombres}
        self._punta_prev: dict[str, np.ndarray] = {}
        self._t_prev = None
        self.subtitulo = ""
        self.objetivos: deque = deque(maxlen=6)      # puntos pedidos [y, x]

    # ------------------------------------------------------------ datos
    def muestrear(self) -> None:
        s = self.s
        t = s.ahora()
        dt = None if self._t_prev is None else max(t - self._t_prev, 1e-4)
        self._t_prev = t
        for n in s.nombres:
            q = s.coreos[n].cmd
            self.rastro[n].append(s.apunta(n, q))
            punta = s.marcos[n].a_mundo(s.modelo.punta(q[:5])[0])
            if dt is not None and n in self._punta_prev:
                self.velocidad[n].append(float(np.linalg.norm(punta - self._punta_prev[n]) / dt))
            self._punta_prev[n] = punta

    # ------------------------------------------------------------ dibujo
    def dibujar(self) -> np.ndarray:
        s = self.s
        img = np.full((self.alto, self.ancho, 3), FONDO, np.uint8)
        ox, oy = 20, 20
        obra = self.obra.copy()
        for p in self.objetivos:
            c = (int(p[1] / 1000 * self.obra_w), int(p[0] / 1000 * self.obra_h))
            cv2.drawMarker(obra, c, (255, 255, 255), cv2.MARKER_CROSS, 18, 2)
        for n in s.nombres:
            pts = [p for p in self.rastro[n]]
            for i in range(1, len(pts)):
                if pts[i] is None or pts[i - 1] is None:
                    continue
                a = (int(pts[i - 1][1] / 1000 * self.obra_w), int(pts[i - 1][0] / 1000 * self.obra_h))
                b = (int(pts[i][1] / 1000 * self.obra_w), int(pts[i][0] / 1000 * self.obra_h))
                grosor = 1 + int(3 * i / len(pts))
                cv2.line(obra, a, b, COLORES[n], grosor, cv2.LINE_AA)
            if pts and pts[-1] is not None:
                c = (int(pts[-1][1] / 1000 * self.obra_w), int(pts[-1][0] / 1000 * self.obra_h))
                cv2.circle(obra, c, 10, COLORES[n], 2, cv2.LINE_AA)
                cv2.circle(obra, c, 3, COLORES[n], -1, cv2.LINE_AA)
        img[oy:oy + self.obra_h, ox:ox + self.obra_w] = obra

        self._vista(img, 800, 20, 460, 250, "Vista frontal", eje_v=2, rango_v=(0, 620))
        self._vista(img, 800, 285, 460, 235, "Vista superior", eje_v=1, rango_v=(-160, 620))

        # Velocidad de la punta
        gx, gy, gw, gh = 20, 540, 760, 110
        cv2.rectangle(img, (gx, gy), (gx + gw, gy + gh), (50, 48, 46), 1)
        cv2.putText(img, "Velocidad de la punta (mm/s)", (gx + 6, gy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, GRIS, 1,
                    cv2.LINE_AA)
        tope = max(300.0, max((max(v) for v in self.velocidad.values() if v), default=300.0))
        for n in s.nombres:
            v = list(self.velocidad[n])
            if len(v) > 1:
                xs = gx + gw - (len(v) - np.arange(len(v))) * gw / 420
                ys = gy + gh - 4 - np.array(v) / tope * (gh - 24)
                cv2.polylines(img, [np.stack([xs, ys], 1).astype(np.int32)], False, COLORES[n], 1, cv2.LINE_AA)

        # Estado
        y = 545
        for n in s.nombres:
            c = s.coreos[n]
            estado = "EMERGENCIA" if c.emergencia else ("detenido" if c.detenido else c.gesto_actual)
            cv2.putText(img, _ascii(f"{n}: {estado}  ritmo {c.reloj.ritmo:.2f}"), (805, y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORES[n], 1, cv2.LINE_AA)
            y += 24
        if s.alertas:
            cv2.putText(img, _ascii("! " + s.alertas[-1][1])[:60], (805, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (90, 90, 255), 1, cv2.LINE_AA)
        if self.subtitulo:
            texto = _ascii(self.subtitulo)[:110]
            cv2.putText(img, texto, (20, 695), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 235, 235), 1, cv2.LINE_AA)
        return img

    def _vista(self, img: np.ndarray, x0: int, y0: int, w: int, h: int, titulo: str, eje_v: int,
               rango_v: tuple[float, float]) -> None:
        s = self.s
        cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (50, 48, 46), 1)
        cv2.putText(img, titulo, (x0 + 6, y0 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, GRIS, 1, cv2.LINE_AA)
        rango_x = (-520.0, 520.0)
        escala = min(w / (rango_x[1] - rango_x[0]), h / (rango_v[1] - rango_v[0]))

        def px(p: np.ndarray) -> tuple[int, int]:
            return (int(x0 + w / 2 + p[0] * escala), int(y0 + h - 6 - (p[eje_v] - rango_v[0]) * escala))

        c = s.cuadro
        esquinas = [c.origen, c.origen + c.u, c.origen + c.u + c.v, c.origen + c.v]
        cv2.polylines(img, [np.array([px(e) for e in esquinas], np.int32)], True, (60, 110, 170), 2, cv2.LINE_AA)
        if eje_v == 2:
            cv2.line(img, px(np.array([rango_x[0], 0, 0.0])), px(np.array([rango_x[1], 0, 0.0])), (80, 80, 80), 1)
        for n in s.nombres:
            cadena = s.seguridad.cadena_mundo(n, s.coreos[n].cmd)
            pts = np.array([px(p) for p in cadena], np.int32)
            cv2.polylines(img, [pts], False, COLORES[n], 3, cv2.LINE_AA)
            for p in pts[1:-1]:
                cv2.circle(img, tuple(int(v) for v in p), 3, (230, 230, 230), -1, cv2.LINE_AA)
            apertura = 3 + int(s.coreos[n].cmd[5] / 12)
            cv2.circle(img, tuple(int(v) for v in pts[-1]), apertura, COLORES[n], 1, cv2.LINE_AA)

    # ------------------------------------------------------------ ventana
    def punto_de_clic(self, x: int, y: int) -> list[float] | None:
        """Convierte un clic en la ventana en un punto [y, x] de la obra, o None."""
        if 20 <= x < 20 + self.obra_w and 20 <= y < 20 + self.obra_h:
            return [round((y - 20) / self.obra_h * 1000, 1), round((x - 20) / self.obra_w * 1000, 1)]
        return None

    def bucle_ventana(self, fin: Any, al_escape: Callable[[], None],
                      al_clic: Callable[[list[float]], None] | None = None, fps: float = 30.0) -> None:
        """Muestra la ventana hasta que `fin` se active. Debe ejecutarse siempre en el mismo hilo."""
        nombre = "so101er"
        cv2.namedWindow(nombre, cv2.WINDOW_AUTOSIZE)

        def raton(evento: int, x: int, y: int, *_: Any) -> None:
            if evento == cv2.EVENT_LBUTTONDOWN and al_clic:
                p = self.punto_de_clic(x, y)
                if p:
                    al_clic(p)

        cv2.setMouseCallback(nombre, raton)
        while not fin.is_set():
            self.muestrear()
            cv2.imshow(nombre, self.dibujar())
            tecla = cv2.waitKey(int(1000 / fps)) & 0xFF
            if tecla == 27:          # Esc
                al_escape()
            try:
                if cv2.getWindowProperty(nombre, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
        cv2.destroyAllWindows()
