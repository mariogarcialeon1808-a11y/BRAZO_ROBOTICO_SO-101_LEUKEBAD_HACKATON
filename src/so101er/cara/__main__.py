"""`python -m so101er.cara --demo`: la página con turnos falsos en bucle.

Sin audio, sin claves y sin brazos: tiempos sintéticos, reloj falso y la imagen de `obra/`
(o el dibujo de ejemplo). Sirve para ver la cara y medir la página en cualquier sistema.
"""
import argparse
from pathlib import Path
import time

import numpy as np

from . import Cara, leer_seccion, PREDETERMINADO

FS = 24000
GUIA = ['Leukerbad está a unos mil cuatrocientos metros de altura, al final del valle del Dala, '
        'al pie de grandes paredes de roca.',
        'Sus aguas termales salen a hasta cincuenta y un grados durante todo el año.']


def voz_falsa(texto, seg_por_caracter=.062):
    """Audio con sílabas sintéticas (para la boca) y su duración. Sin marcas: tiempos proporcionales."""
    dur = max(1., len(texto) * seg_por_caracter)
    t = np.arange(round(dur * FS)) / FS
    silabas = np.clip(np.sin(2 * np.pi * 4.2 * t), 0, None) ** .6
    pausas = np.ones_like(t)
    for m in [i for i, c in enumerate(texto) if c in ',.;:']:
        a = m / len(texto) * dur
        pausas[(t > a) & (t < a + .25)] = .05
    ruido = np.random.default_rng(0).standard_normal(t.size)
    return (ruido * silabas * pausas * 6000).astype(np.int16)


def imagen(raiz, ruta=None):
    import cv2
    from ..obra import buscar_imagen
    from ..interfaz.visor import cuadro_sintetico
    ruta = Path(ruta) if ruta else buscar_imagen(Path(raiz) / 'obra')
    img = cv2.imread(str(ruta)) if ruta else None
    return img if img is not None else cuadro_sintetico()


def decir(cara, texto, bloques, cortar_en=None, preguntado=''):
    cara.pensando(preguntado)
    time.sleep(1.4)
    audio = voz_falsa(texto)
    t0 = time.perf_counter() + .3                       # como el «previo» del Reproductor
    cara.hablar(texto, [], 1., audio, lambda: time.perf_counter() - t0, bloques)
    dur = len(audio) / FS
    hasta = dur * cortar_en if cortar_en else dur + .15
    while time.perf_counter() - t0 < hasta:
        time.sleep(.05)
    cara.callar(interrumpido=bool(cortar_en))


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m so101er.cara', description=__doc__.split('\n')[0])
    p.add_argument('--demo', action='store_true', help='turnos falsos en bucle')
    p.add_argument('--raiz', default='.')
    p.add_argument('--imagen', help='imagen a mostrar (por defecto, la de obra/ o el dibujo de ejemplo)')
    p.add_argument('--puerto', type=int)
    p.add_argument('--sin-navegador', action='store_true')
    args = p.parse_args(argv)
    if not args.demo:
        p.print_help()
        return 0
    from ..aplicacion import demo_bloques
    cfg = leer_seccion(args.raiz, 'cara', PREDETERMINADO)
    cara = Cara(imagen(args.raiz, args.imagen), print, args.puerto or int(cfg['puerto']), float(cfg['desfase_ms']))
    url = f'http://127.0.0.1:{cara.puerto}/'
    print(f'Cara en {url}  (depuración: {url}?debug=1). Ctrl+C para salir.')
    if not args.sin_navegador:
        import webbrowser
        webbrowser.open(url + '?debug=1')
    demo = demo_bloques()
    texto = ' '.join(b['texto'] for b in demo)
    guia = [{'texto': f, 'tipo': 'paisaje', 'brazo': 'der', 'ancla': 3} for f in GUIA]
    try:
        time.sleep(2)
        while True:
            decir(cara, texto, demo, preguntado='¿Qué se ve en el cuadro?')
            time.sleep(3.5)
            decir(cara, ' '.join(GUIA), guia, preguntado='¿Dónde está Leukerbad?')
            time.sleep(3.5)
            decir(cara, texto, demo, cortar_en=.45, preguntado='Explícame el cuadro otra vez')
            time.sleep(3)
    except KeyboardInterrupt:
        pass
    finally:
        cara.cerrar()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
