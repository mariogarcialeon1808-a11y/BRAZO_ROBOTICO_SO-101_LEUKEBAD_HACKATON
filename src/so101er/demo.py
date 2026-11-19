"""Demostración en simulación: una explicación corta del cuadro sintético.

Se ejecuta por pasos (tiempo simulado), puede guardar un vídeo y devuelve un
informe con las medidas de suavidad, sincronía y seguridad.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .config import Config
from .geometria import distancia_cadenas
from .sincronia.director import Director
from .sincronia.partitura import Partitura
from .sincronia.voz import VozMuda
from .sistema import Sistema

# Partitura de ejemplo para el cuadro sintético (paisaje con sol, montañas, lago, árbol y casa).
DEMO: dict = {
    "titulo": "Paisaje al atardecer",
    "frases": [
        {"texto": "Bienvenidos. Este paisaje nos habla de la calma.", "estilo": "sereno",
         "gestos": [{"tipo": "presentar", "brazo": "todos", "ancla": 0}]},
        {"texto": "Arriba, el sol domina la escena con su luz dorada.", "estilo": "solemne",
         "gestos": [{"tipo": "senalar", "brazo": "der", "params": {"punto": [200, 780], "mantener": 1.0}, "ancla": 2},
                    {"tipo": "elevar", "brazo": "izq", "ancla": 8}]},
        {"texto": "Las montañas dibujan una línea quebrada que cruza todo el cuadro.", "estilo": "didactico",
         "gestos": [{"tipo": "trazar", "brazo": "izq", "ancla": 1,
                     "params": {"puntos": [[600, 30], [370, 180], [540, 330], [310, 480]]}},
                    {"tipo": "trazar", "brazo": "der", "ancla": 6,
                     "params": {"puntos": [[320, 520], [570, 700], [430, 860], [590, 980]]}}]},
        {"texto": "Abajo, el agua del lago se mueve despacio, casi dormida.", "estilo": "tierno",
         "gestos": [{"tipo": "ondular", "brazo": "izq", "ancla": 2,
                     "params": {"desde": [840, 230], "hasta": [840, 480], "ondas": 2}},
                    {"tipo": "descender", "brazo": "der", "ancla": 8}]},
        {"texto": "Por un lado la naturaleza, por otro la casa: lo salvaje y lo humano.", "estilo": "entusiasta",
         "gestos": [{"tipo": "senalar", "brazo": "izq", "params": {"punto": [470, 200], "mantener": 0.8}, "ancla": 4},
                    {"tipo": "senalar", "brazo": "der", "params": {"punto": [620, 680], "mantener": 0.8}, "ancla": 8}]},
        {"texto": "Y todo ello, en un instante suspendido.", "estilo": "misterioso",
         "gestos": [{"tipo": "suspender", "brazo": "todos", "ancla": 5, "params": {"duracion": 1.6}}]},
    ],
}


def medir(muestras: np.ndarray, dt: float) -> dict[str, np.ndarray]:
    """Picos de velocidad, aceleración y tirón de una serie de consignas (filas = ciclos)."""
    v = np.diff(muestras, axis=0) / dt
    a = np.diff(v, axis=0) / dt
    j = np.diff(a, axis=0) / dt
    return {"vel": np.abs(v).max(axis=0), "acel": np.abs(a).max(axis=0), "tiron": np.abs(j).max(axis=0)}


def ejecutar_demo(cfg: Config, partitura: Partitura | None = None, video: str | None = None,
                  dt: float = 0.01, velocidad_voz: float = 1.0, al_fotograma: Any = None) -> dict:
    """Interpreta una partitura en simulación por pasos y devuelve un informe."""
    s = Sistema(cfg)
    subtitulos: list[str] = []
    voz = VozMuda(cfg.voz["silabas_por_segundo"], al_subtitulo=subtitulos.append, velocidad=velocidad_voz)
    d = Director(s, voz)
    visor = escritor = None
    if video or al_fotograma:
        import cv2
        from .interfaz.visor import Visor
        visor = Visor(s)
        if video:
            escritor = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (visor.ancho, visor.alto))
    partitura = partitura or Partitura.de_dict(DEMO)
    for f in partitura.frases:
        for g in f.gestos:
            if g.brazo in ("izq", "der") and g.brazo not in s.nombres:
                g.brazo = s.nombres[0]      # modo un brazo: todo lo hace el brazo disponible
            for clave in ("punto",):
                if visor is not None and clave in g.params:
                    visor.objetivos.append(g.params[clave])
    for _ in range(50):
        s.avanzar(dt)
    d.interpretar(partitura)
    registro: dict[str, list[np.ndarray]] = {n: [] for n in s.nombres}
    dist_min = float("inf")
    paso = 0
    while (d.activo or s.ocupado()) and s.t < 600.0:
        s.avanzar(dt)
        paso += 1
        for n in s.nombres:
            registro[n].append(s.coreos[n].cmd.copy())
        if len(s.nombres) == 2 and paso % 5 == 0:
            a, b = (s.seguridad.cadena_mundo(n, s.coreos[n].cmd) for n in s.nombres)
            dist_min = min(dist_min, distancia_cadenas(a[2:], b[2:]))
        if visor is not None and paso % 4 == 0:
            visor.subtitulo = subtitulos[-1] if subtitulos and d.fase in ("hablando", "pausa") else ""
            visor.muestrear()
            img = visor.dibujar()
            if escritor is not None:
                escritor.write(img)
            if al_fotograma:
                al_fotograma(paso, img)
    for _ in range(100):
        s.avanzar(dt)
        for n in s.nombres:
            registro[n].append(s.coreos[n].cmd.copy())
    if escritor is not None:
        escritor.release()
    lim = cfg.limites
    informe: dict[str, Any] = {"duracion_s": round(s.t, 1), "frases": len(partitura.frases),
                               "alertas": [a for _, a in s.alertas], "brazos": {}}
    for n in s.nombres:
        m = medir(np.array(registro[n]), dt)
        informe["brazos"][n] = {
            "velocidad_max_%": round(float(np.max(m["vel"] / lim.velocidad)) * 100, 1),
            "aceleracion_max_%": round(float(np.max(m["acel"] / lim.aceleracion)) * 100, 1),
            "tiron_max_%": round(float(np.max(m["tiron"] / lim.tiron)) * 100, 1),
        }
    if d.anclas:
        errores = [a["apice"] - a["objetivo"] for a in d.anclas]
        informe["sincronia"] = {"gestos_anclados": len(errores),
                                "adelanto_medio_ms": round(-float(np.mean(errores)) * 1000),
                                "peor_retraso_ms": round(float(max(errores)) * 1000)}
    if len(s.nombres) == 2:
        informe["distancia_min_brazos_mm"] = round(dist_min)
    return informe
