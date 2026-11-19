"""`so101er hablar`: conversación con el guía. Chatbot + voz de ElevenLabs + ER 2 en las manos."""
from __future__ import annotations

import statistics
import sys
import time
from typing import Any

import cv2

from ..agente.er2 import crear_cliente
from ..config import Config
from ..montaje import montar
from .cerebro import Cerebro
from .claves import cargar_claves
from .guia import Conversacion
from .manos import Manos
from .voz_eleven import VozEleven

AYUDA = {
    "es": """Mantén pulsada la BARRA ESPACIADORA para hablar (con la ventana de la simulación en primer plano)
y suéltala al terminar. Si el guía está hablando, al pulsarla se calla y te escucha.
También puedes escribir aquí la pregunta y pulsar Enter.
Órdenes: /idioma es|en   /parar   /tiempos   /salir""",
    "en": """Hold the SPACE BAR to talk (with the simulation window in front) and release it when you finish.
If the guide is speaking, pressing it makes it stop and listen.
You can also type your question here and press Enter.
Commands: /idioma es|en   /parar   /tiempos   /salir""",
}


def _resumen(conv: Conversacion, manos: Manos) -> str:
    sonido = [m["primer_sonido_s"] for m in conv.tiempos if "primer_sonido_s" in m]
    partes = []
    if sonido:
        partes.append(f"primer sonido: mediana {statistics.median(sonido):.1f} s (de {len(sonido)} respuestas)")
    if manos.latencias:
        partes.append(f"ER 2: mediana {statistics.median(manos.latencias):.1f} s por gesto ({len(manos.latencias)})")
    return " · ".join(partes) or "sin medidas"


def hablar(cfg: Config, mujoco: bool, idioma: str | None, modelo: str | None, pedir: str | None,
           microfono: bool, ventana: bool) -> int:
    from ..interfaz.audio import Altavoz
    from ..interfaz.registro import Registro

    opciones = cfg.conversacion
    idioma = idioma or str(opciones["idioma"])
    claves = cargar_claves(opciones["env"])
    cliente_google = crear_cliente()
    s, mundo = montar(cfg, mujoco)
    if mundo is not None:
        from ..hardware.mujoco_sim import CamaraMuJoCo
        camara: Any = CamaraMuJoCo(mundo)
    else:
        from ..interfaz.camara import CamaraSim
        camara = CamaraSim(s)
    registro = Registro()

    def decir(texto: str) -> None:
        print(texto, flush=True)
        if mundo is not None and texto.startswith("  « "):
            mundo.subtitulo = texto.strip(" «»")

    def aviso(texto: str) -> None:
        s.registrar(texto, alerta=True)

    s.al_registrar = lambda texto: (registro.evento("sistema", texto=texto),
                                    print(f"  · {texto}", flush=True) if texto.startswith("⚠") else None)
    voz = VozEleven(claves["ELEVENLABS_API_KEY"], claves["ELEVENLABS_VOICE_ID"], idioma,
                    volumen=float(opciones["volumen"]), modelo=str(opciones["voz_modelo"]), al_error=aviso)
    altavoz = Altavoz(voz, s)
    obra_jpeg = cv2.imencode(".jpg", s.imagen_obra, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()
    cerebro = Cerebro(claves["ANTHROPIC_API_KEY"], obra_jpeg, idioma, modelo or str(opciones["modelo_chat"]))
    manos = Manos(cliente_google, s.nombres, camara.jpeg, lambda *a: None, pensar=str(opciones["er2_razonamiento"]),
                  ancho_px=int(opciones["er2_imagen_px"]), al_error=aviso)
    micro = barra = None
    if microfono and not pedir:
        from .oido import BarraEspaciadora, ErrorOido, Micro, Transcriptor
        try:
            micro = Micro()
        except ErrorOido as e:
            print(f"Aviso: {e}. Puedes escribir las preguntas.", file=sys.stderr)
    conv = Conversacion(
        s, voz, cerebro, manos, registro, al_decir=decir, micro=micro,
        crear_transcriptor=(lambda: Transcriptor(claves["ELEVENLABS_API_KEY"], cerebro.idioma)) if micro else None)
    if micro is not None:
        barra = BarraEspaciadora(conv.pulsar, conv.soltar)

    if mundo is not None:
        mundo.iniciar(ventana=ventana, camaras=True)
    s.iniciar()
    altavoz.iniciar()
    voz.conectar_en_segundo_plano()
    cerebro.precargar()
    try:
        limite = time.perf_counter() + 12.0
        while not manos.conectado and time.perf_counter() < limite:
            time.sleep(0.05)
        if pedir:
            conv.preguntar(pedir)
            time.sleep(1.0)
            limite, quieto = time.perf_counter() + 240.0, None
            while time.perf_counter() < limite and not (mundo is not None and mundo.cerrado):
                time.sleep(0.2)
                quieto = None if conv.activa else (quieto or time.perf_counter())
                if quieto is not None and time.perf_counter() - quieto > 2.5:
                    break
        else:
            print(AYUDA[idioma], flush=True)
            while not (mundo is not None and mundo.cerrado):
                try:
                    linea = input().strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not linea:
                    continue
                if linea in ("/salir", "salir"):
                    break
                if linea == "/parar":
                    conv.interrumpir()
                elif linea == "/tiempos":
                    print(_resumen(conv, manos), flush=True)
                elif linea.startswith("/idioma"):
                    nuevo = linea.split()[-1]
                    if nuevo in ("es", "en"):
                        conv.interrumpir()
                        cerebro.cambiar_idioma(nuevo)
                        cerebro.precargar()
                        voz.cambiar_idioma(nuevo)
                        print(AYUDA[nuevo], flush=True)
                    else:
                        print("Uso: /idioma es   o   /idioma en", flush=True)
                elif linea.startswith("/"):
                    print("Orden desconocida. /idioma es|en, /parar, /tiempos, /salir", flush=True)
                else:
                    conv.preguntar(linea)
    finally:
        print(f"Tiempos: {_resumen(conv, manos)}", flush=True)
        conv.cerrar()
        if barra is not None:
            barra.cerrar()
        if micro is not None:
            micro.cerrar()
        manos.cerrar()
        altavoz.cerrar()
        voz.cerrar()
        s.cerrar()
        if mundo is not None:
            mundo.cerrar()
        registro.cerrar()
        print(f"Registro de la sesión: {registro.ruta}", flush=True)
    return 0
