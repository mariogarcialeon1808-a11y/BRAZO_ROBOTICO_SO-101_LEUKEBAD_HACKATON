import json
import numpy as np
import pytest
from so101er.hardware.alineacion import Alineacion,plan_real
from so101er.hardware.manual_usb import Coordenadas


def cal():
    return {'serie_usb':'usb7','identidad_servos':[],
            'rangos':{str(i):{'min_raw':500,'max_raw':3500} for i in range(1,7)}}


def test_cero_operativo_plegado_no_se_confunde_con_cero_urdf():
    raw=[2000,850,3070,2100,2000,2050];fold=[0,-95,90,15,0,0]
    a=Alineacion(cal(),raw,fold,[1,1,-1,1,-1,1])
    np.testing.assert_allclose(a.a_modelo(raw),fold)
    np.testing.assert_allclose(a.a_raw(fold),raw)
    next_raw=np.array(raw)+[0,100,100,0,100,0]
    q=a.a_modelo(next_raw)
    assert q[1]>fold[1] and q[2]<fold[2] and q[4]<fold[4]
    np.testing.assert_allclose(a.a_raw(q),next_raw)


def test_guardar_exige_seis_validaciones_y_no_comparte_usb(tmp_path):
    c=cal();a=Alineacion(c,[2000]*6,[0]*6)
    with pytest.raises(ValueError):a.guardar(tmp_path,'COM7',[True]*5+[False])
    assert not (tmp_path/'config/alineacion_COM7.json').exists()
    a.guardar(tmp_path,'COM7',[True]*6)
    restored=Alineacion.cargar(tmp_path,'COM7',c)
    np.testing.assert_array_equal(restored.a_raw([0]*6),[2000]*6)
    assert Alineacion.cargar(tmp_path,'COM8',c) is None
    other={**c,'serie_usb':'usb8'}
    with pytest.raises(ValueError):Alineacion.cargar(tmp_path,'COM7',other)


def test_cambio_de_rangos_invalida_alineacion(tmp_path):
    c=cal();a=Alineacion(c,[2000]*6,[0]*6);a.guardar(tmp_path,'COM7',[True]*6)
    c['rangos']['3']['max_raw']-=1
    with pytest.raises(ValueError):Alineacion.cargar(tmp_path,'COM7',c)


def test_inversion_conserva_postura_de_referencia():
    a=Alineacion(cal(),[2000]*6,[0,-95,90,15,0,50])
    original=a.a_modelo([2000]*6)
    a.invertir(1)
    np.testing.assert_array_equal(a.a_modelo([2000]*6),original)
    assert a.a_modelo([2000,2100,2000,2000,2000,2000])[1]<original[1]


def test_transformacion_no_depende_de_verdad_simulada():
    a=Alineacion(cal(),[2000]*6,[0]*6)
    sensors=[2010]*6;first=a.a_raw(a.a_modelo(sensors))
    a.xpos_privilegiado=[9999]*3
    np.testing.assert_array_equal(first,a.a_raw(a.a_modelo(sensors)))


def test_ruta_de_envio_ignora_estado_privilegiado_del_visor():
    from types import SimpleNamespace
    from so101er.pruebas_modelo import Panel
    from so101er.cinematica.modelo import Cinematica
    c=cal();c['identidad_servos']=[{'min_raw':500,'max_raw':3500} for _ in range(6)]
    raw=np.array([2000,850,3070,2100,2000,2000]);q=np.array([0,-95,95,0,0,50.])
    a=Alineacion(c,raw,q);out=[]
    native=SimpleNamespace(coords=Coordenadas(c,raw),set=lambda v:out.append(v.copy()))
    p=SimpleNamespace(alignment=a,native=native,modelo=SimpleNamespace(kin=Cinematica(),datos=SimpleNamespace(qpos=0,xpos=0)))
    Panel.enviar_modelo(p,q)
    p.modelo.datos.qpos=999;p.modelo.datos.xpos=-12345
    Panel.enviar_modelo(p,q)
    np.testing.assert_array_equal(out[0],out[1])


@pytest.mark.parametrize('nombre',['Abanico','Saludo'])
def test_plan_de_baile_convertido_completo_y_regreso(nombre):
    from so101er.pruebas_modelo import DANZAS,muestra
    from so101er.cinematica.modelo import Cinematica
    c=cal();c['identidad_servos']=[{'min_raw':500,'max_raw':3500} for _ in range(6)]
    raw=np.array([2000,850,3070,2100,2000,2000]);q=np.array([0,-95,95,0,0,50.])
    a=Alineacion(c,raw,q);coords=Coordenadas(c,raw)
    plans=plan_real(nombre,q,a,coords,Cinematica(),DANZAS)
    np.testing.assert_allclose(plans[-1][3],q)
    for start,duration,_,_ in plans:
        for t in np.linspace(start,start+duration,10):
            raw2=a.a_raw(muestra(plans,t));coords.a_raw(coords.a_ejes(raw2))
