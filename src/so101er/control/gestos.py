"""Biblioteca de gestos: convierte cada gesto en un plan de submovimientos.

Un plan es una lista de tramos (pasos hacia una pose o bultos que salen y
vuelven) con tiempos relativos al inicio del gesto, más el instante del
ápice (el momento expresivo que se ancla a una palabra).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..cinematica.modelo import Cinematica, FueraDeAlcance
from ..config import Limites
from ..geometria import Cuadro, ErrorPunto, Marco, validar_punto
from .cualidades import Cualidades, dinamica
from .perfiles import duracion_minima, fraccion_inversa

NEUTRA = {"alcance": 0.45, "azimut": 0.0, "altura": 0.42, "elevacion": -5.0, "giro": 0.0, "pinza": 40.0}
FORMAS = ("circulo", "espiral", "onda", "vertical", "horizontal", "zigzag", "ocho")


class ErrorGesto(ValueError):
    """El gesto pedido no es válido o no se puede ejecutar. El mensaje va a ER 2."""


@dataclass
class Gesto:
    tipo: str
    brazo: str
    params: dict[str, Any] = field(default_factory=dict)
    estilo: str | None = None
    cualidades: dict[str, float] = field(default_factory=dict)   # ajustes sobre el estilo
    ancla: int | None = None       # índice de la palabra a la que se ancla el ápice
    t: float | None = None         # o instante del ápice dentro de la frase (s)
    relacion: str | None = None    # con dos brazos: "espejo", "canon" o "acompanar"

    def a_dict(self) -> dict:
        d = {"tipo": self.tipo, "brazo": self.brazo, "params": self.params}
        for k in ("estilo", "ancla", "t", "relacion"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.cualidades:
            d["cualidades"] = self.cualidades
        return d

    @staticmethod
    def de_dict(d: dict) -> "Gesto":
        if not isinstance(d, dict) or "tipo" not in d:
            raise ErrorGesto("cada gesto debe tener al menos el campo \"tipo\"")
        return Gesto(tipo=str(d["tipo"]), brazo=str(d.get("brazo", "auto")), params=dict(d.get("params", {})),
                     estilo=d.get("estilo"), cualidades=dict(d.get("cualidades", {})),
                     ancla=d.get("ancla"), t=d.get("t"), relacion=d.get("relacion"))


@dataclass
class Tramo:
    t: float                       # inicio relativo al gesto (s)
    dur: float
    c: float
    retardo: np.ndarray
    q: np.ndarray | None = None    # paso: pose objetivo absoluta
    d: np.ndarray | None = None    # bulto: desplazamiento que sale y vuelve


@dataclass
class Plan:
    tramos: list[Tramo]
    apice: float                   # instante expresivo, relativo al inicio
    fin: float                     # fin del gesto incluido el sostenido
    q_final: np.ndarray
    avisos: list[str] = field(default_factory=list)


@dataclass
class Contexto:
    modelo: Cinematica
    marco: Marco
    cuadro: Cuadro
    limites: Limites
    separacion: float              # separación mínima con la obra (mm)
    exterior: float                # +1 o −1: sentido del azimut "hacia fuera"
    reposo: dict[str, float]
    q: np.ndarray                  # pose de partida (6)
    tempo: float = 1.0             # >1: gestos más breves; <1: más lentos
    exageracion: float = 1.0       # >1: las poses compuestas se alejan más de la pose neutra


# ---------------------------------------------------------------- poses
def pose_apuntar(ctx: Contexto, p_mundo: np.ndarray, alcance: float, giro: float, pinza: float,
                 semilla: np.ndarray | None = None) -> np.ndarray:
    """Pose que apunta a un punto del mundo: punta sobre el rayo hombro→punto."""
    m = ctx.modelo
    v = ctx.marco.a_base(p_mundo) - m.hombro
    dist = float(np.linalg.norm(v))
    direccion = v / dist
    azimut = math.degrees(math.atan2(direccion[1], direccion[0]))
    if abs(azimut) > 105.0:
        raise FueraDeAlcance("el punto queda fuera del giro del brazo (demasiado a un lado o detrás)")
    d_hombro = ctx.cuadro.distancia(ctx.marco.a_mundo(m.hombro))
    if d_hombro <= ctx.separacion + 20.0:
        raise FueraDeAlcance("la base del brazo está demasiado cerca de la obra para apuntar con seguridad")
    tope = dist * (1.0 - (ctx.separacion + 20.0) / d_hombro)
    r = min(alcance * 0.93 * m.alcance_max, tope)
    if r < 110.0:
        raise FueraDeAlcance("el punto está demasiado cerca del brazo para apuntarlo sin tocar la obra")
    elev = math.degrees(math.asin(float(np.clip(direccion[2], -1, 1))))
    ultimo: Exception | None = None
    for _ in range(7):
        try:
            q5 = m.inversa(m.hombro + direccion * r, elev, giro, semilla, peso_elevacion=1.0)
            return np.append(q5, pinza)
        except FueraDeAlcance as e:
            ultimo = e
            r *= 0.9
            if r < 110.0:
                break
    raise FueraDeAlcance(f"no puedo apuntar a ese punto: {ultimo}")


def pose_expresiva(ctx: Contexto, amplitud: float, semilla: np.ndarray | None = None, escalar: bool = True,
                   **p: float) -> tuple[np.ndarray, bool]:
    """Pose definida en el espacio expresivo. Devuelve (q, recortada)."""
    obj = {k: float(p.get(k, NEUTRA[k])) for k in NEUTRA}
    k_amp = (0.45 + 0.55 * amplitud) if escalar else 1.0
    m = ctx.modelo
    for i, s in enumerate((1.0, 0.85, 0.7, 0.55, 0.4, 0.25)):
        v = {k: NEUTRA[k] + s * k_amp * (obj[k] - NEUTRA[k]) for k in NEUTRA}
        v["pinza"] = NEUTRA["pinza"] + k_amp * (obj["pinza"] - NEUTRA["pinza"])
        r = 130.0 + float(np.clip(v["alcance"], 0, 1)) * 200.0
        z = 60.0 + float(np.clip(v["altura"], 0, 1)) * 300.0
        az = math.radians(v["azimut"] * ctx.exterior)
        pos = np.array([m.eje_pan[0] + r * math.cos(az), m.eje_pan[1] + r * math.sin(az), z])
        try:
            q5 = m.inversa(pos, v["elevacion"], v["giro"] * ctx.exterior, semilla)
            return np.append(q5, float(np.clip(v["pinza"], 0, 100))), i > 0
        except FueraDeAlcance:
            continue
    raise FueraDeAlcance("la pose pedida no es alcanzable ni reduciendo su amplitud")


# ---------------------------------------------------------------- constructor
class _Constructor:
    def __init__(self, ctx: Contexto, cual: Cualidades) -> None:
        self.ctx, self.cual, self.din = ctx, cual, dinamica(cual)
        self.q = ctx.q.copy()
        self.t = 0.0
        self.tramos: list[Tramo] = []
        self.avisos: list[str] = []
        self.cero = np.zeros(6)

    def duracion(self, d: np.ndarray, lento: float = 1.0) -> float:
        lim = self.ctx.limites
        estilo = (self.din.factor_duracion * lento / self.ctx.tempo
                  * (0.55 + 0.011 * float(np.max(np.abs(d[:5])))))
        return max(estilo, 0.35, duracion_minima(d, self.din.c, False, lim.velocidad, lim.aceleracion, lim.tiron))

    def ir(self, q_obj: np.ndarray, lento: float = 1.0, adornos: bool = True,
           dur: float | None = None) -> tuple[float, float]:
        """Paso hacia una pose, con anticipación, arco y rebase según las cualidades.

        `dur`: duración pedida en segundos; nunca menos de lo que permiten los límites."""
        d = q_obj - self.q
        if dur is None:
            dur = self.duracion(d, lento)
        else:
            lim = self.ctx.limites
            dur = max(dur, 0.3, duracion_minima(d, self.din.c, False, lim.velocidad, lim.aceleracion, lim.tiron))
        t0 = self.t
        grande = float(np.max(np.abs(d[:5]))) > 10.0
        din = self.din
        if adornos and grande and din.anticipacion > 0.01:
            self.tramos.append(Tramo(t0, 0.6 * dur, 1.0, self.cero, d=-din.anticipacion * d))
            t0 += 0.15 * dur
        self.tramos.append(Tramo(t0, dur, din.c, din.retardos.copy(), q=q_obj.copy()))
        if adornos and grande and din.rebase > 0.01:
            self.tramos.append(Tramo(t0 + 0.45 * dur, 0.9 * dur, 1.0, din.retardos.copy(), d=din.rebase * d))
        if adornos and grande and din.arco > 0.02:
            arco = self._arco(self.q, q_obj)
            if arco is not None:
                self.tramos.append(Tramo(t0, dur, din.c, self.cero, d=arco))
        self.q = q_obj.copy()
        self.t = t0 + dur
        return t0, dur

    def _arco(self, qa: np.ndarray, qb: np.ndarray) -> np.ndarray | None:
        m = self.ctx.modelo
        medio = 0.5 * (qa + qb)
        cuerda = float(np.linalg.norm(m.punta(qb)[0] - m.punta(qa)[0]))
        p_medio = m.punta(medio)[0]
        alto = min(self.din.arco * cuerda, 70.0)
        if alto < 4.0:
            return None
        try:
            q5 = m.inversa(p_medio + np.array([0.0, 0.0, alto]), None, medio[4], medio[:5], tolerancia_mm=3.0)
        except FueraDeAlcance:
            return None
        d = np.zeros(6)
        d[:5] = np.clip(q5 - medio[:5], -25.0, 25.0)
        return d

    def ir_apice(self, q_obj: np.ndarray, lento: float = 1.0) -> float:
        """Paso hacia una pose; devuelve el instante en que el gesto 'llega'."""
        t0, dur = self.ir(q_obj, lento)
        return t0 + dur * fraccion_inversa(0.78, self.din.c) + float(self.din.retardos[3])

    def camino(self, qs: list[np.ndarray], dts: np.ndarray) -> float:
        """Sigue una serie densa de poses con escalones solapados. Devuelve el instante de llegada."""
        lim = self.ctx.limites
        dts = np.array(dts, float)
        previo = self.q
        for i, q in enumerate(qs):
            dts[i] = max(dts[i], float(np.max(np.abs(q - previo) * 1.1 / (0.6 * lim.velocidad))), 0.05)
            previo = q
        # Entrada y salida progresivas: el camino arranca y termina despacio.
        n = len(dts)
        for i, factor in enumerate((3.2, 2.2, 1.6, 1.25)):
            if i < n / 2:
                dts[i] *= factor
                dts[n - 1 - i] *= factor
        if n >= 3:             # sin cambios bruscos de ritmo
            suave = np.convolve(np.pad(dts, 1, mode="edge"), np.ones(3) / 3.0, mode="valid")
            dts = np.maximum(dts, suave)
        inicio = self.t
        centro = self.t
        for q, dt in zip(qs, dts):
            centro += dt
            self.tramos.append(Tramo(centro - 1.5 * dt, 3.0 * dt, 1.0, self.cero, q=q.copy()))
            self.q = q.copy()
        self.t = centro + 1.5 * float(dts[-1])
        return centro

    def bulto(self, d: np.ndarray, t: float, dur: float) -> None:
        lim = self.ctx.limites
        dur = max(dur, duracion_minima(d, 1.0, True, lim.velocidad, lim.aceleracion, lim.tiron))
        self.tramos.append(Tramo(t, dur, 1.0, self.cero, d=np.asarray(d, float)))

    def plan(self, apice: float, mantener: float = 0.0) -> Plan:
        fin = max([self.t] + [x.t + x.dur + float(np.max(x.retardo)) for x in self.tramos]) + mantener
        return Plan(self.tramos, apice, fin, self.q.copy(), self.avisos)


# ---------------------------------------------------------------- utilidades de camino
def _remuestrear(pts: np.ndarray, paso: float, minimo: int = 8, maximo: int = 70) -> np.ndarray:
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    acum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(acum[-1])
    if total < 1e-6:
        raise ErrorGesto("el camino no tiene longitud: da al menos dos puntos distintos")
    n = int(np.clip(round(total / paso), minimo, maximo))
    s = np.linspace(0.0, total, n + 1)
    return np.stack([np.interp(s, acum, pts[:, k]) for k in range(pts.shape[1])], axis=1)


def _tiempos(pts: np.ndarray, velocidad: float, radio_ref: float = 90.0) -> np.ndarray:
    """Tiempo de cada segmento según la ley de los dos tercios (más lento en las curvas)."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    curv = np.zeros(len(pts))
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        area2 = float(np.linalg.norm(np.cross(b - a, c - a)))
        den = float(np.linalg.norm(b - a) * np.linalg.norm(c - b) * np.linalg.norm(c - a))
        curv[i] = 2.0 * area2 / den if den > 1e-9 else 0.0
    curv_seg = 0.5 * (curv[:-1] + curv[1:])
    v = velocidad * (1.0 + curv_seg * radio_ref) ** (-1.0 / 3.0)
    return seg / v


def _forma(nombre: str, vueltas: float, n: int = 120) -> np.ndarray:
    """Puntos (x, y) de una forma en el cuadrado [−1, 1]²; y positivo hacia arriba."""
    s = np.linspace(0.0, 1.0, n)
    if nombre == "circulo":
        a = 2 * math.pi * vueltas * s + math.pi / 2
        return np.stack([np.cos(a), np.sin(a)], axis=1)
    if nombre == "espiral":
        a = 2 * math.pi * max(vueltas, 1.5) * s
        r = 0.15 + 0.85 * s
        return np.stack([r * np.cos(a), r * np.sin(a)], axis=1)
    if nombre == "onda":
        return np.stack([2 * s - 1, 0.4 * np.sin(2 * math.pi * max(vueltas, 1.0) * s)], axis=1)
    if nombre == "vertical":
        return np.stack([np.zeros(n), 2 * s - 1], axis=1)
    if nombre == "horizontal":
        return np.stack([2 * s - 1, np.zeros(n)], axis=1)
    if nombre == "zigzag":
        k = max(vueltas, 1.0) * 2
        tri = 2 * np.abs(2 * ((k * s) % 1.0) - 1) - 1
        return np.stack([2 * s - 1, 0.5 * tri], axis=1)
    if nombre == "ocho":
        a = 2 * math.pi * vueltas * s
        return np.stack([np.sin(a), 0.6 * np.sin(2 * a)], axis=1)
    raise ErrorGesto(f"forma desconocida: '{nombre}'. Disponibles: {', '.join(FORMAS)}")


def _camino_en_obra(k: _Constructor, puntos_yx: np.ndarray, pinza: float, giros: tuple[float, float],
                    duracion: float | None) -> Plan:
    """Prepara el brazo en el primer punto y recorre el camino sobre la obra."""
    ctx = k.ctx
    mundo = np.array([ctx.cuadro.punto_mundo(p) for p in puntos_yx])
    mundo = _remuestrear(mundo, 28.0)
    alcance = 0.55 + 0.4 * k.cual.amplitud
    qs: list[np.ndarray] = []
    semilla = None
    for i, p in enumerate(mundo):
        giro = giros[0] + (giros[1] - giros[0]) * i / (len(mundo) - 1)
        q = pose_apuntar(ctx, p, alcance, giro * ctx.exterior, pinza, semilla)
        semilla = q[:5]
        qs.append(q)
    apice = k.ir_apice(qs[0])
    dts = _tiempos(mundo, 170.0 / k.din.factor_duracion)
    if duracion is not None:
        dts = dts * (max(duracion, 0.3) / float(np.sum(dts)))
    k.camino(qs[1:], dts)
    return k.plan(apice, mantener=0.3)


# ---------------------------------------------------------------- gestos
def _num(params: dict, nombre: str, defecto: float, lo: float, hi: float) -> float:
    v = params.get(nombre, defecto)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ErrorGesto(f"'{nombre}' debe ser un número entre {lo:g} y {hi:g} (valor: {v!r})")
    if not lo <= v <= hi:
        raise ErrorGesto(f"'{nombre}' debe estar entre {lo:g} y {hi:g} (valor: {v:g})")
    return float(v)


def _punto(params: dict, nombre: str) -> np.ndarray:
    if nombre not in params:
        raise ErrorGesto(f"falta '{nombre}': un punto [y, x] con valores de 0 a 1000")
    try:
        return validar_punto(params[nombre])
    except ErrorPunto as e:
        raise ErrorGesto(f"'{nombre}': {e}") from None


def _senalar(k: _Constructor, p: dict) -> Plan:
    punto = _punto(p, "punto")
    mantener = _num(p, "mantener", 1.2, 0.0, 10.0)
    q = pose_apuntar(k.ctx, k.ctx.cuadro.punto_mundo(punto), 0.55 + 0.4 * k.cual.amplitud, 0.0, 8.0, k.q[:5])
    return k.plan(k.ir_apice(q), mantener)


def _trazar(k: _Constructor, p: dict) -> Plan:
    pts = p.get("puntos")
    if not isinstance(pts, (list, tuple)) or len(pts) < 2:
        raise ErrorGesto("'puntos' debe ser una lista de al menos dos puntos [y, x]")
    puntos = np.array([_punto({"p": x}, "p") for x in pts])
    dur = _num(p, "duracion", 0.0, 0.0, 60.0) or None
    return _camino_en_obra(k, puntos, 8.0, (0.0, 0.0), dur)


def _abarcar(k: _Constructor, p: dict) -> Plan:
    a, b = _punto(p, "desde"), _punto(p, "hasta")
    s = np.linspace(0.0, 1.0, 24)[:, None]
    linea = a + (b - a) * s
    largo = float(np.linalg.norm(b - a))
    arriba = np.array([-1.0, 0.0])     # en imagen, "arriba" es y menor
    linea = linea + arriba * (0.14 * largo * k.cual.curvatura) * np.sin(math.pi * s)
    linea = np.clip(linea, 0.0, 1000.0)
    return _camino_en_obra(k, linea, 80.0, (-25.0, 25.0), _num(p, "duracion", 0.0, 0.0, 60.0) or None)


def _dibujar_forma(k: _Constructor, p: dict) -> Plan:
    forma = str(p.get("forma", "circulo"))
    vueltas = _num(p, "vueltas", 1.0, 0.25, 6.0)
    xy = _forma(forma, vueltas)
    plano = str(p.get("plano", "cuadro" if "centro" in p else "aire"))
    dur = _num(p, "duracion", 0.0, 0.0, 60.0) or None
    if plano == "cuadro":
        centro = _punto(p, "centro")
        tam = _num(p, "tamano", 200.0, 20.0, 1000.0) / 2.0
        puntos = np.clip(np.stack([centro[0] - tam * xy[:, 1], centro[1] + tam * xy[:, 0]], axis=1), 0, 1000)
        return _camino_en_obra(k, puntos, 8.0, (0.0, 0.0), dur)
    if plano != "aire":
        raise ErrorGesto("'plano' debe ser \"cuadro\" o \"aire\"")
    ctx, m = k.ctx, k.ctx.modelo
    radio = (45.0 + 75.0 * k.cual.amplitud) * _num(p, "tamano", 1.0, 0.2, 1.5)
    lateral = _num(p, "lateral", 0.3, -1.0, 1.0) * 120.0 * ctx.exterior
    centro3 = np.array([m.eje_pan[0] + 215.0, lateral, 215.0])
    pts = np.stack([np.full(len(xy), centro3[0]), centro3[1] - radio * xy[:, 0] * ctx.exterior,
                    centro3[2] + radio * xy[:, 1]], axis=1)
    pts = _remuestrear(pts, 22.0)
    qs, semilla = [], k.q[:5]
    for pt in pts:
        try:
            q5 = m.inversa(pt, 5.0, 0.0, semilla)
        except FueraDeAlcance as e:
            raise ErrorGesto(f"la forma no cabe en el espacio del brazo: {e}") from None
        semilla = q5
        qs.append(np.append(q5, 30.0))
    apice = k.ir_apice(qs[0])
    dts = _tiempos(pts, 150.0 / k.din.factor_duracion)
    if dur is not None:
        dts = dts * (max(dur, 0.3) / float(np.sum(dts)))
    k.camino(qs[1:], dts)
    return k.plan(apice, mantener=0.3)


def _ondular(k: _Constructor, p: dict) -> Plan:
    ondas = _num(p, "ondas", 2.0, 1.0, 6.0)
    if "desde" in p and "hasta" in p:
        a, b = _punto(p, "desde"), _punto(p, "hasta")
        s = np.linspace(0.0, 1.0, 80)[:, None]
        largo = float(np.linalg.norm(b - a))
        normal = np.array([-(b - a)[1], (b - a)[0]]) / max(largo, 1e-6)
        alto = _num(p, "altura", 0.12, 0.02, 0.5) * largo
        linea = np.clip(a + (b - a) * s + normal * alto * np.sin(2 * math.pi * ondas * s), 0, 1000)
        return _camino_en_obra(k, linea, 55.0, (-20.0, 20.0), _num(p, "duracion", 0.0, 0.0, 60.0) or None)
    return _dibujar_forma(k, {"forma": "onda", "vueltas": ondas, "plano": "aire",
                              **{x: p[x] for x in ("tamano", "duracion", "lateral") if x in p}})


def _expresivo(k: _Constructor, lento: float = 1.0, escalar: bool = True, **pose: float) -> float:
    q, recortada = pose_expresiva(k.ctx, k.cual.amplitud, k.q[:5], escalar, **pose)
    if recortada:
        k.avisos.append("la pose se ha reducido para que el brazo la alcance")
    return k.ir_apice(q, lento)


def _elevar(k: _Constructor, p: dict) -> Plan:
    _expresivo(k, alcance=0.5, altura=0.2, elevacion=-20.0, pinza=28.0, azimut=10.0)
    apice = _expresivo(k, lento=1.25, alcance=0.62, altura=0.97, elevacion=35.0, pinza=82.0, giro=25.0, azimut=18.0)
    return k.plan(apice, _num(p, "mantener", 0.8, 0.0, 10.0))


def _descender(k: _Constructor, p: dict) -> Plan:
    _expresivo(k, alcance=0.6, altura=0.9, elevacion=25.0, pinza=75.0, azimut=15.0)
    apice = _expresivo(k, lento=1.25, alcance=0.55, altura=0.12, elevacion=-35.0, pinza=22.0, giro=-15.0, azimut=8.0)
    return k.plan(apice, _num(p, "mantener", 0.8, 0.0, 10.0))


def _medir(k: _Constructor, p: dict) -> Plan:
    tam = _num(p, "tamano", 0.5, 0.0, 1.0)
    apertura = 8.0 + 88.0 * tam
    q, _ = pose_expresiva(k.ctx, 1.0, k.q[:5], False, alcance=0.6, altura=0.55, elevacion=0.0,
                          azimut=15.0, giro=0.0, pinza=apertura)
    apice = k.ir_apice(q)
    pulso = np.zeros(6)
    pulso[5] = -12.0 if tam > 0.5 else 12.0
    k.bulto(pulso, k.t + 0.15, 0.7)
    k.bulto(pulso * 0.7, k.t + 0.85, 0.7)
    k.t += 1.5
    return k.plan(apice, _num(p, "mantener", 0.4, 0.0, 10.0))


def _contrastar(k: _Constructor, p: dict) -> Plan:
    lado = p.get("lado")
    if lado not in (None, "a", "b"):
        raise ErrorGesto("'lado' debe ser \"a\", \"b\" o no indicarse (los dos, uno tras otro)")
    pausa = _num(p, "pausa", 0.7, 0.0, 5.0)
    a = dict(alcance=0.62, azimut=40.0, altura=0.55, elevacion=5.0, giro=32.0, pinza=72.0)
    b = dict(alcance=0.62, azimut=-22.0, altura=0.5, elevacion=5.0, giro=-32.0, pinza=72.0)
    if lado == "b":
        return k.plan(_expresivo(k, **b), 0.6)
    apice = _expresivo(k, **a)
    if lado is None:
        k.t += pausa
        _expresivo(k, **b)
    return k.plan(apice, 0.6)


def _suspender(k: _Constructor, p: dict) -> Plan:
    dur = _num(p, "duracion", 1.5, 0.3, 10.0)
    k.bulto(np.array([0.0, -4.0, -3.0, -6.0, 0.0, 10.0]) * (0.5 + k.cual.amplitud), k.t, dur * 2.0)
    k.t += dur
    return k.plan(dur * 0.9, 0.0)


def _presentar(k: _Constructor, p: dict) -> Plan:
    apice = _expresivo(k, alcance=0.72, azimut=_num(p, "azimut", 30.0, -60.0, 80.0), altura=0.55,
                       elevacion=10.0, giro=35.0, pinza=88.0)
    return k.plan(apice, _num(p, "mantener", 0.8, 0.0, 10.0))


def _recoger(k: _Constructor, p: dict) -> Plan:
    apice = _expresivo(k, alcance=0.12, azimut=-5.0, altura=0.45, elevacion=-35.0, giro=-10.0, pinza=24.0)
    return k.plan(apice, _num(p, "mantener", 0.6, 0.0, 10.0))


def _reposo(k: _Constructor, p: dict) -> Plan:
    apice = _expresivo(k, lento=1.4, escalar=False, **k.ctx.reposo)
    return k.plan(apice, 0.0)


def _gesto_libre(k: _Constructor, p: dict) -> Plan:
    poses = p.get("poses")
    if not isinstance(poses, (list, tuple)) or not 1 <= len(poses) <= 12:
        raise ErrorGesto("'poses' debe ser una lista de 1 a 12 poses clave")
    rangos = {"alcance": (0, 1), "azimut": (-90, 90), "altura": (0, 1), "elevacion": (-80, 80),
              "giro": (-150, 150), "pinza": (0, 100), "pausa": (0, 10), "lento": (0.5, 3)}
    apice = None
    for i, pose in enumerate(poses):
        if not isinstance(pose, dict):
            raise ErrorGesto(f"pose {i + 1}: debe ser un objeto con alcance, azimut, altura, elevacion, giro, pinza")
        desconocidas = set(pose) - set(rangos)
        if desconocidas:
            raise ErrorGesto(f"pose {i + 1}: campos desconocidos: {', '.join(sorted(desconocidas))}")
        vals = {c: _num(pose, c, NEUTRA.get(c, 0.0), *rangos[c]) for c in pose}
        pausa = vals.pop("pausa", 0.0)
        lento = vals.pop("lento", 1.0)
        t = _expresivo(k, lento=lento, escalar=False, **vals)
        apice = t if apice is None else apice
        k.t += pausa
    return k.plan(apice or 0.0, _num(p, "mantener", 0.5, 0.0, 10.0))


# ---------------------------------------------------------------- trayectoria compuesta (ER 2)
CLAVES_PUNTO = {"mira", "mundo", "alcance", "altura", "lado", "inclinacion", "giro", "pinza", "pausa",
                "duracion", "ancla", "circulo"}
RANGOS_PUNTO = {"alcance": (0.0, 1.0), "altura": (0.0, 1.0), "lado": (-90.0, 90.0), "inclinacion": (-80.0, 80.0),
                "giro": (-150.0, 150.0), "pinza": (0.0, 100.0), "pausa": (0.0, 10.0), "duracion": (0.2, 20.0)}
CLAVES_POSE = ("alcance", "altura", "lado", "inclinacion", "giro", "pinza")

PLANOS = ("frontal", "horizontal", "lateral")


def _circulo(k: _Constructor, spec: Any, q: np.ndarray, i: int) -> tuple[list[np.ndarray], np.ndarray]:
    """Giros de la mano a partir de una pose: devuelve las poses del recorrido y sus tiempos.

    plano: "frontal" (de cara, como limpiar un cristal), "horizontal" (como un lazo sobre la
    cabeza o remover) o "lateral" (hacia delante, como una rueda). `ratio` < 1 lo achata; 0 es
    un vaivén en línea."""
    if not isinstance(spec, dict):
        raise ErrorGesto(f"punto {i + 1}: 'circulo' debe ser un objeto, por ejemplo {{\"radio\": 0.6, \"vueltas\": 2}}")
    sobran = set(spec) - {"radio", "vueltas", "plano", "sentido", "ratio"}
    if sobran:
        raise ErrorGesto(f"punto {i + 1}: 'circulo' no admite: {', '.join(sorted(sobran))}")
    radio = 25.0 + 95.0 * _num(spec, "radio", 0.5, 0.0, 1.0)
    vueltas = _num(spec, "vueltas", 1.0, 0.25, 5.0)
    ratio = _num(spec, "ratio", 1.0, 0.0, 1.0)
    sentido = 1.0 if _num(spec, "sentido", 1.0, -1.0, 1.0) >= 0 else -1.0
    plano = str(spec.get("plano", "frontal"))
    if plano not in PLANOS:
        raise ErrorGesto(f"punto {i + 1}: 'plano' debe ser uno de: {', '.join(PLANOS)}")
    ctx, m = k.ctx, k.ctx.modelo
    adelante, fuera, arriba = np.array([1.0, 0, 0]), np.array([0, ctx.exterior, 0.0]), np.array([0, 0, 1.0])
    a1, a2 = {"frontal": (fuera, arriba), "horizontal": (fuera, adelante), "lateral": (adelante, arriba)}[plano]
    pos = m.punta(q[:5])[0]
    elev = m.elevacion(q[:5])
    centro = pos - radio * a1
    n = max(int(round(14 * vueltas)), 4)
    qs, semilla = [], q[:5]
    for j in range(1, n + 1):
        ang = sentido * 2.0 * math.pi * vueltas * j / n
        pt = centro + radio * (math.cos(ang) * a1 + ratio * math.sin(ang) * a2)
        try:
            q5 = m.inversa(pt, elev, q[4], semilla, tolerancia_mm=3.0)
        except FueraDeAlcance:
            raise ErrorGesto(f"punto {i + 1}: el giro no cabe ahí (prueba menos 'radio', otro 'plano' o una "
                             f"pose menos extendida)") from None
        semilla = q5
        qs.append(np.append(q5, q[5]))
    periodo = 1.7 * k.din.factor_duracion / k.ctx.tempo            # segundos por vuelta: relajado
    return qs, np.full(n, periodo * vueltas / n)



def _trayectoria(k: _Constructor, p: dict) -> Plan:
    """Movimiento compuesto punto a punto por quien lo pide (ER 2). No hay formas prefijadas:
    aquí solo se unen los puntos clave con suavidad.

    Cada punto clave es, o bien 'mira' ([y, x] de la obra: el brazo apunta ahí), o bien una pose
    en el aire (alcance, altura, lado, inclinacion, giro, pinza). Entre dos 'mira' seguidos sin
    pausa, la punta recorre la línea sobre la obra.
    """
    puntos = p.get("puntos")
    if not isinstance(puntos, (list, tuple)) or not 1 <= len(puntos) <= 16:
        raise ErrorGesto("'puntos' debe ser una lista de 1 a 16 puntos clave")
    repetir = int(_num(p, "repetir", 1, 1, 6))
    if repetir > 1:                 # un ciclo que se repite (las anclas solo cuentan la primera vez)
        ciclo = [{c: x for c, x in pc.items() if c != "ancla"} if isinstance(pc, dict) else pc for pc in puntos]
        puntos = (list(puntos) + ciclo * (repetir - 1))[:32]
    ctx = k.ctx
    datos: list[dict] = []
    semilla = k.q[:5]
    for i, pc in enumerate(puntos):
        if not isinstance(pc, dict):
            raise ErrorGesto(f"punto {i + 1}: debe ser un objeto con 'mira' o con una pose en el aire")
        sobran = set(pc) - CLAVES_PUNTO
        if sobran:
            raise ErrorGesto(f"punto {i + 1}: campos desconocidos: {', '.join(sorted(sobran))}. "
                             f"Admitidos: {', '.join(sorted(CLAVES_PUNTO))}")
        v = {c: _num(pc, c, 0.0, *RANGOS_PUNTO[c]) for c in pc if c in RANGOS_PUNTO}
        if "mira" not in pc and ctx.exageracion != 1.0:
            # Como un actor: la pose se aleja de la neutra más de lo pedido (dentro de su rango).
            for c, neutro in (("alcance", NEUTRA["alcance"]), ("altura", NEUTRA["altura"]), ("lado", 0.0),
                              ("inclinacion", NEUTRA["elevacion"]), ("pinza", 50.0), ("giro", 0.0)):
                if c in v:
                    v[c] = float(np.clip(neutro + ctx.exageracion * (v[c] - neutro), *RANGOS_PUNTO[c]))
        yx = None
        try:
            if "mira" in pc:
                yx = _punto(pc, "mira")
                q = pose_apuntar(ctx, ctx.cuadro.punto_mundo(yx), 0.45 + 0.5 * v.get("alcance", 0.8),
                                 v.get("giro", 0.0) * ctx.exterior, v.get("pinza", 10.0), semilla)
            elif "mundo" in pc:          # posición de la mano en el espacio común de los dos brazos
                destino = ctx.marco.a_base(np.array(pc["mundo"], float))
                neutro = np.array([ctx.modelo.eje_pan[0] + 200.0, 0.0, 180.0])
                q = None
                for s in (1.0, 0.85, 0.7, 0.55, 0.4):
                    try:
                        q5 = ctx.modelo.inversa(neutro + s * (destino - neutro), v.get("inclinacion", 0.0),
                                                v.get("giro", 0.0) * ctx.exterior, semilla)
                        q = np.append(q5, v.get("pinza", 50.0))
                        if s < 1.0:
                            k.avisos.append(f"punto {i + 1}: posición acercada para que el brazo llegue")
                        break
                    except FueraDeAlcance:
                        continue
                if q is None:
                    raise FueraDeAlcance("la mano no llega a esa posición")
            elif any(c in pc for c in CLAVES_POSE):
                q, recortada = pose_expresiva(
                    ctx, 1.0, semilla, False, alcance=v.get("alcance", NEUTRA["alcance"]),
                    azimut=v.get("lado", 0.0), altura=v.get("altura", NEUTRA["altura"]),
                    elevacion=v.get("inclinacion", NEUTRA["elevacion"]), giro=v.get("giro", 0.0),
                    pinza=v.get("pinza", NEUTRA["pinza"]))
                if recortada:
                    k.avisos.append(f"punto {i + 1}: pose reducida para que el brazo la alcance")
            else:
                raise ErrorGesto(f"punto {i + 1}: indica 'mira' ([y, x]) o una pose en el aire "
                                 f"({', '.join(CLAVES_POSE)})")
        except FueraDeAlcance as e:
            raise ErrorGesto(f"punto {i + 1}: fuera de alcance: {e}") from None
        semilla = q[:5]
        dato = {"q": q, "yx": yx, "v": v, "pausa": v.get("pausa", 0.0), "dur": v.get("duracion")}
        if "circulo" in pc:
            dato["circulo"] = _circulo(k, pc["circulo"], q, i)
            semilla = dato["circulo"][0][-1][:5]
        datos.append(dato)

    # Entre dos 'mira' seguidos sin pausa: recorrido continuo sobre la obra.
    for i in range(1, len(datos)):
        a, b = datos[i - 1], datos[i]
        if a["yx"] is None or b["yx"] is None or a["pausa"] > 0:
            continue
        mundo = np.array([ctx.cuadro.punto_mundo(a["yx"]), ctx.cuadro.punto_mundo(b["yx"])])
        if float(np.linalg.norm(mundo[1] - mundo[0])) < 15.0:
            continue
        mundo = _remuestrear(mundo, 28.0, minimo=3)
        qs, sem = [], a["q"][:5]
        for j, pt in enumerate(mundo[1:], start=1):
            s = j / (len(mundo) - 1)
            mezcla = {c: a["v"].get(c, d) + s * (b["v"].get(c, d) - a["v"].get(c, d))
                      for c, d in (("alcance", 0.8), ("giro", 0.0), ("pinza", 10.0))}
            try:
                q = pose_apuntar(ctx, pt, 0.45 + 0.5 * mezcla["alcance"], mezcla["giro"] * ctx.exterior,
                                 mezcla["pinza"], sem)
            except FueraDeAlcance as e:
                raise ErrorGesto(f"entre los puntos {i} y {i + 1}: fuera de alcance: {e}") from None
            sem = q[:5]
            qs.append(q)
        dts = _tiempos(mundo, 170.0 / k.din.factor_duracion)
        if b["dur"]:
            dts = dts * (b["dur"] / float(np.sum(dts)))
        b["camino"], b["q"] = (qs, dts), qs[-1]

    def construir(lentos: list[float], esperas: list[float]) -> tuple[_Constructor, list[float]]:
        c = _Constructor(ctx, k.cual)
        llegadas = []
        for i, d in enumerate(datos):
            c.t += esperas[i]
            if "camino" in d:
                qs, dts = d["camino"]
                llegada = c.camino(qs, dts * lentos[i])
            else:
                t0, dur = c.ir(d["q"], lento=lentos[i], dur=d["dur"] * lentos[i] if d["dur"] else None)
                llegada = t0 + dur * fraccion_inversa(0.78, c.din.c) + float(c.din.retardos[3])
                if (i < len(datos) - 1 or "circulo" in d) and d["pausa"] == 0:
                    c.t = t0 + 0.65 * dur          # sin pausa: el siguiente tramo empieza antes de frenar
            if "circulo" in d:
                qs_c, dts_c = d["circulo"]
                c.camino(qs_c, dts_c * lentos[i])
            c.t += d["pausa"]
            llegadas.append(llegada)
        return c, llegadas

    n = len(datos)
    c, llegadas = construir([1.0] * n, [0.0] * n)
    tiempos = {int(i): float(t) for i, t in (p.get("_tiempos") or {}).items() if 0 <= int(i) < n}
    anclados = sorted(tiempos)
    if len(anclados) >= 2:          # varios puntos anclados a palabras: se ajusta el ritmo entre ellos
        lentos, esperas = [1.0] * n, [0.0] * n
        for a, b in zip(anclados, anclados[1:]):
            natural, pedido = llegadas[b] - llegadas[a], tiempos[b] - tiempos[a]
            if natural > 0.05 and pedido > natural:
                f = min(pedido / natural, 2.5)
                for i in range(a + 1, b + 1):
                    lentos[i] = f
                esperas[a + 1] += max(pedido - natural * f, 0.0)
        c, llegadas = construir(lentos, esperas)
    k.tramos, k.q, k.t, k.avisos = c.tramos, c.q, c.t, k.avisos + c.avisos
    return k.plan(llegadas[anclados[0] if anclados else 0], _num(p, "mantener", 0.3, 0.0, 10.0))


def preparar_anclas(g: Gesto, tiempo_de_palabra: Callable[[int], float]) -> None:
    """En una trayectoria con puntos anclados a palabras: ancla el gesto a su primer punto
    anclado y anota cuándo deben alcanzarse los demás (segundos respecto al primero)."""
    if g.tipo != "trayectoria":
        return
    anclas = [(i, int(pc["ancla"])) for i, pc in enumerate(g.params.get("puntos") or [])
              if isinstance(pc, dict) and isinstance(pc.get("ancla"), (int, float)) and not isinstance(pc.get("ancla"), bool)]
    if not anclas:
        return
    g.ancla = anclas[0][1]
    t0 = tiempo_de_palabra(anclas[0][1])
    g.params["_tiempos"] = {i: tiempo_de_palabra(a) - t0 for i, a in anclas}


GESTOS: dict[str, Callable[[_Constructor, dict], Plan]] = {
    "trayectoria": _trayectoria,
    "senalar": _senalar, "trazar": _trazar, "abarcar": _abarcar, "dibujar_forma": _dibujar_forma,
    "ondular": _ondular, "elevar": _elevar, "descender": _descender, "medir": _medir,
    "contrastar": _contrastar, "suspender": _suspender, "presentar": _presentar, "recoger": _recoger,
    "reposo": _reposo, "gesto_libre": _gesto_libre,
}
ALIAS = {"señalar": "senalar", "forma": "dibujar_forma", "libre": "gesto_libre", "casa": "reposo"}
PARAMS: dict[str, set[str]] = {
    "senalar": {"punto", "mantener"}, "trazar": {"puntos", "duracion"},
    "abarcar": {"desde", "hasta", "duracion"},
    "dibujar_forma": {"forma", "centro", "tamano", "vueltas", "plano", "duracion", "lateral"},
    "ondular": {"desde", "hasta", "ondas", "altura", "tamano", "duracion", "lateral"},
    "elevar": {"mantener"}, "descender": {"mantener"}, "medir": {"tamano", "mantener"},
    "contrastar": {"lado", "pausa"}, "suspender": {"duracion"}, "presentar": {"azimut", "mantener"},
    "recoger": {"mantener"}, "reposo": set(), "gesto_libre": {"poses", "mantener"},
    "trayectoria": {"puntos", "mantener", "repetir", "_tiempos"},
}


def tipo_canonico(tipo: str) -> str:
    t = ALIAS.get(tipo.strip().lower(), tipo.strip().lower())
    if t not in GESTOS:
        raise ErrorGesto(f"gesto desconocido: '{tipo}'. Disponibles: {', '.join(sorted(GESTOS))}")
    return t


def planificar(gesto: Gesto, ctx: Contexto, cual: Cualidades) -> Plan:
    """Convierte un gesto en un plan. Lanza ErrorGesto con un mensaje comprensible."""
    tipo = tipo_canonico(gesto.tipo)
    sobran = set(gesto.params) - PARAMS[tipo]
    if sobran:
        raise ErrorGesto(f"{tipo}: parámetros desconocidos: {', '.join(sorted(sobran))}. "
                         f"Admitidos: {', '.join(sorted(PARAMS[tipo])) or 'ninguno'}")
    try:
        return GESTOS[tipo](_Constructor(ctx, cual), gesto.params)
    except FueraDeAlcance as e:
        raise ErrorGesto(f"{tipo}: fuera de alcance: {e}") from None
