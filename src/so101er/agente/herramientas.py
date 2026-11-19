"""Funciones que ve Gemini Robotics ER 2 y puerta de entrada para ejecutarlas.

ER 2 **compone todo el movimiento**: no elige entre gestos prefabricados, sino
que da los puntos clave de cada trayectoria (adónde mira el brazo sobre la obra
o qué pose adopta en el aire), cuándo se alcanza cada uno y con qué carácter.
El programa solo une esos puntos con suavidad y aplica la seguridad.

- `declaraciones(sistema)`: el conjunto de funciones, según el modo y los estilos.
- `para_live` / `para_interacciones`: el mismo conjunto en el formato de cada API.
- `ejecutar_llamada`: ejecuta una llamada y devuelve enseguida "aceptado, en
  curso" o un error redactado para que el modelo pueda corregirse.

La biblioteca de gestos con nombre (senalar, elevar…) sigue existiendo para la
consola manual y la demostración sin IA, pero no se ofrece a ER 2.
"""
from __future__ import annotations

from typing import Any

from ..config import ErrorConfig
from ..control.cualidades import Cualidades
from ..control.gestos import ALIAS, GESTOS, ErrorGesto, Gesto
from ..sincronia.partitura import ErrorPartitura, Frase, Partitura

PUNTO_CLAVE = {
    "type": "object",
    "description": "Un punto clave del movimiento. O bien 'mira' (el brazo apunta a ese punto de la obra), o bien "
                   "una pose en el aire (alcance, altura, lado, inclinacion). 'giro' y 'pinza' valen en los dos casos.",
    "properties": {
        "mira": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                 "description": "Punto [y, x] de la imagen (0–1000) al que apunta el brazo. Dos puntos 'mira' "
                                "seguidos sin pausa hacen que la punta recorra la línea entre ellos sobre la obra."},
        "alcance": {"type": "number", "description": "0 = brazo recogido junto al cuerpo … 1 = extendido del todo. "
                                                     "Con 'mira': cuánto se acerca a la obra."},
        "altura": {"type": "number", "description": "Pose en el aire: 0 = a ras de mesa … 1 = lo más alto posible."},
        "lado": {"type": "number", "description": "Pose en el aire: grados hacia fuera (+) o hacia el centro (−), "
                                                  "de −90 a 90."},
        "inclinacion": {"type": "number", "description": "Pose en el aire: grados que la mano mira hacia arriba (+) "
                                                         "o hacia abajo (−), de −80 a 80."},
        "giro": {"type": "number", "description": "Giro de la muñeca en grados, de −150 a 150 (0 = neutra)."},
        "pinza": {"type": "number", "description": "Apertura de la mano: 0 cerrada (dedo que señala) … 100 abierta "
                                                   "(palma)."},
        "duracion": {"type": "number", "description": "Segundos para llegar a este punto desde el anterior. Si se "
                                                      "omite, lo decide el carácter del movimiento."},
        "pausa": {"type": "number", "description": "Segundos que el brazo se queda en este punto (suspendido, "
                                                   "respirando) antes de seguir. Sin pausa, pasa por él sin frenar."},
        "ancla": {"type": "integer", "description": "Índice (desde 0) de la palabra de la frase en la que el brazo "
                                                    "debe estar llegando a este punto."},
        "circulo": {"type": "object", "description": "Al llegar a este punto, la mano gira en círculos a partir de "
                                                     "él (remover, lazo, rueda, limpiar, saludar).", "properties": {
            "radio": {"type": "number", "description": "0 pequeño … 1 grande"},
            "vueltas": {"type": "number", "description": "Número de vueltas, de 0.25 a 5"},
            "plano": {"type": "string", "enum": ["frontal", "horizontal", "lateral"],
                      "description": "frontal: de cara (limpiar un cristal, saludar). horizontal: como un lazo o "
                                     "remover. lateral: hacia delante, como una rueda."},
            "sentido": {"type": "number", "description": "1 o −1"},
            "ratio": {"type": "number", "description": "1 círculo … 0 vaivén en línea recta"}}},
        "separacion": {"type": "number", "description": "SOLO con brazo 'ambos': distancia entre las dos manos, "
                                                         "0 = juntas en el centro … 1 = abiertas del todo."},
        "adelante": {"type": "number", "description": "SOLO con brazo 'ambos': 0 = manos cerca del cuerpo … 1 = "
                                                       "lejos, hacia la obra."},
        "desnivel": {"type": "number", "description": "SOLO con brazo 'ambos': −1 … 1; positivo sube la mano "
                                                       "izquierda y baja la derecha (balanza, inclinación)."},
    },
}
BIMANUAL = ("separacion", "adelante", "desnivel")


def _esquema_movimiento(sistema: Any) -> dict:
    dos = len(sistema.nombres) == 2
    props: dict[str, Any] = {
        "brazo": {"type": "string", "enum": list(sistema.nombres) + (["ambos"] if dos else []),
                  "description": "Brazo que hace el movimiento." + (
                      " 'ambos': las dos manos a la vez, como las de una persona; cada punto da 'separacion', "
                      "'altura', 'adelante' y 'desnivel' de las manos." if dos else "")},
        "puntos": {"type": "array", "items": PUNTO_CLAVE, "minItems": 1, "maxItems": 16,
                   "description": "Puntos clave, en orden. Tú decides la forma del movimiento con ellos."},
        "estilo": {"type": "string", "enum": sorted(sistema.cfg.estilos),
                   "description": "Carácter con el que se unen los puntos (no cambia los puntos)."},
        "caracter": {"type": "object", "description": "Ajuste fino del carácter, cada valor de −1 a 1.", "properties": {
            "peso": {"type": "number", "description": "−1 ligero … +1 firme"},
            "tiempo": {"type": "number", "description": "−1 sostenido y lento … +1 súbito"},
            "espacio": {"type": "number", "description": "−1 indirecto, con rodeos … +1 directo"},
            "flujo": {"type": "number", "description": "−1 libre, con inercia … +1 contenido"},
            "curvatura": {"type": "number", "description": "0 recto … 1 muy curvo (arcos entre puntos)"}}},
        "mantener": {"type": "number", "description": "Segundos que se sostiene el último punto."},
        "repetir": {"type": "integer", "description": "Repite la lista de puntos como un ciclo, de 1 a 6 veces "
                                                      "(ritmos, vaivenes, alternancias)."},
    }
    if dos:
        props["relacion"] = {"type": "string", "enum": ["espejo", "canon"],
                             "description": "El otro brazo hace lo mismo a la vez (espejo) o con retraso (canon)."}
    return {"type": "object", "properties": props, "required": ["brazo", "puntos"]}


def declaraciones(sistema: Any, con_voz_en_flujo: bool = False, composicion: str = "libre") -> list[dict]:
    """Funciones disponibles para ER 2, en formato neutro (JSON Schema).

    composicion = "libre": ER 2 compone cada movimiento punto a punto (por defecto).
    composicion = "biblioteca": modo anterior, ER 2 elige gestos con nombre."""
    if composicion == "biblioteca":
        from .biblioteca import declaraciones_biblioteca
        return declaraciones_biblioteca(sistema, con_voz_en_flujo)
    mov = _esquema_movimiento(sistema)
    frase_props: dict[str, Any] = {
        "movimientos": {"type": "array", "items": mov,
                        "description": "Movimientos de la frase (uno por brazo, o varios seguidos)."},
    }
    if con_voz_en_flujo:
        frase_props["frase_id"] = {"type": "integer", "description": "Número de la frase que va a decir el guía."}
        requeridos = ["frase_id", "movimientos"]
        desc = ("Pone movimiento a la frase número 'frase_id' que el guía va a decir en voz alta. Usa 'ancla' en "
                "los puntos clave para que coincidan con sus palabras. Llama cuanto antes: la frase suena enseguida.")
    else:
        frase_props["texto"] = {"type": "string", "description": "La frase que se dirá al público (breve)."}
        frase_props["pausa"] = {"type": "number", "description": "Silencio tras la frase, en segundos."}
        requeridos = ["texto"]
        desc = ("Dice una frase al público y la acompaña con movimiento sincronizado. Usa 'ancla' en los puntos "
                "clave para que coincidan con palabras de 'texto'. Las frases se encolan: puedes llamar varias veces.")
    return [
        {"name": "frase_de_movimiento", "description": desc,
         "parameters": {"type": "object", "properties": frase_props, "required": requeridos}},
        {"name": "movimiento", "description": "Hace un movimiento ahora mismo, sin frase. Si el brazo ya se mueve, "
                                              "el movimiento nuevo se funde con el anterior sin parar.",
         "parameters": mov},
        {"name": "matizar", "description": "Cambia el carácter general sin reiniciar el movimiento.",
         "parameters": {"type": "object", "properties": {
             "energia": {"type": "number", "description": "Viveza del reposo, de 0 a 1,6 (1 = normal)."},
             "tempo": {"type": "number", "description": "Rapidez general, de 0,5 a 1,6."}}}},
        {"name": "parar", "description": "Detiene con suavidad los brazos y la explicación en curso.",
         "parameters": {"type": "object", "properties": {
             "brazo": {"type": "string", "enum": list(sistema.nombres) + ["todos"]}}}},
        {"name": "estado", "description": "Devuelve qué hace cada brazo, adónde apunta ([y, x]) y las alertas.",
         "parameters": {"type": "object", "properties": {}}},
    ]


def para_live(decls: list[dict]) -> list[dict]:
    """Formato de la Live API. Con robótica solo se admiten funciones bloqueantes."""
    return [{"function_declarations": [
        {"name": d["name"], "description": d["description"], "behavior": "BLOCKING",
         "parameters_json_schema": d["parameters"]} for d in decls]}]


def para_interacciones(decls: list[dict]) -> list[dict]:
    """Formato de la Interactions API."""
    return [{"type": "function", "name": d["name"], "description": d["description"],
             "parameters": d["parameters"]} for d in decls]


# ---------------------------------------------------------------- ejecución
def _mano_en_el_mundo(sistema: Any, nombre: str, pc: dict) -> list[float]:
    """Posición de una mano en el espacio común de los dos brazos (el "cuerpo")."""
    def valor(clave: str, defecto: float, lo: float, hi: float) -> float:
        x = pc.get(clave, defecto)
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ErrorGesto(f"'{clave}' debe ser un número entre {lo:g} y {hi:g}")
        return float(min(max(x, lo), hi))

    centro = sum(sistema.cfg.brazos[n].base_mm for n in sistema.nombres) / len(sistema.nombres)
    signo = -1.0 if nombre == "izq" else 1.0                        # la mano izquierda, a la izquierda
    desnivel = valor("desnivel", 0.0, -1.0, 1.0) * (1.0 if nombre == "izq" else -1.0)
    return [float(centro[0] + signo * (42.0 + 300.0 * valor("separacion", 0.4, 0.0, 1.0))),
            float(centro[1] + 130.0 + 190.0 * valor("adelante", 0.4, 0.0, 1.0)),
            float(70.0 + 290.0 * valor("altura", 0.5, 0.0, 1.0) + 90.0 * desnivel)]


def _movimiento(sistema: Any, args: dict) -> list[Gesto]:
    """Movimiento compuesto por ER 2 → trayectorias para el motor (una por brazo)."""
    if not isinstance(args, dict):
        raise ErrorGesto("cada movimiento debe ser un objeto con 'brazo' y 'puntos'")
    sobran = set(args) - {"brazo", "puntos", "estilo", "caracter", "mantener", "relacion", "repetir"}
    if sobran:
        raise ErrorGesto(f"movimiento: campos desconocidos: {', '.join(sorted(sobran))}. "
                         f"Admitidos: brazo, puntos, estilo, caracter, mantener, relacion, repetir")
    if str(args.get("brazo")) == "ambos":
        if len(sistema.nombres) != 2:
            raise ErrorGesto(f"brazo 'ambos' no disponible: en modo un brazo solo existe '{sistema.nombres[0]}'")
        puntos = args.get("puntos")
        if not isinstance(puntos, list) or not puntos:
            raise ErrorGesto("'puntos' debe ser una lista de 1 a 16 puntos clave")
        gestos = []
        for n in sistema.nombres:               # las dos manos hacen el mismo recorrido, en espejo
            propios = []
            for pc in puntos:
                if isinstance(pc, dict) and "mira" not in pc and (
                        any(c in pc for c in BIMANUAL) or not any(c in pc for c in ("alcance", "lado"))):
                    nuevo = {c: x for c, x in pc.items() if c not in BIMANUAL and c != "altura"}
                    nuevo["mundo"] = _mano_en_el_mundo(sistema, n, pc)
                    propios.append(nuevo)
                else:
                    propios.append(pc)
            gestos += _movimiento(sistema, {**args, "brazo": n, "puntos": propios})
        return gestos
    for pc in args.get("puntos") or []:
        if isinstance(pc, dict) and any(c in pc for c in BIMANUAL):
            raise ErrorGesto("'separacion', 'adelante' y 'desnivel' solo valen con brazo 'ambos'")
    caracter = args.get("caracter") or {}
    if not isinstance(caracter, dict):
        raise ErrorGesto("'caracter' debe ser un objeto, por ejemplo {\"tiempo\": -0.8}")
    params: dict[str, Any] = {"puntos": args.get("puntos")}
    for clave in ("mantener", "repetir"):
        if clave in args:
            params[clave] = args[clave]
    brazo = str(args.get("brazo", sistema.nombres[0] if len(sistema.nombres) == 1 else "auto"))
    return [Gesto("trayectoria", brazo, params, estilo=args.get("estilo"), cualidades=dict(caracter),
                  relacion=args.get("relacion"))]


def _gesto(sistema: Any, tipo: str, args: dict) -> Gesto:
    """Gesto con nombre de la biblioteca (consola manual, demostración y pruebas)."""
    args = dict(args)
    brazo = str(args.pop("brazo", "auto"))
    estilo = args.pop("estilo", None)
    cualidades = args.pop("cualidades", {}) or {}
    relacion = args.pop("relacion", None)
    ancla, t = args.pop("ancla", None), args.pop("t", None)
    if not isinstance(cualidades, dict):
        raise ErrorGesto("'cualidades' debe ser un objeto, por ejemplo {\"amplitud\": 0.8}")
    for k in list(args):
        if k in Cualidades.nombres():
            cualidades[k] = args.pop(k)
    if tipo == "definido":
        nombre = str(args.pop("nombre", ""))
        guardados = getattr(sistema, "gestos_definidos", {})
        if nombre not in guardados:
            raise ErrorGesto(f"no hay ningún gesto guardado con el nombre '{nombre}'. "
                             f"Guardados: {', '.join(sorted(guardados)) or 'ninguno'}")
        tipo, args = "gesto_libre", {"poses": guardados[nombre], **args}
    if tipo not in GESTOS and tipo not in ALIAS:
        raise ErrorGesto(f"gesto desconocido: '{tipo}'. Disponibles: {', '.join(sorted(GESTOS))}")
    return Gesto(tipo, brazo, args, estilo=estilo, cualidades=cualidades, relacion=relacion, ancla=ancla, t=t)


def _lista(sistema: Any, args: dict) -> list[Gesto]:
    salida = []
    movimientos = args.get("movimientos")
    if movimientos is not None:
        if not isinstance(movimientos, list):
            raise ErrorGesto("'movimientos' debe ser una lista")
        for m in movimientos:
            salida += _movimiento(sistema, m)
    for g in args.get("gestos") or []:            # compatibilidad: gestos con nombre
        if not isinstance(g, dict) or "tipo" not in g:
            raise ErrorGesto("cada gesto debe ser un objeto con al menos 'tipo'")
        salida.append(_gesto(sistema, str(g["tipo"]), {k: v for k, v in g.items() if k != "tipo"}))
    return salida


def ejecutar_llamada(sistema: Any, director: Any, nombre: str, args: dict | None, flujo: Any = None) -> dict:
    """Ejecuta una llamada a función y devuelve su respuesta (nunca lanza excepciones)."""
    args = args or {}
    if not isinstance(args, dict):
        return {"error": "los argumentos deben ser un objeto JSON"}
    try:
        if nombre == "estado":
            return sistema.estado()
        if nombre == "parar":
            if flujo is not None:
                flujo.interrumpir()
            elif director is not None and director.activo:
                director.interrumpir()
            sistema.parar(str(args.get("brazo", "todos")))
            return {"estado": "parado"}
        if nombre == "matizar":
            sobran = set(args) - {"energia", "amplitud", "tempo"}
            if sobran or not args:
                return {"error": "matizar admite energia, amplitud y tempo (números)"}
            return sistema.matizar(**{k: float(v) for k, v in args.items()})
        if nombre == "movimiento":
            gestos = _movimiento(sistema, args)
            for g in gestos:                     # se comprueba todo antes de mover nada
                for n in sistema.resolver_brazos(g):
                    sistema.planificar_solo(g, n)
            respuestas = [sistema.ejecutar(g) for g in gestos]
            return {"estado": "aceptado, en curso", "brazos": [b for r in respuestas for b in r["brazos"]]}
        if nombre == "definir_gesto":
            nombre_gesto, poses = str(args.get("nombre", "")).strip(), args.get("poses")
            if not nombre_gesto:
                return {"error": "definir_gesto necesita 'nombre'"}
            sistema.planificar_solo(Gesto("gesto_libre", sistema.nombres[0], {"poses": poses}), sistema.nombres[0])
            if not hasattr(sistema, "gestos_definidos"):
                sistema.gestos_definidos = {}
            sistema.gestos_definidos[nombre_gesto] = poses
            return {"estado": "guardado", "nombre": nombre_gesto}
        if nombre == "frase_de_movimiento":
            gestos = _lista(sistema, args)
            if args.get("estilo"):
                sistema.cfg.estilo(args["estilo"])
            if flujo is not None:
                if "frase_id" not in args:
                    return {"error": "falta 'frase_id': el número de la frase del guía a la que pones movimiento"}
                return flujo.coreografiar(int(args["frase_id"]), gestos, args.get("estilo"))
            if director is None:
                return {"error": "no hay director de voz en esta sesión"}
            texto = str(args.get("texto", "")).strip()
            if not texto:
                return {"error": "frase_de_movimiento necesita 'texto': la frase que se va a decir"}
            # Se valida antes de encolar, para que el modelo reciba el error ahora y no después.
            for g in gestos:
                for n in sistema.resolver_brazos(g):
                    sistema.planificar_solo(g, n)
            director.interpretar(Partitura([Frase(texto=texto, gestos=gestos, estilo=args.get("estilo"),
                                                  pausa=args.get("pausa"))]))
            return {"estado": "aceptado, en cola", "movimientos": len(gestos)}
        if nombre == "gesto":
            if "tipo" not in args:
                return {"error": f"falta 'tipo'. Disponibles: {', '.join(sorted(GESTOS))}"}
            return sistema.ejecutar(_gesto(sistema, str(args["tipo"]), {k: v for k, v in args.items() if k != "tipo"}))
        if nombre in GESTOS or nombre in ALIAS:      # nombre del gesto como función (consola y pruebas)
            return sistema.ejecutar(_gesto(sistema, nombre, args))
        return {"error": f"función desconocida: '{nombre}'. Disponibles: frase_de_movimiento, movimiento, "
                         f"matizar, parar, estado"}
    except (ErrorGesto, ErrorPartitura, ErrorConfig) as e:
        return {"error": str(e)}
    except (TypeError, ValueError) as e:
        return {"error": f"argumentos no válidos: {e}"}
