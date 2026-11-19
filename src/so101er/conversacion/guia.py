"""La conversación: une el chatbot (qué se dice), la voz, ER 2 (las manos) y los brazos.

Reparto, deliberadamente simple:
- El **chatbot** ve la foto y decide qué decir: describir la obra, volver a un detalle o
  contestar una pregunta. Su texto va a la voz según lo escribe.
- **ER 2** recibe lo mismo (la pregunta, en cuanto se oye, y cada frase del guía, en cuanto
  se escribe) y compone el movimiento de los brazos, con la palabra en la que debe coincidir.
- **Este módulo** ancla cada gesto al instante exacto en que suena su palabra (la voz da el
  tiempo de cada una), marca el ritmo con acentos y corta todo si el visitante vuelve a hablar.

Estados: reposo → escuchando (barra pulsada) → pensando → hablando → reposo.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
from typing import Any, Callable

from ..control.gestos import ErrorGesto, Gesto
from ..sincronia.partitura import VACIAS, contar_silabas
from .manos import a_puntos_clave

_CORTE = re.compile(r"[.!?…]+[\"»”)]*(?=\s)")        # fin de frase seguido de espacio
_LIMPIAR = re.compile(r"[*_#`~>|\[\]{}<>]")


def normalizar(palabra: str) -> str:
    """Minúsculas, sin tildes ni signos: para comparar palabras."""
    base = unicodedata.normalize("NFKD", palabra.lower())
    return "".join(c for c in base if c.isalnum())


class Conversacion:
    def __init__(self, sistema: Any, voz: Any, cerebro: Any, manos: Any, registro: Any,
                 al_decir: Callable[[str], None] | None = None, clave_oido: str = "", micro: Any = None,
                 crear_transcriptor: Callable[[], Any] | None = None) -> None:
        self.s, self.voz, self.cerebro, self.manos, self.registro = sistema, voz, cerebro, manos, registro
        self.al_decir = al_decir or (lambda texto: None)
        self.micro, self._crear_transcriptor = micro, crear_transcriptor
        self.adelanto = float(sistema.cfg.voz["adelanto_gesto_s"]) + float(sistema.cfg.voz["compensacion_s"])
        self.estado = "reposo"
        self.turno = 0
        self._cortar = threading.Event()
        self._cerrojo = threading.RLock()
        self._pendientes: list[dict] = []        # gestos de ER 2 que esperan a su palabra
        self._siguiendo = False
        self._m_base = 0.0
        self._acentos_desde = 0
        self._t_fin: float | None = None
        self._reposar = False
        self._transcriptor: Any = None
        self._fin = threading.Event()
        self.tiempos: list[dict] = []            # medidas por turno, para ver la latencia
        self._t_pregunta = 0.0
        if manos is not None:
            manos.al_gesto = self._gesto_de_er2
        threading.Thread(target=self._bucle, name="conversacion", daemon=True).start()

    # ------------------------------------------------------------ pulsar para hablar
    def pulsar(self) -> None:
        """Barra abajo: si el guía está hablando, se calla; empieza a escuchar."""
        if self.micro is None or self._crear_transcriptor is None:
            return
        self.interrumpir(reposo=False)
        with self._cerrojo:
            self.estado = "escuchando"
            self._transcriptor = self._crear_transcriptor()
        self.micro.empezar(self._transcriptor.enviar_audio)
        self.voz.conectar_en_segundo_plano()
        threading.Thread(target=self.cerebro.calentar, daemon=True).start()
        self.al_decir("  (escuchando…)")

    def soltar(self) -> None:
        """Barra arriba: se transcribe lo dicho y se responde."""
        with self._cerrojo:
            transcriptor, self._transcriptor = self._transcriptor, None
        if transcriptor is None:
            return
        self._t_pregunta = time.perf_counter()
        self.micro.parar()
        texto = transcriptor.confirmar()
        if transcriptor.error:
            self.s.registrar(transcriptor.error, alerta=True)
        if len(normalizar(texto)) < 2:
            with self._cerrojo:
                self.estado = "reposo"
            self.al_decir("  (no te he entendido)")
            return
        self.preguntar(texto, medir_desde=self._t_pregunta)

    # ------------------------------------------------------------ turno
    def preguntar(self, texto: str, medir_desde: float | None = None) -> None:
        """Lanza una respuesta (desde el micrófono o escrita). Vuelve enseguida."""
        self.interrumpir(reposo=False)
        with self._cerrojo:
            self.turno += 1
            turno = self.turno
            self._cortar = threading.Event()
            self.estado = "pensando"
            self._pendientes.clear()
            self._acentos_desde = 0
            self._t_fin, self._reposar = None, True
        self.al_decir(f"\n> {texto}")
        self.registro.evento("visitante", texto=texto)
        threading.Thread(target=self._responder, args=(texto, turno, self._cortar, medir_desde or time.perf_counter()),
                         name="respuesta", daemon=True).start()

    def _responder(self, texto: str, turno: int, cortar: threading.Event, t0: float) -> None:
        medida = {"turno": turno, "pregunta": texto}
        self.tiempos.append(medida)
        self.voz.empezar_turno()
        if self.manos is not None:
            self.manos.cancelar(turno)
            # ER 2 empieza a la vez que el chatbot: reacciona a la pregunta sin esperar a la respuesta.
            # Su gesto se coloca al principio de la respuesta (los primeros 110 caracteres).
            self.manos.pedir(f"El visitante dice: «{texto}»", turno, (0, 110))
        frase, n_frases = "", 0

        def al_texto(trozo: str) -> None:
            nonlocal frase, n_frases
            if cortar.is_set():
                return
            if "primer_texto_s" not in medida:
                medida["primer_texto_s"] = round(time.perf_counter() - t0, 2)
            trozo = _LIMPIAR.sub("", trozo)
            frase += trozo
            completas = list(_CORTE.finditer(frase))
            primera_pausa = (n_frases == 0 and not completas and not medida.get("arrancada")
                             and len(frase) >= 24 and frase.rstrip()[-1:] in ",;:")
            if primera_pausa:
                medida["arrancada"] = True
            self.voz.enviar(trozo, flush=bool(completas) or primera_pausa)
            base = self.voz.letras_enviadas - len(frase)        # posición de `frase` en el texto de la voz
            inicio = 0
            for corte in completas:                 # cada frase terminada, por separado
                una = frase[inicio:corte.end()].strip()
                rango = (base + inicio, base + corte.end())
                inicio = corte.end()
                if not una:
                    continue
                n_frases += 1
                self.al_decir(f"  « {una} »")
                self.registro.evento("guia_dice", texto=una)
                if self.manos is not None and n_frases > 1:
                    self.manos.pedir(f"El guía dice: «{una}»", turno, rango)
            frase = frase[inicio:]

        try:
            self.cerebro.responder(texto, al_texto, cortar)
        except Exception as e:
            self.s.registrar(str(e), alerta=True)
        if cortar.is_set():
            return
        if frase.strip():
            n_frases += 1
            self.al_decir(f"  « {frase.strip()} »")
            self.registro.evento("guia_dice", texto=frase.strip())
            if self.manos is not None and n_frases > 1:
                fin = self.voz.letras_enviadas
                self.manos.pedir(f"El guía dice: «{frase.strip()}»", turno, (fin - len(frase), fin))
        self.voz.fin_texto()
        limite = time.perf_counter() + 8.0
        while self.voz.t_primer_audio is None and time.perf_counter() < limite and not cortar.is_set():
            time.sleep(0.02)
        if self.voz.t_primer_audio is not None:
            medida["primer_sonido_s"] = round(self.voz.t_primer_audio - t0, 2)
        self.registro.evento("tiempos", **medida)

    def interrumpir(self, reposo: bool = True) -> None:
        """Corta la respuesta en curso: la voz se calla y los brazos dejan lo que quedaba por hacer."""
        with self._cerrojo:
            estaba = self.estado
            self._cortar.set()
            self.turno += 1
            self._pendientes.clear()
            self._reposar = False
            self.estado = "reposo"
        if estaba in ("pensando", "hablando"):
            self.voz.interrumpir()
            if self.manos is not None:
                self.manos.cancelar(self.turno)
            if self._siguiendo:
                self.s.compas.liberar(self.s.ahora())
                self._siguiendo = False
            self.registro.evento("interrumpido")
            if reposo:
                self._al_reposo()

    def _al_reposo(self) -> None:
        try:
            self.s.reposo()
        except ErrorGesto as e:
            self.s.registrar(f"no se pudo ir al reposo: {e}", alerta=True)

    # ------------------------------------------------------------ gestos de ER 2
    def _gesto_de_er2(self, args: dict, turno: int) -> None:
        """Llega un movimiento compuesto por ER 2 (desde su hilo)."""
        puntos = a_puntos_clave(args.get("puntos"))
        brazo = str(args.get("brazo", ""))
        if turno != self.turno or not puntos or brazo not in self.s.nombres:
            return
        self.registro.evento("er2_gesto", brazo=brazo, puntos=args.get("puntos"), palabra=args.get("palabra"),
                             latencia_s=round(self.manos.latencias[-1], 2) if self.manos.latencias else None)
        with self._cerrojo:
            self._pendientes.append({"brazo": brazo, "puntos": puntos, "palabra": normalizar(str(args.get("palabra", ""))),
                                     "llegada": time.perf_counter(), "turno": turno, "rango": args.get("rango")})

    def _colocar_gestos(self, t: float) -> None:
        """Ancla cada gesto pendiente a la próxima vez que suene su palabra."""
        if not self._pendientes:
            return
        pos = self.voz.posicion(t)
        for g in list(self._pendientes):
            edad = time.perf_counter() - g["llegada"]
            if not self._siguiendo and self.voz.pendiente() and edad < 4.0:
                continue                        # la voz aún no ha arrancado: se coloca en cuanto suene
            cuando, rango = None, g.get("rango")
            if self._siguiendo:
                hallado = self.voz.cuando(g["palabra"], pos + 0.2, normalizar, rango)
                cuando = hallado[0] if hallado else None
                texto_listo = rango is not None and self.voz.letras_enviadas >= rango[1]
                if cuando is None and rango is not None and (texto_listo or edad >= 2.5):
                    # Su palabra no está en la frase: el gesto acompaña el comienzo de esa frase.
                    comienzo = self.voz.tiempo_de(rango[0]) + 0.6
                    cuando = comienzo if comienzo >= pos + 0.2 else None
                elif cuando is None and edad < 2.5 and self.voz.estado != "terminada" and g["palabra"]:
                    continue                    # aún puede llegar el texto con su palabra
            self._pendientes.remove(g)
            m_apice = (self._m_base + cuando - self.adelanto) if (cuando is not None and self._siguiendo) else None
            gesto = Gesto("trayectoria", g["brazo"], {"puntos": g["puntos"], "mantener": 0.4})
            try:
                r = self.s.ejecutar(gesto, m_apice=m_apice, reemplazar=True)
                b = r["brazos"][0]
                self.registro.evento(
                    "gesto_colocado", brazo=g["brazo"], palabra=g["palabra"], anclado=m_apice is not None,
                    margen_s=round(cuando - pos, 2) if cuando is not None else None,
                    retraso_s=round(b["apice"] - m_apice, 2) if m_apice is not None else None)
            except ErrorGesto as e:
                self.registro.evento("gesto_rechazado", motivo=str(e))

    def _acentos(self, t: float) -> None:
        """Pequeños impulsos de ritmo en las palabras con contenido, a partir de los tiempos de la voz."""
        palabras = self.voz.palabras
        m_ahora, _ = self.s.compas.posicion(t)
        while self._acentos_desde < len(palabras):
            texto, inicio = palabras[self._acentos_desde]
            m = self._m_base + inicio - self.adelanto
            if m > m_ahora + 0.3:
                break
            self._acentos_desde += 1
            limpia = normalizar(texto)
            if (m > m_ahora - 0.1 and limpia not in VACIAS and contar_silabas(texto) >= 3
                    and inicio - getattr(self, "_ultimo_acento", -9.0) > 1.1):
                self._ultimo_acento = inicio
                self.s.acento(m, fuerza=0.9)

    # ------------------------------------------------------------ ciclo
    def _bucle(self) -> None:
        while not self._fin.is_set():
            try:
                self._paso(self.s.ahora())
            except Exception as e:
                self.s.registrar(f"error en la conversación: {type(e).__name__}: {e}", alerta=True)
            time.sleep(0.02)

    def _paso(self, t: float) -> None:
        with self._cerrojo:
            voz, s = self.voz, self.s
            if voz.sonando and not self._siguiendo:           # la voz empieza: el compás la sigue
                m, _ = s.compas.posicion(t)
                self._m_base = m - voz.posicion(t)
                s.compas.seguir(voz, self._m_base)
                self._siguiendo = True
                self._ultimo_acento = -9.0
                if self.estado == "pensando":
                    self.estado = "hablando"
            elif self._siguiendo and not voz.sonando:         # la voz ha terminado
                s.compas.liberar(t)
                self._siguiendo = False
                self._t_fin = t
                if self.estado == "hablando":
                    self.estado = "reposo"
            if self.estado in ("pensando", "hablando"):
                self._colocar_gestos(t)
                if self._siguiendo:
                    self._acentos(t)
            if (self._reposar and self._t_fin is not None and t - self._t_fin > 1.5 and not s.ocupado()
                    and self.estado == "reposo"):
                self._reposar = False
                self._al_reposo()

    @property
    def activa(self) -> bool:
        return self.estado != "reposo" or self.voz.pendiente() or self.s.ocupado()

    def cerrar(self) -> None:
        self._fin.set()
        self.interrumpir(reposo=False)
