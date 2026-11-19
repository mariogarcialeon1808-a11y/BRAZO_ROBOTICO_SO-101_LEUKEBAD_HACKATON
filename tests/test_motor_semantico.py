from dataclasses import replace
import numpy as np
import pytest
from so101er.config import cargar
from so101er.control.semantico import MotorGestos, ejemplos
from so101er.cinematica.modelo import FueraDeAlcance


@pytest.fixture(scope="module")
def motor():
    return MotorGestos(cargar())


@pytest.mark.parametrize("idx", range(4))
def test_cuatro_gestos_limites_y_significado(motor, idx):
    nombre, g, enc = ejemplos(motor)[idx]
    p = motor.compilar(g, enc)
    for n, q in p.q.items():
        np.testing.assert_allclose(q[0], enc[n])
        v = np.diff(q, axis=0)/np.diff(p.tiempos)[:,None]
        a = np.diff(v, axis=0)/np.diff((p.tiempos[1:]+p.tiempos[:-1])/2)[:,None]
        j = np.diff(a, axis=0)/np.diff(p.tiempos[1:-1])[:,None]
        assert np.max(abs(v)/motor.cfg.limites.velocidad) <= 1.001
        assert np.max(abs(a)/motor.cfg.limites.aceleracion) <= 1.001
        assert np.max(abs(j)/motor.cfg.limites.tiron) <= 1.001
        if n != g.brazo:
            np.testing.assert_allclose(q, np.repeat(enc[n][None], len(q), axis=0))
    assert p.error_posicion_mm <= 2 and p.error_eje_grados <= 3
    stroke = p.q[g.brazo][(p.tiempos>=p.inicio_trazo)&(p.tiempos<=p.fin_trazo)]
    fk = [motor.modelo.punta(q[:5]) for q in stroke]
    xyz, axes = np.array([f[0] for f in fk]), np.array([f[1] for f in fk])
    if nombre in ("paisaje", "cielo"):
        assert np.ptp(xyz[:,1]) > 140
        assert np.ptp(xyz[:,2]) < 5
        assert abs(np.mean(xyz[:,2])-(180 if nombre=='paisaje' else 265)) < 3
    elif nombre == "punto":
        assert np.max(np.ptp(xyz, axis=0)) < .01
        target = motor.cuadro.punto_mundo([260,720])
        frame = motor.marcos[g.brazo]
        direction = target-frame.a_mundo(xyz[-1])
        direction /= np.linalg.norm(direction)
        assert np.degrees(np.arccos(np.clip(frame.dir_a_mundo(axes[-1])@direction,-1,1))) < 4
    else:
        assert np.ptp(xyz[:,0]) > 25
        assert np.ptp(xyz[:,1]) < 3 and np.ptp(xyz[:,2]) < 3
        assert np.min(axes[:,0]) > np.cos(np.radians(3))


def test_rechaza_orientacion_imposible_y_datos_no_finitos(motor):
    _, g, enc = ejemplos(motor)[3]
    with pytest.raises(FueraDeAlcance):
        motor.compilar(replace(g,ejes=tuple((1,0,0) for _ in g.ejes)),enc)
    for bad in (float('nan'),float('inf'),-1):
        with pytest.raises(ValueError):
            motor.compilar(replace(g,duracion_s=bad),enc)
    with pytest.raises(ValueError):
        motor.compilar(g, {g.brazo:enc[g.brazo]})


def test_sensorial_invariancia_del_compilador(motor):
    # Frontera de esta prueba: compilador, no los backends históricos del proyecto.
    _, g, enc = ejemplos(motor)[3]
    privileged = {'qpos': np.ones(6), 'contact_force': 900}
    a = motor.compilar(g,enc)
    privileged.update(qpos=np.full(6,999),contact_force=-1000)
    b = motor.compilar(g,{n:q.copy() for n,q in enc.items()})
    for n in a.q:
        np.testing.assert_array_equal(a.q[n],b.q[n])
    np.testing.assert_array_equal(a.tiempos,b.tiempos)
    assert set(vars(motor)) == {'cfg','modelo','marcos','cuadro','seguridad'}


def test_objetivo_nuevo_cambia_trayectoria_y_partida_medida(motor):
    _, g, enc = ejemplos(motor)[3]
    a = motor.compilar(g,enc)
    changed = replace(g,puntos_mm=tuple(tuple(np.array(p)+[0,0,10]) for p in g.puntos_mm))
    b = motor.compilar(changed,enc)
    assert not np.allclose(a.q[g.brazo][-1],b.q[g.brazo][-1])
    enc[g.brazo] = a.q[g.brazo][-1]
    c = motor.compilar(changed,enc)
    np.testing.assert_array_equal(c.q[g.brazo][0],enc[g.brazo])

