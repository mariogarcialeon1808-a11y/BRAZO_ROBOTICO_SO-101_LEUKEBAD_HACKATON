"""Turno frase a frase: se empieza a hablar con la primera frase mientras se preparan las demás.

Nada de esto usa red, altavoz ni brazos: la IA, la voz y la tarjeta de sonido están sustituidas.
"""
import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

from so101er import aplicacion_servicios as S
from so101er.sincronia.reproductor import Reproductor

EN = 'The yellow sun is the brightest point of the picture and it sits just above the small house on the right.'
EN2 = 'The green tree on the left stands next to the river and its leaves are painted with very small strokes.'
ES = 'El sol amarillo es el punto más brillante del cuadro y está justo encima de la casa pequeña de la derecha.'


def _bloque(texto, ancla=2, **cambios):
    return {'texto': texto, 'tipo': 'senalar', 'brazo': 'der', 'punto': [200, 780], 'ancla': ancla, **cambios}


# ---------------------------------------------------------------- altavoz al que se le va añadiendo audio
def test_al_altavoz_abierto_se_le_anade_audio_y_dice_cuando_empieza_cada_trozo():
    r = Reproductor(np.zeros(0, np.int16), previo_s=.1, abierto=True)
    assert r.anadir(np.ones(2400, np.int16)) == 0.                           # justo tras el silencio previo
    assert r.anadir(np.full(2400, 2, np.int16), pausa_s=.5) == pytest.approx(.6)
    assert len(r.track) == 2400 + 2400 + 12000 + 2400 and r.track[4800 + 11999] == 0 and r.track[-1] == 2
    r.cerrar_entrada()
    assert r.abierto is False
    assert Reproductor(np.zeros(10, np.int16)).abierto is False             # el de siempre no cambia


def test_el_altavoz_abierto_emite_silencio_mientras_espera_y_no_pierde_la_cuenta(monkeypatch):
    sd = pytest.importorskip('sounddevice')
    reloj = SimpleNamespace(outputBufferDacTime=0., currentTime=0.); estado = SimpleNamespace(output_underflow=False)
    class Flujo:
        def __init__(self, callback, **k): Flujo.callback = staticmethod(callback)
        def start(self): Flujo.callback(np.zeros((480, 1), np.int16), 480, reloj, estado)
        def abort(self): pass
        def close(self): pass
    monkeypatch.setattr(sd, 'OutputStream', Flujo)
    r = Reproductor(np.zeros(0, np.int16), abierto=True)
    r.iniciar()                                                             # sin audio todavía: suena silencio y el reloj corre
    assert r.cursor == 480 and len(r.track) == 480 and not r.track.any()
    assert r.anadir(np.full(240, 7, np.int16)) == pytest.approx(.02)        # empieza donde va el altavoz, no al principio
    salida = np.zeros((480, 1), np.int16)
    Flujo.callback(salida, 480, reloj, estado)
    assert list(salida[:240, 0]) == [7] * 240 and not salida[240:].any() and r.cursor == 960 == len(r.track)
    r.cerrar_entrada()
    with pytest.raises(sd.CallbackStop):                                    # ya no llegará más: termina al acabar lo que hay
        Flujo.callback(salida, 480, reloj, estado)
    r.cerrar()


# ---------------------------------------------------------------- voz por trozos
def _flujo_eleven(monkeypatch, lineas):
    pedidas = []
    class Respuesta:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter(lineas)
        def read(self):
            return json.dumps({'audio_base64': base64.b64encode(np.zeros(240, '<i2').tobytes()).decode(),
                               'alignment': {'characters': ['a'], 'character_start_times_seconds': [0]}}).encode()
    def abrir(peticion, timeout):
        pedidas.append((peticion.full_url, json.loads(peticion.data)['text'])); return Respuesta()
    monkeypatch.setattr(S.urllib.request, 'urlopen', abrir)
    return pedidas


def test_la_voz_por_trozos_entrega_cada_trozo_con_las_marcas_hasta_ese_momento(monkeypatch):
    crudo = np.arange(1, 5, dtype='<i2').tobytes()                           # 4 muestras, partidas en 5 + 3 bytes
    def linea(datos, letras, tiempos):
        return json.dumps({'audio_base64': base64.b64encode(datos).decode() if datos else None,
                           'alignment': {'characters': letras, 'character_start_times_seconds': tiempos}}).encode() + b'\n'
    pedidas = _flujo_eleven(monkeypatch, [linea(crudo[:5], ['E', 'l'], [0., .1]), b'\n', linea(crudo[5:], [' ', 's'], [.2, .3]),
                                          linea(b'', ['o', 'l'], [.4, .5])])
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'y'})
    trozos = []
    audio, marcas, tipo = voz.sintetizar('El sol', 'es', lambda muestras, m: trozos.append((list(muestras), list(m))))
    assert pedidas[0][0].endswith('/y/stream/with-timestamps?output_format=pcm_24000')
    assert trozos == [([1, 2], [(0, 0.), (1, .1)]), ([3, 4], [(0, 0.), (1, .1), (2, .2), (3, .3)])]      # el byte suelto pasa al trozo siguiente
    assert list(audio) == [1, 2, 3, 4] and marcas == [(0, 0.), (1, .1), (2, .2), (3, .3), (4, .4), (5, .5)]
    assert tipo == 'alineación ElevenLabs'
    voz.sintetizar('El sol')                                                # sin `al_trozo`, la petición de siempre
    assert pedidas[1][0].endswith('/y/with-timestamps?output_format=pcm_24000')


def test_una_voz_que_no_va_por_trozos_entrega_la_frase_entera_de_una_vez():
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'y'})
    voz.sin_credito = 'sin crédito'                                         # se habla con la voz de Windows
    voz.locales['es'] = SimpleNamespace(sintetizar=lambda texto: (np.arange(2400, dtype=np.int16), [(0, 0.), (3, .1)]), cerrar=lambda: None)
    trozos = []
    audio, marcas, _ = voz.sintetizar('El sol.', 'es', lambda muestras, m: trozos.append((len(muestras), m)))
    assert trozos == [(2400, [(0, 0.), (3, .1)])] and len(audio) == 2400


def test_las_voces_se_usan_una_vez_al_abrir_la_sesion_para_que_la_primera_frase_no_espere(monkeypatch):
    pedidas = _flujo_eleven(monkeypatch, [])
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'general'}, voces={'en': 'voz-en', 'fr': 'voz-fr', 'de': 'voz-en'})
    for hilo in voz.preparar():
        hilo.join(5)
    assert sorted(url.split('/text-to-speech/')[1].split('/')[0] for url, _ in pedidas) == ['general', 'voz-en', 'voz-fr']   # cada voz, una vez
    assert all(len(texto) <= 4 for _, texto in pedidas)                     # una sílaba: apenas gasta crédito
    voz.sin_credito = 'sin crédito'
    assert voz.preparar() == [] and S.Voz({}).preparar() == []              # sin crédito o sin clave no se pide nada


# ---------------------------------------------------------------- IA por bloques
class Cliente:
    """Cliente falso: entrega la respuesta a trocitos, como hace la IA al escribir."""
    def __init__(self, *respuestas):
        self.respuestas, self.peticiones, self.models, self.leido = list(respuestas), [], self, 0
    def generate_content_stream(self, model, contents, config):
        self.peticiones.append(contents[1]); texto = self.respuestas.pop(0)
        for i in range(0, len(texto), 9):
            self.leido = i + 9
            yield SimpleNamespace(text=texto[i:i + 9])
    def generate_content(self, model, contents, config):
        self.peticiones.append(contents[1])
        return SimpleNamespace(text=self.respuestas.pop(0))


def _vision(*respuestas):
    pytest.importorskip('google.genai')
    v = S.Vision.__new__(S.Vision)
    v.client, v.modelo, v.historia = Cliente(*respuestas), 'falso', []
    return v


def _json(*bloques):
    return json.dumps({'bloques': list(bloques)}, ensure_ascii=False)


def test_los_bloques_se_reconocen_segun_se_van_escribiendo():
    bloques = [_bloque('Una frase con "comillas", {llaves} y ] corchetes.'), _bloque(EN, region=[[1, 2], [3, 4]])]
    entero = _json(*bloques)
    cuantos = [len(S.bloques_completos(entero[:n])) for n in range(len(entero) + 1)]
    assert cuantos == sorted(cuantos) and cuantos[0] == 0 and cuantos[-1] == 2 and 1 in cuantos
    assert [json.loads(b) for b in S.bloques_completos(entero)] == bloques
    assert S.bloques_completos('{"otra": [1, 2]}') == [] and S.bloques_completos('') == []


def test_la_ia_entrega_cada_frase_en_cuanto_la_termina_de_escribir():
    respuesta = _json(_bloque(EN), _bloque(EN2))
    v = _vision(respuesta)
    flujo = v.por_bloques('what is that?', b'jpeg', {}, 'en')
    primero = next(flujo)
    assert primero['texto'] == EN and v.client.leido < len(respuesta) - 40  # llega antes de que la IA acabe de escribir
    assert [b['texto'] for b in flujo] == [EN2]
    assert v.historia == [{'usuario': 'what is that?'}, {'respuesta': EN + ' ' + EN2}]
    assert 'Responde en inglés (English)' in v.client.peticiones[0] and len(v.client.peticiones) == 1


def test_un_gesto_mal_escrito_no_detiene_la_frase_se_narra_sin_gesto():
    v = _vision(_json(_bloque(EN, tipo='region', region='arriba'), _bloque(EN2)))
    tipos = [(b['texto'], b['tipo']) for b in v.por_bloques('what is that?', b'jpeg', {}, 'en')]
    assert tipos == [(EN, 'sin_gesto'), (EN2, 'senalar')] and len(v.client.peticiones) == 1     # sin pedir la respuesta otra vez


def test_una_frase_en_otro_idioma_no_llega_a_decirse_se_pide_corregida():
    v = _vision(_json(_bloque(EN), _bloque(ES)), _json(_bloque(EN), _bloque(EN2)))
    assert [b['texto'] for b in v.por_bloques('what is that?', b'jpeg', {}, 'en')] == [EN, EN2]
    assert 'tienen que estar en inglés' in v.client.peticiones[1]
    v = _vision(_json(_bloque(EN), _bloque(ES)), _json(_bloque(EN), _bloque(ES)))             # insiste: no se dice nada más
    flujo = v.por_bloques('what is that?', b'jpeg', {}, 'en')
    assert next(flujo)['texto'] == EN
    with pytest.raises(RuntimeError, match='no ha respondido en inglés'):
        next(flujo)
    assert v.historia[-1] == {'respuesta': EN}                              # en la conversación queda lo que sí se dijo


# ---------------------------------------------------------------- acentos de una frase sin gesto
def test_los_acentos_de_una_frase_alternan_de_brazo_empezando_por_el_que_toca():
    from so101er.config import cargar
    from so101er.control.semantico import MotorGestos
    from so101er.control.acompanamiento import solo_acentos
    motor = MotorGestos(cargar())
    audio = (np.random.default_rng(1).normal(0, 3000, 6 * 24000)).astype(np.int16)
    def activo(plan):
        return max(plan.q, key=lambda n: float(np.ptp(plan.q[n][:, :5], axis=0).max()))
    brazos = list(motor.marcos)
    planes, n = solo_acentos(motor, audio, 6.)
    assert n == 2 and [s for s, _ in planes] == [0., 3.] and [activo(p) for _, p in planes] == brazos[:2]
    otros, _ = solo_acentos(motor, audio, 6., primero=1)
    assert [activo(p) for _, p in otros] == [brazos[1], brazos[0]]
    for _, p in planes:                                                      # cada uno empieza y acaba en reposo
        for q in p.q.values():
            np.testing.assert_allclose(q[0], q[-1], atol=1e-6)
    assert solo_acentos(motor, audio[:24000], 1.) == ([], 0)                # en un segundo no cabe ninguno


# ---------------------------------------------------------------- gestos calculados en otro proceso
def test_los_gestos_se_calculan_en_otro_proceso_con_el_mismo_resultado():
    import sys
    from dataclasses import replace
    from so101er.config import cargar
    from so101er.control import calculo_aparte as C
    from so101er.control.escenico import pose_reposo
    from so101er.control.semantico import MotorGestos, ejemplos
    motor = MotorGestos(cargar()); reposo = {n: pose_reposo(motor, n) for n in motor.marcos}
    g = replace(ejemplos(motor)[2][1], preparacion_s=.8, duracion_s=.3, mantener_s=.2)       # señalar con un brazo
    aqui = C.gesto(motor, g, reposo, False)
    c = C.Calculador()
    try:
        assert c.listo(60)
        fuera = c(C.gesto, motor, g, reposo, False)
        assert (c.fuera, c.dentro) == (1, 0)
        np.testing.assert_array_equal(fuera.tiempos, aqui.tiempos)
        for n in aqui.q:
            np.testing.assert_array_equal(fuera.q[n], aqui.q[n])            # el mismo plan, calculado fuera del programa
        quieto = next(n for n, q in fuera.q.items() if float(np.ptp(q[:, :5], axis=0).max()) < 1e-6)
        acompanado = c(C.acompanado, motor, fuera, 1.)
        assert float(np.ptp(acompanado.q[quieto][:, :5], axis=0).max()) > 1                   # el brazo libre ya no espera quieto
        np.testing.assert_allclose(acompanado.q[quieto][0], acompanado.q[quieto][-1], atol=1e-6)
        lento = c(C.alargado, motor, fuera, .7)
        assert lento.inicio_trazo == pytest.approx(fuera.inicio_trazo + .7) and lento.tiempos[-1] == pytest.approx(fuera.tiempos[-1] + .7)
        with pytest.raises(AttributeError):                                 # un error del cálculo llega tal cual…
            c(C.gesto, motor, None, reposo, False)
        assert c.listo() and c.dentro == 0                                  # …y no tumba el proceso ni repite el cálculo aquí
    finally:
        c.cerrar()
    intervalo = sys.getswitchinterval()
    assert not c.listo()
    sin_proceso = c(C.gesto, motor, g, reposo, False)                       # sin el otro proceso se calcula aquí mismo
    np.testing.assert_array_equal(sin_proceso.tiempos, aqui.tiempos)
    assert c.dentro == 1 and sys.getswitchinterval() == pytest.approx(intervalo)


# ---------------------------------------------------------------- el turno
class Altavoz:
    """Reloj de pared en vez de tarjeta de sonido. Guarda lo que se le añade y cuándo."""
    creados = []
    def __init__(self, audio, previo_s=0., frecuencia=24000, abierto=False):
        self.previo_s, self.fin, self.abierto = previo_s, len(audio) / 24000, abierto
        self.terminado, self.cerrado, self.anadidos = threading.Event(), False, []
        Altavoz.creados.append(self)
    def iniciar(self): self.t = time.perf_counter()
    def posicion(self): return time.perf_counter() - self.t - self.previo_s
    def anadir(self, audio, pausa_s=0.):
        inicio = max(self.fin, self.posicion()) + pausa_s
        self.fin = inicio + len(audio) / 24000; self.anadidos.append((inicio, len(audio), time.perf_counter())); return inicio
    def cerrar_entrada(self): self.abierto = False
    def cerrar(self): self.cerrado = True


def _voz(sucesos, duracion=.4):
    """Voz falsa: dos trozos por frase y marcas uniformes."""
    def sintetizar(texto, idioma, al_trozo):
        n = int(duracion * 24000); audio = np.full(n, 100, np.int16)
        marcas = [(i, i * duracion / len(texto)) for i in range(len(texto))]
        sucesos.append(('voz', texto[:12], idioma))
        al_trozo(audio[:n // 2], marcas[:len(marcas) // 2]); time.sleep(.02); al_trozo(audio[n // 2:], marcas)
        return audio, marcas, 'falsa'
    return SimpleNamespace(sintetizar=sintetizar, aviso=None, cerrar=lambda: None)


@pytest.fixture
def altavoz(monkeypatch):
    import so101er.sincronia.reproductor as modulo
    Altavoz.creados = []
    monkeypatch.setattr(modulo, 'Reproductor', Altavoz)
    return Altavoz


def _sesion_de_pega(sucesos):
    from so101er.aplicacion import SesionIntegrada
    avisos = []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.notificar, s.lock, s.ticket, s.cancel = avisos.append, threading.RLock(), 0, threading.Event()
    s.control = SimpleNamespace(frenada=None, error=None, parar=lambda: sucesos.append(('parar',)))
    s.real = False; s.brazos = {}; s.desplegar = lambda: 0.; s.jpeg = lambda: b''; s.estado = lambda: {}; s.inicio_plan = lambda: {}
    s.modelo, s.keys, s.dataset, s._seguimiento, s.directo, s.en_turno = 'falso', {}, 'seg', None, None, 0
    s._informar_carga = lambda: None
    s.voz = _voz(sucesos); s.pool = ThreadPoolExecutor(2); s.por_frases = True
    return s, avisos


def test_el_turno_empieza_a_hablar_con_la_primera_frase_sin_esperar_a_las_demas(altavoz):
    from so101er.aplicacion import SesionIntegrada
    sucesos = []
    s, avisos = _sesion_de_pega(sucesos)
    def por_bloques(texto, jpeg, estado, idioma):
        for frase in (EN, EN2):
            sucesos.append(('ia', frase[:12], idioma)); time.sleep(.05)
            yield {'texto': frase, 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}
    s.vision = SimpleNamespace(por_bloques=por_bloques)
    t0 = time.perf_counter()
    SesionIntegrada._turno(s, 'what is that?', None, threading.Event(), 0, 'en')
    s.pool.shutdown()
    # La primera frase se manda a la voz antes de que la IA entregue la segunda, y todo en el idioma del turno.
    assert sucesos == [('ia', EN[:12], 'en'), ('voz', EN[:12], 'en'), ('ia', EN2[:12], 'en'), ('voz', EN2[:12], 'en')]
    player, = altavoz.creados
    assert player.cerrado and not player.abierto and len(player.anadidos) == 4
    assert player.anadidos[0][2] - t0 < .5                                   # suena enseguida: no espera a la segunda frase
    inicios = [a[0] for a in player.anadidos]
    assert inicios[1] == pytest.approx(inicios[0] + .2) and inicios[2] >= inicios[0] + .4 + SesionIntegrada.PAUSA_FRASES - 1e-6
    dicho = [a for a in avisos if a.endswith('[seg; falsa]')]
    assert dicho == [EN + ' [seg; falsa]', EN2 + ' [seg; falsa]']
    assert any(a.startswith('Primera palabra a los 0.') for a in avisos) and avisos[-1].startswith('Listo.')
    assert s.en_turno == 0 and not any(a.startswith('Error') for a in avisos)
    assert sum('se narra sin gesto' in a for a in avisos) == 2


def test_si_la_ia_falla_a_mitad_se_dice_y_lo_ya_hablado_no_se_repite(altavoz):
    from so101er.aplicacion import SesionIntegrada
    sucesos = []
    s, avisos = _sesion_de_pega(sucesos)
    def por_bloques(texto, jpeg, estado, idioma):
        yield {'texto': EN, 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}
        raise RuntimeError('la IA no ha respondido en inglés ni al pedírselo otra vez')
    s.vision = SimpleNamespace(por_bloques=por_bloques)
    SesionIntegrada._turno(s, 'what is that?', None, threading.Event(), 0, 'en')
    s.pool.shutdown()
    assert [x for x in sucesos if x[0] == 'voz'] == [('voz', EN[:12], 'en')] and ('parar',) in sucesos
    assert any(a.startswith('Error: la IA no ha respondido en inglés') for a in avisos) and s.en_turno == 0
    assert altavoz.creados[0].cerrado


def test_un_turno_interrumpido_no_sigue_hablando(altavoz):
    from so101er.aplicacion import SesionIntegrada
    sucesos = []
    s, avisos = _sesion_de_pega(sucesos)
    cancel = threading.Event()
    def bloques():
        yield {'texto': EN, 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}
        cancel.set()                                                        # el operador interrumpe mientras se prepara la segunda
        yield {'texto': EN2, 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}
    SesionIntegrada._turno(s, '', bloques(), cancel, 0, 'en')
    time.sleep(.1); s.pool.shutdown()
    assert [x for x in sucesos if x[0] == 'voz'] == [('voz', EN[:12], 'en')]
    assert not any(a.startswith(('Error', 'Listo')) for a in avisos) and s.en_turno == 0


def test_sin_marcar_frase_a_frase_el_turno_es_el_de_siempre():
    from so101er.aplicacion import SesionIntegrada
    s = SesionIntegrada.__new__(SesionIntegrada)
    assert s.por_frases is False                                            # quien no lo active sigue con el turno entero
    usados = []
    s._turno_entero = lambda *a: usados.append('entero'); s._turno_por_frases = lambda *a: usados.append('frases')
    s._turno('x', None, None, 0); s.por_frases = True; s._turno('x', None, None, 0)
    assert usados == ['entero', 'frases']
    from so101er.config import cargar
    assert cargar().conversacion['por_frases'] is True                      # en el programa viene activado


def test_un_turno_completo_en_simulacion_coloca_gestos_y_acentos_sin_pisarse(altavoz):
    """Sesión simulada de verdad (motor de gestos y control reales), con voz y altavoz falsos."""
    from conftest import RAIZ
    from so101er.aplicacion import SesionIntegrada, demo_bloques
    avisos, sucesos = [], []
    s = SesionIntegrada(RAIZ, real=False, ventana=False, notificar=avisos.append)
    try:
        s.voz = _voz(sucesos, duracion=5.); s.por_frases = True          # frases de 5 s: cabe el gesto de cada una
        programados = []; programar = s.control.programar
        def anotado(plan, *a, **k):
            if a: programados.append((a[0], a[0] + float(plan.tiempos[-1])))
            return programar(plan, *a, **k)
        s.control.programar = anotado
        fin = threading.Event()
        s.notificar = lambda m: (avisos.append(m), fin.set() if m.startswith(('Listo.', 'Error')) else None)
        s.enviar('', demo_bloques()[2:])                                    # dos frases: señalar y región
        assert fin.wait(40), avisos
        assert not any(a.startswith('Error') for a in avisos), avisos
        assert sum(a.endswith('[' + s.dataset + '; falsa]') for a in avisos) == 2
        assert len(programados) >= 2, (programados, avisos)                 # el gesto de cada frase, como poco
        for (_, acaba), (empieza, _) in zip(programados, programados[1:]):
            assert empieza >= acaba - 1e-6                                  # ningún plan empieza antes de que acabe el anterior
        assert any(a.startswith('Primera palabra a los') for a in avisos)
    finally:
        s.interrumpir(); s.cerrar()
