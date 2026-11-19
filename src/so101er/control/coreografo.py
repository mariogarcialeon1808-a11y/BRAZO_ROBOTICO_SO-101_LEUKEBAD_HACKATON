"""Coreógrafo: el motor de movimiento de un brazo.

En cada ciclo combina la línea de gestos (tiempo gestual), la respiración y
el arrastre de muñeca (tiempo real) y pasa el resultado por el filtro de
seguridad. Nunca espera a nadie: siempre tiene una referencia que seguir.
"""
from __future__ import annotations

import threading

import numpy as np

from ..cinematica.modelo import Cinematica
from ..config import Limites
from .capas import Arrastre, Respiracion, Suave
from .cualidades import Dinamica
from .filtro import FiltroTiron
from .gestos import Plan
from .linea import Linea, Sub, limite_blando
from .perfiles import duracion_minima, fraccion_inversa
from .reloj import RelojBrazo


def insertar_plan(linea: Linea, plan: Plan, inicio: float) -> None:
    """Añade los tramos de un plan a una línea, como desplazamientos sobre su destino."""
    destino = linea.destino()
    for tr in plan.tramos:
        if tr.q is not None:
            d = tr.q - destino
            destino = tr.q.copy()
            linea.subs.append(Sub(inicio + tr.t, tr.dur, d, tr.retardo, tr.c, False))
        else:
            linea.subs.append(Sub(inicio + tr.t, tr.dur, tr.d, tr.retardo, tr.c, True))


class Coreografo:
    def __init__(self, nombre: str, modelo: Cinematica, limites: Limites, q_inicial: np.ndarray,
                 respiracion_grados: float, respiracion_periodo_s: float, fase: float = 0.0,
                 ritmo_max: float = 1.4) -> None:
        self.nombre = nombre
        self.modelo = modelo
        self.limites = limites
        self.cerrojo = threading.Lock()
        q_min = np.append(modelo.lim_inf, 0.0)
        q_max = np.append(modelo.lim_sup, 100.0)
        q0 = np.clip(np.asarray(q_inicial, float), q_min, q_max)
        self.linea = Linea(q0)
        self.reloj = RelojBrazo(ritmo_max=ritmo_max)
        self.respiracion = Respiracion(respiracion_grados, respiracion_periodo_s, fase)
        self.arrastre = Arrastre()
        self.filtro = FiltroTiron(q0, limites.velocidad, limites.aceleracion, limites.tiron, q_min, q_max)
        self.q_min, self.q_max = q_min, q_max
        # Moduladores suaves: nunca cambian de golpe.
        self.energia = Suave(0.0)              # 0 = quieto del todo; 1 = respiración completa
        self.energia.objetivo = 1.0
        self.ganancia_arrastre = Suave(0.5)
        self.factor_respiracion = Suave(1.0)
        # Simpatía: desplazamiento que contagia el otro brazo (como el torso de una persona).
        self.simpatia = np.zeros(6)
        self._simpatia_d = np.zeros(6)
        self.simpatia_objetivo = np.zeros(6)
        self.q_reposo = q0.copy()
        self.detenido = False          # el reloj no avanza hasta nueva orden
        self.emergencia = False        # detenido y sin respiración hasta rearmar
        self._rapido = False
        self._g_prev = q0.copy()
        self.cmd = q0.copy()
        self.gesto_actual = "reposo"
        self._fin_gesto = float("-inf")

    # ------------------------------------------------------------ órdenes
    def programar(self, plan: Plan, m_inicio: float, m_ahora: float, din: Dinamica, etiqueta: str,
                  reemplazar: bool = True) -> float:
        """Inserta un plan en la línea. Devuelve el instante real de inicio (tiempo de compás)."""
        with self.cerrojo:
            if self.emergencia:
                raise RuntimeError("parada de emergencia activa")
            if self.detenido:
                self.detenido = False
                self._rapido = False
                if not self.linea.subs:
                    self.reloj.sincronizar(m_ahora)
            tau = self.reloj.tau
            if reemplazar:
                self.linea.cancelar_pendientes(tau)
            inicio = max(m_inicio, tau + 0.01)
            insertar_plan(self.linea, plan, inicio)
            self.ganancia_arrastre.objetivo = din.arrastre
            self.factor_respiracion.objetivo = din.respiracion
            self.gesto_actual = etiqueta
            self._fin_gesto = inicio + plan.fin
            return inicio

    def acento(self, m: float, fuerza: float = 1.0) -> None:
        """Pequeño impulso blando sobre el gesto en curso, para marcar una palabra."""
        with self.cerrojo:
            if self.emergencia or self.detenido:
                return
            d = np.array([0.6, 2.2, -3.0, 4.5, 1.0, 6.0]) * fuerza
            c = 0.75
            duracion = max(0.6, duracion_minima(d, c, True, self.limites.velocidad, self.limites.aceleracion,
                                                self.limites.tiron, margen=(0.3, 0.2, 0.12)))
            # El punto alto del impulso coincide con la palabra.
            t0 = max(m - fraccion_inversa(0.5, c) * duracion, self.reloj.tau + 0.01)
            self.linea.subs.append(Sub(t0, duracion, d, c=c, es_bulto=True))

    def detener(self, emergencia: bool = False) -> None:
        with self.cerrojo:
            self.detenido = True
            self._rapido = emergencia
            if emergencia:
                self.emergencia = True
                self.energia.objetivo = 0.0

    def rearmar(self) -> None:
        with self.cerrojo:
            self.emergencia = False
            self.energia.objetivo = 1.0

    # ------------------------------------------------------------ ciclo
    def paso(self, t: float, dt: float, m: float, corriendo: bool) -> np.ndarray:
        """Un ciclo de control. `t` es tiempo real; `m`, la posición del compás."""
        with self.cerrojo:
            reloj = self.reloj
            if not self.detenido and not self.linea.subs:
                reloj.sincronizar(m, ritmo=1.0 if corriendo else 0.0)
            else:
                reloj.paso(dt, m, corriendo, bloqueado=self.detenido, rapido=self._rapido)
            tau = reloj.tau
            if self.detenido and reloj.parado and self.linea.subs:
                self.linea.congelar(tau)
                self.gesto_actual = "detenido"
            self.linea.podar(tau)
            g = self.linea.valor(tau)
            if not self.linea.subs and tau > self._fin_gesto and not self.detenido:
                self.gesto_actual = "pausa"
            energia = self.energia.paso(dt)
            ganancia = self.ganancia_arrastre.paso(dt)
            factor = self.factor_respiracion.paso(dt)
        vel = (g - self._g_prev) / dt
        self._g_prev = g
        w = 2.2                         # el contagio es lento y sin esquinas (2.º orden, amortiguado)
        self._simpatia_d += (w * w * (self.simpatia_objetivo - self.simpatia) - 2.0 * w * self._simpatia_d) * dt
        self.simpatia += self._simpatia_d * dt
        ref = g + self.respiracion.valor(t) * (energia * factor) + self.simpatia * min(energia, 1.0)
        ref += self.arrastre.paso(vel, ganancia, dt) * min(energia, 1.0)
        self.cmd = self.filtro.paso(limite_blando(ref, self.q_min, self.q_max), dt)
        return self.cmd

    # ------------------------------------------------------------ consulta
    def ocupado(self) -> bool:
        with self.cerrojo:
            return bool(self.linea.subs) and not self.detenido

    def destino(self) -> np.ndarray:
        with self.cerrojo:
            return self.linea.destino()

    def copia_linea(self) -> tuple[Linea, float]:
        with self.cerrojo:
            return self.linea.copia(), self.reloj.tau
