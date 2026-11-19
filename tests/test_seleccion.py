"""Marcar un punto o un recuadro en la imagen es una entrada para la IA, no una frase fija. Sin red, brazos ni simulación."""
import threading
import time

import cv2
import numpy as np

from so101er.aplicacion import PREGUNTA_SELECCION, SesionIntegrada, pregunta_seleccion
from so101er.idiomas import IDIOMAS

REGION = {'region': [[100., 200.], [500., 800.]]}
PUNTO = {'punto': [500., 250.]}


def _naranja(jpeg):
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), 1)
    return np.nonzero((img[..., 2] > 200) & (img[..., 1] < 190) & (img[..., 0] < 90))


def _sesion():
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.imagen = np.full((440, 700, 3), 255, np.uint8)
    return s


def test_la_ia_ve_dibujado_lo_que_se_ha_marcado():
    s = _sesion()
    assert len(_naranja(s.jpeg())[0]) == 0 and len(_naranja(s.jpeg(None))[0]) == 0        # sin selección, la imagen de siempre
    ys, xs = _naranja(s.jpeg(REGION))
    assert abs(xs.min() - 140) <= 4 and abs(xs.max() - 560) <= 4 and abs(ys.min() - 44) <= 4 and abs(ys.max() - 220) <= 4
    ys, xs = _naranja(s.jpeg(PUNTO))
    assert abs(xs.mean() - 175) <= 3 and abs(ys.mean() - 220) <= 3 and 15 < np.ptp(xs) < 60     # un círculo en el punto
    assert s.imagen.min() == 255                                                           # la imagen del programa no se toca


def test_la_peticion_dice_a_la_ia_que_responda_sobre_lo_marcado():
    nota = SesionIntegrada.nota_seleccion(REGION)
    assert '[[100,200],[500,800]]' in nota and 'responde solo sobre lo que hay dentro' in nota and 'No lo describas' in nota
    nota = SesionIntegrada.nota_seleccion(PUNTO)
    assert '[500,250]' in nota and 'en ese punto y justo a su alrededor' in nota and 'No lo describas' in nota
    assert SesionIntegrada.nota_seleccion(None) == '' and SesionIntegrada.nota_seleccion({}) == ''
    assert set(PREGUNTA_SELECCION) == set(IDIOMAS)                                         # hay pregunta por defecto en cada idioma
    assert pregunta_seleccion('es', REGION) != pregunta_seleccion('es', PUNTO)
    assert pregunta_seleccion('fr', PUNTO).startswith('Explique-moi') and pregunta_seleccion('xx', REGION) == pregunta_seleccion('es', REGION)


def test_la_seleccion_acompana_a_la_pregunta_hasta_el_turno():
    turnos = []
    s = _sesion()
    s.notificar, s.lock, s.ticket, s.cancel = (lambda m: None), threading.RLock(), 0, threading.Event()
    s.bloqueo = lambda: None; s.interrumpir = lambda: None
    s._turno = lambda *a: turnos.append(a)
    def espera(n):
        fin = time.perf_counter() + 2
        while len(turnos) < n and time.perf_counter() < fin:
            time.sleep(.005)
        assert len(turnos) == n
    s.enviar('explícame lo que ves aquí', seleccion=REGION); espera(1)
    assert turnos[0][0] == 'explícame lo que ves aquí' and turnos[0][4] == 'es' and turnos[0][5] == REGION
    s.enviar('¿y esto otro?'); espera(2)
    assert len(turnos[1]) == 5                                                             # sin selección, el turno de siempre


def test_el_turno_pasa_a_la_ia_la_imagen_marcada_y_la_nota():
    visto = {}
    s = _sesion()
    s.notificar, s.lock, s.ticket = (lambda m: None), threading.RLock(), 0
    s.control = type('C', (), {'frenada': None, 'error': None, 'parar': staticmethod(lambda: None)})()
    s.real = False; s.brazos = {}; s.desplegar = lambda: 0.; s.estado = lambda: {}
    s.modelo, s.keys, s.dataset, s._seguimiento = 'falso', {}, 'seg', None
    def responder(texto, jpeg, estado, idioma):
        visto['texto'], visto['marcada'] = texto, len(_naranja(jpeg)[0]) > 0
        raise RuntimeError('fin de la prueba')
    s.vision = type('V', (), {'responder': staticmethod(responder)})()
    SesionIntegrada._turno(s, '¿qué es esto?', None, threading.Event(), 0, 'es', REGION)
    assert visto['marcada'] and visto['texto'].startswith('¿qué es esto?\nEl usuario ha marcado')
    SesionIntegrada._turno(s, '¿qué es esto?', None, threading.Event(), 0, 'es')
    assert not visto['marcada'] and visto['texto'] == '¿qué es esto?'
