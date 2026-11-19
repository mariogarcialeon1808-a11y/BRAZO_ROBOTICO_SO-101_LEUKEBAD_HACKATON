import time
from types import SimpleNamespace
import numpy as np
import pytest
import so101er.hardware.dual_usb as dual


def test_montaje_real_exige_medida_confirmada_y_asigna_lados(tmp_path):
    from so101er.config import cargar
    with pytest.raises(ValueError,match='falta medir'):dual.cargar_montaje(tmp_path)
    with pytest.raises(ValueError,match='confirma'):dual.guardar_montaje(tmp_path,70,True,False)
    for value in (float('nan'),float('inf'),0,201):
        with pytest.raises(ValueError):dual.guardar_montaje(tmp_path,value,True,True)
    d=dual.guardar_montaje(tmp_path,70,False,True)
    assert dual.cargar_montaje(tmp_path)==d
    cfg=cargar();dual.aplicar_montaje(cfg,d)
    assert cfg.brazos['izq'].puerto=='COM8' and cfg.brazos['der'].puerto=='COM7'
    np.testing.assert_array_equal(cfg.brazos['izq'].base_mm,[-350,0,0])
    assert cfg.limites.distancia_min_brazos_mm>=160 and not cfg.simulado


def test_preflight_dual_bloquea_ambos_antes_de_activar(tmp_path,monkeypatch):
    dual.guardar_montaje(tmp_path,70,True,True)
    monkeypatch.setattr(dual,'incidencias_dual',lambda _:['COM8: codo fuera de margen'])
    monkeypatch.setattr(dual,'BrazoChat',lambda *a:pytest.fail('no activar ni el primero'))
    group=dual.GrupoReal(tmp_path)
    with pytest.raises(ValueError,match='COM8: codo'):group.activar()
    assert group.native.closed and not group.brazos


def test_grupo_para_todos_y_suelta_los_demas_si_uno_falla():
    calls=[]
    def fail():calls.append('COM7 soltar');raise RuntimeError('fallo de confirmación')
    a=SimpleNamespace(port='COM7',native=SimpleNamespace(closed=False,entrando=False,error='calor',parar=lambda:calls.append('COM7 parar')),soltar=fail)
    b=SimpleNamespace(port='COM8',native=SimpleNamespace(closed=False,entrando=False,error=None,parar=lambda:calls.append('COM8 parar')),soltar=lambda:calls.append('COM8 soltar'))
    group=dual.GrupoReal.__new__(dual.GrupoReal);group.brazos={'izq':a,'der':b};group.native=dual.EstadoGrupo(group)
    assert group.native.error=='COM7: calor' and not group.native.closed
    group.native.parar()
    with pytest.raises(RuntimeError,match='COM7'):group.soltar()
    assert calls==['COM7 parar','COM8 parar','COM7 soltar','COM8 soltar']


def test_limites_de_cada_usb_validan_su_propio_brazo(monkeypatch):
    from so101er.hardware.chat_usb import BrazoChat
    seen=[];p=SimpleNamespace(q={'izq':np.zeros((2,6)),'der':np.ones((3,6))*7})
    b=SimpleNamespace(validar_q=lambda q:seen.append(q.copy()))
    BrazoChat.validar_plan(b,p,'der')
    assert len(seen)==3 and all(np.all(q==7) for q in seen)


def test_error_sensorial_detiene_ambos_y_no_reenvia_objetivos():
    from so101er.config import cargar
    from so101er.control.semantico import MotorGestos
    from so101er.control.escenico import pose_reposo
    from so101er.control.reproduccion import ControlLocal
    motor=MotorGestos(cargar());q=pose_reposo(motor);calls=[]
    class Arm:
        telemetria_temperatura=False
        def __init__(self,name):self.port=name;self.reads=0
        def leer_articulaciones(self):
            self.reads+=1
            if self.port=='COM7' and self.reads>1:raise RuntimeError('COM7 sin lecturas')
            return q.copy()
        def enviar_objetivo(self,q):calls.append(self.port+' mover')
        def detener(self):calls.append(self.port+' parar')
    c=ControlLocal(motor,{'izq':Arm('COM7'),'der':Arm('COM8')})
    try:
        for _ in range(100):
            if c.error:break
            time.sleep(.005)
        assert c.error=='COM7 sin lecturas'
        before=list(calls);time.sleep(.05)
        assert calls==before==['COM7 parar','COM8 parar']
    finally:c.cerrar()


def test_reposos_reales_distintos_no_se_mezclan():
    from so101er.control.escenico import pose_reposo
    motor=SimpleNamespace(reposos_reales={'izq':np.zeros(6),'der':np.ones(6)*5})
    np.testing.assert_array_equal(pose_reposo(motor,'der'),np.full(6,5))
    with pytest.raises(ValueError,match='indica el brazo'):pose_reposo(motor)


def test_recursos_se_cargan_antes_de_activar_motores(monkeypatch):
    from so101er.chatbot_real import Preparador
    import so101er.aplicacion as app
    import so101er.hardware.chat_usb as hw
    calls=[]
    def warm(*a):calls.append('cargar');return SimpleNamespace(usado=False)
    def enable(*a):calls.append('activar');return SimpleNamespace(native=SimpleNamespace(closed=False))
    monkeypatch.setattr(app,'preparar_recursos',warm);monkeypatch.setattr(hw,'BrazoChat',enable)
    p=SimpleNamespace(root='.',recursos=None,owner=None,armado=SimpleNamespace(set=lambda _:None),
        mostrar=lambda _:None,ui=SimpleNamespace(update_idletasks=lambda:None,after=lambda *a:None),esperar_entrada=lambda:None)
    Preparador.iniciar(p,'COM7')
    assert calls==['cargar','activar'] and p.owner is not None


def test_fallo_arranque_permanece_visible_hasta_reintentar(monkeypatch):
    from so101er.chatbot_real import Preparador
    import so101er.aplicacion as app
    messages=[]
    def fail(*a):raise RuntimeError('fallo específico de precarga')
    monkeypatch.setattr(app,'preparar_recursos',fail)
    p=SimpleNamespace(root='.',recursos=None,owner=None,armado=SimpleNamespace(set=lambda _:None),
        mostrar=messages.append,ui=SimpleNamespace(update_idletasks=lambda:None))
    Preparador.iniciar(p,'COM7')
    assert p.fallo_arranque and not p.lanzando and 'fallo específico' in messages[-1]


def test_tolerancia_solo_de_redondeo_no_amplia_rango_real():
    from so101er.control.escenico import validar
    lim=SimpleNamespace(velocidad=np.ones(6),aceleracion=np.ones(6),tiron=np.ones(6))
    m=SimpleNamespace(modelo=SimpleNamespace(lim_inf=np.zeros(5),lim_sup=np.ones(5)),cfg=SimpleNamespace(limites=lim),
        seguridad=SimpleNamespace(cadena_mundo=lambda *a:None,problema_pose=lambda *a:None,problema_par=lambda *a:None))
    q=np.zeros((5,6));q[:,0]=-1e-13;validar(m,np.arange(5.),{'izq':q})
    q[:,0]=-1e-4
    with pytest.raises(ValueError,match='límites articulares'):validar(m,np.arange(5.),{'izq':q})


def test_plan_normaliza_inicio_sin_falsear_lectura_sensorial():
    from so101er.aplicacion import SesionIntegrada
    raw=np.array([1.,2.,3.,4.,5.,6.]);bounded=raw-.1
    p=SimpleNamespace(real=True,control=SimpleNamespace(medir=lambda:{'izq':raw.copy()}),
        brazos={'izq':SimpleNamespace(validar_q=lambda _:bounded.copy())})
    np.testing.assert_array_equal(SesionIntegrada.inicio_plan(p)['izq'],bounded)
    np.testing.assert_array_equal(p.control.medir()['izq'],raw)
