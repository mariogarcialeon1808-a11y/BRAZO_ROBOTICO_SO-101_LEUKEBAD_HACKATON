from dataclasses import replace
import numpy as np
import pytest
from so101er.control.referencias import leer_bvh,extraer,Motivo,adaptar,forma_en_marco
from so101er.control.semantico import MotorGestos,ejemplos
from so101er.control.anclaje import senalar_plano,barrer_region,recorrer_mundo
from so101er.config import cargar
from so101er.convertir_smplx import leer_parametros


def test_bvh_orden_canales_rotacion_y_traslacion(tmp_path):
    b=tmp_path/'motion.bvh'
    b.write_text('''HIERARCHY
ROOT Shoulder { OFFSET 0 0 0 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
JOINT Wrist { OFFSET 1 0 0 CHANNELS 3 Zrotation Xrotation Yrotation End Site { OFFSET 1 0 0 } } }
MOTION
Frames: 3
Frame Time: 0.5
0 0 0 0 0 0 0 0 0
2 0 0 90 0 0 0 0 0
2 3 0 0 90 90 0 0 0
''')
    t,n,j=leer_bvh(b)
    np.testing.assert_allclose(t,[0,.5,1])
    np.testing.assert_allclose(j[1,n.index('Wrist')],[2,1,0],atol=1e-8)
    # X luego Y intrínsecas: Ry local actúa primero sobre el offset.
    np.testing.assert_allclose(j[2,n.index('Wrist')],[2,4,0],atol=1e-8)


@pytest.fixture
def motivo(tmp_path):
    t=np.linspace(0,1,100)
    joints=np.zeros((100,2,3)); joints[:,0,1]=np.sin(t)*10
    joints[:,1]=joints[:,0]+np.column_stack([t**2,np.sin(t)*.1,t*0])
    p=tmp_path/'human.npz'
    np.savez(p,joints_xyz=joints,joint_names=['Shoulder','Wrist'])
    return extraer(p,id='fixture',fuente='sintético, NO SeG/BEAT2',licencia='fixture propia',
                   etiquetas=['extension'],hombro='Shoulder',muneca='Wrist',fps=30)


def test_importacion_procedencia_y_traslacion_root_invariante(motivo,tmp_path):
    assert motivo.perfil[4]<.15
    out=tmp_path/'m.json'; motivo.guardar(out)
    loaded=Motivo.cargar(out)
    assert loaded.sha256==motivo.sha256 and loaded.fuente==motivo.fuente
    assert len(loaded.forma)==33


def test_retarget_conserva_referente_cambia_ritmo(motivo):
    m=MotorGestos(cargar())
    _,g,q=ejemplos(m)[3]
    changed=adaptar(motivo,g)
    assert changed.puntos_mm==g.puntos_mm and changed.ejes==g.ejes
    a,b=m.compilar(g,q),m.compilar(changed,q)
    np.testing.assert_allclose(a.q[g.brazo][-1],b.q[g.brazo][-1],atol=1e-7)
    assert np.max(abs(a.muestra(2.2)[g.brazo]-b.muestra(2.2)[g.brazo]))>.1


def test_retarget_forma_en_marco(motivo):
    g=forma_en_marco(motivo,[100,200,300],np.eye(3),[20,30,40],[1,0,0],'izq')
    np.testing.assert_allclose(g.puntos_mm[0],[100,200,300])
    assert len(g.puntos_mm)==33
    with pytest.raises(ValueError):
        forma_en_marco(motivo,[0,0,0],np.ones((3,3)),[1,1,1],[1,0,0],'izq')


def test_dos_puntos_imagen_producen_senalamientos_distintos():
    m=MotorGestos(cargar()); _,_,q=ejemplos(m)[0]
    a=senalar_plano(m,[260,720],'der',q)
    b=senalar_plano(m,[350,750],'der',q)
    pa,pb=m.compilar(a,q),m.compilar(b,q)
    assert not np.allclose(pa.q['der'][-1],pb.q['der'][-1])
    assert pa.error_eje_grados<3 and pb.error_eje_grados<3
    region=barrer_region(m,[[300,650],[420,760]],'der',q)
    assert len(region.puntos_mm)==25
    m.compilar(region,q)
    with pytest.raises(ValueError): senalar_plano(m,[500,1001],'der',q)


def test_no_confunde_smplx_con_posiciones(tmp_path):
    f=tmp_path/'poses.npz'; np.savez(f,poses=np.zeros((5,165)))
    assert leer_parametros(f)[0].shape==(5,165)
    with pytest.raises(ValueError,match='convierte antes'):
        extraer(f,id='x',fuente='BEAT2',licencia='consultar',etiquetas=[],hombro='x',muneca='y',fps=30)
    np.savez(f,poses=np.zeros((5,263)))
    with pytest.raises(ValueError): leer_parametros(f)


def test_perfil_invalido_se_rechaza(motivo):
    m=MotorGestos(cargar()); _,g,q=ejemplos(m)[0]
    with pytest.raises(ValueError): m.compilar(replace(g,perfil_tiempo=(0,1,0)),q)


def test_catalogo_sin_inventar_emociones(motivo,tmp_path):
    from so101er.control.referencias import Biblioteca
    f=tmp_path/'m.json'; motivo.guardar(f)
    b=Biblioteca([f])
    assert b.elegir(['extension']).id==motivo.id
    with pytest.raises(LookupError): b.elegir(['tristeza'])


@pytest.mark.parametrize('filename', ['ARMS_ENCOMPASS-1','ARMS_RAISE_TOWORDS_SKY-1'])
def test_seg_real_y_compilacion(filename):
    # Test de integración local: utiliza los dos clips reales descargados, no un fixture atribuido a SeG.
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]/'datos'/'referencias'/'seg'
    if not (root/(filename+'.bvh')).exists(): pytest.skip('muestra privada SeG no instalada')
    t,n,j=leer_bvh(root/(filename+'.bvh'))
    assert len(t)>200 and j.shape[1]==64
    m=Motivo.cargar(root/(filename+'.json'))
    assert np.max(abs(np.asarray(m.perfil)-np.linspace(0,1,17)))>.01
    motor=MotorGestos(cargar()); _,g,enc=ejemplos(motor)[0]
    plan=motor.compilar(adaptar(m,g),enc)
    assert plan.error_posicion_mm<2 and plan.error_eje_grados<3
    frame=motor.marcos['izq']
    mapped=forma_en_marco(m,frame.a_mundo([motor.modelo.eje_pan[0]+235,0,220]),
                         frame.rot@np.array([[0,0,1],[1,0,0],[0,1,0]]),
                         [1,15,15],frame.dir_a_mundo([1,0,0]),'izq')
    plan=motor.compilar(mapped,enc)
    assert plan.error_posicion_mm<2 and plan.error_eje_grados<3
