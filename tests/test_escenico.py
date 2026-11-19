import numpy as np
import pytest
from so101er.config import cargar
from so101er.control.semantico import MotorGestos,ejemplos
from so101er.control.escenico import pose_reposo,ensanchar_abanico,compilar_actuacion,validar
from so101er.sincronia.ritmo import factor_narracion,estirar


@pytest.fixture(scope='module')
def motor():return MotorGestos(cargar())


@pytest.mark.parametrize('index',range(4))
def test_amplitud_pinzas_y_regreso_completo(motor,index):
    name,g,_=ejemplos(motor)[index]
    if name in ('paisaje','cielo'):g=ensanchar_abanico(motor,g)
    initial={n:pose_reposo(motor) for n in motor.marcos}
    plan=compilar_actuacion(motor,g,initial,bilateral=name in ('paisaje','cielo'))
    assert plan.reposo_al_final and plan.inicio_retorno>plan.fin_trazo
    k=np.argmin(abs(plan.tiempos-plan.fin_trazo))
    p,axis=motor.modelo.punta(plan.q[g.brazo][k,:5])
    assert np.linalg.norm(p-motor.modelo.hombro)>.85*motor.modelo.alcance_max
    for n,q in plan.q.items():np.testing.assert_allclose(q[-1],pose_reposo(motor),atol=1e-8)
    if name=='punto':
        assert np.max(plan.q[g.brazo][:,5])==0
        frame=motor.marcos[g.brazo]
        target=motor.cuadro.punto_mundo([260,720])
        direction=target-frame.a_mundo(p);direction/=np.linalg.norm(direction)
        assert frame.dir_a_mundo(axis)@direction>np.cos(np.radians(4))
    else:
        assert np.max(plan.q[g.brazo][:,5])==100
        assert plan.q[g.brazo][-1,5]==0
    if name in ('paisaje','cielo'):
        for n,q in plan.q.items():
            assert np.linalg.norm(motor.modelo.punta(q[k,:5])[0]-motor.modelo.hombro)>.85*motor.modelo.alcance_max
            start=np.searchsorted(plan.tiempos,plan.inicio_trazo)
            xyz=np.array([motor.marcos[n].a_mundo(motor.modelo.punta(v[:5])[0]) for v in q[start:k+1]])
            assert np.ptp(xyz[:,0])>240
    if name=='camino':
        start=np.searchsorted(plan.tiempos,plan.inicio_trazo)
        xyz=np.array([motor.modelo.punta(v[:5])[0] for v in plan.q[g.brazo][start:k+1]])
        assert np.ptp(xyz[:,0])>80
        assert np.ptp(xyz[:,1])<3 and np.ptp(xyz[:,2])<3
    validar(motor,plan.tiempos,plan.q)


def test_ritmo_incluye_recogidas_sin_solaparlas():
    anchors=[1,3,5];apex=[1.5,2,1.5];durations=[5,5,5]
    factor=factor_narracion(anchors,apex,durations)
    starts=np.array(anchors)*factor-np.array(apex)
    assert np.all(np.diff(starts)>=np.array(durations[:-1]))


def test_estirar_voz_conserva_tono():
    pytest.importorskip('av')
    sample=(10000*np.sin(2*np.pi*440*np.arange(24000)/24000)).astype(np.int16)
    result=estirar(sample,1.3)
    assert len(result)==31200
    frequency=np.argmax(abs(np.fft.rfft(result)))*24000/len(result)
    assert abs(frequency-440)<3
