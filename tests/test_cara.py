"""Cara del robot: tiempos, servidor SSE, objeto nulo y aislamiento del turno. Sin red externa ni audio."""
import http.client
import json
import socket
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101er.cara import Cara, CaraNula, crear
from so101er.cara import tiempos


# --- tiempos.py ---------------------------------------------------------------------------

def test_palabras_con_marcas_por_caracter_y_escala():
    texto = 'hola qué tal'
    marks = [(i, i * .1) for i in range(len(texto))]          # como ElevenLabs: una marca por carácter
    p = tiempos.palabras(texto, marks, 1.2)
    assert [w['t'] for w in p] == ['hola', 'qué', 'tal']
    assert [w['ini'] for w in p] == [0., .5, .9]
    assert p[0]['fin'] == p[1]['ini'] and p[-1]['fin'] == 1.2
    estirada = tiempos.palabras(texto, marks, 1.2, escala=1.25)
    assert [w['ini'] for w in estirada] == pytest.approx([0., .625, 1.125])
    assert estirada[-1]['fin'] == pytest.approx(1.5)


def test_palabras_sin_marcas_son_proporcionales_al_caracter():
    texto = 'uno dos tres'
    p = tiempos.palabras(texto, [], 12.)
    assert [w['ini'] for w in p] == [0., 4., 8.]               # caracteres 0, 4 y 8 de 12
    assert all(a['ini'] <= b['ini'] for a, b in zip(p, p[1:]))


def test_anclas_como_en_el_turno():
    from so101er.aplicacion import demo_bloques
    bloques = demo_bloques()
    texto = ' '.join(b['texto'] for b in bloques)
    lista = tiempos.palabras(texto, [], 30.)
    out = tiempos.anclas(bloques, lista)
    assert [b['tipo'] for b in out] == ['senalar', 'region']   # paisaje y cielo no tienen ubicación
    antes = sum(len(b['texto'].split()) for b in bloques[:2])
    assert out[0]['p0'] == antes and out[0]['p1'] == antes + len(bloques[2]['texto'].split()) - 1
    assert out[0]['ancla_s'] == lista[antes + bloques[2]['ancla']]['ini']
    assert out[0]['punto'] == [200., 780.] and out[1]['region'] == [[380., 180.], [600., 400.]]


def test_envolvente_normalizada_cada_20_ms():
    fs = tiempos.FRECUENCIA
    audio = np.r_[np.zeros(fs // 2), 8000 * np.sin(np.arange(fs // 2) * .3)].astype(np.int16)
    env = tiempos.envolvente(audio)
    assert len(env) == 50 and max(env) == 1. and min(env) == 0.
    assert all(v == 0 for v in env[:25]) and all(v > .9 for v in env[26:])
    assert all(round(v, 2) == v for v in env)
    assert tiempos.envolvente(np.zeros(100, np.int16)) == [0.]


def test_evento_turno_completo():
    audio = np.full(24000 * 2, 1000, np.int16)                  # 2 s de voz «estirada»
    ev = tiempos.turno(3, 'a b', [], 2., audio, [], obra_v=7)
    assert ev['id'] == 3 and ev['duracion'] == 2. and ev['paso'] == .02 and ev['obra_v'] == 7
    assert [w['ini'] for w in ev['palabras']] == [0., 1.333] and ev['palabras'][-1]['fin'] == 2.
    assert len(ev['boca']) == 100


# --- servidor -----------------------------------------------------------------------------

class Eventos:
    """Cliente SSE mínimo para las pruebas."""

    def __init__(self, puerto):
        self.c = http.client.HTTPConnection('127.0.0.1', puerto, timeout=5)
        self.c.request('GET', '/eventos')
        self.r = self.c.getresponse()
        assert self.r.status == 200 and self.r.getheader('Content-Type') == 'text/event-stream'

    def siguiente(self, nombre=None):
        evento = None
        while True:
            linea = self.r.fp.readline().decode().rstrip('\n')
            if linea.startswith('event: '):
                evento = linea[7:]
            elif linea.startswith('data: ') and evento:
                datos = json.loads(linea[6:])
                if nombre is None or evento == nombre:
                    return evento, datos
                evento = None

    def cerrar(self):
        self.c.close()


@pytest.fixture
def cara():
    avisos = []
    c = Cara(np.zeros((40, 60, 3), np.uint8), avisos.append, puerto=0)
    c.avisos = avisos
    yield c
    c.cerrar()


def test_sse_turno_reloj_y_fin(cara):
    sse = Eventos(cara.puerto)
    assert sse.siguiente() == ('estado', {'estado': 'IDLE'})
    cara.pensando('¿Qué es eso?')
    assert sse.siguiente('usuario')[1] == {'texto': '¿Qué es eso?'}
    assert sse.siguiente('estado')[1]['estado'] == 'THINKING'
    t0 = time.perf_counter()
    cara.hablar('uno dos', [], 1., np.ones(24000, np.int16), lambda: time.perf_counter() - t0, [])
    _, turno = sse.siguiente('turno')
    assert turno['id'] == 1 and [w['t'] for w in turno['palabras']] == ['uno', 'dos']
    assert sse.siguiente('estado')[1]['estado'] == 'TALKING'
    _, r1 = sse.siguiente('reloj')
    _, r2 = sse.siguiente('reloj')
    assert r1['id'] == 1 and 0 <= r1['pos'] < r2['pos'] < 1
    cara.callar(interrumpido=True)
    assert sse.siguiente('fin')[1] == {'id': 1, 'interrumpido': True}
    assert sse.siguiente('estado')[1]['estado'] == 'IDLE'
    sse.cerrar()


def test_al_reconectar_recibe_estado_y_turno_en_curso(cara):
    cara.hablar('hola', [], 1., np.ones(2400, np.int16), lambda: .05, [])
    time.sleep(.3)
    sse = Eventos(cara.puerto)
    assert sse.siguiente() == ('estado', {'estado': 'TALKING'})
    evento, datos = sse.siguiente()
    assert evento == 'turno' and datos['texto'] == 'hola'
    assert sse.siguiente()[0] == 'reloj'
    sse.cerrar()


def test_reloj_sin_dac_no_falla(cara):
    def sin_reloj():
        raise RuntimeError('el dispositivo aún no ha dado reloj DAC')
    sse = Eventos(cara.puerto)
    cara.hablar('hola', [], 1., np.ones(2400, np.int16), sin_reloj, [])
    sse.siguiente('turno')
    time.sleep(.35)
    cara.callar()
    evento, datos = sse.siguiente()
    while evento == 'estado':
        evento, datos = sse.siguiente()
    assert evento == 'fin' and datos['interrumpido'] is False   # ningún `reloj` y ningún aviso
    assert cara.avisos == []
    sse.cerrar()


def test_estaticos_imagen_y_salud(cara):
    c = http.client.HTTPConnection('127.0.0.1', cara.puerto, timeout=5)
    for ruta, codigo, tipo in (('/', 200, 'text/html'), ('/js/app.js', 200, 'text/javascript'),
                               ('/obra.jpg', 200, 'image/jpeg'), ('/salud', 200, 'application/json'),
                               ('/../__init__.py', 404, 'text/plain'), ('/nada.js', 404, 'text/plain')):
        c.request('GET', ruta)
        r = c.getresponse()
        cuerpo = r.read()
        assert (r.status, r.getheader('Content-Type').split(';')[0]) == (codigo, tipo), ruta
    assert cuerpo == b'no encontrado'
    c.close()


def test_puerto_ocupado_no_lanza(tmp_path):
    ocupado = socket.socket()
    ocupado.bind(('127.0.0.1', 0))
    ocupado.listen()
    puerto = ocupado.getsockname()[1]
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/so101er.toml').write_text(f'[cara]\nactiva = true\npuerto = {puerto}\n')
    avisos = []
    try:
        c = crear(tmp_path, np.zeros((4, 4, 3), np.uint8), avisos.append)
    finally:
        ocupado.close()
    assert isinstance(c, CaraNula) and len(avisos) == 1 and 'no disponible' in avisos[0]


def test_apagada_por_config_o_variable(tmp_path, monkeypatch):
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/so101er.toml').write_text('[cara]\nactiva = false\n')
    avisos = []
    assert isinstance(crear(tmp_path, None, avisos.append), CaraNula) and avisos == []
    (tmp_path / 'config/so101er.toml').write_text('[cara]\nactiva = true\npuerto = 0\n')
    monkeypatch.setenv('SO101_CARA', '0')
    assert isinstance(crear(tmp_path, None, avisos.append), CaraNula) and avisos == []


def test_objeto_nulo():
    c = CaraNula()
    assert not c
    for llamada in (lambda: c.pensando('x'), lambda: c.escuchando(True), lambda: c.error('x'),
                    lambda: c.hablar('x', [], 1., np.zeros(1), lambda: 0, []), lambda: c.callar(True), c.cerrar):
        assert llamada() is None


class _ColaRota:
    """Toda llamada de la API falla por dentro; el hilo de la cara sigue esperando sin trabajo."""

    def put(self, item):
        raise RuntimeError('rota')

    def get(self, timeout=None):
        time.sleep(timeout or .1)
        raise __import__('queue').Empty


def test_una_cara_rota_no_lanza_y_avisa_una_vez(cara):
    cara.cola = _ColaRota()
    for _ in range(3):
        cara.pensando('x')
        cara.hablar('x', [], 1., np.zeros(1), lambda: 0, [])
        cara.callar()
    assert len(cara.avisos) == 3 and all(a.startswith('Cara del robot (') for a in cara.avisos)


# --- enganches en _turno -----------------------------------------------------------------

class _Reproductor:
    """Sustituye a sincronia.reproductor.Reproductor: sin altavoz y con un reloj rápido."""

    def __init__(self, audio, previo_s=0.):
        self.track = np.asarray(audio)
        self.cursor = 0
        self.terminado = threading.Event()
        self.t0 = None

    def iniciar(self):
        self.t0 = time.perf_counter()

    def posicion(self):
        return (time.perf_counter() - self.t0) * 40

    def cerrar(self):
        pass


def _sesion(monkeypatch, cara):
    import so101er.sincronia.reproductor as rep
    from concurrent.futures import ThreadPoolExecutor
    from so101er.aplicacion import SesionIntegrada
    monkeypatch.setattr(rep, 'Reproductor', _Reproductor)
    s = SesionIntegrada.__new__(SesionIntegrada)
    avisos = []
    s.notificar, s.real, s.brazos, s.lock, s.ticket = avisos.append, False, {}, threading.RLock(), 0
    s.audio_actual, s.dataset, s._seguimiento, s.desplegado, s.plegado = None, 'seg', None, True, None
    s.control = SimpleNamespace(frenada=None, error=None, medir=lambda: {}, parar=lambda: None)
    s.voz = SimpleNamespace(sintetizar=lambda t, idioma='es': (np.full(24000, 900, np.int16), [], 'prueba'), aviso=None)
    s.pool = ThreadPoolExecutor(1)
    s.cara = cara
    return s, avisos


def test_enganches_del_turno_en_orden(monkeypatch):
    llamadas = []

    class Grabadora:
        def __getattr__(self, nombre):
            return lambda *a, **k: llamadas.append((nombre, a))

    s, avisos = _sesion(monkeypatch, Grabadora())
    bloques = [{'texto': 'hola a todos', 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}]
    s._turno('', bloques, threading.Event(), 0)
    assert [n for n, _ in llamadas] == ['pensando', 'hablar', 'callar']
    texto, marks, escala, audio, reloj, bl = llamadas[1][1]
    assert texto == 'hola a todos' and escala == 1. and len(audio) == 24000 and bl == bloques and callable(reloj)
    assert avisos[-1].startswith('Listo')


def test_una_excepcion_en_la_cara_no_llega_al_turno(monkeypatch):
    c = Cara(None, lambda m: None, puerto=0)
    try:
        c.cola = _ColaRota()                                     # todos sus métodos fallan por dentro
        s, avisos = _sesion(monkeypatch, c)
        s._turno('', [{'texto': 'hola a todos', 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}],
                 threading.Event(), 0)
        assert avisos[-1].startswith('Listo') and not any(a.startswith('Error') for a in avisos)
    finally:
        c.servidor.cerrar()


def test_turno_antiguo_no_calla_al_nuevo(monkeypatch):
    llamadas = []

    class Grabadora:
        def __getattr__(self, nombre):
            return lambda *a, **k: llamadas.append(nombre)

    s, _ = _sesion(monkeypatch, Grabadora())
    cancel = threading.Event()
    s.ticket = 1                                                 # ya empezó otro turno
    cancel.set()
    s._turno('', [{'texto': 'hola', 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}], cancel, 0)
    assert 'callar' not in llamadas


# ---------------------------------------------------------------- turno frase a frase, mirada e imagen
def _voz(segundos):
    return (np.random.default_rng(2).standard_normal(int(segundos * 24000)) * 4000).astype(np.int16)


def test_las_frases_salen_una_a_una_cuando_el_altavoz_llega_a_ellas(cara):
    sse = Eventos(cara.puerto)
    sse.siguiente('estado')
    cara.pensando('¿cómo llego?')
    t0 = time.perf_counter()
    reloj = lambda: time.perf_counter() - t0
    cara.frase('a', 'uno dos tres', [], _voz(.5), reloj, .15, [])
    cara.frase('b', 'cuatro cinco', [], _voz(.4), reloj, .75, [])                # se prepara antes de que le toque
    _, primera = sse.siguiente('turno')
    assert primera['id'] == 1 and primera['rev'] == 0 and [w['t'] for w in primera['palabras']] == ['uno', 'dos', 'tres']
    assert .1 <= time.perf_counter() - t0 < .45                                 # sale cuando empieza a sonar, no antes
    assert sse.siguiente('estado')[1]['estado'] == 'TALKING'
    _, r = sse.siguiente('reloj')
    assert r['id'] == 1 and -.05 <= r['pos'] < .5                               # el reloj es el de la frase, no el del turno
    assert sse.siguiente('fin')[1] == {'id': 1, 'interrumpido': False}          # la anterior termina sin cortarse
    _, segunda = sse.siguiente('turno')
    assert segunda['id'] == 2 and [w['t'] for w in segunda['palabras']] == ['cuatro', 'cinco'] and time.perf_counter() - t0 >= .7
    cara.callar()
    assert sse.siguiente('fin')[1] == {'id': 2, 'interrumpido': False}
    assert sse.siguiente('estado')[1]['estado'] == 'IDLE' and cara.avisos == []
    sse.cerrar()


def test_una_frase_que_ya_suena_recibe_despues_sus_tiempos_definitivos(cara):
    sse = Eventos(cara.puerto)
    t0 = time.perf_counter()
    reloj = lambda: time.perf_counter() - t0
    texto = 'siga recto hasta la plaza'
    cara.frase('a', texto, [(0, 0.), (5, .3)], _voz(.4), reloj, 0., [], duracion=2.)      # solo ha llegado el principio de la voz
    _, provisional = sse.siguiente('turno')
    assert provisional['rev'] == 0 and provisional['duracion'] == 2. and len(provisional['boca']) == 20
    marcas = [(i, i * .08) for i in range(len(texto))]
    cara.frase('a', texto, marcas, _voz(2.), reloj, 0., [])
    _, definitiva = sse.siguiente('turno')
    assert definitiva['id'] == provisional['id'] and definitiva['rev'] == 1 and len(definitiva['boca']) == 100
    assert [w['ini'] for w in definitiva['palabras']] == [0., .4, .88, 1.36, 1.6]
    assert provisional['palabras'][3]['ini'] == .3                              # lo que aún no había llegado estaba amontonado al final
    cara.callar(True)
    sse.cerrar()


def test_la_cara_mira_hacia_el_gesto_de_los_brazos_mientras_dura(cara):
    sse = Eventos(cara.puerto)
    t0 = time.perf_counter()
    reloj = lambda: time.perf_counter() - t0
    cara.frase('a', 'gire a la derecha', [], _voz(.6), reloj, 0., [])
    cara.gesto(reloj, .2, .5, lado=1, vertical=-1, animo='atento')
    assert sse.siguiente('mirada')[1] == {'lado': 1, 'vertical': -1, 'animo': 'atento'}
    assert .15 <= time.perf_counter() - t0 < .5
    assert sse.siguiente('mirada')[1] == {'lado': 0, 'vertical': 0, 'animo': 'neutro'} and time.perf_counter() - t0 >= .45
    cara.gesto(reloj, 0., 30., lado=-1)                                         # un turno que se corta también suelta la mirada
    assert sse.siguiente('mirada')[1]['lado'] == -1
    cara.callar(True)
    assert sse.siguiente('mirada')[1] == {'lado': 0, 'vertical': 0, 'animo': 'neutro'}
    otro = Eventos(cara.puerto)                                                 # quien se conecta tarde recibe la mirada actual
    assert otro.siguiente('mirada')[1]['lado'] == 0
    sse.cerrar(); otro.cerrar()


def test_que_cara_pone_con_cada_gesto():
    from so101er.cara.expresiones import de_bloque
    assert de_bloque({'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'E05'}) == {'lado': 1, 'vertical': 0, 'animo': 'neutro'}
    assert de_bloque({'tipo': 'gesto', 'brazo': 'izq', 'movimiento': 'E08', 'otro': 'E16'}) == {'lado': -1, 'vertical': 1, 'animo': 'neutro'}
    assert de_bloque({'tipo': 'gesto', 'brazo': 'izq', 'movimiento': 'E12', 'otro': 'M20'}) == {'lado': -1, 'vertical': 1, 'animo': 'alegre'}
    assert de_bloque({'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'M03'})['animo'] == 'serio'
    assert de_bloque({'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'E04', 'otro': 'M07'})['animo'] == 'neutro'       # «hasta el final» no es un enfado
    assert de_bloque({'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'B06'}) == {'lado': 0, 'vertical': 0, 'animo': 'pensativo'}   # dos brazos: al frente
    assert de_bloque({'tipo': 'senalar', 'brazo': 'izq'}) == {'lado': -1, 'vertical': 0, 'animo': 'atento'}
    assert de_bloque({'tipo': 'cielo', 'brazo': 'der'}) == {'lado': 0, 'vertical': 1, 'animo': 'neutro'}
    assert de_bloque({'tipo': 'gesto', 'brazo': 'der', 'movimiento': 'E05'}, espejo=True)['lado'] == -1


def test_la_imagen_de_la_cara_cambia_con_la_del_programa(cara):
    def pedir():
        c = http.client.HTTPConnection('127.0.0.1', cara.puerto, timeout=5)
        c.request('GET', '/obra.jpg')
        datos = c.getresponse().read(); c.close()
        return datos
    antes, version = pedir(), cara.obra_v
    cara.imagen_nueva(np.full((80, 120, 3), 200, np.uint8))
    fin = time.perf_counter() + 2
    while cara.obra_v == version and time.perf_counter() < fin:
        time.sleep(.01)
    assert cara.obra_v != version and pedir() != antes and cara.avisos == []


def test_el_turno_frase_a_frase_lleva_a_la_cara_cada_frase_y_cada_gesto(monkeypatch):
    """Sesión simulada de verdad, con voz y altavoz falsos y una cara que solo apunta lo que recibe."""
    from conftest import RAIZ
    from test_turno_por_frases import Altavoz, _voz as voz_falsa
    import so101er.sincronia.reproductor as rep
    from so101er.aplicacion import SesionIntegrada, demo_biblioteca
    monkeypatch.setenv('SO101_CARA', '0')                                       # la sesión no abre el puerto de verdad
    monkeypatch.setattr(rep, 'Reproductor', Altavoz)
    llamadas = []

    class Grabadora:
        espejo = False
        def __getattr__(self, nombre):
            return lambda *a, **k: llamadas.append((nombre, a, k))

    avisos = []
    s = SesionIntegrada(RAIZ, real=False, ventana=False, notificar=avisos.append)
    try:
        assert not s.cara                                                       # apagada: objeto nulo
        s.cara = Grabadora(); s.voz = voz_falsa([], duracion=5.); s.por_frases = True
        fin = threading.Event()
        s.notificar = lambda m: (avisos.append(m), fin.set() if m.startswith(('Listo.', 'Error')) else None)
        s.enviar('', demo_biblioteca()[3:5])                                    # «gire… río» y «un edificio alto con una torre»
        assert fin.wait(60) and not any(a.startswith('Error') for a in avisos), avisos
    finally:
        s.interrumpir(); s.cerrar()
    nombres = [n for n, _, _ in llamadas]
    assert nombres[0] == 'callar' and nombres[1] == 'pensando'                  # el turno anterior calla; este empieza pensando
    frases = [a for n, a, _ in llamadas if n == 'frase']
    assert len(frases) == 4 and frases[0][0] == frases[1][0] != frases[2][0] == frases[3][0]      # cada frase, provisional y definitiva
    assert frases[0][1].startswith('En la plaza gire') and len(frases[0][3]) < len(frases[1][3])  # primero parte de la voz; luego toda
    assert frases[2][5] >= frases[0][5] + 5                                     # la segunda empieza cuando acaba la primera
    gestos = [(a, k) for n, a, k in llamadas if n == 'gesto']
    assert [k for _, k in gestos] == [{'lado': 1, 'vertical': 0, 'animo': 'neutro'}, {'lado': -1, 'vertical': 1, 'animo': 'neutro'}]
    assert all(a[1] < a[2] for a, _ in gestos) and 'error' not in nombres and nombres.count('callar') >= 2
