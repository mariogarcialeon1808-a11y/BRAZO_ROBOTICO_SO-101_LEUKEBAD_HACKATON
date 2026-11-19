"""Monta el sistema con la obra de la carpeta `obra/` y, si se pide, la escena de MuJoCo."""
from __future__ import annotations

import time
from typing import Any

from . import obra
from .config import Config
from .sistema import Sistema


def montar(cfg: Config, mujoco: bool) -> tuple[Sistema, Any]:
    """Devuelve (sistema, mundo de MuJoCo o None)."""
    imagen = obra.preparar(cfg)
    if not mujoco:
        s = Sistema(cfg)
        s.imagen_obra = imagen
        return s, None
    from .hardware.mujoco_sim import MundoMuJoCo
    mundo = MundoMuJoCo(cfg, cfg.brazos_activos, imagen)
    s = Sistema(cfg, brazos=mundo.brazo)
    s.cuadro.homografia = mundo.homografia_fija()
    s.imagen_obra = imagen
    return s, mundo


def demo_en_mujoco(cfg: Config, partitura: Any = None) -> int:
    """Interpreta una partitura en tiempo real en MuJoCo, con voz muda (subtítulos)."""
    from .demo import DEMO
    from .sincronia.director import Director
    from .sincronia.partitura import Partitura
    from .sincronia.voz import VozMuda

    s, mundo = montar(cfg, True)

    def subtitulo(texto: str) -> None:
        print(f"  « {texto} »", flush=True)
        mundo.subtitulo = texto

    d = Director(s, VozMuda(cfg.voz["silabas_por_segundo"], al_subtitulo=subtitulo))
    partitura = partitura or Partitura.de_dict(DEMO)
    for f in partitura.frases:
        for g in f.gestos:
            if g.brazo in ("izq", "der") and g.brazo not in s.nombres:
                g.brazo = s.nombres[0]
    s.al_registrar = lambda texto: print(f"  · {texto}", flush=True) if texto.startswith(("brazo", "PARADA")) else None
    mundo.iniciar(ventana=True)
    s.iniciar()
    d.iniciar()
    try:
        time.sleep(1.5)
        d.interpretar(partitura)
        while (d.activo or s.ocupado()) and not mundo.cerrado:
            time.sleep(0.1)
        fin = time.perf_counter() + 2.0
        while time.perf_counter() < fin and not mundo.cerrado:
            time.sleep(0.1)
    except KeyboardInterrupt:
        s.parar(emergencia=True)
    finally:
        d.cerrar()
        s.cerrar(ir_a_reposo=False)
        mundo.cerrar()
    print(f"Alertas: {[a for _, a in s.alertas] or 'ninguna'} · jitter del control: {s.resumen_jitter()}")
    return 0
