"""La cara del robot, en pequeño, para la esquina de la Pantalla 3D.

Es la misma cara que la de la página (so101er.cara): ojos azules, boca que se abre con la voz, y el
mismo estado, mirada y ánimo. Es dibujo y nada más: no lee sensores ni decide nada. En silencio se
queda quieta.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

PARPADEO_S = 0.13                 # lo que dura un parpadeo
ENTRE_PARPADEOS_S = (2.2, 4.6)    # mientras habla


def nivel_de_voz(reproductor) -> float | None:
    """Volumen (0–1) de lo que suena ahora en un `Reproductor`, o None si no está sonando voz.

    Mira unos 40 ms de la pista alrededor del instante que sale por el altavoz y los compara
    con el volumen medio de esa misma pista, así no depende de lo alta que venga la voz.
    """
    if reproductor is None or getattr(reproductor, "cerrado", False):
        return None
    try:
        t = reproductor.posicion()
    except RuntimeError:                                          # el altavoz aún no ha dado reloj
        return None
    pista, previo = reproductor.track, reproductor.previo
    i = previo + int(t * reproductor.frecuencia)
    if i < previo or i >= len(pista):
        return None
    trozo = pista[max(previo, i - 480):i + 480].astype(np.float32)
    if getattr(reproductor, "abierto", None) is not None and not trozo.any():
        return None                                               # silencio de espera de un altavoz al que aún le llega audio
    medido, referencia = getattr(reproductor, "_volumen_medio", (0, None))
    if referencia is None or len(pista) > 1.5 * medido:           # la pista puede haber crecido: se vuelve a medir
        voz = pista[previo:].astype(np.float32)
        if getattr(reproductor, "abierto", None) is not None:
            voz = voz[voz != 0]                                   # sin contar los silencios de espera añadidos a la pista
        referencia = float(np.sqrt(np.mean(voz * voz))) if len(voz) else 0.0
        reproductor._volumen_medio = (len(pista), referencia)
    if referencia < 1.0 or not len(trozo):
        return 0.0
    return float(min(1.0, math.sqrt(float(np.mean(trozo * trozo))) / (1.8 * referencia)))


# Lo que sigue reproduce la cara de la página (src/so101er/cara/web/js/eyes.js, de Javier García Pavón) para
# dibujarla en la esquina de la Pantalla 3D: los mismos ojos, estados, mirada y ánimo. Si se cambia allí,
# hay que cambiarlo aquí. Medidas en píxeles de una cara de 1150 de ancho, como en la página; colores en RGB.
CIAN = (60, 220, 255)
ESTADOS = {
    "IDLE":      dict(w=250, h=300, r=0.32, gap=170, lidIn=0.0,  lidOut=0.0,  happy=0.0, lookX=0,  lookY=0,   mouth=0.0, smile=0.0, color=CIAN),
    "LISTENING": dict(w=270, h=330, r=0.36, gap=160, lidIn=0.0,  lidOut=0.0,  happy=0.0, lookX=0,  lookY=-6,  mouth=0.0, smile=0.0, color=(80, 235, 255)),
    "THINKING":  dict(w=240, h=230, r=0.30, gap=175, lidIn=0.12, lidOut=0.18, happy=0.0, lookX=70, lookY=-60, mouth=0.0, smile=0.0, color=CIAN),
    "TALKING":   dict(w=250, h=270, r=0.32, gap=170, lidIn=0.0,  lidOut=0.0,  happy=0.0, lookX=0,  lookY=-20, mouth=1.0, smile=0.0, color=CIAN),
    "ERROR":     dict(w=230, h=200, r=0.18, gap=190, lidIn=0.42, lidOut=0.05, happy=0.0, lookX=0,  lookY=0,   mouth=0.0, smile=0.0, color=(255, 60, 60)),
}
ANIMOS = {
    "neutro":    {},
    "alegre":    dict(happy=0.55, smile=0.35, h=-10, color=(90, 255, 200)),
    "serio":     dict(lidIn=0.15, lidOut=0.03, h=-24),
    "atento":    dict(w=14, h=46, lookY=-6),
    "duda":      dict(lidOut=0.30, lidIn=0.04, lookY=12),
    "pensativo": dict(lidIn=0.10, lidOut=0.16, lookY=-28),
}
MIRADA_X, MIRADA_Y = 95, 60       # cuánto se van los ojos hacia el brazo que gesticula, y arriba o abajo
NUMERICOS = ("w", "h", "r", "gap", "lidIn", "lidOut", "happy", "lookX", "lookY", "mouth", "smile")
GRANDES = ("w", "h", "gap", "lookX", "lookY")


def _redondo(img, x0, y0, x1, y1, radio, color) -> None:
    """Rectángulo relleno de esquinas redondeadas."""
    x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
    r = int(max(0, min(radio, (x1 - x0) / 2, (y1 - y0) / 2)))
    cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), color, -1, cv2.LINE_AA)
    cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), color, -1, cv2.LINE_AA)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
        cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)


class Cara:
    """La cara del robot en pequeño. Quieta en silencio; al hablar mueve la boca con la voz, parpadea y mira.

    `paso` admite además el estado y la mirada de la cara de la página, para que las dos hagan lo mismo.
    """

    def __init__(self, semilla: int = 7) -> None:
        self.boca = 0.0               # apertura, 0 cerrada – 1 abierta
        self.parpadeo = 0.0           # 0 ojos abiertos – 1 cerrados
        self.mirada = 0.0             # −1 izquierda – 1 derecha: el vaivén propio al hablar
        self.estado = "IDLE"
        self.p = {k: float(ESTADOS["IDLE"][k]) for k in NUMERICOS}
        self.color = [float(c) for c in CIAN]
        self._azar = np.random.default_rng(semilla)
        self._t = None
        self._habla_desde = None
        self._parpadea_en = None

    def paso(self, ahora: float, nivel: float | None, estado: str | None = None, gesto: dict | None = None) -> None:
        """Avanza la animación. `nivel` es el volumen de la voz (0–1) o None si no habla.

        `estado` (IDLE, LISTENING, THINKING, TALKING, ERROR) y `gesto` ({lado, vertical, animo}) son los de la
        cara de la página; sin ellos, habla cuando hay voz y descansa cuando no.
        """
        dt = 0.0 if self._t is None else min(0.2, max(0.0, ahora - self._t))
        self._t = ahora
        if estado not in ESTADOS or (nivel is not None and estado == "IDLE"):
            estado = "TALKING" if nivel is not None else "IDLE"
        self.estado = estado
        objetivo, color = dict(ESTADOS[estado]), ESTADOS[estado]["color"]
        if estado == "TALKING":
            g = gesto or {}
            animo = ANIMOS.get(g.get("animo"), {})
            for k in NUMERICOS:
                objetivo[k] += animo.get(k, 0)
            objetivo["lookX"] += float(np.clip(g.get("lado", 0) or 0, -1, 1)) * MIRADA_X
            objetivo["lookY"] -= float(np.clip(g.get("vertical", 0) or 0, -1, 1)) * MIRADA_Y
            color = animo.get("color", color)
        k = 1.0 - math.exp(-dt * 9.0)
        for nombre in NUMERICOS:
            self.p[nombre] += (objetivo[nombre] - self.p[nombre]) * k
            if abs(objetivo[nombre] - self.p[nombre]) < (0.05 if nombre in GRANDES else 0.002):
                self.p[nombre] = float(objetivo[nombre])              # llega del todo: en reposo la imagen no cambia
        for i in range(3):
            self.color[i] += (color[i] - self.color[i]) * (1.0 - math.exp(-dt * 6.0))
            if abs(color[i] - self.color[i]) < 0.5:
                self.color[i] = float(color[i])
        if nivel is None:                                         # sin voz: boca cerrada, ojos al frente, quieta
            self._habla_desde = self._parpadea_en = None
            self.boca = max(0.0, self.boca - dt / 0.10)
            self.parpadeo = max(0.0, self.parpadeo - dt / 0.06)
            self.mirada *= max(0.0, 1.0 - dt / 0.25)
            if self.boca < 0.01 and abs(self.mirada) < 0.01:
                self.boca = self.mirada = 0.0
            return
        if self._habla_desde is None:
            self._habla_desde = ahora
            self._parpadea_en = ahora + float(self._azar.uniform(0.6, 1.6))
        apertura = float(np.clip(nivel, 0.0, 1.0)) ** 0.7
        ritmo = 0.045 if apertura > self.boca else 0.09           # abre deprisa, cierra algo más despacio
        self.boca += (apertura - self.boca) * min(1.0, dt / ritmo)
        desde = ahora - self._parpadea_en
        if desde >= PARPADEO_S:
            self._parpadea_en = ahora + float(self._azar.uniform(*ENTRE_PARPADEOS_S))
            desde = -1.0
        self.parpadeo = math.sin(math.pi * desde / PARPADEO_S) if 0.0 <= desde < PARPADEO_S else 0.0
        self.mirada = 0.55 * math.sin(0.9 * (ahora - self._habla_desde))

    def clave(self) -> tuple[int, int, int]:
        """Boca, parpadeo y vaivén redondeados: (0, 0, 0) cuando no habla."""
        return round(self.boca * 24), round(self.parpadeo * 6), round(self.mirada * 16)

    def imagen(self, lado: int) -> np.ndarray:
        """La cara como imagen RGB de `lado` × `lado`."""
        boca, parpadeo, mirada = (v / d for v, d in zip(self.clave(), (24, 6, 16)))
        p = {k: (round(self.p[k]) if k in GRANDES else round(self.p[k], 2)) for k in NUMERICOS}
        color = tuple(int(round(c)) for c in self.color)
        L = lado * 3                                              # se dibuja al triple y se reduce: bordes suaves
        s = L / 1150.0                                            # con este margen los ojos caben aunque miren a un lado
        img = np.zeros((L, L, 3), np.uint8)
        cx = L / 2 + (p["lookX"] + 40 * mirada) * s
        cy = L * 0.43 + p["lookY"] * s
        ancho = p["w"] * s
        alto = max(4 * s, p["h"] * s * (1.0 - 0.92 * parpadeo))
        for lado_ojo in (-1, 1):
            x = cx + lado_ojo * (p["gap"] * s + ancho / 2)
            _redondo(img, x - ancho / 2, cy - alto / 2, x + ancho / 2, cy + alto / 2, min(ancho, alto) * p["r"], color)
            dentro, fuera, arriba = x - lado_ojo * ancho / 2, x + lado_ojo * ancho / 2, cy - alto / 2
            if p["lidIn"] > 0.005 or p["lidOut"] > 0.005:        # párpado: recorta por arriba, más por un lado que por otro
                margen = 6 * s
                parpado = np.array([[dentro - lado_ojo * margen, arriba - margen], [fuera + lado_ojo * margen, arriba - margen],
                                    [fuera + lado_ojo * margen, arriba + alto * p["lidOut"]],
                                    [dentro - lado_ojo * margen, arriba + alto * p["lidIn"]]])
                cv2.fillPoly(img, [np.round(parpado).astype(np.int32)], (0, 0, 0), cv2.LINE_AA)
            if p["happy"] > 0.01:                                 # ojos alegres: un óvalo tapa la parte de abajo
                cv2.ellipse(img, (int(round(x)), int(round(cy + alto / 2 + alto * 0.15))),
                            (int(round(ancho * 0.75)), int(round(alto * 0.62 * p["happy"]))), 0, 0, 360, (0, 0, 0), -1, cv2.LINE_AA)
        if p["mouth"] > 0.02:
            bx, by = L / 2 + 16 * mirada * s, L * 0.80
            hablar = max(0.0, 1.0 - abs(p["smile"]))
            if hablar > 0.05:                                     # boca que se abre con el volumen de la voz
                tono = tuple(int(c * min(1.0, p["mouth"]) * hablar) for c in color)
                w, h = (120 + 40 * boca) * s, (12 + 78 * boca) * s
                _redondo(img, bx - w / 2, by - h / 2, bx + w / 2, by + h / 2, min(w, h) / 2, tono)
            if abs(p["smile"]) > 0.05:
                w, curva = 170 * s, 50 * s * p["smile"]
                u = np.linspace(0, 1, 24)
                puntos = np.column_stack([bx - w / 2 + w * u,
                                          (1 - u) ** 2 * (by - curva / 2) + 2 * u * (1 - u) * (by + curva * 1.5) + u ** 2 * (by - curva / 2)])
                tono = tuple(int(c * min(1.0, p["mouth"]) * min(1.0, abs(p["smile"]) + 0.4)) for c in color)
                cv2.polylines(img, [np.round(puntos).astype(np.int32)], False, tono, max(2, int(round(16 * s))), cv2.LINE_AA)
        brillo = cv2.GaussianBlur(img, (0, 0), L * 0.022)        # el resplandor de los ojos
        img = np.clip(img.astype(np.float32) + 0.5 * brillo, 0, 255).astype(np.uint8)
        return cv2.resize(img, (lado, lado), interpolation=cv2.INTER_AREA)
