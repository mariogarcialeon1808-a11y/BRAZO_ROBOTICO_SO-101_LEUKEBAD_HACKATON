"""Partitura: la unidad común entre la voz y los gestos.

Cada frase tiene su texto, sus palabras con tiempos (estimados o reales) y
los gestos anclados a palabras, no a segundos.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..control.gestos import ErrorGesto, Gesto

_VOCALES = re.compile(r"[aeiouáéíóúüy]+", re.IGNORECASE)
_PALABRA = re.compile(r"[\wáéíóúüñÁÉÍÓÚÜÑ]+", re.UNICODE)
VACIAS = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y", "o",
          "que", "se", "su", "sus", "con", "por", "para", "es", "son", "lo", "le", "como", "más", "pero",
          "este", "esta", "esto", "ese", "esa", "muy", "nos", "me", "te", "si", "no", "ya", "hay"}


class ErrorPartitura(ValueError):
    pass


@dataclass
class Palabra:
    texto: str
    inicio: float      # segundos desde el comienzo de la frase
    fin: float
    silabas: int


@dataclass
class Frase:
    texto: str
    gestos: list[Gesto] = field(default_factory=list)
    acentos: list[int] | None = None       # índices de palabra; None = automáticos
    estilo: str | None = None              # estilo por defecto de los gestos de la frase
    pausa: float | None = None             # silencio tras la frase (s)
    palabras: list[Palabra] = field(default_factory=list)
    duracion: float = 0.0

    def a_dict(self) -> dict:
        d: dict = {"texto": self.texto, "gestos": [g.a_dict() for g in self.gestos]}
        for k in ("acentos", "estilo", "pausa"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        return d


@dataclass
class Partitura:
    frases: list[Frase]
    titulo: str = ""

    def a_dict(self) -> dict:
        return {"titulo": self.titulo, "frases": [f.a_dict() for f in self.frases]}

    def guardar(self, ruta: str | Path) -> None:
        Path(ruta).write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def de_dict(d: dict) -> "Partitura":
        if not isinstance(d, dict) or not isinstance(d.get("frases"), list) or not d["frases"]:
            raise ErrorPartitura("la partitura debe tener una lista \"frases\" con al menos una frase")
        frases = []
        for i, f in enumerate(d["frases"]):
            if not isinstance(f, dict) or not str(f.get("texto", "")).strip():
                raise ErrorPartitura(f"frase {i + 1}: falta el texto")
            try:
                gestos = [Gesto.de_dict(g) for g in f.get("gestos", [])]
            except ErrorGesto as e:
                raise ErrorPartitura(f"frase {i + 1}: {e}") from None
            frases.append(Frase(texto=str(f["texto"]).strip(), gestos=gestos, acentos=f.get("acentos"),
                                estilo=f.get("estilo"), pausa=f.get("pausa")))
        return Partitura(frases, titulo=str(d.get("titulo", "")))

    @staticmethod
    def cargar(ruta: str | Path) -> "Partitura":
        try:
            return Partitura.de_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
        except FileNotFoundError:
            raise ErrorPartitura(f"no se encuentra la partitura: {ruta}") from None
        except json.JSONDecodeError as e:
            raise ErrorPartitura(f"la partitura {ruta} no es JSON válido: {e}") from None


def contar_silabas(palabra: str) -> int:
    return max(1, len(_VOCALES.findall(palabra)))


def estimar_tiempos(texto: str, silabas_por_segundo: float = 4.6) -> tuple[list[Palabra], float]:
    """Tiempos aproximados de cada palabra a partir de sus sílabas y la puntuación."""
    palabras: list[Palabra] = []
    t = 0.0
    for trozo in texto.split():
        m = _PALABRA.search(trozo)
        if not m:
            continue
        n = sum(contar_silabas(x) for x in _PALABRA.findall(trozo))
        dur = n / silabas_por_segundo
        palabras.append(Palabra(trozo, t, t + dur, n))
        t += dur
        if trozo[-1] in ",;:":
            t += 0.22
        elif trozo[-1] in ".!?…":
            t += 0.4
    return palabras, t


def acentos_automaticos(palabras: list[Palabra], separacion_s: float = 0.9) -> list[int]:
    """Palabras con contenido en las que cae un acento gestual."""
    salida, ultimo = [], -1e9
    for i, p in enumerate(palabras):
        limpia = "".join(_PALABRA.findall(p.texto)).lower()
        if limpia in VACIAS or p.silabas < 2:
            continue
        if p.inicio - ultimo >= separacion_s:
            salida.append(i)
            ultimo = p.inicio
    return salida
