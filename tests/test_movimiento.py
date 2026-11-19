import numpy as np
import pytest

from conftest import DT, crear, derivadas, grabar
from so101er.control.filtro import FiltroTiron
from so101er.control.gestos import GESTOS, ErrorGesto, Gesto
from so101er.control.linea import Linea, Sub
from so101er.control.perfiles import bulto, deformar, escalon


def dentro_de_limites(s, x, margen=1.0):
    v, a, j = derivadas(x)
    lim = s.cfg.limites
    assert np.all(np.abs(v).max(0) <= lim.velocidad * margen), np.abs(v).max(0) / lim.velocidad
    assert np.all(np.abs(a).max(0) <= lim.aceleracion * margen), np.abs(a).max(0) / lim.aceleracion
    assert np.all(np.abs(j).max(0) <= lim.tiron * margen), np.abs(j).max(0) / lim.tiron


def test_formas_basicas():
    u = np.linspace(0, 1, 2001)
    for c in (0.6, 1.0, 1.5):
        f = escalon(deformar(u, c))
        assert f[0] == 0 and f[-1] == pytest.approx(1)
        assert np.all(np.diff(f) >= -1e-12)                       # monótono
        for orden in (1, 2, 3):                                   # arranque y llegada suaves
            d = np.diff(f, n=orden) / (u[1] ** orden)
            assert abs(d[0]) < 0.06 * np.abs(d).max() and abs(d[-1]) < 0.06 * np.abs(d).max()
    b = bulto(u)
    assert b[0] == 0 and b[-1] == 0 and b.max() == pytest.approx(1)


def test_superposicion_es_suave_aunque_se_solapen():
    linea = Linea(np.zeros(6))
    linea.subs.append(Sub(0.0, 1.0, np.full(6, 40.0)))
    linea.subs.append(Sub(0.35, 0.8, np.full(6, -70.0)))          # nuevo objetivo a mitad de movimiento
    linea.subs.append(Sub(0.5, 0.6, np.full(6, 5.0), es_bulto=True))
    t = np.arange(0, 1.6, 0.001)
    x = np.array([linea.valor(k) for k in t])
    a = np.diff(x[:, 0], n=2) / 1e-6
    assert np.max(np.abs(np.diff(a))) < 0.02 * np.max(np.abs(a))  # aceleración sin saltos
    assert np.allclose(linea.valor(5.0), -30.0) and np.allclose(linea.destino(), -30.0)
    linea.podar(5.0)
    assert not linea.subs and np.allclose(linea.base, -30.0)


def test_filtro_sigue_exacto_dentro_de_limites_y_limita_un_salto():
    lim = ([150], [600], [8000], [-200], [200])
    f = FiltroTiron(np.zeros(1), *lim)
    for k in range(300):
        ref = np.array([60 * escalon(k * DT / 1.5)])
        assert abs(f.paso(ref, DT)[0] - ref[0]) < 1e-9
    f = FiltroTiron(np.zeros(1), *lim)
    x = np.array([f.paso(np.array([80.0]), DT)[0] for _ in range(500)])
    v = np.diff(x) / DT
    assert x.max() <= 80.0 + 1e-6 and x[-1] == pytest.approx(80.0, abs=0.01)   # sin rebasar
    assert np.abs(v).max() <= 150 + 1e-6 and np.abs(np.diff(v) / DT).max() <= 600 + 1e-6


@pytest.mark.parametrize("estilo", ["solemne", "entusiasta", "misterioso", "dramatico", "tierno"])
def test_un_gesto_respeta_los_limites(dos, estilo):
    dos.ejecutar(Gesto("senalar", "izq", {"punto": [300, 250]}, estilo=estilo))
    dos.ejecutar(Gesto("dibujar_forma", "der", {"forma": "ocho", "plano": "aire"}, estilo=estilo))
    x = grabar(dos, hasta_quieto=True)
    for n in dos.nombres:
        dentro_de_limites(dos, x[n], 0.9)
        assert not dos.coreos[n].filtro.saturado
    assert not dos.alertas


def test_todos_los_gestos_se_ejecutan(dos):
    params = {"senalar": {"punto": [400, 300]}, "trazar": {"puntos": [[200, 100], [500, 400]]},
              "abarcar": {"desde": [300, 100], "hasta": [300, 450]},
              "dibujar_forma": {"forma": "circulo", "centro": [500, 300], "tamano": 250},
              "ondular": {"desde": [700, 50], "hasta": [700, 450]},
              "gesto_libre": {"poses": [{"alcance": 0.7, "altura": 0.8, "pinza": 80}, {"altura": 0.3, "azimut": 30}]},
              "trayectoria": {"puntos": [{"mira": [300, 150]}, {"mira": [600, 400]}, {"altura": 0.8, "pinza": 90}]}}
    for tipo in GESTOS:
        r = dos.ejecutar(Gesto(tipo, "izq", params.get(tipo, {})))
        assert r["estado"].startswith("aceptado")
        x = grabar(dos, hasta_quieto=True)
        dentro_de_limites(dos, x["izq"])
    assert not dos.alertas


def test_senalar_apunta_donde_se_pide(dos):
    for brazo, punto in (("izq", [300, 250]), ("der", [650, 800]), ("izq", [800, 420])):
        dos.ejecutar(Gesto("senalar", brazo, {"punto": punto, "mantener": 0.2}, cualidades={"tension": 1.0}))
        grabar(dos, hasta_quieto=True)
        real = dos.apunta(brazo, dos.coreos[brazo].linea.destino())
        assert np.linalg.norm(np.array(real) - punto) < 25        # < ~15 mm sobre la obra


def test_cambio_de_objetivo_a_mitad_sin_parar_ni_tirones(dos):
    dos.ejecutar(Gesto("senalar", "izq", {"punto": [250, 150]}))
    a = grabar(dos, 0.9)["izq"]                                   # a mitad de camino…
    dos.ejecutar(Gesto("senalar", "izq", {"punto": [750, 450]}))  # …llega otro objetivo
    b = grabar(dos, hasta_quieto=True)["izq"]
    x = np.vstack([a, b])
    dentro_de_limites(dos, x, 0.9)
    v = np.abs(derivadas(x)[0][:, :4]).max(axis=1)
    cambio = len(a)
    assert v[cambio - 20: cambio + 40].min() > 2.0                # no se detiene en el empalme
    assert not dos.coreos["izq"].filtro.saturado


def test_gestos_encadenados_se_funden(dos):
    r = dos.ejecutar(Gesto("presentar", "izq", {"mantener": 0.0}))
    fin = r["brazos"][0]["apice"]
    m, _ = dos.compas.posicion(dos.t)
    grabar(dos, fin - m - 0.25)                                   # justo antes de llegar
    dos.ejecutar(Gesto("recoger", "izq"), reemplazar=False)
    x = grabar(dos, 1.0)["izq"]
    v = np.abs(derivadas(x)[0][:, :4]).max(axis=1)
    assert v[:80].min() > 1.0                                     # la recogida empieza antes de frenar del todo


def test_parar_es_suave_y_se_reanuda(dos):
    dos.ejecutar(Gesto("elevar", "todos", estilo="dramatico"))
    a = grabar(dos, 1.2)
    dos.parar()
    b = grabar(dos, 1.5)
    for n in dos.nombres:
        x = np.vstack([a[n], b[n]])
        dentro_de_limites(dos, x, 0.9)
        assert np.abs(derivadas(b[n][-30:])[0][:, :5]).max() < 3.0     # quieto (solo respira)
    dos.ejecutar(Gesto("reposo", "todos"))
    grabar(dos, hasta_quieto=True)
    assert not dos.ocupado()


def test_emergencia_detiene_todo_y_exige_rearmar(dos):
    dos.ejecutar(Gesto("presentar", "todos"))
    grabar(dos, 0.6)
    dos.parar(emergencia=True)
    x = grabar(dos, 4.5)
    for n in dos.nombres:
        dentro_de_limites(dos, x[n], 1.0001)                      # frena al límite, nunca por encima
        assert np.abs(np.diff(x[n][-50:], axis=0)).max() < 1e-3   # completamente quieto, sin respiración
    with pytest.raises(ErrorGesto, match="emergencia"):
        dos.ejecutar(Gesto("reposo", "todos"))
    dos.rearmar()
    assert dos.ejecutar(Gesto("reposo", "todos"))["estado"].startswith("aceptado")


def test_reposo_vivo_respira(dos):
    x = grabar(dos, 6.0)["izq"]
    recorrido = x.max(0) - x.min(0)
    assert 0.5 < recorrido[1] < 5.0                               # se mueve, pero poco
    dentro_de_limites(dos, x, 0.2)


def test_matizar_reduce_la_amplitud(dos):
    grande = dos.planificar_solo(Gesto("presentar", "izq"), "izq").q_final
    dos.matizar(amplitud=0.4)
    chico = dos.planificar_solo(Gesto("presentar", "izq"), "izq").q_final
    base = dos.coreos["izq"].destino()
    assert np.abs(chico - base)[:5].sum() < np.abs(grande - base)[:5].sum()
