"""La conversación sin red: chatbot, voz y ER 2 sustituidos por dobles."""
import threading
import time

import numpy as np

from conftest import crear
from so101er.conversacion.guia import Conversacion, normalizar
from so101er.conversacion.manos import a_puntos_clave
from so101er.conversacion.voz_eleven import VozEleven
from so101er.interfaz.registro import RegistroNulo


def test_formato_compacto_de_er2():
    puntos = a_puntos_clave([[200, 780], [0.7, 0.9, 40, 100], [5000, -3], "x", [1, 2, 3]])
    assert puntos == [{"mira": [200.0, 780.0]}, {"alcance": 0.7, "altura": 0.9, "lado": 40.0, "pinza": 100.0},
                      {"mira": [1000.0, 0.0]}]
    assert a_puntos_clave([[300, 400]]) == [{"mira": [300.0, 400.0], "pausa": 0.6}]     # señalar y sostener
    assert normalizar("¡Árbol,") == "arbol" and normalizar("El SOL.") == "elsol"


def _voz_con_texto(texto, alineado_hasta=0, ritmo=15.0):
    """Una voz con texto enviado y, opcionalmente, parte de su audio ya recibido."""
    voz = VozEleven("clave", "voz", "es")
    voz.empezar_turno()
    voz._texto = texto
    pos = 0
    for palabra in texto[:alineado_hasta].split(" "):
        if palabra:
            voz.palabras.append((palabra, pos / ritmo))
            voz._pos_palabras.append(pos)
        pos += len(palabra) + 1
    voz._alineados = alineado_hasta
    voz._base_al = alineado_hasta / ritmo
    return voz


def test_cuando_suena_una_palabra_real_o_estimada():
    texto = "Arriba brilla el sol. Abajo descansa el lago. Y arriba, otra vez, el sol. "
    voz = _voz_con_texto(texto, alineado_hasta=22)                  # solo ha llegado el audio de la 1.ª frase
    t, exacto = voz.cuando("sol", 0.0, normalizar)
    assert exacto and abs(t - 17 / 15) < 1e-6                        # tiempo real
    t, exacto = voz.cuando("lago", 0.0, normalizar)
    assert not exacto and abs(t - texto.index("lago") / 15) < 0.05   # estimado por posición y ritmo
    # Limitado a su frase: no se ancla al "sol" de la última frase si se busca en la segunda.
    segunda = (22, 47)
    assert voz.cuando("sol", 0.0, normalizar, segunda) is None
    t, _ = voz.cuando("sol", 2.0, normalizar)
    assert t > 4.0                                                   # sin límite, encontraría el último
    assert abs(voz.tiempo_de(22) - 22 / 15) < 1e-6 and voz.tiempo_de(5) == 0.0


class VozFalsa:
    """Voz sin sonido que avanza en tiempo real: cada palabra dura 0,3 s."""

    def __init__(self):
        self.estado, self.t0, self.palabras, self._texto = "inactiva", None, [], ""
        self.t_primer_audio = None
        self.interrumpida = False

    letras_enviadas = property(lambda self: len(self._texto))
    sonando = property(lambda self: self.estado == "hablando")

    def empezar_turno(self):
        self.palabras, self._texto, self.t0, self.estado, self.interrumpida = [], "", None, "esperando", False

    def enviar(self, texto, flush=False):
        for palabra in texto.split():
            self.palabras.append((palabra, 0.3 * len(self.palabras)))
        self._texto += texto
        if self.t0 is None and self.palabras:
            self.t0 = self.t_primer_audio = time.perf_counter()
            self.estado = "hablando"

    def fin_texto(self):
        pass

    def posicion(self, t):
        if self.t0 is None:
            return 0.0
        pos = time.perf_counter() - self.t0
        if self.estado == "hablando" and pos > 0.3 * len(self.palabras):
            self.estado = "terminada"
        return min(pos, 0.3 * len(self.palabras))

    def pendiente(self):
        return self.estado in ("esperando", "hablando")

    def cuando(self, palabra, desde, normalizar_, rango=None):
        for texto, inicio in self.palabras:
            if inicio >= desde and palabra and palabra in normalizar_(texto):
                return inicio, True
        return None

    def tiempo_de(self, c):
        return 0.0

    def interrumpir(self):
        self.estado, self.interrumpida = "inactiva", True

    def conectar_en_segundo_plano(self):
        pass


class CerebroFalso:
    idioma = "es"

    def __init__(self, respuesta, pausa=0.0):
        self.respuesta, self.pausa = respuesta, pausa

    def calentar(self):
        pass

    def responder(self, texto, al_texto, cortar):
        for palabra in self.respuesta.split(" "):
            if cortar.is_set():
                break
            al_texto(palabra + " ")
            time.sleep(self.pausa)
        return self.respuesta


class ManosFalsas:
    """Responde a la pregunta con un gesto del brazo derecho, tras 0,2 s."""

    def __init__(self):
        self.latencias, self.pedidos, self.al_gesto, self.turno = [0.2], [], None, 0

    def pedir(self, texto, turno, rango=None):
        self.pedidos.append(texto)
        if texto.startswith("El visitante"):
            threading.Timer(0.2, lambda: self.al_gesto(
                {"brazo": "der", "puntos": [[200, 780]], "palabra": "sol", "rango": rango}, turno)).start()

    def cancelar(self, turno):
        self.turno = turno


def _montar(respuesta, pausa=0.0):
    s = crear("dos")
    s.iniciar()
    voz, manos = VozFalsa(), ManosFalsas()
    conv = Conversacion(s, voz, CerebroFalso(respuesta, pausa), manos, RegistroNulo())
    return s, voz, manos, conv


def _esperar(condicion, maximo=8.0):
    limite = time.perf_counter() + maximo
    while not condicion() and time.perf_counter() < limite:
        time.sleep(0.02)
    return condicion()


def test_el_gesto_de_er2_llega_con_su_palabra():
    s, voz, manos, conv = _montar("Arriba a la derecha, en lo alto del cielo, brilla el sol amarillo.")
    try:
        conv.preguntar("¿Qué es eso amarillo?")
        assert _esperar(lambda: s.coreos["der"].ocupado())           # ER 2 ha movido el brazo derecho
        assert manos.pedidos[0].startswith("El visitante dice")
        t_sol = next(t for p, t in voz.palabras if "sol" in p)       # cuándo suena «sol»
        # El brazo llega a apuntar al sol alrededor de esa palabra.
        apunta = lambda: s.apunta("der", s.coreos["der"].cmd)
        assert _esperar(lambda: apunta() is not None and np.linalg.norm(np.array(apunta()) - [200, 780]) < 60)
        llegada = time.perf_counter() - voz.t0
        assert abs(llegada - t_sol) < 0.6, (llegada, t_sol)
        assert _esperar(lambda: not conv.activa, 15.0) and not s.alertas
    finally:
        conv.cerrar()
        s.cerrar(ir_a_reposo=False)


def test_hablarle_interrumpe_la_voz_y_empieza_otra_respuesta():
    s, voz, manos, conv = _montar("Una frase muy larga. " * 12, pausa=0.05)
    try:
        conv.preguntar("Describe el cuadro")
        assert _esperar(lambda: conv.estado == "hablando")
        turno = conv.turno
        conv.interrumpir()                                           # como al pulsar la barra espaciadora
        assert voz.interrumpida and conv.estado == "reposo" and conv.turno > turno
        conv.cerebro.respuesta, conv.cerebro.pausa = "Es el sol.", 0.0
        conv.preguntar("¿Y eso?")
        assert _esperar(lambda: any("sol" in p for p, _ in voz.palabras))
        assert sum("sol" in p for p, _ in voz.palabras) == 1 and len(voz.palabras) == 3    # solo la respuesta nueva
    finally:
        conv.cerrar()
        s.cerrar(ir_a_reposo=False)
