# Barras de calibración y sombra de referencia

El panel de pruebas conserva las barras articulares. «Calibrar rangos con barras»
abre el calibrador simple anterior: elegir USB/motor, moverlo a mano, registrar
mínimo/máximo y guardar. En este acceso no se abre otra copia del panel al guardar.
Primero hay que sujetar y soltar cualquier brazo activo; se libera la lectura del
panel para que no compita por los mismos USB.

La vista distingue fuentes:

- Amarillo: pose estimada desde encoders y alineación, si están disponibles.
- Azul semitransparente: referencia guardada o, seleccionándolo, objetivo mandado.
- En alineación provisional se rotula que la referencia está capturada sin guardar.
- Al ajustar el dibujo antes de capturar no se lo presenta como una lectura real.
- En simulación se rotula que solo son consignas del modelo; no hay lectura física.

«Sombra azul» permite mostrar/ocultar la comparación; su desplegable elige la
referencia o el objetivo. Durante lectura pasiva sin par no se inventa un objetivo
mandado. Sin alineación, el panel no convierte grados relativos en una pose URDF.
La sombra no soluciona por sí sola esa alineación ni certifica la geometría física.

La sombra se compone con una segunda pasada de render del modelo. Tiene datos de
render independientes de la pose principal; no cambia sensores, consignas, rangos
ni calibraciones. No interviene en el controlador. Sus pruebas comprueban que las
referencias de entrada y la pose principal se conservan al dibujarla.
