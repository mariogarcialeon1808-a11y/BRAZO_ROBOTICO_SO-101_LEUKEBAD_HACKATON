# Imágenes de la obra y vídeo en directo

En la pestaña **4 · Chatbot**, debajo del cuadro, el botón **Imágenes…** abre una ventana
emergente. No es una pestaña nueva ni bloquea la principal: **PARAR**, **Interrumpir** y
**Soltar** siguen a mano mientras está abierta.

## Qué se puede hacer

- **◀ Anterior / Siguiente ▶** (o las flechas del teclado): recorre el cuadro de ejemplo y
  las imágenes guardadas en la carpeta `obra/`.
- **Explorar…**: añade fotos de cualquier otra carpeta (varias a la vez). Se copian a
  `obra/`; los originales no se tocan. Una foto que ya estaba no se duplica y dos fotos
  distintas con el mismo nombre se guardan como `nombre_2`.
- **Usar esta imagen** (o Intro): la carga en la sesión. Se ve en el cuadro de la pestaña 4
  y en la vista 3D, y es la que recibe ER 2 en la siguiente pregunta.
- **Ver entera / Recortar para llenar**: cambia el encuadre de esa imagen. Si está
  recortada, se puede arrastrar para elegir qué parte se ve. El encuadre se recuerda.
- **Quitar**: saca la imagen de la galería. No se borra: pasa a `obra/_quitadas/`.
- **Vídeo en directo**: muestra la cámara elegida (Cámara 1 a 4) o un archivo de vídeo.
  **Congelar** detiene la imagen; **Tomar instantánea y usarla** (o Espacio) guarda el
  fotograma en `obra/` como `instantanea_AAAAMMDD_HHMMSS.jpg` y lo carga. La cámara solo se
  abre al entrar en el vídeo y se suelta al salir o cerrar la ventana.
- **Usar en directo**: deja la cámara (o el vídeo) como imagen del cuadro; ver más abajo.

La imagen elegida se recuerda para la próxima sesión (`obra/_galeria.json`, junto con los
encuadres, la última carpeta explorada y la cámara usada). Sin elección guardada se sigue
usando la foto más reciente de `obra/`, como antes; con la carpeta vacía, el cuadro de ejemplo.

## Cámara en directo como imagen del cuadro

Con **Usar en directo** el cuadro deja de ser una foto fija y pasa a ser lo que ve la cámara:

- En reposo, el cuadro de la pestaña 4, la vista 3D pequeña y la pantalla 3D muestran el
  vídeo según llega. El rótulo dice «Imagen: Cámara 1 en directo».
- **Cada pregunta, clic o región usa la imagen de ese instante.** Es la que recibe ER 2 y
  sobre la que se señala. Mientras dura la explicación el cuadro la muestra **detenida**,
  para que lo que señalan los brazos coincida con lo que se ve; al terminar vuelve el directo.
- Cargar una foto con **Usar esta imagen** termina el directo y suelta la cámara. Volver a
  **Vídeo en directo** en la ventana de imágenes lo recupera sin reabrir la cámara; si entonces
  no se pulsa de nuevo **Usar en directo**, queda cargada la última imagen.
- Si la cámara deja de dar imagen, se avisa, se deja el directo y queda la última imagen.
- El directo no se recuerda entre sesiones: la cámara nunca se enciende sola al arrancar.

Cada fotograma se adapta al cuadro con la misma regla que las fotos.

## Pantalla 3D y cara

El botón **Pantalla 3D** (pestaña 4, a la derecha del rótulo de la imagen) abre una ventana
aparte del programa, pensada para enseñarla: la escena de MuJoCo con los brazos, el cuadro en
su sitio con la imagen cargada o el vídeo en directo, y una **cara** en la esquina superior
derecha. Funciona igual en simulación y con los brazos reales.

- La cara son dos ojos y una boca. **Solo se mueve mientras habla**: la boca sigue el volumen
  de la voz que está sonando, y los ojos parpadean y miran un poco a los lados. En silencio
  está quieta, con una sonrisa leve.
- Los brazos se dibujan según sus encoders. Si un brazo no se puede leer (control detenido, sin
  par), se queda en su última postura. Con la gráfica integrada de este equipo salen unas 12
  imágenes por segundo: los brazos tienen 650 000 triángulos y las sombras obligan a dibujarlos
  dos veces.
- **La escena se compila antes de activar los motores**, al pulsar «Preparar y arrancar», y la
  ventana solo la dibuja. Compilarla con los brazos ya con par dejaba sin atender su bucle USB
  unas décimas de segundo (los avisos «pico de latencia de 250 ms» del 15-11-2026 al abrir la
  pantalla). Ahora abrirla lo retrasa 90 ms como mucho, por debajo del umbral de aviso (200 ms).
- La ventana se puede agrandar o poner a pantalla completa (la imagen se escala). Arrastrar con
  el botón izquierdo gira la vista y la rueda acerca o aleja.
- Es **solo una vista**: nada la lee para decidir un movimiento, y cerrarla, con su X o con
  **Cerrar pantalla 3D**, no detiene ni suelta nada. Se cierra sola al cerrar la sesión.

La escena se dibuja con un renderizador propio de MuJoCo y se muestra en una ventana de OpenCV,
no en el visor interactivo de MuJoCo. Es deliberado: ese visor tumba el proceso entero si se
cierra su ventana mientras otro hilo le está enviando una imagen (comprobado el 15-11-2026), y
con los brazos con par un cierre así no es aceptable. El visor de MuJoCo de la simulación sigue
como estaba: muestra la foto cargada y, con directo, la última imagen analizada.

## Cómo se adapta cada imagen

El cuadro es un rectángulo fijo delante de los brazos (`[cuadro]` en `config/so101er.toml`,
700 × 440 mm). Toda imagen se lleva a esa proporción, a 1280 px de ancho:

| La imagen… | Se hace | Ejemplos |
|---|---|---|
| ya tiene la proporción | nada | el cuadro de ejemplo |
| pierde hasta un 25 % al recortarla | **se recorta** por el centro | fotos 4:3, 3:2, 16:9 apaisadas |
| perdería más | **se ajusta entera**, con bandas grises | fotos verticales, cuadradas, panorámicas |

Ese reparto es solo el punto de partida: el botón de encuadre lo cambia imagen por imagen.
A ER 2 se le envía esa misma imagen a 768 px de ancho, y las instrucciones le dicen que las
bandas grises son relleno. Lo que se ve en la ventana es exactamente lo que recibe.

También se resuelve al leer: la orientación que guarda la cámara del móvil (EXIF), la
transparencia (sobre blanco), las imágenes en gris y las rutas con acentos o eñes, que
`cv2.imread` no abre en Windows. Sirven PNG, JPG, BMP y WEBP; otros formatos legibles (TIFF)
se guardan como PNG. Lo que no se puede leer (HEIC, archivos dañados) se explica en la ventana
y se salta.

## Qué cambia y qué no en la sesión

Cambiar de imagen es una consigna del operador. **No mueve los brazos ni cambia la
geometría**: como la proporción es siempre la del rectángulo configurado, un punto [y, x]
cae en el mismo lugar del plano con cualquier imagen. Lo que sí hace:

- corta la explicación en curso (hablaba de la imagen anterior), igual que **Interrumpir**;
- vacía el contexto de conversación de la IA;
- actualiza el dibujo de las vistas 3D. Son solo dibujo: si alguna no se pudiera
  actualizar, se avisa y la sesión sigue.

La **Demo humana** describe siempre el cuadro de ejemplo; con otra imagen cargada lo avisa.

Antes (`obra.preparar`) era el rectángulo el que se encogía hasta la proporción de la foto.
La aplicación integrada usa ahora `obra.preparar_adaptada`; la función anterior se conserva
para la demostración por consola.

## Límites que conviene conocer

- El cuadro sigue siendo **virtual**. Los brazos señalan dónde estaría cada punto de la
  imagen sobre ese rectángulo de 700 × 440 mm. Una instantánea de la cámara no convierte a
  la cámara en un sensor del entorno: si se fotografía un objeto real, los brazos no apuntan
  al objeto, sino a su posición dentro de la imagen proyectada en el plano. Para que coincidan,
  lo fotografiado tiene que estar en ese plano y ocupar el encuadre.
- La vista previa del vídeo va a 15 imágenes por segundo como mucho, en un hilo aparte (la cámara de este
  equipo da 1280 × 720 a 10 por segundo). No se ha
  medido con los brazos reales en movimiento; si alguna vez coincidiera con un aviso de
  ciclo lento, basta con salir del vídeo.
- Las cámaras no se enumeran por nombre: se ofrecen «Cámara 1» a «Cámara 4» y, si la
  elegida no existe, se dice.

- La pantalla 3D y el directo tampoco se han medido con los brazos reales en movimiento. Sí
  se ha medido sin brazos que dibujar la escena en su hilo no retrasa un bucle de 50 Hz como
  el de control (peor ciclo, 33 ms con y sin pantalla). Aun así es carga añadida: si
  coincidiera con avisos de ciclo lento, ciérrala y compáralo.

Código: `src/so101er/galeria.py` (carpeta, adaptación y vídeo, sin interfaz),
`src/so101er/interfaz/ventana_imagenes.py` (la ventana de imágenes), `src/so101er/interfaz/cara.py`
(la cara), `src/so101er/hardware/pantalla.py` (la pantalla 3D) y, en `src/so101er/aplicacion.py`,
`SesionIntegrada.cambiar_imagen`, `usar_directo` y `abrir_pantalla`.
Pruebas: `tests/test_galeria.py` y `tests/test_pantalla.py`.

## Marcar una zona y preguntar por ella

Sobre la imagen de la pestaña 4 se puede marcar un recuadro («Marcar región») o un punto
(«Marcar punto»). Marcar no dice nada por sí solo: deja la zona seleccionada, en naranja, para
la pregunta siguiente.

- **Con texto o por voz:** «explícame lo que ves aquí», «¿qué es esto?». La IA responde solo
  sobre lo marcado y, si señala, lo hace dentro de esa zona.
- **Sin escribir nada:** «Preguntar a la IA» pide que explique la zona con detalle, en el idioma
  de la conversación.
- **Quitar selección** la borra. También se borra al usarla en una pregunta y al cambiar de imagen.

La IA recibe la imagen con la marca dibujada y la petición con sus coordenadas. Es una consigna
del operador: nada del control la lee.

Antes, marcar una zona hacía decir una frase fija («Observa esta región del cuadro») sin pasar
por la IA, y con frases tan cortas el gesto ni siquiera llegaba a hacerse.

## Dónde está la cámara

La cámara del vídeo en directo está centrada entre los dos brazos (a 25 cm de cada uno) y a 32 cm
de altura. Está apuntado en `[camara] posicion_mm` de la configuración. Todavía no se usa para
calcular nada: para que los brazos señalen en el espacio real lo que se ve en el vídeo hace falta
además el ángulo de visión de la cámara.
