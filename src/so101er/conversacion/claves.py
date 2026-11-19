"""Claves de los servicios de la conversación. Nunca se guardan en el proyecto ni se muestran.

Se leen del entorno; las que falten se buscan en un archivo `.env` (por ejemplo, el de la
carpeta robot-guia-bot), cuya ruta se da en `conversacion.env` de la configuración.
"""
from __future__ import annotations

import os
from pathlib import Path

NECESARIAS = ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")


class ErrorClaves(RuntimeError):
    pass


def cargar_claves(ruta_env: str | os.PathLike | None) -> dict[str, str]:
    """Devuelve las claves necesarias. Lanza ErrorClaves, diciendo cuáles faltan, si no están."""
    valores = {k: os.environ.get(k, "").strip() for k in NECESARIAS}
    if ruta_env and Path(ruta_env).is_file():
        for linea in Path(ruta_env).read_text(encoding="utf-8", errors="replace").splitlines():
            clave, sep, valor = linea.strip().partition("=")
            clave = clave.strip()
            if sep and clave in valores and not valores[clave]:
                valores[clave] = valor.strip().strip('"').strip("'")
    faltan = [k for k, v in valores.items() if not v]
    if faltan:
        raise ErrorClaves(f"Faltan claves: {', '.join(faltan)}. Defínelas como variables de entorno o en el "
                          f"archivo .env indicado en conversacion.env ({ruta_env or 'sin indicar'}).")
    return valores
