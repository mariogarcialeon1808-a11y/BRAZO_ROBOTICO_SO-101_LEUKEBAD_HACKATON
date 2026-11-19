# Protocolo expresivo: cómo conversa el robot con el cuerpo

Reglas para una conversación completa en la que el robot da la información y la expresa con
los dos brazos. El vocabulario de movimientos y las conexiones concepto → movimiento están en
[REGISTRO_EXPRESIVO.md](REGISTRO_EXPRESIVO.md) (84 movimientos, 273 conexiones).

**Estado (16-11-2026):** la biblioteca está en el programa. Cada frase lleva dos conceptos, uno
por brazo y cada uno en su palabra, y uno de los dos tiene que ser gráfico. Probado en
simulación y con la IA real; la primera versión se probó en los brazos, esta última no. Lo que el protocolo pide y el programa
aún no hace está en [Qué hace ya el programa y qué falta](#qué-hace-ya-el-programa-y-qué-falta).

## El problema

Hasta ahora la IA solo podía pedir cinco gestos: señalar un punto, barrer una región, abanico
horizontal, abanico elevado y línea recta. Cuatro de los cinco sirven para describir un cuadro.
Para decir «gire a la derecha», «cierra a las dos», «es obligatorio» o «hay retención» no había
nada, y el robot acababa señalando o moviendo los brazos sin decir nada con ellos. Además el
brazo que no hacía el gesto solo acompañaba: nunca aportaba significado.

## Lo que el cuerpo puede decir

Un SO-101 tiene cinco articulaciones y una pinza, sin dedos. Estos son sus canales:

| Canal | Qué expresa |
|---|---|
| Dónde está la pinza | Lugar, altura, distancia: arriba es más, cerca es propio, lejos es ajeno |
| Qué dibuja al moverse | Forma y trayecto: recta, giro, arco, círculo, onda, escalones |
| Hacia dónde apunta | Dirección y referencia: esto, allí, usted |
| Apertura de la pinza | Abierto o cerrado, mucho o poco, dar o guardar, hablar |
| Giro de la muñeca | Ofrecer (pinza hacia arriba), cortar (de canto), dudar (vaivén) |
| Ritmo | Deprisa, despacio, firme, repetido, sostenido |
| Relación entre los dos brazos | Tamaño, unión, reparto, comparación, origen y destino |
| Quietud | Escuchar, esperar, dejar que se mire lo señalado |

## Reglas

### Principios

- **R1. La palabra manda.** Cada gesto con significado va ligado a una palabra de la frase, su
  ancla. Sin palabra que lo pida, no hay gesto con significado.
- **R2. El cuerpo añade.** Se gesticula lo que la voz deja menos claro: dónde, hacia dónde,
  cuánto, en qué orden, con qué permiso. No se ilustra cada sustantivo.
- **R3. Un significado por brazo y momento.** Un brazo no mezcla dos gestos con significado.
- **R4. No se inventan referentes.** En la imagen solo se señala lo que la IA ve en ella. Lo que
  no está en la imagen se dibuja en el aire o se expresa con un gesto de discurso.
- **R5. Señalar no es el gesto por defecto.** Se señala cuando hay algo concreto en la imagen y
  importa cuál es. Para todo lo demás hay 77 movimientos que no señalan.
- **R6. Todo sale del registro.** Si un concepto no tiene conexión, la frase lleva acento y el
  concepto se apunta para añadirlo. El robot no improvisa movimientos.

### Capas

- **R7. Cuatro capas, de menos a más prioridad:** postura (reposo o escucha), ritmo (acentos),
  significado (un movimiento del registro) y referencia (señalar la imagen). La de más
  prioridad ocupa el brazo; las de menos se retiran sin terminar a medias: acaban su recorrido.
- **R8. Escuchando no se gesticula.** Mientras habla la persona, los dos brazos están en la
  postura de escucha (M23), quietos. Ni acentos ni preparación.
- **R9. El ritmo rellena, no estorba.** Un acento no empieza si con él el gesto siguiente no
  llegaría a tiempo a su palabra.
- **R10. La manera de moverse también significa.** Cualquier movimiento se puede hacer lento
  (calma, dificultad, cuidado), rápido (urgencia, facilidad), firme (norma), repetido
  (frecuencia, insistencia) o sostenido (importancia, espera). El registro lo indica en «Notas».

### Fases de un gesto

- **R11. Preparación, ápice, sostenido y salida.** La preparación lleva el brazo a la primera
  postura; el ápice es el momento que significa; el sostenido lo deja ver; la salida va al
  gesto siguiente o a reposo.
- **R12. El ápice cae en la palabra.** El movimiento empieza antes para que el ápice coincida
  con el ancla, con 0,2 s de adelanto, como hoy.
- **R13. Se sostiene lo que hay que mirar.** Un punto señalado, una medida o una barrera se
  sostienen al menos 0,4 s. Un trazo (una ruta, un giro) no se sostiene: se termina.
- **R14. Cada respuesta acaba en punto cero.** Dentro de una respuesta cada movimiento sale de
  la postura de trabajo y vuelve a ella; no se encadena uno con otro sin pasar por ella. Al
  terminar la respuesta los brazos reales se pliegan a punto cero, despacio, y la petición
  siguiente los despliega mientras la IA piensa. Plegar en cada gesto añadiría varios segundos
  a cada uno.

### Los dos brazos

- **R15. Un principal y un papel para el otro.** El otro brazo acompaña, hace de espejo, ancla,
  prepara, hace contrapunto o queda libre. El registro dice cuál pide cada concepto.
- **R16. El principal es el del lado.** Lo que está o va hacia la izquierda lo hace el brazo
  izquierdo, y lo de la derecha, el derecho. Si no hay lado, lo hace el brazo que no hizo el
  gesto anterior.
- **R17. El brazo libre prepara.** Si ya se conoce el gesto siguiente y le toca a él, va a su
  primera postura mientras el principal hace el gesto actual. Es lo que hace que el siguiente
  llegue a tiempo.
- **R18. Si no hay siguiente, acompaña.** Como hoy: se inclina con el gesto del otro y vuelve.
- **R19. Si el principal sostiene algo preciso, el otro descansa.** Un punto señalado, una
  medida o un destino piden que nada más se mueva.
- **R20. Mientras uno señala, el otro hace otra cosa.** Prepara, ancla o hace contrapunto.
  Nunca señala otra cosa distinta, salvo en los dos gestos pensados para eso (B15 enmarcar y
  B16 origen y trayecto).
- **R21. La simetría significa.** Los dos brazos en espejo se reservan para conjunto, tamaño,
  unión, separación y trato (bienvenida, calma). No se usan para dar énfasis.
- **R22. El ancla espera.** El brazo que sostiene una referencia no se retira hasta que el
  principal termina; salen los dos a la vez.
- **R23. Cada brazo en su mitad.** No se cruzan ni se acercan a menos de 160 mm. Lo comprueba
  el motor y, si no cabe, el gesto no se hace.
- **R24. Se turnan.** Como mucho dos gestos con significado seguidos del mismo brazo. En
  enumeraciones y contrastes, uno cada vez.

### La conversación entera

| Momento | Qué hace el cuerpo |
|---|---|
| Apertura | Saludo (M20) o bienvenida (B09), y ofrecer ayuda (M24) |
| Escucha | Postura de escucha con los dos brazos (M23), quietos |
| Toma de turno | Entendido (M05). Si la respuesta tarda, consultar (M11 con M22) |
| Respuesta | Marco, detalle y cierre: reglas R28 a R31 |
| Cesión de turno | Ceder el turno (M24) y vuelta a la escucha |
| Despedida | Agradecer (B11) y saludo (M20) |

- **R25. Se abre y se cierra con el cuerpo.** La primera y la última frase de la conversación
  llevan gesto de trato, no de contenido.
- **R26. Se nota que escucha.** Al terminar su turno el robot cede (M24) y pasa a la postura de
  escucha; no vuelve a un reposo neutro.
- **R27. La espera se dice.** Entre la pregunta y la primera palabra pasan de 2 a 3,5 s. Si
  pasan de 1,5 s, un brazo pide espera (M22) y el otro consulta (M11).
- **R28. Marco, detalle y cierre.** La primera frase de la respuesta lleva un gesto amplio que
  sitúa (una zona, un conjunto, una dirección general). Las centrales llevan el detalle. La
  última lleva un gesto de discurso: confirmar, plazo, ceder el turno.
- **R29. Las listas se anuncian y se cuentan.** Primero cuántas cosas son (M06) y después una
  por parada, alternando de brazo si son dos o tres.
- **R30. Las direcciones van por tramos y en orden.** Una instrucción por frase. El brazo del
  lado del giro hace el giro; el otro prepara el siguiente. Se acaba clavando el destino (E17)
  o señalándolo en el mapa (D01).
- **R31. Los avisos van en tres pasos.** Atención (M21), después la norma o el peligro (M03,
  B14, M30) y por último qué hacer (E13 rodear, M02 alternativa, B13 moderar).
- **R32. Las comparaciones usan los dos brazos.** Cada opción es de un brazo durante toda la
  comparación (B17, B06); no se cambian a mitad.
- **R33. Lo que no se sabe también se dice.** «No tengo ese dato» lleva B12, no un acento.

### Elegir el gesto

- **R34. Orden de preferencia para la palabra ancla:**
  1. Está en la imagen y importa cuál es: deíctico (D).
  2. Tiene forma, trayecto o dirección: espacial (E).
  3. Es una relación entre dos cosas o una cantidad: bimanual (B).
  4. Es permiso, tiempo, trámite o trato: discurso (M).
  5. Nada de lo anterior: acento (M01).
- **R35. Dos conceptos por frase, uno por brazo, y uno de ellos gráfico.** El gráfico dibuja lo
  que se dice: una forma, un trayecto, un tamaño, una cantidad o una acción. El otro puede ser
  gráfico o de apoyo (dirección, trato, permiso). Cada uno tiene su palabra y su brazo llega a
  ella en ese momento. Los movimientos de dos brazos cuentan como los dos conceptos.
- **R36. No se repite.** El mismo movimiento no va en dos frases seguidas. Si el concepto se
  repite, la segunda vez lleva acento o lo hace el otro brazo.
- **R37. El tamaño sigue a la importancia.** Lo principal, amplio y alto. Lo accesorio, corto y
  cerca del cuerpo.
- **R38. La imagen gana.** Si en pantalla hay un mapa o una foto que contiene lo que se nombra,
  se señala ahí en vez de dibujarlo en el aire.
- **R39. Lo compuesto se reparte.** Un concepto con dos partes da una a cada brazo: «zona
  peatonal» es una superficie (E19) y un alto a los coches (M03).
- **R40. Ante la duda, acento.** Un gesto equivocado informa peor que ninguno.

### Tiempos

Medidos el 16-11-2026 contra el motor, a 110°/s y con los brazos a 500 mm:

| Medida | Mínimo | Mediana | Máximo |
|---|---|---|---|
| De reposo a la primera postura | 0,8 s | 1,2 s | 2,4 s |
| Gesto entero, saliendo de reposo y volviendo | 2,0 s | 4,5 s | 6,3 s |

- **R41. Presupuesto por frase.** Una frase de 6 s da para un plan con los dos brazos, cada uno
  con su concepto.
- **R42. Volver a reposo cuesta alrededor de 1 s** por movimiento. Se asume: es lo que pide R14.
- **R43. Tarde vale mientras dure la frase.** Un gesto con retraso se hace si su ápice cae antes
  de que acabe la frase que ilustra. Si no, se intenta con el principal solo, que es más corto, y
  si tampoco llega, se omite. Los ápices de los dos conceptos de una frase no se separan más de
  1,5 s, para que el plan de los dos brazos no se alargue.
- **R44. La pinza es lenta.** Abrir o cerrar del todo lleva casi 1 s. Los gestos de pinza usan
  recorridos parciales o empiezan antes.
- **R45. El primer gesto del turno es corto.** No hay tiempo de preparar: se elige uno cuya
  primera postura esté a 1 s o menos de reposo (D13, E04, M05, M08).

### Convenciones del espacio

- **R46. Izquierda y derecha son las de quien escucha.** Hoy los brazos miran a la imagen igual
  que el público, así que coinciden con las del robot. Si el robot se monta de cara al público,
  se invierte qué brazo hace cada lado: es un ajuste del montaje, no del registro.
- **R47. El tiempo va de izquierda a derecha.** Antes, hacia la izquierda de quien escucha;
  después, hacia la derecha. La línea del tiempo la lleva el brazo derecho (M14 antes, M13
  después). Si lo hace el izquierdo, se invierten.
- **R48. La altura es cantidad.** Más, mejor, importante o superior, arriba. Menos, abajo.
- **R49. La distancia es pertenencia.** Cerca del cuerpo, lo propio y el servicio. Lejos, el
  destino y lo ajeno. Al frente y al centro, quien escucha.
- **R50. Las series avanzan hacia la derecha** de quien escucha, igual que el tiempo.
- **R51. En el mapa, el mapa manda.** El norte está donde lo pone el mapa, y las direcciones
  sobre el mapa se señalan en él, no en el aire.

### Límites

- **R52. Solo consignas y sensores.** Las posturas del registro son constantes nominales. Nada
  de esto lee el estado interno del simulador, y antes de ejecutar un plan se comprueba con los
  encoders que el brazo está donde el plan empieza. Es la norma de `AGENTS.md`.
- **R53. Todo plan se valida entero** antes de moverse: rangos, velocidad, altura sobre la mesa
  y distancia a la obra y entre brazos. Si no pasa, la frase lleva acento.
- **R54. Lo que estos brazos no pueden decir:**

| No se puede | Se sustituye por |
|---|---|
| Contar con dedos más de tres | Paradas (M06) hasta tres; después, «mucho» (M26) |
| Tocarse: reloj en la muñeca, mano al pecho | Círculo de reloj (M12), recoger hacia sí (D13) |
| Cruzar los brazos en X | Barrera con los dos al frente (B14) |
| Señalar hacia atrás | Arco que pasa por encima (E13) |
| Gestos de cara y cabeza | Nada: lo dice la cara de la pantalla o la voz |
| Formas de mano: OK, comillas, teléfono | Pinza que habla (M17), afirmar (M05) |

- **R55. Lejos de las personas.** Todos los movimientos quedan dentro del volumen comprobado,
  delante de los brazos. Ninguno alcanza a quien escucha.
- **R56. A la velocidad acordada.** 110°/s en los brazos reales.

## Un ejemplo completo

Pregunta: «¿Cómo llego al ayuntamiento?»

| Frase | Brazo derecho | Brazo izquierdo |
|---|---|---|
| (mientras pregunta) | Escucha (M23) | Escucha (M23) |
| «Está cerca, a unos cinco minutos a pie.» | Un poco (M25) | Prepara avanzar recto |
| «Siga recto por esta calle hasta la plaza.» | Prepara el giro | Avanzar recto (E04) y clavar (E17), encadenados |
| «Allí gire a la derecha.» | Girar hacia fuera (E05) | Prepara subir |
| «Verá el ayuntamiento, un edificio alto con una torre.» | Marca la base (E16) | Subir (E08) |
| «¿Quiere que se lo marque en el mapa?» | Ceder el turno (M24) | Acompaña |
| (espera la respuesta) | Escucha (M23) | Escucha (M23) |

Cinco frases, seis gestos con significado, ningún señalamiento y ningún brazo esperando quieto
mientras se habla. Con los cinco gestos de antes, las mismas frases llevarían una línea recta y acentos.

## Las fuentes

| Fuente | Qué es | Qué se usa aquí |
|---|---|---|
| SeG | 208 gestos humanos con descripción y contextos de uso. Lista completa y dos clips en local | El significado: 68 de los 84 movimientos citan el gesto de SeG del que toman el sentido |
| RoboGesture | Artículo de agosto de 2026 (ECCV 2026) para un humanoide Unitree G1 con manos de dedos, 41 articulaciones | El método: dos capas (significado sobre ritmo), el gesto se adelanta a su palabra, y cada clase se prueba en el robot y se descarta si no es realizable |
| SmolVLA | Un modelo, no un conjunto de datos: 450 millones de parámetros, entrenado para manipular objetos | El formato: cada movimiento del registro lleva la frase de tarea con la que se grabaría |
| BEAT2, MM-Conv | Un clip de cada uno en local | Ritmo y gestos referenciales, como hasta ahora |

Dos cosas que conviene saber:

- **RoboGesture no publica su lista de clases.** El artículo habla de más de 300, construidas a
  partir de SeG y EgoGesture, pero no las enumera ni dice que los datos estén disponibles. Su
  punto de partida, SeG, sí lo tenemos, y es lo que se ha usado.
- **De los 208 gestos de SeG, muchos no caben en un SO-101.** Los de dedos, cara y contacto
  con el cuerpo se han descartado o sustituido (R54), igual que RoboGesture descartó los que su
  humanoide no podía hacer.

## Sobre la política entrenada

Hoy no hay ninguna política entrenada ejecutando gestos, y este protocolo no la necesita.

- **Cómo se mueve el robot ahora:** la IA (ER 2) escribe la frase y elige el gesto; un motor
  propio calcula la trayectoria, la valida y la sincroniza con la voz al milisegundo. No hay
  aprendizaje en la ejecución.
- **Qué haría falta para SmolVLA:** unas 50 demostraciones grabadas por cada movimiento, con
  cámaras y un brazo guía para teleoperar. Para 84 movimientos son unas 4 200 grabaciones, y
  después un entrenamiento de unas 4 horas en una GPU A100 por cada ajuste.
- **Qué se ganaría y qué se perdería:** una política da movimiento más orgánico, pero decide
  ella cuándo llega el ápice, así que la sincronía con la palabra deja de estar garantizada, y
  sus movimientos no pasan por la validación previa del plan entero.

Con un brazo guía para teleoperar las demostraciones se pueden grabar, pero no en unas horas:
solo grabar y entrenar un movimiento fiable lleva más de una jornada.

Recomiendo seguir con el motor para ejecutar y dejar la política como opción futura. El registro
ya está preparado para ella: cada movimiento tiene su frase de tarea, y el motor puede generar
las trayectorias de ejemplo sin teleoperar. Si se quisiera probar, lo sensato es empezar por
cinco o seis movimientos, no por los 84.

## Qué hace ya el programa y qué falta

**Hecho:**

- **La IA elige de la biblioteca.** Cada frase trae el movimiento gráfico, obligatorio, y un
  segundo concepto de apoyo para el otro brazo, cada uno con el índice de su palabra:

```json
{"texto": "En la plaza gire a la derecha y cruce el puente que pasa sobre el río.",
 "tipo": "gesto", "brazo": "der", "grafico": "E05", "ancla": 3, "apoyo": "E10", "ancla_apoyo": 14}
```

- **También al señalar.** Un bloque `senalar` o `region` lleva además `grafico` y `ancla_grafico`:
  mientras un brazo señala algo de la imagen, el otro dibuja.
- **Cada brazo llega a su palabra.** Los dos movimientos se funden en un solo plan con el ápice
  de cada uno en su instante, validado entero. Si juntos acercarían demasiado los brazos, se
  hace solo el principal.
- **Se cuenta y se dice.** Al acabar el turno el registro escribe «Conceptos gráficos: 4 de 4
  frases». Si la IA no pone el gráfico en alguna, la frase se dice igual y el recuento lo delata.
- **Los acentos de relleno son de seis formas** en vez de una, y la mitad no abre la pinza.
- **El control los ejecuta** en los dos tipos de turno (frase a frase y entero), con la misma
  validación previa, la misma sincronía con la palabra y los mismos acentos alrededor.
  El código está en `src/so101er/control/expresion.py`.
- **Queda escrito qué se hizo.** El registro de la sesión añade a cada frase su movimiento:
  «… [beat2; alineación ElevenLabs] · E05 girar hacia fuera (der) + E10 ondular».
- **Demo biblioteca:** un botón nuevo en la pestaña 4 lanza una conversación de seis frases con
  movimientos de la biblioteca, sin pasar por la IA.

Con la IA real (16-11-2026), en seis preguntas y 19 frases: 16 llevaron concepto gráfico, 18
usaron los dos brazos y salieron 17 movimientos distintos en 25 usos. El primer bloque llegó a
1,0–1,9 s, igual que antes de añadir la lista.

**Falta:**

1. **Preparación anticipada** (R17): que el brazo libre vaya ya a la primera postura de su
   gesto siguiente. El encadenado sin pasar por reposo queda descartado (R14).
2. **Postura de escucha y gestos de turno** (R8, R25 a R27). El robot no cambia de postura
   mientras escucha ni mientras espera la respuesta.
3. **Que las reglas se apliquen fuera de la IA.** Hoy quien decide el movimiento es la IA
   leyendo la lista; no hay una comprobación posterior de variedad, lado o presupuesto.

## Cómo supervisar y cambiar el registro

- **Leer:** [REGISTRO_EXPRESIVO.md](REGISTRO_EXPRESIVO.md) tiene las tablas, por familia de
  movimiento y por ámbito.
- **Cambiar:** se edita `datos/expresion/registro.json` (un movimiento, una conexión, una
  postura) y se vuelve a generar:

```bash
python tools/registro_expresivo.py
```

- **Qué comprueba:** que cada conexión use movimientos que existen, y que cada movimiento quepa
  en los dos brazos con el montaje y la velocidad reales. Si uno deja de caber, lo dice con el
  motivo.

## Verlo en simulación

```bash
python tools/demo_registro.py conversacion
```

```bash
python tools/demo_registro.py catalogo
```

El primero graba la conversación de ejemplo con los dos brazos; el segundo, los 72 movimientos
nuevos uno a uno, con su rótulo, en un vídeo por familia (tarda unos 12 minutos). Los vídeos
quedan en `salidas/expresion/`, sin voz. La escena
es la del programa, con el montaje y la velocidad reales y física simulada: los brazos siguen
las consignas a través de sus actuadores y el seguimiento se mide con los encoders simulados.
En la conversación el error de seguimiento máximo fue de 3,1° (el control se detiene a 25°).

## Sin comprobar

- **En los brazos reales.** «Cabe» es una comprobación del motor: rangos, velocidad y
  distancias. Los movimientos nuevos solo se han visto en simulación.
- **Que se entiendan.** Que un círculo vertical se lea como «horario» o una pinza que se cierra
  como «completo» es una propuesta. Hay que verlo y preguntar a quien lo mire.
- **Las conexiones.** Son 273 propuestas mías a partir de SeG y del diseño propio; no salen de
  datos de uso. Están para que las revises y las cambies. La IA no las consulta: elige leyendo
  el nombre y la descripción de cada movimiento.
- **Lo que la IA sabe.** Sigue siendo una guía de la imagen que tiene delante. Si se le pregunta
  por un horario o un precio que no están en la imagen, los inventa. Para dar información real
  de servicios hay que darle esos datos.
