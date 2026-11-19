"""Compilador local de gestos semánticos. Sin red, simulador ni E/S de motores.

Entradas: consignas, posiciones de encoders (grados y pinza %) y calibración.
La salida es una trayectoria nominal verificable; no certifica el montaje físico.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from ..cinematica.modelo import Cinematica, FueraDeAlcance
from ..config import Config
from ..geometria import Cuadro, Marco
from .seguridad import BrazoSeguro, Seguridad


def vector(x, n, nombre):
    a = np.asarray(x, dtype=float)
    if a.shape != (n,) or not np.isfinite(a).all():
        raise ValueError(f"{nombre}: se requieren {n} valores finitos")
    return a.copy()


def unidad(x):
    x = vector(x, 3, "dirección")
    if np.linalg.norm(x) < 1e-8:
        raise ValueError("dirección nula")
    return x / np.linalg.norm(x)


TOLERANCIA_INICIO = 1.0   # grados (y % de pinza) que un encoder de partida puede exceder el límite nominal


def inicio_nominal(modelo, encoders):
    """Postura de partida medida, llevada al límite nominal si lo excede por ruido.

    Un brazo real apoyado en su tope mide décimas de grado más allá del límite del URDF
    (una cuenta de encoder son 0,09°). Rechazarlo dejaba la sesión entera sin gestos.
    Más allá de la tolerancia sigue siendo un error: no se planifica desde una pose imposible.
    """
    q = vector(encoders, 6, "encoders")
    exceso = max(float(np.max(modelo.lim_inf - q[:5])), float(np.max(q[:5] - modelo.lim_sup)),
                 float(-q[5]), float(q[5] - 100))
    if exceso > TOLERANCIA_INICIO:
        raise ValueError("encoders fuera de límites nominales")
    q[:5] = np.clip(q[:5], modelo.lim_inf, modelo.lim_sup)
    q[5] = np.clip(q[5], 0, 100)
    return q


@dataclass(frozen=True)
class Intencion:
    """Posiciones en mm del mundo calibrado; el eje de pinza es independiente.

    referencia indica si son coordenadas expresivas o un plano calibrado.
    Ninguna coordenada se interpreta como profundidad medida por un VLM.
    """
    tipo: str
    brazo: str
    puntos_mm: tuple
    ejes: tuple
    duracion_s: float = 2.0
    mantener_s: float = 0.35
    pinza: float = 35.0
    referencia: str = "expresivo"
    ancla: int = 0
    preparacion_s: float = 1.5
    pinzas: tuple = ()  # apertura por punto, 0 cerrado / 100 abierto
    perfil_tiempo: tuple = ()  # progreso humano normalizado; vacío = perfil procedural


@dataclass
class Trayectoria:
    tiempos: np.ndarray
    q: dict[str, np.ndarray]
    inicio_trazo: float
    fin_trazo: float
    intencion: Intencion
    error_posicion_mm: float
    error_eje_grados: float
    inicio_retorno: float | None = None
    reposo_al_final: bool = False

    def muestra(self, t: float) -> dict[str, np.ndarray]:
        """Lectura causal desde el reloj de reproducción. Mantiene extremos."""
        if not math.isfinite(t):
            raise ValueError("tiempo no finito")
        return {n: np.array([np.interp(t, self.tiempos, a[:, j])
                             for j in range(6)]) for n, a in self.q.items()}


class MotorGestos:
    def __init__(self, cfg: Config, modelo: Cinematica | None = None):
        self.cfg = cfg
        self.modelo = modelo or Cinematica()
        self.marcos = {n: Marco(b.base_mm, b.orientacion_grados)
                       for n, b in cfg.brazos.items() if n in cfg.brazos_activos}
        self.cuadro = Cuadro(cfg.cuadro.sup_izq, cfg.cuadro.sup_der, cfg.cuadro.inf_izq,
                             lado_brazos=np.mean([m.pos for m in self.marcos.values()], axis=0))
        self.seguridad = Seguridad(cfg.limites, self.cuadro, cfg.cuadro.separacion_min_mm,
                                  {n: BrazoSeguro(self.modelo, m) for n, m in self.marcos.items()},
                                  cfg.zona_compartida)

    def inversa_eje(self, posicion, eje, semilla):
        """IK con tolerancias explícitas. Nunca descarta la orientación en silencio.

        La rotación alrededor del propio eje no se prescribe (5 GDL del SO-101).
        """
        p, eje = vector(posicion, 3, "posición"), unidad(eje)
        semilla = vector(semilla, 5, "semilla")
        m = self.modelo
        def residuo(q):
            pos, direction = m.punta(q)
            return np.r_[pos - p, 90.0 * (direction - eje)]
        seeds = [semilla]
        try:
            seeds.append(m.inversa(p, None, semilla[4], semilla))
        except FueraDeAlcance:
            pass
        for seed in seeds:
            q = seed.copy()
            for _ in range(100):
                r = residuo(q)
                jac = np.column_stack([(residuo(q + np.eye(5)[i] * .02) - r) / .02
                                       for i in range(4)])
                step = np.linalg.solve(jac.T @ jac + .1 * np.eye(4), -jac.T @ r)
                step *= min(1., 10. / max(np.linalg.norm(step), 1e-8))
                improved = False
                for scale in (1., .5, .2, .05):
                    new = q.copy()
                    new[:4] = np.clip(q[:4] + scale * step, m.lim_inf[:4], m.lim_sup[:4])
                    if np.linalg.norm(residuo(new)) < np.linalg.norm(r):
                        q, improved = new, True
                        break
                pos, direction = m.punta(q)
                ep = np.linalg.norm(pos - p)
                ea = np.degrees(np.arccos(np.clip(direction @ eje, -1, 1)))
                if ep <= 2.0 and ea <= 3.0:
                    return q
                if not improved:
                    break
        raise FueraDeAlcance("posición y eje incompatibles con el SO-101; modifica el gesto")

    def compilar(self, g: Intencion, encoders: dict[str, np.ndarray]) -> Trayectoria:
        if g.brazo not in self.marcos or set(encoders) != set(self.marcos):
            raise ValueError("se requieren encoders de todos los brazos activos")
        if g.tipo not in ("extension", "senalar", "recorrer"):
            raise ValueError("intención desconocida")
        if g.referencia not in ("expresivo", "plano_calibrado"):
            raise ValueError("referencia desconocida")
        if not isinstance(g.ancla, int) or isinstance(g.ancla, bool) or g.ancla < 0:
            raise ValueError("ancla debe ser un índice de palabra no negativo")
        if not (math.isfinite(g.duracion_s) and .3 <= g.duracion_s <= 20
                and math.isfinite(g.mantener_s) and 0 <= g.mantener_s <= 10
                and math.isfinite(g.pinza) and 0 <= g.pinza <= 100):
            raise ValueError("duración, sostenido o pinza fuera de rango")
        if not 2 <= len(g.puntos_mm) <= 128 or len(g.ejes) != len(g.puntos_mm):
            raise ValueError("se requieren 2–128 puntos con sus ejes")
        puntos = np.array([vector(p, 3, "punto") for p in g.puntos_mm])
        ejes = np.array([unidad(e) for e in g.ejes])
        pinzas = np.asarray(g.pinzas, float) if len(g.pinzas) else np.full(len(puntos),g.pinza)
        if pinzas.shape != (len(puntos),) or not np.isfinite(pinzas).all() or (pinzas<0).any() or (pinzas>100).any():
            raise ValueError("perfil de pinza inválido")
        initial = {n: inicio_nominal(self.modelo, q) for n, q in encoders.items()}
        marco = self.marcos[g.brazo]
        # La continuidad de rama parte del encoder, no de una pose interna del simulador.
        seed = initial[g.brazo][:5]
        keys = []
        for index, (p, e) in enumerate(zip(puntos, ejes)):
            if index == 0 or not (np.array_equal(p, puntos[index-1]) and np.array_equal(e, ejes[index-1])):
                seed = self.inversa_eje(marco.a_base(p), marco.dir_a_base(e), seed)
            keys.append(np.r_[seed, pinzas[index]])
        keys = np.array(keys)
        # Hermite cúbico por puntos, con tangentes compartidas: sin detenerse en cada punto.
        # Quintica en el reloj global del trazo: entrada/salida con velocidad y aceleración cero.
        profile = np.asarray(g.perfil_tiempo, float)
        if profile.size:
            from .referencias import validar_perfil
            profile = validar_perfil(profile)
        def phase(u):
            w = u**3 * (10 + u * (-15 + 6*u))
            if profile.size:
                # Bernstein monótono: conserva el ritmo sin quiebros de una interpolación lineal.
                w = sum(math.comb(16,i) * profile[i] * w**i * (1-w)**(16-i) for i in range(17))
            return w
        def stroke(u):
            w = phase(u)
            x = np.minimum(w * (len(keys) - 1), len(keys) - 1 - 1e-10)
            i = x.astype(int); s = (x - i)[:, None]
            tang = np.empty_like(keys)
            tang[1:-1] = (keys[2:] - keys[:-2]) / 2
            tang[0], tang[-1] = keys[1]-keys[0], keys[-1]-keys[-2]
            result = ((2*s**3-3*s**2+1)*keys[i] + (s**3-2*s**2+s)*tang[i]
                    + (-2*s**3+3*s**2)*keys[i+1] + (s**3-s**2)*tang[i+1])
            result[:,5] = np.clip(result[:,5],0,100)
            return result
        if not np.isfinite(g.preparacion_s) or not .3 <= g.preparacion_s <= 5:
            raise ValueError("preparación fuera de rango")
        prep, duration = g.preparacion_s, g.duracion_s
        hz = float(self.cfg.frecuencia_hz)
        if not math.isfinite(hz) or not 20 <= hz <= 200:
            raise ValueError("frecuencia de compilación fuera de 20–200 Hz")
        # Retiming global: ninguna capa posterior altera el significado del trazo.
        for _ in range(8):
            if (prep + duration + g.mantener_s) * hz > 20000:
                raise ValueError("trayectoria demasiado larga; divide la expresión en bloques")
            tp = np.linspace(0, prep, math.ceil(prep*hz)+1)
            ts = np.linspace(0, duration, math.ceil(duration*hz)+1)
            th = np.linspace(0, max(g.mantener_s, 1/hz), max(2, math.ceil(g.mantener_s*hz)+1))
            u = tp[:, None] / prep
            smooth = phase(u) if g.tipo == "senalar" else u**3 * (10 + u*(-15 + 6*u))
            qa = np.vstack([initial[g.brazo] + smooth*(keys[0]-initial[g.brazo]),
                            stroke(ts[1:]/duration), np.repeat(keys[-1][None], len(th)-1, axis=0)])
            times = np.r_[tp, prep+ts[1:], prep+duration+th[1:]]
            v = np.diff(qa, axis=0)/np.diff(times)[:, None]
            a = np.diff(v, axis=0)/np.diff((times[1:]+times[:-1])/2)[:, None]
            j = np.diff(a, axis=0)/np.diff(times[1:-1])[:, None]
            lim = self.cfg.limites
            factor = max(1., float(np.max(abs(v)/lim.velocidad)),
                         float(np.max(abs(a)/lim.aceleracion))**.5,
                         float(np.max(abs(j)/lim.tiron))**(1/3))
            if factor <= 1.001:
                break
            prep *= factor*1.08; duration *= factor*1.08
        else:
            raise ValueError("no se pudo ajustar el tiempo a los límites")
        # Comprueba también el INTERIOR de la interpolación, no solo los puntos IK.
        # Referencia espacial: polilínea solicitada con orientación interpolada.
        # Si la interpolación articular se aparta demasiado, se rechaza; no se oculta.
        for u, qsample in zip(ts/duration, stroke(ts/duration)):
            w = phase(u)
            x = min(w*(len(keys)-1), len(keys)-1-1e-10)
            i, s = int(x), x-int(x)
            wanted_p = (1-s)*puntos[i]+s*puntos[i+1]
            wanted_e = unidad((1-s)*ejes[i]+s*ejes[i+1])
            actual_p, actual_e = self.modelo.punta(qsample[:5])
            ep = np.linalg.norm(marco.a_mundo(actual_p)-wanted_p)
            ea = np.degrees(np.arccos(np.clip(marco.dir_a_mundo(actual_e)@wanted_e,-1,1)))
            if ep > 5 or ea > 5:
                raise ValueError("interpolación alejada del gesto: añade puntos o cambia el diseño")
        q = {n: qa if n == g.brazo else np.repeat(initial[n][None], len(times), axis=0)
             for n in self.marcos}
        # Verifica el recorrido completo de AMBOS brazos, sin tolerancias que relajen límites.
        for k in range(len(times)):
            cadenas = {}
            for n in self.marcos:
                if ((q[n][k,:5] < self.modelo.lim_inf).any()
                        or (q[n][k,:5] > self.modelo.lim_sup).any()):
                    raise ValueError(f"trayectoria rechazada ({n}): límite articular")
                cadenas[n] = self.seguridad.cadena_mundo(n, q[n][k])
                problema = self.seguridad.problema_pose(n, q[n][k], cadenas[n])
                if problema or not 0 <= q[n][k, 5] <= 100:
                    raise ValueError(f"trayectoria rechazada ({n}): {problema or 'pinza'}")
            problema = self.seguridad.problema_par(cadenas)
            if problema:
                raise ValueError(f"trayectoria rechazada: {problema}")
        # Error de los puntos solicitados (el informe no confunde esta métrica con seguimiento real).
        actual = [self.modelo.punta(k[:5]) for k in keys]
        ep = max(np.linalg.norm(marco.a_mundo(p)-target) for (p, _), target in zip(actual, puntos))
        ea = max(np.degrees(np.arccos(np.clip(marco.dir_a_mundo(e)@target, -1, 1)))
                 for (_, e), target in zip(actual, ejes))
        return Trayectoria(times, q, prep, prep+duration, g, float(ep), float(ea))


def ejemplos(motor: MotorGestos):
    """Cuatro consignas explícitas y parametrizables; no es un clasificador de lenguaje.

    El marco expresivo es nominal. Los fixtures iniciales NO son sensores reales.
    Cada demo deja el otro brazo en apoyo estable; ambos se validan conjuntamente.
    """
    m = motor.modelo
    # Pose de apoyo alcanzable, expresada en los ángulos nominales del URDF.
    apoyo = motor.inversa_eje([m.eje_pan[0]+235., 0., 180.], [1., 0., 0.], np.zeros(5))
    initial = {n: np.r_[apoyo, 35.] for n in motor.marcos}
    result = []
    for nombre, tipo, z, brazo in (("paisaje", "extension", 180., "izq"),
                                   ("cielo", "extension", 265., "der"),
                                   ("punto", "senalar", 220., "der"),
                                   ("camino", "recorrer", 220., "izq")):
        if brazo not in motor.marcos:
            brazo = next(iter(motor.marcos))
        marco = motor.marcos[brazo]
        if tipo == "senalar":
            # Rayo a un punto DEL PLANO nominal, con posición y eje coherentes.
            target = motor.cuadro.punto_mundo([260, 720])
            local = marco.a_base(target)
            direction = unidad(local - m.hombro)
            p = m.hombro + direction*250.
            ps = np.repeat(p[None], 2, axis=0)
            es = np.repeat(direction[None], 2, axis=0)
        else:
            # Extensión: abanico en horizontal, elevado para cielo.
            # Camino: recta radial y cabezal PARALELO al recorrido.
            t = np.linspace(-1, 1, 25)
            if tipo == "recorrer":
                ps = np.column_stack([m.eje_pan[0]+235+15*t, np.zeros_like(t), np.full_like(t, z)])
                es = np.repeat([[1., 0., 0.]], len(t), axis=0)
            else:
                angles = np.radians(22*t)
                ps = np.column_stack([m.eje_pan[0]+235*np.cos(angles), 235*np.sin(angles), np.full_like(t, z)])
                elevation = math.radians(30 if nombre == "cielo" else 0)
                es = np.column_stack([np.cos(angles)*math.cos(elevation),
                                      np.sin(angles)*math.cos(elevation),
                                      np.full_like(t, math.sin(elevation))])
        g = Intencion(tipo, brazo, tuple(map(tuple, marco.a_mundo(ps))),
                      tuple(map(tuple, marco.dir_a_mundo(es))),
                      duracion_s=2.5, mantener_s=.7 if tipo == "senalar" else .3,
                      pinza=12. if tipo == "senalar" else 55.,
                      referencia="plano_calibrado" if tipo == "senalar" else "expresivo", ancla=2)
        result.append((nombre, g, {n:q.copy() for n,q in initial.items()}))
    return result



