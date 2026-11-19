# Alinear el cero operativo de cada brazo

El cero operativo recogido de este montaje no coincide con q=0 del URDF. Los
rangos de encoder solos tampoco definen esa correspondencia. La alineación guarda
una postura física conocida (encoders), su postura URDF indicada por el operador
y los seis signos. No cambia EEPROM ni offsets del servo.

En `PRUEBAS_SO101.cmd`, para cada USB por separado:

1. Con el brazo sin par, elegir COM7 o COM8 y marcar «Alinear este USB sin mover
   motores». Si estaba activado, sujetarlo y pulsar primero «Soltar brazo».
2. «Recogida orientativa» proporciona solo un punto de partida dibujado. Ajustar
   los seis deslizadores para igualar la postura real, incluyendo giro de base,
   muñeca y pinza. Se puede arrastrar la imagen para girar la cámara y revisar
   desde varios ángulos. La referencia orientativa no se registra como calibración.
3. «Capturar postura» toma los encoders. Desde ese instante el modelo sigue las
   lecturas reales mediante la transformación provisional; los deslizadores de
   ajuste quedan bloqueados.
4. Mover a mano cada eje de forma individual. Si el modelo gira al revés, pulsar
   su botón `±`. Comprobar postura y sentido en varias posiciones, no solo en el
   extremo recogido. Marcar «Coincide» para los seis ejes, incluida apertura.
5. «Guardar alineación» exige las seis confirmaciones. Se conserva por separado
   en `config/alineacion_COM7.json` o `alineacion_COM8.json`. Las copias anteriores
   se guardan; estos archivos locales se excluyen de Git.
6. Desmarcar Alinear, apartar el otro brazo y activar el elegido. El dibujo usa
   encoders transformados y las consignas hacen la conversión inversa. Para
   cambiar al otro brazo hay que sujetar y soltar el primero.

La comprobación es visual/manual: no es una calibración metrológica ni certifica
las bases, obstáculos o colisiones. No se ha supuesto una postura absoluta a
partir de la foto. Cambiar rangos, adaptador o ajustes de servo invalida el archivo.

## COM8 junto al tope de codo

La casilla «COM8: entrada suave del codo (≤3°)» permite únicamente entrar hacia el
interior del rango del codo de ese USB al activar. Solo se acepta si las otras
cinco articulaciones ya están en rango, la lectura está dentro del recorrido
observado y la corrección no supera 3°. Se limita inicialmente el servo a unas
11 cuentas/s (aproximadamente 1°/s), sin cambiar sus límites. Se reserva espacio
para la banda muerta. El control normal no se habilita hasta estar dentro del
rango; si no entra en 20 s se detiene con error. No se realiza durante la alineación.

Al activar con esta opción puede haber ese pequeño movimiento intencional. El
objetivo escrito antes del par es el punto interior validado, no el encoder fuera
de límite. «PARAR» mantiene el punto permitido más cercano; «Soltar» requiere
sujetar el brazo porque elimina el par de las seis articulaciones.

## Bailes

Solo funcionan físicamente con alineación guardada y validada para ese USB. Antes
de emitir consignas se comprueba la secuencia completa: límites URDF, conversión
a los rangos reales y altura nominal sobre mesa. La apertura usa los extremos
útiles con margen. La transición inicial también se valida y la secuencia regresa
a su postura de comienzo. Un baile que no cabe se rechaza sin comenzarlo.

El controlador usa encoders/telemetría, referencias del operador, calibración
nominal y memoria. El renderizado MuJoCo no aporta verdad interna a sus decisiones.
Las pruebas cubren conversiones y signos, archivos independientes, invalidación,
secuencias convertidas, entrada de COM8 con un bus de prueba e invariancia del
envío ante cambios de estado privilegiado del visor. Falta la comprobación visual
y física con el operador en los dos brazos.
