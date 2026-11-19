"""Fase 2 sin red: ER 2 y la voz en flujo, con sesiones falsas en lugar de la API de Google."""
import asyncio
from types import SimpleNamespace as NS

import numpy as np
import pytest

pytest.importorskip("google.genai")

from conftest import DT, crear
from so101er.agente.er2 import ER2Directo, ER2Estandar
from so101er.agente.herramientas import declaraciones, para_interacciones, para_live
from so101er.agente.prompt_sistema import prompt_coreografo, prompt_guia
from so101er.control.gestos import Gesto
from so101er.interfaz.camara import CamaraSim
from so101er.interfaz.registro import RegistroNulo
from so101er.sesion import mensaje_frase
from so101er.sincronia.director import Director
from so101er.sincronia.flujo import DirectorFlujo, VozFlujo
from so101er.sincronia.voz import VozMuda


def _llamada(nombre, args, id_):
    return NS(tool_call=NS(function_calls=[NS(name=nombre, args=args, id=id_)]), server_content=None,
              go_away=None, session_resumption_update=None)


def _texto(texto):
    return NS(tool_call=None, go_away=None, session_resumption_update=NS(resumable=True, new_handle="asa-1"),
              server_content=NS(model_turn=NS(parts=[NS(text=texto, thought=False)]), turn_complete=True))


class SesionFalsa:
    """Imita una sesión Live: responde a cada mensaje según un guion."""

    def __init__(self, guion, cortar_tras=None):
        self.guion, self.cortar_tras = guion, cortar_tras
        self.mensajes, self.respuestas = [], []
        self._cola = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send_client_content(self, turns, turn_complete=True):
        texto = turns.parts[-1].text
        assert any(getattr(p, "inline_data", None) and p.inline_data.mime_type == "image/jpeg"
                   for p in turns.parts)                                  # cada mensaje lleva la imagen
        self.mensajes.append(texto)
        for m in self.guion(texto, None):
            self._cola.put_nowait(m)

    async def send_tool_response(self, function_responses):
        for r in function_responses:
            self.respuestas.append((r.name, r.response))
            for m in self.guion(None, r):
                self._cola.put_nowait(m)

    async def receive(self):
        while True:
            m = await self._cola.get()
            if m == "CORTE":
                raise ConnectionError("red caída")
            yield m
            if m.server_content and m.server_content.turn_complete:
                return


async def _bombear(s, condicion, maximo_s=90.0):
    """Avanza la simulación mientras los agentes trabajan."""
    while not condicion() and s.t < maximo_s:
        s.avanzar(DT)
        await asyncio.sleep(0)
    for _ in range(30):
        s.avanzar(DT)
        await asyncio.sleep(0)


def test_declaraciones_segun_el_modo():
    dos, uno = crear("dos"), crear("uno", "der")
    # Modo libre (por defecto): ER 2 compone el movimiento; no se le ofrecen gestos con nombre.
    d2, d1 = declaraciones(dos), declaraciones(uno)
    assert [d["name"] for d in d2] == ["frase_de_movimiento", "movimiento", "matizar", "parar", "estado"]
    mov2 = next(d for d in d2 if d["name"] == "movimiento")["parameters"]["properties"]
    mov1 = next(d for d in d1 if d["name"] == "movimiento")["parameters"]["properties"]
    assert mov2["brazo"]["enum"] == ["izq", "der", "ambos"] and "relacion" in mov2
    assert {"circulo", "separacion", "desnivel"} <= set(mov2["puntos"]["items"]["properties"]) and "repetir" in mov2
    assert mov1["brazo"]["enum"] == ["der"] and "relacion" not in mov1           # modo uno: solo ese brazo
    assert {"mira", "alcance", "altura", "lado", "pinza", "ancla", "pausa"} <= set(mov2["puntos"]["items"]["properties"])
    assert "senalar" not in str(d2) and "elevar" not in str(d2)
    assert all(f["behavior"] == "BLOCKING" for f in para_live(d2)[0]["function_declarations"])
    assert all(f["type"] == "function" for f in para_interacciones(d2))
    assert "frase_id" in declaraciones(dos, con_voz_en_flujo=True)[0]["parameters"]["required"]
    assert "DOS brazos" in prompt_coreografo(dos, False) and "UN brazo" in prompt_coreografo(uno, False)
    assert "[y, x]" in prompt_coreografo(dos, True) and "guía de museo" in prompt_guia(dos)
    assert "prefabricado" in prompt_coreografo(dos, False)
    # Modo biblioteca (el anterior, conservado).
    b2, b1 = declaraciones(dos, composicion="biblioteca"), declaraciones(uno, composicion="biblioteca")
    assert [d["name"] for d in b2] == ["frase_de_movimiento", "gesto", "definir_gesto", "matizar", "parar", "estado"]
    gesto2 = next(d for d in b2 if d["name"] == "gesto")["parameters"]["properties"]
    gesto1 = next(d for d in b1 if d["name"] == "gesto")["parameters"]["properties"]
    assert gesto2["brazo"]["enum"] == ["izq", "der", "todos", "auto"] and "elevar" in gesto2["tipo"]["enum"]
    assert gesto1["brazo"]["enum"] == ["der"] and "trayectoria" not in gesto2["tipo"]["enum"]
    assert "GESTOS" in prompt_coreografo(dos, False, "biblioteca")


def test_er2_directo_con_error_correccion_y_reconexion():
    s = crear("dos")
    d = Director(s, VozMuda(4.6))
    estado = {"sesiones": [], "fase": 0}

    def guion(texto, respuesta):
        if texto and "explica" in texto.lower() and "Reconexión" not in texto:
            return [_llamada("frase_de_movimiento", {
                "texto": "Arriba, el sol domina la escena.", "estilo": "solemne",
                "gestos": [{"tipo": "senalar", "brazo": "der", "punto": [200, 780], "ancla": 2}]}, "c1")]
        if respuesta is not None and respuesta.name == "frase_de_movimiento":
            return [_llamada("gesto", {"tipo": "senalar", "brazo": "izq", "punto": [3000, 100]}, "c2")]   # mal
        if respuesta is not None and "error" in respuesta.response:
            assert "0 a 1000" in respuesta.response["error"]
            return [_llamada("gesto", {"tipo": "senalar", "brazo": "izq", "punto": [470, 200]}, "c3")]    # corrige
        if respuesta is not None and respuesta.name == "gesto":
            return [_texto("He señalado el sol y el árbol."), "CORTE"] if estado["fase"] == 0 else []
        if texto and "Reconexión" in texto:
            estado["fase"] = 1
            return [_texto("Sigo con la tarea.")]
        if texto and "han terminado" in texto:
            return [_texto("hecho")]
        return []

    def conectar(model, config):
        assert model == "gemini-robotics-er-2-streaming-preview" and config["response_modalities"] == ["TEXT"]
        ses = SesionFalsa(guion)
        estado["sesiones"].append((ses, config["session_resumption"]["handle"]))
        return ses

    textos = []
    agente = ER2Directo(s, d, CamaraSim(s), RegistroNulo(), al_texto=textos.append, conectar=conectar,
                        latido_s=0.05, espera_reconexion_s=0.01)

    async def prueba():
        tarea = asyncio.create_task(agente.ejecutar())
        agente.pedir("Explica el sol", urgente=True, es_tarea=True)
        await _bombear(s, lambda: "hecho" in textos)
        agente.cerrar()
        await tarea

    asyncio.run(prueba())
    assert textos == ["He señalado el sol y el árbol.", "Sigo con la tarea.", "hecho"]
    assert [ll["funcion"] for ll in agente.llamadas] == ["frase_de_movimiento", "gesto", "gesto"]
    assert "error" in agente.llamadas[1]["respuesta"] and agente.llamadas[2]["respuesta"]["estado"].startswith("aceptado")
    assert all(ll["ms"] < 800 for ll in agente.llamadas)                 # las funciones responden enseguida
    assert agente.reconexiones == 1 and len(estado["sesiones"]) == 2
    assert estado["sesiones"][1][1] == "asa-1"                           # reanuda la sesión anterior
    assert any("Reconexión" in m and "Explica el sol" in m for m in estado["sesiones"][1][0].mensajes)
    assert len(d.anclas) == 1 and not s.ocupado()
    avisos = [a for _, a in s.alertas]
    assert len(avisos) == 1 and "desconectado" in avisos[0]             # el corte se avisa; nada más falla


def test_er2_estandar_bucle_de_funciones():
    s = crear("uno", "izq")
    d = Director(s, VozMuda(4.6))
    peticiones = []

    def crear_interaccion(**k):
        peticiones.append(k)
        if len(peticiones) == 1:
            return NS(id="i1", output_text="", steps=[NS(type="function_call", id="f1", name="gesto",
                                                         arguments={"tipo": "presentar"})])
        return NS(id="i2", output_text="Listo.", steps=[])

    textos = []
    agente = ER2Estandar(s, d, CamaraSim(s), RegistroNulo(), al_texto=textos.append, crear=crear_interaccion)

    async def prueba():
        tarea = asyncio.create_task(agente.ejecutar())
        agente.pedir("Saluda", es_tarea=True)
        await _bombear(s, lambda: bool(textos))
        agente.cerrar()
        await tarea

    asyncio.run(prueba())
    assert textos == ["Listo."] and len(peticiones) == 2
    assert peticiones[0]["model"] == "gemini-robotics-er-2-preview" and peticiones[0]["input"][1]["type"] == "image"
    assert peticiones[1]["previous_interaction_id"] == "i1"
    resultado = peticiones[1]["input"][0]
    assert resultado["type"] == "function_result" and resultado["call_id"] == "f1" and "aceptado" in resultado["result"][0]["text"]
    assert peticiones[1]["input"][2]["type"] == "image"                  # imagen nueva tras el movimiento


FREC = 24000


def _voz_falsa(s, voz, frases, ritmo=2.0):
    """Genera un turno de voz: el audio llega más deprisa que el tiempo real, con su texto."""
    estado = {"i": 0, "enviado": 0.0, "t0": s.t}
    plan = []
    for texto in frases:
        for palabra in texto.split():
            plan.append((palabra + " ", 0.36))

    def paso():
        if estado["i"] >= len(plan):
            if estado["i"] == len(plan):
                voz.fin_turno(s.t)
                estado["i"] += 1
            return
        while estado["i"] < len(plan) and estado["enviado"] < (s.t - estado["t0"]) * ritmo:
            palabra, dur = plan[estado["i"]]
            voz.audio(bytes(int(dur * FREC) * 2), s.t)
            voz.transcripcion(palabra, s.t)
            estado["enviado"] += dur
            estado["i"] += 1
    return paso


def test_voz_en_flujo_gestos_sincronizados_con_el_audio():
    s = crear("dos")
    voz = VozFlujo(retardo_s=4.0)
    pendientes = []
    flujo = DirectorFlujo(s, voz, al_frase=lambda f: pendientes.append((s.t + 0.9, f)))    # ER 2 tarda 0,9 s
    frases = ["Arriba, el sol domina la escena con su luz dorada.", "Abajo descansa el lago, tranquilo y azul."]
    alimentar = _voz_falsa(s, voz, frases)
    mensajes, filas, anclados = [], [], []
    while s.t < 60:
        alimentar()
        voz.leer(int(DT * FREC), s.t)                                    # el altavoz consume audio
        for cuando, frase in [p for p in pendientes if p[0] <= s.t]:
            pendientes.remove((cuando, frase))
            mensajes.append(mensaje_frase(frase))
            objetivo = {"sol": [200, 780], "lago,": [840, 400]}
            for i, p in enumerate(frase.palabras):
                if p.texto in objetivo:
                    g = Gesto("senalar", "auto", {"punto": objetivo[p.texto], "mantener": 0.6}, ancla=i)
                    r = flujo.coreografiar(frase.id, [g])
                    assert r == {"estado": "aceptado", "programados": 1}, r
                    anclados.append((frase.id, i))
        s.avanzar(DT)
        m, _ = s.compas.posicion(s.t)
        filas.append((s.t, voz.posicion(s.t), m, s.coreos["der"].reloj.tau, s.coreos["izq"].reloj.tau))
        if s.t > 5 and not flujo.activo and not s.ocupado():
            break
    filas = np.array(filas)
    assert " ".join(f.texto for f in flujo.frases.values()) == " ".join(frases)
    assert all(len(f.palabras) <= 7 for f in flujo.frases.values())      # fragmentos cortos
    assert mensajes[0].startswith("Frase 1: \"Arriba, el sol") and "2:sol" in mensajes[0]
    assert len(flujo.anclas) == 2 and not s.alertas
    t_inicio_voz = filas[np.argmax(filas[:, 1] > 0), 0]
    assert 3.9 < t_inicio_voz - 0.3 < 4.2                                # la voz suena con el retardo previsto
    for ancla, col, (fid, i) in zip(flujo.anclas, (3, 4), anclados):
        assert ancla["apice"] <= ancla["objetivo"] + 1e-6 and not ancla["avisos"]
        palabra = flujo.frases[fid].palabras[i]
        t_palabra = filas[np.argmax(filas[:, 1] >= palabra.inicio), 0]   # cuándo suena de verdad la palabra
        t_gesto = filas[np.argmax(filas[:, col] >= ancla["apice"]), 0]   # cuándo llega de verdad el gesto
        assert -0.25 < t_gesto - t_palabra < 0.05, (t_gesto, t_palabra)  # con la palabra o un instante antes
    for n in s.nombres:
        assert s.coreos[n].gesto_actual in ("reposo", "pausa")           # al acabar la voz, vuelven al reposo


def test_voz_en_flujo_gesto_tardio_e_interrupcion():
    s = crear("dos")
    voz = VozFlujo(retardo_s=0.3)
    frases_vistas = []
    flujo = DirectorFlujo(s, voz, al_frase=frases_vistas.append)
    alimentar = _voz_falsa(s, voz, ["Arriba, el sol domina la escena.", "Abajo descansa el lago azul y tranquilo."])
    while s.t < 6.0:                                                     # la primera frase ya ha sonado
        alimentar()
        voz.leer(int(DT * FREC), s.t)
        s.avanzar(DT)
    r = flujo.coreografiar(1, [Gesto("senalar", "der", {"punto": [200, 780]}, ancla=1)])
    assert r["programados"] == 0 and r["descartados_por_llegar_tarde"] == 1
    assert "error" in flujo.coreografiar(99, [])
    flujo.interrumpir()                                                  # el visitante interrumpe
    assert not voz.pendiente() and voz.leer(240, s.t) == bytes(480)
    s.avanzar_hasta_quieto()
    assert not flujo.activo and s.coreos["izq"].gesto_actual in ("reposo", "pausa")


# ------------------------------------------------------------------ movimiento compuesto por ER 2
def test_er2_compone_el_movimiento_punto_a_punto():
    from so101er.agente.herramientas import ejecutar_llamada
    s = crear("dos")
    d = Director(s, VozMuda(4.6))
    # "Arriba, el sol domina la escena con su luz dorada." → 2:sol, 7:luz
    r = ejecutar_llamada(s, d, "frase_de_movimiento", {
        "texto": "Arriba, el sol domina la escena con su luz dorada.",
        "movimientos": [
            {"brazo": "der", "estilo": "solemne", "puntos": [
                {"alcance": 0.4, "altura": 0.5, "lado": 10, "pinza": 30},           # preparación
                {"mira": [200, 780], "ancla": 2, "pausa": 0.4},                      # llega al sol en "sol"
                {"alcance": 0.7, "altura": 0.95, "inclinacion": 40, "pinza": 95, "ancla": 7}]},   # se abre en "luz"
            {"brazo": "izq", "caracter": {"tiempo": -0.8}, "puntos": [
                {"mira": [620, 60], "ancla": 3}, {"mira": [380, 250]}, {"mira": [560, 450]}]},     # traza las montañas
        ]})
    assert r == {"estado": "aceptado, en cola", "movimientos": 2}, r
    filas, rastro, cima = [], [], (0.0, 0.0)
    while d.activo or s.ocupado():
        s.avanzar(DT)
        m, _ = s.compas.posicion(s.t)
        filas.append((s.t, m, s.coreos["der"].reloj.tau))
        rastro.append(s.apunta("izq", s.coreos["izq"].linea.valor(s.coreos["izq"].reloj.tau)))
        cmd = s.coreos["der"].cmd
        cima = max(cima, (cmd[5], s.marcos["der"].a_mundo(s.modelo.punta(cmd[:5])[0])[2]))
        assert s.t < 60
    assert not s.alertas and len(d.anclas) == 2
    der = next(a for a in d.anclas if a["brazo"] == "der")
    assert der["apice"] <= der["objetivo"] + 1e-6 and der["objetivo"] - der["apice"] < 0.2    # llega en "sol"
    # El brazo izquierdo ha recorrido la línea quebrada: pasa cerca de sus tres vértices, en orden.
    rastro = np.array([p for p in rastro if p is not None])
    cerca = [int(np.argmin(np.linalg.norm(rastro - v, axis=1))) for v in ([620, 60], [380, 250], [560, 450])]
    dist = [float(np.linalg.norm(rastro[i] - v)) for i, v in zip(cerca, ([620, 60], [380, 250], [560, 450]))]
    assert cerca == sorted(cerca) and max(dist) < 60, (cerca, dist)
    # El brazo derecho llega arriba y abierto, como se pidió, antes de volver al reposo.
    assert cima[0] > 85 and cima[1] > 300, cima


def test_varios_puntos_anclados_ajustan_el_ritmo():
    s = crear("dos")
    base = {"puntos": [{"mira": [300, 700]}, {"alcance": 0.6, "altura": 0.9, "pinza": 90}]}
    natural = s.planificar_solo(Gesto("trayectoria", "der", dict(base)), "der")
    lento = s.planificar_solo(Gesto("trayectoria", "der", {**base, "_tiempos": {0: 0.0, 1: 4.0}}), "der")
    assert lento.fin > natural.fin + 1.0                      # el segundo punto espera a su palabra
    assert abs(lento.apice - natural.apice) < 0.05            # el primero no cambia


def test_errores_de_un_movimiento_compuesto():
    from so101er.agente.herramientas import ejecutar_llamada
    s = crear("uno", "izq")
    casos = [
        ({"brazo": "izq", "puntos": []}, "de 1 a 16 puntos"),
        ({"brazo": "izq", "puntos": [{"mira": [1500, 10]}]}, "0 a 1000"),
        ({"brazo": "izq", "puntos": [{"pausa": 1}]}, "indica 'mira'"),
        ({"brazo": "izq", "puntos": [{"altura": 3}]}, "entre 0 y 1"),
        ({"brazo": "izq", "puntos": [{"mira": [500, 300], "color": 1}]}, "campos desconocidos"),
        ({"brazo": "der", "puntos": [{"mira": [500, 300]}]}, "solo existe 'izq'"),
        ({"brazo": "izq", "puntos": [{"mira": [500, 300]}], "velocidad": 2}, "campos desconocidos"),
    ]
    for args, texto in casos:
        r = ejecutar_llamada(s, None, "movimiento", args)
        assert "error" in r and texto in r["error"], (args, r)
    r = ejecutar_llamada(s, Director(s, VozMuda(4.6)), "frase_de_movimiento",
                         {"texto": "Hola a todos.", "movimientos": [{"brazo": "izq", "puntos": [{"mira": [9000, 1]}]}]})
    assert "error" in r and "0 a 1000" in r["error"]          # se avisa al llamar, no más tarde
    assert ejecutar_llamada(s, None, "movimiento", {"brazo": "izq", "puntos": [{"mira": [500, 300]}]})["estado"].startswith("aceptado")


# ------------------------------------------------------------------ los dos brazos de una persona
def _manos(s):
    return {n: s.marcos[n].a_mundo(s.modelo.punta(s.coreos[n].linea.valor(s.coreos[n].reloj.tau)[:5])[0])
            for n in s.nombres}


def test_las_dos_manos_se_separan_como_las_de_una_persona():
    from so101er.agente.herramientas import ejecutar_llamada
    s = crear("dos")
    r = ejecutar_llamada(s, None, "movimiento", {"brazo": "ambos", "estilo": "sereno", "puntos": [
        {"separacion": 0.05, "altura": 0.4, "adelante": 0.3, "pinza": 30, "pausa": 0.5},
        {"separacion": 1.0, "altura": 0.8, "adelante": 0.8, "pinza": 100}]})
    assert r["estado"].startswith("aceptado") and {b["brazo"] for b in r["brazos"]} == {"izq", "der"}, r
    distancias, alturas = [], []
    while s.ocupado():
        s.avanzar(DT)
        m = _manos(s)
        distancias.append(float(np.linalg.norm(m["izq"] - m["der"])))
        alturas.append((m["izq"][2], m["der"][2]))
    assert min(distancias) < 130 and distancias[-1] > 600          # juntas en el centro → abiertas del todo
    assert max(abs(a - b) for a, b in alturas) < 25                 # a la vez y a la misma altura: en espejo
    assert not s.alertas


def test_una_mano_quieta_y_la_otra_girando():
    from so101er.agente.herramientas import ejecutar_llamada
    s = crear("dos")
    r = ejecutar_llamada(s, None, "movimiento", {"brazo": "izq", "puntos": [{"mira": [450, 200], "pausa": 6}]})
    assert r["estado"].startswith("aceptado")
    r = ejecutar_llamada(s, None, "movimiento", {"brazo": "der", "puntos": [
        {"alcance": 0.6, "altura": 0.7, "lado": 20, "pinza": 60,
         "circulo": {"plano": "horizontal", "radio": 0.6, "vueltas": 2}}]})
    assert r["estado"].startswith("aceptado"), r
    for _ in range(350):                                            # los dos llegan a su sitio
        s.avanzar(DT)
    izq, der = [], []
    while s.coreos["der"].ocupado():
        s.avanzar(DT)
        m = _manos(s)
        izq.append(m["izq"])
        der.append(m["der"])
    izq, der = np.array(izq), np.array(der)
    assert np.ptp(izq, axis=0).max() < 12                           # la izquierda, quieta
    assert np.ptp(der[:, 0]) > 120 and np.ptp(der[:, 1]) > 120      # la derecha, girando en horizontal…
    assert np.ptp(der[:, 2]) < 40                                   # …sin cambiar de altura
    assert not s.alertas


def test_repetir_un_ciclo_y_errores_a_dos_manos():
    from so101er.agente.herramientas import ejecutar_llamada
    s = crear("dos")
    uno = s.planificar_solo(Gesto("trayectoria", "der", {"puntos": [{"altura": 0.8}, {"altura": 0.2}]}), "der")
    tres = s.planificar_solo(Gesto("trayectoria", "der", {"puntos": [{"altura": 0.8}, {"altura": 0.2}],
                                                          "repetir": 3}), "der")
    assert tres.fin > 2.2 * uno.fin
    r = ejecutar_llamada(s, None, "movimiento", {"brazo": "der", "puntos": [{"separacion": 0.5}]})
    assert "solo valen con brazo 'ambos'" in r["error"]
    r = ejecutar_llamada(crear("uno", "izq"), None, "movimiento", {"brazo": "ambos", "puntos": [{"separacion": 0.5}]})
    assert "solo existe 'izq'" in r["error"]
    r = ejecutar_llamada(s, None, "movimiento", {"brazo": "der", "puntos": [
        {"altura": 0.5, "circulo": {"plano": "diagonal"}}]})
    assert "'plano' debe ser" in r["error"]


def test_un_brazo_arrastra_un_poco_al_otro():
    s = crear("dos")
    antes = s.coreos["der"].cmd.copy()
    s.ejecutar(Gesto("trayectoria", "izq", {"puntos": [{"alcance": 0.9, "altura": 0.95, "lado": 60}], "mantener": 3}))
    for _ in range(400):
        s.avanzar(DT)
    movido = np.abs(s.coreos["der"].simpatia[:3]).max()
    assert 1.0 < movido < 8.0                                       # se nota, pero es pequeño
    assert np.abs(s.coreos["der"].cmd - antes)[:3].max() < 12 and not s.alertas
