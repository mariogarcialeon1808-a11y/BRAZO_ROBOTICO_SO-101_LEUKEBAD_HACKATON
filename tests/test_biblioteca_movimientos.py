"""La biblioteca de movimientos dentro del programa: la IA puede pedirlos (tipo «gesto») y el control los ejecuta.

Sin red, sin altavoz y sin brazos: la IA, la voz y la tarjeta de sonido están sustituidas.
"""
import json
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from so101er import aplicacion_servicios as S
from so101er.control import expresion as E
from test_turno_por_frases import Altavoz, _voz, altavoz  # noqa: F401  (altavoz es un accesorio de pytest)


@pytest.fixture(scope='module')
def motor():
    from so101er.config import cargar
    from so101er.control.semantico import MotorGestos
    cfg = cargar(); cfg.frecuencia_hz = 50
    return MotorGestos(cfg)


def _reposo(motor):
    from so101er.control.escenico import pose_reposo
    return {n: pose_reposo(motor, n) for n in motor.marcos}


def test_un_movimiento_de_la_biblioteca_es_un_plan_como_los_demas(motor):
    biblioteca = E.disponibles()
    assert len(biblioteca) >= 70 and 'E05' in biblioteca and 'D01' not in biblioteca       # los de siempre no están aquí
    reposo = _reposo(motor)
    plan = E.plan(motor, 'der', biblioteca['E05']['movimiento'], reposo)
    assert 0 < plan.inicio_trazo < plan.fin_trazo == plan.inicio_retorno < plan.tiempos[-1] and plan.reposo_al_final
    for n in motor.marcos:
        np.testing.assert_allclose(plan.q[n][0], reposo[n], atol=1e-9)                     # sale de donde se le dice
        np.testing.assert_allclose(plan.q[n][-1], reposo[n], atol=1e-9)                    # y acaba en reposo
    assert np.ptp(plan.q['der'][:, :5], axis=0).max() > 20 and np.ptp(plan.q['izq'], axis=0).max() < 1e-9   # un brazo; el otro, quieto
    np.testing.assert_allclose(plan.muestra(plan.tiempos[-1] + 1)['der'], reposo['der'], atol=1e-9)
    # El mismo movimiento con el otro brazo es su imagen en espejo: «hacia fuera» es hacia su lado.
    espejo = E.plan(motor, 'izq', biblioteca['E05']['movimiento'], reposo)
    i = int(np.searchsorted(plan.tiempos, plan.fin_trazo)) - 1
    assert plan.q['der'][i, 0] == pytest.approx(-espejo.q['izq'][i, 0], abs=0.05) and abs(plan.q['der'][i, 0]) > 30


def test_el_otro_brazo_puede_hacer_a_la_vez_un_segundo_movimiento(motor):
    biblioteca = E.disponibles()
    reposo = _reposo(motor)
    rotonda = E.plan(motor, 'der', biblioteca['E07']['movimiento'], reposo, biblioteca['M06']['movimiento'])
    assert np.ptp(rotonda.q['der'][:, :5], axis=0).max() > 10 and np.ptp(rotonda.q['izq'][:, :5], axis=0).max() > 10
    assert np.ptp(rotonda.q['izq'][:, 5]) > 50                                             # el otro cuenta abriendo la pinza
    balanza = E.plan(motor, 'izq', biblioteca['B06']['movimiento'], reposo, biblioteca['M06']['movimiento'])
    sola = E.plan(motor, 'izq', biblioteca['B06']['movimiento'], reposo)
    assert E.de_dos_brazos(biblioteca['B06']) and np.array_equal(balanza.q['der'], sola.q['der'])      # un bimanual ya trae su otro brazo
    # Desde una postura que no es reposo también sale un plan continuo.
    desde = {n: q + np.array([8., 5., -5., 4., 0., 10.]) for n, q in reposo.items()}
    plan = E.plan(motor, 'der', biblioteca['M03']['movimiento'], desde)
    np.testing.assert_allclose(plan.q['izq'][0], desde['izq'], atol=1e-9)
    with pytest.raises(ValueError, match='brazo no disponible'):
        E.plan(motor, 'centro', biblioteca['M03']['movimiento'], reposo)


def test_la_ia_puede_pedir_movimientos_de_la_biblioteca():
    texto = 'En la rotonda tome la tercera salida y siga por la avenida principal hasta el final.'
    def bloque(**campos):
        return {'bloques': [{'texto': texto, 'tipo': 'gesto', 'brazo': 'der', 'ancla': 2, **campos}]}
    assert S.validar_bloques(bloque(movimiento='E07', otro='M06'))[0]['otro'] == 'M06'
    assert 'otro' not in S.validar_bloques(bloque(movimiento='E07'))[0]
    assert 'otro' not in S.validar_bloques(bloque(movimiento='E07', otro='B06'))[0]        # un bimanual no vale de segundo
    assert 'otro' not in S.validar_bloques(bloque(movimiento='B06', otro='M06'))[0]        # ni un bimanual admite segundo
    assert 'otro' not in S.validar_bloques(bloque(movimiento='E07', otro='Z99'))[0]
    for malo in (bloque(movimiento='Z99'), bloque(), bloque(movimiento='D01')):
        with pytest.raises(ValueError, match='movimiento desconocido'):
            S.validar_bloques(malo)
    with pytest.raises(ValueError, match='ancla inválida'):
        S.validar_bloques(bloque(movimiento='E07', ancla=99))


def test_las_instrucciones_de_siempre_no_cambian_y_la_biblioteca_va_detras():
    lista = S.biblioteca_ia()
    assert 'BIBLIOTECA DE MOVIMIENTOS' not in S.instrucciones_vision() and lista.startswith('\nBIBLIOTECA DE MOVIMIENTOS')
    assert '"tipo":"gesto"' in lista and 'E05 girar hacia fuera' in lista and 'M12 reloj' in lista and 'B06 balanza' in lista
    assert 'D01 ' not in lista and lista.count('\n') > 80 and len(lista) < 9000
    pytest.importorskip('google.genai')
    peticiones = []
    class Cliente:
        models = None
        def generate_content(self, model, contents, config):
            peticiones.append(contents[1])
            return SimpleNamespace(text=json.dumps({'bloques': [{'texto': 'Gire a la derecha al llegar a la plaza y siga recto hasta el final.',
                                                               'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'E05', 'ancla': 0}]}))
    v = S.Vision.__new__(S.Vision)
    v.client, v.modelo, v.historia = Cliente(), 'falso', []
    v.client.models = v.client
    bloques = v.responder('¿cómo llego?', b'jpeg', {})
    assert bloques[0]['movimiento'] == 'E05' and peticiones[0].startswith(S.instrucciones_vision() + lista)
    assert E.texto_para_ia('no/existe.json') == '' and E.disponibles('no/existe.json') == {}   # sin registro, el programa de siempre


def test_la_demo_de_la_biblioteca_es_valida_y_dice_que_movimiento_lleva_cada_frase():
    from so101er.aplicacion import SesionIntegrada, demo_biblioteca
    bloques = demo_biblioteca()
    assert S.validar_bloques({'bloques': [dict(b) for b in bloques]}) and {b['tipo'] for b in bloques} == {'gesto'}
    assert [b['movimiento'] for b in bloques] == ['E12', 'M25', 'E04', 'E05', 'E08', 'M12']
    assert all(E.bloque_grafico(b) and b['ancla_otro'] != b['ancla'] for b in bloques)      # dos conceptos, cada uno en su palabra
    assert SesionIntegrada.rotulo_movimiento(bloques[3]) == ' · E05 girar hacia fuera (der) + E10 ondular'
    assert SesionIntegrada.rotulo_movimiento({'tipo': 'senalar'}) == ''
    assert SesionIntegrada.rotulo_movimiento({'tipo': 'senalar', 'brazo': 'izq', 'otro': 'E10'}) == ' · senalar (izq) + E10 ondular'


def test_cada_frase_lleva_un_movimiento_grafico_y_la_ia_lo_escribe_en_su_campo():
    dibujan = E.graficos()
    assert {'E05', 'E07', 'B06', 'M12', 'M25'} <= dibujan and not {'M20', 'M24', 'D06', 'B09'} & dibujan and len(dibujan) >= 35
    lista = S.biblioteca_ia()
    for trozo in ('GRÁFICOS de un brazo:', 'GRÁFICOS de DOS BRAZOS:', '"grafico":"E05"', '"apoyo":"M20"', '"ancla_grafico"', 'obligatorio'):
        assert trozo in lista, trozo
    assert lista.index('E05 girar hacia fuera') < lista.index('GRÁFICOS de DOS BRAZOS:') < lista.index('B06 balanza') < lista.index('M20 saludar')
    texto = 'En la plaza gire a la derecha y cruce el puente que pasa sobre el río.'
    def uno(**campos):
        return S.validar_bloques({'bloques': [{'texto': texto, 'brazo': 'der', **campos}]})[0]
    # Formato A: «grafico» y «apoyo», cada uno con su palabra. Dentro del programa son movimiento, otro y ancla_otro.
    b = uno(tipo='gesto', grafico='E05', ancla=3, apoyo='E10', ancla_apoyo=14)
    assert (b['movimiento'], b['ancla'], b['otro'], b['ancla_otro']) == ('E05', 3, 'E10', 14) and 'grafico' not in b and E.bloque_grafico(b)
    assert 'otro' not in uno(tipo='gesto', grafico='E05', ancla=3) and 'ancla_otro' not in uno(tipo='gesto', grafico='E05', ancla=3, apoyo='M20')
    assert 'ancla_otro' not in uno(tipo='gesto', grafico='E05', ancla=3, apoyo='M20', ancla_apoyo=99)      # ancla imposible: van a la vez
    b = uno(tipo='gesto', grafico='nada', ancla=3, apoyo='M20', ancla_apoyo=0)                             # solo vale el de apoyo
    assert (b['movimiento'], b['ancla']) == ('M20', 0) and 'otro' not in b and not E.bloque_grafico(b)
    assert not E.bloque_grafico(uno(tipo='gesto', grafico='M16', ancla=3, apoyo='M20')) and E.bloque_grafico(uno(tipo='gesto', grafico='M16', ancla=3, apoyo='E10'))
    # Formato B: mientras un brazo señala o recorre una región, el otro dibuja.
    b = uno(tipo='senalar', punto=[200, 780], ancla=10, grafico='E10', ancla_grafico=14)
    assert (b['otro'], b['ancla_otro']) == ('E10', 14) and E.bloque_grafico(b)
    assert not E.bloque_grafico(uno(tipo='senalar', punto=[200, 780], ancla=10)) and not E.bloque_grafico(uno(tipo='senalar', punto=[200, 780], ancla=10, grafico='D08'))
    assert 'otro' not in uno(tipo='region', region=[[100, 100], [400, 500]], ancla=2, grafico='B06')        # un bimanual no cabe con un señalamiento
    assert 'otro' not in uno(tipo='paisaje', ancla=2, grafico='E10') and E.bloque_grafico(uno(tipo='paisaje', ancla=2))
    with pytest.raises(ValueError, match='movimiento desconocido'):
        uno(tipo='gesto', grafico='nada', ancla=3)


def test_los_dos_brazos_llevan_cada_uno_su_concepto_en_su_palabra(motor):
    biblioteca = E.disponibles()
    reposo = _reposo(motor)
    giro, rio = E.plan(motor, 'der', biblioteca['E05']['movimiento'], reposo), E.plan(motor, 'izq', biblioteca['E10']['movimiento'], reposo)
    def instante_del_apice(plan, brazo, referencia):          # cuándo pasa el plan fundido por la postura del ápice del original
        i = int(np.searchsorted(referencia.tiempos, E.apice(referencia)))
        return float(plan.tiempos[int(np.argmin(np.abs(plan.q[brazo] - referencia.q[brazo][i]).sum(axis=1)))])
    for delta in (2.0, 0.0, -1.5):
        junto = E.fundir(motor, giro, rio, 'der', 'izq', E.apice(giro), E.apice(rio), delta)
        assert instante_del_apice(junto, 'izq', rio) - instante_del_apice(junto, 'der', giro) == pytest.approx(delta, abs=0.06), delta
        assert E.apice(junto) == pytest.approx(instante_del_apice(junto, 'der', giro), abs=0.06)      # el ápice del plan sigue siendo el del principal
        for n in motor.marcos:
            np.testing.assert_allclose(junto.q[n][0], reposo[n], atol=1e-9)
            np.testing.assert_allclose(junto.q[n][-1], reposo[n], atol=1e-6)
    assert E.fundir(motor, giro, rio, 'der', 'izq', E.apice(giro), E.apice(rio), 2.0).tiempos[-1] > giro.tiempos[-1]
    # Dos movimientos que juntos acercarían demasiado los brazos no se funden: queda el principal.
    dentro = biblioteca['E06']['movimiento']
    a, b = E.plan(motor, 'der', dentro, reposo), E.plan(motor, 'izq', dentro, reposo)
    with pytest.raises(ValueError, match='los brazos se acercarían'):
        E.fundir(motor, a, b, 'der', 'izq', E.apice(a), E.apice(b))
    solo = E.plan(motor, 'der', dentro, reposo, dentro)
    assert np.ptp(solo.q['izq'], axis=0).max() < 1e-9 and np.array_equal(solo.q['der'], a.q['der'])


def test_los_acentos_de_relleno_ya_no_son_siempre_el_mismo_gesto(motor):
    from so101er.control.acompanamiento import FORMAS_ACENTO, acento, solo_acentos
    formas = [acento(motor, 'izq', 2.6, 1.3, f) for f in range(len(FORMAS_ACENTO))]
    cimas = [p.q['izq'][int(np.searchsorted(p.tiempos, 1.3))] for p in formas]
    for i, a in enumerate(cimas):
        for b in cimas[i + 1:]:
            assert np.abs(a[:5] - b[:5]).max() > 8                                          # cada forma lleva el brazo a un sitio distinto
    assert sum(p.q['izq'][:, 5].max() < 1 for p in formas) >= 3                              # la mitad no abre la pinza
    for p in formas:
        np.testing.assert_allclose(p.q['izq'][0], p.q['izq'][-1], atol=1e-9)
    np.testing.assert_array_equal(acento(motor, 'izq', 2.6, 1.3).q['izq'], formas[0].q['izq'])       # sin pedir forma, el de siempre
    audio = np.random.default_rng(3).normal(0, 3000, 8 * 24000).astype(np.int16)
    pulsos, n = solo_acentos(motor, audio, 8.)
    assert n == 3
    picos = [float(np.abs(p.q[b] - p.q[b][0])[:, :5].max()) for _, p in pulsos for b in p.q]
    assert len({round(x, 1) for x in picos}) >= 3                                            # tres acentos seguidos, tres formas


def test_un_turno_con_movimientos_de_la_biblioteca_en_simulacion(altavoz):
    """Sesión simulada de verdad (control y física reales), con voz y altavoz falsos, frase a frase."""
    from conftest import RAIZ
    from so101er.aplicacion import SesionIntegrada, demo_biblioteca
    avisos, sucesos = [], []
    s = SesionIntegrada(RAIZ, real=False, ventana=False, notificar=avisos.append)
    try:
        s.voz = _voz(sucesos, duracion=4.5); s.por_frases = True
        s._planes_vistos = []
        programados = []; programar = s.control.programar
        def anotado(plan, *a, **k):
            if a: programados.append((a[0], a[0] + float(plan.tiempos[-1]), getattr(plan.intencion, 'tipo', '')))
            if a: s._planes_vistos.append(plan)
            return programar(plan, *a, **k)
        s.control.programar = anotado
        fin = threading.Event()
        s.notificar = lambda m: (avisos.append(m), fin.set() if m.startswith(('Listo.', 'Error')) else None)
        s.enviar('', demo_biblioteca()[2:5])                                # recto · gire y río · edificio alto con su base
        assert fin.wait(60), avisos
        assert not any(a.startswith('Error') for a in avisos), avisos
        dichas = [a for a in avisos if '; falsa]' in a]
        assert len(dichas) == 3 and dichas[1].endswith(' · E05 girar hacia fuera (der) + E10 ondular')
        dos = [plan for plan in s._planes_vistos if all(np.ptp(q[:, :5], axis=0).max() > 5 for q in plan.q.values())]
        assert len(dos) >= 2, avisos                                        # los dos brazos se mueven en el mismo plan
        assert 'Conceptos gráficos: 3 de 3 frases.' in avisos
        de_biblioteca = [p for p in programados if p[2] == 'registro']
        assert len(de_biblioteca) >= 2, (programados, avisos)               # los movimientos de la biblioteca se ejecutan
        for (_, acaba, _), (empieza, _, _) in zip(programados, programados[1:]):
            assert empieza >= acaba - 1e-6
    finally:
        s.interrumpir(); s.cerrar()
