"""El registro expresivo (movimientos y conexiones concepto → movimiento) es coherente y su documento está al día.

El programa no lee todavía el registro: estas pruebas solo protegen la documentación comprobable.
"""
import importlib.util
import statistics
from collections import Counter

import pytest

from conftest import RAIZ


@pytest.fixture(scope='module')
def herramienta():
    spec = importlib.util.spec_from_file_location('registro_expresivo', RAIZ / 'tools' / 'registro_expresivo.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope='module')
def registro(herramienta):
    return herramienta.leer()


def test_el_registro_no_tiene_incoherencias(herramienta, registro):
    assert herramienta.problemas(registro) == []
    roto = herramienta.leer()
    roto['conexiones'][0]['principal'] = 'Z99'
    roto['conexiones'][1]['otro'] = {'papel': 'ancla'}
    fallos = herramienta.problemas(roto)
    assert any('primitiva desconocida Z99' in f for f in fallos) and any('necesita decir con qué movimiento' in f for f in fallos)


def test_hay_vocabulario_para_todos_los_ambitos(registro):
    assert len(registro['primitivas']) >= 80 and len(registro['conexiones']) >= 250
    por_dominio = Counter(c['dominio'] for c in registro['conexiones'])
    assert set(por_dominio) == {d['id'] for d in registro['dominios']} and min(por_dominio.values()) >= 15
    usados = {c['principal'] for c in registro['conexiones']} | {c['otro'].get('primitiva') for c in registro['conexiones']}
    usados |= {g for c in registro['conexiones'] for g in c.get('despues', [])}
    assert all(p['id'] in usados for p in registro['primitivas'])                # ningún movimiento sin concepto
    # Señalar no es el recurso por defecto: la mayoría de las conexiones no señalan la imagen.
    senalan = {'D01', 'D02', 'D03', 'D04', 'D05', 'B15', 'B16'}
    assert sum(c['principal'] in senalan for c in registro['conexiones']) < len(registro['conexiones']) / 5
    # El otro brazo aporta significado (espejo, ancla, contrapunto) en una parte apreciable.
    papeles = Counter(c['otro']['papel'] for c in registro['conexiones'])
    assert papeles['espejo'] + papeles['ancla'] + papeles['contrapunto'] >= 100


def test_cada_movimiento_dice_si_cabe_en_los_dos_brazos(registro):
    comprobacion = registro['comprobacion']
    assert comprobacion['brazos'] == ['izq', 'der'] and comprobacion['velocidad_grados_s'] > 0
    for p in registro['primitivas']:
        estado = p['motor']['estado']
        assert estado in ('existente', 'comprobado', 'motor'), (p['id'], p['motor'])      # ninguno «no cabe» ni sin mirar
        if estado == 'comprobado':
            assert set(p['motor']['dura_s']) == {'izq', 'der'} and 1.5 <= max(p['motor']['dura_s'].values()) <= 7, p['id']
            assert 0.5 <= max(p['motor']['apice_s'].values()) <= 3, p['id']
    duraciones = [p['motor']['dura_s']['izq'] for p in registro['primitivas'] if p['motor']['estado'] == 'comprobado']
    assert 4 <= statistics.median(duraciones) <= 5                               # la cifra que cita el protocolo


def test_el_documento_esta_generado_del_registro(herramienta, registro):
    escrito = (RAIZ / 'docs' / 'REGISTRO_EXPRESIVO.md').read_text(encoding='utf8')
    assert escrito == herramienta.documento(registro)       # si falla: python tools/registro_expresivo.py documento
    for regla in ('R1.', 'R17.', 'R34.', 'R56.'):
        assert f'**{regla}' in (RAIZ / 'docs' / 'PROTOCOLO_EXPRESIVO.md').read_text(encoding='utf8')


def test_la_comprobacion_contra_el_motor_se_puede_repetir(herramienta, registro):
    motor, _ = herramienta.montar_motor()
    por_id = {p['id']: p for p in registro['primitivas']}
    for id_ in ('E05', 'B06', 'M02'):                       # un brazo, los dos a la vez, y con giro de muñeca
        resultado = herramienta.comprobar_movimiento(motor, por_id[id_]['movimiento'])
        assert resultado['cabe'] and resultado['dura_s'] == por_id[id_]['motor']['dura_s'], id_
    lejos = {'principal': [{'r': 900, 'az': 0, 'z': 200, 'giro': 0, 'pinza': 30}]}
    assert herramienta.comprobar_movimiento(motor, lejos)['cabe'] is False      # lo que no cabe se rechaza, con su motivo
    assert 'motivo' in herramienta.comprobar_movimiento(motor, lejos)
