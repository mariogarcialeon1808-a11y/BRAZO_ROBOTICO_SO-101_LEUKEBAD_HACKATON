"""Registro expresivo: comprueba cada movimiento contra el motor de gestos y escribe el documento para supervisarlo.

    python tools/registro_expresivo.py comprobar     # ¿cabe cada movimiento en los dos SO-101? Anota el resultado en el registro
    python tools/registro_expresivo.py documento     # reescribe docs/REGISTRO_EXPRESIVO.md a partir del registro
    python tools/registro_expresivo.py               # las dos cosas

No forma parte del programa: no mueve brazos, no abre puertos y no cambia cómo gesticula hoy el robot.
Solo usa consignas, constantes nominales y la calibración del montaje (distancia entre bases y velocidad
real). La comprobación es la misma que pasa cualquier plan antes de ejecutarse (`control.escenico.validar`):
rangos articulares, velocidad, aceleración y tirón, altura sobre la mesa, distancia a la obra y entre brazos.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
from so101er.control import expresion  # noqa: E402  (las posturas y trayectorias son las del programa)

hacia_fuera, postura = expresion.hacia_fuera, expresion.postura
REGISTRO = RAIZ / 'datos' / 'expresion' / 'registro.json'
DOCUMENTO = RAIZ / 'docs' / 'REGISTRO_EXPRESIVO.md'
ROLES = ('acompana', 'espejo', 'ancla', 'prepara', 'contrapunto', 'libre')
ESTADOS = {'existente': 'Lo hacía ya', 'comprobado': 'En la biblioteca', 'motor': 'Con el motor actual (sin conectar)',
           'no_cabe': 'No cabe tal cual', 'sin_comprobar': 'Sin comprobar'}


def leer() -> dict:
    return json.loads(REGISTRO.read_text(encoding='utf8'))


def escribir(registro: dict) -> None:
    REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + '\n', encoding='utf8', newline='\n')


# ------------------------------------------------------------------ comprobación contra el motor
def montar_motor():
    """Motor de gestos con el montaje y la velocidad de los brazos reales, si están guardados."""
    from so101er.config import cargar
    from so101er.control.semantico import MotorGestos
    cfg = cargar(RAIZ / 'config' / 'so101er.toml')
    cfg.frecuencia_hz = 50
    datos = {'velocidad': float(cfg.limites.velocidad[0]), 'distancia_mm': None}
    try:
        from so101er.aplicacion import perfil_real
        from so101er.hardware.dual_usb import aplicar_montaje, cargar_montaje
        montaje = cargar_montaje(RAIZ)
        aplicar_montaje(cfg, montaje)
        datos = {'velocidad': float(perfil_real(cfg, RAIZ)), 'distancia_mm': float(montaje['distancia_mm'])}
    except Exception as error:                                  # sin montaje guardado: geometría nominal de la simulación
        datos['aviso'] = 'sin montaje real guardado: ' + str(error)
    return MotorGestos(cfg), datos


def trayectoria(motor, claves: dict[str, list]):
    """(tiempos, consignas, instante de la primera postura) de un movimiento que sale de reposo y vuelve a él."""
    return expresion.trayectoria(motor, claves)[:3]


def comprobar_movimiento(motor, movimiento: dict) -> dict:
    """¿Cabe el movimiento con cada brazo como principal? Tiempo total y hasta la primera postura clave."""
    from so101er.cinematica.modelo import FueraDeAlcance
    resultado = {'cabe': True, 'dura_s': {}, 'apice_s': {}}
    brazos = list(motor.marcos)
    for principal in brazos:
        otro = next((b for b in brazos if b != principal), None)
        claves = {principal: movimiento['principal']}
        if otro is not None and movimiento.get('otro'):
            claves[otro] = movimiento['otro']
        try:
            t, _, apice = trayectoria(motor, claves)
            resultado['dura_s'][principal] = round(float(t[-1]), 1)
            resultado['apice_s'][principal] = round(float(apice), 1)
        except (FueraDeAlcance, ValueError) as error:
            resultado['cabe'] = False
            resultado.setdefault('motivo', {})[principal] = str(error)
    return resultado


def comprobar(registro: dict) -> None:
    motor, datos = montar_motor()
    registro['comprobacion'] = {'fecha': date.today().isoformat(), 'velocidad_grados_s': datos['velocidad'],
                                'distancia_entre_bases_mm': datos['distancia_mm'], 'brazos': list(motor.marcos),
                                'nota': datos.get('aviso', 'montaje y velocidad de los brazos reales; sin hardware')}
    for p in registro['primitivas']:
        if p.get('existente'):
            p['motor'] = {'estado': 'existente'}
        elif p.get('movimiento'):
            r = comprobar_movimiento(motor, p['movimiento'])
            p['motor'] = {'estado': 'comprobado' if r.pop('cabe') else 'no_cabe', **r}
        else:
            p['motor'] = {'estado': 'motor' if p.get('con_motor_actual') else 'sin_comprobar'}
        m = p['motor']
        print(f"{p['id']:4} {p['nombre']:26} {m['estado']:13} {m.get('dura_s', '')} {m.get('motivo', '')}")


# ------------------------------------------------------------------ comprobaciones del propio registro
def problemas(registro: dict) -> list[str]:
    """Incoherencias del registro: identificadores repetidos, referencias que no existen, papeles desconocidos."""
    fallos = []
    primitivas = {}
    for p in registro['primitivas']:
        if p['id'] in primitivas:
            fallos.append(f"primitiva repetida: {p['id']}")
        primitivas[p['id']] = p
        if not p.get('existente') and not p.get('movimiento') and not p.get('con_motor_actual'):
            fallos.append(f"{p['id']}: ni existe, ni tiene movimiento definido, ni se indica cómo se haría")
        for campo in ('nombre', 'familia', 'descripcion', 'instruccion', 'origen'):
            if not p.get(campo):
                fallos.append(f"{p['id']}: falta {campo}")
    fuentes = {f['id'] for f in registro['fuentes']}
    familias = {f['id'] for f in registro['familias']}
    dominios = {d['id'] for d in registro['dominios']}
    for p in registro['primitivas']:
        if p['familia'] not in familias:
            fallos.append(f"{p['id']}: familia desconocida {p['familia']}")
        for o in p.get('origen', []):
            if o.split(':')[0] not in fuentes:
                fallos.append(f"{p['id']}: fuente desconocida {o}")
    vistos = set()
    for c in registro['conexiones']:
        if c['id'] in vistos:
            fallos.append(f"conexión repetida: {c['id']}")
        vistos.add(c['id'])
        if c['dominio'] not in dominios:
            fallos.append(f"{c['id']}: dominio desconocido {c['dominio']}")
        for g in [c['principal']] + ([c['otro']['primitiva']] if c['otro'].get('primitiva') else []) + list(c.get('despues', [])):
            if g not in primitivas:
                fallos.append(f"{c['id']}: primitiva desconocida {g}")
        if c['otro']['papel'] not in ROLES:
            fallos.append(f"{c['id']}: papel desconocido {c['otro']['papel']}")
        if c['otro']['papel'] in ('ancla', 'contrapunto') and not c['otro'].get('primitiva'):
            fallos.append(f"{c['id']}: el papel {c['otro']['papel']} necesita decir con qué movimiento")
        if not c.get('concepto') or not c.get('ejemplo'):
            fallos.append(f"{c['id']}: falta concepto o ejemplo")
    return fallos


def estado_conexion(c: dict, primitivas: dict) -> str:
    """Una conexión está tan disponible como el menos disponible de sus movimientos."""
    orden = ['existente', 'comprobado', 'motor', 'sin_comprobar', 'no_cabe']
    usados = [c['principal']] + ([c['otro']['primitiva']] if c['otro'].get('primitiva') else []) + list(c.get('despues', []))
    return max((primitivas[g].get('motor', {}).get('estado', 'sin_comprobar') for g in usados), key=orden.index)


# ------------------------------------------------------------------ documento para supervisar
def documento(registro: dict) -> str:
    primitivas = {p['id']: p for p in registro['primitivas']}
    comp = registro.get('comprobacion', {})
    lineas = ['# Registro expresivo: conceptos y movimientos', '',
              '> Generado por `tools/registro_expresivo.py` a partir de `datos/expresion/registro.json`. '
              'Para cambiar algo, edita el JSON y vuelve a generar; no edites este archivo.', '',
              'Las reglas de uso están en [PROTOCOLO_EXPRESIVO.md](PROTOCOLO_EXPRESIVO.md).', '']
    cuenta = {}
    for p in registro['primitivas']:
        e = p.get('motor', {}).get('estado', 'sin_comprobar')
        cuenta[e] = cuenta.get(e, 0) + 1
    cuenta_c = {}
    for c in registro['conexiones']:
        e = estado_conexion(c, primitivas)
        cuenta_c[e] = cuenta_c.get(e, 0) + 1
    lineas += ['## Resumen', '', f"- **{len(registro['primitivas'])} movimientos** y **{len(registro['conexiones'])} conexiones** concepto → movimiento.", '']
    lineas += ['| Estado | Movimientos | Conexiones |', '|---|---|---|']
    for e, texto in ESTADOS.items():
        if cuenta.get(e) or cuenta_c.get(e):
            lineas.append(f"| {texto} | {cuenta.get(e, 0)} | {cuenta_c.get(e, 0)} |")
    lineas += ['']
    if comp:
        distancia = f"{comp['distancia_entre_bases_mm']:.1f} mm entre bases" if comp.get('distancia_entre_bases_mm') else 'geometría nominal'
        lineas += [f"Comprobado el {comp['fecha']} contra el motor de gestos, a {comp['velocidad_grados_s']:.0f}°/s y {distancia} "
                   f"({comp['nota']}). «Cabe» significa que el movimiento, saliendo de reposo y volviendo a él, respeta rangos, "
                   'velocidad, altura sobre la mesa y distancia a la obra y entre brazos. No significa que se haya visto en los brazos.', '']
    lineas += ['## Estados', '',
               '- **Lo hacía ya:** uno de los gestos de siempre (señalar, región, abanicos, línea, acento).',
               '- **En la biblioteca:** comprobado contra el motor; la IA lo puede pedir con el tipo `gesto` y el programa lo ejecuta.',
               '- **Con el motor actual (sin conectar):** se compone con piezas que el motor ya tiene; sin comprobación propia.',
               '- **No cabe tal cual:** el motor lo rechaza; el motivo está en la tabla.', '',
               '## Papeles del otro brazo', '']
    for r in registro['papeles']:
        lineas.append(f"- **{r['id']}:** {r['descripcion']}")
    lineas += ['', '## Fuentes', '', '| Fuente | Qué aporta | Estado |', '|---|---|---|']
    for f in registro['fuentes']:
        nombre = f"[{f['nombre']}]({f['url']})" if f.get('url') else f['nombre']
        lineas.append(f"| {nombre} (`{f['id']}`) | {f['aporta']} | {f['estado']} |")
    lineas += ['', '## Movimientos', '',
               '«Gráfico» son los que dibujan el concepto: una forma, un trayecto, un tamaño, una cantidad o una acción. '
               'Cada frase tiene que llevar al menos uno.', '']
    for fam in registro['familias']:
        lineas += [f"### {fam['nombre']}", '', fam['descripcion'], '',
                   '| Id | Movimiento | Gráfico | Qué hace | Estado | Dura (izq / der) | Origen |', '|---|---|---|---|---|---|---|']
        for p in registro['primitivas']:
            if p['familia'] != fam['id']:
                continue
            m = p.get('motor', {})
            dura = ' / '.join(f"{m['dura_s'][b]:.1f} s" if b in m.get('dura_s', {}) else '—' for b in comp.get('brazos', [])) if m.get('dura_s') else '—'
            estado = ESTADOS[m.get('estado', 'sin_comprobar')]
            if m.get('motivo'):
                estado += ': ' + '; '.join(f"{b}: {v}" for b, v in m['motivo'].items())
            lineas.append(f"| {p['id']} | {p['nombre']} | {'sí' if p.get('grafico') else ''} | {p['descripcion']} | {estado} | {dura} | {', '.join(p['origen'])} |")
        lineas.append('')
    lineas += ['## Conexiones concepto → movimiento', '',
               'Cada fila dice qué hace el brazo principal y qué hace el otro mientras tanto. '
               '«Después» es el movimiento que encadena el mismo brazo sin pasar por reposo.', '']
    for dom in registro['dominios']:
        filas = [c for c in registro['conexiones'] if c['dominio'] == dom['id']]
        if not filas:
            continue
        lineas += [f"### {dom['nombre']} ({len(filas)})", '', dom['descripcion'], '',
                   '| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |', '|---|---|---|---|---|---|---|']
        for c in filas:
            principal = f"{c['principal']} {primitivas[c['principal']]['nombre']}"
            if c.get('despues'):
                principal += ' → ' + ' → '.join(f"{g} {primitivas[g]['nombre']}" for g in c['despues'])
            otro = c['otro']['papel'] + (f": {c['otro']['primitiva']} {primitivas[c['otro']['primitiva']]['nombre']}" if c['otro'].get('primitiva') else '')
            lineas.append(f"| {c['id']} | {c['concepto']} | «{c['ejemplo']}» | {principal} | {otro} | {ESTADOS[estado_conexion(c, primitivas)]} | {c.get('notas', '')} |")
        lineas.append('')
    lineas += ['## Instrucciones para una política entrenada', '',
               'Si algún día se graban demostraciones para ajustar una política (SmolVLA u otra), esta es la frase de tarea de cada '
               'movimiento. `{brazo}` es `left` o `right`.', '', '| Id | Instrucción |', '|---|---|']
    for p in registro['primitivas']:
        lineas.append(f"| {p['id']} | {p['instruccion']} |")
    return '\n'.join(lineas) + '\n'


def main(argv: list[str]) -> int:
    orden = argv[1] if len(argv) > 1 else 'todo'
    registro = leer()
    fallos = problemas(registro)
    if fallos:
        print('\n'.join(fallos))
        return 1
    if orden in ('comprobar', 'todo'):
        comprobar(registro)
        escribir(registro)
    if orden in ('documento', 'todo'):
        DOCUMENTO.write_text(documento(registro), encoding='utf8', newline='\n')
        print('escrito', DOCUMENTO.relative_to(RAIZ))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
