"""Ensambla el sistema: brazos, coreógrafos, compás y seguridad.

Puede funcionar de dos maneras con el mismo código:
- por pasos (`avanzar(dt)`), determinista y sin hilos: tests y vídeos de simulación;
- en tiempo real (`iniciar()`), con un hilo de control por brazo.
"""
from __future__ import annotations

import math
import sys
import threading
import time
from collections import deque
from typing import Any, Callable

import numpy as np

from .cinematica.modelo import Cinematica
from .config import Config
from .control.coreografo import Coreografo, insertar_plan
from .control.cualidades import Cualidades, dinamica
from .control.gestos import (Contexto, ErrorGesto, Gesto, Plan, planificar, pose_expresiva, tipo_canonico)
from .control.reloj import Compas
from .control.seguridad import BrazoSeguro, Seguridad
from .geometria import Cuadro, Marco
from .hardware.sim import BrazoSim


class Sistema:
    def __init__(self, cfg: Config, brazos: dict[str, Any] | None = None) -> None:
        self.cfg = cfg
        self.t = 0.0
        self.compas = Compas()
        self.modelo = Cinematica()
        self.nombres = cfg.brazos_activos
        centro = np.mean([cfg.brazos[n].base_mm for n in self.nombres], axis=0)
        self.cuadro = Cuadro(cfg.cuadro.sup_izq, cfg.cuadro.sup_der, cfg.cuadro.inf_izq,
                             lado_brazos=centro + np.array([0.0, 0.0, 100.0]))
        self.marcos = {n: Marco(cfg.brazos[n].base_mm, cfg.brazos[n].orientacion_grados) for n in self.nombres}
        self.exterior: dict[str, float] = {}
        for n in self.nombres:
            lateral = self.marcos[n].rot[:, 1]
            if len(self.nombres) == 2:
                s = float(np.dot(lateral, cfg.brazos[n].base_mm - centro))
                self.exterior[n] = 1.0 if s >= 0 else -1.0
            else:
                self.exterior[n] = 1.0 if n == "izq" else -1.0
        self.seguridad = Seguridad(
            cfg.limites, self.cuadro, cfg.cuadro.separacion_min_mm,
            {n: BrazoSeguro(self.modelo, self.marcos[n]) for n in self.nombres}, cfg.zona_compartida)

        self.brazos: dict[str, Any] = {}
        self.coreos: dict[str, Coreografo] = {}
        mov = cfg.movimiento
        for i, n in enumerate(self.nombres):
            q_reposo, _ = pose_expresiva(self._contexto(n, np.zeros(6)), 1.0, None, False, **mov["reposo"])
            if callable(brazos):
                brazo = brazos(n, q_reposo)
            elif brazos and n in brazos:
                brazo = brazos[n]
            elif cfg.simulado:
                brazo = BrazoSim(n, q_reposo)
            else:
                raise NotImplementedError("el backend real con LeRobot llega en la Fase 3; usa --sim")
            brazo.conectar()
            # Arranque seguro: la posición leída es el objetivo inicial (sin saltos).
            q0 = brazo.leer_articulaciones()
            self.brazos[n] = brazo
            self.coreos[n] = Coreografo(n, self.modelo, cfg.limites, q0, mov["respiracion_grados"],
                                        mov["respiracion_periodo_s"], fase=2.1 * i, ritmo_max=mov["ritmo_max"])

        self._simpatia = float(mov["simpatia"])
        self.amplitud_global = 1.0
        self.tempo_global = 1.0
        self.historial: deque[tuple[float, str]] = deque(maxlen=300)
        self.alertas: deque[tuple[float, str]] = deque(maxlen=50)
        self.al_registrar: Callable[[str], None] | None = None
        self.director: Any = None
        self._orden = threading.RLock()
        self._cadenas: dict[str, np.ndarray] = {}
        self._medido: dict[str, np.ndarray] = {n: self.brazos[n].leer_articulaciones() for n in self.nombres}
        self._ciclos = {n: 0 for n in self.nombres}
        self._t_error = {n: 0.0 for n in self.nombres}
        self._sobrecargas = {n: 0 for n in self.nombres}
        self.jitter: dict[str, deque[float]] = {n: deque(maxlen=2000) for n in self.nombres}
        self._hilos: list[threading.Thread] = []
        self._fin = threading.Event()
        self._t0 = 0.0
        self.tiempo_real = False

    # ------------------------------------------------------------ utilidades
    def ahora(self) -> float:
        return time.perf_counter() - self._t0 if self.tiempo_real else self.t

    def registrar(self, texto: str, alerta: bool = False) -> None:
        t = self.ahora()
        self.historial.append((t, texto))
        if alerta:
            self.alertas.append((t, texto))
        if self.al_registrar:
            self.al_registrar(("⚠ " if alerta else "") + texto)

    def _contexto(self, nombre: str, q: np.ndarray, reduccion: float = 1.0) -> Contexto:
        exageracion = float(self.cfg.movimiento["exageracion"])
        if reduccion < 1.0:      # 0,7 → la mitad de la exageración; 0,45 → ninguna
            exageracion = 1.0 + (exageracion - 1.0) * max(reduccion - 0.45, 0.0) / 0.55
        return Contexto(modelo=self.modelo, marco=self.marcos[nombre], cuadro=self.cuadro,
                        limites=self.cfg.limites, separacion=self.cfg.cuadro.separacion_min_mm + 10.0,
                        exterior=self.exterior[nombre], reposo=self.cfg.movimiento["reposo"], q=q,
                        tempo=getattr(self, "tempo_global", 1.0),
                        exageracion=exageracion)

    def cualidades(self, gesto: Gesto) -> Cualidades:
        try:
            cual = self.cfg.estilo(gesto.estilo)
            validas = set(Cualidades.nombres())
            sobran = set(gesto.cualidades) - validas
            if sobran:
                raise ErrorGesto(f"cualidades desconocidas: {', '.join(sorted(sobran))}. "
                                 f"Admitidas: {', '.join(sorted(validas))}")
            cual = cual.con(**{k: float(v) for k, v in gesto.cualidades.items()})
        except ErrorGesto:
            raise
        except Exception as e:
            raise ErrorGesto(str(e)) from None
        if gesto.tipo == "trayectoria":
            # Movimiento compuesto por ER 2: siempre relajado (nunca súbito), con arcos e inercia
            # salvo que pida otra cosa de forma explícita.
            ajustes = {"tiempo": min(cual.tiempo, -0.2)}
            if "curvatura" not in gesto.cualidades:
                ajustes["curvatura"] = max(cual.curvatura, 0.6)
            if "flujo" not in gesto.cualidades:
                ajustes["flujo"] = min(cual.flujo, -0.3)
            cual = cual.con(**ajustes)
        return cual.con(amplitud=cual.amplitud * self.amplitud_global)

    def resolver_brazos(self, gesto: Gesto) -> list[str]:
        b = gesto.brazo
        if b in ("todos", "ambos"):
            return list(self.nombres)
        if b == "auto":
            punto = gesto.params.get("punto") or gesto.params.get("centro") or gesto.params.get("desde")
            if punto is None and gesto.params.get("puntos"):
                punto = gesto.params["puntos"][0]
                if isinstance(punto, dict):
                    punto = next((pc.get("mira") for pc in gesto.params["puntos"]
                                  if isinstance(pc, dict) and pc.get("mira") is not None), None)
            if punto is not None and len(self.nombres) == 2:
                try:
                    x = self.cuadro.punto_mundo(punto)
                except ValueError as e:
                    raise ErrorGesto(str(e)) from None
                return [min(self.nombres, key=lambda n: float(np.linalg.norm(self.cfg.brazos[n].base_mm - x)))]
            return [self.nombres[0]]
        if b not in self.nombres:
            if len(self.nombres) == 1:
                raise ErrorGesto(f"brazo '{b}' no disponible: en modo un brazo solo existe '{self.nombres[0]}'")
            raise ErrorGesto(f"brazo desconocido: '{b}'. Usa 'izq', 'der', 'todos' o 'auto'")
        return [b]

    # ------------------------------------------------------------ órdenes
    def ejecutar(self, gesto: Gesto, m_apice: float | None = None, reemplazar: bool = True) -> dict:
        """Planifica, verifica y programa un gesto. Devuelve enseguida ("aceptado, en curso").

        Lanza ErrorGesto, con un mensaje pensado para que ER 2 pueda corregir, si el
        gesto no es válido, no es alcanzable o no es seguro.
        """
        tipo = tipo_canonico(gesto.tipo)
        nombres = self.resolver_brazos(gesto)
        if gesto.relacion not in (None, "espejo", "canon", "acompanar"):
            raise ErrorGesto("'relacion' debe ser \"espejo\", \"canon\" o \"acompanar\"")
        cual = self.cualidades(gesto)
        with self._orden:
            m_ahora, _ = self.compas.posicion(self.ahora())
            trabajos: list[tuple[str, Gesto, Cualidades, float]] = [(n, gesto, cual, 0.0) for n in nombres]
            if gesto.relacion and len(self.nombres) == 2 and len(nombres) == 1:
                otro = next(n for n in self.nombres if n != nombres[0])
                if gesto.relacion == "espejo":
                    trabajos.append((otro, gesto, cual, 0.0))
                elif gesto.relacion == "canon":
                    trabajos.append((otro, gesto, cual, 0.45))
                else:
                    apoyo = Gesto("presentar", otro, {"azimut": 20.0, "mantener": 0.5})
                    trabajos.append((otro, apoyo, cual.con(amplitud=cual.amplitud * 0.45), 0.25))

            for n, _, _, _ in trabajos:
                if self.coreos[n].emergencia:
                    raise ErrorGesto("parada de emergencia activa: hay que rearmar antes de mover")
            problema = None
            # Si el gesto completo no es seguro, se intenta más pequeño y contenido antes de rechazarlo.
            for reduccion in (1.0, 0.7, 0.45):
                preparados, lineas, taus, fin_total = self._preparar(trabajos, m_ahora, m_apice, reemplazar,
                                                                     reduccion)
                problema = self.seguridad.verificar(lineas, min(taus.values()), fin_total + 0.3)
                if not problema:
                    break
            if problema:
                raise ErrorGesto(f"{tipo} rechazado por seguridad: {problema}")
            resultados = []
            for n, g, c, plan, inicio, avisos in preparados:
                real = self.coreos[n].programar(plan, inicio, m_ahora, dinamica(c), tipo_canonico(g.tipo),
                                                reemplazar)
                resultados.append({"brazo": n, "gesto": tipo_canonico(g.tipo), "inicio": round(real, 3),
                                   "apice": round(real + plan.apice, 3), "fin": round(real + plan.fin, 3),
                                   "avisos": avisos})
            self.registrar(f"{tipo} {'+'.join(r['brazo'] for r in resultados)} "
                           f"{gesto.estilo or self.cfg.movimiento['estilo']} {gesto.params or ''}".strip())
            return {"estado": "aceptado, en curso", "brazos": resultados}

    def _preparar(self, trabajos: list, m_ahora: float, m_apice: float | None, reemplazar: bool,
                  reduccion: float) -> tuple[list, dict, dict, float]:
        """Planifica los gestos sobre copias de las líneas, sin tocar los brazos."""
        if True:
            lineas = {}
            taus = {}
            for n in self.nombres:
                lineas[n], taus[n] = self.coreos[n].copia_linea()
            preparados = []
            fin_total = m_ahora
            for n, g, c, retraso in trabajos:
                linea = lineas[n]
                if reduccion < 1.0:
                    c = c.con(amplitud=c.amplitud * reduccion, flujo=1.0, curvatura=0.0, peso=min(c.peso, 0.0))
                if reemplazar:
                    linea.cancelar_pendientes(taus[n])
                plan = planificar(g, self._contexto(n, linea.destino(), reduccion), c)
                avisos = list(plan.avisos)
                if reduccion < 1.0:
                    avisos.append("gesto reducido para mantener las distancias de seguridad")
                if m_apice is not None:
                    hueco = m_apice + retraso - m_ahora
                    for _ in range(3):      # si no cabe en el tiempo: más pequeño, no más rápido
                        if plan.apice <= hueco + 0.05 or c.amplitud < 0.25 or g.tipo == "trayectoria":
                            break
                        c = c.con(amplitud=c.amplitud * max(0.5, hueco / plan.apice))
                        plan = planificar(g, self._contexto(n, linea.destino(), reduccion), c)
                        avisos.append("gesto reducido para llegar a tiempo")
                    inicio = max(m_apice + retraso - plan.apice, m_ahora + 0.02)
                else:
                    inicio = m_ahora + 0.02 + retraso
                inicio = max(inicio, taus[n] + 0.01)
                insertar_plan(linea, plan, inicio)
                preparados.append((n, g, c, plan, inicio, avisos))
                fin_total = max(fin_total, inicio + plan.fin)
            return preparados, lineas, taus, fin_total

    def planificar_solo(self, gesto: Gesto, nombre: str) -> Plan:
        """Plan de un gesto desde el destino actual del brazo, sin programarlo."""
        return planificar(gesto, self._contexto(nombre, self.coreos[nombre].destino()), self.cualidades(gesto))

    def acento(self, m: float, fuerza: float = 1.0, brazo: str = "todos") -> None:
        for n in (self.nombres if brazo == "todos" else [brazo]):
            if n in self.coreos:
                self.coreos[n].acento(m, fuerza)

    def parar(self, brazo: str = "todos", emergencia: bool = False) -> None:
        for n in (self.nombres if brazo == "todos" else [brazo]):
            if n not in self.coreos:
                raise ErrorGesto(f"brazo desconocido: '{brazo}'")
            self.coreos[n].detener(emergencia)
        self.registrar(("PARADA DE EMERGENCIA" if emergencia else "parar") + f" ({brazo})", alerta=emergencia)

    def rearmar(self) -> None:
        for c in self.coreos.values():
            c.rearmar()
        self.registrar("rearmado tras la parada de emergencia")

    def quitar_par(self) -> None:
        for n in self.nombres:
            self.brazos[n].desactivar_par()
        self.registrar("par de los motores desactivado", alerta=True)

    def reposo(self, brazo: str = "todos") -> dict:
        return self.ejecutar(Gesto("reposo", brazo))

    def matizar(self, energia: float | None = None, amplitud: float | None = None,
                tempo: float | None = None) -> dict:
        if energia is not None:
            for c in self.coreos.values():
                if not c.emergencia:
                    c.energia.objetivo = float(np.clip(energia, 0.0, 1.6))
        if amplitud is not None:
            self.amplitud_global = float(np.clip(amplitud, 0.3, 1.3))
        if tempo is not None:
            self.tempo_global = float(np.clip(tempo, 0.5, 1.6))
        self.registrar(f"matizar energia={energia} amplitud={amplitud} tempo={tempo}")
        return {"estado": "aceptado"}

    # ------------------------------------------------------------ consulta
    def apunta(self, nombre: str, q: np.ndarray) -> list[float] | None:
        """Punto [y, x] de la imagen al que apunta la herramienta, o None."""
        pos, eje = self.modelo.punta(q[:5])
        marco = self.marcos[nombre]
        st = self.cuadro.interseccion(marco.a_mundo(pos), marco.dir_a_mundo(eje))
        if st is None or not (-0.2 <= st[0] <= 1.2 and -0.2 <= st[1] <= 1.2):
            return None
        return [round(float(v), 1) for v in self.cuadro.obra_a_imagen(*st)]

    def ocupado(self) -> bool:
        return any(c.ocupado() for c in self.coreos.values())

    def estado(self) -> dict:
        m, corriendo = self.compas.posicion(self.ahora())
        brazos = {}
        for n in self.nombres:
            c = self.coreos[n]
            q = self._medido[n]
            punta = self.marcos[n].a_mundo(self.modelo.punta(q[:5])[0])
            brazos[n] = {
                "actividad": c.gesto_actual, "en_movimiento": c.ocupado(),
                "detenido": c.detenido, "emergencia": c.emergencia,
                "punta_mm": [round(float(v)) for v in punta],
                "apunta_yx": self.apunta(n, q), "pinza": round(float(q[5])),
                "ritmo": round(c.reloj.ritmo, 2),
            }
        return {"modo": self.cfg.modo, "compas": round(m, 2), "voz_activa": not corriendo or self.compas._voz is not None,
                "brazos": brazos, "alertas": [a for _, a in list(self.alertas)[-5:]]}

    # ------------------------------------------------------------ ciclo de control
    def tick(self, nombre: str, t: float, dt: float) -> None:
        coreo, brazo, lim = self.coreos[nombre], self.brazos[nombre], self.cfg.limites
        if len(self.nombres) == 2:      # los dos brazos son de un mismo cuerpo: uno arrastra un poco al otro
            otro = self.coreos[self.nombres[1] if nombre == self.nombres[0] else self.nombres[0]]
            arrastre = np.clip(otro._g_prev[:3] - otro.q_reposo[:3], -45.0, 45.0) * self._simpatia
            coreo.simpatia_objetivo[:3] = arrastre
        m, corriendo = self.compas.posicion(t)
        cmd = coreo.paso(t, dt, m, corriendo)
        cadena = self.seguridad.cadena_mundo(nombre, cmd)
        self._cadenas[nombre] = cadena
        if not coreo.detenido:
            problema = self.seguridad.problema_pose(nombre, cmd, cadena, margen=15.0)
            if problema:
                coreo.detener()
                self.registrar(f"brazo {nombre} detenido: {problema}", alerta=True)
            elif len(self._cadenas) == 2:
                problema = self.seguridad.problema_par(self._cadenas, margen=15.0)
                if problema:
                    for c in self.coreos.values():
                        c.detener()
                    self.registrar(f"brazos detenidos: {problema}", alerta=True)
        brazo.enviar_objetivo(cmd)
        if hasattr(brazo, "avanzar"):
            brazo.avanzar(dt)
        self._ciclos[nombre] += 1
        if self._ciclos[nombre] % 5 == 0:
            medido = brazo.leer_articulaciones()
            self._medido[nombre] = medido
            error = float(np.max(np.abs(medido[:5] - cmd[:5])))
            self._t_error[nombre] = self._t_error[nombre] + 5 * dt if error > lim.error_seguimiento_max_grados else 0.0
            motivo = None
            if self._t_error[nombre] > getattr(brazo, "tiempo_error_s", 0.3):
                motivo = f"error de seguimiento de {error:.0f}° (¿brazo bloqueado?)"
            elif self._ciclos[nombre] % 50 == 0:
                sobrecarga = (getattr(brazo, "telemetria_carga", True) and
                              float(np.max(brazo.leer_carga()[:5])) > lim.carga_max)
                self._sobrecargas[nombre] = self._sobrecargas[nombre] + 1 if sobrecarga else 0
                if (getattr(brazo, "telemetria_temperatura", True) and
                        float(np.max(brazo.leer_temperatura())) > lim.temperatura_max_c):
                    motivo = "temperatura de un motor demasiado alta"
                elif self._sobrecargas[nombre] >= 4:        # unos 2 s seguidos
                    motivo = "carga de un motor demasiado alta de forma sostenida"
            if motivo and not coreo.detenido:
                coreo.detener()
                self.registrar(f"brazo {nombre} detenido: {motivo}", alerta=True)

    def avanzar(self, dt: float) -> None:
        """Modo por pasos: avanza todo el sistema un intervalo `dt` de tiempo simulado."""
        self.t += dt
        if self.director is not None:
            self.director.paso(self.t)
        for n in self.nombres:
            self.tick(n, self.t, dt)

    def avanzar_hasta_quieto(self, dt: float = 0.01, maximo_s: float = 60.0, extra_s: float = 0.3) -> float:
        inicio = self.t
        while self.t - inicio < maximo_s and (self.ocupado() or (self.director and self.director.activo)):
            self.avanzar(dt)
        for _ in range(int(extra_s / dt)):
            self.avanzar(dt)
        return self.t - inicio

    # ------------------------------------------------------------ tiempo real
    def iniciar(self) -> None:
        """Arranca un hilo de control por brazo."""
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        # Turnos cortos entre hilos: la planificacion de un gesto no retrasa el control.
        sys.setswitchinterval(0.002)
        self.tiempo_real = True
        self._t0 = time.perf_counter() - self.t
        self._fin.clear()
        for n in self.nombres:
            h = threading.Thread(target=self._bucle, args=(n,), name=f"control-{n}", daemon=True)
            h.start()
            self._hilos.append(h)

    def _bucle(self, nombre: str) -> None:
        periodo = 1.0 / self.cfg.frecuencia_hz
        siguiente = time.perf_counter()
        anterior = siguiente - periodo
        while not self._fin.is_set():
            ahora = time.perf_counter()
            dt = min(max(ahora - anterior, 0.5 * periodo), 3.0 * periodo)
            self.jitter[nombre].append(ahora - anterior - periodo)
            anterior = ahora
            try:
                self.tick(nombre, ahora - self._t0, dt)
            except Exception as e:     # nunca dejar un brazo sin control
                self.registrar(f"error en el control de {nombre}: {e}", alerta=True)
                self.coreos[nombre].detener(emergencia=True)
            siguiente += periodo
            falta = siguiente - time.perf_counter()
            if falta < -periodo:       # muy retrasado: no acumular
                siguiente = time.perf_counter()
            elif falta > 0:
                time.sleep(falta)

    def resumen_jitter(self) -> dict[str, dict[str, float]]:
        salida = {}
        for n, d in self.jitter.items():
            if d:
                a = np.abs(np.array(d))
                salida[n] = {"medio_ms": round(float(a.mean()) * 1e3, 3), "max_ms": round(float(a.max()) * 1e3, 3)}
        return salida

    def cerrar(self, ir_a_reposo: bool = True) -> None:
        """Cierre seguro: reposo lento, parar los hilos y quitar el par."""
        if self.tiempo_real and ir_a_reposo and not any(c.emergencia for c in self.coreos.values()):
            try:
                self.reposo()
                limite = time.perf_counter() + 8.0
                time.sleep(0.2)
                while self.ocupado() and time.perf_counter() < limite:
                    time.sleep(0.05)
            except ErrorGesto:
                pass
        self._fin.set()
        for h in self._hilos:
            h.join(timeout=1.0)
        self._hilos.clear()
        for n in self.nombres:
            self.brazos[n].desactivar_par()
            self.brazos[n].desconectar()
        if self.tiempo_real and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        self.tiempo_real = False


def angulo_legible(q: np.ndarray) -> str:
    return " ".join(f"{math.floor(v + 0.5):4d}" for v in q)

