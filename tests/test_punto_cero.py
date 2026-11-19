"""Botón «Volver a punto cero» y el fallo «actuación supera límites de movimiento». Sin hardware."""
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101er.config import cargar
from so101er.control.acompanamiento import acento, acompanar, completar, preparar_antes
from so101er.control.escenico import pose_reposo, validar
from so101er.control.semantico import MotorGestos


@pytest.fixture(scope='module')
def motor():
    return MotorGestos(cargar())


def test_acompanar_antes_de_alargar_la_preparacion_rompia_el_turno(motor):
    from dataclasses import replace
    from so101er.control.escenico import compilar_actuacion
    from so101er.control.semantico import ejemplos
    _, g, inicial = next(e for e in ejemplos(motor) if e[0] == 'punto')      # un gesto real: señalar con un brazo
    reposo = {n: pose_reposo(motor) for n in inicial}
    gesto = compilar_actuacion(motor, replace(g, preparacion_s=.8, duracion_s=.3, mantener_s=.2), reposo)
    libre = next(n for n in gesto.q if n != g.brazo)
    assert np.ptp(gesto.q[libre][:, :5], axis=0).max() == 0   # sin acompañamiento, el otro brazo no se mueve
    preparar_antes(motor, gesto, 2.0)                         # alargar la preparación del gesto solo: válido
    # El orden anterior: el brazo libre aún está subiendo cuando acaba la preparación, y al alargar
    # solo ese tramo su velocidad da un salto. Era el «Error: actuación supera límites de movimiento».
    acompanado = acompanar(motor, gesto)
    assert np.ptp(acompanado.q[libre][:, 3]) > 4
    with pytest.raises(ValueError, match='movimiento'):
        preparar_antes(motor, acompanado, 2.0)
    # Ahora `completar` ajusta primero los tiempos y añade el acompañamiento al final.
    fin = float(gesto.tiempos[-1]) + 2.0
    planes, _ = completar(motor, [(2.0, gesto)], np.zeros(int(fin * 24000), np.int16), fin)
    primero = planes[0][1]
    assert planes[0][0] == 0 and primero.inicio_trazo == pytest.approx(gesto.inicio_trazo + 2.0)
    assert np.ptp(primero.q[libre][:, 3]) > 4                # el brazo libre acompaña
    for _, plan in planes:
        validar(motor, plan.tiempos, plan.q)


def _nativo():
    import so101er.hardware.manual_usb as usb
    n = usb.ManualUSB.__new__(usb.ManualUSB)
    n.lock = threading.RLock()
    n.coords = SimpleNamespace(low=np.full(6, 1000.), high=np.full(6, 3000.))
    n.measured = np.array([2000., 2100., 990., 2000., 2000., 2000.])     # el codo, algo fuera del margen
    n.cmd = np.full(6, 2500.); n.target = n.cmd.copy()
    n.error = 'COM7, apertura de pinza (ID 6): carga indicada 476'; n._desfase_desde = 3.0; n.enviado = (227, 1)
    return n


def test_reanudar_parte_de_lo_que_miden_los_encoders():
    n = _nativo()
    n.reanudar()
    assert n.error is None and n._desfase_desde is None and n.enviado is None
    np.testing.assert_array_equal(n.cmd, [2000, 2100, 1000, 2000, 2000, 2000])   # medido, dentro del rango guardado
    np.testing.assert_array_equal(n.target, n.cmd)


def _sesion(error):
    from so101er.aplicacion import SesionIntegrada
    avisos = []; llamadas = []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.real, s.liberado, s.notificar, s.lock = True, False, avisos.append, threading.RLock()
    s.cfg = cargar(); s.velocidad = 110.; s.desplegado = True; s.cancel = threading.Event()
    s.plegado = {'izq': np.zeros(6)}
    s.interrumpir = lambda: llamadas.append('interrumpir')
    s.brazos = {'izq': SimpleNamespace(native=SimpleNamespace(reanudar=lambda: llamadas.append('servo reanudado')))}
    control = SimpleNamespace(error=error, frenada=None)
    def reanudar():
        control.error = None; llamadas.append('control reanudado')
    control.reanudar = reanudar
    s.control = control
    def mover(destino, aviso):
        llamadas.append((aviso, float(s.cfg.limites.velocidad[0]))); return time.perf_counter() - 1
    s._mover_a = mover
    return s, avisos, llamadas


def _espera(avisos, texto):
    limite = time.perf_counter() + 3
    while time.perf_counter() < limite and not any(texto in a for a in avisos):
        time.sleep(.01)
    assert any(texto in a for a in avisos), avisos


def test_volver_a_cero_tras_una_parada_por_carga_la_reconoce_y_vuelve_despacio():
    s, avisos, llamadas = _sesion('COM7: COM7, apertura de pinza (ID 6): carga indicada 476. Sujeta y suelta')
    s.volver_a_cero()
    _espera(avisos, 'Brazos en punto cero')
    assert llamadas == ['interrumpir', 'servo reanudado', 'control reanudado', ('Volviendo a punto cero', 30.)]
    assert any('Parada reconocida' in a for a in avisos) and s.desplegado is False
    assert s.cfg.limites.velocidad[0] == 110                 # el perfil de trabajo se recupera al acabar
    assert s.plegar.__func__ is s.volver_a_cero.__func__     # el nombre anterior sigue valiendo


@pytest.mark.parametrize('parada', ['COM8, hombro (ID 2): 58 °C sostenidos. Sujeta y suelta el brazo',
                                    'tensión fuera de margen', 'COM8: servo 2 sin respuesta válida',
                                    'COM8: la pinza bajaría de la altura mínima sobre la mesa (25 mm)'])
def test_volver_a_cero_no_reanuda_paradas_que_exigen_soltar(parada):
    s, avisos, llamadas = _sesion(parada)
    s.volver_a_cero()
    _espera(avisos, 'Tras esta parada no se puede volver a punto cero')
    assert llamadas == ['interrumpir'] and s.control.error == parada


def test_volver_a_cero_sin_parada_solo_interrumpe_y_vuelve():
    s, avisos, llamadas = _sesion(None)
    s.volver_a_cero()
    _espera(avisos, 'Brazos en punto cero')
    assert llamadas == ['interrumpir', ('Volviendo a punto cero', 30.)]
    s.liberado = True; llamadas.clear(); s.volver_a_cero()
    assert llamadas == []                                    # sin par no se mueve nada


def test_control_reanudado_vuelve_a_seguir_planes():
    from so101er.control.reproduccion import ControlLocal
    motor = MotorGestos(cargar()); reposo = pose_reposo(motor)

    class Brazo:
        telemetria_temperatura = False
        def __init__(self): self.enviados = 0; self.fallo = None
        def leer_articulaciones(self):
            if self.fallo: raise RuntimeError(self.fallo)
            return reposo.copy()
        def enviar_objetivo(self, q): self.enviados += 1
        def detener(self): pass

    brazos = {n: Brazo() for n in motor.marcos}
    c = ControlLocal(motor, brazos)
    try:
        brazos['izq'].fallo = 'COM7: carga indicada 476'
        limite = time.perf_counter() + 2
        while time.perf_counter() < limite and not c.error: time.sleep(.01)
        assert c.error == 'COM7: carga indicada 476'
        with pytest.raises(RuntimeError): c.reanudar()         # mientras el brazo siga en fallo, no se reanuda
        brazos['izq'].fallo = None
        c.reanudar()
        assert c.error is None and c.plan is None and c.frenada is None
        antes = brazos['izq'].enviados; time.sleep(.15)
        assert brazos['izq'].enviados > antes                   # el bucle vuelve a emitir consignas
    finally:
        c.cerrar()


def test_al_acabar_cada_respuesta_los_brazos_vuelven_a_punto_cero():
    from so101er.aplicacion import SesionIntegrada
    s, avisos, llamadas = _sesion(None)
    s.ticket = 0
    hechos = []
    s._turno_por_frases = lambda *a: hechos.append('frases'); s._turno_entero = lambda *a: hechos.append('entero')
    s.por_frases = True; s.plegar_al_acabar = True
    SesionIntegrada._turno(s, 'hola', None, threading.Event(), 0, 'es')
    assert hechos == ['frases'] and llamadas == [('Volviendo a punto cero', 30.)]      # después de la respuesta, despacio
    assert avisos[-1] == 'Brazos en punto cero.' and s.desplegado is False             # la petición siguiente los despliega
    assert s.cfg.limites.velocidad[0] == 110                                           # y el perfil de trabajo se recupera
    # No se pliega si la respuesta se interrumpió, si ya hay otra petición, si el control está detenido o si está apagado.
    for cambio in ('cancelado', 'otro turno', 'control detenido', 'apagado', 'simulación'):
        s, avisos, llamadas = _sesion('COM7: carga' if cambio == 'control detenido' else None)
        s.ticket = 1 if cambio == 'otro turno' else 0
        s._turno_por_frases = lambda *a: None; s.por_frases = True
        s.plegar_al_acabar = cambio != 'apagado'; s.real = cambio != 'simulación'
        cancel = threading.Event()
        if cambio == 'cancelado':
            cancel.set()
        SesionIntegrada._turno(s, 'hola', None, cancel, 0, 'es')
        assert llamadas == [] and s.desplegado is True, cambio
    assert SesionIntegrada.plegar_al_acabar is False                                   # quien no lo active no pliega
    assert cargar().brazos is not None


def test_una_peticion_nueva_interrumpe_la_vuelta_a_punto_cero():
    from so101er.aplicacion import SesionIntegrada
    s, avisos, llamadas = _sesion(None)
    s.ticket = 0; s._turno_por_frases = lambda *a: None; s.por_frases = True; s.plegar_al_acabar = True
    s._mover_a = lambda destino, aviso: time.perf_counter() + 30                       # una vuelta larga
    cancel = threading.Event()
    hilo = threading.Thread(target=SesionIntegrada._turno, args=(s, 'hola', None, cancel, 0, 'es'), daemon=True)
    hilo.start(); time.sleep(.15)
    assert hilo.is_alive() and s.desplegado is False
    cancel.set(); hilo.join(1)                                                         # llega otra petición
    assert not hilo.is_alive() and 'Brazos en punto cero.' not in avisos
    s._mover_a = lambda destino, aviso: (_ for _ in ()).throw(ValueError('fuera de rango'))
    SesionIntegrada._turno(s, 'hola', None, threading.Event(), 0, 'es')
    assert avisos[-1] == 'No se pudo volver a punto cero: fuera de rango' and s.cfg.limites.velocidad[0] == 110
