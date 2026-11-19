"""El modo real debe comportarse como la simulación. Sin hardware.

Causas de «Gesto omitido: … encoders fuera de límites nominales» y «factor temporal fuera
de rango» en los brazos reales:
  1. el brazo apoyado en su tope mide décimas de grado más allá del límite del URDF;
  2. el reposo entre gestos era la postura plegada (en simulación es una postura en el aire);
  3. a 20°/s un gesto amplio tarda casi un minuto y la voz tendría que frenarse más de 8 veces.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from so101er.config import cargar
from so101er.control.escenico import pose_reposo, pose_trabajo, transicion, validar
from so101er.control.semantico import MotorGestos, ejemplos, inicio_nominal


@pytest.fixture(scope='module')
def motor():
    return MotorGestos(cargar())


def test_un_encoder_apoyado_en_el_tope_se_lleva_al_limite_nominal(motor):
    m = motor.modelo
    q = np.r_[m.lim_inf + [0, -.18, 0, -.09, 0], -.3]       # una o dos cuentas más allá del URDF
    limpio = inicio_nominal(m, q)
    np.testing.assert_allclose(limpio[:5], m.lim_inf)
    assert limpio[5] == 0 and q[1] < m.lim_inf[1]           # no altera la lectura original
    dentro = np.r_[np.zeros(5), 40.]
    np.testing.assert_array_equal(inicio_nominal(m, dentro), dentro)
    for malo in (np.r_[m.lim_inf - [0, 1.5, 0, 0, 0], 0.], np.r_[m.lim_sup + [0, 0, 0, 0, 2.], 0.], np.r_[np.zeros(5), 103.]):
        with pytest.raises(ValueError, match='encoders fuera de límites nominales'):
            inicio_nominal(m, malo)


def test_compilar_acepta_partir_de_un_tope_con_ruido_de_encoder(motor):
    _, g, inicial = ejemplos(motor)[0]
    otro = next(n for n in inicial if n != g.brazo)
    inicial[otro][4] = motor.modelo.lim_sup[4] + .18         # el brazo que no se mueve, apoyado en su tope
    plan = motor.compilar(g, inicial)
    assert plan.q[otro][0, 4] == motor.modelo.lim_sup[4]
    inicial[otro][4] = motor.modelo.lim_sup[4] + 3
    with pytest.raises(ValueError, match='encoders fuera de límites nominales'):
        motor.compilar(g, inicial)


def test_transicion_es_suave_validada_y_llega_exacta(motor):
    reposo = pose_trabajo(motor)
    np.testing.assert_array_equal(pose_reposo(motor), reposo)   # en simulación el reposo ES la postura de trabajo
    inicio = {n: reposo + [8., 6., -10., -20., 5., 30.] for n in motor.marcos}
    destino = {n: reposo.copy() for n in motor.marcos}
    plan = transicion(motor, inicio, destino)
    for n in motor.marcos:
        np.testing.assert_allclose(plan.q[n][0], inicio[n])
        np.testing.assert_allclose(plan.q[n][-1], destino[n], atol=1e-9)
    validar(motor, plan.tiempos, plan.q)                        # límites de movimiento, mesa, obra y separación
    lim = motor.cfg.limites
    v = np.diff(plan.q['izq'], axis=0) / np.diff(plan.tiempos)[:, None]
    assert np.all(abs(v) <= lim.velocidad * 1.005)
    hundido = {n: q.copy() for n, q in destino.items()}
    hundido['izq'][1:4] = [60., 60., 60.]                       # la pinza acabaría bajo la mesa
    with pytest.raises(ValueError):
        transicion(motor, inicio, hundido)


def test_transicion_solo_depende_de_encoders_y_constantes(motor):
    reposo = pose_trabajo(motor)
    inicio = {n: reposo + [4., 0., 0., -10., 0., 0.] for n in motor.marcos}
    destino = {n: reposo.copy() for n in motor.marcos}
    a = transicion(motor, inicio, destino)
    motor.verdad_privilegiada = SimpleNamespace(qpos=np.full(12, 9.), xpos=np.full(3, -5.))   # cambiar verdad interna…
    b = transicion(motor, inicio, destino)
    del motor.verdad_privilegiada
    for n in motor.marcos:
        np.testing.assert_array_equal(a.q[n], b.q[n])                                        # …no cambia la acción


def _plan(duracion):
    return SimpleNamespace(tiempos=np.array([0., duracion]))


def test_gestos_que_no_caben_se_omiten_en_vez_de_frenar_la_voz():
    from so101er.aplicacion import encajar_en_la_voz, ESTIRADO_MAX
    # Como en simulación: gestos de 6–7 s con anclas separadas 9 s. Caben todos, voz intacta.
    rapidos = [(4., 3., _plan(7.)), (13., 2.5, _plan(6.)), (22., 1., _plan(3.7)), (31., 2.8, _plan(6.4))]
    quedan, factor, quitados = encajar_en_la_voz(rapidos)
    assert len(quedan) == 4 and quitados == 0 and factor == 1
    # Como en real a 20°/s: gestos de 34–59 s. Antes: factor 6 (o «fuera de rango» y turno perdido).
    lentos = [(4., 25., _plan(59.)), (13., 22., _plan(55.)), (22., 12., _plan(34.)), (31., 21., _plan(53.))]
    quedan, factor, quitados = encajar_en_la_voz(lentos)
    assert quedan[0] is lentos[0] and quitados == 3 and factor <= ESTIRADO_MAX
    # Un caso intermedio conserva los que sí dan tiempo.
    medios = [(4., 3., _plan(7.)), (8., 3., _plan(7.)), (22., 3., _plan(7.))]
    quedan, factor, quitados = encajar_en_la_voz(medios)
    assert [g[0] for g in quedan] == [4., 22.] and quitados == 1 and factor == 1


def test_perfil_real_escala_como_la_simulacion(tmp_path):
    from so101er.aplicacion import perfil_real
    (tmp_path / 'config').mkdir()
    cfg = cargar()
    sim = cfg.limites.velocidad[0], cfg.limites.aceleracion[0]
    assert perfil_real(cfg, tmp_path) == 20                     # sin configuración: perfil de pruebas
    assert np.all(cfg.limites.velocidad[:5] == 20) and cfg.limites.velocidad[5] == 60
    assert np.all(cfg.limites.aceleracion == 80) and np.all(cfg.limites.tiron == 800)
    (tmp_path / 'config/so101er.toml').write_text('[real]\nvelocidad_grados_s = 150\n', encoding='utf8')
    assert perfil_real(cfg, tmp_path) == 150
    assert (cfg.limites.velocidad[0], cfg.limites.aceleracion[0]) == sim   # misma velocidad y aceleración que en simulación
