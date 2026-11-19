# Chatbot con USB real y cuadro virtual

«Preparar y arrancar» reutiliza la alineación ya guardada del USB elegido y arma
las comprobaciones automáticas. Pulsarlo confirma que el otro brazo está apartado.
Si aún no hay alineación válida, abre el asistente de primera puesta en marcha
sin activar motores y deja el arranque desarmado. Tras esa comprobación inicial
no hay que volver a ajustar el modelo cada sesión. Si cambian rangos, offsets,
adaptador o montaje, hace falta revisar la referencia: no se vuelve a poner a
cero desde una foto ni se sobrescribe automáticamente la referencia existente.

Abrir `CHATBOT_REAL.cmd` o `ABRIR_CHATBOT_REAL.cmd` en la carpeta superior. El
preparador lee los USB y repite las comprobaciones cada tres segundos. Sus avisos
indican COM, articulación/ID y acción: conectar, liberar un puerto ocupado, sujetar
y soltar un brazo con par, dejar enfriar un motor o guardar su alineación.

No se activan motores al abrir. Elegir COM7 o COM8, apartar el otro brazo de todo
el recorrido y marcar «Preparado». Cuando las comprobaciones pasan se activa SOLO
ese USB y se abre el chatbot. Si falta alineación, «Abrir alineación y pruebas»
permite completarla; guardar y cerrar Pruebas para liberar el puerto. El preparador
retoma automáticamente. No inventa archivos verificados ni modifica EEPROM.

La pequeña entrada de codo de COM8 puede suceder al activar, a aproximadamente
1°/s y con corrección total máxima de 3°. Se muestra antes de armar y conserva
los límites. El chatbot espera a que termine. Cancelar impide abrir después el
chatbot, incluso si esa entrada estaba en curso. Sujetar antes de Soltar.

## Referencia de imagen y control

Se usa el dibujo del paisaje, no una cámara real ni una fotografía del entorno.
El plano virtual continúa en la configuración nominal existente, a y=520 mm
delante de la base virtual; no es una distancia medida. Los puntos de la IA son
consignas sobre ese dibujo. No permiten detectar obstáculos, localizar un cuadro
físico ni asegurar que se apunta a un píxel físico con precisión.

La calibración articular viene del archivo de alineación del USB elegido. Toda
lectura para el controlador procede de encoders/telemetría reales. El planificador
usa esos sensores, consignas, calibración nominal y memoria. El MuJoCo de la vista
3D solo proyecta la pose estimada desde encoders; no ejecuta física para decidir
acciones y no proporciona observaciones al controlador ni imágenes a la IA.
Cerrar esa vista por el usuario detiene el movimiento. Un fallo de render no
cambia decisiones físicas; el controlador mantiene su supervisión sensorial.

Se fuerza un único brazo lógico activo y se evita el abanico bilateral. Cada
plan completo y su acompañamiento se convierte a los rangos físicos y valida
antes de reproducirlo. Si no cabe, se informa; no se amplían rangos. La pinza
emplea sus extremos útiles con margen. El retorno usa la referencia operativa
guardada, limitada al interior de los rangos. Las bases y obstáculos reales no
están medidos: mover uno solo no garantiza que no alcance al otro brazo aparcado.

## Voz, micrófono y parada

El chatbot conserva Gemini, ElevenLabs, marcas de palabras y el reloj DAC del
audio. Texto, micro, clic en un punto y región funcionan como en simulación.
Las claves se leen del entorno/.env ya configurado, nunca se copian al proyecto.
El micrófono sigue siendo por botón; no escucha permanentemente.

El perfil inicial real limita el plan a 6°/s (y 6 puntos porcentuales/s para pinza),
por debajo del límite nativo de 8°/s. Es un estreno lento: los gestos y la narración
pueden durar más que en simulación. No se ha medido todavía la naturalidad ni la
sincronía física. La adaptación temporal de voz tiene límites y un turno que no
cabe falla antes de iniciar el audio.

Interrumpir/Escape detiene el turno manteniendo par. Ante seguimiento, carga o
temperatura anómalos se indica el motor y la corrección necesaria. Antes de
cambiar de USB o cerrar, sujetar y pulsar «Soltar brazo». No se corta el par de
improviso dejando caer una postura elevada. No es un sistema de emergencia
certificado; el operador debe permanecer junto al montaje.

El arranque `--real` histórico sin preparador queda bloqueado. Las pruebas de
software usan buses de ensayo y verifican que faltar alineación impide abrir
el controlador, los avisos por motor, un único brazo, límites, conversiones y
ausencia de dependencia de verdad interna del visor. La prueba conjunta física
de voz/gestos queda pendiente de las alineaciones del operador.
