"""Las manos: Gemini Robotics ER 2 en su modo más rápido.

ER 2 ve la obra y, para cada cosa que se dice (la pregunta del visitante o una frase del
guía), compone el movimiento de los brazos. Aquí se le pide lo mínimo —instrucciones cortas,
una sola función compacta y razonamiento mínimo— porque así reacciona en torno a un segundo
(medido: 1,1 s de mediana, frente a 3–4 s con el prompt largo y las funciones detalladas).

Corre en su propio hilo, con una sesión Live abierta toda la conversación.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable

import cv2
import numpy as np

MODELO = "gemini-robotics-er-2-streaming-preview"


def _sistema(nombres: list[str]) -> str:
    if len(nombres) == 2:
        brazos = ("Tienes dos brazos, como los de una persona: 'izq' (a la izquierda de la imagen) y 'der' (a la "
                  "derecha). Llama a gesto() una vez por brazo: normalmente uno señala o recorre lo que se nombra "
                  "y el otro acompaña con una pose amplia; para ideas de conjunto, tamaño o distancia, los dos se "
                  "abren, se juntan o suben a la vez. Cada brazo alcanza mejor su mitad de la imagen.")
    else:
        brazos = f"Tienes un brazo, '{nombres[0]}'. Llama a gesto() una vez."
    return f"""Eres las manos de un guía de museo que habla delante de la obra de la imagen. Te llegará lo \
que pregunta el visitante o la frase que el guía va a decir. Responde SOLO con llamadas a gesto(); nunca escribas texto.

{brazos}

puntos: de 2 a 4, en orden. Cada punto es:
- [y, x]: un lugar de la imagen (0-1000; y hacia abajo, x hacia la derecha) que el brazo señala. Varios seguidos \
hacen que recorra la línea entre ellos (un contorno, una dirección, un horizonte).
- [alcance, altura, lado, pinza]: una pose en el aire. alcance 0-1 (recogido a extendido), altura 0-1, lado de \
-60 a 90 grados (hacia fuera positivo), pinza 0-100 (cerrada a abierta).
Gesticula como un actor: movimientos muy amplios y suaves, que usen todo el espacio. Subir y abrirse para lo \
grande, luminoso o importante; bajar y recogerse para lo pequeño, oscuro o íntimo.

palabra: la palabra de la frase con la que el gesto debe coincidir (la que nombra lo que señalas). Si es la \
pregunta de un visitante, la palabra que seguramente dirá el guía al responder."""


def _funcion(nombres: list[str]) -> list[dict]:
    return [{"function_declarations": [{
        "name": "gesto", "behavior": "BLOCKING",
        "description": "Mueve un brazo pasando por los puntos, llegando al principal cuando suena 'palabra'.",
        "parameters_json_schema": {"type": "object", "required": ["brazo", "puntos"], "properties": {
            "brazo": {"type": "string", "enum": list(nombres)},
            "puntos": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
            "palabra": {"type": "string"}}}}]}]


def a_puntos_clave(puntos: Any) -> list[dict]:
    """Formato compacto de ER 2 → puntos clave del motor. [y, x] señala; 4 números son una pose."""
    salida = []
    for p in puntos if isinstance(puntos, list) else []:
        if not isinstance(p, (list, tuple)) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in p):
            continue
        if len(p) == 2:
            salida.append({"mira": [float(np.clip(p[0], 0, 1000)), float(np.clip(p[1], 0, 1000))]})
        elif len(p) >= 4:
            salida.append({"alcance": float(np.clip(p[0], 0, 1)), "altura": float(np.clip(p[1], 0, 1)),
                           "lado": float(np.clip(p[2], -90, 90)), "pinza": float(np.clip(p[3], 0, 100))})
    if salida and "mira" in salida[0] and len(salida) == 1:
        salida[0]["pausa"] = 0.6          # un solo punto: señalar y sostener un instante
    return salida


class Manos:
    def __init__(self, cliente: Any, nombres: list[str], imagen: Callable[[], bytes],
                 al_gesto: Callable[[dict, int], None], pensar: str = "minimal", ancho_px: int = 512,
                 al_error: Callable[[str], None] | None = None, conectar: Callable[..., Any] | None = None) -> None:
        self._conectar = conectar or cliente.aio.live.connect
        self.nombres, self._imagen, self.al_gesto = nombres, imagen, al_gesto
        self.pensar, self.ancho_px = pensar, ancho_px
        self.al_error = al_error or (lambda texto: None)
        self.conectado = False
        self.latencias: list[float] = []
        self.turno = 0
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._cola: asyncio.Queue | None = None
        self._fin = threading.Event()
        self._hilo = threading.Thread(target=self._correr, name="manos-er2", daemon=True)
        self._hilo.start()

    # ------------------------------------------------------------ desde otros hilos
    def pedir(self, texto: str, turno: int, rango: tuple[int, int] | None = None) -> None:
        """Encola algo que se va a decir. La respuesta llega por `al_gesto`, con su `rango`
        (el tramo del texto de la voz al que pertenece el gesto)."""
        if self._bucle is not None and self._cola is not None:
            self._bucle.call_soon_threadsafe(self._cola.put_nowait, (texto, turno, rango))

    def cancelar(self, turno: int) -> None:
        """Lo pendiente de turnos anteriores ya no interesa."""
        self.turno = turno

    def cerrar(self) -> None:
        self._fin.set()
        if self._bucle is not None:
            self._bucle.call_soon_threadsafe(lambda: None)

    # ------------------------------------------------------------ hilo propio
    def _correr(self) -> None:
        self._bucle = asyncio.new_event_loop()
        asyncio.set_event_loop(self._bucle)
        self._cola = asyncio.Queue()
        try:
            self._bucle.run_until_complete(self._sesiones())
        except Exception as e:
            self.al_error(f"las manos (ER 2) se han detenido: {type(e).__name__}: {e}")

    def _jpeg(self) -> bytes:
        datos = self._imagen()
        img = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
        if img is None or img.shape[1] <= self.ancho_px:
            return datos
        img = cv2.resize(img, (self.ancho_px, int(img.shape[0] * self.ancho_px / img.shape[1])))
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()

    async def _sesiones(self) -> None:
        espera = 1.0
        while not self._fin.is_set():
            config = {"response_modalities": ["TEXT"], "system_instruction": _sistema(self.nombres),
                      "tools": _funcion(self.nombres), "thinking_config": {"thinking_level": self.pensar},
                      "context_window_compression": {"sliding_window": {}}}
            try:
                async with self._conectar(model=MODELO, config=config) as sesion:
                    self.conectado, espera = True, 1.0
                    await self._atender(sesion)
            except Exception as e:
                if not self._fin.is_set():
                    self.al_error(f"ER 2 desconectado ({type(e).__name__}); reintentando")
            finally:
                self.conectado = False
            if not self._fin.is_set():
                await asyncio.sleep(espera)
                espera = min(espera * 2, 10.0)

    async def _atender(self, sesion: Any) -> None:
        from google.genai import types
        while not self._fin.is_set():
            try:
                texto, turno, rango = await asyncio.wait_for(self._cola.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if turno < self.turno:
                continue                                  # de una respuesta ya interrumpida
            partes = [types.Part(inline_data=types.Blob(data=self._jpeg(), mime_type="image/jpeg")),
                      types.Part(text=texto)]
            t0 = time.perf_counter()
            await sesion.send_client_content(turns=types.Content(role="user", parts=partes), turn_complete=True)
            fin, primera = False, True
            while not fin:
                async for msg in sesion.receive():
                    if getattr(msg, "go_away", None):
                        raise ConnectionError("go_away")
                    if getattr(msg, "tool_call", None):
                        respuestas = []
                        for llamada in msg.tool_call.function_calls or []:
                            if primera:
                                self.latencias.append(time.perf_counter() - t0)
                                del self.latencias[:-50]
                                primera = False
                            if llamada.name == "gesto" and turno >= self.turno:
                                self.al_gesto({**dict(llamada.args or {}), "frase": texto, "rango": rango}, turno)
                            respuestas.append(types.FunctionResponse(name=llamada.name, response={"ok": True},
                                                                     id=llamada.id))
                        await sesion.send_tool_response(function_responses=respuestas)
                    c = getattr(msg, "server_content", None)
                    if c is not None and getattr(c, "turn_complete", False):
                        fin = True
