import json
from types import SimpleNamespace
import numpy as np
import pytest
import so101er.hardware.chat_usb as hw
from so101er.hardware.alineacion import Alineacion
from so101er.hardware.manual_usb import Coordenadas


def cal():
    return {'puerto':'COM7','serie_usb':'A','rangos':{str(i):{'min_raw':1000,'max_raw':3000} for i in range(1,7)},
            'identidad_servos':[{'id':i,'min_raw':1000,'max_raw':3000,'modelo_raw':777,'modo':0,'offset_raw':0} for i in range(1,7)]}


def escribir(tmp_path):
    (tmp_path/'config').mkdir();(tmp_path/'config/calibracion_rangos_usb.json').write_text(json.dumps({'brazos':[cal()]}))


def test_sin_alineacion_no_abre_control_ni_activa_motores(tmp_path,monkeypatch):
    escribir(tmp_path)
    monkeypatch.setattr(hw,'ManualUSB',lambda *a,**k:pytest.fail('no debe activar'))
    with pytest.raises(ValueError,match='falta alineación'):hw.BrazoChat(tmp_path,'COM7')


def test_aviso_exacto_motor_caliente_y_alineacion_faltante_solo_lectura(tmp_path,monkeypatch):
    escribir(tmp_path)
    class ReadOnly:
        def __init__(self,port):assert port=='COM7'
        def leer(self,*a):return b'\x00'
        def escribir(self,*a):pytest.fail('solo lectura')
        def cerrar(self):pass
    monkeypatch.setattr(hw,'puertos',lambda:[{'puerto':'COM7','serie':'A'}])
    monkeypatch.setattr(hw,'BusSoloLectura',ReadOnly)
    monkeypatch.setattr(hw,'identidad',lambda b:cal()['identidad_servos'])
    monkeypatch.setattr(hw,'estado',lambda b:{'raw':np.full(6,2000),'temperatura':np.array([25,56,25,25,25,25]),'voltaje':np.full(6,120)})
    issues=hw.incidencias(tmp_path,'COM7')
    assert any('COM7, hombro (ID 2)' in s and '56' in s and 'espera' in s for s in issues)
    assert any('falta guardar la alineación' in s for s in issues)


def puente():
    c=cal();raw=np.full(6,2000.);q=np.r_[np.zeros(5),50.]
    bridge=hw.BrazoChat.__new__(hw.BrazoChat);bridge.port='COM7'
    bridge.alineacion=Alineacion(c,raw,q)
    sent=[];coords=Coordenadas(c,raw)
    bridge.native=SimpleNamespace(coords=coords,error=None,entrando=False,raw_actual=lambda:raw.copy(),set=lambda v:sent.append(v.copy()))
    bounds=np.array([bridge.alineacion.a_modelo(coords.low),bridge.alineacion.a_modelo(coords.high)])
    bridge.low=np.min(bounds,axis=0);bridge.high=np.max(bounds,axis=0)
    return bridge,sent


def test_puente_usa_encoders_y_calibracion_no_estado_del_visor():
    b,sent=puente();q=b.leer_articulaciones();q[0]=3
    b.enviar_objetivo(q)
    b.mujoco_qpos=np.full(6,999);b.mujoco_xpos=np.full(3,-999)
    b.enviar_objetivo(q)
    np.testing.assert_array_equal(sent[0],sent[1])
    q[0]=500
    with pytest.raises(ValueError,match=r'COM7, base \(ID 1\)'):b.enviar_objetivo(q)
    assert len(sent)==2


def test_sesion_real_un_solo_brazo_y_limites_iniciales():
    from conftest import RAIZ
    from so101er.aplicacion import SesionIntegrada
    b,_=puente();b.desconectar=lambda:None
    s=SesionIntegrada(RAIZ,real=True,ventana=False,brazo_real=b,notificar=lambda _:None)
    try:
        assert list(s.brazos)==['izq'] and s.cfg.modo=='uno'
        # El perfil real es el de `[real] velocidad_grados_s`, nunca el de la simulación sin pedirlo.
        from so101er.hardware.manual_usb import velocidad_real
        v=velocidad_real(RAIZ)
        assert 20<=v<=150 and s.velocidad==v
        assert np.all(s.cfg.limites.velocidad[:5]==v) and s.cfg.limites.velocidad[5]==max(60,v)
        # La postura medida al activar es la plegada, a la que se vuelve antes de soltar;
        # el reposo entre gestos es la postura de trabajo de la simulación, validada para este brazo.
        from so101er.control.escenico import pose_trabajo
        np.testing.assert_array_equal(s.plegado['izq'],b.leer_articulaciones())
        np.testing.assert_allclose(s.motor.reposo_real,b.validar_q(pose_trabajo(s.motor)))
        s.control.registro=None                       # la prueba no deja archivos de seguimiento
        assert s.desplegado is False and s.desplegar()>0
    finally:s.cerrar()


def test_arranque_real_heredado_no_activa_sin_preparador():
    from conftest import RAIZ
    from so101er.aplicacion import SesionIntegrada
    with pytest.raises(ValueError,match='CHATBOT_REAL'):SesionIntegrada(RAIZ,real=True)


def test_cancelar_entrada_no_abre_chat_despues():
    from so101er.chatbot_real import Preparador
    messages=[];calls=[]
    p=SimpleNamespace(owner=object(),cancelado=True,mostrar=messages.append,ui=SimpleNamespace(after=lambda *a:calls.append(a)))
    Preparador.esperar_entrada(p)
    assert messages and not calls


def test_otro_brazo_con_par_bloquea_arranque(tmp_path,monkeypatch):
    escribir(tmp_path)
    class ReadOnly:
        def __init__(self,p):self.p=p
        def leer(self,i,*a):return bytes([int(self.p=='COM8' and i==1)])
        def cerrar(self):pass
    monkeypatch.setattr(hw,'puertos',lambda:[{'puerto':p,'serie':'A'} for p in ('COM7','COM8')])
    monkeypatch.setattr(hw,'BusSoloLectura',ReadOnly)
    monkeypatch.setattr(hw,'identidad',lambda b:cal()['identidad_servos'])
    monkeypatch.setattr(hw,'estado',lambda b:{'raw':np.full(6,2000),'temperatura':np.full(6,25),'voltaje':np.full(6,120)})
    assert any('COM8' in s and 'otro brazo tiene par activo' in s for s in hw.incidencias(tmp_path,'COM7'))


@pytest.mark.parametrize('guardada',[False,True])
def test_boton_reutiliza_alineacion_y_nunca_inventa_primera_calibracion(tmp_path,monkeypatch,guardada):
    from so101er.chatbot_real import Preparador
    escribir(tmp_path);messages=[];assistant=[];armed=[]
    monkeypatch.setattr(Alineacion,'cargar',lambda *a:object() if guardada else None)
    p=SimpleNamespace(owner=None,root=tmp_path,port=SimpleNamespace(get=lambda:'COM7'),
                      armado=SimpleNamespace(set=armed.append),mostrar=messages.append,alinear=lambda:assistant.append(True))
    Preparador.preparar_un_boton(p)
    assert armed[-1] is guardada
    assert bool(assistant) is not guardada
    assert not (tmp_path/'config/alineacion_COM7.json').exists()
