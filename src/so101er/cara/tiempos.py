"""Tiempos de la cara: palabras, envolvente de la boca y anclas de cada bloque. Sin E/S.

Todo se mide en segundos de la voz final (ya estirada si hizo falta), el mismo reloj que
`Reproductor.posicion()`.
"""
import re

import numpy as np

from ..aplicacion_servicios import tiempo_ancla

FRECUENCIA = 24000


def palabras(texto, marks, duracion, escala=1.0):
    """Una entrada por `\\S+` de `texto`: {t, ini, fin}.

    `duracion` es la de la voz ORIGINAL (antes de estirar): `tiempo_ancla` trabaja con ella,
    como en `_turno`. Con `escala` se pasa al reloj de la voz final.
    """
    found = list(re.finditer(r'\S+', texto))
    starts = []
    for i in range(len(found)):
        t = float(tiempo_ancla(texto, i, marks, duracion)) * escala
        starts.append(max(t, starts[-1]) if starts else max(t, 0.))
    total = max(duracion * escala, starts[-1] if starts else 0.)
    return [{'t': m.group(), 'ini': round(starts[i], 3),
             'fin': round(starts[i + 1] if i + 1 < len(starts) else total, 3)} for i, m in enumerate(found)]


def envolvente(audio, paso=0.02, frecuencia=FRECUENCIA):
    """RMS del audio cada `paso` s, normalizada 0-1 y con 2 decimales."""
    a = np.asarray(audio, dtype=np.float32).ravel()
    n = max(1, round(paso * frecuencia))
    if a.size == 0:
        return []
    a = np.r_[a, np.zeros((-a.size) % n, np.float32)]
    rms = np.sqrt(np.mean(a.reshape(-1, n) ** 2, axis=1))
    top = float(np.percentile(rms, 98))
    if top <= 1e-6:
        return [0.] * len(rms)
    return [round(float(v), 2) for v in np.clip(rms / top, 0, 1)]


def anclas(bloques, lista):
    """Bloques con `punto` o `region`: {tipo, punto|region, ancla_s, p0, p1}.

    El índice del ancla es `palabras_anteriores + ancla`, como en `_turno`; p0 y p1 son la
    primera y la última palabra de su frase dentro de `lista` (salida de `palabras`).
    """
    out = []
    offset = 0
    for b in bloques or []:
        n = len(str(b.get('texto', '')).split())
        donde = 'punto' if b.get('punto') is not None else 'region' if b.get('region') is not None else None
        if donde and n and lista:
            i = min(offset + max(0, int(b.get('ancla', 0) or 0)), offset + n - 1, len(lista) - 1)
            out.append({'tipo': b.get('tipo'), donde: [list(map(float, p)) for p in b[donde]] if donde == 'region'
                        else list(map(float, b[donde])),
                        'ancla_s': lista[i]['ini'], 'p0': min(offset, len(lista) - 1),
                        'p1': min(offset + n - 1, len(lista) - 1)})
        offset += n
    return out


def turno(id_, texto, marks, escala, audio, bloques, obra_v=0, paso=0.02, frecuencia=FRECUENCIA, duracion=None):
    """El evento `turno` completo para el navegador.

    `duracion` es la prevista cuando aún no ha llegado toda la voz (turno frase a frase): la boca y las
    palabras de lo que falta se corrigen con el evento siguiente de la misma frase.
    """
    escala = float(escala or 1.)
    duracion = max(len(audio) / frecuencia, float(duracion or 0.))
    lista = palabras(texto, marks, duracion / escala, escala)
    return {'id': id_, 'texto': texto, 'palabras': lista, 'duracion': round(duracion, 3),
            'boca': envolvente(audio, paso, frecuencia), 'paso': paso,
            'bloques': anclas(bloques, lista), 'obra_v': obra_v}
