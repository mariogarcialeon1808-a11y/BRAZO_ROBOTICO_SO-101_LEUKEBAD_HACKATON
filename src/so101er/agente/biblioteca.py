"""Modo anterior (se conserva): ER 2 elige gestos con nombre de una biblioteca.

En este modo ER 2 no compone el recorrido: escoge entre gestos ya definidos
(senalar, elevar, presentar…) y ajusta sus parámetros. Se activa con
`er2.composicion = "biblioteca"` o `so101er run --composicion biblioteca`.
El modo por defecto es "libre" (ver herramientas.py y prompt_sistema.py).
"""
from __future__ import annotations

from typing import Any

from ..control.gestos import FORMAS, GESTOS

PUNTO = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
         "description": "Punto [y, x] de la imagen, cada valor de 0 a 1000 (y hacia abajo, x hacia la derecha)."}
POSE = {"type": "object", "description": "Pose clave en el espacio expresivo del brazo.", "properties": {
    "alcance": {"type": "number", "description": "0 recogido … 1 extendido"},
    "azimut": {"type": "number", "description": "Grados hacia fuera (+) o hacia dentro (−), de −90 a 90"},
    "altura": {"type": "number", "description": "0 bajo … 1 alto"},
    "elevacion": {"type": "number", "description": "Inclinación de la pinza en grados, de −80 a 80"},
    "giro": {"type": "number", "description": "Giro de muñeca en grados, de −150 a 150"},
    "pinza": {"type": "number", "description": "Apertura de 0 (cerrada) a 100 (abierta)"},
    "pausa": {"type": "number", "description": "Segundos de espera tras llegar"}}}

SIGNIFICADO = {
    "senalar": "apunta a 'punto' y sostiene ('mantener' segundos)",
    "trazar": "recorre la línea 'puntos' (contornos, diagonales, direcciones)",
    "abarcar": "barre de 'desde' a 'hasta' con la pinza abierta (una zona entera)",
    "dibujar_forma": "dibuja 'forma' (círculo, espiral, onda…) sobre la obra ('centro', 'tamano') o en el aire",
    "ondular": "onda de 'desde' a 'hasta', o en el aire: agua, tela, luz, música",
    "elevar": "sube y se abre: importancia, crecimiento, luz, alegría",
    "descender": "baja y se cierra: caída, peso, tristeza, calma",
    "medir": "muestra un tamaño con la pinza ('tamano' de 0 a 1)",
    "contrastar": "un lado y luego el otro: \"por un lado… por otro\"",
    "suspender": "pausa contenida antes de una idea clave ('duracion')",
    "presentar": "se abre hacia fuera: mostrar, ofrecer, dar la bienvenida",
    "recoger": "se recoge hacia dentro: intimidad, recogimiento, final",
    "reposo": "vuelve al descanso",
    "gesto_libre": "gesto inventado con 'poses' clave",
}
TIPOS = sorted(set(GESTOS) - {"trayectoria"})


def _esquema_gesto(sistema: Any, con_ancla: bool) -> dict:
    dos = len(sistema.nombres) == 2
    brazos = list(sistema.nombres) + (["todos", "auto"] if dos else [])
    props: dict[str, Any] = {
        "tipo": {"type": "string", "enum": TIPOS + ["definido"],
                 "description": "; ".join(f"{k}: {v}" for k, v in SIGNIFICADO.items())
                                + "; definido: un gesto guardado con definir_gesto ('nombre')."},
        "brazo": {"type": "string", "enum": brazos,
                  "description": "Brazo que hace el gesto." + (" 'auto' elige el más cercano al punto." if dos else "")},
        "estilo": {"type": "string", "enum": sorted(sistema.cfg.estilos),
                   "description": "Carácter del movimiento."},
        "amplitud": {"type": "number", "description": "Tamaño del gesto, de 0 (mínimo) a 1 (amplio)."},
        "punto": PUNTO, "desde": PUNTO, "hasta": PUNTO, "centro": PUNTO,
        "puntos": {"type": "array", "items": PUNTO, "description": "Lista de puntos [y, x] de una línea."},
        "forma": {"type": "string", "enum": list(FORMAS)},
        "plano": {"type": "string", "enum": ["cuadro", "aire"], "description": "Dónde se dibuja la forma."},
        "tamano": {"type": "number", "description": "Formas sobre la obra: diámetro en unidades de imagen (20–1000). "
                                                    "Formas en el aire: 0,2–1,5. medir: 0–1."},
        "vueltas": {"type": "number"}, "ondas": {"type": "number"},
        "lado": {"type": "string", "enum": ["a", "b"], "description": "contrastar: solo un lado."},
        "mantener": {"type": "number", "description": "Segundos que se sostiene el gesto al llegar."},
        "duracion": {"type": "number", "description": "Duración en segundos (trazos, formas, suspender)."},
        "poses": {"type": "array", "items": POSE, "description": "gesto_libre: de 1 a 12 poses clave."},
        "nombre": {"type": "string", "description": "definido: nombre del gesto guardado."},
    }
    if dos:
        props["relacion"] = {"type": "string", "enum": ["espejo", "canon", "acompanar"],
                             "description": "Qué hace el otro brazo: lo mismo, lo mismo con retraso, o acompaña."}
    if con_ancla:
        props["ancla"] = {"type": "integer", "description": "Índice (desde 0) de la palabra de la frase en la que "
                                                            "debe caer el momento principal del gesto."}
    return {"type": "object", "properties": props, "required": ["tipo"]}


def declaraciones_biblioteca(sistema: Any, con_voz_en_flujo: bool = False) -> list[dict]:
    """Funciones para ER 2 en el modo de biblioteca de gestos."""
    brazos_parar = list(sistema.nombres) + ["todos"]
    frase_props: dict[str, Any] = {
        "gestos": {"type": "array", "items": _esquema_gesto(sistema, True),
                   "description": "Gestos de la frase, cada uno anclado a una palabra."},
        "estilo": {"type": "string", "enum": sorted(sistema.cfg.estilos)},
    }
    if con_voz_en_flujo:
        frase_props["frase_id"] = {"type": "integer", "description": "Número de la frase que va a decir el guía."}
        requeridos = ["frase_id", "gestos"]
        desc = ("Coreografía la frase número 'frase_id' que el guía va a decir en voz alta. Ancla cada gesto a "
                "una palabra de esa frase. Llama cuanto antes: la frase suena poco después.")
    else:
        frase_props["texto"] = {"type": "string", "description": "La frase que se dirá al público (breve)."}
        frase_props["pausa"] = {"type": "number", "description": "Silencio tras la frase, en segundos."}
        requeridos = ["texto"]
        desc = ("Dice una frase al público y la acompaña con gestos sincronizados. Cada gesto se ancla a una "
                "palabra de 'texto'. Las frases se encolan: puedes llamar varias veces seguidas.")
    return [
        {"name": "frase_de_movimiento", "description": desc,
         "parameters": {"type": "object", "properties": frase_props, "required": requeridos}},
        {"name": "gesto", "description": "Hace un gesto ahora mismo, sin frase. Si el brazo ya se mueve, el gesto "
                                         "nuevo se funde con el anterior sin parar.",
         "parameters": _esquema_gesto(sistema, False)},
        {"name": "definir_gesto", "description": "Guarda un gesto inventado (poses clave) para reutilizarlo con "
                                                 "tipo 'definido'.",
         "parameters": {"type": "object", "properties": {
             "nombre": {"type": "string"}, "poses": {"type": "array", "items": POSE}},
             "required": ["nombre", "poses"]}},
        {"name": "matizar", "description": "Cambia el carácter general sin reiniciar el movimiento.",
         "parameters": {"type": "object", "properties": {
             "energia": {"type": "number", "description": "Viveza del reposo, de 0 a 1,6 (1 = normal)."},
             "amplitud": {"type": "number", "description": "Tamaño general de los gestos, de 0,3 a 1,3."},
             "tempo": {"type": "number", "description": "Rapidez general, de 0,5 a 1,6."}}}},
        {"name": "parar", "description": "Detiene con suavidad los brazos y la explicación en curso.",
         "parameters": {"type": "object", "properties": {"brazo": {"type": "string", "enum": brazos_parar}}}},
        {"name": "estado", "description": "Devuelve qué hace cada brazo, adónde apunta ([y, x]) y las alertas.",
         "parameters": {"type": "object", "properties": {}}},
    ]


def prompt_biblioteca(sistema: Any, con_voz_en_flujo: bool, escena: str) -> str:
    """Prompt de sistema para ER 2 en el modo de biblioteca de gestos."""
    estilos = ", ".join(sorted(sistema.cfg.estilos))
    gestos = "\n".join(f"- {k}: {v}." for k, v in SIGNIFICADO.items())
    if con_voz_en_flujo:
        trabajo = (
            "CÓMO TRABAJAS\n"
            "Un guía (otra IA) explica la obra en voz alta. Tú no hablas al público: pones los gestos.\n"
            "Recibirás mensajes así: «Frase 7: \"Arriba, el sol domina la escena.\" Palabras: 0:Arriba, 1:el "
            "2:sol …». La frase sonará poco después. Responde enseguida con UNA llamada a "
            "frase_de_movimiento(frase_id, gestos, estilo), anclando cada gesto ('ancla') al índice de la "
            "palabra donde debe caer. Si una frase no pide gesto, envía gestos vacíos: el brazo ya marca el "
            "ritmo por sí solo. No escribas texto salvo que haya un problema.")
    else:
        trabajo = (
            "CÓMO TRABAJAS\n"
            "El usuario te pide por texto que expliques la obra o una parte. Tú escribes la explicación y "
            "sus gestos: llama a frase_de_movimiento una vez por frase (texto breve, de 8 a 16 palabras), con "
            "los gestos anclados ('ancla') al índice de la palabra, contando desde 0, donde debe caer cada "
            "gesto. Puedes encolar varias frases seguidas. La voz y los brazos las interpretan en orden. "
            "Para un gesto suelto sin frase, usa gesto(...). Responde con texto solo para avisar de algo.")
    return f"""Eres el coreógrafo de un guía de museo robótico. Tu función es convertir una explicación en \
EXPRESIÓN CORPORAL: movimientos suaves, relajados y descriptivos, como los brazos de una bailarina.

ESCENA
{escena}
Ves la obra por la cámara. Los puntos se dan siempre como [y, x] en coordenadas de imagen de 0 a 1000:
y crece hacia abajo, x hacia la derecha; [0, 0] es la esquina superior izquierda. Respeta el orden [y, x].
Localiza tú en la imagen lo que haya que señalar (figuras, objetos, líneas de composición, zonas de luz).

{trabajo}

GESTOS
{gestos}

ESTILOS (parámetro 'estilo'): {estilos}.
Elige el estilo por el contenido: solemne para lo grave, entusiasta para lo luminoso, misterioso para lo
oculto, didactico para lo técnico, tierno para lo íntimo, dramatico para lo intenso. 'amplitud' (0–1)
ajusta el tamaño.

CÓMO HACER BUENA EXPRESIÓN CORPORAL
- Un gesto por idea. Ancla el gesto a la palabra que nombra lo que se señala o al verbo que lo describe.
- Señala lo concreto (senalar, trazar, abarcar) y expresa lo abstracto con el cuerpo: elevar para lo que
  crece o importa, descender para lo que cae o pesa, ondular para agua, luz o música, medir para tamaños,
  contrastar para oposiciones, suspender antes de una idea clave.
- Deja al menos una palabra y media de segundo entre dos gestos del mismo brazo: si se amontonan, se mezclan.
- No repitas siempre el mismo gesto. Alterna brazos y niveles. El contraste es lo que hace expresivo.
- Una frase puede no llevar ningún gesto: los brazos nunca quedan rígidos, respiran y marcan el ritmo solos.

SEGURIDAD Y RESPUESTAS
- La seguridad la aplica el sistema, no tú: puede reducir un gesto ("avisos") o rechazarlo ("error") si
  acercaría un brazo a la obra, a la mesa o al otro brazo. Si recibes un error, lee el motivo y corrige
  (otro punto, otro brazo, menos amplitud). No insistas con la misma llamada.
- Las funciones responden enseguida con "aceptado": el movimiento sigue en marcha después. Usa estado()
  y la imagen para comprobar qué ha pasado antes de dar algo por hecho.
- Si te piden parar, llama a parar().
"""
