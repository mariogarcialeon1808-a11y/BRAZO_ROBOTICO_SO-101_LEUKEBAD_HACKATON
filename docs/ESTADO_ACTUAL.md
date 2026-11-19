# Estado del proyecto — 15 de noviembre de 2026

Esta revisión conserva el estado actual de desarrollo. No restaura una copia
histórica ni declara cerrada la integración física.

## Incluido

- Programa con pestañas para rangos manuales, alineación 3D, preparación y chatbot.
- Rangos con barras verdes, postura de referencia, marcas y sombra del modelo.
- Control por USB de uno o dos SO-101, montaje relativo configurable, visor
  conjunto desde encoders y parada común.
- Saludo y abanico, apertura de pinzas, retorno a la postura inicial y postura de
  trabajo con plegado posterior.
- Gemini para interpretar el dibujo, voz ElevenLabs y reconocimiento local por
  micrófono; normalización de regiones y corrección del formato de respuesta.
- Perfil real configurable en `[real] velocidad_grados_s`. Las pruebas de esta
  sesión usaron una consigna de 20°/s para brazos y 60°/s para pinzas, mientras la
  configuración local guardada está a 60°/s para brazos. No confundir ambos valores.

## Comprobación física y límites conocidos

Se ejecutó un saludo simultáneo sin repetir el bloqueo anterior de la pinza.
También se observaron paradas previas por seguimiento y numerosas lecturas aisladas
anómalas de telemetría que se comprueban con una segunda lectura. Esto no certifica
la fiabilidad del hardware ni sustituye la comprobación de cada montaje.

La demo de la versión actual también se detuvo en MuJoCo por seguimiento del
hombro derecho superior a 25°. Es un problema pendiente de reproducir y resolver
antes de dar por recuperado el comportamiento de la simulación anterior. Las
copias históricas permanecen fuera del repositorio; no se sobrescriben fuentes
actuales para ocultar este fallo.

**Verificación de esta publicación: 223 pruebas pasadas y 4 omitidas** en una
copia congelada de las fuentes. Esas pruebas verifican software; no equivalen a una demostración física
completa ni garantizan movimientos libres de colisiones.

## Datos locales excluidos

Claves y `.env`, registros, salidas generadas, modelos descargados, fuentes y
motivos derivados de datasets con licencia propia, calibraciones de encoders,
alineaciones y medidas particulares del montaje permanecen fuera de Git. La
postura de referencia nominal incluida no es una calibración de encoders.

El controlador utiliza sensores o cálculos causales desde sensores, consignas,
calibración y memoria. La geometría y el estado interno del visor no son entradas
para decidir acciones físicas. No se deben trasladar controles de una copia
histórica a hardware sin revisar esta procedencia.
