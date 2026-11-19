from pathlib import Path
import numpy as np
import pytest
from so101er.hardware.sensores import Encoders
from so101er.hardware.usb import paquete
from so101er.fk_humana_nominal import convertir_nominal
from so101er.aplicacion_servicios import validar_bloques,tiempo_ancla
from so101er.config import cargar
from so101er.control.semantico import MotorGestos,ejemplos


def test_retardo_encoder_y_sin_acceso_a_verdad():
    e=Encoders();e.adquirir(0,np.zeros(6));initial=e.leer(0)
    e.adquirir(.01,np.full(6,10));np.testing.assert_array_equal(e.leer(.01),initial)
    e.adquirir(.02,np.full(6,20));np.testing.assert_array_equal(e.leer(.02),initial)
    assert np.max(abs(e.leer(.04)[:5]-20))<.4


def test_mujoco_sensorial_invariancia_completa_compilador():
    pytest.importorskip('mujoco')
    from so101er.hardware.mujoco_sim import MundoMuJoCo
    from so101er.interfaz.visor import cuadro_sintetico
    m=MotorGestos(cargar());_,g,q=ejemplos(m)[0]
    w=MundoMuJoCo(m.cfg,list(m.marcos),cuadro_sintetico())
    try:
        arms={n:w.brazo(n,initial) for n,initial in q.items()}
        assert w.modelo.nsensor==12
        observed={n:b.leer_articulaciones() for n,b in arms.items()}
        a=m.compilar(g,observed)
        from so101er.control.escenico import compilar_actuacion
        escenico_a=compilar_actuacion(m,g,observed)
        # No actualizar sensores: el ensayo cambia únicamente verdad privilegiada.
        w.datos.qpos[:]+=.8;w.datos.qvel[:]=5;w.datos.xfrc_applied[:]=400
        second={n:b.leer_articulaciones() for n,b in arms.items()}
        for n in observed:np.testing.assert_array_equal(observed[n],second[n])
        b=m.compilar(g,second)
        for n in a.q:np.testing.assert_array_equal(a.q[n],b.q[n])
        escenico_b=compilar_actuacion(m,g,second)
        for n in escenico_a.q:np.testing.assert_array_equal(escenico_a.q[n],escenico_b.q[n])
        assert all(not arm.telemetria_carga for arm in arms.values())
    finally:w.cerrar()


def test_fk_nominal_conserva_rotaciones_no_anatomia(tmp_path):
    p=tmp_path/'raw.npz';out=tmp_path/'joints.npz'
    poses=np.zeros((3,165));poses[1,18*3+2]=np.pi/2
    np.savez(p,poses=poses,trans=np.zeros((3,3)))
    convertir_nominal(p,out)
    with np.load(out) as f:
        j=f['joints_xyz']
        np.testing.assert_allclose(j[0,20]-j[0,16],[.54,0,0],atol=1e-8)
        np.testing.assert_allclose(j[1,20]-j[1,16],[.28,.26,0],atol=1e-8)
        assert 'nominal' in str(f['conversion'])


def test_paquete_usb_y_validacion_ia():
    p=paquete(1,2,[56,2]);assert p[:2]==b'\xff\xff' and (sum(p[2:])&255)==255
    blocks=[{'texto':'Observa este punto.','tipo':'senalar','brazo':'der','punto':[200,800],'ancla':1}]
    assert validar_bloques({'bloques':blocks})==blocks
    assert tiempo_ancla('Observa este punto.',1,[(0,0),(8,.5),(13,1)],2)==.5
    blocks[0]['punto']=[0,1001]
    with pytest.raises(ValueError):validar_bloques({'bloques':blocks})


@pytest.mark.parametrize('dataset',['beat2','mmconv'])
def test_muestras_reales_transformadas(dataset):
    from so101er.control.referencias import Motivo,adaptar,forma_en_marco
    root=Path(__file__).resolve().parents[1]
    f=root/'datos/referencias'/dataset/f'motivo_{dataset}.json'
    if not f.exists():pytest.skip('datos privados no instalados')
    clip=Motivo.cargar(f);m=MotorGestos(cargar());_,g,enc=ejemplos(m)[0]
    m.compilar(adaptar(clip,g),enc)
    frame=m.marcos['izq']
    mapped=forma_en_marco(clip,frame.a_mundo([m.modelo.eje_pan[0]+235,0,220]),
                         frame.rot@np.array([[0,0,1],[1,0,0],[0,1,0]]),
                         [1,12,12],frame.dir_a_mundo([1,0,0]),'izq')
    m.compilar(mapped,enc)

