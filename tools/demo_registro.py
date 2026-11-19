"""Demostración en simulación del registro expresivo: graba vídeo, no mueve brazos ni cambia el programa.

    python tools/demo_registro.py conversacion    # la conversación de ejemplo del protocolo, con los dos brazos
    python tools/demo_registro.py catalogo        # los movimientos nuevos, uno a uno, con su rótulo: un vídeo por familia
    python tools/demo_registro.py catalogo E M02  # solo esas familias o esos movimientos, en un vídeo
    python tools/demo_registro.py prueba          # tres imágenes fijas para ver el encuadre

Los vídeos quedan en salidas/expresion/. La escena es la del programa (dos SO-101 con el montaje y la velocidad
reales) con física simulada: los brazos siguen las consignas a través de sus actuadores, y el seguimiento se mide
con los encoders simulados, igual que hace el control. Cada trayectoria pasa antes la validación de siempre.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import registro_expresivo as H  # noqa: E402

SALIDA = RAIZ / 'salidas' / 'expresion'
ANCHO, ALTO, FRANJA, FPS = 960, 540, 110, 25
NOMBRE = {'der': 'Derecho', 'izq': 'Izquierdo'}


# ------------------------------------------------------------------ rótulos (con acentos: los dibuja Windows)
def rotulos(textos: list[tuple[str, str]]) -> dict[tuple[str, str], np.ndarray]:
    """Una franja de imagen por cada (título, línea). cv2 no escribe acentos, así que las dibuja System.Drawing."""
    carpeta = SALIDA / '_rotulos'
    carpeta.mkdir(parents=True, exist_ok=True)
    unicos = list(dict.fromkeys(textos))
    lista = [{'archivo': str(carpeta / f'r{i:03d}.png'), 'titulo': t, 'linea': s} for i, (t, s) in enumerate(unicos)]
    (carpeta / 'lista.json').write_text(json.dumps(lista, ensure_ascii=False), encoding='utf8')
    guion = (
        "Add-Type -AssemblyName System.Drawing;"
        f"$l = Get-Content -Raw -Encoding UTF8 '{carpeta / 'lista.json'}' | ConvertFrom-Json;"
        "$f1 = New-Object System.Drawing.Font('Segoe UI', 17, [System.Drawing.FontStyle]::Bold);"
        "$f2 = New-Object System.Drawing.Font('Segoe UI', 12.5);"
        "foreach ($r in $l) {"
        f" $b = New-Object System.Drawing.Bitmap({ANCHO}, {FRANJA});"
        " $g = [System.Drawing.Graphics]::FromImage($b);"
        " $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias;"
        " $g.Clear([System.Drawing.Color]::FromArgb(22, 24, 28));"
        f" $g.DrawString($r.titulo, $f1, [System.Drawing.Brushes]::White, (New-Object System.Drawing.RectangleF(16, 10, {ANCHO - 32}, 44)));"
        f" $g.DrawString($r.linea, $f2, [System.Drawing.Brushes]::Gainsboro, (New-Object System.Drawing.RectangleF(17, 54, {ANCHO - 34}, 52)));"
        " $g.Dispose(); $b.Save($r.archivo, [System.Drawing.Imaging.ImageFormat]::Png); $b.Dispose() }"
    )
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', guion], check=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return {(r['titulo'], r['linea']): cv2.imdecode(np.fromfile(r['archivo'], np.uint8), cv2.IMREAD_COLOR) for r in lista}


# ------------------------------------------------------------------ componer los dos brazos paso a paso
def componer(motor, pasos: list[dict]):
    """Trayectoria de los dos brazos a partir de pasos simultáneos. Devuelve (tiempos, consignas, [(inicio, fin) de cada paso]).

    Cada paso dice a qué postura va cada brazo (`None`: se queda donde está; `"reposo"`) y cuánto sostiene después.
    Empieza en reposo y, tras el último paso, vuelve a él. Es la misma cuenta de tiempos que la comprobación del registro.
    """
    from so101er.control.escenico import pose_reposo, validar
    lim = motor.cfg.limites
    brazos = list(motor.marcos)
    actual = {b: pose_reposo(motor, b) for b in brazos}
    filas = {b: [actual[b]] for b in brazos}
    pausas = []
    for paso in pasos + [{b: 'reposo' for b in brazos}]:
        for b in brazos:
            clave = paso.get(b)
            if clave is not None:
                actual[b] = H.postura(motor, b, clave, actual[b][:5])
            filas[b].append(actual[b])
        pausas.append(float(paso.get('pausa', 0.0)))
    holgura = 1.12
    for _ in range(6):
        tiempos, consignas, tramos = [0.0], {b: [filas[b][0]] for b in brazos}, []
        for i in range(len(pausas)):
            dur = 0.3
            for b in brazos:
                d = np.abs(filas[b][i + 1] - filas[b][i])
                dur = max(dur, float(np.max(1.875 * d / lim.velocidad)), float(np.sqrt(np.max(5.78 * d / lim.aceleracion))),
                          float(np.cbrt(np.max(60 * d / lim.tiron))))
            dur *= holgura
            n = max(2, math.ceil(dur * motor.cfg.frecuencia_hz))
            s = np.linspace(0, 1, n + 1)[1:]
            suave = (s ** 3 * (10 + s * (-15 + 6 * s)))[:, None]
            inicio = tiempos[-1]
            for b in brazos:
                consignas[b].extend(filas[b][i] + suave * (filas[b][i + 1] - filas[b][i]))
            tiempos.extend(inicio + s * dur)
            quietos = round(pausas[i] * motor.cfg.frecuencia_hz)
            if quietos:
                for b in brazos:
                    consignas[b].extend([filas[b][i + 1]] * quietos)
                tiempos.extend(tiempos[-1] + (np.arange(quietos) + 1) / motor.cfg.frecuencia_hz)
            tramos.append((inicio, tiempos[-1]))
        t, poses = np.array(tiempos), {b: np.array(v) for b, v in consignas.items()}
        try:
            validar(motor, t, poses)
            return t, poses, tramos
        except ValueError as error:
            if 'movimiento' not in str(error):
                raise
            holgura *= 1.2
    raise ValueError('no se pudo ajustar a los límites de velocidad')


# ------------------------------------------------------------------ escena y grabación
class Escena:
    def __init__(self, motor):
        from so101er import galeria
        from so101er.control.escenico import pose_reposo
        from so101er.hardware.mujoco_sim import MundoMuJoCo
        cfg = motor.cfg
        imagen = galeria.adaptar(galeria.ejemplo(), galeria.proporcion(cfg))[0]
        self.motor, self.mundo = motor, MundoMuJoCo(cfg, cfg.brazos_activos, imagen)
        self.brazos = {n: self.mundo.brazo(n, pose_reposo(motor, n)) for n in motor.marcos}
        self.mundo.modelo.vis.global_.offwidth, self.mundo.modelo.vis.global_.offheight = ANCHO, ALTO
        self.render = self.mundo.mj.Renderer(self.mundo.modelo, ALTO, ANCHO)
        self.camara = self.mundo.mj.MjvCamera()
        self.camara.lookat[:] = [0.0, 0.17, 0.24]
        self.camara.distance, self.camara.azimuth, self.camara.elevation = 1.38, 97, -21
        for _ in range(300):                                    # que la física se asiente en reposo
            self.mundo.paso_fisico()

    def cuadro(self, consigna: dict, franja: np.ndarray) -> tuple[np.ndarray, float]:
        """Avanza un fotograma de física hacia `consigna` y devuelve la imagen y el error de seguimiento medido."""
        for n, q in consigna.items():
            self.brazos[n].enviar_objetivo(q)
        for _ in range(round(1 / FPS / self.mundo.modelo.opt.timestep)):
            self.mundo.paso_fisico()
        error = max(float(np.max(np.abs(self.brazos[n].leer_articulaciones()[:5] - q[:5]))) for n, q in consigna.items())
        self.render.update_scene(self.mundo.datos, camera=self.camara)
        imagen = np.zeros((ALTO + FRANJA, ANCHO, 3), np.uint8)
        imagen[:ALTO] = cv2.cvtColor(self.render.render(), cv2.COLOR_RGB2BGR)
        imagen[ALTO:] = franja
        return imagen, error

    def cerrar(self):
        self.render.close()
        self.mundo.cerrar()


def grabar(escena, video, t, poses, texto_en, franjas) -> float:
    """Graba la trayectoria. `texto_en(t)` da el (título, línea) de cada instante. Devuelve el mayor error de seguimiento."""
    peor = 0.0
    paso = round(escena.motor.cfg.frecuencia_hz / FPS)
    for i in range(0, len(t), paso):
        imagen, error = escena.cuadro({n: q[i] for n, q in poses.items()}, franjas[texto_en(float(t[i]))])
        video.write(imagen)
        peor = max(peor, error)
    return peor


def sin_acentos(texto: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if not unicodedata.combining(c))


def abrir_video(nombre: str):
    SALIDA.mkdir(parents=True, exist_ok=True)
    return cv2.VideoWriter(str(SALIDA / nombre), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (ANCHO, ALTO + FRANJA))


# ------------------------------------------------------------------ la conversación de ejemplo
def conversacion(motor, registro):
    P = {p['id']: p for p in registro['primitivas']}

    def k(id_, i, **cambios):
        clave = dict(P[id_]['movimiento']['principal'][i])
        clave.update(cambios)
        return clave

    escucha = 'Los dos brazos: postura de escucha (M23), quietos'
    frases = [
        ('(escucha la pregunta) «¿Cómo llego al ayuntamiento?»', escucha),
        ('«Está cerca, a unos cinco minutos a pie.»', 'Derecho: un poco (M25)   ·   Izquierdo: se prepara para «avanzar recto»'),
        ('«Siga recto por esta calle hasta la plaza.»', 'Izquierdo: avanzar recto (E04) y clavar (E17), encadenados   ·   Derecho: se prepara para el giro'),
        ('«Allí gire a la derecha.»', 'Derecho: girar hacia fuera (E05)   ·   Izquierdo: se prepara para «subir»'),
        ('«Verá el ayuntamiento, un edificio alto con una torre.»', 'Izquierdo: subir (E08)   ·   Derecho: marca la base (E16)'),
        ('«¿Quiere que se lo marque en el mapa?»', 'Derecho: ceder el turno (M24)   ·   Izquierdo: vuelve a reposo'),
        ('(espera la respuesta)', escucha),
        ('', 'Vuelta a reposo'),
    ]
    pasos = [
        {'frase': 0, 'der': k('M23', 0, pausa=0), 'izq': k('M23', 0, pausa=0), 'pausa': 2.4},
        {'frase': 1, 'der': k('M25', 0), 'izq': k('E04', 0)},
        {'frase': 1, 'der': k('M25', 1), 'pausa': 0.4},
        {'frase': 2, 'izq': k('E04', 1), 'der': k('E05', 0)},
        {'frase': 2, 'izq': k('E17', 0)},
        {'frase': 2, 'izq': k('E17', 1), 'pausa': 0.25},
        {'frase': 3, 'der': k('E05', 1), 'izq': k('E08', 0)},
        {'frase': 3, 'der': k('E05', 2), 'pausa': 0.3},
        {'frase': 4, 'izq': k('E08', 1), 'der': k('E16', 0, z=135), 'pausa': 0.6},
        {'frase': 5, 'der': k('M24', 0), 'izq': 'reposo', 'pausa': 0.7},
        {'frase': 6, 'der': k('M23', 0, pausa=0), 'izq': k('M23', 0, pausa=0), 'pausa': 2.0},
    ]
    # Cada frase dura al menos lo que se tarda en decirla (2,25 palabras por segundo): si el gesto acaba antes, se sostiene.
    for _ in range(2):
        t, poses, tramos = componer(motor, pasos)
        for f, (texto, _) in enumerate(frases[1:6], start=1):
            suyos = [i for i, p in enumerate(pasos) if p['frase'] == f]
            falta = len(texto.strip('«»¿?.').split()) / 2.25 - (tramos[suyos[-1]][1] - tramos[suyos[0]][0])
            if falta > 0.05:
                pasos[suyos[-1]]['pausa'] = pasos[suyos[-1]].get('pausa', 0.0) + falta
    t, poses, tramos = componer(motor, pasos)
    limites = [(tramos[i][0], frases[p['frase']]) for i, p in enumerate(pasos)] + [(tramos[-1][0], frases[7])]

    def texto_en(instante):
        actual = limites[0][1]
        for inicio, frase in limites:
            if instante >= inicio:
                actual = frase
        return actual

    franjas = rotulos(frases)
    escena = Escena(motor)
    video = abrir_video('conversacion_ayuntamiento.mp4')
    try:
        error = grabar(escena, video, t, poses, texto_en, franjas)
    finally:
        video.release()
        escena.cerrar()
    informe = {'video': 'conversacion_ayuntamiento.mp4', 'dura_s': round(float(t[-1]), 1), 'error_seguimiento_max_grados': round(error, 1),
               'frases': [{'texto': frases[f][0], 'de_s': round(min(tramos[i][0] for i, p in enumerate(pasos) if p['frase'] == f), 1),
                           'a_s': round(max(tramos[i][1] for i, p in enumerate(pasos) if p['frase'] == f), 1)} for f in range(7)]}
    (SALIDA / 'conversacion_ayuntamiento.json').write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(informe, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ el catálogo
def catalogo(motor, registro, solo: list[str], nombre: str):
    """Graba en `nombre`.mp4 los movimientos de las familias o identificadores de `solo`, uno tras otro."""
    ejemplo = {}
    for c in registro['conexiones']:
        ejemplo.setdefault(c['principal'], c['ejemplo'])
    familias = {f['id']: f['nombre'].split(':')[0] for f in registro['familias']}
    brazos = list(motor.marcos)
    clips = []
    for i, p in enumerate(q for q in registro['primitivas'] if q.get('movimiento') and (q['id'] in solo or q['familia'] in solo)):
        dos = bool(p['movimiento'].get('otro'))
        principal = brazos[i % 2] if not dos else brazos[0]
        otro = next(b for b in brazos if b != principal)
        claves = {principal: p['movimiento']['principal']}
        if dos:
            claves[otro] = p['movimiento']['otro']
        t, poses, _ = H.trayectoria(motor, claves)
        quien = 'los dos brazos' if dos else f'brazo {NOMBRE[principal].lower()}'
        rotulo = (f"{p['id']} · {p['nombre']}", f"«{ejemplo.get(p['id'], '')}»   ·   {familias[p['familia']]}, {quien}")
        clips.append((p, t, poses, rotulo))
    franjas = rotulos([c[3] for c in clips])
    escena = Escena(motor)
    video = abrir_video(nombre + '.mp4')
    informe, reloj = [], 0.0
    try:
        for p, t, poses, rotulo in clips:
            error = grabar(escena, video, t, poses, lambda _t, r=rotulo: r, franjas)
            quieto = {n: q[-1] for n, q in poses.items()}
            for _ in range(round(0.5 * FPS)):                   # medio segundo en reposo entre uno y otro
                video.write(escena.cuadro(quieto, franjas[rotulo])[0])
            informe.append({'id': p['id'], 'nombre': p['nombre'], 'empieza_s': round(reloj, 1), 'dura_s': round(float(t[-1]), 1),
                            'error_seguimiento_max_grados': round(error, 1)})
            reloj += float(t[-1]) + 0.5
            print(f"{p['id']} {p['nombre']:28} a los {informe[-1]['empieza_s']:6.1f} s  seguimiento {error:4.1f}°", flush=True)
    finally:
        video.release()
        escena.cerrar()
    (SALIDA / (nombre + '.json')).write_text(
        json.dumps({'dura_s': round(reloj, 1), 'movimientos': informe}, ensure_ascii=False, indent=1), encoding='utf8')
    print(f'{len(informe)} movimientos, {reloj / 60:.1f} min; mayor error de seguimiento {max(m["error_seguimiento_max_grados"] for m in informe):.1f}°')


def prueba(motor, registro):
    """Tres imágenes fijas para comprobar el encuadre y los rótulos."""
    P = {p['id']: p for p in registro['primitivas']}
    escena = Escena(motor)
    franjas = rotulos([('B03 · expandir', '«La zona verde se ha ampliado.»   ·   Bimanuales, los dos brazos')])
    franja = next(iter(franjas.values()))
    try:
        for id_ in ('B03', 'E05', 'M21'):
            claves = {'der': P[id_]['movimiento']['principal']}
            if P[id_]['movimiento'].get('otro'):
                claves['izq'] = P[id_]['movimiento']['otro']
            t, poses, apice = H.trayectoria(motor, claves)
            fin = int(np.searchsorted(t, apice + 1.2))
            for i in range(0, fin, 2):
                imagen, _ = escena.cuadro({n: q[i] for n, q in poses.items()}, franja)
            cv2.imencode('.png', imagen)[1].tofile(str(SALIDA / f'prueba_{id_}.png'))
            for i in range(fin, len(t), 2):
                escena.cuadro({n: q[i] for n, q in poses.items()}, franja)
    finally:
        escena.cerrar()
    print('imágenes en', SALIDA)


def main(argv):
    orden = argv[1] if len(argv) > 1 else 'conversacion'
    SALIDA.mkdir(parents=True, exist_ok=True)
    registro = H.leer()
    motor, datos = H.montar_motor()
    print('motor:', datos)
    if orden == 'conversacion':
        conversacion(motor, registro)
    elif orden == 'catalogo':
        familias = {f['id']: f for f in registro['familias']}
        if len(argv) == 3 and argv[2] in familias:
            catalogo(motor, registro, [argv[2]], 'catalogo_' + argv[2] + '_' + sin_acentos(familias[argv[2]]['nombre'].split(':')[0].split()[0].lower()))
        elif argv[2:]:
            catalogo(motor, registro, argv[2:], 'catalogo_' + '_'.join(argv[2:]))
        else:
            for f in registro['familias']:
                catalogo(motor, registro, [f['id']], 'catalogo_' + f['id'] + '_' + sin_acentos(f['nombre'].split(':')[0].split()[0].lower()))
    elif orden == 'prueba':
        prueba(motor, registro)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
