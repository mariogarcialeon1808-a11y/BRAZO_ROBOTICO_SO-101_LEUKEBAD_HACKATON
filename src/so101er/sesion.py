"""Sesión con IA: `so101er run`.

Dos formas de voz:
- muda: tú escribes qué explicar, ER 2 redacta las frases y sus gestos, y la
  explicación sale en subtítulos.
- live: Gemini 3.8 Live habla (altavoz) y escucha (micrófono); cada frase suya
  se pasa a ER 2, que le pone los gestos.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any

from .agente.er2 import ER2Directo, ER2Estandar, ErrorAgente, crear_cliente
from .config import Config
from .sincronia.director import Director
from .sincronia.voz import VozMuda
from .sistema import Sistema

AYUDA = """Escribe lo que quieras que se explique (por ejemplo: explica el cuadro).
Órdenes: /estado  /llamadas  /parar  /rearmar  /ayuda  /salir
Parada de emergencia: Esc o F12 (segunda pulsación: quita el par). Ctrl+C: quita el par y sale."""


def mensaje_frase(frase: Any) -> str:
    """Mensaje para ER 2 con una frase del guía y sus palabras numeradas."""
    palabras = " ".join(f"{i}:{p.texto}" for i, p in enumerate(frase.palabras))
    return f"Frase {frase.id}: \"{frase.texto}\"\nPalabras: {palabras}"


class Sesion:
    def __init__(self, cfg: Config, voz: str, agente: str, ventana: bool, microfono: bool, registrar: bool,
                 mujoco: bool = False, peticion: str | None = None) -> None:
        self.peticion = peticion
        if not cfg.simulado:
            raise ErrorAgente("La cámara y los brazos reales llegan en la Fase 3. Usa --sim.")
        from .interfaz.camara import CamaraSim
        from .interfaz.registro import Registro, RegistroNulo
        self.cfg, self.tipo_voz = cfg, voz
        cliente = crear_cliente()               # falla aquí, con un mensaje claro, si falta la clave
        from .montaje import montar
        self.s, self.mundo = montar(cfg, mujoco)
        self._ventana = ventana
        if self.mundo is not None:
            from .hardware.mujoco_sim import CamaraMuJoCo
            self.camara: Any = CamaraMuJoCo(self.mundo)
        else:
            self.camara = CamaraSim(self.s)
        self.registro = Registro() if registrar else RegistroNulo()
        self.visor = None
        if ventana and self.mundo is None:
            from .interfaz.visor import Visor
            self.visor = Visor(self.s)
        self.fin = threading.Event()
        self._emergencias = 0
        self.guia = self.altavoz = self.micro = self.flujo = self.voz = None
        self._quiere_microfono = microfono and bool(cfg.voz["microfono"])
        if voz == "live":
            from .agente.guia import GuiaLive
            from .interfaz.audio import Altavoz
            from .sincronia.flujo import DirectorFlujo, VozFlujo
            self.voz = VozFlujo(float(cfg.voz["retardo_s"]))
            self.flujo = self.d = DirectorFlujo(self.s, self.voz, al_frase=self._frase)
            self.altavoz = Altavoz(self.voz, self.s)
            self.guia = GuiaLive(self.s, self.voz, self.camara, self.registro, flujo=self.flujo,
                                 conectar=cliente.aio.live.connect,
                                 al_visitante=lambda x: self._decir(f"  (visitante) {x}"))
        elif voz in ("local", "tts"):
            from .interfaz.audio import Altavoz
            from .sincronia.voz_sintetizada import SintetizadorGemini, SintetizadorWindows, VozSintetizada
            if voz == "local":
                sintetizador: Any = SintetizadorWindows(str(cfg.voz["voz_local"]), int(cfg.voz["ritmo_voz_local"]))
            else:
                sintetizador = SintetizadorGemini(cliente, str(cfg.voz["modelo_tts"]), str(cfg.voz["nombre_voz"]))
            self.voz = VozSintetizada(sintetizador, cfg.voz["silabas_por_segundo"], al_subtitulo=self._subtitulo,
                                      al_error=lambda x: self.s.registrar(x, alerta=True),
                                      volumen=float(cfg.voz["volumen"]))
            self.altavoz = Altavoz(self.voz, self.s)
            self.d = Director(self.s, self.voz)
        else:
            self.d = Director(self.s, VozMuda(cfg.voz["silabas_por_segundo"], al_subtitulo=self._subtitulo))
        if agente == "estandar":
            self.agente: Any = ER2Estandar(self.s, None if self.flujo else self.d, self.camara, self.registro,
                                           flujo=self.flujo, al_texto=lambda x: self._decir(f"ER 2: {x}"),
                                           crear=cliente.interactions.create)
        else:
            self.agente = ER2Directo(self.s, None if self.flujo else self.d, self.camara, self.registro,
                                     flujo=self.flujo, al_texto=lambda x: self._decir(f"ER 2: {x}"),
                                     conectar=cliente.aio.live.connect)
        self.s.al_registrar = lambda texto: (self._decir(f"  · {texto}"), self.registro.evento("sistema", texto=texto))
        self._bucle: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------ salidas
    def _decir(self, texto: str) -> None:
        print(texto, flush=True)

    def _subtitulo(self, texto: str) -> None:
        self._decir(f"  « {texto} »")
        if self.visor is not None:
            self.visor.subtitulo = texto
        if self.mundo is not None:
            self.mundo.subtitulo = texto

    def _frase(self, frase: Any) -> None:
        """Llamado desde el hilo del director: pasa la frase del guía a ER 2."""
        if self.visor is not None:
            self.visor.subtitulo = frase.texto
        if self.mundo is not None:
            self.mundo.subtitulo = frase.texto
        self._decir(f"  « {frase.texto} »")
        if self._bucle is not None:
            self._bucle.call_soon_threadsafe(self.agente.pedir, mensaje_frase(frase))

    def emergencia(self) -> None:
        self._emergencias += 1
        if self._emergencias == 1:
            self.d.interrumpir()
            self.s.parar(emergencia=True)
            self._decir("PARADA DE EMERGENCIA: brazos quietos. Otra pulsación quita el par; /rearmar para seguir.")
        else:
            self.s.quitar_par()

    def estado_breve(self) -> str:
        con = "conectado" if self.agente.conectado else "SIN CONEXIÓN"
        brazos = "  ".join(f"{n}: {self.s.coreos[n].gesto_actual}" for n in self.s.nombres)
        voz = ""
        if self.guia is not None:
            voz = f" | voz {'conectada' if self.guia.conectado else 'SIN CONEXIÓN'}"
        return f" ER 2 {con} · {self.agente.latencia_s:.1f} s{voz} | {brazos} "

    # ------------------------------------------------------------ órdenes
    def orden(self, linea: str) -> None:
        linea = linea.strip()
        if not linea:
            return
        if linea in ("/salir", "salir"):
            self.fin.set()
        elif linea == "/ayuda":
            self._decir(AYUDA)
        elif linea == "/estado":
            import json
            self._decir(json.dumps(self.s.estado(), ensure_ascii=False, indent=1))
            self._decir(self.estado_breve())
        elif linea == "/llamadas":
            for ll in self.agente.llamadas[-10:]:
                self._decir(f"  {ll['funcion']}({ll['args']}) → {ll['respuesta']}")
        elif linea == "/parar":
            self.d.interrumpir()
            self.s.parar()
            self.agente.pedir("El usuario ha pedido parar. No continúes hasta nueva orden.", urgente=True)
        elif linea == "/rearmar":
            self._emergencias = 0
            for n in self.s.nombres:
                self.s.brazos[n].activar_par()
            self.s.rearmar()
        elif linea.startswith("/"):
            self._decir("Orden desconocida. Escribe /ayuda.")
        else:
            self.registro.evento("usuario", texto=linea)
            if self.guia is not None:
                self.guia.pedir(linea)
            else:
                self.agente.pedir(linea, urgente=True, es_tarea=True)

    # ------------------------------------------------------------ bucles
    async def _terminal(self) -> None:
        if not sys.stdin.isatty():
            while not self.fin.is_set():
                linea = await asyncio.to_thread(sys.stdin.readline)
                if not linea:
                    break
                self.orden(linea)
            while not self.fin.is_set() and (self.s.ocupado() or self.d.activo):
                await asyncio.sleep(0.2)
            self.fin.set()
            return
        from prompt_toolkit import PromptSession
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.patch_stdout import patch_stdout
        teclas = KeyBindings()

        @teclas.add("escape", eager=True)
        @teclas.add("f12")
        def _(evento: Any) -> None:
            self.emergencia()

        sesion: PromptSession = PromptSession(key_bindings=teclas, bottom_toolbar=self.estado_breve,
                                              refresh_interval=0.5)
        self._decir(AYUDA)
        with patch_stdout():
            while not self.fin.is_set():
                try:
                    self.orden(await sesion.prompt_async("so101er> "))
                except KeyboardInterrupt:
                    self.s.parar(emergencia=True)
                    self.s.quitar_par()
                    self.fin.set()
                except EOFError:
                    self.fin.set()

    async def _una_peticion(self) -> None:
        """Hace una sola petición y termina cuando la explicación ha acabado."""
        import time
        limite = time.perf_counter() + 20.0
        while not self.agente.conectado and time.perf_counter() < limite and not self.fin.is_set():
            await asyncio.sleep(0.1)
        self._decir(f"> {self.peticion}")
        self.orden(self.peticion)
        limite, quieto = time.perf_counter() + 240.0, None
        while not self.fin.is_set() and time.perf_counter() < limite:
            await asyncio.sleep(0.2)
            activo = self.s.ocupado() or self.d.activo or not self.agente.llamadas
            quieto = None if activo else (quieto or time.perf_counter())
            if quieto is not None and time.perf_counter() - quieto > 2.5:
                break
        self.fin.set()

    async def ejecutar(self) -> None:
        self._bucle = asyncio.get_running_loop()
        if self.mundo is not None:
            self.mundo.iniciar(ventana=self._ventana, camaras=True)
        self.s.iniciar()
        self.d.iniciar()
        if self.altavoz is not None:
            self.altavoz.iniciar()
            if self._quiere_microfono and self.guia is not None:
                from .interfaz.audio import Microfono
                self.micro = Microfono(self._bucle)
                self.micro.iniciar()
                self.guia.microfono = self.micro
        if self.visor is not None:
            threading.Thread(target=self.visor.bucle_ventana, args=(self.fin, self.emergencia), name="ventana",
                             daemon=True).start()
        tareas = [asyncio.create_task(self.agente.ejecutar()),
                  asyncio.create_task(self._una_peticion() if self.peticion else self._terminal())]
        if self.guia is not None:
            tareas.append(asyncio.create_task(self.guia.ejecutar()))

        async def vigilar() -> None:
            import time
            peor, ultimo = 0.0, time.perf_counter()
            while not self.fin.is_set():
                t0 = time.perf_counter()
                await asyncio.sleep(0.1)
                peor = max(peor, time.perf_counter() - t0 - 0.1)
                if time.perf_counter() - ultimo > 2.0:
                    datos = {"retraso_bucle_ms": round(peor * 1000), "jitter": self.s.resumen_jitter()}
                    if self.mundo is not None:
                        datos["saltos_fisica"] = self.mundo.saltos
                    if self.flujo is not None:
                        datos.update(audio_recibido_s=round(self.voz.recibidas / self.voz.frecuencia, 2),
                                     audio_sonado_s=round(self.voz.reproducidas / self.voz.frecuencia, 2))
                    self.registro.evento("pulso", **datos)
                    peor, ultimo = 0.0, time.perf_counter()
        tareas.append(asyncio.create_task(vigilar()))
        try:
            hechas, _ = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
            for t in hechas:
                if t.exception():
                    raise t.exception()
        finally:
            self.fin.set()
            self.agente.cerrar()
            if self.guia is not None:
                self.guia.cerrar()
            await asyncio.wait(tareas, timeout=2.0)
            for t in tareas:
                t.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
            for cosa in (self.micro, self.altavoz):
                if cosa is not None:
                    cosa.cerrar()
            self.d.cerrar()
            if hasattr(self.voz, "cerrar"):
                self.voz.cerrar()
            self.s.cerrar()
            if self.mundo is not None:
                self.mundo.cerrar()
            self.registro.cerrar()
            if self.registro.ruta:
                self._decir(f"Registro de la sesión: {self.registro.ruta}")
