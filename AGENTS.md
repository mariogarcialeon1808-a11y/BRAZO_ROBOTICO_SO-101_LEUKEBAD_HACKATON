# Control del robot exclusivamente sensorial

El actor y todo controlador que decide una acción desplegada deben usar solo
mediciones disponibles en el robot real, estimaciones causales derivadas de ellas,
constantes nominales/calibración, consignas externas, acciones emitidas y memoria.

Nunca usar verdad interna de MuJoCo para decidir acciones, directa o indirectamente
a través de preprocesado, referencias, ganancias, FSM o selección de movimientos.
Esto incluye qpos/qvel de base, xpos/xmat, velocidades reales, contactos/fuerzas/
fricción del solver y xfrc_applied. La adquisición simulada pasa por sensores
declarados equivalentes al hardware, con ruido, sesgo, retardo y límites explícitos.
Los estimadores también se inicializan desde esa adquisición.

Crítico, recompensa, evaluación y terminación física pueden usar privilegios durante
entrenamiento si no se filtran al actor. Ante algo no observable, construir un
estimador sensorial o cambiar representación; no consultar verdad física como atajo.

Antes de certificar un cambio, rastrear entradas/decisiones y verificar invariancia:
con sensores, consignas y memoria iguales, cambiar verdad privilegiada no debe
cambiar las entradas ni la acción. Corregir y declarar cualquier dependencia.

Esta fase está autorizada en simulación. Los brazos físicos siguen pendientes de
prueba/calibración. Antes de cambios amplios conservar un snapshot completo en
`COPIAS DE SEGURIDAD FASE2`, fuera del repositorio. Conservar fuentes históricas
para reproducibilidad; no asumir que son un despliegue sensorial validado.
