import json
from types import SimpleNamespace
import numpy as np
import pytest
from so101er.pruebas_modelo import secuencia,muestra,DANZAS
from so101er.pruebas_modelo import pose_para_vista,Panel
import so101er.hardware.prueba_base as pb


def test_grados_relativos_usb_no_se_dibujan_como_pose_urdf():
    for p in ('COM7','COM8'):
        assert pose_para_vista(p,np.zeros(6)) is None
        assert pose_para_vista(p,np.full(6,20)) is None
    np.testing.assert_array_equal(pose_para_vista('Simulación',np.zeros(6)),np.zeros(6))


def test_baile_usb_no_emite_acciones_sin_alineacion():
    class Status:
        def set(self,text):self.text=text
    class Native:
        def set(self,q):raise AssertionError('no debe emitir consignas')
    p=SimpleNamespace(worker=None,device=SimpleNamespace(get=lambda:'COM7'),native=Native(),alignment=None,status=Status(),dance=None)
    Panel.bailar(p,'Saludo')
    assert p.dance is None and 'bloqueado' in p.status.text


@pytest.mark.parametrize('name',list(DANZAS))
def test_danza_suave_vuelve_al_inicio_y_respeta_velocidad(name):
    start=np.array([4,-2,3,0,4,20.]);plans=secuencia(name,start)
    end=plans[-1][0]+plans[-1][1]
    np.testing.assert_allclose(muestra(plans,0),start)
    np.testing.assert_allclose(muestra(plans,end+1),start)
    qs=np.array([muestra(plans,t) for t in np.arange(0,end,.01)])
    velocity=np.diff(qs,axis=0)/.01
    assert abs(velocity[:,:5]).max()<=18.01 and abs(velocity[:,5]).max()<=60.01
    assert np.all((qs[:,5]>=0)&(qs[:,5]<=100))


def test_guardia_no_permite_otro_servo_eeprom_broadcast_o_exceso(monkeypatch):
    forwarded=[]
    monkeypatch.setattr(pb.Bus,'orden',lambda self,i,ins,p:forwarded.append((i,ins,p)) or b'\x00')
    bus=pb.BusBase.__new__(pb.BusBase);bus.limites=(1000,3000)
    valid=[41,5,208,7,0,0,91,0]
    bus.orden(1,3,valid)
    count=len(forwarded)
    for id,ins,p in [(2,3,valid),(254,0x83,valid),(1,3,[31,0,0]),
                     (1,3,[41,5,0,0,0,0,91,0]),(1,3,[41,5,208,7,0,0,255,0])]:
        with pytest.raises(ValueError):bus.orden(id,ins,p)
    assert len(forwarded)==count


def test_no_amplia_si_no_cabe_en_rangos():
    with pytest.raises(ValueError):pb.parametros_barrido(510,{'min_raw':500,'max_raw':3500},
                                                       {'min_raw':500,'max_raw':3500})


def fake_run(tmp_path,monkeypatch,privileged=0,opposite_moves=False):
    meta=[{'id':i,'modelo_raw':777,'min_raw':500,'max_raw':3500,'offset_raw':0,'modo':0} for i in range(1,7)]
    arms=[{'puerto':p,'serie_usb':p,'identidad_servos':meta,
           'rangos':{str(i):{'min_raw':500,'max_raw':3500} for i in range(1,7)}} for p in ('COM7','COM8')]
    (tmp_path/'config').mkdir(exist_ok=True)
    (tmp_path/'config/calibracion_rangos_usb.json').write_text(json.dumps({'brazos':arms}))
    clock=SimpleNamespace(t=0.)
    class Cancel:
        def is_set(self):return False
        def wait(self,t):clock.t+=t;return False
    instances=[];writes=[]
    class Fake:
        def __init__(self,port):
            self.port=port;self.q=2000;self.par=0;self.privileged=privileged;instances.append(self)
        def leer(self,i,reg,n):
            if reg==40:return bytes([self.par if i==1 else 0])
            if reg==41:return bytes([1,208,7,0,0,0,0])
            if reg==56:
                q=self.q if i==1 else 2000
                if opposite_moves and self.port=='COM8' and clock.t>3:q+=100
                return bytes([q&255,q>>8,0,0,0,0,120,25])
            raise AssertionError((reg,n))
        def escribir(self,i,reg,data):
            assert self.port=='COM7' and i==1
            writes.append((self.port,i,reg,list(data)))
            if reg==40:self.par=data[0]
            if reg==41 and len(data)==7:self.q=data[1]+256*data[2]
        def cerrar(self):pass
    monkeypatch.setattr(pb,'BusBase',Fake);monkeypatch.setattr(pb,'BusSoloLectura',Fake)
    monkeypatch.setattr(pb,'puertos',lambda:[{'puerto':p,'serie':p} for p in ('COM7','COM8')])
    monkeypatch.setattr(pb,'identidad',lambda b:meta)
    monkeypatch.setattr(pb,'time',SimpleNamespace(monotonic=lambda:clock.t))
    if opposite_moves:
        with pytest.raises(RuntimeError,match='apartado'):pb.ejecutar(tmp_path,Cancel(),lambda _:None)
        assert instances[0].par==0
        return writes
    report=pb.ejecutar(tmp_path,Cancel(),lambda _:None)
    assert report['paso_corto_superado'] and report['barrido_superado']
    assert report['par_final_base']==0 and report['error_retorno_grados']==0
    assert 69<report['recorrido_medido_grados']<71
    return writes


def test_prueba_corta_y_amplia_solo_una_base_y_suelta_par(tmp_path,monkeypatch):
    writes=fake_run(tmp_path,monkeypatch)
    assert all(port=='COM7' and id==1 for port,id,_,_ in writes)


def test_si_otro_brazo_se_mueve_detiene_y_suelta_par(tmp_path,monkeypatch):
    fake_run(tmp_path,monkeypatch,opposite_moves=True)


def test_control_invariante_a_verdad_no_observable(tmp_path,monkeypatch):
    a=fake_run(tmp_path,monkeypatch,privileged=0)
    b=fake_run(tmp_path,monkeypatch,privileged=12345)
    assert a==b
