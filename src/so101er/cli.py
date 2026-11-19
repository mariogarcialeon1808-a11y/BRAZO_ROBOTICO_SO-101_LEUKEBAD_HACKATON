"""Comando `so101er`."""
from __future__ import annotations

import argparse
import json
import sys
import threading

from .config import ErrorConfig, cargar, detectar_wsl


def _comunes(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="archivo de configuración (por defecto config/so101er.toml)")
    p.add_argument("--modo", choices=["uno", "dos"], help="número de brazos")
    p.add_argument("--brazo", choices=["izq", "der"], help="brazo usado en modo uno")
    p.add_argument("--sim", action="store_true", help="sin hardware: brazos simulados")
    p.add_argument("--mujoco", action="store_true",
                   help="simulación 3D en MuJoCo, en tiempo real (la foto de la carpeta obra/ es el cuadro)")


def _cargar(args: argparse.Namespace):
    return cargar(args.config, modo=args.modo, brazo=args.brazo, simulado=True if args.sim else None)


def _manual(args: argparse.Namespace) -> int:
    from .interfaz.consola import Consola
    from .sincronia.director import Director
    from .sincronia.voz import VozMuda
    from .sistema import Sistema

    from .montaje import montar
    cfg = _cargar(args)
    if args.mujoco:
        cfg.simulado = True
    s, mundo = montar(cfg, args.mujoco)
    visor = None
    if mundo is not None:
        mundo.iniciar(ventana=not args.sin_ventana)
    elif not args.sin_ventana:
        from .interfaz.visor import Visor
        visor = Visor(s)

    def subtitulo(texto: str) -> None:
        print(f"  « {texto} »", flush=True)
        if visor is not None:
            visor.subtitulo = texto
        if mundo is not None:
            mundo.subtitulo = texto

    d = Director(s, VozMuda(cfg.voz["silabas_por_segundo"], al_subtitulo=subtitulo))
    consola = Consola(s, d, visor)
    s.iniciar()
    d.iniciar()
    hilo_ventana = None
    if visor is not None:
        def clic(p: list[float]) -> None:
            print(consola.ejecutar(f"senalar auto {p[0]} {p[1]}"), flush=True)
        hilo_ventana = threading.Thread(
            target=visor.bucle_ventana, args=(consola.fin, lambda: print(consola.emergencia(), flush=True), clic),
            name="ventana", daemon=True)
        hilo_ventana.start()
    try:
        consola.bucle()
        if not sys.stdin.isatty():       # órdenes por tubería: esperar a que acaben
            import time
            time.sleep(0.3)
            while s.ocupado() or d.activo:
                time.sleep(0.1)
    except KeyboardInterrupt:
        s.parar(emergencia=True)
        s.quitar_par()
    finally:
        consola.fin.set()
        d.cerrar()
        s.cerrar()
        if mundo is not None:
            mundo.cerrar()
        print(f"Jitter del control: {json.dumps(s.resumen_jitter())}")
    return 0


def _demo(args: argparse.Namespace) -> int:
    from .demo import ejecutar_demo
    from .sincronia.partitura import ErrorPartitura, Partitura

    cfg = cargar(args.config, modo=args.modo, brazo=args.brazo, simulado=True)
    try:
        partitura = Partitura.cargar(args.partitura) if args.partitura else None
    except ErrorPartitura as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if args.mujoco:
        from .hardware.mujoco_sim import ErrorMuJoCo
        from .montaje import demo_en_mujoco
        try:
            return demo_en_mujoco(cfg, partitura)
        except ErrorMuJoCo as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
    from . import obra
    obra.preparar(cfg)
    informe = ejecutar_demo(cfg, partitura, video=args.video)
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    if args.video:
        print(f"Vídeo guardado en {args.video}")
    return 0


def _hablar(args: argparse.Namespace) -> int:
    from .agente.er2 import ErrorAgente
    from .conversacion.app import hablar
    from .conversacion.claves import ErrorClaves
    from .interfaz.audio import ErrorAudio

    cfg = _cargar(args)
    cfg.simulado = True
    try:
        return hablar(cfg, mujoco=args.mujoco, idioma=args.idioma, modelo=args.modelo, pedir=args.pedir,
                      microfono=not args.sin_microfono, ventana=not args.sin_ventana)
    except (ErrorAgente, ErrorAudio, ErrorClaves) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


def _estilos(args: argparse.Namespace) -> int:
    cfg = _cargar(args)
    for nombre, c in sorted(cfg.estilos.items()):
        print(f"{nombre:12s} {c}")
    return 0


def _run(args: argparse.Namespace) -> int:
    import asyncio

    from .agente.er2 import ErrorAgente
    from .interfaz.audio import ErrorAudio
    from .sesion import Sesion
    from .sincronia.voz_sintetizada import ErrorVoz

    cfg = _cargar(args)
    if args.mujoco:
        cfg.simulado = True
    if args.composicion:
        cfg.er2["composicion"] = args.composicion
    try:
        sesion = Sesion(cfg, voz=args.voz or cfg.voz["proveedor"], agente=args.agente,
                        ventana=not args.sin_ventana, microfono=not args.sin_microfono,
                        registrar=not args.sin_registro, mujoco=args.mujoco, peticion=args.pedir)
        asyncio.run(sesion.ejecutar())
    except (ErrorAgente, ErrorAudio, ErrorVoz) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        sys.stdin.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(prog="so101er", description="Brazos SO-101 que explican una obra con gestos.")
    sub = p.add_subparsers(dest="orden", required=True)
    g = sub.add_parser("gestos", help="cuatro ejemplos semánticos, solo vista previa local")
    _comunes(g)
    g.add_argument("--salida", default="salidas/gestos", help="carpeta para HTML y consignas JSON")
    g.add_argument("--referencia", help="motivo humano JSON: transfiere ritmo y conserva geometría")
    def demo_gestos(args):
        from .gestos_demo import exportar
        informe = exportar(_cargar(args), args.salida, args.referencia)
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0
    g.set_defaults(func=demo_gestos)
    imp = sub.add_parser("importar-movimiento", help="convierte BVH o joints_xyz NPZ a motivo local")
    imp.add_argument("archivo")
    imp.add_argument("--id", required=True)
    imp.add_argument("--fuente", required=True)
    imp.add_argument("--licencia", required=True)
    imp.add_argument("--hombro", required=True)
    imp.add_argument("--muneca", required=True)
    imp.add_argument("--etiquetas", nargs="+", default=[])
    imp.add_argument("--inicio", type=int, default=0)
    imp.add_argument("--fin", type=int)
    imp.add_argument("--fps", type=float)
    imp.add_argument("--salida", required=True)
    def importar_movimiento(args):
        from .control.referencias import extraer
        motivo = extraer(args.archivo, id=args.id, fuente=args.fuente, licencia=args.licencia,
                         hombro=args.hombro, muneca=args.muneca, etiquetas=args.etiquetas,
                         inicio=args.inicio, fin=args.fin, fps=args.fps)
        motivo.guardar(args.salida)
        print(json.dumps({"id":motivo.id,"sha256":motivo.sha256,"salida":args.salida}))
        return 0
    imp.set_defaults(func=importar_movimiento)
    a = sub.add_parser("iniciar", help="aplicación integrada: cuadro, IA, voz, micro y MuJoCo o USB")
    a.add_argument("--raiz", default=".")
    a.add_argument("--imagen")
    a.add_argument("--modelo", default="gemini-robotics-er-2-preview")
    a.add_argument("--voz", choices=["elevenlabs","local"], default="elevenlabs")
    a.add_argument("--demo", action="store_true")
    a.add_argument("--real", action="store_true", help="exige ambos puertos y calibraciones verificadas")
    def app_integrada(args):
        from .aplicacion import iniciar
        iniciar(args.raiz,imagen=args.imagen,modelo=args.modelo,voz=args.voz,demo=args.demo,real=args.real)
        return 0
    a.set_defaults(func=app_integrada)
    usb = sub.add_parser("usb", help="diagnóstico USB de lectura, sin activar par")
    def usb_diagnostico(args):
        from .hardware.usb import puertos,diagnosticar
        print(json.dumps({"puertos":puertos(),"brazos":diagnosticar()},ensure_ascii=False,indent=2))
        return 0
    usb.set_defaults(func=usb_diagnostico)
    m = sub.add_parser("manual", help="consola manual sin IA")
    _comunes(m)
    m.add_argument("--sin-ventana", action="store_true", help="no abrir la ventana de vídeo")
    m.set_defaults(func=_manual)
    d = sub.add_parser("demo", help="demostración en simulación (por pasos), con informe y vídeo opcional")
    _comunes(d)
    d.add_argument("--partitura", help="archivo JSON de partitura (por defecto, la de ejemplo)")
    d.add_argument("--video", help="guardar un vídeo MP4 de la simulación")
    d.set_defaults(func=_demo)
    h = sub.add_parser("hablar", help="conversación: un chatbot habla (voz de ElevenLabs) y ER 2 mueve los brazos")
    _comunes(h)
    h.add_argument("--idioma", choices=["es", "en"], help="idioma de la conversación")
    h.add_argument("--modelo", choices=["haiku", "sonnet"], help="modelo del chatbot")
    h.add_argument("--pedir", metavar="TEXTO", help="hace una sola pregunta y sale al terminar la respuesta")
    h.add_argument("--sin-microfono", action="store_true", help="solo preguntas escritas")
    h.add_argument("--sin-ventana", action="store_true", help="no abrir la ventana de la simulación")
    h.set_defaults(func=_hablar)
    e = sub.add_parser("estilos", help="lista los estilos expresivos")
    _comunes(e)
    e.set_defaults(func=_estilos)
    r = sub.add_parser("run", help="explicación con IA: Gemini Robotics ER 2 pone los gestos")
    _comunes(r)
    r.add_argument("--voz", choices=["local", "tts", "muda", "live"],
                   help="local: voz de Windows (por defecto); tts: Gemini TTS; muda: subtítulos; "
                        "live: habla Gemini 3.8 Live")
    r.add_argument("--agente", choices=["directo", "estandar"], default="directo",
                   help="directo: Live API (por defecto); estandar: Interactions API (reserva)")
    r.add_argument("--pedir", metavar="TEXTO", help="hace una sola petición y sale al terminar la explicación")
    r.add_argument("--composicion", choices=["libre", "biblioteca"],
                   help="libre: ER 2 compone cada movimiento (por defecto); biblioteca: elige gestos con nombre")
    r.add_argument("--sin-ventana", action="store_true", help="no abrir la ventana de vídeo")
    r.add_argument("--sin-microfono", action="store_true", help="con voz live: no escuchar por el micrófono")
    r.add_argument("--sin-registro", action="store_true", help="no guardar el registro de la sesión")
    r.set_defaults(func=_run)
    args = p.parse_args(argv)
    if detectar_wsl():
        print("Aviso: estás dentro de WSL2. El USB-serie y las webcams no funcionan bien ahí; "
              "usa Windows o Linux nativos.", file=sys.stderr)
    try:
        return args.func(args)
    except ErrorConfig as e:
        print(f"Error de configuración: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())



