"""Director: coordina la voz y los gestos de una partitura, frase a frase.

Para cada frase prepara la voz, planifica los gestos de modo que su ápice
caiga en la palabra ancla (un instante antes), los verifica, los programa en
el compás y arranca la voz. Mientras la voz habla, el compás la sigue.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import replace
from typing import Any

from ..control.cualidades import dinamica
from ..control.gestos import ErrorGesto, Gesto, preparar_anclas
from .partitura import Frase, Partitura, acentos_automaticos


class Director:
    def __init__(self, sistema: Any, voz: Any) -> None:
        self.sistema = sistema
        self.voz = voz
        cfg = sistema.cfg.voz
        self.adelanto = float(cfg["adelanto_gesto_s"]) + float(cfg["compensacion_s"])
        self.pausa = float(cfg["pausa_entre_frases_s"])
        self.espera_cuerpo = float(cfg["espera_al_cuerpo_s"])
        self.entrada_max = float(cfg["entrada_max_s"])
        self.cola: deque[Frase] = deque()
        self.fase = "inactivo"        # inactivo | preparado | hablando | pausa
        self.frase: Frase | None = None
        self.m_voz = 0.0              # posición del compás en la que empieza la voz
        self._t_pausa = 0.0
        self._acentos: list[float] = []
        self._fuerza_acento = 1.0
        self._hay_que_reposar = False
        self.anclas: list[dict] = []  # registro para medir la sincronía
        self._cerrojo = threading.RLock()
        self._hilo: threading.Thread | None = None
        self._fin = threading.Event()
        sistema.director = self

    # ------------------------------------------------------------ órdenes
    def interpretar(self, partitura: Partitura) -> None:
        with self._cerrojo:
            self.cola.extend(partitura.frases)
            self._hay_que_reposar = True
        if hasattr(self.voz, "precalentar"):
            for frase in partitura.frases:
                self.voz.precalentar(frase.texto)

    def decir(self, texto: str, gestos: list[Gesto] | None = None, estilo: str | None = None) -> None:
        self.interpretar(Partitura([Frase(texto=texto, gestos=gestos or [], estilo=estilo)]))

    def interrumpir(self) -> None:
        """La voz se corta (p. ej. un visitante pregunta): los brazos se recogen al reposo."""
        with self._cerrojo:
            t = self.sistema.ahora()
            self.cola.clear()
            if self.fase in ("preparado", "hablando", "sintetizando"):
                self.voz.interrumpir(t)
                self.sistema.compas.liberar(t)
            self.fase = "inactivo"
            self.frase = None
            self._acentos = []
            self._hay_que_reposar = False
        self.sistema.registrar("voz interrumpida: brazos al reposo")
        try:
            self.sistema.reposo()
        except ErrorGesto as e:
            self.sistema.registrar(f"no se pudo ir al reposo: {e}", alerta=True)

    @property
    def activo(self) -> bool:
        return self.fase != "inactivo" or bool(self.cola) or self._hay_que_reposar

    # ------------------------------------------------------------ ciclo
    def paso(self, t: float) -> None:
        pendiente = None
        with self._cerrojo:
            if self.fase == "inactivo" and self.cola:
                pendiente = self.cola.popleft()
                self.fase = "sintetizando"
        if pendiente is not None:
            palabras, duracion = self.voz.preparar(pendiente)       # puede tardar: sin cerrojo
            with self._cerrojo:
                if self.fase == "sintetizando":                     # si no se ha interrumpido entretanto
                    pendiente.palabras, pendiente.duracion = palabras, duracion
                    self._preparar(pendiente, self.sistema.ahora())
            return
        with self._cerrojo:
            s = self.sistema
            if self.fase == "inactivo":
                if self.cola:
                    pass
                elif self._hay_que_reposar and not s.ocupado():
                    self._hay_que_reposar = False
                    try:
                        s.reposo()
                    except ErrorGesto as e:
                        s.registrar(f"no se pudo ir al reposo: {e}", alerta=True)
            elif self.fase == "preparado":
                m, _ = s.compas.posicion(t)
                if m >= self.m_voz:
                    self.voz.iniciar(t)
                    s.compas.seguir(self.voz, self.m_voz)
                    self.fase = "hablando"
            elif self.fase == "hablando":
                m, _ = s.compas.posicion(t)
                while self._acentos and self._acentos[0] <= m + 0.25:
                    s.acento(self._acentos.pop(0), fuerza=self._fuerza_acento)
                if self.voz.estado == "terminada":
                    s.compas.liberar(t)
                    self.fase = "pausa"
                    pausa = self.frase.pausa if self.frase and self.frase.pausa is not None else self.pausa
                    self._t_pausa = t + pausa
                elif self.voz.estado == "interrumpida":
                    self.interrumpir()
            elif self.fase == "pausa" and t >= self._t_pausa and (
                    not s.ocupado() or t >= self._t_pausa + self.espera_cuerpo):
                self.fase = "inactivo"

    def _preparar(self, frase: Frase, t: float) -> None:
        s = self.sistema
        self.frase = frase
        m_ahora, _ = s.compas.posicion(t)
        # Ápice de cada gesto, relativo al inicio de la voz.
        tiempos = []
        ultima = max(len(frase.palabras) - 1, 0)
        for g in frase.gestos:
            preparar_anclas(g, lambda i: frase.palabras[min(max(int(i), 0), ultima)].inicio if frase.palabras else 0.0)
            if g.t is not None:
                rel = float(g.t)
            elif g.ancla is not None and 0 <= int(g.ancla) < len(frase.palabras):
                rel = frase.palabras[int(g.ancla)].inicio
            else:
                rel = 0.0
            tiempos.append(rel - self.adelanto)
        orden = sorted(range(len(frase.gestos)), key=lambda i: tiempos[i])
        # La preparación del primer gesto ocurre antes de que suene su palabra:
        # si no cabe, la voz empieza un poco más tarde.
        entrada = 0.05
        if orden:
            primero = frase.gestos[orden[0]]
            try:
                nombres = s.resolver_brazos(primero)
                plan = s.planificar_solo(self._con_estilo(primero, frase), nombres[0])
                entrada = max(entrada, plan.apice - tiempos[orden[0]] + 0.05)
            except ErrorGesto:
                pass
        self.m_voz = m_ahora + min(entrada, self.entrada_max)
        con_movimiento: set[str] = set()
        for i in orden:
            g = self._con_estilo(frase.gestos[i], frase)
            try:
                brazos = set(s.resolver_brazos(g))
                primero_del_brazo = not brazos <= con_movimiento
                con_movimiento |= brazos
                r = s.ejecutar(g, m_apice=self.m_voz + tiempos[i], reemplazar=primero_del_brazo)
                for b in r["brazos"]:
                    self.anclas.append({"gesto": b["gesto"], "brazo": b["brazo"], "apice": b["apice"],
                                        "objetivo": self.m_voz + tiempos[i] + self.adelanto})
            except ErrorGesto as e:
                s.registrar(f"gesto omitido en \"{frase.texto[:30]}…\": {e}", alerta=True)
        indices = frase.acentos if frase.acentos is not None else acentos_automaticos(frase.palabras)
        self._acentos = sorted(self.m_voz + frase.palabras[i].inicio - self.adelanto
                               for i in indices if 0 <= i < len(frase.palabras))
        try:
            self._fuerza_acento = dinamica(s.cfg.estilo(frase.estilo)).acento
        except Exception:
            self._fuerza_acento = 1.0
        self.fase = "preparado"
        s.registrar(f"frase: \"{frase.texto}\"")

    @staticmethod
    def _con_estilo(g: Gesto, frase: Frase) -> Gesto:
        return g if g.estilo or not frase.estilo else replace(g, estilo=frase.estilo)

    # ------------------------------------------------------------ tiempo real
    def iniciar(self, periodo: float = 0.02) -> None:
        def bucle() -> None:
            while not self._fin.is_set():
                try:
                    self.paso(self.sistema.ahora())
                except Exception as e:
                    self.sistema.registrar(f"error en el director: {e}", alerta=True)
                time.sleep(periodo)
        self._fin.clear()
        self._hilo = threading.Thread(target=bucle, name="director", daemon=True)
        self._hilo.start()

    def cerrar(self) -> None:
        self._fin.set()
        if self._hilo:
            self._hilo.join(timeout=1.0)
