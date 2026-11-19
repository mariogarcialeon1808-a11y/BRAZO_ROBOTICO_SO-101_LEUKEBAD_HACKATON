# Ventana de rangos manuales

Abrir `CALIBRAR_USB.cmd`. Elegir COM7 o COM8 y un motor en los dos desplegables;
también se puede seleccionar directamente su fila en la tabla. Mover a mano el
motor elegido por su rango útil, despacio, evitando colisiones y sin forzar topes.
El mínimo y máximo se registran automáticamente mientras ese motor está seleccionado.
Cambiar de motor y repetir. «Reiniciar rango» borra solo la captura seleccionada.
«Guardar rangos» guarda todas las capturas, aunque sean parciales.

La ventana tiene solo esos dos botones. Lee los doce encoders, temperatura y par;
no activa ni desactiva motores y no modifica EEPROM, offsets o límites del servo.
El bus bloquea cualquier instrucción de escritura. Si hay par, error USB o datos
antiguos se detiene la captura. Para redetectar un USB, cerrar y volver a abrir.

El resultado es `config/calibracion_rangos_usb.json`, con el número de serie de
cada adaptador y una copia de los ajustes existentes. Al guardar otra vez se
conserva el archivo anterior. Las capturas de rangos no se presentan como ceros
URDF ni sentidos verificados: esa correspondencia y la geometría del montaje se
comprueban antes de habilitar gestos automáticos. No genera automáticamente los
archivos `calibracion_izq.json` y `calibracion_der.json` exigidos por el controlador.

En el diagnóstico inicial respondieron los seis motores de ambos adaptadores:
COM7, serie 5B90100837; COM8, serie 5B90102636. Todos estaban sin par, a 24–26 °C.
Las dos bases están próximas y las pinzas pueden alcanzarse: no se ha validado
todavía su geometría real ni se ha ejecutado movimiento motorizado.

Las entradas de esta herramienta son exclusivamente sensores de hardware y
elecciones del operador. No importa MuJoCo ni usa verdad privilegiada simulada.

## Los rangos guardados se cargan al abrir

Los rangos no hay que recorrerlos cada vez que se arranca el programa. Al abrir, la pestaña 1
carga los de `config/calibracion_rangos_usb.json` y los muestra con el estado **guardado** y la
fecha en que se guardaron. Un motor con rango guardado no se vuelve a registrar aunque se mueva
a mano.

- **Repetir un solo motor:** elígelo, pulsa **Reiniciar rango de este motor**, recórrelo de
  extremo a extremo y pulsa **Guardar rangos**. Los otros once se conservan como estaban.
- **Guardar sin cambios** no escribe nada: lo dice y deja el archivo intacto.
- Si un brazo no está conectado, sus rangos guardados se ven como «guardado · USB sin conectar»
  y se conservan al guardar los del otro.
- Si el adaptador de ese puerto es otro, o los servos tienen ahora otro offset o límites
  internos, los rangos guardados no se cargan: ya no describen ese brazo y hay que recorrerlos.

Guardar rangos nuevos sigue invalidando la postura de la pestaña 2 de ese brazo, que hay que
repetir una vez. Por eso conviene no volver a guardar rangos si no hace falta.

La ventana se abre en la primera pestaña que hace falta: la 1 si faltan rangos, la 2 si falta o
hay que repetir la postura, y la 3 si todo está guardado. La línea de arriba dice qué le falta a
cada brazo.

