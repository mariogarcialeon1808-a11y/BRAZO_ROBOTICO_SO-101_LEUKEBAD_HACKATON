# Perfil amplio, pinzas y retorno a reposo

Aplicado a los gestos de la interfaz integrada y a los cuatro ejemplos exportados.

- Se busca el mayor alcance válido entre el 86 y el 94 % del alcance nominal del
  URDF. Los cuatro ejemplos alcanzaron aproximadamente el 92–94 % antes de recogerse.
- Paisaje y cielo abren los DOS brazos hacia fuera, con 65 grados de barrido por
  brazo. La cámara del visor se aleja para mostrar la apertura completa.
- Señalar conserva el rayo al punto de la imagen, alargando el brazo sobre ese rayo.
- Recorrer conserva la rectitud y la orientación; el recorrido expresivo se amplía
  aproximadamente al triple. No se normaliza cada punto sobre una esfera.
- Las pinzas abren de 0 a 100 % durante los barridos y cierran de nuevo al recogerse.
  Al señalar permanecen completamente cerradas durante toda la fase expresiva.
- Cada gesto termina con una recogida comprobada de AMBOS brazos a la pose plegada
  de reposo, con pinzas cerradas. Esa recogida forma parte del plan y de su duración.

La pose de reposo es una constante cinemática nominal: punta a 150 mm por delante
del eje pan y 180 mm de altura en cada base; pinza al 0 %. El inicio del controlador
sigue leyendo los encoders declarados y su adquisición sensorial.

El trazo llega a la extensión antes de recogerse: el extremo final de la trayectoria
completa es reposo. `fin_trazo` y `inicio_retorno` permiten distinguir ambas fases.
Los brazos no vuelven a desplegarse hasta que termina el retorno del gesto anterior.
Escape/interrumpir conserva su función de frenada; no obliga a continuar un gesto
que el usuario haya cortado.

No se aumentaron las velocidades, aceleraciones ni límites articulares. Se validan
la separación, la mesa, el cuadro, ambos brazos y las diferencias finitas de velocidad,
aceleración y tirón en todo el plan, incluida la recogida y la apertura de pinza.

La planificación de voz reserva tiempo para la actuación completa. Si hace falta,
el audio continuo se alarga con `atempo` conservando el tono; las marcas de palabras
se escalan con él. No se omiten gestos por falta de hueco entre frases. La demo y
las instrucciones de ER2 usan descripciones más largas con anclas relevantes para
dejar espacio natural a los movimientos y reducir la necesidad de ralentizar voz.
Esto puede prolongar el turno: la extensión y el regreso requieren tiempo físico.

Los movimientos son referencias calculadas desde sensores/consignas, calibración
y memoria; no se introducen posiciones, contactos ni fuerzas privilegiadas del
simulador en el nuevo perfil. La prueba de invariancia cubre también este compilador.

`tools/demo_expresivo.py` genera un vídeo MuJoCo y mide seguimiento/retorno desde
los encoders declarados. La prueba comprueba el regreso con error menor de 2 grados
o puntos porcentuales y el seguimiento con menos de 25 grados. La geometría sigue
siendo nominal y la sesión se mantiene en simulación, como indicó el usuario.

Verificación: 119 pruebas pasadas. En el vídeo, el error máximo de seguimiento fue
4,72 grados y el error final de reposo fue menor de 0,3 grados/puntos porcentuales.
