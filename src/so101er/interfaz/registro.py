"""Registro de sesión en un archivo JSONL (una línea por evento)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class Registro:
    def __init__(self, carpeta: str | Path = "registros") -> None:
        Path(carpeta).mkdir(parents=True, exist_ok=True)
        self.ruta = Path(carpeta) / time.strftime("sesion_%Y%m%d_%H%M%S.jsonl")
        self._f = open(self.ruta, "a", encoding="utf-8")
        self._cerrojo = threading.Lock()
        self._t0 = time.perf_counter()

    def evento(self, tipo: str, **datos: Any) -> None:
        linea = {"t": round(time.perf_counter() - self._t0, 3), "tipo": tipo, **datos}
        with self._cerrojo:
            if not self._f.closed:
                self._f.write(json.dumps(linea, ensure_ascii=False, default=str) + "\n")
                self._f.flush()

    def cerrar(self) -> None:
        with self._cerrojo:
            self._f.close()


class RegistroNulo:
    ruta = None

    def evento(self, tipo: str, **datos: Any) -> None:
        pass

    def cerrar(self) -> None:
        pass
