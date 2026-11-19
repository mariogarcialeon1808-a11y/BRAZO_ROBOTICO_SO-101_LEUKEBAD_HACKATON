# Los dos brazos en el mundo real

En la pestaña **3 · Preparar y probar**, elige **Ambos**. Registra la distancia
entre los centros de las bases, qué lado ocupa COM7 y si ambas bases están a la
misma altura y orientadas en paralelo hacia delante. Guarda estos datos mediante
**Preparar y arrancar**. No se utiliza la separación de la simulación como medida real.

El montaje local confirmado es COM7 a la izquierda y COM8 a la derecha, con una
separación aproximada de 73,35 cm. Está en `config/montaje_dual.json`; es un dato
local del montaje. Cambiar físicamente las bases requiere actualizarlo.

Los dos USB se comprueban antes de activar el primer motor. El visor y las
referencias se cargan antes de activar par. La pestaña 4 muestra el dibujo y los
dos modelos colocados según el montaje guardado, siguiendo sus encoders reales.
No se usa la física ni la información interna del visor para decidir movimientos.

**Saludo ambos** dura unos 14 segundos desde la postura recogida de este montaje.
Mantiene quietas las bases, eleva algo los brazos, gira las pinzas, las abre y
regresa a la postura de inicio. **Abanico ambos** conserva el barrido amplio;
su recorrido completo se comprueba antes de ejecutarlo.

## Velocidad, postura de trabajo y diferencias con la simulación

La velocidad de las articulaciones reales se fija en `config/so101er.toml`:

```toml
[real]
velocidad_grados_s = 110    # de 20 a 150; la simulación usa 150
```

Desde el 15-11-2026 está en 110, elegido por el operador tras probar 60 (correcto, pero
con pocos gestos) y 150 (demasiado brusco). Sin ese valor se usa el perfil de pruebas
de 20°/s.

Ese único valor limita la planificación de gestos (aceleración 4·v y tirón 40·v, la
misma proporción que la simulación), la rampa de consigna del control USB y el perfil
que se escribe en cada servo. La pinza nunca va por debajo de 60°/s. Con 20°/s un
gesto amplio con su regreso tarda entre 30 y 60 s: no cabe en una frase. Para que los
brazos reales hagan lo que hace la simulación hay que subirlo, por pasos (60, 90, 150)
y con la mano cerca de **PARAR** la primera vez de cada paso. Ningún perfil por encima
de 20°/s se ha probado todavía en los brazos: solo en pruebas sin hardware.

La velocidad también se cambia en la propia ventana, con el desplegable **Velocidad**
(20, 60, 90, 120 y 150°/s). Vale para la sesión en curso; al abrir otra se vuelve al
valor del archivo.

Medición con la demostración de cuatro frases (15-11-2026, sin hardware; el modo real
con un modelo de la cadena USB: ciclo de 31 ms, rampa y perfil del servo):

| | Movimientos | La voz arranca | Voz | En movimiento | Pausa más larga | Retraso brazo–voz |
|---|---|---|---|---|---|---|
| Simulación | 4 gestos + 6 acentos | 4,5 s | intacta | 85 % | 0,8 s | 60 ms |
| Real a 150°/s | 4 gestos + 6 acentos | 6,4 s (incluye desplegar) | intacta | 83 % | 0,9 s | 40 ms |
| Real a 60°/s | 3 gestos | 15,5 s | 31 % más lenta | 56 % | 11,9 s | 40 ms |

**Primera medida en los brazos (15-11-2026, 08:03, demostración a 60°/s, lanzada con
`python -m so101er.programa --arrancar --brazo Ambos --demo --velocidad 60`):** terminó
sin paradas. Dos gestos de 96–115° de recorrido a 58°/s; desviación máxima respecto al
plan 6,4° (hombro; el control se detiene a 25°); el encoder iba 90–100 ms por detrás del
plan con el adelanto de 60 ms, y descontado ese retraso el resto era menor de 1°. El bus
lee los seis servos en 2,8 ms. Por eso `retardo_s` vale ahora 0,15 s y los umbrales de
«no sigue la consigna» del control USB se expresan en tiempo (lo que recorre la consigna
en 0,2 s sostenido y en 0,4 s de golpe, con mínimos de 8° y 20°). Esos dos ajustes y
cualquier velocidad por encima de 60°/s siguen sin probar en los brazos.

**Segunda medida (15-11-2026, 08:20, demostración a 150°/s):** se detuvo a los 0,66 s
del primer gesto por «COM7, hombro (ID 2): carga indicada 464» (el control se detiene a
450). Hasta ese instante los dos brazos seguían el plan con menos de 2,3° de desviación y
sin retraso apreciable, con el hombro subiendo a 128°/s: el adelanto de 0,15 s es
correcto. El operador lo vio demasiado brusco y fijó **110°/s** (aceleración 440°/s²),
que es el valor por defecto desde entonces y está sin probar en los brazos. Las
protecciones no se han tocado. Al acabar cada turno la ventana escribe la carga máxima
que midieron los servos, para saber cuánto margen queda.

**Brazo libre y acentos.** El brazo que no hace el gesto lo acompaña (sube con el trazo
del otro, se sostiene y vuelve con su recogida; `acompanar` en
`control/acompanamiento.py`) en vez de esperar inmóvil: antes pasaba quieto el 41–48 %
del tiempo de voz, con pausas de hasta 7–8 s. Los acentos entre gestos abren la pinza lo
que sus límites permiten en ese pulso en lugar de descartarse. Sin hardware, a 110°/s:
4 gestos y 3 acentos, voz intacta, brazos en movimiento el 83 % del tiempo de voz y
ningún brazo quieto más de 2,4 s seguidos.

**Volver a punto cero.** El botón lleva los brazos, a 30°/s como mucho, a la postura de
referencia de la alineación (sustituye a «Plegar»). Interrumpe lo que estén haciendo y
valida el recorrido entero antes de moverse. También sirve tras una parada por carga o
por seguimiento («carga indicada», «no sigue la consigna», «error de seguimiento»): la
reconoce, parte de lo que miden los encoders y vuelve, sin soltar ni preparar de nuevo;
si la causa persiste, se detiene otra vez. Las paradas por temperatura, tensión,
comunicaciones o postura insegura siguen exigiendo sujetar y soltar.

**Carga.** La «carga» del STS3215 es el ciclo de trabajo de su motor, que sube también
con la velocidad aunque nada se le oponga: una pinza abriéndose en el aire a ~137°/s
indicaba 452–484 y los hombros a 100–128°/s, 408–464, y eso cortaba los turnos a 110°/s.
El límite sigue en 450, pero se aplica a la carga neta: la indicada menos el 80 % de la
que corresponde a la velocidad medida por el propio servo (registro 58; velocidad sin
carga tomada como 3072 cuentas/s). Con el servo parado o bloqueado no se descuenta nada.
Al acabar cada turno la ventana escribe la carga neta máxima y la indicada. Si la velocidad
no se leyera, el límite se comporta como antes.

**Comprobado en los brazos (15-11-2026, 15:56–16:03, `sesion_20261115_155618.log`):** cinco
turnos seguidos a 110°/s sin ninguna parada. La carga indicada llegó a 488 (COM7, hombro) y
484 (COM8, hombro), que antes habrían detenido el turno; la neta no pasó de 320. La velocidad
se lee bien: en todos los turnos la neta sale claramente por debajo de la indicada. Al final,
**Volver a punto cero** llevó los dos brazos a la postura de referencia en 12 s.

**Temperatura.** Los servos dan lecturas sueltas imposibles (55–142 °C entre dos de
~28 °C, decenas por sesión). Ya no se relee ni se avisa por cada una: solo detiene un
calor sostenido, cuando la mediana de unos 2 s de lecturas llega a 55 °C, y antes de
activar se usa la mediana de cinco lecturas (límite 50 °C).

**Acompañamiento y ajuste de tiempos.** El movimiento del brazo libre se añade después
de alargar la preparación o la recogida de cada gesto. Añadirlo antes dejaba un quiebro
de velocidad en el empalme y el turno fallaba con «actuación supera límites de
movimiento» (15-11-2026, 12:59).

Cada sesión real guarda plan y encoders de cada ciclo en
`salidas/diagnostico/seguimiento_*.csv` (solo diagnóstico; nada lo lee para decidir).

Solo a 150°/s el modo real hace lo mismo que la simulación. Tres cosas lo acercan a
cualquier velocidad: la consigna se emite por delante del plan (`retardo_s` de
`BrazoChat`, el retardo de la cadena USB) y el seguimiento se juzga contra el plan sin
adelantar; la voz se sintetiza mientras se compilan los gestos; y los gestos se
compilan mientras los brazos se despliegan.

Una trama USB sin respuesta o corrupta se repite hasta tres veces antes de detener la
sesión (`Bus.reintentos` cuenta las repeticiones). Una temperatura, tensión o carga
anómala solo cuenta si se mantiene en tres lecturas seguidas: los hombros dan lecturas
sueltas de 57–135 °C al moverse y la siguiente vuelve a ser normal.

Entre gestos los brazos descansan en la **postura de trabajo**, que es la postura de
reposo de la simulación (en el aire, a poca distancia de cualquier gesto), no en la
postura plegada de la alineación. En la primera petición el programa anuncia
«Desplegando a la postura de trabajo» y lleva los dos brazos a ella mientras la IA y
la voz preparan la respuesta. Antes de soltar, pulsa **Plegar**: los devuelve a la
postura plegada de partida. Si la postura de trabajo no cabe en los rangos guardados
de un brazo, se avisa y se sigue usando la plegada.

Un brazo apoyado en su tope mide décimas de grado más allá del límite nominal del
modelo. Hasta 1° se lleva al límite y se planifica desde él; antes, una sola cuenta de
ruido descartaba todos los gestos («encoders fuera de límites nominales»).

Si a la velocidad configurada no da tiempo a hacer un gesto y volver a reposo antes
del siguiente, ese gesto se omite con un aviso. La voz no se ralentiza más de 1,35
veces; antes se frenaba hasta 8 veces y, por encima, fallaba el turno entero
(«factor temporal fuera de rango»).

Las consignas siguen limitadas en velocidad, aceleración y tirón. Los objetivos
USB se envían juntos y solo se repiten si cambia su posición o velocidad.

Un pico de ciclo superior a 200 ms avisa; no produce una parada permanente. El
avance por ciclo se acota para evitar recuperar el retraso con un salto. Una
interrupción de al menos 1 s, un error de comunicación o un seguimiento incorrecto
detienen la sesión. Una temperatura, tensión o carga anómalas se vuelven a leer
antes de bloquear; una anomalía confirmada sigue deteniendo ambos brazos.

La pequeña tolerancia de cuatro cuentas de encoder absorbe cuantización de la
lectura inicial. Los objetivos emitidos siempre se recortan al interior del margen
guardado; no se amplían los topes de los motores.

La separación se comprueba con cinemática nominal de las consignas y de los
encoders. También se comprueban combinaciones de posiciones por el envío sucesivo
a los dos USB. Esto requiere que el montaje y la alineación guardados correspondan
al montaje físico; el modelo no observa la mesa ni detecta objetos externos.

**PARAR** detiene las órdenes de toda la sesión manteniendo el par. **Soltar ambos**
requiere sujetarlos y verifica el par cero. En la pestaña 3, **Soltar seleccionados**
también permite recuperar una activación incompleta que no llegó a abrir el chatbot.

El lanzador normal no activa motores por abrirse. La opción explícita de CLI
`--arrancar --brazo Ambos` autoriza el arranque usando el montaje guardado.

Las regiones visuales admiten dos esquinas, cuatro coordenadas o campos ymin/xmin/
ymax/xmax. Se conserva el orden y,x y el rango 0–1000; no se inventa profundidad.
Si el formato falla, la IA tiene un intento de corrección. Si solo queda texto
válido, ese bloque se narra sin ejecutar un gesto inventado.
