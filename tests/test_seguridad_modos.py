import numpy as np
import pytest

from conftest import DT, RAIZ, crear, grabar
from so101er.agente.herramientas import ejecutar_llamada
from so101er.config import ErrorConfig, cargar
from so101er.control.gestos import ErrorGesto, Gesto
from so101er.geometria import distancia_cadenas


# ------------------------------------------------------------------ seguridad
def test_verificacion_detecta_brazos_que_se_cruzan(dos):
    from so101er.control.gestos import pose_apuntar
    from so101er.control.linea import Linea
    cruz = {"izq": [600, 950], "der": [600, 50]}
    lineas = {n: Linea(pose_apuntar(dos._contexto(n, np.zeros(6)), dos.cuadro.punto_mundo(p), 0.95, 0.0, 8.0))
              for n, p in cruz.items()}
    assert "brazos se acercarían" in dos.seguridad.verificar(lineas, 0.0, 0.2)
    lineas["der"] = Linea(dos.coreos["der"].destino())
    assert dos.seguridad.verificar(lineas, 0.0, 0.2) is None


def test_gestos_cruzados_nunca_acercan_los_brazos(dos):
    # Aunque se pida que los brazos se crucen, el segundo gesto se reduce o se rechaza.
    dos.ejecutar(Gesto("senalar", "izq", {"punto": [600, 950], "mantener": 5}, cualidades={"amplitud": 1.0}))
    try:
        r = dos.ejecutar(Gesto("senalar", "der", {"punto": [600, 50], "mantener": 5}, cualidades={"amplitud": 1.0}))
        assert any("seguridad" in a for a in r["brazos"][0]["avisos"])
    except ErrorGesto as e:
        assert "rechazado por seguridad" in str(e)
    minimo = 1e9
    while dos.ocupado():
        dos.avanzar(DT)
        a, b = (dos.seguridad.cadena_mundo(n, dos.coreos[n].cmd) for n in dos.nombres)
        minimo = min(minimo, distancia_cadenas(a[2:], b[2:]))
    assert minimo >= dos.cfg.limites.distancia_min_brazos_mm - 15
    assert not dos.alertas


def test_distancia_minima_durante_gestos_simultaneos(dos):
    dos.ejecutar(Gesto("abarcar", "izq", {"desde": [300, 50], "hasta": [300, 480]}))
    dos.ejecutar(Gesto("abarcar", "der", {"desde": [300, 950], "hasta": [300, 520]}))
    minimo = 1e9
    while dos.ocupado():
        dos.avanzar(DT)
        a, b = (dos.seguridad.cadena_mundo(n, dos.coreos[n].cmd) for n in dos.nombres)
        minimo = min(minimo, distancia_cadenas(a[2:], b[2:]))
    assert minimo >= dos.cfg.limites.distancia_min_brazos_mm
    assert not dos.alertas


def test_zona_compartida_solo_un_brazo():
    s = crear("dos", zona_compartida={"activa": True, "x_min_mm": -140.0, "x_max_mm": 140.0})
    def en_zona(n):
        cadena = s.seguridad.cadena_mundo(n, s.coreos[n].cmd)
        return any(-140.0 <= p[0] <= 140.0 for p in cadena[-2:])

    s.ejecutar(Gesto("senalar", "izq", {"punto": [350, 520], "mantener": 6}, cualidades={"amplitud": 1.0}))
    try:      # ER 2 pide que entre también el otro: se rechaza (o se reduce hasta quedar fuera)
        s.ejecutar(Gesto("senalar", "der", {"punto": [700, 480], "mantener": 6}, cualidades={"amplitud": 1.0}))
    except ErrorGesto as e:
        assert "zona compartida" in str(e)
    dentro_izq = False
    while s.ocupado():
        s.avanzar(DT)
        dentro_izq = dentro_izq or en_zona("izq")
        assert not (en_zona("izq") and en_zona("der"))             # nunca los dos a la vez
    assert dentro_izq and not s.alertas
    s.ejecutar(Gesto("reposo", "todos"))                           # al salir el primero…
    grabar(s, hasta_quieto=True)
    r = s.ejecutar(Gesto("senalar", "der", {"punto": [700, 480]}, cualidades={"amplitud": 1.0}))
    assert not r["brazos"][0]["avisos"]                            # …el segundo entra sin reducirse


def test_no_se_acerca_a_la_obra():
    # Obra muy cerca de los brazos: el gesto debe mantenerse a la separación mínima.
    s = crear("dos", cuadro={"sup_izq": [-350.0, 300.0, 460.0], "sup_der": [350.0, 300.0, 460.0],
                             "inf_izq": [-350.0, 300.0, 60.0]})
    s.ejecutar(Gesto("senalar", "izq", {"punto": [500, 300]}, cualidades={"amplitud": 1.0}))
    minimo = 1e9
    while s.ocupado():
        s.avanzar(DT)
        cadena = s.seguridad.cadena_mundo("izq", s.coreos["izq"].cmd)
        minimo = min(minimo, min(s.cuadro.distancia(p) for p in cadena[3:]))
    assert minimo >= s.cfg.cuadro.separacion_min_mm - 15
    assert not s.alertas


def test_pose_bajo_la_mesa_se_rechaza(dos):
    with pytest.raises(ErrorGesto, match="altura mínima|codo|fuera de alcance|reducido"):
        dos.ejecutar(Gesto("gesto_libre", "izq", {"poses": [{"alcance": 1.0, "altura": 0.0, "elevacion": -80}]}))
        grabar(dos, hasta_quieto=True)
        problema = dos.seguridad.problema_pose("izq", dos.coreos["izq"].cmd)
        if problema:
            raise ErrorGesto(problema)
        raise ErrorGesto("reducido")       # aceptado solo si quedó dentro de la zona segura


def test_brazo_bloqueado_se_detiene_y_avisa(dos):
    dos.brazos["izq"].desactivar_par()                             # el motor no sigue la consigna
    dos.ejecutar(Gesto("elevar", "izq", estilo="dramatico"))
    grabar(dos, 4.0)
    assert dos.coreos["izq"].detenido
    assert any("error de seguimiento" in a for _, a in dos.alertas)
    assert not dos.coreos["der"].detenido


def test_temperatura_alta_detiene(dos):
    dos.brazos["der"].temperatura[:] = 75.0
    grabar(dos, 1.2)
    assert dos.coreos["der"].detenido and any("temperatura" in a for _, a in dos.alertas)


def test_arranque_sin_saltos():
    s = crear("dos")
    for n in s.nombres:
        medido = s.brazos[n].leer_articulaciones()
        assert np.abs(s.coreos[n].cmd - medido).max() < 4.0        # solo la respiración


# ------------------------------------------------------------------ modos
def test_modo_uno_y_modo_dos_sin_tocar_codigo():
    for modo, brazo, esperado in (("dos", "izq", ["izq", "der"]), ("uno", "izq", ["izq"]), ("uno", "der", ["der"])):
        s = crear(modo, brazo)
        assert s.nombres == esperado and set(s.coreos) == set(esperado)
        r = s.ejecutar(Gesto("presentar", "todos"))
        assert [b["brazo"] for b in r["brazos"]] == esperado
        grabar(s, hasta_quieto=True)
        assert not s.alertas


def test_modo_uno_rechaza_el_otro_brazo(uno):
    with pytest.raises(ErrorGesto, match="solo existe 'izq'"):
        uno.ejecutar(Gesto("presentar", "der"))


def test_brazo_auto_elige_el_mas_cercano(dos):
    assert dos.resolver_brazos(Gesto("senalar", "auto", {"punto": [500, 100]})) == ["izq"]
    assert dos.resolver_brazos(Gesto("senalar", "auto", {"punto": [500, 900]})) == ["der"]


def test_relaciones_entre_brazos(dos):
    for relacion in ("espejo", "canon", "acompanar"):
        r = dos.ejecutar(Gesto("elevar", "izq", relacion=relacion))
        assert {b["brazo"] for b in r["brazos"]} == {"izq", "der"}
        grabar(dos, hasta_quieto=True)
    assert not dos.alertas


# ------------------------------------------------------------------ configuración
@pytest.mark.parametrize("datos, texto", [
    ({"general": {"modo": "tres"}}, "general.modo"),
    ({"general": {"frecuencia_hz": -5}}, "frecuencia_hz"),
    ({"limites": {"velocidad_grados_s": [1, 2, 3]}}, "se esperaban 6"),
    ({"cuadro": {"sup_der": [-350.0, 520.0, 560.0]}}, "no definen un plano"),
    ({"movimiento": {"estilo": "inexistente"}}, "estilo desconocido"),
    ({"estilos": {"raro": {"brillo": 1}}}, "cualidades desconocidas"),
    ({"brazos": {"izq": {"signo": [1, 1, 2, 1, 1]}}}, "1 o -1"),
])
def test_errores_de_configuracion_en_espanol(datos, texto):
    with pytest.raises(ErrorConfig, match=texto):
        cargar(RAIZ / "config" / "so101er.toml", datos=datos)


def test_sin_simulacion_exige_puertos():
    with pytest.raises(ErrorConfig, match="puerto está vacío"):
        cargar(RAIZ / "config" / "so101er.toml", simulado=False)


def test_configuracion_incluida_igual_que_la_editable():
    assert (RAIZ / "config" / "so101er.toml").read_text(encoding="utf-8") == \
        (RAIZ / "src" / "so101er" / "predeterminado.toml").read_text(encoding="utf-8")


# ------------------------------------------------------------------ validación de funciones
@pytest.mark.parametrize("nombre, args, texto", [
    ("senalar", {"brazo": "izq"}, "falta 'punto'"),
    ("senalar", {"punto": [1500, 20]}, "0 a 1000"),
    ("senalar", {"punto": [100, 200], "velocidad": 3}, "parámetros desconocidos"),
    ("trazar", {"puntos": [[1, 2]]}, "al menos dos puntos"),
    ("dibujar_forma", {"forma": "triangulo", "plano": "aire"}, "forma desconocida"),
    ("medir", {"tamano": 7}, "entre 0 y 1"),
    ("presentar", {"estilo": "punk"}, "estilo desconocido"),
    ("presentar", {"brazo": "centro"}, "brazo desconocido"),
    ("presentar", {"cualidades": {"brillo": 2}}, "cualidades desconocidas"),
    ("bailar", {}, "función desconocida"),
    ("matizar", {"volumen": 3}, "energia, amplitud y tempo"),
])
def test_validacion_de_funciones_con_mensajes_utiles(dos, nombre, args, texto):
    r = ejecutar_llamada(dos, None, nombre, args)
    assert "error" in r and texto in r["error"], r


def test_las_funciones_responden_enseguida(dos):
    import time
    t0 = time.perf_counter()
    r = ejecutar_llamada(dos, None, "senalar", {"brazo": "izq", "punto": [300, 250], "estilo": "solemne"})
    assert time.perf_counter() - t0 < 0.5
    assert r["estado"] == "aceptado, en curso" and dos.ocupado()
    estado = ejecutar_llamada(dos, None, "estado", {})
    assert estado["brazos"]["izq"]["en_movimiento"] and estado["brazos"]["izq"]["actividad"] == "senalar"
