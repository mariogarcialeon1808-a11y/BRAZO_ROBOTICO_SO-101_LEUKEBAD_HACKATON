import time
import pytest
from so101er.hardware.calibracion import BusSoloLectura,CapturaRangos,guardar_atomicamente


def sample(raw=None,**changes):
    return {'puerto':'COM7','serie':'serie-a','identidad':[],
            'raw':raw or [2000]*6,'par':[0]*6,'temperaturas':[25]*6,'t':time.monotonic(),**changes}


def test_bus_de_calibracion_rechaza_toda_escritura_sin_abrir_usb():
    bus=BusSoloLectura.__new__(BusSoloLectura)
    for instruction in (3,4,5,6,0x83):
        with pytest.raises(RuntimeError,match='lectura'):bus.orden(1,instruction,[40,1])


def test_extremos_solo_del_motor_seleccionado_y_sin_falsa_verificacion():
    c=CapturaRangos('COM7','serie-a',[])
    c.observar(1,sample());c.observar(1,sample([1000,3000,1000,1000,1000,1000]))
    c.observar(1,sample([3000,800,3000,3000,3000,3000]))
    assert list(c.rangos)==[1]
    assert c.rangos[1]['min_raw']==800 and c.rangos[1]['max_raw']==3000
    assert c.exportar()['referencia_modelo_verificada'] is False
    c.reiniciar(1);assert c.rangos=={}


@pytest.mark.parametrize('change',[{'puerto':'COM8'},{'serie':'otro'},{'identidad':[1]},
                                  {'par':[0,0,1,0,0,0]},{'t':time.monotonic()-10},
                                  {'raw':[5000]*6},{'temperaturas':[70]*6}])
def test_no_registra_otro_brazo_lecturas_viejas_o_motores_con_par(change):
    c=CapturaRangos('COM7','serie-a',[])
    with pytest.raises(ValueError):c.observar(0,sample(**change))
    assert c.rangos=={}


def test_guardar_conserva_anterior(tmp_path):
    path=tmp_path/'cal.json'
    guardar_atomicamente(path,{'valor':1});guardar_atomicamente(path,{'valor':2})
    assert '2' in path.read_text()
    previous=list(tmp_path.glob('cal.anterior_*.json'))
    assert len(previous)==1 and '1' in previous[0].read_text()
