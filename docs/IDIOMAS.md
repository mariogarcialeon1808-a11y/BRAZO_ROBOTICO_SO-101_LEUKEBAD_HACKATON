# Idiomas de la conversación

El chatbot conversa en **español, inglés, alemán, francés y chino**. Responde en el idioma de la
última petición y se queda en él hasta que llega una petición en otro. Al abrir una sesión
el idioma es el español.

## Cómo se decide

Hay un único idioma por turno y se decide **en este equipo**, antes de llamar a ningún
servicio:

| Petición | Quién decide | Regla |
|---|---|---|
| Texto escrito | `idiomas.detectar` (propio, sin dependencias) | Si el texto está claro, la conversación pasa a ese idioma. Si no (una palabra que vale en dos idiomas como «no» o «photo», un «ok», un número, un idioma que no es de los nuestros), **no cambia**. |
| Voz | El modelo local de reconocimiento (`datos/modelos/whisper_base`) | Estima el idioma de lo hablado. Solo se comparan los nuestros, y solo se cambia si otro gana con claridad; una frase corta o con ruido no cambia el idioma. Después transcribe forzando ese idioma, así que el texto y el idioma salen de la misma decisión. |
| Clic o región en el cuadro, Demo humana | Nadie | Se usa el idioma en que está la conversación. Las frases fijas y la demo existen en los cinco. |
| Selector **Idioma** de la pestaña 4 | El operador | Muestra el idioma actual y permite fijarlo a mano. No lo bloquea: la siguiente petición en otro idioma lo vuelve a cambiar. |

Cada cambio se anota en la ventana: «Idioma de la conversación: inglés.»

## Por qué no se traduce

No hay traducción, ni local ni externa. La IA escribe **directamente** en el idioma del turno.
Traducir después una respuesta en español tendría tres problemas: cambiaría el orden de las
palabras, y con él la palabra a la que está anclado cada gesto; añadiría segundos de espera y
más de un gigabyte de modelos; y daría peor texto, sobre todo en chino.

Lo que evita las mezclas no es traducir, sino que **todas las piezas reciban el mismo idioma
del mismo sitio**:

1. `SesionIntegrada.enviar` decide el idioma y se lo entrega al turno. El turno lo lleva
   consigo hasta el final, aunque la conversación cambie mientras tanto.
2. Las instrucciones a ER 2 piden la respuesta en ese idioma. En español son, letra por
   letra, las de antes.
3. **La respuesta se comprueba en local** antes de sintetizar o mover nada
   (`idiomas.en_idioma`, frase por frase). Si alguna frase está en otro idioma, se le pide a
   la IA una vez que la reescriba; si insiste, el turno falla con un aviso y **no se dice
   nada**. Nunca se pronuncia una mezcla.
4. La voz se pide a ElevenLabs con ese mismo idioma (`language_code`).
5. Las anclas de los gestos se cuentan con la regla de ese idioma.

## Una voz por idioma

Cada idioma puede tener su propia voz de ElevenLabs, nativa de ese idioma. Para cada turno el
programa busca el Voice ID en este orden y usa el primero que encuentre:

1. La tabla `[conversacion.voces]` de `config/so101er.toml`:

   ```toml
   [conversacion.voces]
   es = "FFHOCNsj5TuX6tRgEswC"
   de = "1J0wWp4zPQIvsK7Xwh34"
   ```

2. La variable `ELEVENLABS_VOICE_ID_<CÓDIGO>` (`_ES`, `_EN`, `_DE`, `_FR`, `_ZH`), del entorno de
   Windows o del archivo `.env`:

   ```
   ELEVENLABS_VOICE_ID_FR=bts16wA7hWMfnlEIHuRo
   ```

3. La voz general, `ELEVENLABS_VOICE_ID`.

Hoy la tabla trae una voz para cada uno de los cinco idiomas. Para volver a una sola voz para
todo, borra sus líneas. En el `.env` cada línea es `NOMBRE=valor`, con `=`; una línea escrita
con `:` se ignora sin avisar.

- Si la cuenta de ElevenLabs no puede usar la voz de un idioma, ese turno se dice con la voz
  general, la ventana lo avisa una vez con el motivo y ya no se vuelve a intentar hasta reiniciar.
- Si no hay voz para un idioma en ninguno de los tres sitios, el turno falla con «falta el
  Voice ID de ElevenLabs para este idioma» y no se dice nada.
- Los Voice ID no son secretos (identifican una voz, no una cuenta); la clave sí, y sigue solo
  en el `.env`.

Las cinco voces de la tabla son de la biblioteca de ElevenLabs. El 15-11-2026, con la cuenta
actual, ninguna figuraba entre las voces de la cuenta, pero una frase de prueba con la de español
se sintetizó bien. Las otras cuatro no se pudieron probar por falta de crédito.

## El chino

En chino no hay espacios entre palabras, así que el ancla de cada gesto cuenta **caracteres**
en vez de palabras, y a la IA se le piden frases de 35–55 caracteres en vez de 20–30 palabras.
Contar caracteres no es el fuerte de la IA: un ancla que se pase del final se lleva al último
carácter en vez de descartar el gesto.

## Comprobado (15-11-2026, sin brazos)

Con el cuadro de ejemplo, ER 2, ElevenLabs y el reconocimiento local reales:

- ER 2 respondió en el idioma pedido a la primera en las siete preguntas (es, en, fr, zh,
  vuelta a en, «ok» manteniendo el inglés y vuelta a es), en 1,6–2,5 s. Ninguna frase fuera
  de idioma.
- En alemán, cinco preguntas más: respondió en alemán, lo mantuvo tras un «ok», volvió a
  español con una pregunta en español y de nuevo a alemán. Ninguna frase fuera de idioma. El
  alemán hablado y su voz no se han podido probar: no quedaba crédito en ElevenLabs y Windows
  no tiene voz en alemán.
- ElevenLabs leyó cada respuesta en su idioma, con marcas por carácter también en chino.
- El reconocimiento local identificó bien el idioma de las cuatro voces, tanto si la
  conversación venía en español como en inglés.

## Límites

- **El reconocimiento de voz es el modelo «base».** Identifica bien el idioma, pero la
  transcripción en chino tiene errores de caracteres (en la prueba, 7 de 27). A la IA le suele
  bastar para entender la pregunta. Un modelo mayor lo mejoraría a cambio de más espera.
- **La voz local de Windows** solo sirve para los idiomas con voz instalada (en este equipo,
  español e inglés). Con ElevenLabs van los cinco. Si falta la voz, el turno lo dice y no habla.
- **Si ElevenLabs se queda sin crédito** (responde 401 con «quota_exceeded»), el robot no se
  queda mudo: ese turno y los siguientes se dicen con la voz de Windows, y la ventana avisa una
  vez con el motivo. Se vuelve a intentar con ElevenLabs al reiniciar el programa. En alemán,
  francés y chino, sin voz de Windows instalada, el turno falla diciendo por qué. Cualquier otro rechazo
  (clave no válida, por ejemplo) se muestra con su motivo y no se tapa con la voz de Windows.
- **Los avisos de la ventana siguen en español**: son para el operador, no para el visitante.
- El detector de texto conoce unas doscientas palabras frecuentes por idioma. Una pregunta de
  una sola palabra rara puede no reconocerse; en ese caso no cambia el idioma, que es lo seguro.
- Sin probar con los brazos reales. El idioma no interviene en ningún movimiento: solo cambia
  el texto, la voz y la palabra a la que se ancla cada gesto.

Código: `src/so101er/idiomas.py` (detección, unidades, frases fijas e instrucciones),
`aplicacion_servicios.py` (`Vision.responder`, `Voz.sintetizar`, `Microfono.transcribir`,
`tiempo_ancla`) y `SesionIntegrada.enviar` en `aplicacion.py`. Pruebas: `tests/test_idiomas.py`.
