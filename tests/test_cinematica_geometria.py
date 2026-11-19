import numpy as np
import pytest

from so101er.cinematica.modelo import Cinematica, FueraDeAlcance
from so101er.geometria import Cuadro, ErrorPunto, distancia_segmentos, validar_punto


@pytest.fixture(scope="module")
def m() -> Cinematica:
    return Cinematica()


def test_pose_cero_del_urdf(m):
    pos, eje = m.punta(np.zeros(5))
    assert np.allclose(pos, [391.4, 0.0, 226.5], atol=0.5)
    assert np.allclose(eje, [1, 0, 0], atol=1e-3)
    assert m.puntos(np.zeros(5)).shape == (7, 3)


def test_ida_y_vuelta_directa_inversa(m):
    rng = np.random.default_rng(7)
    for _ in range(40):
        q = rng.uniform(m.lim_inf * 0.8, m.lim_sup * 0.8)
        pos, _ = m.punta(q)
        q2 = m.inversa(pos, giro=q[4], semilla=q + rng.uniform(-8, 8, 5))
        assert np.linalg.norm(m.punta(q2)[0] - pos) < 1.5
        assert np.all(q2 >= m.lim_inf - 1e-6) and np.all(q2 <= m.lim_sup + 1e-6)


def test_inversa_sin_semilla_y_con_elevacion(m):
    q = m.inversa(np.array([260.0, 80.0, 220.0]), elevacion=0.0)
    assert np.linalg.norm(m.punta(q)[0] - [260.0, 80.0, 220.0]) < 1.5
    assert abs(m.elevacion(q)) < 3.0


def test_fuera_de_alcance_da_error_claro(m):
    with pytest.raises(FueraDeAlcance, match="fuera del alcance"):
        m.inversa(np.array([900.0, 0.0, 200.0]))


def _cuadro() -> Cuadro:
    return Cuadro([-350, 520, 560], [350, 520, 560], [-350, 520, 120], lado_brazos=np.array([0, 0, 100.0]))


def test_orden_y_x_de_los_puntos():
    c = _cuadro()
    assert np.allclose(c.punto_mundo([0, 0]), [-350, 520, 560])        # arriba-izquierda
    assert np.allclose(c.punto_mundo([0, 1000]), [350, 520, 560])      # y=0, x=1000: arriba-derecha
    assert np.allclose(c.punto_mundo([1000, 0]), [-350, 520, 120])     # y=1000, x=0: abajo-izquierda
    assert np.allclose(c.punto_mundo([500, 500]), [0, 520, 340])


def test_obra_a_imagen_es_la_inversa():
    c = _cuadro()
    s, t = c.imagen_a_obra([250, 800])
    assert (s, t) == pytest.approx((0.8, 0.25))
    assert np.allclose(c.obra_a_imagen(s, t), [250, 800])


def test_rayo_hacia_la_obra():
    c = _cuadro()
    assert c.distancia(np.array([0, 0, 100.0])) == pytest.approx(520)
    st = c.interseccion(np.array([0.0, 0.0, 340.0]), np.array([0.0, 1.0, 0.0]))
    assert st == pytest.approx((0.5, 0.5))
    assert c.interseccion(np.array([0.0, 0.0, 340.0]), np.array([0.0, -1.0, 0.0])) is None


@pytest.mark.parametrize("malo", [[1200, 10], [-1, 5], [1, 2, 3], "x", [float("nan"), 0]])
def test_puntos_no_validos(malo):
    with pytest.raises(ErrorPunto):
        validar_punto(malo)


def test_distancia_entre_segmentos():
    a = distancia_segmentos(np.array([0, 0, 0.0]), np.array([10, 0, 0.0]), np.array([5, 3, 0.0]), np.array([5, 9, 0.0]))
    assert a == pytest.approx(3.0)
    b = distancia_segmentos(np.array([0, 0, 0.0]), np.array([10, 0, 0.0]), np.array([0, 0, 4.0]), np.array([10, 0, 4.0]))
    assert b == pytest.approx(4.0)
