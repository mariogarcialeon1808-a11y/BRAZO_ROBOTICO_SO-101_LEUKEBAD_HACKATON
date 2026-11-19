"""Sincronía y robustez del modo real frente a la simulación. Sin hardware.

Medido con la demostración de cuatro frases: la simulación hace 4 gestos y 6 acentos con el brazo
60 ms detrás de la voz. El modo real perdía sesiones por una sola trama USB sin respuesta, daba por
buenas lecturas de temperatura imposibles y, a igual velocidad, iba 100 ms detrás (18° de los 25°
que detienen el control).
"""
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101er.hardware.usb import Bus, paquete


class SerieFalsa:
    """Responde a una lectura de 2 bytes; `fallos` respuestas iniciales se pierden o llegan corruptas."""
    def __init__(self, fallos=0, corrupta=False, error_servo=0):
        self.fallos, self.corrupta, self.error_servo, self.escritos, self.cola = fallos, corrupta, error_servo, 0, b''
    def reset_input_buffer(self): self.cola = b''
    def flush(self): pass
    def write(self, datos):
        self.escritos += 1
        cuerpo = bytes([datos[2], 4, self.error_servo, 0x34, 0x12])
        trama = b'\xff\xff' + cuerpo + bytes([(~sum(cuerpo)) & 255])
        if self.fallos:
            self.fallos -= 1
            trama = trama[:-1] + bytes([trama[-1] ^ 1]) if self.corrupta else b''
        self.cola = trama
    def read(self, n):
        out, self.cola = self.cola[:n], self.cola[n:]
        return out


def bus(serie):
    b = Bus.__new__(Bus); b.serial = serie; b.lock = threading.Lock()
    return b


@pytest.mark.parametrize('corrupta', [False, True])
def test_una_trama_perdida_o_corrupta_se_repite_y_no_detiene(corrupta):
    b = bus(SerieFalsa(fallos=2, corrupta=corrupta))
    assert b.leer(3, 56, 2) == b'\x34\x12'
    assert b.serial.escritos == 3 and b.reintentos == 2


def test_tres_fallos_seguidos_si_son_un_error_y_el_del_servo_no_se_repite():
    b = bus(SerieFalsa(fallos=3))
    with pytest.raises(TimeoutError, match='servo 3 sin respuesta válida'):
        b.leer(3, 56, 2)
    assert b.serial.escritos == 3
    b = bus(SerieFalsa(error_servo=32))                    # el servo contesta con su propio código de error
    with pytest.raises(IOError, match='servo 3: error 32'):
        b.leer(3, 56, 2)
    assert b.serial.escritos == 1
    b = bus(SerieFalsa(fallos=5))                          # una orden a todos (254) no espera respuesta
    assert b.orden(254, 0x83, [41, 7]) == b'' and b.serial.escritos == 1
    assert paquete(1, 2, [56, 8])[:2] == b'\xff\xff'


def test_la_consigna_real_se_adelanta_el_retardo_de_la_cadena_usb():
    from so101er.config import cargar
    from so101er.control.semantico import MotorGestos
    from so101er.control.escenico import pose_reposo
    from so101er.control.reproduccion import ControlLocal
    motor = MotorGestos(cargar()); reposo = pose_reposo(motor)

    class Brazo:
        telemetria_temperatura = False
        def __init__(self, retardo):
            self.enviados = []
            if retardo: self.retardo_s = retardo
        def leer_articulaciones(self): return reposo.copy()
        def enviar_objetivo(self, q): self.enviados.append(q.copy())

    def plan_de_prueba():
        # El giro de pinza vale 10 grados por segundo de plan: revela qué instante se ha muestreado.
        return SimpleNamespace(muestra=lambda t: {n: reposo + [0, 0, 0, 0, 10 * t, 0] for n in motor.marcos})

    for retardo in (0., .06):
        brazos = {n: Brazo(retardo) for n in motor.marcos}
        c = ControlLocal(motor, brazos)
        try:
            assert c.adelanto == retardo
            c.programar(plan_de_prueba(), inicio=0., reloj=lambda: 1.0)   # reloj de la voz detenido en 1,0 s
            limite = time.perf_counter() + 2
            while time.perf_counter() < limite and not any(abs(q[4] - reposo[4]) > 1 for q in brazos['izq'].enviados):
                time.sleep(.01)
            assert c.error is None
            muestreado = (brazos['izq'].enviados[-1][4] - reposo[4]) / 10
            assert muestreado == pytest.approx(1.0 + retardo, abs=1e-6)
        finally:
            c.cerrar()


def test_el_selector_cambia_a_la_vez_planificacion_rampa_y_perfil_del_servo():
    import so101er.hardware.manual_usb as usb
    from so101er.aplicacion import SesionIntegrada
    from so101er.config import cargar
    avisos = []; parado = []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.real, s.liberado, s.notificar, s.lock, s.cfg, s.velocidad = True, False, avisos.append, threading.RLock(), cargar(), 60.
    s.interrumpir = lambda: parado.append(1)
    nativos = []
    for _ in range(2):
        n = usb.ManualUSB.__new__(usb.ManualUSB); n.speed = 227; n.vel = 60.; nativos.append(n)
    s.brazos = {'izq': SimpleNamespace(native=nativos[0]), 'der': SimpleNamespace(native=nativos[1])}
    simulacion = cargar().limites
    s.fijar_velocidad(150)
    assert parado and s.velocidad == 150 and 'simulación' in avisos[-1]
    # Base, hombro y codo, que son los que marcan la duración de un gesto, quedan como en simulación.
    np.testing.assert_array_equal(s.cfg.limites.velocidad[:3], simulacion.velocidad[:3])
    np.testing.assert_array_equal(s.cfg.limites.aceleracion[:3], simulacion.aceleracion[:3])
    for n in nativos:
        assert n.vel == 150 and n._rampa()[0] > 150 and n._perfil(1)[1] > 150 * usb.CUENTAS_GRADO
    s.fijar_velocidad(999)                                  # nunca más que la simulación
    assert s.velocidad == 150
    s.fijar_velocidad(5)                                    # ni menos que el perfil de pruebas
    assert s.velocidad == 20 and nativos[0]._perfil(1) == (15, 341)
    s.liberado = True; s.fijar_velocidad(90)
    assert s.velocidad == 20                                # sin par no se cambia nada
