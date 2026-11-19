# Motor local: primera implementación

La ruta vigente es `so101er gestos`. Produce cuatro ejemplos reproducibles para dos
SO-101 y una vista HTML sin dependencias externas. No conecta a puertos serie ni
usa cámara, API, audio, modelos aprendidos o estado de MuJoCo.

## Qué se conserva y qué se sustituye

Se reutilizan URDF, cinemática directa, configuración de marcos, plano calibrado y
comprobaciones geométricas. El compilador nuevo (`control/semantico.py`) resuelve
posición y eje de herramienta con tolerancias explícitas. No utiliza el fallback
de orientación del solver antiguo. Conserva libre la rotación sobre el propio eje.

El recorrido usa Hermite con tangentes compartidas y un reloj quintico, seguido de
retiming global. Se comprueban velocidad, aceleración y tirón mediante diferencias
finitas en las consignas muestreadas; esto no certifica la dinámica física del servo.
Se validan también errores de posición y eje dentro del trazo interpolado.
No se añaden respiración, simpatía, exageración ni acentos que deformen la consigna.
El otro brazo mantiene una pose de apoyo estable y participa en la comprobación
de separación. Aún no se componen dos trazos expresivos simultáneos.

El backend MuJoCo histórico queda bloqueado al construir `MundoMuJoCo`: consultaba
`datos.qpos` como lectura de articulaciones y `actuator_force` como carga, sin sensores
declarados equivalentes al hardware, ruido, sesgo, retardo o límites de adquisición.
No son admisibles como entradas del controlador. Además había marcadores de
señalamiento derivados de geometría privilegiada en las imágenes enviadas al agente.
El código queda conservado para poder migrarlo, pero no se ejecuta por la ruta nueva.
Los otros comandos son históricos: no se han certificado globalmente como sensoriales.

## Contrato de entrada y salida

`MotorGestos.compilar(Intencion, encoders)` recibe:

- Tipo: extensión, señalamiento o recorrido.
- Brazo principal, puntos del mundo en mm y eje de la pinza en cada punto.
- Duración solicitada, sostenido, apertura de pinza y ancla de palabra.
- Referencia expresiva o plano calibrado, declarada explícitamente.
- Encoders de TODOS los brazos activos: cinco ángulos nominales en grados y pinza %.

El ancla se conserva para la futura sincronización de voz; aún no activa audio.
Las posiciones solicitadas son consignas. La referencia no convierte un número
inventado por un modelo en una medición. La aplicación que reciba píxeles de una
cámara deberá transformarlos con calibración real antes de pedir un señalamiento físico.

El resultado contiene tiempos, consignas para ambos brazos, inicio/fin del trazo
y errores de los puntos IK. `muestra(t)` permite consultar el plan desde un reloj de
reproducción y mantiene la última pose al terminar. No se recortan velocidades
posteriormente ni se despachan consignas al hardware desde este módulo.

## Ejemplos y procedencia

`ejemplos()` genera explícitamente poses iniciales nominales de demostración. NO son
encoders reales. No hay estimación de sensores a partir de la verdad del simulador.
Los cuatro ejemplos son diseños procedurales propios, todavía sin movimientos SeG.

- Paisaje: arco horizontal a 180 mm, pinza aproximadamente horizontal.
- Cielo: arco a 265 mm, eje elevado 30 grados.
- Punto: eje hacia [260,720] sobre el plano nominal, sostenido estable.
- Camino: recta de 30 mm y eje paralelo al desplazamiento; escala inicial limitada
  por la combinación de orientación, altura y alcance del SO-101.

Las alturas se expresan en la base nominal del brazo. El tamaño y posición se pueden
modificar mediante `Intencion`; no hay reconocimiento de frases por palabras clave.
La cinemática rechaza geometría imposible en vez de cambiar el significado sin aviso.
El tiempo total incluye preparación y sostenido: no es la latencia de planificación.

## Verificación y alcance

`tests/test_motor_semantico.py` comprueba los cuatro significados con FK en todo
el trazo, límites muestreados, sostén del segundo brazo, cambio de objetivo,
inicio desde posiciones proporcionadas, entradas inválidas y rechazo de orientación
incompatible. Comprueba repetibilidad al cambiar un estado privilegiado que no
cruza el contrato del compilador. La auditoría de procedencia cubre este módulo:
solo usa consignas, encoders, constantes nominales y cálculos cinemáticos causales.
No certifica los backends históricos ni un controlador físico todavía inexistente.

Las comprobaciones de separación usan cadenas de segmentos nominales. No cubren
volúmenes completos, cables, personas ni obstáculos desconocidos. Falta comprobar
el montaje físico, la correspondencia de ejes y offsets, lecturas reales, límites
conservadores de servo, seguimiento, watchdog y frenada desde estado medido.

La siguiente integración conectará bloques conjuntos texto/gestos del modelo con
este contrato, audio alineado y una cola común. La biblioteca humana y la
coordinación bilateral expresiva ampliarán después esta base verificada.

## Ejecución

```powershell
python -m pip install -e ".[dev]"
so101er gestos --config config/so101er.toml --salida salidas/gestos
python -m pytest
```

El JSON exportado contiene todas las consignas y marcos nominales. El HTML reduce
solo la reproducción visual a unos 25 FPS; el JSON mantiene la frecuencia del plan.
Se conserva una copia íntegra anterior a los cambios en `COPIAS DE SEGURIDAD FASE2`
en la carpeta superior indicada por el usuario.

Verificación en este portátil: 85 pruebas pasadas y 1 módulo opcional omitido.
Los 7 casos nuevos pasan también después de la comprobación estricta de límites.
No se realizaron pruebas con motores, Google ni voz. Los errores IK de los cuatro
ejemplos fueron inferiores a 2 mm y 1,7 grados sobre el modelo nominal; no son
errores medidos en los brazos físicos.
