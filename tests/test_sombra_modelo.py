from types import SimpleNamespace
import numpy as np
import pytest


def test_sombra_solo_render_no_cambia_pose_principal_ni_referencias():
    pytest.importorskip('mujoco')
    from so101er.pruebas_modelo import Modelo
    from so101er.hardware.mujoco_sim import MundoMuJoCo
    q=np.array([0.,-60.,60.,10.,0.,30.]);ref=np.array([0.,-95.,95.,0.,0.,0.])
    saved_q=q.copy();saved_ref=ref.copy();m=Modelo()
    try:
        plain=m.foto(q,2);shadow=m.foto(q,2,ref)
        assert np.count_nonzero(plain!=shadow)>1000
        np.testing.assert_array_equal(q,saved_q);np.testing.assert_array_equal(ref,saved_ref)
        np.testing.assert_allclose(m.data.qpos,MundoMuJoCo.a_rad(q))
        np.testing.assert_allclose(m.ghost_data.qpos,MundoMuJoCo.a_rad(ref))
    finally:m.cerrar()


def test_calibrador_de_barras_no_se_abre_con_un_brazo_activado():
    from so101er.pruebas_modelo import Panel
    messages=[]
    p=SimpleNamespace(native=object(),status=SimpleNamespace(set=messages.append))
    Panel.abrir_rangos(p)
    assert messages and 'suelta' in messages[0]
