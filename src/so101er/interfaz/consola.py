"""Consola manual: prueba todos los gestos sin IA."""
from __future__ import annotations

import json
import shlex
import sys
import threading
from typing import Any

from ..control.cualidades import Cualidades
from ..control.gestos import ALIAS, FORMAS, GESTOS, ErrorGesto, Gesto, tipo_canonico
from ..sincronia.partitura import ErrorPartitura, Partitura

BRAZOS = ("izq", "der", "todos", "ambos", "auto")
AYUDA = """Gestos (el brazo es opcional: izq, der, todos o auto; los puntos son y x de 0 a 1000):
  senalar [brazo] Y X              apuntar a un punto de la obra
  trazar [brazo] Y,X Y,X ...       recorrer una línea
  abarcar [brazo] Y,X Y,X          barrer una zona
  forma [brazo] NOMBRE [Y X TAM]   circulo, espiral, onda, vertical, horizontal, zigzag, ocho
  ondular [brazo] [Y,X Y,X]        onda sobre la obra o en el aire
  elevar | descender | presentar | recoger | suspender | contrastar | reposo [brazo]
  medir [brazo] TAMANO             tamaño de 0 a 1
Opciones de cualquier gesto: estilo=solemne amplitud=0.9 peso= tiempo= espacio= flujo=
  curvatura= tension= relacion=espejo|canon|acompanar y los parámetros propios (mantener=2 ...)
Voz y partituras:
  decir "texto" [estilo=...]       frase con voz muda y acentos automáticos
  partitura ARCHIVO.json           interpretar una partitura
  demo                             partitura de demostración
  interrumpir                      cortar la voz (los brazos se recogen)
Control:
  matizar energia=1 amplitud=1 tempo=1
  estado | estilos | parar [brazo] | emergencia | rearmar | ayuda | salir
Parada de emergencia: Esc o F12 (segunda pulsación: quita el par). Ctrl+C: quita el par y sale."""


def _valor(texto: str) -> Any:
    if "," in texto:
        return [_valor(x) for x in texto.split(",") if x]
    try:
        return float(texto) if any(c in texto for c in ".eE") else int(texto)
    except ValueError:
        return texto


def _punto(texto: str) -> list[float]:
    v = _valor(texto)
    if not isinstance(v, list) or len(v) != 2:
        raise ErrorGesto(f"punto no válido: '{texto}'. Escribe Y,X (por ejemplo 400,300)")
    return v


def crear_gesto(tokens: list[str]) -> Gesto:
    """Convierte una línea de la consola en un gesto."""
    tipo = tipo_canonico(tokens[0])
    resto = tokens[1:]
    brazo = "auto"
    if resto and resto[0] in BRAZOS:
        brazo, resto = resto[0], resto[1:]
    pos = [x for x in resto if "=" not in x]
    claves = dict(x.split("=", 1) for x in resto if "=" in x)
    params: dict[str, Any] = {}
    if tipo == "senalar":
        if len(pos) != 2:
            raise ErrorGesto("uso: senalar [brazo] Y X")
        params["punto"] = [_valor(pos[0]), _valor(pos[1])]
    elif tipo == "trazar":
        params["puntos"] = [_punto(x) for x in pos]
    elif tipo == "abarcar" or (tipo == "ondular" and pos):
        if len(pos) != 2:
            raise ErrorGesto(f"uso: {tipo} [brazo] Y,X Y,X")
        params["desde"], params["hasta"] = _punto(pos[0]), _punto(pos[1])
    elif tipo == "dibujar_forma":
        if not pos or pos[0] not in FORMAS:
            raise ErrorGesto(f"uso: forma [brazo] NOMBRE [Y X TAM]. Formas: {', '.join(FORMAS)}")
        params["forma"] = pos[0]
        if len(pos) >= 3:
            params["centro"] = [_valor(pos[1]), _valor(pos[2])]
        if len(pos) >= 4:
            params["tamano"] = _valor(pos[3])
    elif tipo == "medir" and pos:
        params["tamano"] = _valor(pos[0])
    elif pos:
        raise ErrorGesto(f"{tipo}: sobran argumentos: {' '.join(pos)}")
    g = Gesto(tipo, brazo, params)
    for k, v in claves.items():
        if k == "estilo":
            g.estilo = v
        elif k == "relacion":
            g.relacion = v
        elif k in Cualidades.nombres():
            g.cualidades[k] = _valor(v)
        elif k in ("centro", "desde", "hasta", "punto"):
            g.params[k] = _punto(v)
        else:
            g.params[k] = _valor(v)
    return g


class Consola:
    def __init__(self, sistema: Any, director: Any, visor: Any = None) -> None:
        self.s, self.d, self.visor = sistema, director, visor
        self.fin = threading.Event()
        self._emergencias = 0

    def emergencia(self) -> str:
        """Primera pulsación: todo quieto manteniendo la posición. Segunda: quita el par."""
        self._emergencias += 1
        if self._emergencias == 1:
            self.d.interrumpir() if self.d.activo else None
            self.s.parar(emergencia=True)
            return "PARADA DE EMERGENCIA: brazos quietos. Otra pulsación quita el par; 'rearmar' para seguir."
        self.s.quitar_par()
        return "Par desactivado."

    def ejecutar(self, linea: str) -> str:
        """Ejecuta una línea y devuelve el texto de respuesta."""
        try:
            tokens = shlex.split(linea)
        except ValueError as e:
            return f"No entiendo la línea: {e}"
        if not tokens:
            return ""
        orden = tokens[0].lower()
        try:
            if orden in ("salir", "exit", "quit"):
                self.fin.set()
                return "Cerrando…"
            if orden in ("ayuda", "help", "?"):
                return AYUDA
            if orden == "estado":
                return json.dumps(self.s.estado(), ensure_ascii=False, indent=1)
            if orden == "estilos":
                return "\n".join(f"  {n}: {c}" for n, c in sorted(self.s.cfg.estilos.items()))
            if orden == "parar":
                self.d.interrumpir() if self.d.activo else None
                self.s.parar(tokens[1] if len(tokens) > 1 else "todos")
                return "Parado. El siguiente gesto reanuda el movimiento."
            if orden == "emergencia":
                return self.emergencia()
            if orden == "rearmar":
                self._emergencias = 0
                for n in self.s.nombres:
                    self.s.brazos[n].activar_par()
                self.s.rearmar()
                return "Rearmado."
            if orden == "interrumpir":
                self.d.interrumpir()
                return "Voz interrumpida."
            if orden == "matizar":
                claves = {k: float(v) for k, v in (x.split("=", 1) for x in tokens[1:] if "=" in x)}
                sobran = set(claves) - {"energia", "amplitud", "tempo"}
                if sobran or not claves:
                    return "uso: matizar energia=1 amplitud=1 tempo=1"
                self.s.matizar(**claves)
                return "Hecho."
            if orden == "decir":
                textos = [x for x in tokens[1:] if "=" not in x or " " in x]
                claves = dict(x.split("=", 1) for x in tokens[1:] if "=" in x and " " not in x)
                if not textos:
                    return "uso: decir \"texto\" [estilo=...]"
                if claves.get("estilo"):
                    self.s.cfg.estilo(claves["estilo"])
                self.d.decir(" ".join(textos), estilo=claves.get("estilo"))
                return "Frase en cola."
            if orden == "partitura":
                if len(tokens) != 2:
                    return "uso: partitura ARCHIVO.json"
                self.d.interpretar(Partitura.cargar(tokens[1]))
                return "Partitura en cola."
            if orden == "demo":
                from ..demo import DEMO
                self.d.interpretar(Partitura.de_dict(DEMO))
                return "Demostración en cola."
            if orden in GESTOS or orden in ALIAS:
                g = crear_gesto(tokens)
                if self.visor is not None:
                    for clave in ("punto", "centro", "desde", "hasta"):
                        if clave in g.params:
                            self.visor.objetivos.append(g.params[clave])
                r = self.s.ejecutar(g)
                partes = [f"{b['brazo']}: ápice en {b['apice'] - b['inicio']:.1f} s, fin en {b['fin'] - b['inicio']:.1f} s"
                          + (f" ({'; '.join(b['avisos'])})" if b["avisos"] else "") for b in r["brazos"]]
                return "Aceptado. " + " | ".join(partes)
            return f"Orden desconocida: '{orden}'. Escribe 'ayuda'."
        except (ErrorGesto, ErrorPartitura) as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"

    def bucle(self) -> None:
        """Lee órdenes hasta 'salir'. Usa prompt_toolkit en una terminal; si no, la entrada estándar."""
        if sys.stdin.isatty():
            self._bucle_interactivo()
        else:
            for linea in sys.stdin:
                if self.fin.is_set():
                    break
                salida = self.ejecutar(linea.strip())
                if salida:
                    print(salida, flush=True)

    def _bucle_interactivo(self) -> None:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.patch_stdout import patch_stdout

        teclas = KeyBindings()

        @teclas.add("escape", eager=True)
        @teclas.add("f12")
        def _(evento: Any) -> None:
            print(self.emergencia())

        sesion: PromptSession = PromptSession(key_bindings=teclas)
        self.s.al_registrar = lambda texto: print(f"  · {texto}")
        print("Consola manual de so101er. Escribe 'ayuda' para ver las órdenes.")
        with patch_stdout():
            while not self.fin.is_set():
                try:
                    linea = sesion.prompt("so101er> ")
                except KeyboardInterrupt:
                    self.s.parar(emergencia=True)
                    self.s.quitar_par()
                    print("Ctrl+C: par desactivado. Saliendo.")
                    self.fin.set()
                    break
                except EOFError:
                    self.fin.set()
                    break
                salida = self.ejecutar(linea)
                if salida:
                    print(salida)
