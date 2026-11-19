import json,time
import numpy as np
import pytest
import so101er.hardware.manual_usb as module


def cal():
    return {'puerto':'COM7','serie_usb':'A','rangos':{str(i):{'min_raw':1000,'max_raw':3000} for i in range(1,7)},
            'identidad_servos':[{'id':i,'min_raw':1000,'max_raw':3000,'modelo_raw':777,'modo':0,'offset_raw':0} for i in range(1,7)]}


def test_conversion_nativa_rangos_y_rechazo_de_exceso():
    c=module.Coordenadas(cal(),np.full(6,2000.))
    for raw in (c.low,c.high,c.home):np.testing.assert_allclose(c.a_raw(c.a_ejes(raw)),raw)
    q=c.a_ejes(c.home);q[0]=500
    with pytest.raises(ValueError):c.a_raw(q)
    edge=module.Coordenadas(cal(),np.full(6,1000.))
    np.testing.assert_array_equal(edge.home,edge.low)
    with pytest.raises(ValueError):module.Coordenadas(cal(),np.full(6,995.))


def test_com8_codo_fuera_del_limite_no_se_admite_y_se_identifica():
    c=cal();c['rangos']['3']={'min_raw':860,'max_raw':3094}
    c['identidad_servos'][2].update(min_raw=867,max_raw=3078)
    with pytest.raises(ValueError,match=r'codo \(ID 3\).*3086.*879–3066'):
        module.Coordenadas(c,[2000,2000,3086,2000,2000,2000])
    coords=module.Coordenadas(c,[2000,2000,3050,2000,2000,2000])
    np.testing.assert_allclose(coords.a_raw(coords.a_ejes(coords.home)),coords.home)


def ejecutar_ciclo(monkeypatch,elapsed,privileged):
    import threading
    from types import SimpleNamespace
    c=module.ManualUSB.__new__(module.ManualUSB)
    c.port='COM7';c.lock=threading.RLock();c.measured=np.full(6,2000.)
    c.cmd=c.measured.copy();c.target=c.cmd+10;c.speed=91;c.error=None;c.entrando=False
    c.coords=module.Coordenadas(cal(),c.measured);c.simulator_truth=privileged
    c.stop=threading.Event();sent=[]
    c.bus=SimpleNamespace(orden=lambda *args:sent.append(args))
    times=iter([0.,.02,elapsed])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(times))
    monkeypatch.setattr(module,'estado',lambda _:dict(raw=np.full(6,2000),temperatura=np.full(6,25),
        voltaje=np.full(6,120),carga=np.zeros(6)))
    monkeypatch.setattr(c.stop,'wait',lambda _:c.stop.set())
    c._loop()
    return c,sent


def test_syncwrite_mismo_objetivo_sin_dependencia_de_visor(monkeypatch):
    a,sent=ejecutar_ciclo(monkeypatch,.025,0)
    b,other=ejecutar_ciclo(monkeypatch,.025,999)
    assert sent==other and len(sent)==1 and a.error is None and b.error is None
    id,instruction,p=sent[0]
    assert (id,instruction,p[:2])==(254,0x83,[41,7])
    assert len(p)==50
    for j in range(6):
        record=p[2+j*8:10+j*8]
        assert record[0]==j+1 and record[1]==5 and record[4:]==[0,0,91,0]
        assert 2000<=record[2]+256*record[3]<=2010


def test_perdida_prolongada_sigue_bloqueando_movimiento(monkeypatch):
    c,sent=ejecutar_ciclo(monkeypatch,1.25,0)
    assert sent==[] and '1230 ms' in c.error and 'máximo 1000 ms' in c.error


def test_pico_aislado_avisa_sin_salto_de_recuperacion(monkeypatch):
    c,sent=ejecutar_ciclo(monkeypatch,.25,0)
    assert c.error is None and len(sent)==1 and '230 ms' in c.aviso
    assert np.max(c.cmd[:5]-2000)<=20*module.CUENTAS_GRADO*.04
    assert c.cmd[5]-2000<=60*module.CUENTAS_GRADO*.04


def test_entrada_inicial_acotada_no_busca_topes_ni_cambia_rangos():
    import copy
    c=cal();before=copy.deepcopy(c);raw=np.array([999,1005,3001,2000,2000,1007.])
    target=module.objetivo_entrada(c,raw)
    assert c==before
    np.testing.assert_array_equal(target,[1024,1024,2976,2000,2000,1024])
    assert max(abs(target-raw))<3*module.CUENTAS_GRADO
    with pytest.raises(ValueError,match='fuera del rango'):
        module.objetivo_entrada(c,[970,2000,2000,2000,2000,2000])


def test_objetivo_identico_no_reinicia_perfil_servo():
    from types import SimpleNamespace
    c=module.ManualUSB.__new__(module.ManualUSB);c.speed=11;calls=[]
    c.bus=SimpleNamespace(orden=lambda *a:calls.append(a))
    for _ in range(50):c._write_all(np.full(6,2000.))
    assert len(calls)==1
    c._write_all(np.full(6,2001.));assert len(calls)==2
    c.speed=91;c._write_all(np.full(6,2001.));assert len(calls)==3


def test_telemetria_alta_se_confirma_sin_ignorar_calor_persistente(monkeypatch):
    def sample(temp):return dict(temperatura=np.full(6,temp),voltaje=np.full(6,120),carga=np.zeros(6))
    # Una lectura suelta de temperatura ya no provoca relecturas ni avisos: se usa tal cual llega.
    reads=iter([sample(120)])
    monkeypatch.setattr(module,'estado',lambda _:next(reads))
    data,notice=module.estado_confirmado(None)
    assert max(data['temperatura'])==120 and notice is None and module.anomalia(sample(120)) is None
    # Antes de activar se decide con la mediana de cinco lecturas: dos falsas no bloquean, el calor real sí.
    reads=iter([sample(26),sample(135),sample(27),sample(91),sample(26)])
    assert max(module.temperatura_fiable(None))==27
    reads=iter([sample(52)]*5)
    assert max(module.temperatura_fiable(None))>=module.TEMPERATURA_ARRANQUE


def test_cuantizacion_pequena_siempre_manda_objetivo_dentro_del_margen():
    coords=module.Coordenadas(cal(),[1011,2000,2000,2000,2000,2000])
    assert coords.home[0]==coords.low[0]==1012
    raw=coords.a_raw(coords.a_ejes([1010,2000,2000,2000,2000,2000]))
    assert raw[0]==1012
    with pytest.raises(ValueError):coords.a_raw(coords.a_ejes([995,2000,2000,2000,2000,2000]))


@pytest.mark.parametrize('port,entrada',[('COM7',False),('COM8',True)])
def test_control_solo_usb_elegido_objetivo_antes_de_par_y_suelta(tmp_path,monkeypatch,port,entrada):
    data=cal();data['puerto']=port
    if entrada:data['rangos']['3']['max_raw']=3020
    initial=[2000]*6
    if entrada:initial[2]=3008
    expected=initial.copy()
    if entrada:expected[2]=2976
    (tmp_path/'config').mkdir();(tmp_path/'config/calibracion_rangos_usb.json').write_text(json.dumps({'brazos':[data]}))
    writes=[]
    class Fake:
        def __init__(self,selected):assert selected==port;self.q=initial.copy();self.par=[0]*6
        def leer(self,i,reg,n):
            if reg==40:return bytes([self.par[i-1]])
            if reg==41:return bytes([5,208,7,0,0,91,0])
            if reg==56:
                raw=self.q[i-1];return bytes([raw&255,raw>>8,0,0,0,0,120,25])
            raise AssertionError(reg)
        def escribir(self,i,reg,values):
            writes.append((i,reg,list(values)))
            if reg==40:self.par[i-1]=values[0]
            elif reg==41 and len(values)==7:self.q[i-1]=values[1]+256*values[2]
            else:assert reg in (41,44)
        def orden(self,id,instruction,params):
            assert id==254 and instruction==0x83 and params[:2]==[41,7]
            for j in range(2,len(params),8):
                i=params[j];self.escribir(i,41,params[j+1:j+8])
        def cerrar(self):pass
    monkeypatch.setattr(module,'Bus',Fake);monkeypatch.setattr(module,'identidad',lambda bus:data['identidad_servos'])
    monkeypatch.setattr(module,'puertos',lambda:[{'puerto':port,'serie':'A'}])
    c=module.ManualUSB(tmp_path,port,entrada_suave=entrada)
    try:
        assert [r for _,r,_ in writes[:12]]==[41]*6+[40]*6
        assert [values[1]+256*values[2] for _,reg,values in writes[:6]]==expected
        if entrada:assert all(values[-2]==11 for _,_,values in writes[:6])
        time.sleep(.04)
        q=c.ejes();q[0]=2;c.set(q);time.sleep(.08);c.parar()
        assert c.error is None
    finally:c.soltar()
    assert c.bus.par==[0]*6
    assert all(1<=i<=6 and reg in (40,41,44) for i,reg,_ in writes)
