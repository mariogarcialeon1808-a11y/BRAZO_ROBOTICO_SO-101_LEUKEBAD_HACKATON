from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from so101er.config import cargar
from so101er.sistema import Sistema

RAIZ = Path(__file__).resolve().parents[1]
DT = 0.01


def crear(modo: str = "dos", brazo: str = "izq", **datos) -> Sistema:
    cfg = cargar(RAIZ / "config" / "so101er.toml", modo=modo, brazo=brazo, simulado=True, datos=datos or None)
    s = Sistema(cfg)
    for _ in range(30):
        s.avanzar(DT)
    return s


def grabar(s: Sistema, segundos: float | None = None, hasta_quieto: bool = False) -> dict[str, np.ndarray]:
    """Avanza la simulación y devuelve las consignas de cada brazo (filas = ciclos)."""
    datos: dict[str, list] = {n: [] for n in s.nombres}
    pasos = int((segundos or 60.0) / DT)
    for _ in range(pasos):
        s.avanzar(DT)
        for n in s.nombres:
            datos[n].append(s.coreos[n].cmd.copy())
        if hasta_quieto and not s.ocupado() and not (s.director and s.director.activo):
            break
    return {n: np.array(v) for n, v in datos.items()}


def derivadas(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = np.diff(x, axis=0) / DT
    a = np.diff(v, axis=0) / DT
    j = np.diff(a, axis=0) / DT
    return v, a, j


@pytest.fixture
def dos() -> Sistema:
    return crear("dos")


@pytest.fixture
def uno() -> Sistema:
    return crear("uno", "izq")


@pytest.fixture
def raiz():
    """Ventana raíz de Tk para una prueba de interfaz. Se destruye al acabar: si quedara viva, las
    imágenes de la siguiente ventana que se cree (la del programa) irían a parar a esta."""
    tk = pytest.importorskip('tkinter')
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip('sin pantalla')
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass
