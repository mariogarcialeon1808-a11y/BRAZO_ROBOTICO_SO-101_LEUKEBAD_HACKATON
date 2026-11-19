import time
import numpy as np
import pytest
from so101er.config import cargar
from so101er.control.semantico import MotorGestos
from so101er.control.escenico import pose_reposo,validar
from so101er.control.acompanamiento import acento,completar
from so101er.sincronia.reproductor import Reproductor


@pytest.fixture(scope='module')
def motor():return MotorGestos(cargar())


@pytest.mark.parametrize('side',['izq','der'])
def test_acento_mueve_brazo_y_pinza_y_recoge_sin_exceder_limites(motor,side):
    plan=acento(motor,side,2.6,1.3)
    rest=pose_reposo(motor)
    assert np.ptp(plan.q[side][:,3])>13
    assert np.max(plan.q[side][:,5])==pytest.approx(75)
    for n,q in plan.q.items():
        np.testing.assert_allclose(q[0],rest)
        np.testing.assert_allclose(q[-1],rest,atol=1e-10)
        if n!=side:np.testing.assert_allclose(q,np.tile(rest,(len(q),1)))
    validar(motor,plan.tiempos,plan.q)


def test_completar_cubre_huecos_alterna_brazos_y_conserva_apices(motor):
    first=acento(motor,'izq',2.6,1.3);second=acento(motor,'der',2.6,1.3)
    voice=np.zeros(24*24000,np.int16)
    voice[9*24000:10*24000]=10000
    plans,metrics=completar(motor,[(0,first),(13,second)],voice,24)
    assert metrics['huecos_antes_s']>18
    assert metrics['huecos_despues_s']==0 and metrics['acentos']>=6
    # El gesto de cada brazo se conserva intacto; el brazo libre ya no espera inmóvil.
    np.testing.assert_array_equal(plans[0][1].q['izq'],first.q['izq'])
    np.testing.assert_array_equal(next(p for s,p in plans if s==13).q['der'],second.q['der'])
    assert plans[0][1].fin_trazo==first.fin_trazo and np.ptp(plans[0][1].q['der'][:,3])>4
    for (start,plan),(s2,p2) in zip(plans,plans[1:]):
        assert start+plan.tiempos[-1]==pytest.approx(s2)
        for n in plan.q:np.testing.assert_allclose(plan.q[n][-1],p2.q[n][0],atol=1e-10)
    assert plans[-1][0]+plans[-1][1].tiempos[-1]==pytest.approx(24)
    for _,plan in plans:validar(motor,plan.tiempos,plan.q)


def test_hueco_corto_alarga_solo_recogida(motor):
    first=acento(motor,'izq',2.6,1.3);second=acento(motor,'der',2.6,1.3)
    plans,metrics=completar(motor,[(0,first),(3.1,second)],np.zeros(6*24000,np.int16),5.7)
    result=plans[0][1]
    assert result.fin_trazo==first.fin_trazo
    assert result.inicio_retorno==first.inicio_retorno
    np.testing.assert_array_equal(result.q['izq'],first.q['izq'])
    assert result.tiempos[-1]==pytest.approx(3.1)
    assert metrics['acentos']==0 and metrics['huecos_despues_s']==0


def test_no_inventa_referentes_si_no_hay_plan(motor):
    plans,metrics=completar(motor,[],np.zeros(24000,np.int16),1)
    assert plans==[] and metrics['acentos']==0


@pytest.mark.parametrize('latency',[.015,.13,.35])
def test_reloj_dac_incluye_latencia_y_preroll_sin_adelantar_la_voz(latency):
    player=Reproductor(np.zeros(24000,np.int16),previo_s=.5)
    player.registrar_buffer(0,400+latency,400,100)
    assert player.posicion(100)==pytest.approx(-.5-latency)
    assert player.posicion(100+latency+.5)==pytest.approx(0)
    player.registrar_buffer(12000,400.5+latency,400.5,100.5)
    assert player.posicion(101+latency)==pytest.approx(.5)


def test_control_sigue_el_reloj_del_altavoz_y_su_pausa(motor):
    from so101er.control.reproduccion import ControlLocal
    class Brazo:
        telemetria_temperatura=False
        def __init__(self):self.q=pose_reposo(motor)
        def leer_articulaciones(self):return self.q.copy()
        def enviar_objetivo(self,q):self.q=q.copy()
    arms={n:Brazo() for n in motor.marcos};control=ControlLocal(motor,arms)
    clock=[100.]
    plan=acento(motor,'izq',2.6,1.3)
    try:
        control.programar(plan,99.,reloj=lambda:clock[0])
        time.sleep(.08)
        for n in arms:np.testing.assert_allclose(control.cmd[n],plan.muestra(1.)[n])
        clock[0]=100.1;time.sleep(.08)
        for n in arms:np.testing.assert_allclose(control.cmd[n],plan.muestra(1.1)[n])
        assert control.error is None
    finally:control.cerrar()


def test_el_brazo_libre_acompana_y_vuelve_exactamente_a_donde_estaba(motor):
    from so101er.control.acompanamiento import acompanar,SIMPATIA
    solo=acento(motor,'izq',3.0,1.4)
    rest=pose_reposo(motor)
    np.testing.assert_allclose(solo.q['der'],np.tile(rest,(len(solo.tiempos),1)))   # antes: inmóvil todo el plan
    plan=acompanar(motor,solo)
    np.testing.assert_array_equal(plan.q['izq'],solo.q['izq'])                       # el gesto no se toca
    np.testing.assert_array_equal(plan.tiempos,solo.tiempos)
    libre=plan.q['der']
    np.testing.assert_allclose(libre[0],rest);np.testing.assert_allclose(libre[-1],rest,atol=1e-10)
    np.testing.assert_allclose(np.max(abs(libre[:,:5]-rest[:5]),axis=0),abs(SIMPATIA),rtol=1e-6)
    assert np.max(libre[:,5])==pytest.approx(45)
    validar(motor,plan.tiempos,plan.q)
    # Se mueve casi todo el plan: menos de 0,8 s seguidos por debajo de 1 grado/s.
    v=np.max(abs(np.diff(libre[:,:5],axis=0)),axis=1)/np.diff(plan.tiempos)
    quieto=0.;peor=0.
    for parado,dt in zip(v<1.,np.diff(plan.tiempos)):
        quieto=quieto+dt if parado else 0.;peor=max(peor,quieto)
    assert peor<.8
    # Un plan en el que ya se mueven los dos brazos no se altera.
    assert acompanar(motor,plan) is plan


def test_acompanar_no_se_aplica_si_no_cabe_y_solo_usa_consignas(motor):
    from so101er.control.acompanamiento import acompanar
    solo=acento(motor,'izq',3.0,1.4)
    def no_cabe(plan):raise ValueError('fuera de los rangos guardados del brazo real')
    assert acompanar(motor,solo,comprobar=no_cabe) is solo        # los rangos del brazo real mandan
    corto=acento(motor,'izq',1.6,.8);corto.fin_trazo=.5            # sin tiempo para subir con suavidad
    assert acompanar(motor,corto) is corto
    a=acompanar(motor,solo)
    motor.verdad_privilegiada=np.full(12,9.)                       # cambiar verdad interna no cambia la acción
    b=acompanar(motor,solo)
    del motor.verdad_privilegiada
    for n in a.q:np.testing.assert_array_equal(a.q[n],b.q[n])
