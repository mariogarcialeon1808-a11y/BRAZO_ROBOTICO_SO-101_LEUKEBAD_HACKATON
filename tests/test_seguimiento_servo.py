"""Seguimiento consigna–encoder del control USB real, sin hardware.

Causa del fallo «apertura de pinza (ID 6): no sigue la consigna»: el servo recibía
aceleración 5 y una velocidad máxima igual a la de la rampa de consigna, así que la pinza
(60°/s) iba hasta 27° por detrás y una sola lectura por encima de 8° detenía la sesión.
"""
import threading
from types import SimpleNamespace

import numpy as np
import pytest

import so101er.hardware.manual_usb as module

CG = module.CUENTAS_GRADO


def cal():
    return {'puerto': 'COM7', 'serie_usb': 'A', 'rangos': {str(i): {'min_raw': 1000, 'max_raw': 3000} for i in range(1, 7)},
            'identidad_servos': [{'id': i, 'min_raw': 1000, 'max_raw': 3000, 'modelo_raw': 777, 'modo': 0, 'offset_raw': 0}
                                 for i in range(1, 7)]}


def test_perfil_del_servo_da_margen_sobre_la_rampa():
    c = module.ManualUSB.__new__(module.ManualUSB)
    c.speed = 227                                           # funcionamiento normal
    assert [c._perfil(i) for i in range(1, 6)] == [(15, 341)] * 5
    assert c._perfil(6) == (60, 1024)                       # la pinza: más aceleración y más margen
    for i in range(1, 7):
        acel, vel = c._perfil(i)
        rampa = 684 if i == 6 else 227
        assert vel > rampa and 1 <= acel <= 254 and vel < 4096
    c.speed = 11                                            # entrada inicial lenta: sin cambios
    assert [c._perfil(i) for i in range(1, 7)] == [(5, 11)] * 6


@pytest.mark.parametrize('v', [20, 60, 90, 150])
def test_a_cualquier_velocidad_configurada_el_servo_modelado_sigue_su_rampa(v):
    c = module.ManualUSB.__new__(module.ManualUSB)
    c.speed, c.vel = 227, float(v)
    rampa = c._rampa()
    assert rampa[0] >= v and rampa[5] >= 60                 # la consigna nunca va más lenta que el plan
    sostenido, inmediato = c._desfases()
    assert sostenido >= module.DESFASE_MAX and inmediato > sostenido
    for i, recorrido in ((2, 90 * CG), (6, 1430)):          # 90° de hombro; pinza de extremo a extremo
        acel, vel = c._perfil(i)
        assert 1 <= acel <= 254 and vel <= 3400
        plan = v if i != 6 else max(60, v)                  # velocidad máxima que pide la planificación
        peor = _desfase_modelado(recorrido, 1.875 * recorrido / (plan * CG), rampa[i - 1], vel, acel)
        assert peor < sostenido, (v, i, peor / CG)


def test_velocidad_real_se_lee_de_la_configuracion_y_se_acota(tmp_path):
    (tmp_path / 'config').mkdir()
    f = tmp_path / 'config/so101er.toml'
    assert module.velocidad_real(tmp_path) == 20            # sin archivo: perfil de pruebas
    for texto, esperado in (('[real]\nvelocidad_grados_s = 90\n', 90), ('[real]\nvelocidad_grados_s = 900\n', 150),
                            ('[real]\nvelocidad_grados_s = 3\n', 20), ('[real]\nvelocidad_grados_s = "x"\n', 20),
                            ('[voz]\nx = 1\n', 20)):
        f.write_text(texto, encoding='utf8')
        assert module.velocidad_real(tmp_path) == esperado


def _controlador(monkeypatch, desfases_grados, ciclo_s=0.03, temperaturas=None, carga=None, velocidad=None):
    """Ejecuta el bucle con el encoder de la pinza a `desfase` grados de la consigna en cada ciclo."""
    c = module.ManualUSB.__new__(module.ManualUSB)
    c.port = 'COM7'
    c.lock = threading.RLock()
    c.measured = np.full(6, 2000.)
    c.cmd = c.measured.copy()
    c.target = c.cmd.copy()
    c.speed = 227
    c.error = None
    c.entrando = False
    c.coords = module.Coordenadas(cal(), c.measured)
    c.stop = threading.Event()
    c.bus = SimpleNamespace(orden=lambda *a: None)
    reloj = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: reloj[0])
    import itertools
    lecturas = itertools.chain(desfases_grados, itertools.repeat(desfases_grados[-1]))   # el control relee al confirmar

    def estado(_):
        raw = np.full(6, 2000)
        raw[5] = round(2000 - next(lecturas) * CG)          # solo cambia lo que mide el encoder
        calor = np.full(6, 25)
        if temperaturas is not None:
            calor[1] = next(temperaturas)
        lectura = dict(raw=raw, temperatura=calor, voltaje=np.full(6, 120), carga=np.zeros(6))
        if carga is not None:
            lectura['carga'][5] = carga                        # la pinza
        if velocidad is not None:
            lectura['velocidad'] = np.zeros(6); lectura['velocidad'][5] = velocidad
        return lectura

    monkeypatch.setattr(module, 'estado', estado)
    quedan = [len(desfases_grados)]

    def esperar(_):
        reloj[0] += ciclo_s
        quedan[0] -= 1
        if quedan[0] <= 0:
            c.stop.set()

    monkeypatch.setattr(c.stop, 'wait', esperar)
    c._loop()
    return c


def test_lecturas_sueltas_de_temperatura_no_detienen_y_el_calor_sostenido_si(monkeypatch):
    # Como en los brazos: una lectura de cada cinco es imposible (57–142 °C) y la siguiente vuelve a ~28 °C.
    sueltas = iter([142 if k % 5 == 0 else 28 for k in range(200)])
    c = _controlador(monkeypatch, [0] * 200, temperaturas=sueltas)
    assert c.error is None and not getattr(c, 'aviso', None)
    # Un motor que de verdad está a 58 °C durante segundos sí detiene, y dice cuál.
    c = _controlador(monkeypatch, [0] * 200, temperaturas=iter([58] * 200))
    assert c.error and 'hombro (ID 2): 58 °C sostenidos' in c.error


def test_la_carga_descuenta_la_velocidad_medida(monkeypatch):
    # La pinza abriéndose en el aire a ~137 grados/s (1560 cuentas/s) indicó 452–484 en los brazos.
    libre = dict(carga=np.array([0, 448, 0, 0, 0, 484.]), velocidad=np.array([0, 1250, 0, 0, 0, 1560.]))
    neta = module.carga_neta(libre)
    assert neta[5] < 100 and neta[1] < 150 and module.anomalia({**libre, 'voltaje': np.full(6, 120)}) is None
    # Con el servo parado (contra un obstáculo o un tope) no se descuenta nada: protege como antes.
    parado = dict(carga=np.array([0, 0, 0, 0, 0, 484.]), velocidad=np.zeros(6), voltaje=np.full(6, 120))
    assert module.carga_neta(parado)[5] == 484
    assert module.anomalia(parado) == 'apertura de pinza (ID 6) con carga 484'
    # Sin lectura de velocidad (o con una absurda) nunca se descuenta más del 80 % del ciclo de trabajo.
    assert module.carga_neta(dict(carga=np.full(6, 484.)))[0] == 484
    assert module.carga_neta(dict(carga=np.full(6, 1000.), velocidad=np.full(6, 30000.)))[0] == pytest.approx(200)
    # En el bucle: moviéndose libre no detiene; el mismo valor con el servo parado sí, y lo dice.
    c = _controlador(monkeypatch, [0] * 40, carga=484, velocidad=1560)
    assert c.error is None and c.carga_pico[5] < 100 and c.carga_bruta_pico[5] == 484
    c = _controlador(monkeypatch, [0] * 40, carga=484, velocidad=0)
    assert c.error and 'apertura de pinza (ID 6): carga indicada 484.' in c.error
    # Un esfuerzo grande de verdad detiene aunque el servo se mueva.
    c = _controlador(monkeypatch, [0] * 40, carga=900, velocidad=1560)
    assert c.error and 'carga indicada 900 (494 descontada su velocidad)' in c.error


def test_un_desfase_breve_no_detiene(monkeypatch):
    # 12° durante 5 ciclos de 30 ms (0,15 s): el retraso normal del servo al acelerar.
    c = _controlador(monkeypatch, [0, 12, 12, 12, 12, 12, 3, 0, 0])
    assert c.error is None and c._desfase_desde is None


def test_un_desfase_sostenido_si_detiene_y_dice_cuanto(monkeypatch):
    c = _controlador(monkeypatch, [0] + [12] * 14)
    assert c.error and 'apertura de pinza (ID 6): no sigue la consigna' in c.error
    assert '12° de desfase durante 0.' in c.error


def test_un_desfase_grande_detiene_en_la_misma_lectura(monkeypatch):
    c = _controlador(monkeypatch, [0, 25, 0, 0])
    assert c.error and '25° de desfase)' in c.error


def test_el_aviso_de_telemetria_dice_que_medida_y_que_motor(monkeypatch):
    def muestra(temp=25, voltaje=120, carga=0, motor=3):
        t, v, c = np.full(6, 25), np.full(6, 120), np.zeros(6)
        t[motor], v[motor], c[motor] = temp, voltaje, carga
        return dict(temperatura=t, voltaje=v, carga=c)

    assert module.anomalia(muestra()) is None
    assert module.anomalia(muestra(temp=61)) is None            # la temperatura se vigila por su mediana, no aquí
    assert module.anomalia(muestra(voltaje=96, motor=0)) == 'base (ID 1) con tensión 9.6 V'
    assert module.anomalia(muestra(carga=480, motor=5)) == 'apertura de pinza (ID 6) con carga 480'
    lecturas = iter([muestra(carga=480, motor=5), muestra()])
    monkeypatch.setattr(module, 'estado', lambda _: next(lecturas))
    _, aviso = module.estado_confirmado(None)
    assert aviso.endswith('apertura de pinza (ID 6) con carga 480')


def _desfase_modelado(recorrido, duracion, rampa_gps, vel_servo, acel_reg, ciclo=0.031):
    """Servo con perfil trapezoidal persiguiendo la rampa de consigna: desfase máximo en cuentas."""
    dt, acel = 0.001, acel_reg * 100.0
    pos = vel = cmd = t = prox = peor = 0.0
    while t < duracion + 1.5:
        if t >= prox:
            peor = max(peor, abs(cmd - pos))
            s = min(t / duracion, 1.0)
            objetivo = recorrido * s**3 * (10 + s * (-15 + 6 * s))
            paso = rampa_gps * CG * min(ciclo, 0.04)
            cmd += float(np.clip(objetivo - cmd, -paso, paso))
            prox += ciclo
        e = cmd - pos
        v_des = np.sign(e) * min(vel_servo, (2 * acel * abs(e)) ** 0.5)
        vel += float(np.clip(v_des - vel, -acel * dt, acel * dt))
        pos += vel * dt
        t += dt
    return peor


@pytest.mark.parametrize('nombre, i, recorrido, duracion, rampa', [
    ('pinza: abrir del todo (Saludo)', 6, 1430, 3.93, 60),
    ('pinza: gesto corto', 6, 436, 1.5, 60),
    ('articulación: 20 grados', 2, 228, 1.875, 20),
])
def test_con_el_perfil_nuevo_el_servo_modelado_sigue_la_consigna(nombre, i, recorrido, duracion, rampa):
    c = module.ManualUSB.__new__(module.ManualUSB)
    c.speed = 227
    acel, vel = c._perfil(i)
    assert _desfase_modelado(recorrido, duracion, rampa, vel, acel) < 0.5 * module.DESFASE_MAX, nombre
    # Con el perfil anterior (aceleración 5, velocidad igual a la rampa) la pinza superaba el umbral.
    if i == 6:
        assert _desfase_modelado(recorrido, duracion, rampa, 684, 5) > module.DESFASE_MAX


def test_control_detenido_no_consulta_a_la_ia_y_dice_que_hacer():
    from so101er.aplicacion import SesionIntegrada
    avisos = []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.real, s.liberado, s.notificar = True, False, avisos.append
    s.control = SimpleNamespace(error='COM7: COM7, apertura de pinza (ID 6): no sigue la consigna')
    s.enviar('explícame lo que ves')          # si intentara seguir, fallaría por falta de atributos
    s.bailar('Saludo')
    assert len(avisos) == 2 and all('no se consulta a la IA' in a and 'pulsa Soltar' in a for a in avisos)
    s.liberado = True
    assert s.bloqueo().startswith('Brazo sin par')
    s.liberado, s.control.error = False, None
    assert s.bloqueo() is None
