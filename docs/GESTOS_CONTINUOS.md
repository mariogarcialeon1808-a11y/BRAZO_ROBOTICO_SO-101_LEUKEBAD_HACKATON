# Habla con acompañamiento continuo

La interfaz integrada conserva los gestos amplios que describen el cuadro. Entre
ellos añade acentos de acompañamiento que alternan los brazos y abren las pinzas.
Sus ápices buscan energía en el audio ya sintetizado; no pretenden señalar nuevos
objetos. Cada acento vuelve a reposo antes del siguiente movimiento.

Un hueco corto se absorbe alargando suavemente la recogida anterior. Si sobra tiempo
antes del primer gesto, se reparte en su preparación. Los señalamientos conservan
su rayo, la pinza cerrada y el momento de énfasis. No se superponen movimientos ni
se añaden gestos mientras se escucha al usuario. El audio de un turno sigue siendo
continuo y está preparado antes de iniciar la actuación.

## Sincronía

El controlador sigue un reloj derivado de `outputBufferDacTime` de PortAudio, que
indica cuándo saldrá el primer sample de cada buffer por el dispositivo. Se incluye
el silencio previo necesario para preparar los brazos. La latencia no se suma a
las anclas después de iniciar la voz.

`[voz].adelanto_expresivo_s = 0.22` en `config/so101er.toml` adelanta el ápice planificado
220 ms respecto a la palabra. Es un ajuste inicial de expresión/seguimiento, no
una medida acústica del altavoz ni una garantía de percepción de sincronía.
No se corrige el controlador usando estado privilegiado de MuJoCo.

## Comprobación en este portátil

En una narración de demostración de 35,43 s con voz ElevenLabs y MuJoCo:

- Se añadieron cinco acentos entre los cuatro gestos principales.
- Los 14,35 s de huecos planificados quedaron cubiertos con acompañamiento o
  recogida continua. Los ápices y las vueltas a reposo se conservaron.
- El dispositivo no notificó subalimentaciones de audio.
- No se omitieron planes ni se detectaron errores del controlador.
- El error final de seguimiento fue inferior a 0,18 grados/puntos porcentuales,
  medido mediante los encoders declarados.

Son resultados de esa ejecución, no un certificado de sincronía audiovisual ni
de movimiento permanente: se mantienen las detenciones expresivas del señalamiento
y la velocidad llega suavemente a cero al pasar por reposo. El diagnóstico está
en `salidas/continuo/verificacion.json`.

Las pruebas verifican continuidad, límites, regreso a reposo, conservación de
anclas, transformación del reloj con distintas latencias y seguimiento del reloj
de audio. La prueba existente de invariancia sensorial sigue formando parte de la
suite. Los acentos dependen de constantes nominales, consignas y audio generado;
no consultan posiciones, fuerzas ni contactos internos del simulador.

Suite completa: 128 pruebas pasadas en este portátil.
