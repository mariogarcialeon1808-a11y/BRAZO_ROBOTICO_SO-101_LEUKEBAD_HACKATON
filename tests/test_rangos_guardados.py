"""Los rangos guardados se cargan al abrir: no hay que recorrerlos cada vez. Sin hardware."""
import json
import time
from types import SimpleNamespace

import pytest

from so101er.calibracion_usb import Asistente, cargar_guardados
from so101er.hardware.alineacion import huella
from so101er.programa import Programa

META = {'COM7': [{'id': i, 'modelo_raw': 777, 'min_raw': 0, 'max_raw': 4095, 'offset_raw': 0, 'modo': 0} for i in range(1, 7)],
        'COM8': [{'id': i, 'modelo_raw': 777, 'min_raw': 0, 'max_raw': 4095, 'offset_raw': 5, 'modo': 0} for i in range(1, 7)]}
SERIE = {'COM7': 'A', 'COM8': 'B'}


def _guardar(root, puertos=('COM7', 'COM8')):
    (root / 'config').mkdir(exist_ok=True)
    brazos = [{'puerto': p, 'serie_usb': SERIE[p], 'identidad_servos': META[p], 'referencia_modelo_verificada': False,
               'rangos': {str(i): {'min_raw': 800 + 10 * i, 'max_raw': 3000 + 10 * i, 'muestras': 50} for i in range(1, 7)}} for p in puertos]
    doc = {'version': 1, 'fecha_utc': '2026-11-15T21:06:00+00:00', 'verificada': False, 'brazos': brazos}
    (root / 'config/calibracion_rangos_usb.json').write_text(json.dumps(doc), encoding='utf8')
    return doc


class Lector:
    """Como el monitor de encoders, con las lecturas que se le pongan."""
    def __init__(self, puertos=('COM7', 'COM8')):
        self.raw = {p: [2000] * 6 for p in puertos}; self.meta = dict(META)
    def leer(self):
        return {p: {'puerto': p, 'serie': SERIE[p], 'identidad': self.meta[p], 'raw': list(r), 'temperaturas': [25] * 6,
                    'par': [0] * 6, 't': time.monotonic()} for p, r in self.raw.items()}, {}
    def cerrar(self): pass


@pytest.fixture(scope='module')
def ventana():
    """Una sola ventana raíz de Tk para todo este archivo: crear muchas seguidas falla a veces en Windows."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip('sin pantalla')
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def asistente(ventana, tmp_path):
    def crear(lector):
        a = Asistente(tmp_path, abrir_modelo=False, parent=ventana, autoconectar=False)
        a.monitor = lector
        a.poll()
        creados.append(a)
        return a
    creados = []
    yield crear
    for a in creados:
        a.closed = True


def test_cargar_guardados_tolera_que_no_haya_o_este_roto(tmp_path):
    assert cargar_guardados(tmp_path) == ({}, None)
    (tmp_path / 'config').mkdir(); (tmp_path / 'config/calibracion_rangos_usb.json').write_text('{ roto')
    assert cargar_guardados(tmp_path) == ({}, None)
    _guardar(tmp_path)
    brazos, fecha = cargar_guardados(tmp_path)
    assert set(brazos) == {'COM7', 'COM8'} and '15-11-2026' in fecha


def test_al_abrir_estan_los_doce_rangos_guardados_y_no_se_tocan(asistente, tmp_path):
    doc = _guardar(tmp_path)
    lector = Lector()
    a = asistente(lector)
    assert a.progreso.get().startswith('12 de 12 motores con rango guardado el 15-11-2026')
    assert 'No hace falta recorrerlos' in a.progreso.get() and 'Rangos guardados cargados' in a.status.get()
    assert a.table.item('COM7_0')['values'][2:] == [810, 3010, '193.4', 'guardado']
    assert a.table.item('COM8_5')['values'][2:] == [860, 3060, '193.4', 'guardado']
    # Mover a mano un motor con rango guardado, incluso más allá de sus extremos, no cambia nada.
    lector.raw['COM7'][0] = 100; a.poll(); lector.raw['COM7'][0] = 4000; a.poll()
    assert a.capturas['COM7'].rangos[0]['min_raw'] == 810 and a.capturas['COM7'].rangos[0]['max_raw'] == 3010
    assert not a.hay_cambios()
    antes = sorted(p.name for p in (tmp_path / 'config').iterdir())
    a.guardar()                                                            # sin cambios no se escribe nada
    assert 'No hay nada nuevo que guardar' in a.status.get()
    assert sorted(p.name for p in (tmp_path / 'config').iterdir()) == antes
    # Lo que se exportaría es idéntico a lo guardado: la alineación hecha sobre estos rangos sigue valiendo.
    for brazo in doc['brazos']:
        exportado = a.capturas[brazo['puerto']].exportar()
        assert huella(exportado) == huella(brazo)


def test_se_puede_repetir_un_solo_motor_sin_recorrer_los_otros_once(asistente, tmp_path):
    _guardar(tmp_path)
    lector = Lector()
    a = asistente(lector)
    a.port.set('COM8'); a.motor.set('5 · Giro muñeca')
    a.reiniciar()
    assert ('COM8', 4) not in a.congelados and a.hay_cambios() and 4 not in a.capturas['COM8'].rangos
    for valor in (2000, 150, 4000, 2000):                                   # ahora sí se registra ese motor
        lector.raw['COM8'][4] = valor; a.poll()
    assert a.table.item('COM8_4')['values'][2:] == [150, 4000, '338.4', 'recorrido ahora, sin guardar']
    assert a.progreso.get().startswith('12 de 12 motores con rango (11 guardados de antes)')
    hecho = []
    a.guardado_callback = lambda: hecho.append(1)
    a.guardar()
    nuevo = json.loads((tmp_path / 'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
    com8 = next(b for b in nuevo['brazos'] if b['puerto'] == 'COM8')
    assert (com8['rangos']['5']['min_raw'], com8['rangos']['5']['max_raw']) == (150, 4000)
    assert (com8['rangos']['4']['min_raw'], com8['rangos']['4']['max_raw']) == (840, 3040)      # los demás, intactos
    assert next(b for b in nuevo['brazos'] if b['puerto'] == 'COM7')['rangos']['1']['min_raw'] == 810
    assert hecho == [1] and any('anterior' in p.name for p in (tmp_path / 'config').iterdir())    # y queda copia de lo de antes
    assert not a.hay_cambios() and a.table.item('COM8_4')['values'][-1] == 'recorrido ahora, sin guardar'
    a.poll()
    assert a.table.item('COM8_4')['values'][-1] == 'guardado'


def test_si_los_servos_han_cambiado_los_rangos_guardados_no_se_cargan(asistente, tmp_path):
    _guardar(tmp_path)
    lector = Lector()
    lector.meta['COM8'] = [{**m, 'offset_raw': 99} for m in META['COM8']]   # otro ajuste interno en los servos de COM8
    a = asistente(lector)
    assert a.capturas['COM7'].rangos and len(a.capturas['COM7'].rangos) == 6
    assert set(a.capturas['COM8'].rangos) <= {0} and ('COM8', 1) not in a.congelados              # COM8 hay que recorrerlo de nuevo
    assert 'COM8' in a.status.get() and 'otros ajustes internos' in a.status.get()
    assert '6 guardados de antes' in a.progreso.get()


def test_un_brazo_desconectado_conserva_sus_rangos(asistente, tmp_path):
    _guardar(tmp_path)
    lector = Lector(puertos=('COM7',))
    a = asistente(lector)
    assert a.table.item('COM8_2')['values'][2:] == [830, 3030, '193.4', 'guardado · USB sin conectar']
    assert a.progreso.get().startswith('12 de 12 motores con rango guardado')
    a.port.set('COM7'); a.motor.set('2 · Hombro'); a.reiniciar()
    for valor in (2000, 900, 3300):
        lector.raw['COM7'][1] = valor; a.poll()
    a.guardado_callback = lambda: None
    a.guardar()
    nuevo = json.loads((tmp_path / 'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
    assert {b['puerto'] for b in nuevo['brazos']} == {'COM7', 'COM8'}                            # sigue completo
    assert next(b for b in nuevo['brazos'] if b['puerto'] == 'COM8')['rangos']['3']['max_raw'] == 3030
    assert next(b for b in nuevo['brazos'] if b['puerto'] == 'COM7')['rangos']['2']['min_raw'] == 900


def test_la_ventana_abre_en_la_pestana_que_hace_falta(tmp_path, monkeypatch):
    import so101er.hardware.alineacion as al
    p = SimpleNamespace(root=tmp_path)
    p.estado_guardado = lambda port: Programa.estado_guardado(p, port)
    assert Programa.estado_guardado(p, 'COM7') == (0, 'COM7: faltan los rangos (pestaña 1)')
    assert Programa.pestana_inicial(p) == 0                                 # sin nada guardado: a recorrer rangos
    _guardar(tmp_path)
    assert Programa.estado_guardado(p, 'COM8') == (1, 'COM8: rangos guardados; falta la postura (pestaña 2)')
    assert Programa.pestana_inicial(p) == 1
    def antigua(root, puerto, cal):
        raise ValueError('alineación antigua o distinta de estos rangos/servos; repítela')
    monkeypatch.setattr(al.Alineacion, 'cargar', classmethod(lambda cls, *a: antigua(*a)))
    assert Programa.estado_guardado(p, 'COM7') == (1, 'COM7: rangos guardados; repite la postura (pestaña 2)')
    monkeypatch.setattr(al.Alineacion, 'cargar', classmethod(lambda cls, *a: object()))
    assert Programa.estado_guardado(p, 'COM7') == (None, 'COM7: rangos y postura guardados')
    assert Programa.pestana_inicial(p) == 2                                 # todo guardado: directo a preparar y arrancar
