# Panel de modelo, ejes y secuencias

La versión actual incorpora [alineación por brazo y entrada suave de COM8](ALINEACION_USB.md).
Ese documento sustituye las limitaciones y comportamientos históricos de abajo.

## Corrección de correspondencia de coordenadas

Los grados relativos al instante de activación se estaban dibujando directamente
como ángulos URDF. Eso era incorrecto: un brazo completamente recogido podía
aparecer extendido. Registrar extremos de encoder no establece ceros ni signos
del modelo. No se han cambiado los offsets del hardware ni se han supuesto ángulos
de recogida a partir de una descripción verbal.

La vista de COM7/COM8 ahora indica que falta alineación en lugar de dibujar una
pose física falsa. Los controles manuales siguen siendo relativos a la postura
de activación. Los bailes físicos se bloquean hasta completar esa correspondencia;
los bailes en simulación siguen disponibles. Esta corrección sustituye las
afirmaciones de bailes USB habilitados que figuran en el historial más abajo.
Falta registrar una postura física conocida por brazo y comprobar los cinco
sentidos de giro. Esa transformación debe usarse tanto al visualizar encoders
como al convertir consignas de modelo, sin alimentar el controlador con MuJoCo.

## Control actual: Simulación / COM7 / COM8

El desplegable superior elige el destino. En USB, apartar el otro brazo, confirmar
la casilla y pulsar «Activar brazo seleccionado». Se leen los encoders y se asignan
esas posiciones como objetivos ANTES de activar los seis motores. Solo se conecta
para escribir al USB elegido. Los deslizadores mueven sus articulaciones en tiempo
real, a un máximo de 8 grados/s. Si una articulación está en un tope, apartarla a
mano antes de activar: se reserva un margen de 12 cuentas respecto a la intersección
de límites heredados y rangos observados.

Los primeros cinco valores son grados relativos a la postura de activación, no
ceros URDF. La pinza usa 0–100 % del rango útil. La vista del modelo sigue siendo
ilustrativa: no certifica la postura física ni colisiones. La geometría del montaje
y la alineación URDF aún no están verificadas.

«Abanico» y «Saludo» funcionan también en el USB activo, como secuencias nativas
con amplitud reducida respecto a la versión virtual. Se valida la secuencia entera
antes de iniciarla; si no cabe en los rangos, no comienza. Regresan a su postura
inicial. El movimiento real se limita a 6 grados/s en los bailes.

«PARAR» o Escape detiene el movimiento manteniendo par para evitar que el brazo
caiga. Para cambiar de brazo o cerrar, sujetarlo primero y pulsar «Soltar brazo».
No se cambian offsets ni EEPROM. El controlador utiliza solo encoders/telemetría
reales, constantes, consignas y memoria; no importa MuJoCo. Se probaron conversiones,
límites, selección exclusiva de USB, objetivo anterior al par y liberación mediante
un bus de prueba. Falta verificar este control manual en el hardware con el usuario.

## Versión anterior del panel (referencia histórica)

Abrir `PRUEBAS_SO101.cmd`. Al terminar las doce capturas de rangos y pulsar
«Guardar» en el calibrador también se abre este panel y se liberan los USB.

Los seis controles mueven solo el modelo nominal. La articulación seleccionada
muestra sus ejes locales: X rojo, Y verde, Z azul. «Abanico» y «Saludo» ejecutan
secuencias articulares explícitas, con interpolación quintica y regreso al inicio.
No se han entrenado ni se ejecutan como una policy. Las danzas son vistas previas;
no se envían al hardware.

El modelo se renderiza desde consignas y la cinemática nominal. Sus datos internos
y la proyección de las guías no alimentan al controlador USB. El archivo de rangos
sigue sin certificar ceros, sentidos ni geometría del montaje. La postura dibujada
no se presenta como una medición de la postura física de COM7 o COM8.

## Primera prueba física independiente

El botón «Probar base de COM7» requiere confirmar que COM8 está apartado y todo el
barrido queda libre. Hay cinco segundos de cuenta atrás. Solo se activa el servo 1
(giro de base) de COM7. El resto permanece sin par; COM8 se abre exclusivamente en
lectura. No se mantiene una postura nueva ni se accionan las pinzas.

Primero se prueban 3 grados y regreso. Si se alcanza el objetivo, sigue un barrido
de +35 a -35 grados respecto al inicio y vuelta al inicio. El límite de velocidad
es 8 grados/s, con consignas quinticas y velocidad del servo limitada. El recorrido
debe caber en la intersección de rangos observados y límites del servo, con 64
cuentas de margen por extremo. Si no cabe, no se activa el motor.

Se comprueban identidad de adaptadores, ajustes heredados, modo, par inicial,
temperatura, tensión, carga indicada, seguimiento y estabilidad de las otras
articulaciones y del brazo apartado. Esas comprobaciones no sustituyen una
validación geométrica del montaje ni garantizan ausencia de colisiones.

«PARAR» o Escape cancela la prueba y desactiva solo el giro de base. Cerrar espera
a que la tarea termine su salida. El par también se desactiva al finalizar o ante
un error; si falla la comunicación se informa que no pudo confirmarse. No se
escribe EEPROM. Los ajustes temporales de aceleración/tiempo/velocidad se restauran
con el servo sin par. El resultado queda en `salidas/diagnostico/prueba_base_COM7.json`.

La prueba de hardware usa exclusivamente encoders y telemetría reales, rangos
observados, consignas y memoria. Las pruebas verifican escritura limitada al servo
1/RAM, límites, regreso, parada ante movimiento del otro brazo e invariancia al
cambiar verdad no observable conservando sensores y memoria.
