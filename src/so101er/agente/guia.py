"""El guía que habla: sesión de Gemini 3.8 Live (audio de entrada y de salida).

El audio que genera no va directo al altavoz: pasa por `VozFlujo`, que lo
reproduce con un pequeño retardo para que los gestos lleguen a tiempo.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from .er2 import crear_cliente
from .prompt_sistema import prompt_guia


def _segundos(valor: Any) -> float:
    if valor is None:
        return 0.0
    if hasattr(valor, "total_seconds"):
        return float(valor.total_seconds())
    return float(str(valor).rstrip("s") or 0.0)


class GuiaLive:
    def __init__(self, sistema: Any, voz: Any, camara: Any, registro: Any, flujo: Any = None,
                 conectar: Callable[..., Any] | None = None, microfono: Any = None,
                 al_visitante: Callable[[str], None] | None = None, espera_reconexion_s: float = 1.0) -> None:
        self.s, self.voz, self.camara, self.registro, self.flujo = sistema, voz, camara, registro, flujo
        self._conectar = conectar
        self.microfono = microfono              # objeto con cola asyncio de trozos PCM a 16 kHz, o None
        self.al_visitante = al_visitante or (lambda texto: None)
        self.espera_reconexion_s = espera_reconexion_s
        self.conectado = False
        self.reconexiones = 0
        self._asa: str | None = None
        self._cola: asyncio.Queue = asyncio.Queue()
        self._fin = asyncio.Event()

    def pedir(self, texto: str) -> None:
        """Mensaje de texto para el guía (por ejemplo, «explica el cuadro»)."""
        self._cola.put_nowait(texto)

    def cerrar(self) -> None:
        self._fin.set()

    def _config(self) -> dict:
        cfg = self.s.cfg.voz
        return {
            "response_modalities": ["AUDIO"],
            "system_instruction": prompt_guia(self.s),
            "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": cfg["nombre_voz"]}}},
            "output_audio_transcription": {"word_timestamp": True} if cfg["tiempos_de_palabra"] else {},
            "input_audio_transcription": {},
            "context_window_compression": {"sliding_window": {}},
            "session_resumption": {"handle": self._asa},
        }

    async def ejecutar(self) -> None:
        if self._conectar is None:
            self._conectar = crear_cliente().aio.live.connect
        espera = self.espera_reconexion_s
        while not self._fin.is_set():
            try:
                async with self._conectar(model=self.s.cfg.voz["modelo_live"], config=self._config()) as sesion:
                    self.conectado = True
                    espera = self.espera_reconexion_s
                    self.registro.evento("guia", estado="conectado")
                    tareas = [asyncio.create_task(c) for c in
                              (self._recibir(sesion), self._texto(sesion), self._video(sesion),
                               self._audio(sesion), self._fin.wait())]
                    hechas, pendientes = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
                    for t in pendientes:
                        t.cancel()
                    await asyncio.gather(*pendientes, return_exceptions=True)
                    for t in hechas:
                        if t.exception():
                            raise t.exception()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.registro.evento("guia", estado="desconectado", motivo=str(e))
                if not self._fin.is_set():
                    self.s.registrar(f"voz desconectada ({type(e).__name__}). Reintentando…", alerta=True)
                    if self.flujo is not None:
                        await asyncio.to_thread(self.flujo.interrumpir)
            finally:
                self.conectado = False
            if self._fin.is_set():
                break
            self.reconexiones += 1
            await asyncio.sleep(espera)
            espera = min(espera * 2, 15.0)

    async def _texto(self, sesion: Any) -> None:
        from google.genai import types
        while True:
            texto = await self._cola.get()
            partes = [types.Part(inline_data=types.Blob(data=self.camara.jpeg(), mime_type="image/jpeg")),
                      types.Part(text="Esta es la obra que tienes delante. " + texto)]
            await sesion.send_client_content(turns=types.Content(role="user", parts=partes), turn_complete=True)
            self.registro.evento("guia_mensaje", texto=texto)

    async def _video(self, sesion: Any) -> None:
        from google.genai import types
        periodo = 1.0 / max(min(float(self.s.cfg.er2["fotogramas_por_segundo"]), 1.0), 0.05)   # máximo 1 fps
        while True:
            await sesion.send_realtime_input(video=types.Blob(data=self.camara.jpeg(), mime_type="image/jpeg"))
            await asyncio.sleep(periodo)

    async def _audio(self, sesion: Any) -> None:
        """Envía el micrófono. Mientras suena la voz se silencia: sin cancelación de eco, el
        modelo se oiría a sí mismo y se interrumpiría solo."""
        if self.microfono is None:
            await asyncio.Event().wait()
        from google.genai import types
        mientras_habla = bool(self.s.cfg.voz["microfono_mientras_habla"])
        while True:
            trozo = await self.microfono.cola.get()
            if self.voz.pendiente() and not mientras_habla:
                continue
            await sesion.send_realtime_input(audio=types.Blob(data=trozo, mime_type="audio/pcm;rate=16000"))

    async def _recibir(self, sesion: Any) -> None:
        while True:
            recibido = False
            async for msg in sesion.receive():
                recibido = True
                t = self.s.ahora()
                if getattr(msg, "session_resumption_update", None):
                    act = msg.session_resumption_update
                    if getattr(act, "resumable", False) and getattr(act, "new_handle", None):
                        self._asa = act.new_handle
                if getattr(msg, "go_away", None):
                    raise ConnectionError("el servidor anuncia el cierre de la conexión (go_away)")
                c = getattr(msg, "server_content", None)
                if not c:
                    continue
                if getattr(c, "interrupted", False):         # el visitante ha interrumpido
                    if self.flujo is not None:
                        await asyncio.to_thread(self.flujo.interrumpir)
                    else:
                        self.voz.interrumpir(t)
                turno = getattr(c, "model_turn", None)
                for parte in (turno.parts if turno and turno.parts else []):
                    datos = getattr(parte, "inline_data", None)
                    if datos is not None and datos.data:
                        self.voz.audio(datos.data, t)
                salida = getattr(c, "output_transcription", None)
                if salida is not None and getattr(salida, "text", None):
                    palabras = None
                    if getattr(salida, "words", None):
                        palabras = [(w.word, _segundos(w.start_offset)) for w in salida.words]
                    self.voz.transcripcion(salida.text, t, palabras)
                    self.registro.evento("guia_dice", texto=salida.text)
                entrada = getattr(c, "input_transcription", None)
                if entrada is not None and getattr(entrada, "text", None):
                    self.al_visitante(entrada.text)
                    self.registro.evento("visitante", texto=entrada.text)
                if getattr(c, "turn_complete", False):
                    self.voz.fin_turno(t)
            if not recibido:
                await asyncio.sleep(0.05)
