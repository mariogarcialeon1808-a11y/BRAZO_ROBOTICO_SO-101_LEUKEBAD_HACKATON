"""Biblioteca de movimientos expresivos: los del registro, convertidos en planes que el control ejecuta.

El registro (`datos/expresion/registro.json`) describe cada movimiento con unas pocas posturas clave de la
pinza. Aquí se resuelven esas posturas con la cinemática nominal, se unen con arranques y paradas suaves
dentro de los límites de velocidad y se valida el recorrido entero, igual que cualquier otro plan.

Solo intervienen consignas y constantes: las posturas del registro, los límites configurados y la postura
de partida prevista. No se lee ningún sensor ni estado del simulador; antes de ejecutar el plan, el turno
comprueba con los encoders que el brazo está donde el plan empieza. Las reglas de uso están en
docs/PROTOCOLO_EXPRESIVO.md.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REGISTRO = Path(__file__).resolve().parents[3] / 'datos' / 'expresion' / 'registro.json'


@lru_cache(maxsize=4)
def cargar(ruta: str | None = None) -> dict:
    """El registro, o uno vacío si el archivo no está: sin biblioteca el programa sigue con sus gestos de siempre."""
    try:
        return json.loads(Path(ruta or REGISTRO).read_text(encoding='utf8'))
    except (OSError, ValueError):
        return {'primitivas': [], 'conexiones': [], 'familias': []}


def disponibles(ruta: str | None = None) -> dict[str, dict]:
    """Movimientos que se pueden pedir: los que tienen posturas y pasaron la comprobación contra el motor."""
    return {p['id']: p for p in cargar(ruta)['primitivas']
            if p.get('movimiento') and p.get('motor', {}).get('estado') == 'comprobado'}


def de_dos_brazos(primitiva: dict) -> bool:
    return bool(primitiva['movimiento'].get('otro'))


def graficos(ruta: str | None = None) -> set[str]:
    """Movimientos que dibujan el concepto: una forma, un trayecto, un tamaño, una cantidad o una acción."""
    return {id_ for id_, p in disponibles(ruta).items() if p.get('grafico')}


def bloque_grafico(bloque: dict, ruta: str | None = None) -> bool:
    """¿Lleva este bloque de la IA algún movimiento gráfico? Los abanicos y la línea de siempre también lo son."""
    dibujan = graficos(ruta)
    if bloque.get('tipo') in ('paisaje', 'cielo', 'camino'):
        return True
    return bloque.get('otro') in dibujan or (bloque.get('tipo') == 'gesto' and bloque.get('movimiento') in dibujan)


def texto_para_ia(ruta: str | None = None) -> str:
    """Lo que se añade a las instrucciones de la IA para que pueda elegir de la biblioteca. Vacío si no hay."""
    movimientos = disponibles(ruta)
    if not movimientos:
        return ''
    lineas = [
        'BIBLIOTECA DE MOVIMIENTOS. Estas reglas sustituyen a las de longitud y de gesto anteriores.',
        'Responde en 3 a 5 bloques de una frase de 14 a 18 palabras. Cada bloque expresa DOS conceptos con el cuerpo, uno por',
        'brazo. Uno de los dos es obligatoriamente GRÁFICO: dibuja con el brazo la forma, el trayecto, el tamaño, la cantidad,',
        'el orden o la acción de lo que se dice. Escribe cada frase alrededor de algo que se pueda dibujar así.',
        'Formato A, sin coordenadas:',
        '{"texto":"...","tipo":"gesto","brazo":"der","grafico":"E05","ancla":3,"apoyo":"M20","ancla_apoyo":0}',
        '"grafico" es obligatorio: un movimiento de las listas GRÁFICOS. Lo hace el brazo indicado y "ancla" es el índice de la',
        'palabra que dibuja. "apoyo" es el segundo concepto: cualquier otro movimiento de un brazo, gráfico o no, que hace el',
        'otro brazo; "ancla_apoyo" es el índice de su palabra, distinta de la primera. Si "grafico" es de DOS BRAZOS, sin "apoyo".',
        'Formato B, solo para algo concreto que se ve en la imagen: senalar o region como antes y, además, obligatorio,',
        '"grafico":"E10","ancla_grafico":7 con un movimiento GRÁFICO de un brazo: mientras un brazo señala, el otro dibuja.',
        'En el formato B, "ancla" es el índice de la palabra que nombra lo señalado, no la primera de la frase.',
        'Ejemplos: «gire a la derecha y cruce el puente sobre el río»: grafico E05 en «gire», apoyo E10 en «río». «Abre de',
        'nueve a dos»: grafico M12 en «nueve», apoyo M15 en «Abre». «Un edificio alto con una torre»: grafico E08 en «alto»,',
        'apoyo E16 en «torre». «El sol brilla sobre las montañas»: senalar el sol y grafico E10 en «montañas».',
        'Cada movimiento se usa una sola vez por turno si hay otro que sirva, y el brazo principal se alterna. Para izquierda',
        'o derecha usa el brazo de ese lado. No dediques un bloque a saludar: el saludo (M20) va como "apoyo" de un bloque',
        'que ya dibuja algo.',
    ]
    def lista(titulo, filtro):
        elegidos = [f"{id_} {p['nombre']}: {p['descripcion']}" for id_, p in movimientos.items() if filtro(p)]
        if elegidos:
            lineas.append(titulo)
            lineas.extend(elegidos)
    lista('GRÁFICOS de un brazo:', lambda p: p.get('grafico') and not de_dos_brazos(p))
    lista('GRÁFICOS de DOS BRAZOS:', lambda p: p.get('grafico') and de_dos_brazos(p))
    lista('De apoyo, de un brazo (dirección, trato, permiso, tono): solo acompañando a uno gráfico.', lambda p: not p.get('grafico') and not de_dos_brazos(p))
    lista('De apoyo, de DOS BRAZOS (trato): solo en saludos, despedidas y avisos.', lambda p: not p.get('grafico') and de_dos_brazos(p))
    return '\n' + '\n'.join(lineas) + '\n'


# ------------------------------------------------------------------ de posturas clave a trayectoria
def hacia_fuera(motor, brazo: str) -> float:
    """Signo del eje lateral de la base que aleja del otro brazo."""
    marco = motor.marcos[brazo]
    centro = np.mean([m.pos for m in motor.marcos.values()], axis=0)
    return 1.0 if marco.rot[:, 1] @ (marco.pos - centro) >= 0 else -1.0


def postura(motor, brazo: str, clave, semilla) -> np.ndarray:
    """Las seis consignas de una postura clave: `"reposo"` o {r, az, z, elev, giro, pinza}.

    r: mm en horizontal desde el eje de giro de la base · az: grados, 0 al frente, positivo hacia fuera ·
    z: mm sobre la mesa · elev: inclinación de la pinza · giro: giro de muñeca · pinza: 0 cerrada, 100 abierta.
    """
    from .escenico import pose_reposo
    if clave == 'reposo':
        return pose_reposo(motor, brazo)
    modelo = motor.modelo
    az = math.radians(clave.get('az', 0.0)) * hacia_fuera(motor, brazo)
    pos = [modelo.eje_pan[0] + clave['r'] * math.cos(az), modelo.eje_pan[1] + clave['r'] * math.sin(az), clave['z']]
    q = modelo.inversa(pos, elevacion=clave.get('elev'), giro=clave.get('giro', 0.0), semilla=semilla)
    return np.r_[q, float(clave.get('pinza', 35.0))]


def trayectoria(motor, claves: dict[str, list], inicio: dict | None = None):
    """Pasa por las posturas clave de cada brazo y vuelve a reposo. Los brazos se mueven a la vez, tramo a tramo.

    `inicio` es la postura de partida prevista de cada brazo (por defecto, reposo). Devuelve
    (tiempos, consignas, instante de la primera postura, instante en que empieza la vuelta).
    Lanza ValueError o FueraDeAlcance si el recorrido no cabe: no se emite nada en ese caso.
    """
    from .escenico import pose_reposo, validar
    lim = motor.cfg.limites
    n = max(len(v) for v in claves.values())
    puntos, pausas = {}, [0.0] * n
    for brazo in motor.marcos:
        lista = list(claves.get(brazo) or [])
        lista += ['reposo' if not lista else lista[-1]] * (n - len(lista))
        reposo = pose_reposo(motor, brazo)
        q = reposo if inicio is None else np.asarray(inicio[brazo], float)
        fila = [q]
        for i, clave in enumerate(lista):
            q = postura(motor, brazo, clave, q[:5])
            fila.append(q)
            if isinstance(clave, dict):
                pausas[i] = max(pausas[i], float(clave.get('pausa', 0.0)))
        fila.append(reposo)
        puntos[brazo] = fila
    holgura = 1.12
    for _ in range(6):
        tiempos, consignas, apice, vuelta = [0.0], {b: [p[0]] for b, p in puntos.items()}, 0.0, 0.0
        for i in range(n + 1):
            if i == n:
                vuelta = tiempos[-1]
            dur = 0.35
            for fila in puntos.values():
                d = np.abs(fila[i + 1] - fila[i])
                dur = max(dur, float(np.max(1.875 * d / lim.velocidad)), float(np.sqrt(np.max(5.78 * d / lim.aceleracion))),
                          float(np.cbrt(np.max(60 * d / lim.tiron))))
            dur *= holgura
            pasos = max(2, math.ceil(dur * motor.cfg.frecuencia_hz))
            s = np.linspace(0, 1, pasos + 1)[1:]
            suave = (s ** 3 * (10 + s * (-15 + 6 * s)))[:, None]
            for b, fila in puntos.items():
                consignas[b].extend(fila[i] + suave * (fila[i + 1] - fila[i]))
            tiempos.extend(tiempos[-1] + s * dur)
            if i == 0:
                apice = tiempos[-1]
            if i < n and pausas[i] > 0:                              # sostener la postura clave
                quietos = max(1, round(pausas[i] * motor.cfg.frecuencia_hz))
                for b, fila in puntos.items():
                    consignas[b].extend([fila[i + 1]] * quietos)
                tiempos.extend(tiempos[-1] + (np.arange(quietos) + 1) / motor.cfg.frecuencia_hz)
        t = np.array(tiempos)
        poses = {b: np.array(v) for b, v in consignas.items()}
        try:
            validar(motor, t, poses)
            return t, poses, float(apice), float(vuelta)
        except ValueError as error:
            if 'movimiento' not in str(error):
                raise
            holgura *= 1.2
    raise ValueError('el movimiento no se ajusta a los límites de velocidad')


def apice(plan) -> float:
    """El instante del plan que debe caer en la palabra: la mitad de su trazo."""
    return (float(plan.inicio_trazo) + float(plan.fin_trazo)) / 2


def plan(motor, brazo: str, movimiento: dict, inicio: dict, otro: dict | None = None, delta: float = 0.0):
    """Plan ejecutable de un movimiento de la biblioteca con `brazo` como principal.

    `movimiento` es el campo "movimiento" de una primitiva. Si es de dos brazos, el otro hace su parte; si no,
    `otro` (el "movimiento" de una primitiva de un brazo) es lo que hace el otro brazo, con su ápice `delta`
    segundos después del ápice del principal (antes, si es negativo). Empieza en `inicio` y acaba en reposo.
    El trazo va de la primera postura clave al comienzo de la vuelta.
    """
    from .semantico import Trayectoria
    if brazo not in motor.marcos:
        raise ValueError('brazo no disponible')
    claves = {brazo: movimiento['principal']}
    companero = next((b for b in motor.marcos if b != brazo), None)
    if companero is not None and movimiento.get('otro'):
        claves[companero] = movimiento['otro']
    t, poses, primera, vuelta = trayectoria(motor, claves, inicio)
    principal = Trayectoria(t, poses, primera, max(vuelta, primera), SimpleNamespace(tipo='registro', brazo=brazo, ancla=0), 0.0, 0.0,
                            inicio_retorno=max(vuelta, primera), reposo_al_final=True)
    if companero is None or movimiento.get('otro') or otro is None:
        return principal
    return con_otro(motor, principal, brazo, otro, inicio, apice(principal), delta)


def con_otro(motor, principal, brazo: str, otro: dict, inicio: dict, apice_principal: float, delta: float = 0.0):
    """Añade a un plan de un brazo un movimiento de la biblioteca en el otro brazo, cada uno con su ápice.

    Si los dos juntos no caben (se acercarían demasiado), devuelve el plan principal tal cual.
    """
    companero = next((b for b in motor.marcos if b != brazo), None)
    if companero is None:
        return principal
    try:
        segundo = plan(motor, companero, otro, inicio)
        return fundir(motor, principal, segundo, brazo, companero, apice_principal, apice(segundo), delta)
    except Exception:
        return principal


def fundir(motor, plan_a, plan_b, brazo_a: str, brazo_b: str, apice_a: float, apice_b: float, delta: float = 0.0):
    """Un solo plan con `brazo_a` haciendo `plan_a` y `brazo_b` haciendo `plan_b`, validado entero.

    El ápice de `plan_b` queda `delta` segundos después del de `plan_a`. Cada plan debe dejar quieto en reposo al
    brazo que no es el suyo. Lanza ValueError si los dos movimientos juntos no respetan la distancia entre brazos.
    """
    from dataclasses import replace
    from .escenico import validar
    paso = 1.0 / motor.cfg.frecuencia_hz
    desfase = float(apice_a) + float(delta) - float(apice_b)       # cuánto más tarde que el plan A empieza el plan B
    espera_a = round(max(0.0, -desfase) / paso) * paso
    espera_b = round(max(0.0, desfase) / paso) * paso
    total = max(espera_a + float(plan_a.tiempos[-1]), espera_b + float(plan_b.tiempos[-1]))
    t = np.arange(0, math.ceil(total / paso) + 1) * paso
    def columna(p, brazo, espera):
        return np.column_stack([np.interp(t - espera, p.tiempos, p.q[brazo][:, j]) for j in range(6)])
    poses = {brazo_a: columna(plan_a, brazo_a, espera_a), brazo_b: columna(plan_b, brazo_b, espera_b)}
    validar(motor, t, poses)
    return replace(plan_a, tiempos=t, q=poses, inicio_trazo=espera_a + float(plan_a.inicio_trazo), fin_trazo=espera_a + float(plan_a.fin_trazo),
                   inicio_retorno=max(espera_a + float(plan_a.inicio_retorno if plan_a.inicio_retorno is not None else plan_a.fin_trazo),
                                      espera_b + float(plan_b.inicio_retorno if plan_b.inicio_retorno is not None else plan_b.fin_trazo)),
                   reposo_al_final=True)
