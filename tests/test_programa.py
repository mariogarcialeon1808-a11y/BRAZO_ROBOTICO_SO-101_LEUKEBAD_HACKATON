from types import SimpleNamespace
import json
import pytest

from so101er.interfaz.referencia import posicion_marca
from so101er.programa import Programa


def test_marca_distingue_referencia_fuera_del_rango():
    assert posicion_marca(0,-100,100,216)==(108,False)
    assert posicion_marca(-110,-100,100,216)==(8,True)
    assert posicion_marca(110,-100,100,216)==(208,True)
    assert posicion_marca(0,1,1,216) is None


def test_ventana_unica_cede_usb_y_bloquea_salida_con_par(monkeypatch):
    import so101er.hardware.calibracion as cal
    import so101er.hardware.chat_usb as hw
    from conftest import RAIZ
    readers=[]
    class Reader:
        def __init__(self):
            assert not any(not r.closed for r in readers)
            self.closed=False;readers.append(self)
        def leer(self):return {},{}
        def cerrar(self):self.closed=True
    monkeypatch.setattr(cal,'Monitor',Reader)
    monkeypatch.setattr(hw,'incidencias',lambda *a:['Prueba sin USB'])
    monkeypatch.setattr(hw,'ManualUSB',lambda *a,**k:pytest.fail('ningún tab debe activar motores'))
    # La pestaña inicial depende de lo que haya guardado en el equipo; esta prueba parte siempre de la 1.
    monkeypatch.setattr(Programa,'pestana_inicial',lambda self:0)
    p=Programa(RAIZ);p.ui.withdraw()
    try:
        p.ui.update()
        assert len(readers)==1 and p.current==0
        p.book.select(1);p.ui.update()
        assert readers[0].closed and p.panel.visible
        assert not p.prep.habilitado
        p.panel.device.set('COM7');p.panel.edit.set(True)
        p.panel.editar_alineacion()
        assert len(readers)==2 and not readers[1].closed
        p.book.select(0);p.ui.update()
        assert readers[1].closed and len(readers)==3
        p.book.select(1);p.ui.update()
        p.panel.native=SimpleNamespace(closed=False)
        p.book.select(0);p.ui.update()
        assert p.book.index(p.book.select())==1
        assert p.current==1 and 'par' in p.notice.get()
        p.panel.native=None
        p.book.select(2);p.ui.update()
        assert p.prep.habilitado and not p.panel.visible
        assert all(r.closed for r in readers)
    finally:
        p.panel.native=None;p.cerrar()


def test_guardar_incompleto_no_sustituye_rangos_previos(tmp_path):
    from so101er.calibracion_usb import Asistente
    config=tmp_path/'config';config.mkdir()
    previous=config/'calibracion_rangos_usb.json';previous.write_text('{"previo": true}')
    notices=[]
    p=SimpleNamespace(root=tmp_path,capturas={'COM7':SimpleNamespace(rangos={0:{'min_raw':100,'max_raw':500}})},
                      documento=lambda:{'borrador':True},status=SimpleNamespace(set=notices.append))
    Asistente.guardar(p)
    assert json.loads(previous.read_text())=={'previo':True}
    assert (config/'calibracion_rangos_usb.borrador.json').exists()
    assert 'progreso parcial' in notices[0]


def test_parar_cancela_sesion_y_mantiene_par():
    calls=[]
    native=SimpleNamespace(closed=False,parar=lambda:calls.append('native'),soltar=lambda:pytest.fail('no soltar'))
    p=SimpleNamespace(prep=SimpleNamespace(armado=SimpleNamespace(set=lambda _:None),owner=SimpleNamespace(native=native)),
        panel=SimpleNamespace(dance=None),session=SimpleNamespace(closed=False,interrumpir=lambda:calls.append('sesion')),
        nativo_panel_activo=lambda:False,notice=SimpleNamespace(set=lambda _:None))
    Programa.parar(p)
    assert calls==['sesion'] and p.prep.cancelado
