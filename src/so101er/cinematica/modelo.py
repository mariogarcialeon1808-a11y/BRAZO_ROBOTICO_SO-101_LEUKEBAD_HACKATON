"""Cinemática directa e inversa del SO-101 a partir de su URDF oficial.

Unidades: grados para las articulaciones, milímetros para las posiciones.
El vector de articulaciones es (shoulder_pan, shoulder_lift, elbow_flex,
wrist_flex, wrist_roll); la pinza no interviene en la cinemática.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ARTICULACIONES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
RUTA_URDF = Path(__file__).with_name("so101.urdf")


class FueraDeAlcance(Exception):
    """El punto pedido no es alcanzable por el brazo."""


def _rot_rpy(r: float, p: float, y: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


def _transformacion(xyz: list[float], rpy: list[float]) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = _rot_rpy(*rpy)
    t[:3, 3] = np.array(xyz) * 1000.0  # metros → milímetros
    return t


class Cinematica:
    """Modelo cinemático de un SO-101 (en el sistema de su propia base)."""

    def __init__(self, ruta_urdf: Path | None = None) -> None:
        raiz = ET.parse(ruta_urdf or RUTA_URDF).getroot()
        por_nombre = {j.get("name"): j for j in raiz.findall("joint")}
        self._origenes: list[np.ndarray] = []
        inf, sup = [], []
        for nombre in ARTICULACIONES:
            j = por_nombre[nombre]
            o = j.find("origin")
            self._origenes.append(_transformacion(
                [float(v) for v in o.get("xyz").split()], [float(v) for v in o.get("rpy").split()]))
            lim = j.find("limit")
            inf.append(math.degrees(float(lim.get("lower"))))
            sup.append(math.degrees(float(lim.get("upper"))))
        o = por_nombre["gripper_frame_joint"].find("origin")
        self._punta = _transformacion(
            [float(v) for v in o.get("xyz").split()], [float(v) for v in o.get("rpy").split()])
        self.lim_inf = np.array(inf)
        self.lim_sup = np.array(sup)
        # Eje de giro del hombro (pan) y altura del hombro, en la base.
        self.eje_pan = self._origenes[0][:3, 3].copy()
        self.hombro = self.puntos(np.zeros(5))[2].copy()
        self.hombro[:2] = self.eje_pan[:2]
        # Extensión máxima útil hombro → punta.
        self.alcance_max = self._medir_alcance()

    # ------------------------------------------------------------------ directa
    def marcos(self, q: np.ndarray) -> list[np.ndarray]:
        """Transformaciones base→articulación (tras girar) y, al final, base→punta."""
        t = np.eye(4)
        salida = []
        for origen, ang in zip(self._origenes, q[:5]):
            a = math.radians(float(ang))
            c, s = math.cos(a), math.sin(a)
            giro = np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1.0]])
            t = t @ origen @ giro
            salida.append(t)
        salida.append(t @ self._punta)
        return salida

    def puntos(self, q: np.ndarray) -> np.ndarray:
        """Puntos de la cadena: base, 5 articulaciones y punta. Forma (7, 3), en mm."""
        ms = self.marcos(q)
        return np.vstack([np.zeros(3)] + [m[:3, 3] for m in ms])

    def punta(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posición de la punta (mm) y eje de la herramienta (unitario, hacia fuera)."""
        m = self.marcos(q)[-1]
        return m[:3, 3].copy(), m[:3, 2].copy()

    def elevacion(self, q: np.ndarray) -> float:
        """Ángulo de la herramienta sobre la horizontal, en grados."""
        return math.degrees(math.asin(float(np.clip(self.punta(q)[1][2], -1, 1))))

    def _medir_alcance(self) -> float:
        mejor = 0.0
        for lift in np.linspace(self.lim_inf[1], self.lim_sup[1], 15):
            for codo in np.linspace(self.lim_inf[2], self.lim_sup[2], 15):
                for mun in np.linspace(self.lim_inf[3], self.lim_sup[3], 9):
                    p, _ = self.punta(np.array([0, lift, codo, mun, 0.0]))
                    mejor = max(mejor, float(np.linalg.norm(p - self.hombro)))
        return mejor

    # ------------------------------------------------------------------ inversa
    def _residuo_y_jacobiano(self, q: np.ndarray, pos: np.ndarray, elev: float | None,
                             peso: float) -> tuple[np.ndarray, np.ndarray]:
        """Residuo (mm; la elevación en grados × peso) y su jacobiano analítico respecto a las
        cuatro primeras articulaciones (por grado). Una sola cinemática directa por llamada."""
        ms = self.marcos(q)
        punta, eje = ms[-1][:3, 3], ms[-1][:3, 2]
        r = list(punta - pos)
        jac = np.zeros((4 if elev is not None else 3, 4))
        k = math.pi / 180.0
        for i in range(4):
            z = ms[i][:3, 2]
            jac[:3, i] = np.cross(z, punta - ms[i][:3, 3]) * k
        if elev is not None:
            seno = float(np.clip(eje[2], -0.9999, 0.9999))
            r.append(peso * (math.degrees(math.asin(seno)) - elev))
            coseno = math.sqrt(1.0 - seno * seno)
            for i in range(4):
                jac[3, i] = peso * float(np.cross(ms[i][:3, 2], eje)[2]) / coseno
        return np.array(r), jac

    def _resolver(self, q0: np.ndarray, pos: np.ndarray, elev: float | None, peso: float,
                  iteraciones: int = 80) -> tuple[np.ndarray, float]:
        q = np.clip(np.asarray(q0, float).copy(), self.lim_inf, self.lim_sup)
        lam = 1.0
        r, jac = self._residuo_y_jacobiano(q, pos, elev, peso)
        coste = float(r @ r)
        for _ in range(iteraciones):
            if coste < 1e-4:
                break
            mejora = False
            for _ in range(8):
                paso = np.linalg.solve(jac.T @ jac + lam * np.eye(4), -jac.T @ r)
                norma = float(np.linalg.norm(paso))
                if norma > 20.0:
                    paso *= 20.0 / norma
                q2 = q.copy()
                q2[:4] = np.clip(q[:4] + paso, self.lim_inf[:4], self.lim_sup[:4])
                r2, jac2 = self._residuo_y_jacobiano(q2, pos, elev, peso)
                c2 = float(r2 @ r2)
                if c2 < coste:
                    q, r, jac, coste = q2, r2, jac2, c2
                    lam = max(lam * 0.4, 1e-4)
                    mejora = True
                    break
                lam *= 4.0
            if not mejora:
                break
        err_pos = float(np.linalg.norm(self.punta(q)[0] - pos))
        return q, err_pos

    def inversa(self, pos: np.ndarray, elevacion: float | None = None, giro: float = 0.0,
                semilla: np.ndarray | None = None, peso_elevacion: float = 0.6,
                tolerancia_mm: float = 1.5) -> np.ndarray:
        """Articulaciones (5) que llevan la punta a `pos` (mm, sistema de la base).

        `elevacion` (grados) es un objetivo blando para la inclinación de la
        herramienta; la posición tiene prioridad. Lanza FueraDeAlcance si no
        hay solución dentro de la tolerancia.
        """
        pos = np.asarray(pos, float)
        giro = float(np.clip(giro, self.lim_inf[4], self.lim_sup[4]))
        pan = math.degrees(math.atan2(pos[1] - self.eje_pan[1], pos[0] - self.eje_pan[0]))
        semillas = []
        if semilla is not None:
            semillas.append(np.asarray(semilla, float)[:5].copy())
        # El signo de pan en el modelo es opuesto al azimut geométrico.
        for lift, codo, mun in ((0, 0, 0), (-40, 40, 30), (30, -30, 0), (-70, 80, 40), (40, 40, -60)):
            semillas.append(np.array([-pan, lift, codo, mun, giro], float))
        mejor_q, mejor_err = None, float("inf")
        for s in semillas:
            s = s.copy()
            s[4] = giro
            for elev in ((elevacion, None) if elevacion is not None else (None,)):
                q, err = self._resolver(s, pos, elev, peso_elevacion)
                if err < tolerancia_mm:
                    return q
                if err < mejor_err:
                    mejor_q, mejor_err = q, err
        raise FueraDeAlcance(
            f"punto ({pos[0]:.0f}, {pos[1]:.0f}, {pos[2]:.0f}) mm fuera del alcance del brazo "
            f"(error mínimo {mejor_err:.0f} mm)")
