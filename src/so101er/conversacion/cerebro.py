"""Cerebro de la conversación: un chatbot sencillo que ve la foto de la obra y decide qué decir.

Es quien describe la obra, vuelve a describir lo que le pidan y contesta preguntas. Escribe en
streaming (el texto va a la voz según sale) y no sabe nada de brazos: de eso se ocupa ER 2.
Adaptado del prototipo robot-guia-bot (Claude sin razonamiento extendido, esfuerzo bajo).
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any, Callable

MODELOS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}

SISTEMA = {
    "es": """Eres un guía de museo. Hablas con visitantes que están delante de la obra de la imagen. \
Todo lo que escribes se dice en voz alta, y a tu lado unos brazos robóticos gesticulan y señalan lo que nombras.

Cómo hablas:
- Si te piden describir o explicar la obra: una descripción detallada en 5 a 7 frases cortas. Primero lo \
general y luego los detalles, uno por frase.
- Si te hacen una pregunta concreta o te piden volver a un detalle: 1 o 2 frases, 35 palabras como mucho.
- En cada frase nombra con claridad qué se ve y dónde está (arriba, a la izquierda, en el centro, al fondo).
- Frases completas y naturales, que suenen bien dichas en voz alta. Sin listas, sin markdown, sin emojis ni \
símbolos que no se puedan pronunciar.
- Habla solo de lo que se ve en la imagen. Si no lo sabes o no se aprecia, dilo en pocas palabras.
- No hables de los brazos ni de ti como sistema. Responde siempre en español.""",
    "en": """You are a museum guide. You talk with visitors standing in front of the artwork in the image. \
Everything you write is spoken aloud, and beside you two robotic arms gesture and point at what you name.

How you speak:
- If asked to describe or explain the artwork: a detailed description in 5 to 7 short sentences. The overall \
impression first, then the details, one per sentence.
- If asked a specific question or to go back to a detail: 1 or 2 sentences, 35 words at most.
- In every sentence name clearly what is seen and where it is (at the top, on the left, in the centre, in the \
background).
- Complete, natural sentences that sound good spoken aloud. No lists, no markdown, no emojis and no symbols \
that can't be pronounced.
- Talk only about what can be seen in the image. If you don't know or it can't be made out, say so briefly.
- Don't talk about the arms or about yourself as a system. Always reply in English.""",
}
PRESENTACION = {"es": "Esta es la obra que tienes delante.", "en": "This is the artwork in front of you."}
ENTENDIDO = {"es": "Entendido. Estoy delante de la obra con los visitantes.",
             "en": "Understood. I am in front of the artwork with the visitors."}


class Cerebro:
    def __init__(self, clave: str, imagen_jpeg: bytes, idioma: str = "es", modelo: str = "haiku",
                 max_tokens: int = 700) -> None:
        import anthropic
        self._anthropic = anthropic
        self.cliente = anthropic.Anthropic(api_key=clave)
        self.modelo = MODELOS.get(modelo, modelo)
        self.idioma = idioma
        self.max_tokens = max_tokens
        self._imagen = base64.b64encode(imagen_jpeg).decode("ascii")
        self.mensajes: list[dict[str, Any]] = []     # solo los turnos; la imagen va en el prefijo fijo
        self.t_primer_texto: float | None = None

    def _prefijo(self) -> list[dict[str, Any]]:
        """Principio fijo de toda petición: la imagen de la obra. Idéntico siempre, para que se
        sirva de la caché y el chatbot empiece a escribir antes."""
        return [
            {"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self._imagen}},
                {"type": "text", "text": PRESENTACION[self.idioma], "cache_control": {"type": "ephemeral"}}]},
            {"role": "assistant", "content": ENTENDIDO[self.idioma]},
        ]

    def _opciones(self) -> dict:
        if self.modelo == MODELOS["sonnet"]:
            return {"thinking": {"type": "between_tools"}, "output_config": {"effort": "low"}}
        return {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}

    def calentar(self) -> None:
        """Abre la conexión mientras el visitante aún habla (ahorra el saludo TLS en el primer texto)."""
        try:
            self.cliente.models.retrieve(self.modelo)
        except Exception:
            pass

    def precargar(self) -> None:
        """Al arrancar: una petición mínima que deja la imagen en la caché del servicio."""
        try:
            self.cliente.beta.messages.create(
                model=self.modelo, max_tokens=1, system=SISTEMA[self.idioma],
                messages=self._prefijo() + [{"role": "user", "content": "."}], **self._opciones())
        except Exception:
            pass

    def cambiar_idioma(self, idioma: str) -> None:
        self.idioma = idioma

    def responder(self, texto: str, al_texto: Callable[[str], None], cortar: threading.Event) -> str:
        """Un turno. `al_texto` recibe cada trozo según llega; `cortar` detiene la respuesta."""
        self.mensajes.append({"role": "user", "content": texto})
        dicho = ""
        self.t_primer_texto = None
        try:
            with self.cliente.beta.messages.stream(
                    model=self.modelo, max_tokens=self.max_tokens, system=SISTEMA[self.idioma],
                    messages=self._prefijo() + self.mensajes, **self._opciones()) as stream:
                for evento in stream:
                    if cortar.is_set():
                        break
                    if evento.type == "text":
                        if self.t_primer_texto is None:
                            self.t_primer_texto = time.perf_counter()
                        dicho += evento.text
                        al_texto(evento.text)
        except self._anthropic.APIError as e:
            if not dicho:
                self.mensajes.pop()
                raise RuntimeError(f"el chatbot no responde ({type(e).__name__}: {e})") from None
        # Al historial va solo lo que llegó a escribirse (si se cortó, lo dicho hasta ahí).
        self.mensajes.append({"role": "assistant", "content": dicho or "…"})
        del self.mensajes[:-12]     # historial corto: los últimos turnos
        return dicho
