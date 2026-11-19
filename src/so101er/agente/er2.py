"""Agentes de Gemini Robotics ER 2: en directo (Live API) y estándar (Interactions API).

Los dos comparten la misma interfaz:
    await agente.ejecutar()        bucle principal (hasta agente.cerrar())
    agente.pedir(texto, urgente)   encola un mensaje para el modelo

Las funciones se ejecutan en local y responden en milisegundos ("aceptado, en
curso"); el movimiento sigue después. Los brazos nunca esperan a la red.
"""
from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, Callable

from .herramientas import declaraciones, ejecutar_llamada, para_interacciones, para_live
from .prompt_sistema import contexto_reconexion, prompt_coreografo


class ErrorAgente(RuntimeError):
    pass


def _clave_de_usuario_windows() -> str:
    """Lee GEMINI_API_KEY de las variables de entorno del usuario de Windows.

    Así una clave recién definida con `setx` funciona sin reiniciar el programa que nos lanza."""
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, "GEMINI_API_KEY")[0]).strip()
    except OSError:
        return ""


def crear_cliente() -> Any:
    """Cliente de la API de Gemini. La clave se lee de GEMINI_API_KEY, nunca de archivos."""
    clave = os.environ.get("GEMINI_API_KEY", "").strip() or _clave_de_usuario_windows()
    if not clave:
        raise ErrorAgente(
            "Falta la variable de entorno GEMINI_API_KEY. Crea una clave en Google AI Studio "
            "(debe estar restringida: una clave sin restricciones devuelve el error 403) y defínela "
            "antes de arrancar.")
    try:
        from google import genai
    except ImportError:
        raise ErrorAgente("Falta el paquete google-genai. Instálalo con: pip install -e \".[ia]\"") from None
    return genai.Client(api_key=clave, http_options={"api_version": "v1beta"})


class _AgenteBase:
    def __init__(self, sistema: Any, director: Any, camara: Any, registro: Any, flujo: Any = None,
                 al_texto: Callable[[str], None] | None = None) -> None:
        self.s, self.d, self.camara, self.registro, self.flujo = sistema, director, camara, registro, flujo
        self.al_texto = al_texto or (lambda texto: None)
        self.composicion = str(sistema.cfg.er2.get("composicion", "libre"))
        self.decls = declaraciones(sistema, flujo is not None, self.composicion)
        self.prompt = prompt_coreografo(sistema, flujo is not None, self.composicion)
        self.conectado = False
        self.tarea = ""                 # último encargo del usuario (se reenvía al reconectar)
        self.latencia_s = 0.0           # tiempo hasta la primera respuesta del último mensaje
        self.llamadas: list[dict] = []  # historial de funciones llamadas
        self._cola: asyncio.Queue = asyncio.Queue()
        self._fin = asyncio.Event()
        self._aviso_pendiente = False

    def pedir(self, texto: str, urgente: bool = False, es_tarea: bool = False) -> None:
        if es_tarea:
            self.tarea = texto
        self._cola.put_nowait((texto, urgente))

    def cerrar(self) -> None:
        self._fin.set()

    async def _llamar(self, nombre: str, args: dict | None) -> dict:
        """Ejecuta una función en otro hilo (la planificación no debe frenar el bucle de red)."""
        t0 = time.perf_counter()
        respuesta = await asyncio.to_thread(ejecutar_llamada, self.s, self.d, nombre, args, self.flujo)
        ms = round((time.perf_counter() - t0) * 1000)
        self.llamadas.append({"funcion": nombre, "args": args, "respuesta": respuesta, "ms": ms})
        if nombre != "estado" and "error" not in respuesta:
            self._aviso_pendiente = True      # hay movimiento en marcha del que informar al acabar
        del self.llamadas[:-100]
        self.registro.evento("funcion", nombre=nombre, args=args, respuesta=respuesta, ms=ms)
        return respuesta

    def _actividad(self) -> bool:
        return self.s.ocupado() or (self.d is not None and self.d.activo)


class ER2Directo(_AgenteBase):
    """ER 2 por la Live API: sesión bidireccional, con reconexión automática."""

    def __init__(self, sistema: Any, director: Any, camara: Any, registro: Any, flujo: Any = None,
                 al_texto: Callable[[str], None] | None = None, conectar: Callable[..., Any] | None = None,
                 latido_s: float = 4.0, espera_reconexion_s: float = 1.0) -> None:
        super().__init__(sistema, director, camara, registro, flujo, al_texto)
        self._conectar = conectar
        self.latido_s = latido_s
        self.espera_turno_s = 20.0           # tiempo máximo esperando a que el modelo cierre su turno
        self.espera_reconexion_s = espera_reconexion_s
        self.reconexiones = 0
        self._asa: str | None = None          # identificador para reanudar la sesión
        self._turno_libre = asyncio.Event()
        self._turno_libre.set()
        self._t_envio = 0.0
        self._espera_respuesta = False

    def _config(self) -> dict:
        return {
            "response_modalities": ["TEXT"],
            "system_instruction": self.prompt,
            "tools": para_live(self.decls),
            "thinking_config": {"thinking_level": str(self.s.cfg.er2["razonamiento_directo"])},
            # Sin compresión, una sesión con vídeo dura 2 minutos.
            "context_window_compression": {"sliding_window": {}},
            "session_resumption": {"handle": self._asa},
        }

    async def ejecutar(self) -> None:
        if self._conectar is None:
            cliente = crear_cliente()
            self._conectar = cliente.aio.live.connect
        modelo = self.s.cfg.er2["modelo_directo"]
        espera = self.espera_reconexion_s
        while not self._fin.is_set():
            try:
                async with self._conectar(model=modelo, config=self._config()) as sesion:
                    self.conectado = True
                    self._turno_libre.set()
                    self._alerta_vista = self.s.alertas[-1] if self.s.alertas else None
                    espera = self.espera_reconexion_s
                    self.registro.evento("er2", estado="conectado", reanudada=self._asa is not None)
                    if self.reconexiones:
                        self.s.registrar("ER 2 reconectado")
                        await self._enviar(sesion, contexto_reconexion(self.s, self.tarea))
                    tareas = [asyncio.create_task(c) for c in
                              (self._recibir(sesion), self._emitir(sesion), self._latido(), self._fin.wait())]
                    hechas, pendientes = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
                    for t in pendientes:
                        t.cancel()
                    await asyncio.gather(*pendientes, return_exceptions=True)
                    for t in hechas:
                        if t.exception():
                            raise t.exception()
            except asyncio.CancelledError:
                raise
            except ErrorAgente:
                raise
            except Exception as e:                # corte de red, límite de sesión, go_away…
                self.registro.evento("er2", estado="desconectado", motivo=str(e))
                if not self._fin.is_set():
                    self.s.registrar(f"ER 2 desconectado ({type(e).__name__}): los brazos terminan la frase "
                                     f"en curso y esperan. Reintentando…", alerta=True)
            finally:
                self.conectado = False
            if self._fin.is_set():
                break
            self.reconexiones += 1
            await asyncio.sleep(espera)
            espera = min(espera * 2, 15.0)

    async def _enviar(self, sesion: Any, texto: str) -> None:
        from google.genai import types
        partes = []
        imagenes = self.camara.imagenes()
        if self.flujo is not None or not texto.startswith(("Los brazos han terminado", "Aviso del sistema")):
            imagenes = imagenes[:1]           # al pedir una explicación, solo la cámara fija: responde antes
        for rotulo, jpeg in imagenes:
            partes += [types.Part(text=rotulo), types.Part(inline_data=types.Blob(data=jpeg, mime_type="image/jpeg"))]
        partes.append(types.Part(text=texto))
        self._turno_libre.clear()
        self._t_envio = time.perf_counter()
        self._espera_respuesta = True
        await sesion.send_client_content(turns=types.Content(role="user", parts=partes), turn_complete=True)
        self.registro.evento("mensaje", texto=texto)

    async def _emitir(self, sesion: Any) -> None:
        """Envía los mensajes en cola. Los no urgentes esperan a que el modelo acabe su turno,
        porque un mensaje a mitad de turno cancela lo que el modelo estaba haciendo."""
        while True:
            texto, urgente = await self._cola.get()
            if not urgente:
                try:
                    await asyncio.wait_for(self._turno_libre.wait(), timeout=self.espera_turno_s)
                except asyncio.TimeoutError:
                    self._turno_libre.set()
                while not self._cola.empty():            # junta los mensajes acumulados en uno
                    otro, urg = self._cola.get_nowait()
                    texto += "\n" + otro
                    urgente = urgente or urg
            await self._enviar(sesion, texto)

    async def _latido(self) -> None:
        """Mientras hay movimiento, avisa a ER 2 de cuándo termina para que compruebe el resultado."""
        ultimo = time.perf_counter()
        while True:
            await asyncio.sleep(min(self.latido_s, 0.2))
            ahora_activo = self._actividad()
            # Tras una orden de movimiento, cuando los brazos acaban y el modelo ha cerrado su turno.
            if (self.flujo is None and self._aviso_pendiente and not ahora_activo
                    and self._turno_libre.is_set() and self.tarea):
                self._aviso_pendiente = False
                self.pedir("Los brazos han terminado lo que pediste. Si ya dijiste todo lo que se te pidió, "
                           "responde solo con la palabra \"hecho\", sin llamar a ninguna función y sin añadir "
                           "frases de cierre ni despedidas. Solo si quedó algo por decir, continúa.")
                ultimo = time.perf_counter()
            elif (self.flujo is None and ahora_activo and self.s.alertas and self._turno_libre.is_set()
                  and time.perf_counter() - ultimo > self.latido_s and self._alerta_nueva()):
                self.pedir(f"Aviso del sistema: {self.s.alertas[-1][1]}. No repitas frases ya dichas; tenlo en "
                           f"cuenta en los movimientos siguientes.")
                ultimo = time.perf_counter()

    def _alerta_nueva(self) -> bool:
        ultima = self.s.alertas[-1] if self.s.alertas else None
        if ultima is None or ultima == getattr(self, "_alerta_vista", None):
            return False
        self._alerta_vista = ultima
        return True

    async def _recibir(self, sesion: Any) -> None:
        texto = ""
        while True:
            recibido = False
            async for msg in sesion.receive():           # el iterador termina en cada fin de turno
                recibido = True
                if self._espera_respuesta:
                    self.latencia_s = time.perf_counter() - self._t_envio
                    self._espera_respuesta = False
                if getattr(msg, "session_resumption_update", None):
                    act = msg.session_resumption_update
                    if getattr(act, "resumable", False) and getattr(act, "new_handle", None):
                        self._asa = act.new_handle
                if getattr(msg, "go_away", None):
                    raise ConnectionError("el servidor anuncia el cierre de la conexión (go_away)")
                if getattr(msg, "tool_call", None):
                    from google.genai import types
                    respuestas = []
                    for llamada in msg.tool_call.function_calls or []:
                        r = await self._llamar(llamada.name, dict(llamada.args or {}))
                        respuestas.append(types.FunctionResponse(name=llamada.name, response=r, id=llamada.id))
                    await sesion.send_tool_response(function_responses=respuestas)
                contenido = getattr(msg, "server_content", None)
                if contenido:
                    turno = getattr(contenido, "model_turn", None)
                    for parte in (turno.parts if turno and turno.parts else []):
                        if getattr(parte, "text", None) and not getattr(parte, "thought", False):
                            texto += parte.text
                    if getattr(contenido, "turn_complete", False):
                        if texto.strip():
                            self.al_texto(texto.strip())
                            self.registro.evento("er2_texto", texto=texto.strip())
                            if texto.strip().lower().strip(".\"") == "hecho":
                                self.tarea = ""
                        texto = ""
                        self._turno_libre.set()
            if not recibido:
                await asyncio.sleep(0.05)


class ER2Estandar(_AgenteBase):
    """ER 2 por la Interactions API: un bucle de petición y respuesta (modo de reserva)."""

    def __init__(self, sistema: Any, director: Any, camara: Any, registro: Any, flujo: Any = None,
                 al_texto: Callable[[str], None] | None = None, crear: Callable[..., Any] | None = None,
                 max_pasos: int = 12, espera_movimiento_s: float = 25.0) -> None:
        super().__init__(sistema, director, camara, registro, flujo, al_texto)
        self._crear = crear
        self.max_pasos = max_pasos
        self.espera_movimiento_s = espera_movimiento_s
        self._previo: str | None = None

    def _imagenes(self) -> list[dict]:
        salida: list[dict] = []
        for rotulo, jpeg in self.camara.imagenes():
            salida += [{"type": "text", "text": rotulo},
                       {"type": "image", "data": base64.b64encode(jpeg).decode("ascii"), "mime_type": "image/jpeg"}]
        return salida

    async def _interaccion(self, entrada: list) -> Any:
        argumentos: dict[str, Any] = {
            "model": self.s.cfg.er2["modelo_estandar"], "input": entrada,
            "tools": para_interacciones(self.decls), "system_instruction": self.prompt,
            "generation_config": {"thinking_level": self.s.cfg.er2["razonamiento"]}}
        if self._previo:
            argumentos["previous_interaction_id"] = self._previo
        t0 = time.perf_counter()
        r = await asyncio.to_thread(self._crear, **argumentos)
        self.latencia_s = time.perf_counter() - t0
        self._previo = getattr(r, "id", None)
        return r

    async def ejecutar(self) -> None:
        if self._crear is None:
            self._crear = crear_cliente().interactions.create
        while not self._fin.is_set():
            pedir = asyncio.create_task(self._cola.get())
            fin = asyncio.create_task(self._fin.wait())
            hechas, pendientes = await asyncio.wait({pedir, fin}, return_when=asyncio.FIRST_COMPLETED)
            for t in pendientes:
                t.cancel()
            if pedir not in hechas:
                break
            texto, _ = pedir.result()
            try:
                await self._tarea(texto)
                self.conectado = True
            except Exception as e:
                self.conectado = False
                self._previo = None
                self.registro.evento("er2", estado="error", motivo=str(e))
                self.s.registrar(f"ER 2 no responde ({type(e).__name__}: {e}). Los brazos esperan.", alerta=True)

    async def _tarea(self, texto: str) -> None:
        entrada: list = self._imagenes() + [{"type": "text", "text": texto}]
        self.registro.evento("mensaje", texto=texto)
        for _ in range(self.max_pasos):
            r = await self._interaccion(entrada)
            llamadas = [p for p in (getattr(r, "steps", None) or []) if getattr(p, "type", "") == "function_call"]
            if not llamadas:
                salida = (getattr(r, "output_text", "") or "").strip()
                if salida:
                    self.al_texto(salida)
                    self.registro.evento("er2_texto", texto=salida)
                return
            entrada = []
            for ll in llamadas:
                import json
                respuesta = await self._llamar(ll.name, dict(ll.arguments or {}))
                entrada.append({"type": "function_result", "name": ll.name, "call_id": ll.id,
                                "result": [{"type": "text", "text": json.dumps(respuesta, ensure_ascii=False)}]})
            # Antes de volver a preguntar, espera a que los brazos terminen y manda la imagen nueva.
            limite = time.perf_counter() + self.espera_movimiento_s
            await asyncio.sleep(0.05)
            while self._actividad() and time.perf_counter() < limite and not self._fin.is_set():
                await asyncio.sleep(0.05)
            entrada += self._imagenes() + [{"type": "text", "text": "Imágenes actuales tras el movimiento."}]
        self.s.registrar("ER 2 ha superado el número máximo de pasos de una tarea", alerta=True)
