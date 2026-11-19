# Una ventana para preparar y utilizar los SO-101

Abre **ABRIR_SO101.cmd**. Los accesos anteriores de pruebas y chatbot también
abren esta misma ventana. No abras dos copias al mismo tiempo.

Para usar los dos a la vez: [modo Ambos, montaje y bailes conjuntos](DOS_BRAZOS_REALES.md).
Los pasos 1 y 2 siguen haciéndose por separado para cada USB.

La primera vez se hacen los pasos 1 y 2 para los dos brazos. Después se reutilizan
los archivos guardados: basta ir al paso 3 y preparar el brazo elegido.

## 1 · Rangos: cuánto puede girar cada motor

Los motores deben estar sin par, es decir, sueltos para moverlos a mano.
Sujeta el brazo, trabaja despacio y deja el otro fuera de su recorrido.

1. Elige COM7 y el primer motor.
2. Mueve solo esa articulación a mano por su recorrido, sin forzar los topes.
   La barra verde muestra el tramo registrado y el punto naranja la posición actual.
3. Repite con los seis motores de COM7 y después los seis de COM8.
4. Pulsa **Guardar rangos**. El contador debe indicar 12 de 12.

Un guardado parcial conserva el trabajo en un borrador y no sustituye los rangos
completos anteriores. El contador solo indica recorrido registrado; no demuestra
que hayas alcanzado los topes correctos. Esta pantalla nunca mueve los motores.
Al guardar rangos nuevos puede ser necesario volver a guardar la alineación.

## 2 · Postura y alineación: que el dibujo coincida con el brazo

Los rangos no dicen cómo está doblado el brazo. Esta segunda comprobación relaciona
las lecturas de sus motores con la postura del modelo 3D.

1. Elige COM7 o COM8 y marca **Alinear este USB sin mover motores**.
2. Coloca el brazo recogido como tu postura habitual. Pulsa **Usar postura de
   referencia** y ajusta las barras del dibujo hasta que imite al brazo real.
   En este paso las barras solo cambian el dibujo.
3. Pulsa **Esta es la postura**. Se relacionan las lecturas actuales con el dibujo.
4. Mueve cada articulación un poco a mano. Ahora el dibujo debe seguir al brazo.
   Si gira al revés, pulsa el botón **±** correspondiente. Comprueba también
   apertura y cierre de la pinza. Marca **Coincide** tras comprobar cada parte.
5. Pulsa **Guardar alineación** y repite con el otro USB.

La miniatura fija y las bolitas azules muestran la postura de referencia que
indicaste. No prueban que el brazo físico esté ahí. Una bolita hueca indica que
esa referencia queda fuera del rango mostrado. La sombra azul se puede cambiar
entre esa postura, la referencia guardada y el objetivo enviado al motor.

El amarillo representa un ajuste manual hasta capturar una postura; después sigue
los encoders usando la alineación. El texto bajo el modelo indica qué representa.
No marques Coincide si el dibujo no sigue correctamente al brazo.

Para probar las barras sobre el robot o los bailes **Abanico** y **Saludo**,
sal de la alineación, aparta el otro brazo, confirma la casilla de espacio libre
y pulsa **Activar brazo seleccionado**. Se activa uno cada vez.
Antes de cambiar de brazo, sujétalo y pulsa **Soltar brazo**.

## 3 · Preparar y probar: arrancar con los datos guardados

Elige un USB y aparta el otro brazo. Pulsar **Preparar y arrancar** confirma que
el recorrido está libre y autoriza la activación cuando las comprobaciones pasen.
El programa revisa USB, identidad, rangos, postura y temperatura. Si falta algo,
indica el brazo y la articulación que requieren atención. No amplía límites.

La pequeña entrada suave opcional de COM8 está limitada a su codo y a 3 grados;
no busca topes ni sustituye la calibración manual. Revisa el aviso antes de armarlo.

## 4 · Chatbot

El chatbot se abre en la última pestaña, con texto, voz, micrófono, dibujo del campo
y vista 3D de las lecturas reales. No hay cámara: el cuadro es una referencia virtual
delante de los brazos. Las claves de Gemini y ElevenLabs deben estar configuradas.

**PARAR** o Escape interrumpe la interacción y mantiene el brazo sujeto por sus
motores. Para quitar el par, sujétalo físicamente y pulsa **Soltar brazo**.
El programa impide volver a la calibración manual mientras haya un brazo activo.

La próxima sesión no necesita repetir rangos ni alineación si no cambian el montaje,
los servos o su configuración. El programa comprueba la compatibilidad de los datos.
