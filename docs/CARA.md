# Cara del robot

Una página a pantalla completa con la cara animada, los subtítulos sincronizados con la voz y una
tarjeta con la imagen que se explica (con la zona de cada frase resaltada). La sirve el propio
programa en `http://127.0.0.1:8765/` y se abre en su propia ventana del navegador, aparte de la
Pantalla 3D. Es la cara del conjunto: mira hacia el brazo que gesticula y cambia de ánimo con lo
que se dice.

La cara, la página y el servidor son de Javier García Pavón (rama `cara-display` de
`javiergarcia132008-glitch/so101-cuadro-gestos-publico`). Aquí se ha adaptado al turno frase a
frase y se le ha añadido la mirada y el ánimo según los brazos. Su guía local con Ollama no se ha
integrado.

## Uso

1. Arrancar como siempre (`ABRIR_SO101.cmd` o `INICIAR_SIMULACION.cmd`). En la ventana aparece
   «Cara del robot en http://127.0.0.1:8765/».
2. Abrirla de una de estas dos formas:
   - Botón **Cara** de la pestaña 4: una ventana normal del navegador, para moverla a otra pantalla.
   - Doble clic en `ABRIR_CARA.cmd`: pantalla completa (modo kiosko) en Chrome o, si no está, en
     Edge. Espera a que el programa la sirva. Alt+F4 la cierra.

   Si se cierra y se vuelve a abrir una sesión, la página se reconecta sola.

Depuración: `http://127.0.0.1:8765/?debug=1` muestra posición de la voz, palabra, estado y desfase.
`?desfase=80` prueba un desfase sin tocar la configuración.

## Apagar y ajustar

`[cara]` en `config/so101er.toml`: `activa = false` (o la variable `SO101_CARA=0`) deja el programa
exactamente como antes. `puerto`, `desfase_ms` (positivo: subtítulos y boca más tarde),
`imagen = false` (sin tarjeta) y `espejo = true` (la cara mira al lado contrario: para cuando el
público la ve de frente y los brazos le quedan cruzados). Si el puerto está ocupado o algo falla, se avisa una vez en la
ventana y el turno sigue igual.

## Qué se ve

- Ojos: IDLE, LISTENING (micro grabando), THINKING (Gemini o el guía local), TALKING (boca con el
  volumen real de la voz) y ERROR (unos segundos).
- Subtítulos: dos líneas como máximo, palabra que suena en amarillo, las siguientes atenuadas. Nunca
  van por delante de la voz. Al acabar se quedan 2 s y se desvanecen; si se interrumpe, queda lo dicho.
- Tarjeta de imagen: entra al empezar una frase con `punto` o `region`; el resaltado cambia al
  sonar su palabra ancla. Si se cambia la imagen en la galería, la tarjeta cambia con ella.
- Mirada: mientras un brazo hace un gesto, los ojos se van hacia ese brazo (al frente si son los
  dos) y suben o bajan con los gestos que suben o bajan.
- Ánimo: según el movimiento, la cara se pone alegre (saludar, ofrecer, afirmar), seria (alto,
  negar, obligatorio), atenta (señalar, pedir atención), dudosa (más o menos, esperar) o
  pensativa (reloj, buscar, comparar). La tabla está en `src/so101er/cara/expresiones.py`.

## Con el turno frase a frase

El programa empieza a hablar con la primera frase mientras prepara las demás, así que la cara
recibe las frases una a una:

- Cada frase sale en pantalla cuando el altavoz llega a su comienzo, no cuando se prepara.
- La primera frase empieza a sonar antes de que haya llegado toda su voz. Sale con lo que hay y,
  en cuanto llega el resto, se corrige en marcha con los tiempos definitivos de cada palabra.
- Los gestos van aparte: el programa avisa de cuándo empieza y acaba cada uno y la cara mira
  mientras dura.

## Protocolo (`GET /eventos`, Server-Sent Events)

| Evento | Datos |
|---|---|
| `estado` | `{estado, texto?}` |
| `usuario` | `{texto}`: la pregunta del visitante |
| `turno` | `{id, rev, texto, palabras:[{t, ini, fin}], duracion, boca:[0..1], paso:0.02, bloques:[{tipo, punto\|region, ancla_s, p0, p1}], obra_v, desfase_ms}`. Uno por frase; el mismo `id` con `rev` mayor trae sus tiempos definitivos |
| `reloj` | `{id, pos}` cada 100 ms: segundos desde el comienzo de esa frase |
| `fin` | `{id, interrumpido}` |
| `mirada` | `{lado, vertical, animo}`: -1, 0 o 1 en cada eje y el ánimo. Al empezar y al acabar cada gesto |

Tiempos en segundos de la voz final (ya estirada). Al conectarse llega el último `estado` y, si hay
turno en curso, su `turno`. El navegador interpola el reloj en cada fotograma; no usa temporizadores.
Otras rutas: `/`, `/js/...`, `/obra.jpg` (lado largo ≤ 1600 px) y `/salud`.

## Probar sin hardware

`python -m so101er.cara --demo` abre la página con turnos falsos en bucle (sin audio, claves ni
brazos; en Windows, Mac o Linux). En Windows sin claves: `python -m so101er.cli iniciar --raiz .
--voz local --demo` y `ABRIR_CARA.cmd`.

## Archivos

Nuevo: `src/so101er/cara/` (`tiempos.py` sin E/S, `servidor.py` con `http.server`, `web/`), `ABRIR_CARA.cmd`,
`tests/test_cara.py`. `web/js/eyes.js` y el maquetado de subtítulos vienen del display anterior.
Tocados: `aplicacion.py` (crear la cara en la sesión; `pensando`, `hablar`, `callar`, `error` en
`_turno`; `callar` en `interrumpir`; `cerrar`; `escuchando` en el micro), `pyproject.toml`
(estáticos), `[cara]` en las dos configuraciones y `.cara-profile/` en `.gitignore`.

La cara es solo salida de conversación: encola y vuelve. Nada del control la lee ni espera por ella
(AGENTS.md); `player.posicion` se lee, no se modifica. Lo que recibe de los brazos son consignas
ya decididas (qué gesto y cuándo), no medidas de sensores.
