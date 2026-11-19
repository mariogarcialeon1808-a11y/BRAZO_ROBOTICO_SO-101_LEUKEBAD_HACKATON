import json

import numpy as np
import pytest

from conftest import DT, crear, derivadas
from so101er.agente.herramientas import ejecutar_llamada
from so101er.control.gestos import Gesto
from so101er.demo import DEMO, ejecutar_demo
from so101er.sincronia.director import Director
from so101er.sincronia.partitura import (ErrorPartitura, Frase, Partitura, acentos_automaticos, contar_silabas,
                                         estimar_tiempos)
from so101er.sincronia.voz import VozMuda


def test_estimacion_de_tiempos():
    assert [contar_silabas(p) for p in ("sol", "cuadro", "montañas", "bienvenidos")] == [1, 2, 3, 4]
    palabras, duracion = estimar_tiempos("Arriba, el sol domina la escena.", 4.0)
    assert [p.texto for p in palabras][:3] == ["Arriba,", "el", "sol"]
    assert palabras[1].inicio == pytest.approx(0.75 + 0.22)        # 3 sílabas + pausa de la coma
    assert duracion == pytest.approx(sum(p.silabas for p in palabras) / 4.0 + 0.22 + 0.4)
    assert acentos_automaticos(palabras)[0] == 0


def test_partitura_ida_y_vuelta(tmp_path):
    p = Partitura.de_dict(DEMO)
    ruta = tmp_path / "p.json"
    p.guardar(ruta)
    q = Partitura.cargar(ruta)
    assert q.a_dict() == p.a_dict() and len(q.frases) == 6
    with pytest.raises(ErrorPartitura, match="falta el texto"):
        Partitura.de_dict({"frases": [{"gestos": []}]})


def _interpretar(s, d, frase, voz_eventos=()):
    """Interpreta una frase y registra (t, τ del brazo, compás, velocidad articular)."""
    d.interpretar(Partitura([frase]))
    filas, eventos = [], dict(voz_eventos)
    previo = s.coreos["izq"].cmd.copy()
    while d.activo or s.ocupado():
        for cuando, accion in list(eventos.items()):
            if d.fase == "hablando" and d.voz.posicion(s.t) >= cuando:
                accion(s.t)
                del eventos[cuando]
        s.avanzar(DT)
        cmd = s.coreos["izq"].cmd
        m, _ = s.compas.posicion(s.t)
        filas.append((s.t, s.coreos["izq"].reloj.tau, m, float(np.abs(cmd - previo)[:5].max() / DT)))
        previo = cmd.copy()
        assert s.t < 120
    return np.array(filas)


def _desfase_en(filas, instante_compas):
    """Diferencia entre cuándo llega el brazo y cuándo llega la voz a un instante del compás."""
    t_voz = filas[np.argmax(filas[:, 2] >= instante_compas), 0]
    t_brazo = filas[np.argmax(filas[:, 1] >= instante_compas), 0]
    return t_brazo - t_voz


@pytest.mark.parametrize("velocidad", [1.0, 0.75, 1.2])
def test_el_gesto_llega_con_la_palabra_aunque_la_voz_cambie_de_ritmo(velocidad):
    s = crear("dos")
    d = Director(s, VozMuda(4.6, velocidad=velocidad))
    frase = Frase("Arriba, el sol domina la escena con su luz dorada.",
                  gestos=[Gesto("senalar", "izq", {"punto": [200, 300]}, ancla=2),
                          Gesto("presentar", "izq", ancla=8)])
    filas = _interpretar(s, d, frase)
    assert len(d.anclas) == 2
    for ancla in d.anclas:
        assert ancla["apice"] <= ancla["objetivo"] + 1e-6          # planificado: nunca después de la palabra
        assert ancla["objetivo"] - ancla["apice"] < 0.2
        assert abs(_desfase_en(filas, ancla["apice"])) < 0.06      # ejecutado: el brazo va con la voz
    assert not s.alertas


def test_si_la_voz_se_detiene_el_gesto_queda_suspendido():
    s = crear("dos")
    voz = VozMuda(4.6)
    d = Director(s, voz)
    frase = Frase("Las montañas dibujan una línea quebrada que cruza todo el cuadro.",
                  gestos=[Gesto("trazar", "izq", {"puntos": [[600, 30], [370, 180], [540, 330]]}, ancla=1)])
    d.interpretar(Partitura([frase]))
    while d.fase != "hablando":
        s.avanzar(DT)
    corte = d.anclas[0]["apice"] - d.m_voz + 1.0        # un segundo después de empezar el trazo
    filas, t_pausa, reanudada = [], None, False
    previo = s.coreos["izq"].cmd.copy()
    while d.activo or s.ocupado():
        if t_pausa is None and voz.estado == "hablando" and voz.posicion(s.t) >= corte:
            voz.pausar(s.t)
            t_pausa = s.t
        if t_pausa is not None and not reanudada and s.t >= t_pausa + 2.0:
            voz.reanudar(s.t)
            reanudada = True
        s.avanzar(DT)
        cmd = s.coreos["izq"].cmd
        filas.append((s.t, s.coreos["izq"].reloj.tau, float(np.abs(cmd - previo)[:5].max() / DT)))
        previo = cmd.copy()
        assert s.t < 120
    filas = np.array(filas)
    t, tau, vel = filas[:, 0], filas[:, 1], filas[:, 2]
    assert t_pausa is not None and reanudada
    en_pausa = (t > t_pausa + 0.8) & (t < t_pausa + 1.9)
    assert vel[(t > t_pausa - 0.3) & (t < t_pausa)].max() > 6.0     # se estaba moviendo…
    assert vel[en_pausa].max() < 3.0                                # …y queda suspendido (solo respira)
    assert tau[en_pausa].max() - tau[en_pausa].min() < 0.02
    assert vel[(t > t_pausa + 2.4) & (t < t_pausa + 3.5)].max() > 6.0   # y continúa al volver la voz
    assert np.abs(np.diff(vel)).max() / DT < s.cfg.limites.aceleracion.max()   # sin tirones al parar ni al seguir
    assert not s.alertas


def test_interrupcion_de_la_voz_recoge_los_brazos():
    s = crear("dos")
    d = Director(s, VozMuda(4.6))
    d.interpretar(Partitura.de_dict(DEMO))
    while not (d.fase == "hablando" and s.ocupado()):
        s.avanzar(DT)
    for _ in range(80):
        s.avanzar(DT)
    d.interrumpir()
    assert not d.cola and d.fase == "inactivo"
    s.avanzar_hasta_quieto()
    reposo = s.planificar_solo(Gesto("reposo", "izq"), "izq").q_final
    for n in s.nombres:
        assert s.coreos[n].gesto_actual in ("reposo", "pausa")
    assert np.abs(s.coreos["izq"].destino() - reposo).max() < 1.0
    assert not [a for _, a in s.alertas if "interrumpida" not in a]


# ------------------------------------------------------------------ extremo a extremo
@pytest.mark.parametrize("modo, brazo", [("dos", "izq"), ("uno", "izq"), ("uno", "der")])
def test_demo_completa_en_simulacion(modo, brazo):
    from so101er.config import cargar
    from conftest import RAIZ
    cfg = cargar(RAIZ / "config" / "so101er.toml", modo=modo, brazo=brazo, simulado=True)
    informe = ejecutar_demo(cfg)
    assert informe["frases"] == 6
    assert not [a for a in informe["alertas"] if "omitido" not in a]
    for datos in informe["brazos"].values():
        assert datos["velocidad_max_%"] < 90 and datos["aceleracion_max_%"] < 90 and datos["tiron_max_%"] < 90
    assert informe["sincronia"]["peor_retraso_ms"] <= 0
    if modo == "dos":
        assert not informe["alertas"]
        assert informe["sincronia"]["gestos_anclados"] == 12
        assert informe["distancia_min_brazos_mm"] >= cfg.limites.distancia_min_brazos_mm


class AgenteFalso:
    """Hace de ER 2: recibe la respuesta de cada función y decide la siguiente llamada."""

    def __init__(self):
        self.guion = [
            ("frase_de_movimiento", {"texto": "Mirad el sol, arriba a la derecha.", "estilo": "solemne",
                                     "gestos": [{"tipo": "senalar", "brazo": "der", "punto": [200, 780], "ancla": 2}]}),
            ("senalar", {"brazo": "izq", "punto": [2000, 100]}),                 # error a propósito
            ("senalar", {"brazo": "izq", "punto": [470, 200], "estilo": "didactico"}),   # corrección
            ("estado", {}),
            ("frase_de_movimiento", {"texto": "El lago descansa abajo, tranquilo.", "estilo": "tierno",
                                     "gestos": [{"tipo": "ondular", "brazo": "izq", "desde": [840, 230],
                                                 "hasta": [840, 480], "ancla": 1}]}),
            ("reposo", {"brazo": "todos"}),
        ]
        self.respuestas = []

    def siguiente(self):
        return self.guion.pop(0) if self.guion else None


def test_extremo_a_extremo_con_agente_falso():
    s = crear("dos")
    d = Director(s, VozMuda(4.6))
    agente = AgenteFalso()
    while (llamada := agente.siguiente()) is not None:
        nombre, args = llamada
        respuesta = ejecutar_llamada(s, d, nombre, args)
        json.dumps(respuesta)                                      # serializable para la API
        agente.respuestas.append((nombre, respuesta))
        s.avanzar_hasta_quieto()                                   # el agente "mira" y espera
    errores = [r for _, r in agente.respuestas if "error" in r]
    assert len(errores) == 1 and "0 a 1000" in errores[0]["error"]
    estado = next(r for n, r in agente.respuestas if n == "estado")
    assert np.linalg.norm(np.array(estado["brazos"]["izq"]["apunta_yx"]) - [470, 200]) < 30
    assert len(d.anclas) == 2 and not s.alertas
    final = ejecutar_llamada(s, d, "estado", {})
    assert all(not b["en_movimiento"] for b in final["brazos"].values())
