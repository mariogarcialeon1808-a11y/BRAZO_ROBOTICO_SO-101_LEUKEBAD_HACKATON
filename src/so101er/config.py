"""Carga y validación de la configuración. Los errores se dan en español."""
from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .control.cualidades import ESTILOS_BASE, Cualidades

NOMBRES_BRAZO = ("izq", "der")
RUTA_PREDETERMINADA = Path(__file__).with_name("predeterminado.toml")


class ErrorConfig(Exception):
    """La configuración no es válida."""


@dataclass
class ConfigBrazo:
    nombre: str
    puerto: str
    base_mm: np.ndarray
    orientacion_grados: float
    signo: np.ndarray
    desfase_grados: np.ndarray


@dataclass
class ConfigCuadro:
    sup_izq: np.ndarray
    sup_der: np.ndarray
    inf_izq: np.ndarray
    separacion_min_mm: float
    imagen: str


@dataclass
class Limites:
    velocidad: np.ndarray
    aceleracion: np.ndarray
    tiron: np.ndarray
    altura_min_mm: float
    distancia_min_brazos_mm: float
    temperatura_max_c: float
    carga_max: float
    error_seguimiento_max_grados: float


@dataclass
class Config:
    modo: str
    brazo: str
    simulado: bool
    frecuencia_hz: float
    brazos: dict[str, ConfigBrazo]
    cuadro: ConfigCuadro
    limites: Limites
    zona_compartida: dict[str, Any]
    movimiento: dict[str, Any]
    voz: dict[str, Any]
    camara: dict[str, Any]
    er2: dict[str, Any]
    estilos: dict[str, Cualidades] = field(default_factory=dict)
    conversacion: dict[str, Any] = field(default_factory=dict)

    @property
    def brazos_activos(self) -> list[str]:
        return list(NOMBRES_BRAZO) if self.modo == "dos" else [self.brazo]

    def estilo(self, nombre: str | None) -> Cualidades:
        nombre = nombre or self.movimiento["estilo"]
        if nombre not in self.estilos:
            raise ErrorConfig(f"estilo desconocido: '{nombre}'. Disponibles: {', '.join(sorted(self.estilos))}")
        return self.estilos[nombre]


def _mezclar(base: dict, extra: dict) -> dict:
    salida = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(salida.get(k), dict):
            salida[k] = _mezclar(salida[k], v)
        else:
            salida[k] = v
    return salida


def _vector(valor: Any, n: int, donde: str) -> np.ndarray:
    try:
        v = np.array(valor, dtype=float)
    except (TypeError, ValueError):
        raise ErrorConfig(f"{donde}: se esperaba una lista de {n} números") from None
    if v.shape != (n,):
        raise ErrorConfig(f"{donde}: se esperaban {n} números y hay {v.size}")
    return v


def _positivo(valor: Any, donde: str) -> float:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or valor <= 0:
        raise ErrorConfig(f"{donde}: debe ser un número mayor que cero (valor: {valor!r})")
    return float(valor)


def detectar_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def cargar(ruta: str | os.PathLike | None = None, *, modo: str | None = None,
           brazo: str | None = None, simulado: bool | None = None,
           datos: dict | None = None) -> Config:
    """Carga la configuración. Sin ruta, usa config/so101er.toml si existe o la incluida."""
    with open(RUTA_PREDETERMINADA, "rb") as f:
        crudo = tomllib.load(f)
    if ruta is None and Path("config/so101er.toml").exists():
        ruta = "config/so101er.toml"
    if ruta is not None:
        try:
            with open(ruta, "rb") as f:
                crudo = _mezclar(crudo, tomllib.load(f))
        except FileNotFoundError:
            raise ErrorConfig(f"no se encuentra el archivo de configuración: {ruta}") from None
        except tomllib.TOMLDecodeError as e:
            raise ErrorConfig(f"el archivo {ruta} no es TOML válido: {e}") from None
    if datos:
        crudo = _mezclar(crudo, datos)

    g = crudo["general"]
    modo = modo or g["modo"]
    brazo = brazo or g["brazo"]
    if modo not in ("uno", "dos"):
        raise ErrorConfig(f"general.modo debe ser \"uno\" o \"dos\" (valor: {modo!r})")
    if brazo not in NOMBRES_BRAZO:
        raise ErrorConfig(f"general.brazo debe ser \"izq\" o \"der\" (valor: {brazo!r})")
    frecuencia = _positivo(g["frecuencia_hz"], "general.frecuencia_hz")
    if not 20 <= frecuencia <= 500:
        raise ErrorConfig("general.frecuencia_hz debe estar entre 20 y 500")

    brazos = {}
    for nombre in NOMBRES_BRAZO:
        if nombre not in crudo.get("brazos", {}):
            raise ErrorConfig(f"falta la sección [brazos.{nombre}]")
        b = crudo["brazos"][nombre]
        signo = _vector(b["signo"], 5, f"brazos.{nombre}.signo")
        if not np.all(np.abs(signo) == 1):
            raise ErrorConfig(f"brazos.{nombre}.signo: cada valor debe ser 1 o -1")
        brazos[nombre] = ConfigBrazo(
            nombre=nombre, puerto=str(b.get("puerto", "")),
            base_mm=_vector(b["base_mm"], 3, f"brazos.{nombre}.base_mm"),
            orientacion_grados=float(b["orientacion_grados"]), signo=signo,
            desfase_grados=_vector(b["desfase_grados"], 5, f"brazos.{nombre}.desfase_grados"))

    c = crudo["cuadro"]
    cuadro = ConfigCuadro(
        sup_izq=_vector(c["sup_izq"], 3, "cuadro.sup_izq"), sup_der=_vector(c["sup_der"], 3, "cuadro.sup_der"),
        inf_izq=_vector(c["inf_izq"], 3, "cuadro.inf_izq"),
        separacion_min_mm=_positivo(c["separacion_min_mm"], "cuadro.separacion_min_mm"),
        imagen=str(c.get("imagen", "")))
    u, v = cuadro.sup_der - cuadro.sup_izq, cuadro.inf_izq - cuadro.sup_izq
    if np.linalg.norm(np.cross(u, v)) < 1e-6:
        raise ErrorConfig("cuadro: las tres esquinas están alineadas; no definen un plano")

    lim = crudo["limites"]
    limites = Limites(
        velocidad=_vector(lim["velocidad_grados_s"], 6, "limites.velocidad_grados_s"),
        aceleracion=_vector(lim["aceleracion_grados_s2"], 6, "limites.aceleracion_grados_s2"),
        tiron=_vector(lim["tiron_grados_s3"], 6, "limites.tiron_grados_s3"),
        altura_min_mm=float(lim["altura_min_mm"]),
        distancia_min_brazos_mm=_positivo(lim["distancia_min_brazos_mm"], "limites.distancia_min_brazos_mm"),
        temperatura_max_c=_positivo(lim["temperatura_max_c"], "limites.temperatura_max_c"),
        carga_max=_positivo(lim["carga_max"], "limites.carga_max"),
        error_seguimiento_max_grados=_positivo(lim["error_seguimiento_max_grados"],
                                               "limites.error_seguimiento_max_grados"))
    for nombre_lim in ("velocidad", "aceleracion", "tiron"):
        if np.any(getattr(limites, nombre_lim) <= 0):
            raise ErrorConfig(f"limites.{nombre_lim}: todos los valores deben ser mayores que cero")

    estilos = dict(ESTILOS_BASE)
    validas = set(Cualidades.nombres())
    for nombre, valores in crudo.get("estilos", {}).items():
        sobran = set(valores) - validas
        if sobran:
            raise ErrorConfig(f"estilos.{nombre}: cualidades desconocidas: {', '.join(sorted(sobran))}")
        estilos[nombre] = estilos.get(nombre, Cualidades()).con(**{k: float(x) for k, x in valores.items()})
    if crudo["er2"].get("composicion", "libre") not in ("libre", "biblioteca"):
        raise ErrorConfig("er2.composicion debe ser \"libre\" o \"biblioteca\"")
    if crudo["conversacion"].get("idioma") not in ("es", "en"):
        raise ErrorConfig("conversacion.idioma debe ser \"es\" o \"en\"")
    mov = crudo["movimiento"]
    if mov["estilo"] not in estilos:
        raise ErrorConfig(f"movimiento.estilo: estilo desconocido '{mov['estilo']}'")

    cfg = Config(
        modo=modo, brazo=brazo, simulado=g["simulado"] if simulado is None else simulado,
        frecuencia_hz=frecuencia, brazos=brazos, cuadro=cuadro, limites=limites,
        zona_compartida=crudo["zona_compartida"], movimiento=mov, voz=crudo["voz"],
        camara=crudo["camara"], er2=crudo["er2"], estilos=estilos, conversacion=crudo["conversacion"])
    if not cfg.simulado:
        for nombre in cfg.brazos_activos:
            if not cfg.brazos[nombre].puerto:
                raise ErrorConfig(f"brazos.{nombre}.puerto está vacío. Indica el puerto o usa --sim")
    return cfg
