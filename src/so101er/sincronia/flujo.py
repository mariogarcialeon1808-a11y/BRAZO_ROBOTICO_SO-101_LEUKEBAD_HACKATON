"""Voz en flujo (p. ej. Gemini 3.8 Live) y su coordinación con los gestos.

Una voz en flujo genera audio y texto a la vez, sin que conozcamos la frase
de antemano. Para que los gestos lleguen con la palabra, el audio **se
reproduce con un pequeño retardo**: durante ese margen la transcripción se
trocea en frases, ER 2 las coreografía y los gestos quedan programados antes
de que suene cada palabra. Como la reproducción es local, la posición de la
voz se conoce con exactitud y hace de reloj de todo el sistema.

Tiempo de voz `v`: segundos de audio reproducidos desde el inicio de la sesión.
"""
from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from ..control.gestos import ErrorGesto, Gesto, preparar_anclas
from .partitura import Palabra, acentos_automaticos, contar_silabas

_FIN_FRASE = re.compile(r"[.!?…]+[\"»”)]*$")


class VozFlujo:
    """Recibe audio y transcripción de la red y entrega el audio al altavoz con retardo."""

    def __init__(self, retardo_s: float = 1.6, frecuencia: int = 24000) -> None:
        self.retardo = retardo_s
        self.frecuencia = frecuencia
        self._cerrojo = threading.Lock()
        self._buf = bytearray()
        self.recibidas = 0             # muestras recibidas en total
        self.reproducidas = 0          # muestras reproducidas en total
        self._t_primera: float | None = None
        self.sonando = False
        self.turno_abierto = False
        self.estado = "inactiva"
        self.eventos: deque[dict] = deque()

    # ---------------------------------------------------------------- entrada (hilo de red)
    def audio(self, pcm: bytes, t: float) -> None:
        with self._cerrojo:
            if not self.turno_abierto:
                self.turno_abierto = True
                self.eventos.append({"inicio": self.recibidas / self.frecuencia})
            if not self._buf and not self.sonando:
                self._t_primera = t
            self._buf += pcm
            self.recibidas += len(pcm) // 2

    def transcripcion(self, texto: str, t: float, palabras: list[tuple[str, float]] | None = None) -> None:
        """Texto de lo que dice la voz. `palabras`: (palabra, segundos desde el inicio del turno), si las hay."""
        with self._cerrojo:
            self.eventos.append({"texto": texto, "v": self.recibidas / self.frecuencia, "palabras": palabras})

    def fin_turno(self, t: float) -> None:
        with self._cerrojo:
            if self.turno_abierto:
                self.turno_abierto = False
                self.eventos.append({"fin": True})

    def interrumpir(self, t: float) -> None:
        """Descarta el audio pendiente (el visitante ha interrumpido)."""
        with self._cerrojo:
            self._buf.clear()
            self.recibidas = self.reproducidas
            self.sonando = False
            self.turno_abierto = False
            self.estado = "inactiva"
            self.eventos.clear()
            self.eventos.append({"interrumpido": True})

    # ---------------------------------------------------------------- reproducción
    def leer(self, muestras: int, t: float) -> bytes:
        """Audio para el altavoz (PCM de 16 bits). Silencio mientras dura el retardo o si falta audio."""
        pedido = muestras * 2
        with self._cerrojo:
            if not self.sonando:
                if self._buf and self._t_primera is not None and t >= self._t_primera + self.retardo:
                    self.sonando = True
                else:
                    self.estado = "inactiva"
                    return bytes(pedido)
            n = min(pedido, len(self._buf))
            n -= n % 2
            datos = bytes(self._buf[:n])
            del self._buf[:n]
            self.reproducidas += n // 2
            if n > 0:
                self.estado = "hablando"
            if not self._buf:
                if self.turno_abierto:
                    self.estado = "pausada" if n == 0 else self.estado     # la red va más lenta que la voz
                else:
                    self.sonando = False                                   # fin del tramo
                    self.estado = "inactiva" if n == 0 else self.estado
            return datos + bytes(pedido - n)

    def posicion(self, t: float) -> float:
        return self.reproducidas / self.frecuencia

    def pendiente(self) -> bool:
        return bool(self._buf) or self.sonando

    def inicio_previsto(self, t: float) -> float | None:
        """Instante real en que empezará a sonar el audio que espera, o None."""
        with self._cerrojo:
            if self.sonando or not self._buf or self._t_primera is None:
                return None
            return max(t, self._t_primera + self.retardo)


@dataclass
class FraseFlujo:
    id: int
    texto: str
    palabras: list[Palabra]          # inicio y fin en tiempo de voz (s)
    gestos: int = 0
    coreografiada: bool = False


@dataclass
class _Turno:
    v_inicio: float = 0.0
    texto: str = ""                  # texto aún no convertido en palabras
    marca: float = 0.0               # tiempo de voz hasta el que hay palabras colocadas
    palabras: list[Palabra] = field(default_factory=list)


class DirectorFlujo:
    """Convierte la voz en flujo en frases, las ofrece a ER 2 y programa sus gestos."""

    def __init__(self, sistema: Any, voz: VozFlujo, al_frase: Callable[[FraseFlujo], None] | None = None,
                 palabras_max: int | None = None) -> None:
        self.sistema, self.voz, self.al_frase = sistema, voz, al_frase
        cfg = sistema.cfg.voz
        self.adelanto = float(cfg["adelanto_gesto_s"]) + float(cfg["compensacion_s"])
        self.silabas_s = float(cfg["silabas_por_segundo"])
        self.palabras_max = int(palabras_max or cfg["palabras_por_fragmento"])
        self.frases: dict[int, FraseFlujo] = {}
        self.anclas: list[dict] = []
        self._id = 0
        self._turno = _Turno()
        self._siguiendo = False
        self._m_base = 0.0
        self._v_base = 0.0
        self._acentos: list[float] = []          # en tiempo de voz
        self._t_silencio: float | None = None
        self._reposar = False
        self._cerrojo = threading.RLock()
        sistema.director = self

    @property
    def activo(self) -> bool:
        return self.voz.pendiente() or self._reposar

    @property
    def fase(self) -> str:
        return "hablando" if self._siguiendo else "inactivo"

    # ---------------------------------------------------------------- tiempo
    def m_de_v(self, v: float, t: float) -> float:
        """Posición del compás en la que sonará el instante `v` de la voz."""
        if self._siguiendo:
            return self._m_base + (v - self._v_base)
        m_ahora, _ = self.sistema.compas.posicion(t)
        inicio = self.voz.inicio_previsto(t)
        return m_ahora + ((inicio - t) if inicio is not None else 0.0) + (v - self.voz.posicion(t))

    # ---------------------------------------------------------------- ciclo
    def paso(self, t: float) -> None:
        with self._cerrojo:
            s, voz = self.sistema, self.voz
            if voz.sonando and not self._siguiendo:
                m, _ = s.compas.posicion(t)
                self._v_base, self._m_base = voz.posicion(t), m
                s.compas.seguir(voz, m - self._v_base)
                self._siguiendo, self._reposar, self._t_silencio = True, True, None
            elif not voz.sonando and self._siguiendo:
                s.compas.liberar(t)
                self._siguiendo, self._t_silencio = False, t
            while voz.eventos:
                self._evento(voz.eventos.popleft(), t)
            m_ahora, _ = s.compas.posicion(t)
            while self._acentos and self.m_de_v(self._acentos[0], t) <= m_ahora + 0.25:
                s.acento(self.m_de_v(self._acentos.pop(0), t))
            if (self._reposar and self._t_silencio is not None and t - self._t_silencio > 2.0
                    and not voz.pendiente() and not s.ocupado()):
                self._reposar = False
                try:
                    s.reposo()
                except ErrorGesto as e:
                    s.registrar(f"no se pudo ir al reposo: {e}", alerta=True)

    def _evento(self, ev: dict, t: float) -> None:
        turno = self._turno
        if "interrumpido" in ev:
            self._turno = _Turno()
            self._acentos.clear()
            return
        if "inicio" in ev:
            self._turno = _Turno(v_inicio=ev["inicio"], marca=ev["inicio"])
            return
        if "fin" in ev:
            self._colocar(turno, turno.texto.split(), max(turno.marca, self.voz.recibidas / self.voz.frecuencia), None)
            turno.texto = ""
            self._emitir(turno, t, forzar=True)
            return
        turno.texto += ev["texto"]
        trozos = turno.texto.split()
        if not trozos:
            return
        completo = turno.texto[-1].isspace() or bool(_FIN_FRASE.search(trozos[-1]))
        listos = trozos if completo else trozos[:-1]
        turno.texto = "" if completo else trozos[-1]
        self._colocar(turno, listos, ev["v"], ev.get("palabras"))
        self._emitir(turno, t, forzar=False)

    def _colocar(self, turno: _Turno, textos: list[str], v_hasta: float,
                 tiempos: list[tuple[str, float]] | None) -> None:
        """Da tiempo de voz a las palabras nuevas."""
        if not textos:
            return
        silabas = [contar_silabas(x) for x in textos]
        if tiempos and len(tiempos) >= len(textos):        # tiempos reales por palabra
            inicios = [turno.v_inicio + float(x[1]) for x in tiempos[-len(textos):]]
            fines = inicios[1:] + [inicios[-1] + silabas[-1] / self.silabas_s]
        else:                                               # reparto por sílabas en el audio recibido
            desde = turno.marca
            hasta = v_hasta if v_hasta > desde + 0.05 else desde + sum(silabas) / self.silabas_s
            paso = (hasta - desde) / sum(silabas)
            inicios, fines, v = [], [], desde
            for n in silabas:
                inicios.append(v)
                v += n * paso
                fines.append(v)
        for texto, ini, fin, n in zip(textos, inicios, fines, silabas):
            turno.palabras.append(Palabra(texto, ini, fin, n))
        turno.marca = fines[-1]

    def _emitir(self, turno: _Turno, t: float, forzar: bool) -> None:
        """Cierra las frases completas y las ofrece al coreógrafo."""
        while turno.palabras:
            # Se corta en el fin de frase o, antes, en una coma: cuanto más corto el fragmento,
            # antes lo recibe ER 2 y más margen tiene para colocar los gestos.
            corte = next((i for i, p in enumerate(turno.palabras)
                          if _FIN_FRASE.search(p.texto) or (i >= 3 and p.texto[-1] in ",;:")), None)
            if corte is None:
                if len(turno.palabras) >= self.palabras_max:
                    corte = self.palabras_max - 1
                elif forzar:
                    corte = len(turno.palabras) - 1
                else:
                    return
            palabras, turno.palabras = turno.palabras[:corte + 1], turno.palabras[corte + 1:]
            self._id += 1
            frase = FraseFlujo(self._id, " ".join(p.texto for p in palabras), palabras)
            self.frases[frase.id] = frase
            for viejo in [k for k in self.frases if k < frase.id - 30]:
                del self.frases[viejo]
            self._acentos += [palabras[i].inicio - self.adelanto for i in acentos_automaticos(palabras)]
            self._acentos.sort()
            self.sistema.registrar(f"frase {frase.id}: \"{frase.texto}\"")
            if self.al_frase:
                self.al_frase(frase)

    # ---------------------------------------------------------------- órdenes
    def coreografiar(self, frase_id: int, gestos: list[Gesto], estilo: str | None = None) -> dict:
        """Programa los gestos de una frase del guía. Devuelve enseguida."""
        with self._cerrojo:
            frase = self.frases.get(frase_id)
            if frase is None:
                return {"error": f"no existe la frase {frase_id}. Últimas: {sorted(self.frases)[-3:]}"}
            s = self.sistema
            t = s.ahora()
            v_ahora = self.voz.posicion(t)
            programados, tarde, errores = 0, 0, []
            ultima = len(frase.palabras) - 1
            for g in gestos:
                preparar_anclas(g, lambda i: frase.palabras[min(max(int(i), 0), ultima)].inicio)
            for g in sorted(gestos, key=lambda x: x.ancla or 0):
                ancla = min(max(int(g.ancla or 0), 0), len(frase.palabras) - 1)
                v_apice = frase.palabras[ancla].inicio - self.adelanto
                retraso = v_ahora - v_apice
                if retraso > 1.0:                 # la palabra sonó hace más de un segundo: ya no pinta nada
                    tarde += 1
                    continue
                # Si la palabra acaba de sonar, el gesto se hace ya (llega algo tarde, pero llega).
                m_apice = self.m_de_v(v_apice, t) if retraso <= 0.15 else None
                try:
                    r = s.ejecutar(g if g.estilo or not estilo else replace(g, estilo=estilo),
                                   m_apice=m_apice, reemplazar=False)
                    programados += 1
                    for b in r["brazos"]:
                        if m_apice is None:
                            b["avisos"].append("gesto hecho con retraso: la palabra ya había sonado")
                        self.anclas.append({"frase": frase_id, "gesto": b["gesto"], "brazo": b["brazo"],
                                            "apice": b["apice"], "avisos": b["avisos"],
                                            "objetivo": (m_apice if m_apice is not None else b["apice"])
                                            + self.adelanto})
                except ErrorGesto as e:
                    errores.append(str(e))
            frase.coreografiada, frase.gestos = True, programados
            salida: dict[str, Any] = {"estado": "aceptado", "programados": programados}
            if tarde:
                salida["descartados_por_llegar_tarde"] = tarde
            if errores:
                salida["errores"] = errores
            return salida

    def interrumpir(self) -> None:
        with self._cerrojo:
            t = self.sistema.ahora()
            self.voz.interrumpir(t)
            if self._siguiendo:
                self.sistema.compas.liberar(t)
                self._siguiendo = False
            self._acentos.clear()
            self._reposar = False
        self.sistema.registrar("voz interrumpida: brazos al reposo")
        try:
            self.sistema.reposo()
        except ErrorGesto as e:
            self.sistema.registrar(f"no se pudo ir al reposo: {e}", alerta=True)

    # ---------------------------------------------------------------- tiempo real
    def iniciar(self, periodo: float = 0.02) -> None:
        import time
        self._fin = threading.Event()

        def bucle() -> None:
            while not self._fin.is_set():
                try:
                    self.paso(self.sistema.ahora())
                except Exception as e:
                    self.sistema.registrar(f"error en el director de voz: {e}", alerta=True)
                time.sleep(periodo)
        self._hilo = threading.Thread(target=bucle, name="director-flujo", daemon=True)
        self._hilo.start()

    def cerrar(self) -> None:
        if hasattr(self, "_fin"):
            self._fin.set()
            self._hilo.join(timeout=1.0)
