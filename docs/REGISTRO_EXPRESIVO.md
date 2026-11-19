# Registro expresivo: conceptos y movimientos

> Generado por `tools/registro_expresivo.py` a partir de `datos/expresion/registro.json`. Para cambiar algo, edita el JSON y vuelve a generar; no edites este archivo.

Las reglas de uso están en [PROTOCOLO_EXPRESIVO.md](PROTOCOLO_EXPRESIVO.md).

## Resumen

- **84 movimientos** y **273 conexiones** concepto → movimiento.

| Estado | Movimientos | Conexiones |
|---|---|---|
| Lo hacía ya | 7 | 20 |
| En la biblioteca | 72 | 240 |
| Con el motor actual (sin conectar) | 5 | 13 |

Comprobado el 2026-11-16 contra el motor de gestos, a 110°/s y 500.0 mm entre bases (montaje y velocidad de los brazos reales; sin hardware). «Cabe» significa que el movimiento, saliendo de reposo y volviendo a él, respeta rangos, velocidad, altura sobre la mesa y distancia a la obra y entre brazos. No significa que se haya visto en los brazos.

## Estados

- **Lo hacía ya:** uno de los gestos de siempre (señalar, región, abanicos, línea, acento).
- **En la biblioteca:** comprobado contra el motor; la IA lo puede pedir con el tipo `gesto` y el programa lo ejecuta.
- **Con el motor actual (sin conectar):** se compone con piezas que el motor ya tiene; sin comprobación propia.
- **No cabe tal cual:** el motor lo rechaza; el motivo está en la tabla.

## Papeles del otro brazo

- **acompana:** Se mueve un poco con el gesto del principal y vuelve, como hoy. No añade significado.
- **espejo:** Hace el mismo movimiento en simetría: los dos forman un solo gesto.
- **ancla:** Sostiene una referencia (un punto, una altura, una mitad) mientras el principal se mueve respecto a ella.
- **prepara:** Va ya a la postura de salida del gesto siguiente, para que empiece a tiempo.
- **contrapunto:** Hace otro movimiento con significado propio que completa al principal.
- **libre:** El gesto es de un solo brazo y el otro no añade significado. Queda disponible: prepara el gesto siguiente si ya se conoce; si no, acompaña o descansa (reglas R17 a R19 del protocolo).

## Fuentes

| Fuente | Qué aporta | Estado |
|---|---|---|
| Diseño propio para el SO-101 (`propio`) | La geometría de cada movimiento: posturas clave que caben en un brazo de 5 articulaciones y pinza, sin dedos. | Comprobado contra el motor de gestos; sin ver en los brazos. |
| [SeG (Semantic Gesticulator)](https://github.com/LuMen-ze/Semantic-Gesticulator-Official) (`seg`) | El significado: 208 gestos humanos con su descripción y sus contextos de uso. Cada movimiento cita el gesto de SeG del que toma el sentido, con su índice. | Lista completa y dos clips en local. Licencia de investigación no comercial, sin redistribución. |
| [BEAT2](https://huggingface.co/datasets/haiyangliu0/BEAT2) (`beat2`) | El ritmo: cómo se reparte un movimiento en el tiempo al hablar. | Un clip en local, convertido a perfil de ritmo. |
| [MM-Conv / SGS-HSI 2026](https://huggingface.co/datasets/hsi-workshop/referential-gesture-challenge) (`mmconv`) | Los gestos referenciales: señalar algo concreto del entorno mientras se conversa. | Un clip en local. |
| [RoboGesture (ECCV 2026)](https://arxiv.org/abs/2608.28693) (`robogesture`) | El método, no los datos: dos capas (gesto con significado sobre movimiento rítmico), el gesto empieza antes que su palabra, y cada clase se valida en el robot y se descarta si no es realizable. | Es para un humanoide Unitree G1 con manos de dedos (41 articulaciones). El artículo no publica la lista de sus más de 300 clases ni dice que los datos estén disponibles; parte de SeG, que sí tenemos. |
| [SmolVLA (LeRobot)](https://huggingface.co/docs/lerobot/smolvla) (`smolvla`) | El formato de una política entrenada: una frase de tarea por movimiento y unas 50 demostraciones por tarea. Cada movimiento del registro lleva ya su frase. | No es un conjunto de datos de gestos: es un modelo de 450 M de parámetros entrenado para manipular objetos. No se usa para ejecutar; ver el protocolo. |

## Movimientos

«Gráfico» son los que dibujan el concepto: una forma, un trayecto, un tamaño, una cantidad o una acción. Cada frase tiene que llevar al menos uno.

### Deícticos: señalar y recorrer

Dicen dónde: un punto, una zona o un trayecto de la imagen, o una dirección del espacio real.

| Id | Movimiento | Gráfico | Qué hace | Estado | Dura (izq / der) | Origen |
|---|---|---|---|---|---|---|
| D01 | señalar un punto |  | Apunta a un punto de la imagen y lo sostiene. | Lo hacía ya | — | propio, seg:FOREFINGER POINT (1211), mmconv |
| D02 | barrer una región |  | Recorre de lado a lado una zona de la imagen. | Lo hacía ya | — | propio, seg:FOREFINGER SCAN (1221) |
| D03 | trazar una ruta |  | Sigue sobre la imagen un trayecto de varios puntos: una calle, un recorrido en el mapa. | Con el motor actual (sin conectar) | — | propio, mmconv |
| D04 | rodear una zona |  | Dibuja el contorno de una zona de la imagen. | Con el motor actual (sin conectar) | — | propio, seg:HANDS DRAW-OUTLINE (1301) |
| D05 | saltar entre puntos |  | Apunta a varios puntos de la imagen uno tras otro, con una parada breve en cada uno. | Con el motor actual (sin conectar) | — | propio, seg:FOREFINGER HOP (1230) |
| D06 | indicar hacia un lado |  | Extiende el brazo hacia su lado, fuera de la imagen: «a la izquierda», «a la derecha». | En la biblioteca | 3.1 s / 3.1 s | propio, seg:FOREFINGER POINT (1211) |
| D07 | indicar al frente |  | Extiende el brazo recto hacia delante. | En la biblioteca | 3.7 s / 3.7 s | propio, seg:FOREFINGERS POINT-FORWARD (1212) |
| D08 | indicar arriba |  | Sube la pinza apuntando al techo. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:FOREFINGER RAISE-SKY (3102) |
| D09 | indicar abajo |  | Baja la pinza apuntando al suelo. | En la biblioteca | 3.0 s / 3.0 s | propio |
| D10 | aquí mismo |  | Dos toques cortos hacia abajo, cerca: «aquí», «en este punto». | En la biblioteca | 4.2 s / 4.2 s | propio |
| D11 | allí, lejos |  | El brazo se alarga y sube hacia fuera: «al fondo», «a lo lejos». | En la biblioteca | 5.0 s / 5.0 s | propio, seg:ARM ENDEAVOR (2302) |
| D12 | hacia quien escucha |  | Pinza abierta hacia el centro, donde está la persona: «usted», «su caso». | En la biblioteca | 3.4 s / 3.4 s | propio, seg:FOREFINGERS POINT-FORWARD (1212) |
| D13 | hacia sí mismo |  | Recoge la pinza hacia el propio cuerpo: «yo», «nosotros», «este servicio». | En la biblioteca | 2.0 s / 2.0 s | propio |

### Espaciales: dibujar en el aire

Un brazo dibuja la forma o el trayecto de lo que se cuenta: una calle, una cuesta, un río, una rotonda.

| Id | Movimiento | Gráfico | Qué hace | Estado | Dura (izq / der) | Origen |
|---|---|---|---|---|---|---|
| E01 | abanico horizontal | sí | Arco amplio a media altura: un paisaje, una extensión. | Lo hacía ya | — | propio, seg:ARMS ENCOMPASS (3032) |
| E02 | abanico elevado | sí | Arco amplio con la pinza levantada: cielo, horizonte. | Lo hacía ya | — | propio, seg:ARMS RAISE TOWORDS-SKY (2001) |
| E03 | línea recta | sí | Recta corta con la pinza paralela al trayecto. | Lo hacía ya | — | propio |
| E04 | avanzar recto | sí | De cerca hacia delante: «siga recto», «continúe». | En la biblioteca | 4.3 s / 4.3 s | propio, seg:PALM THRUST (2113) |
| E05 | girar hacia fuera | sí | Avanza y dobla hacia el lado del brazo: «gire a la izquierda/derecha». | En la biblioteca | 5.1 s / 5.1 s | propio |
| E06 | girar hacia dentro | sí | Avanza y dobla hacia el centro. | En la biblioteca | 5.0 s / 5.0 s | propio |
| E07 | rotonda | sí | Círculo horizontal completo. | En la biblioteca | 5.0 s / 5.0 s | propio, seg:FOREFINGER SPIN (2310) |
| E08 | subir | sí | Línea vertical de abajo arriba: cuesta, aumento, planta superior. | En la biblioteca | 3.5 s / 3.5 s | propio, seg:HANDS RISE (3010) |
| E09 | bajar | sí | Línea vertical de arriba abajo: descenso, bajada, reducción. | En la biblioteca | 3.3 s / 3.3 s | propio, seg:PALM LOWER (2321), seg:ARMS DESCEND (2220) |
| E10 | ondular | sí | Avanza de lado subiendo y bajando: río, colinas, oleaje. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:HAND WOBBLE (2011) |
| E11 | zigzag | sí | Avanza de lado acercándose y alejándose: curvas, callejuelas. | En la biblioteca | 5.0 s / 5.0 s | propio |
| E12 | escalones | sí | Sube por tramos: plantas, niveles, fases. | En la biblioteca | 5.3 s / 5.3 s | propio, seg:HAND FALL (3012) |
| E13 | arco de un lado a otro | sí | De un punto a otro pasando por arriba: puente, conexión, traslado. | En la biblioteca | 3.9 s / 3.9 s | propio, seg:HAND DOORWAY-TURN (3020) |
| E14 | ida y vuelta | sí | Va de un lado a otro y regresa. | En la biblioteca | 4.5 s / 4.5 s | propio |
| E15 | espiral ascendente | sí | Círculos que suben: proceso, desarrollo. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:FOREFINGER SPIRAL (1232) |
| E16 | marcar una altura | sí | Pinza abierta y quieta a una altura: «así de alto». | En la biblioteca | 4.1 s / 4.1 s | propio, seg:HAND MEASURE-UP (3011), seg:HAND MEASURE-DOWN (2320) |
| E17 | clavar un punto | sí | Golpe corto hacia abajo: «justo ahí», una parada, el destino. | En la biblioteca | 3.6 s / 3.6 s | propio, seg:FOREFINGER BEAT (1011) |
| E18 | línea transversal | sí | Raya de lado a lado delante del cuerpo: frontera, calle que cruza. | En la biblioteca | 4.3 s / 4.3 s | propio, seg:PALMS BOUNDARY (2032) |
| E19 | superficie llana | sí | Pasada baja con la pinza abierta: plaza, explanada, llano. | En la biblioteca | 4.6 s / 4.6 s | propio |
| E20 | puntear una serie | sí | Tres toques seguidos avanzando de lado: paradas, lista de sitios. | En la biblioteca | 5.2 s / 5.2 s | propio, seg:FOREFINGER HOP (1230) |

### Bimanuales: los dos brazos componen

Los dos brazos forman juntos un solo significado: tamaño, unión, reparto, comparación.

| Id | Movimiento | Gráfico | Qué hace | Estado | Dura (izq / der) | Origen |
|---|---|---|---|---|---|---|
| B01 | abarcar con los dos | sí | Los dos brazos abren a la vez un abanico amplio. | Lo hacía ya | — | propio, seg:ARMS ENCOMPASS (3032) |
| B02 | medir un tamaño | sí | Las dos pinzas se detienen enfrentadas: «así de ancho». | En la biblioteca | 3.1 s / 3.1 s | propio, seg:FOREFINGERS MEASURE (1213) |
| B03 | expandir | sí | Del centro hacia fuera, abriendo las pinzas: grande, crecer, ampliar. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:PALMS EXPAND (3031) |
| B04 | juntar | sí | De fuera hacia el centro, cerrando las pinzas: unir, concentrar, reunir. | En la biblioteca | 5.0 s / 5.0 s | propio, seg:ARMS FUSE (3310), seg:HANDS UNITE (3313) |
| B05 | dividir en dos | sí | Los dos bajan juntos en el centro y se separan: reparto, dos partes. | En la biblioteca | 4.5 s / 4.5 s | propio, seg:HANDS DIVIDE (2201) |
| B06 | balanza | sí | Uno sube mientras el otro baja, y se igualan: comparar, depende. | En la biblioteca | 4.5 s / 4.5 s | propio, seg:PALMS BALANCE (2012) |
| B07 | paralelas | sí | Los dos avanzan a la vez en líneas paralelas: avenida, carriles, orillas. | En la biblioteca | 3.9 s / 3.9 s | propio |
| B08 | cruce | sí | Un brazo avanza recto y el otro traza una raya transversal por encima. | En la biblioteca | 4.4 s / 4.4 s | propio |
| B09 | bienvenida |  | Los dos se abren hacia fuera, bajos y con las pinzas abiertas. | En la biblioteca | 4.4 s / 4.4 s | propio, seg:ARMS WELCOME (3101) |
| B10 | celebrar |  | Los dos arriba y abiertos, en V. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:ARMS RAISE V-SHAPE (3100) |
| B11 | inclinarse para agradecer |  | Las dos pinzas bajan hacia delante un momento. | En la biblioteca | 3.2 s / 3.2 s | propio, seg:ARM GRATITUDE (3233) |
| B12 | encogerse |  | Los dos suben un poco hacia fuera con las pinzas abiertas: duda, «no consta». | En la biblioteca | 3.4 s / 3.4 s | propio, seg:HANDS SHRUG (2021), seg:PALMS UP-LOW (2312) |
| B13 | calmar |  | Los dos bajan despacio, dos veces: tranquilidad, despacio. | En la biblioteca | 5.1 s / 5.1 s | propio, seg:PALM LOWER (2321), seg:HAND FLOP (3331) |
| B14 | barrera |  | Los dos al frente y altos, pinzas abiertas y quietas: cerrado, prohibido, peligro. | En la biblioteca | 5.0 s / 5.0 s | propio, seg:PALMS FRONT (2031), seg:HANDS CROSS (2132) |
| B15 | enmarcar |  | Cada brazo señala un extremo de una zona de la imagen y los dos sostienen. | Con el motor actual (sin conectar) | — | propio, seg:HANDS DRAW-OUTLINE (1301) |
| B16 | origen y trayecto |  | Un brazo sostiene el punto de partida mientras el otro recorre el trayecto. | Con el motor actual (sin conectar) | — | propio, mmconv |
| B17 | por un lado, por otro |  | Un brazo presenta hacia su lado y vuelve; después lo hace el otro. | En la biblioteca | 5.9 s / 5.9 s | propio, seg:PALMS REVERSE (2023) |
| B18 | capas | sí | Las dos pinzas quedan una sobre otra y la de abajo pasa arriba: niveles, acumulación. | En la biblioteca | 3.7 s / 3.7 s | propio |
| B19 | rodear | sí | Los dos cierran un arco de fuera al centro: recinto, zona protegida, conjunto. | En la biblioteca | 4.8 s / 4.8 s | propio, seg:ARMS SURROUND (3311), seg:HANDS SHELTER (3330) |
| B20 | engranar | sí | Los dos dibujan círculos a contratiempo: funcionamiento, proceso en marcha, circulación. | En la biblioteca | 5.4 s / 5.4 s | propio, seg:WRISTS CHANGE (1310) |

### Discurso y trato: lo que no es un lugar

Cantidad, tiempo, permiso, cortesía y marcha de la conversación. Son movimientos cortos, cerca del cuerpo.

| Id | Movimiento | Gráfico | Qué hace | Estado | Dura (izq / der) | Origen |
|---|---|---|---|---|---|---|
| M01 | acento |  | Pulso breve cerca del cuerpo, al ritmo de la voz. | Lo hacía ya | — | propio, beat2, seg:HANDS EMPHASIS (3021) |
| M02 | ofrecer |  | Pinza abierta y girada hacia arriba, baja y al frente: «aquí tiene», «puede usar». | En la biblioteca | 3.8 s / 3.8 s | propio, seg:PALM OFFER (3002), seg:PALM UP (3001) |
| M03 | alto |  | Brazo al frente y arriba, pinza abierta y quieta: detener, prohibido. | En la biblioteca | 5.4 s / 5.4 s | propio, seg:PALM HALT (2300) |
| M04 | negar |  | Vaivén lateral corto, dos veces: no, no disponible. | En la biblioteca | 4.9 s / 4.9 s | propio, seg:HAND WAG (2130), seg:FOREFINGER WAG (2101) |
| M05 | afirmar |  | Dos bajadas cortas: sí, correcto, de acuerdo. | En la biblioteca | 3.4 s / 3.4 s | propio, seg:HAND JAB (1013) |
| M06 | enumerar | sí | Tres paradas avanzando de lado, con la pinza un tercio más abierta en cada una: primero, segundo, tercero. | En la biblioteca | 5.0 s / 5.0 s | propio, seg:FINGERS 'THREE' (1201) |
| M07 | corte | sí | Bajada seca con la pinza de canto: fin, límite, «hasta aquí». | En la biblioteca | 4.5 s / 4.5 s | propio, seg:HAND CHOP (2210), seg:FOREARM CUT (2211) |
| M08 | apartar |  | Del centro hacia fuera abriendo la pinza: descartar, salvo, evite. | En la biblioteca | 4.2 s / 4.2 s | propio, seg:FOREARM THROW-SIDE (2111), seg:HAND FLAP (2110) |
| M09 | atraer | sí | De lejos hacia el cuerpo cerrando la pinza: venga, traiga, recoja. | En la biblioteca | 4.2 s / 4.2 s | propio, seg:HANDS DRAW-BACK (3211), seg:FINGERS BECKON (3320) |
| M10 | empujar | sí | Del cuerpo hacia delante con la pinza abierta: envíe, entregue, continúe. | En la biblioteca | 4.2 s / 4.2 s | propio, seg:PALM THRUST (2113) |
| M11 | buscar |  | Círculo pequeño y cercano: consultando, un momento. | En la biblioteca | 4.4 s / 4.4 s | propio, seg:HAND ROTATE (2311) |
| M12 | reloj | sí | Círculo en vertical: duración, horario, tiempo de espera. | En la biblioteca | 5.1 s / 5.1 s | propio, seg:WRIST CHECK-TIME (0212) |
| M13 | desplazar hacia fuera |  | Del frente hacia el lado del brazo y sostiene: después, más adelante, lo siguiente. | En la biblioteca | 3.3 s / 3.3 s | propio, seg:PALMS TURN-PAGE (1222) |
| M14 | desplazar hacia dentro |  | Del frente hacia el centro y sostiene: antes, lo anterior. | En la biblioteca | 3.3 s / 3.3 s | propio |
| M15 | abrir la pinza |  | La pinza se abre del todo y se queda: abierto, disponible, empieza. | En la biblioteca | 5.2 s / 5.2 s | propio, seg:HAND OPEN (2020), seg:HAND BLOOM (3212) |
| M16 | cerrar la pinza |  | La pinza se cierra del todo y se queda: cerrado, completo, guardado. | En la biblioteca | 5.2 s / 5.2 s | propio, seg:FIST CLASP (1021), seg:FINGERS SHUT (2100) |
| M17 | hablar con la pinza |  | La pinza se abre y se cierra dos veces arriba: llamar, preguntar, por teléfono. | En la biblioteca | 6.3 s / 6.3 s | propio, seg:FINGERS TALK (2330), seg:HAND CALL (3321) |
| M18 | escribir | sí | Trazo pequeño y bajo en zigzag: formulario, firma, solicitud. | En la biblioteca | 4.2 s / 4.2 s | propio, seg:HAND 'WRITE' (3300) |
| M19 | entregar | sí | Ofrece y cierra la pinza al avanzar: pagar, entregar un documento. | En la biblioteca | 5.1 s / 5.1 s | propio, seg:PALM OFFER (3002), seg:HANDS INSERT (3302) |
| M20 | saludar |  | Brazo arriba y vaivén: hola, adiós. | En la biblioteca | 5.5 s / 5.5 s | propio, seg:HAND WAVE (3123), seg:FINGERS WAVE (3121) |
| M21 | pedir atención |  | Brazo en alto y quieto, pinza abierta: atención, importante, aviso. | En la biblioteca | 5.2 s / 5.2 s | propio, seg:ARM RAISE HIGH-LEVEL (3110) |
| M22 | esperar |  | Pinza abierta al frente, baja y quieta: espere, un momento, su turno. | En la biblioteca | 4.7 s / 4.7 s | propio, seg:HANDS T-SIGN (2301), seg:PALM HALT (2300) |
| M23 | escuchar |  | Se inclina un poco hacia quien habla, pinza a medias, y se queda. | En la biblioteca | 3.0 s / 3.0 s | propio, robogesture |
| M24 | ceder el turno |  | Ofrece hacia la persona y sostiene: «¿y usted?», «¿alguna pregunta?». | En la biblioteca | 4.5 s / 4.5 s | propio, seg:PALM UP (3001), seg:ARMS REACH (3111) |
| M25 | un poco | sí | La pinza casi se cierra, en alto: poco, pequeño, breve, cerca. | En la biblioteca | 4.4 s / 4.4 s | propio, seg:FINGERS ESTIMATE (2322) |
| M26 | mucho | sí | Arco de un brazo de dentro y abajo a fuera y arriba, abriendo la pinza. | En la biblioteca | 4.4 s / 4.4 s | propio, seg:HAND PURSE-AROUND (0010) |
| M27 | más o menos |  | La muñeca gira a un lado y a otro: aproximado, depende. | En la biblioteca | 4.6 s / 4.6 s | propio, seg:HAND ROTATE (2311), seg:HAND WOBBLE (2011) |
| M28 | deprisa | sí | Dos avances cortos y seguidos: rápido, urgente, ya. | En la biblioteca | 4.7 s / 4.7 s | propio, seg:ARMS RUN (1122) |
| M29 | despacio |  | Pasada larga con la pinza abierta, hecha a la mitad de velocidad: con calma, zona tranquila. | En la biblioteca | 4.1 s / 4.1 s | propio, seg:ARM ENDEAVOR (2302) |
| M30 | golpe firme |  | Bajada fuerte con la pinza cerrada: obligatorio, imprescindible. | En la biblioteca | 3.0 s / 3.0 s | propio, seg:FIST PUNCH (1133), seg:FIST BEAT (1131) |
| M31 | dos opciones |  | Un brazo presenta a un lado y luego al otro. | En la biblioteca | 5.4 s / 5.4 s | propio, seg:PALMS OVERTURN (2222) |

## Conexiones concepto → movimiento

Cada fila dice qué hace el brazo principal y qué hace el otro mientras tanto. «Después» es el movimiento que encadena el mismo brazo sin pasar por reposo.

### Conversación (28)

Trato y marcha del diálogo: saludar, escuchar, confirmar, ordenar lo que se dice.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| CV01 | saludo | «Hola, buenos días.» | M20 saludar | acompana | En la biblioteca |  |
| CV02 | bienvenida | «Bienvenido a la oficina de turismo.» | B09 bienvenida | espejo | En la biblioteca |  |
| CV03 | presentarse | «Soy el asistente de este punto de información.» | D13 hacia sí mismo | libre | En la biblioteca |  |
| CV04 | ofrecer ayuda | «¿En qué puedo ayudarle?» | M24 ceder el turno | acompana | En la biblioteca |  |
| CV05 | escuchar | «(mientras la persona habla)» | M23 escuchar | espejo | En la biblioteca | Los dos brazos quietos e inclinados. Sin acentos: no se gesticula mientras se escucha. |
| CV06 | entendido | «Entendido.» | M05 afirmar | libre | En la biblioteca |  |
| CV07 | pedir que repita | «¿Puede repetirlo?» | M09 atraer | libre | En la biblioteca | Corto y hacia sí. |
| CV08 | pedir que elija entre dos | «¿Se refiere al centro de salud o al hospital?» | M31 dos opciones | libre | En la biblioteca |  |
| CV09 | consultar un dato | «Un momento, lo consulto.» | M11 buscar | ancla: M22 esperar | En la biblioteca | Un brazo pide espera mientras el otro «busca». |
| CV10 | no lo sé | «No tengo ese dato.» | B12 encogerse | espejo | En la biblioteca |  |
| CV11 | afirmar | «Sí, está abierto.» | M05 afirmar | acompana | En la biblioteca |  |
| CV12 | negar | «No, hoy no hay servicio.» | M04 negar | libre | En la biblioteca |  |
| CV13 | agradecer | «Gracias por esperar.» | B11 inclinarse para agradecer | espejo | En la biblioteca |  |
| CV14 | disculparse | «Disculpe las molestias.» | B11 inclinarse para agradecer | espejo | En la biblioteca | Más lento y con más sostenido que el agradecimiento. |
| CV15 | despedida | «Hasta luego, que tenga buen día.» | M20 saludar | acompana | En la biblioteca |  |
| CV16 | ceder el turno | «¿Necesita algo más?» | M24 ceder el turno | libre | En la biblioteca |  |
| CV17 | anunciar una lista | «Necesita tres cosas.» | M06 enumerar | prepara | En la biblioteca | El otro brazo va ya a la primera cosa de la lista. |
| CV18 | primero, segundo, tercero | «Primero… después… por último…» | M06 enumerar | libre | En la biblioteca | Una parada por elemento, repartidas en las frases. |
| CV19 | por un lado, por otro | «Por un lado es más rápido; por otro, más caro.» | B17 por un lado, por otro | contrapunto: B17 por un lado, por otro | En la biblioteca |  |
| CV20 | cambiar de tema | «Pasando a otra cosa…» | M13 desplazar hacia fuera | prepara | En la biblioteca |  |
| CV21 | resumir | «En resumen…» | B04 juntar | espejo | En la biblioteca |  |
| CV22 | recalcar | «Esto es importante.» | M21 pedir atención | libre | En la biblioteca |  |
| CV23 | énfasis de una palabra | «(cualquier palabra acentuada)» | M01 acento | acompana | Lo hacía ya |  |
| CV24 | tranquilizar | «No se preocupe, tiene tiempo.» | B13 calmar | espejo | En la biblioteca |  |
| CV25 | felicitar | «¡Enhorabuena, trámite completado!» | B10 celebrar | espejo | En la biblioteca |  |
| CV26 | corregirse | «Espere, lo corrijo.» | M22 esperar | libre | En la biblioteca |  |
| CV27 | invitar a mirar | «Fíjese en la pantalla.» | M09 atraer | ancla: D01 señalar un punto | En la biblioteca | Un brazo señala la imagen y el otro invita a acercarse. |
| CV28 | usted, su caso | «En su caso…» | D12 hacia quien escucha | libre | En la biblioteca |  |

### Cantidad y medida (23)

Cuánto, de qué tamaño, más o menos que.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| CA01 | mucho | «Hay muchas plazas libres.» | M26 mucho | acompana | En la biblioteca |  |
| CA02 | poco | «Quedan pocas.» | M25 un poco | libre | En la biblioteca |  |
| CA03 | todo | «Todo el barrio está incluido.» | B01 abarcar con los dos | espejo | Lo hacía ya |  |
| CA04 | ninguno | «No queda ninguna.» | M04 negar | libre | En la biblioteca |  |
| CA05 | la mitad | «La mitad del recorrido.» | B05 dividir en dos | espejo | En la biblioteca |  |
| CA06 | una parte y el resto | «Una parte es peatonal; el resto, no.» | M31 dos opciones | libre | En la biblioteca |  |
| CA07 | anchura | «Una acera así de ancha.» | B02 medir un tamaño | espejo | En la biblioteca |  |
| CA08 | altura | «Un edificio de esta altura.» | E16 marcar una altura | ancla: E16 marcar una altura | En la biblioteca | El otro brazo marca el suelo, a baja altura: la distancia entre los dos es la altura. |
| CA09 | aumentar | «El precio sube en verano.» | E08 subir | acompana | En la biblioteca |  |
| CA10 | disminuir | «La afluencia baja por la tarde.» | E09 bajar | acompana | En la biblioteca |  |
| CA11 | más que, menos que | «El tren tarda menos que el autobús.» | B06 balanza | contrapunto: B06 balanza | En la biblioteca |  |
| CA12 | igual | «Cuestan lo mismo.» | E16 marcar una altura | espejo | En la biblioteca | Los dos a la misma altura, quietos. |
| CA13 | aproximadamente | «Unos diez minutos.» | M27 más o menos | libre | En la biblioteca |  |
| CA14 | exactamente | «Justo a las nueve.» | E17 clavar un punto | libre | En la biblioteca |  |
| CA15 | número pequeño | «Dos paradas.» | M06 enumerar | libre | En la biblioteca | Tantas paradas como el número, hasta tres. |
| CA16 | número grande | «Más de doscientas.» | M26 mucho | acompana | En la biblioteca |  |
| CA17 | crecer | «La zona verde se ha ampliado.» | B03 expandir | espejo | En la biblioteca |  |
| CA18 | concentrarse | «Se concentra en dos calles.» | B04 juntar | espejo | En la biblioteca |  |
| CA19 | lleno | «El aparcamiento está completo.» | M16 cerrar la pinza | libre | En la biblioteca |  |
| CA20 | libre | «Hay sitio libre.» | M15 abrir la pinza | libre | En la biblioteca |  |
| CA21 | por tramos | «Hay tres tarifas.» | E12 escalones | libre | En la biblioteca |  |
| CA22 | se acumula | «Se suman los recargos.» | B18 capas | contrapunto: B18 capas | En la biblioteca |  |
| CA23 | máximo | «Como máximo, dos horas.» | M07 corte | ancla: E16 marcar una altura | En la biblioteca | El otro brazo marca el tope y el principal corta contra él. |

### Tiempo (21)

Cuándo, cuánto dura, en qué orden.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| TI01 | ahora | «Ahora mismo está abierto.» | D10 aquí mismo | libre | En la biblioteca |  |
| TI02 | antes | «Antes pasaba por aquí.» | M14 desplazar hacia dentro | libre | En la biblioteca |  |
| TI03 | después | «Después verá una rotonda.» | M13 desplazar hacia fuera | prepara | En la biblioteca |  |
| TI04 | duración | «Tarda unos veinte minutos.» | M12 reloj | libre | En la biblioteca |  |
| TI05 | hora de apertura | «Abre a las nueve.» | M15 abrir la pinza | contrapunto: M12 reloj | En la biblioteca | Un brazo marca el reloj y el otro abre. |
| TI06 | hora de cierre | «Cierra a las dos.» | M16 cerrar la pinza | contrapunto: M12 reloj | En la biblioteca |  |
| TI07 | plazo | «El plazo acaba el viernes.» | M13 desplazar hacia fuera → M07 corte | ancla: D10 aquí mismo | En la biblioteca | El otro brazo sostiene «hoy»; el principal se desplaza hasta la fecha y corta. |
| TI08 | cada cierto tiempo | «Pasa cada diez minutos.» | E20 puntear una serie | libre | En la biblioteca | Toques regulares. |
| TI09 | todo el día | «Funciona todo el día.» | E18 línea transversal | libre | En la biblioteca | Sin pausa, de extremo a extremo. |
| TI10 | nunca | «Los domingos no abre.» | M04 negar | libre | En la biblioteca |  |
| TI11 | enseguida | «Llega enseguida.» | M28 deprisa | libre | En la biblioteca |  |
| TI12 | retraso | «Lleva retraso.» | M29 despacio | contrapunto: M12 reloj | En la biblioteca |  |
| TI13 | urgente | «Es urgente.» | M28 deprisa | ancla: M21 pedir atención | En la biblioteca |  |
| TI14 | esperar | «Espere su turno.» | M22 esperar | libre | En la biblioteca |  |
| TI15 | por pasos | «El trámite tiene tres pasos.» | E12 escalones | prepara | En la biblioteca |  |
| TI16 | en marcha | «La solicitud está en trámite.» | B20 engranar | contrapunto: B20 engranar | En la biblioteca |  |
| TI17 | evolución | «El barrio ha ido cambiando con los años.» | E15 espiral ascendente | libre | En la biblioteca |  |
| TI18 | terminado | «Ya está resuelto.» | M16 cerrar la pinza | libre | En la biblioteca |  |
| TI19 | empezar | «Empiece por aquí.» | M10 empujar | libre | En la biblioteca |  |
| TI20 | provisional | «Es un desvío provisional.» | M27 más o menos | libre | En la biblioteca |  |
| TI21 | desde… hasta | «De lunes a viernes.» | M13 desplazar hacia fuera | ancla: M14 desplazar hacia dentro | En la biblioteca | Un brazo sostiene el principio y el otro lleva hasta el final. |

### Espacio y orientación (25)

Dónde está algo respecto a quien escucha o a otra cosa.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| ES01 | aquí | «Usted está aquí.» | D10 aquí mismo | libre | En la biblioteca | Con mapa en pantalla, mejor IM17. |
| ES02 | allí | «Está allí.» | D11 allí, lejos | libre | En la biblioteca |  |
| ES03 | a la izquierda | «A su izquierda.» | D06 indicar hacia un lado | libre | En la biblioteca | Brazo izquierdo. |
| ES04 | a la derecha | «A su derecha.» | D06 indicar hacia un lado | libre | En la biblioteca | Brazo derecho. |
| ES05 | enfrente | «Justo enfrente.» | D07 indicar al frente | libre | En la biblioteca |  |
| ES06 | arriba | «En la planta de arriba.» | D08 indicar arriba | libre | En la biblioteca |  |
| ES07 | abajo | «En el sótano.» | D09 indicar abajo | libre | En la biblioteca |  |
| ES08 | cerca | «Está muy cerca.» | M25 un poco | libre | En la biblioteca |  |
| ES09 | lejos | «Queda lejos.» | D11 allí, lejos | libre | En la biblioteca |  |
| ES10 | entre | «Entre el banco y la farmacia.» | B02 medir un tamaño | espejo | En la biblioteca | Con mapa en pantalla, mejor IM08. |
| ES11 | alrededor | «Alrededor de la plaza.» | E07 rotonda | libre | En la biblioteca |  |
| ES12 | dentro | «Dentro del recinto.» | B19 rodear | espejo | En la biblioteca |  |
| ES13 | fuera | «Fuera del casco urbano.» | M08 apartar | libre | En la biblioteca |  |
| ES14 | junto a | «Junto a la estación.» | E17 clavar un punto | ancla: E17 clavar un punto | En la biblioteca | El otro brazo clava la referencia; el principal, lo que está al lado. |
| ES15 | a lo largo de | «A lo largo del paseo.» | E18 línea transversal | acompana | En la biblioteca |  |
| ES16 | al otro lado | «Al otro lado de la plaza.» | E13 arco de un lado a otro | libre | En la biblioteca |  |
| ES17 | en el centro | «En el centro del pueblo.» | B04 juntar | espejo | En la biblioteca |  |
| ES18 | en la esquina | «En la esquina.» | E05 girar hacia fuera | libre | En la biblioteca | Versión corta: el giro, sin el tramo recto. |
| ES19 | límite | «Hasta el límite municipal.» | E18 línea transversal → M07 corte | libre | En la biblioteca |  |
| ES20 | al fondo | «Al fondo del pasillo.» | D11 allí, lejos | libre | En la biblioteca |  |
| ES21 | detrás | «Detrás del edificio.» | E13 arco de un lado a otro | libre | En la biblioteca | El arco pasa por encima y cae al otro lado. Los brazos no pueden señalar hacia atrás. |
| ES22 | delante | «Delante de la entrada.» | D07 indicar al frente | libre | En la biblioteca |  |
| ES23 | un punto del mapa | «La oficina está aquí.» | D01 señalar un punto | prepara | Lo hacía ya |  |
| ES24 | una zona del mapa | «Todo este barrio.» | D04 rodear una zona | acompana | Con el motor actual (sin conectar) |  |
| ES25 | desde aquí hasta allí | «Desde la estación hasta el museo.» | B16 origen y trayecto | contrapunto: B16 origen y trayecto | Con el motor actual (sin conectar) |  |

### Direcciones por la calle (25)

Cómo llegar: tramos, giros, cruces, destino.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| DI01 | siga recto | «Siga recto por esta calle.» | E04 avanzar recto | prepara | En la biblioteca | El otro brazo va ya a la postura del giro siguiente. |
| DI02 | gire a la izquierda | «Gire a la izquierda.» | E05 girar hacia fuera | libre | En la biblioteca | Brazo izquierdo. |
| DI03 | gire a la derecha | «Gire a la derecha.» | E05 girar hacia fuera | libre | En la biblioteca | Brazo derecho. |
| DI04 | la segunda calle | «La segunda a la derecha.» | M06 enumerar → E05 girar hacia fuera | libre | En la biblioteca | Tantas paradas como el ordinal y, sin volver a reposo, el giro. |
| DI05 | rotonda y salida | «En la rotonda, la tercera salida.» | E07 rotonda | contrapunto: M06 enumerar | En la biblioteca | Un brazo dibuja la rotonda; el otro cuenta las salidas. |
| DI06 | cruzar la calle | «Cruce al otro lado.» | E13 arco de un lado a otro | libre | En la biblioteca |  |
| DI07 | cruzar un puente | «Pase el puente.» | E13 arco de un lado a otro | contrapunto: E10 ondular | En la biblioteca | El otro brazo es el río, por debajo. |
| DI08 | intersección | «En el cruce.» | B08 cruce | contrapunto: B08 cruce | En la biblioteca |  |
| DI09 | subir | «Suba la cuesta.» | E08 subir | libre | En la biblioteca |  |
| DI10 | bajar | «Baje hasta el río.» | E09 bajar | libre | En la biblioteca |  |
| DI11 | hasta el final | «Hasta el final de la avenida.» | E04 avanzar recto → M07 corte | libre | En la biblioteca |  |
| DI12 | media vuelta | «Dé media vuelta.» | E14 ida y vuelta | libre | En la biblioteca |  |
| DI13 | a pocos metros | «A cincuenta metros.» | M25 un poco | libre | En la biblioteca |  |
| DI14 | bastante más adelante | «Un kilómetro más adelante.» | D11 allí, lejos | libre | En la biblioteca |  |
| DI15 | el destino | «Ha llegado: es ahí.» | E17 clavar un punto | libre | En la biblioteca | Con mapa en pantalla, D01. |
| DI16 | pasar de largo | «Deje atrás la gasolinera.» | M13 desplazar hacia fuera | libre | En la biblioteca |  |
| DI17 | la ruta en el mapa | «El camino es este.» | B16 origen y trayecto | contrapunto: B16 origen y trayecto | Con el motor actual (sin conectar) |  |
| DI18 | atajo | «Hay un atajo por el parque.» | E13 arco de un lado a otro | libre | En la biblioteca | Arco bajo y rápido. |
| DI19 | callejuelas | «Por las calles del casco antiguo.» | E11 zigzag | libre | En la biblioteca |  |
| DI20 | la paralela | «Vaya por la calle paralela.» | B07 paralelas | espejo | En la biblioteca |  |
| DI21 | a un lado verá | «A su derecha verá la catedral.» | D06 indicar hacia un lado | prepara | En la biblioteca | Brazo del lado nombrado. |
| DI22 | plantas | «Suba a la segunda planta.» | E12 escalones | libre | En la biblioteca | Tantos escalones como plantas. |
| DI23 | entrada y salida | «La entrada está por aquí; la salida, por allí.» | B17 por un lado, por otro | contrapunto: B17 por un lado, por otro | En la biblioteca |  |
| DI24 | recto y giro al otro lado | «Recto y, al final, hacia el otro lado.» | E04 avanzar recto → E06 girar hacia dentro | libre | En la biblioteca | Cuando el giro cae del lado contrario al brazo que avanza y el otro está ocupado. |
| DI25 | sentido obligatorio | «Solo se puede ir en este sentido.» | E04 avanzar recto | contrapunto: M03 alto | En la biblioteca | Un brazo avanza; el otro cierra el sentido contrario. |

### Entorno urbano (21)

Lo que hay en una ciudad y cómo es.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| UR01 | calle | «Esta calle.» | E03 línea recta | libre | Lo hacía ya |  |
| UR02 | avenida | «Una avenida de cuatro carriles.» | B07 paralelas | espejo | En la biblioteca |  |
| UR03 | plaza | «La plaza mayor.» | E19 superficie llana | acompana | En la biblioteca |  |
| UR04 | torre | «La torre del ayuntamiento.» | E08 subir | ancla: E16 marcar una altura | En la biblioteca | El otro brazo marca la base. |
| UR05 | barrio | «El barrio de pescadores.» | D04 rodear una zona | acompana | Con el motor actual (sin conectar) |  |
| UR06 | casco antiguo | «El casco histórico.» | B19 rodear | espejo | En la biblioteca |  |
| UR07 | puente | «El puente de piedra.» | E13 arco de un lado a otro | contrapunto: E10 ondular | En la biblioteca |  |
| UR08 | río o canal | «El canal atraviesa el centro.» | E10 ondular | libre | En la biblioteca |  |
| UR09 | parque | «El parque central.» | E19 superficie llana | contrapunto: E08 subir | En la biblioteca | Un brazo es el suelo; el otro, los árboles. |
| UR10 | parada | «La parada de autobús.» | E17 clavar un punto | libre | En la biblioteca |  |
| UR11 | aparcamiento | «El aparcamiento público.» | E19 superficie llana | contrapunto: E20 puntear una serie | En la biblioteca | Un brazo es la explanada; el otro puntea las plazas. |
| UR12 | monumento | «El monumento de la plaza.» | D01 señalar un punto | acompana | Lo hacía ya |  |
| UR13 | zona comercial | «La zona de tiendas.» | D02 barrer una región | acompana | Lo hacía ya |  |
| UR14 | zona peatonal | «Esta zona es peatonal.» | E19 superficie llana | contrapunto: M03 alto | En la biblioteca | Un brazo muestra la zona; el otro para a los coches. |
| UR15 | carril bici | «El carril bici.» | E04 avanzar recto | ancla: M25 un poco | En la biblioteca | El otro brazo dice «estrecho». |
| UR16 | obras | «Hay obras en esta calle.» | M03 alto | ancla: D01 señalar un punto | En la biblioteca | Un brazo señala dónde; el otro avisa. |
| UR17 | muralla | «La muralla rodea el centro.» | E18 línea transversal | ancla: E16 marcar una altura | En la biblioteca |  |
| UR18 | paso subterráneo | «Por el paso subterráneo.» | E09 bajar → E04 avanzar recto | libre | En la biblioteca |  |
| UR19 | mirador | «Desde el mirador se ve toda la ciudad.» | B01 abarcar con los dos | espejo | Lo hacía ya |  |
| UR20 | perfil de la ciudad | «Edificios altos y bajos.» | E10 ondular | libre | En la biblioteca | Sube y baja como la línea de los tejados. |
| UR21 | del centro a las afueras | «Del centro hacia las afueras.» | B03 expandir | espejo | En la biblioteca |  |

### Entorno rural (22)

Paisaje, relieve, tiempo atmosférico.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| RU01 | campo | «Los campos de cereal.» | E01 abanico horizontal | acompana | Lo hacía ya |  |
| RU02 | horizonte | «Hasta donde alcanza la vista.» | E02 abanico elevado | acompana | Lo hacía ya |  |
| RU03 | montaña | «La sierra, al norte.» | E13 arco de un lado a otro | libre | En la biblioteca | El arco alto es el perfil de la montaña. |
| RU04 | cordillera | «Una cadena de montañas.» | E10 ondular | libre | En la biblioteca | Ondas altas. |
| RU05 | valle | «El pueblo está en el valle.» | E09 bajar | espejo | En la biblioteca | Los dos bajan hacia el centro: las dos laderas. |
| RU06 | colinas | «Colinas suaves.» | E10 ondular | libre | En la biblioteca | Lento. |
| RU07 | río | «El río baja hacia el sur.» | E10 ondular | libre | En la biblioteca | Con mapa en pantalla, D03 sobre su cauce. |
| RU08 | sendero en zigzag | «El sendero sube en zigzag.» | E11 zigzag | libre | En la biblioteca |  |
| RU09 | camino | «El camino del molino.» | E03 línea recta | libre | Lo hacía ya |  |
| RU10 | bosque | «Un bosque de pinos.» | E20 puntear una serie | espejo | En la biblioteca | Toques altos: los troncos. |
| RU11 | cultivos en hileras | «Viñedos en hileras.» | B07 paralelas | espejo | En la biblioteca |  |
| RU12 | pueblo | «Un pueblo pequeño.» | B04 juntar | espejo | En la biblioteca |  |
| RU13 | casas dispersas | «Casas dispersas por la ladera.» | B03 expandir | espejo | En la biblioteca |  |
| RU14 | cielo despejado | «Cielo despejado.» | E02 abanico elevado | acompana | Lo hacía ya |  |
| RU15 | lluvia | «Se esperan lluvias.» | E09 bajar | espejo | En la biblioteca | Dos bajadas cortas con las pinzas abiertas. |
| RU16 | viento | «Sopla viento fuerte.» | E14 ida y vuelta | libre | En la biblioteca | Rápido. |
| RU17 | sol | «Mucho sol a mediodía.» | D08 indicar arriba → M15 abrir la pinza | libre | En la biblioteca |  |
| RU18 | desnivel | «Un desnivel fuerte.» | E08 subir | ancla: E16 marcar una altura | En la biblioteca |  |
| RU19 | embalse | «El embalse.» | E07 rotonda | libre | En la biblioteca | Círculo bajo y lento. |
| RU20 | costa | «La línea de costa.» | E18 línea transversal | contrapunto: E10 ondular | En la biblioteca | Un brazo es la orilla; el otro, las olas. |
| RU21 | ruta de senderismo | «La ruta sale del pueblo y sube al collado.» | B16 origen y trayecto | contrapunto: B16 origen y trayecto | Con el motor actual (sin conectar) |  |
| RU22 | distancia entre pueblos | «Están a diez kilómetros.» | B02 medir un tamaño | espejo | En la biblioteca |  |

### Información vial y transporte (28)

Estado del tráfico, normas, transporte público.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| VI01 | tráfico fluido | «Circulación fluida.» | B07 paralelas | espejo | En la biblioteca |  |
| VI02 | tráfico denso | «Tráfico denso.» | M29 despacio | espejo | En la biblioteca |  |
| VI03 | retención | «Hay dos kilómetros de retención.» | B04 juntar | espejo | En la biblioteca | Lento, y sostenido al final. |
| VI04 | carretera cortada | «La carretera está cortada.» | B14 barrera | espejo | En la biblioteca |  |
| VI05 | carril cerrado | «Hay un carril cerrado.» | E04 avanzar recto | contrapunto: M03 alto | En la biblioteca |  |
| VI06 | desvío | «Tome el desvío señalizado.» | E13 arco de un lado a otro | ancla: M03 alto | En la biblioteca | El otro brazo es el obstáculo; el principal lo rodea. |
| VI07 | obras en la calzada | «Obras en el kilómetro doce.» | M03 alto | ancla: D01 señalar un punto | En la biblioteca |  |
| VI08 | accidente | «Accidente más adelante.» | M21 pedir atención | contrapunto: D11 allí, lejos | En la biblioteca |  |
| VI09 | peligro | «Precaución, firme deslizante.» | M21 pedir atención | espejo | En la biblioteca |  |
| VI10 | reducir la velocidad | «Modere la velocidad.» | B13 calmar | espejo | En la biblioteca |  |
| VI11 | límite de velocidad | «Limitado a treinta.» | M07 corte | ancla: E16 marcar una altura | En la biblioteca |  |
| VI12 | prohibido el paso | «Prohibido el paso.» | M03 alto | libre | En la biblioteca |  |
| VI13 | sentido único | «Calle de sentido único.» | E04 avanzar recto | contrapunto: M03 alto | En la biblioteca |  |
| VI14 | ceder el paso | «Ceda el paso.» | M22 esperar | libre | En la biblioteca |  |
| VI15 | semáforo | «Espere al semáforo.» | M16 cerrar la pinza → M15 abrir la pinza | libre | En la biblioteca | Cierra y abre: rojo y verde. |
| VI16 | peaje | «Ese tramo es de peaje.» | M19 entregar | libre | En la biblioteca |  |
| VI17 | aparcamiento libre | «Hay plazas libres.» | M15 abrir la pinza | libre | En la biblioteca |  |
| VI18 | aparcamiento completo | «Está completo.» | M16 cerrar la pinza | libre | En la biblioteca |  |
| VI19 | tiempo limitado | «Máximo dos horas.» | M12 reloj → M07 corte | libre | En la biblioteca |  |
| VI20 | frecuencia de paso | «Un autobús cada quince minutos.» | E20 puntear una serie | contrapunto: M12 reloj | En la biblioteca |  |
| VI21 | paradas de la línea | «Para en Mercado, Catedral y Estación.» | E20 puntear una serie | libre | En la biblioteca | Con mapa en pantalla, D05 sobre las paradas. |
| VI22 | transbordo | «Cambie a la línea 3.» | E13 arco de un lado a otro | libre | En la biblioteca |  |
| VI23 | retraso | «Circula con veinte minutos de retraso.» | M29 despacio | contrapunto: M12 reloj | En la biblioteca |  |
| VI24 | hora punta | «En hora punta se llena.» | B04 juntar | espejo | En la biblioteca |  |
| VI25 | ruta alternativa | «Mejor por la circunvalación.» | E13 arco de un lado a otro | contrapunto: M04 negar | En la biblioteca | Un brazo niega el camino habitual; el otro dibuja el rodeo. |
| VI26 | dirección | «Dirección centro.» | D07 indicar al frente | libre | En la biblioteca |  |
| VI27 | distancia restante | «Faltan tres kilómetros.» | B02 medir un tamaño | espejo | En la biblioteca |  |
| VI28 | a pie | «A pie son diez minutos.» | E20 puntear una serie | libre | En la biblioteca | Toques cortos: los pasos. |

### Servicios públicos y atención al ciudadano (36)

Trámites, horarios, requisitos, avisos.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| SP01 | horario de atención | «La oficina atiende de nueve a dos.» | M12 reloj | ancla: M15 abrir la pinza | En la biblioteca |  |
| SP02 | cerrado | «Hoy está cerrado.» | M16 cerrar la pinza | libre | En la biblioteca |  |
| SP03 | cita previa | «Necesita cita previa.» | E17 clavar un punto | contrapunto: M12 reloj | En la biblioteca | Un brazo es el reloj; el otro fija la cita. |
| SP04 | documentación necesaria | «Traiga el DNI, el justificante y el formulario.» | M06 enumerar | prepara | En la biblioteca |  |
| SP05 | formulario | «Rellene la solicitud.» | M18 escribir | ancla: M02 ofrecer | En la biblioteca | El otro brazo ofrece el «papel»; el principal escribe. |
| SP06 | firma | «Firme aquí.» | M18 escribir | libre | En la biblioteca | Corto. |
| SP07 | tasa | «La tasa es de doce euros.» | M19 entregar | libre | En la biblioteca |  |
| SP08 | gratuito | «Es gratuito.» | M02 ofrecer | libre | En la biblioteca | Se ofrece sin cerrar la pinza: no hay entrega. |
| SP09 | ventanilla | «Diríjase a la ventanilla tres.» | D06 indicar hacia un lado | contrapunto: M06 enumerar | En la biblioteca | Un brazo indica el lado; el otro, el número. |
| SP10 | turno | «Espere a que salga su número.» | M22 esperar | libre | En la biblioteca |  |
| SP11 | plazo de presentación | «Tiene diez días para presentarlo.» | M12 reloj → M07 corte | libre | En la biblioteca |  |
| SP12 | teléfono | «Llame al 010.» | M17 hablar con la pinza | libre | En la biblioteca |  |
| SP13 | por internet | «Puede hacerlo en la sede electrónica.» | D01 señalar un punto | contrapunto: M18 escribir | En la biblioteca | Un brazo señala la pantalla; el otro «teclea». |
| SP14 | obligatorio | «Es obligatorio.» | M30 golpe firme | libre | En la biblioteca |  |
| SP15 | opcional | «Es opcional.» | M27 más o menos | libre | En la biblioteca |  |
| SP16 | aprobado | «Su solicitud está aprobada.» | M05 afirmar | acompana | En la biblioteca |  |
| SP17 | denegado | «Ha sido denegada.» | M04 negar | libre | En la biblioteca |  |
| SP18 | reclamación | «Puede presentar una reclamación.» | M10 empujar | libre | En la biblioteca |  |
| SP19 | entregar | «Entréguelo en el registro.» | M19 entregar | libre | En la biblioteca |  |
| SP20 | recoger | «Puede recogerlo mañana.» | M09 atraer | libre | En la biblioteca |  |
| SP21 | ayuda | «Le podemos ayudar con el trámite.» | M02 ofrecer | espejo | En la biblioteca |  |
| SP22 | emergencia | «En caso de emergencia llame al 112.» | M21 pedir atención | contrapunto: M17 hablar con la pinza | En la biblioteca |  |
| SP23 | centro de salud | «El centro de salud más cercano.» | D01 señalar un punto | acompana | Lo hacía ya |  |
| SP24 | zona vigilada | «Es una zona vigilada.» | B19 rodear | espejo | En la biblioteca |  |
| SP25 | entrada accesible | «La entrada es accesible.» | E19 superficie llana | libre | En la biblioteca | Llano y lento. |
| SP26 | para todos | «Es para todos los vecinos.» | B01 abarcar con los dos | espejo | Lo hacía ya |  |
| SP27 | empadronamiento | «Para empadronarse.» | M18 escribir → E17 clavar un punto | libre | En la biblioteca |  |
| SP28 | reciclaje | «Separe el vidrio y el papel.» | B05 dividir en dos | espejo | En la biblioteca |  |
| SP29 | recogida | «La recogida es los martes.» | M09 atraer | contrapunto: M12 reloj | En la biblioteca |  |
| SP30 | corte de suministro | «Corte de agua de ocho a doce.» | M07 corte | contrapunto: M12 reloj | En la biblioteca |  |
| SP31 | ayuda económica | «Hay una ayuda disponible.» | M02 ofrecer | libre | En la biblioteca |  |
| SP32 | no permitido | «No está permitido.» | M03 alto | libre | En la biblioteca |  |
| SP33 | permitido | «Sí está permitido.» | M05 afirmar | libre | En la biblioteca |  |
| SP34 | otra oficina | «Eso lo lleva otra oficina.» | D06 indicar hacia un lado | libre | En la biblioteca | Brazo del lado hacia el que queda. |
| SP35 | comprender una queja | «Entiendo la molestia.» | M23 escuchar | espejo | En la biblioteca |  |
| SP36 | solo el titular | «Solo puede hacerlo el titular.» | D12 hacia quien escucha → E17 clavar un punto | libre | En la biblioteca |  |

### Imágenes y mapas (19)

Describir la imagen o el mapa que se muestra.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| IM01 | un elemento | «Este es el campanario.» | D01 señalar un punto | acompana | Lo hacía ya |  |
| IM02 | una zona | «Toda esta parte es el mercado.» | D02 barrer una región | acompana | Lo hacía ya |  |
| IM03 | el conjunto | «La imagen muestra toda la bahía.» | B01 abarcar con los dos | espejo | Lo hacía ya |  |
| IM04 | el cielo | «Arriba, el cielo.» | E02 abanico elevado | acompana | Lo hacía ya |  |
| IM05 | el paisaje | «Un paisaje abierto.» | E01 abanico horizontal | acompana | Lo hacía ya |  |
| IM06 | un camino | «El camino cruza la imagen.» | E03 línea recta | acompana | Lo hacía ya |  |
| IM07 | el contorno | «El recinto es este.» | D04 rodear una zona | acompana | Con el motor actual (sin conectar) |  |
| IM08 | dos elementos a la vez | «El árbol y la casa.» | B15 enmarcar | espejo | Con el motor actual (sin conectar) |  |
| IM09 | de un elemento a otro | «Del sol a la casa.» | D05 saltar entre puntos | libre | Con el motor actual (sin conectar) |  |
| IM10 | contraste | «Luz arriba, sombra abajo.» | B06 balanza | contrapunto: B06 balanza | En la biblioteca |  |
| IM11 | un detalle | «Un detalle: la veleta.» | D01 señalar un punto | ancla: M25 un poco | En la biblioteca | El otro brazo dice «pequeño». |
| IM12 | primer plano y fondo | «En primer plano, el puente; al fondo, la sierra.» | D02 barrer una región | prepara | Lo hacía ya | El principal barre abajo; el otro va ya arriba para la segunda parte. |
| IM13 | simetría | «Una composición simétrica.» | B03 expandir | espejo | En la biblioteca |  |
| IM14 | recorrido de la mirada | «La vista va de aquí hacia allí.» | D03 trazar una ruta | libre | Con el motor actual (sin conectar) |  |
| IM15 | escala del mapa | «Esto son quinientos metros.» | B15 enmarcar | espejo | Con el motor actual (sin conectar) |  |
| IM16 | símbolos del mapa | «Los puntos azules son fuentes.» | D05 saltar entre puntos | libre | Con el motor actual (sin conectar) |  |
| IM17 | usted está aquí | «Usted está aquí.» | D01 señalar un punto | contrapunto: D12 hacia quien escucha | En la biblioteca | Un brazo señala el mapa; el otro, a la persona. |
| IM18 | origen y destino | «De la estación al museo.» | B16 origen y trayecto | contrapunto: B16 origen y trayecto | Con el motor actual (sin conectar) |  |
| IM19 | zona de servicio | «Da servicio a toda esta zona.» | D04 rodear una zona | acompana | Con el motor actual (sin conectar) |  |

### Cualidades y estados (25)

Cómo es o cómo está algo.

| Id | Concepto | Ejemplo | Brazo principal | El otro brazo | Estado | Notas |
|---|---|---|---|---|---|---|
| CU01 | seguro | «Es una zona segura.» | B19 rodear | espejo | En la biblioteca |  |
| CU02 | peligroso | «Es un cruce peligroso.» | M21 pedir atención | libre | En la biblioteca |  |
| CU03 | fácil | «Es muy sencillo.» | M02 ofrecer | libre | En la biblioteca | Suave. |
| CU04 | largo | «Es un trámite largo.» | D11 allí, lejos | libre | En la biblioteca | Lento. |
| CU05 | nuevo | «Es un servicio nuevo.» | M15 abrir la pinza | libre | En la biblioteca |  |
| CU06 | rápido | «Es rápido.» | M28 deprisa | libre | En la biblioteca |  |
| CU07 | lento | «Va despacio.» | M29 despacio | libre | En la biblioteca |  |
| CU08 | tranquilo | «Es una calle tranquila.» | B13 calmar | espejo | En la biblioteca |  |
| CU09 | concurrido | «Suele estar lleno de gente.» | B04 juntar | espejo | En la biblioteca |  |
| CU10 | grande | «Es un recinto grande.» | B03 expandir | espejo | En la biblioteca |  |
| CU11 | pequeño | «Es una plaza pequeña.» | M25 un poco | libre | En la biblioteca |  |
| CU12 | alto | «Es un edificio alto.» | E16 marcar una altura | libre | En la biblioteca |  |
| CU13 | bajo | «El muro es bajo.» | E16 marcar una altura | libre | En la biblioteca | A baja altura. |
| CU14 | ancho | «La calle es ancha.» | B02 medir un tamaño | espejo | En la biblioteca |  |
| CU15 | estrecho | «El paso es estrecho.» | B02 medir un tamaño | espejo | En la biblioteca | Las pinzas, lo más juntas que permite la distancia mínima entre brazos. |
| CU16 | recto | «El tramo es recto.» | E04 avanzar recto | libre | En la biblioteca |  |
| CU17 | sinuoso | «La carretera es sinuosa.» | E11 zigzag | libre | En la biblioteca |  |
| CU18 | llano | «El terreno es llano.» | E19 superficie llana | libre | En la biblioteca |  |
| CU19 | empinado | «La calle es empinada.» | E08 subir | libre | En la biblioteca |  |
| CU20 | fijo | «El horario es fijo.» | E17 clavar un punto | libre | En la biblioteca |  |
| CU21 | variable | «El precio varía.» | M27 más o menos | libre | En la biblioteca |  |
| CU22 | restringido | «El acceso es restringido.» | M03 alto | libre | En la biblioteca |  |
| CU23 | unido | «Los dos barrios están unidos.» | B04 juntar | espejo | En la biblioteca |  |
| CU24 | separado | «Están en edificios distintos.» | B05 dividir en dos | espejo | En la biblioteca |  |
| CU25 | distinto | «Son trámites distintos.» | B06 balanza | contrapunto: B06 balanza | En la biblioteca |  |

## Instrucciones para una política entrenada

Si algún día se graban demostraciones para ajustar una política (SmolVLA u otra), esta es la frase de tarea de cada movimiento. `{brazo}` es `left` o `right`.

| Id | Instrucción |
|---|---|
| D01 | point with the {brazo} arm at the given spot of the picture and hold |
| D02 | sweep the {brazo} arm across the given region of the picture |
| D03 | trace with the {brazo} arm the route through the given picture points |
| D04 | outline with the {brazo} arm the given area of the picture |
| D05 | point with the {brazo} arm at each given picture spot in turn, pausing on each |
| D06 | extend the {brazo} arm out to its side and hold |
| D07 | extend the {brazo} arm straight ahead and hold |
| D08 | raise the {brazo} arm pointing up and hold |
| D09 | lower the {brazo} arm pointing down and hold |
| D10 | tap twice downwards close in front with the {brazo} arm |
| D11 | reach far and slightly up with the {brazo} arm and hold |
| D12 | open the gripper and present the {brazo} arm towards the listener |
| D13 | draw the {brazo} gripper back towards the robot body and hold |
| E01 | sweep the {brazo} arm in a wide horizontal arc |
| E02 | sweep the {brazo} arm in a wide raised arc |
| E03 | draw a short straight line with the {brazo} arm |
| E04 | move the {brazo} arm straight forward from near to far |
| E05 | move the {brazo} arm forward and then turn outwards |
| E06 | move the {brazo} arm forward and then turn inwards |
| E07 | draw a horizontal circle with the {brazo} arm |
| E08 | raise the {brazo} arm in a vertical line |
| E09 | lower the {brazo} arm in a vertical line |
| E10 | move the {brazo} arm sideways in a wave |
| E11 | move the {brazo} arm sideways in a zigzag |
| E12 | raise the {brazo} arm in three steps |
| E13 | draw an arch with the {brazo} arm from one side over to the other |
| E14 | move the {brazo} arm across and back |
| E15 | draw a rising spiral with the {brazo} arm |
| E16 | hold the {brazo} open gripper level at a given height |
| E17 | bring the {brazo} arm down onto a spot with a short firm stroke |
| E18 | draw a line across from inside to outside with the {brazo} arm |
| E19 | glide the {brazo} open gripper low and flat from inside to outside |
| E20 | tap three spots in a row with the {brazo} arm |
| B01 | sweep both arms outwards in a wide mirrored arc |
| B02 | bring both grippers inwards facing each other and hold them apart |
| B03 | move both arms from the centre outwards while opening the grippers |
| B04 | move both arms from outside in to the centre while closing the grippers |
| B05 | bring both arms down at the centre and then apart |
| B06 | raise one arm while lowering the other, swap, then level them |
| B07 | move both arms forward together in parallel lines |
| B08 | move one arm straight forward while the other draws a line across above it |
| B09 | open both arms outwards low with open grippers |
| B10 | raise both arms up and out in a V |
| B11 | dip both grippers forward and down briefly |
| B12 | lift both arms slightly outwards with open grippers |
| B13 | lower both open grippers slowly, twice |
| B14 | hold both arms forward and high with open grippers |
| B15 | point each arm at one end of the given picture area and hold both |
| B16 | hold one arm on the start point while the other traces the route |
| B17 | present with one arm to its side, return, then do the same with the other arm |
| B18 | hold both grippers at different heights, then lift the lower one above the other |
| B19 | close both arms in an arc from outside round to the centre |
| B20 | draw circles with both arms half a turn out of phase |
| M01 | give a short beat with the {brazo} arm close to the body |
| M02 | present the {brazo} open gripper turned upwards, low and forward, and hold |
| M03 | hold the {brazo} arm forward and up with the gripper open |
| M04 | wag the {brazo} arm side to side twice |
| M05 | nod the {brazo} gripper down twice |
| M06 | stop the {brazo} arm at three positions moving sideways, opening the gripper a third more at each |
| M07 | chop the {brazo} arm straight down with the gripper on edge |
| M08 | flick the {brazo} arm from the centre outwards while opening the gripper |
| M09 | pull the {brazo} arm from far back towards the body while closing the gripper |
| M10 | push the {brazo} arm forward from the body with the gripper open |
| M11 | draw a small circle close to the body with the {brazo} arm |
| M12 | draw a vertical circle with the {brazo} arm |
| M13 | slide the {brazo} arm from the front outwards and hold |
| M14 | slide the {brazo} arm from the front inwards and hold |
| M15 | open the {brazo} gripper fully in front and hold |
| M16 | close the {brazo} gripper fully in front and hold |
| M17 | open and close the {brazo} gripper twice held up |
| M18 | make a small low scribble with the {brazo} gripper |
| M19 | present the {brazo} open gripper and close it while moving forward |
| M20 | wave the raised {brazo} arm side to side |
| M21 | raise the {brazo} arm high with the gripper open and hold |
| M22 | hold the {brazo} open gripper forward at mid height |
| M23 | lean the {brazo} arm slightly towards the listener and stay |
| M24 | present the {brazo} open gripper towards the listener and hold |
| M25 | raise the {brazo} gripper and close it to a small gap |
| M26 | sweep the {brazo} arm from low inside to high outside while opening the gripper |
| M27 | rock the {brazo} wrist left, right and left |
| M28 | jab the {brazo} arm forward twice quickly |
| M29 | glide the {brazo} open gripper slowly from inside to outside |
| M30 | bring the {brazo} closed gripper down firmly |
| M31 | present the {brazo} open gripper to one side and then to the other |
