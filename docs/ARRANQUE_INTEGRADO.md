# Aplicación integrada en este portátil

El perfil de movimiento actual está descrito en [GESTOS_AMPLIOS.md](GESTOS_AMPLIOS.md):
extensión, pinzas y vuelta a reposo. Sus cambios de sincronización sustituyen la
omisión de gestos por falta de tiempo descrita más abajo para la versión anterior.


## Arranque

Ejecutar `INICIAR_SIMULACION.cmd`, o el acceso `INICIAR_SO101.cmd` de la carpeta superior.
Se abren el visor MuJoCo y una interfaz con el dibujo del campo, montañas, árbol,
sol, casa y lago. No necesita una imagen nueva ni una clave pegada en la interfaz.

- **Preguntar a la IA:** escribir y pulsar Enter. ER2 ve el cuadro y devuelve texto y gestos juntos.
- **Hablar por micro:** pulsar para grabar, hablar y volver a pulsar para enviar. Máximo 20 s.
- **Señalar:** hacer clic en un punto de la imagen.
- **Marcar región:** seleccionar el modo y arrastrar un rectángulo.
- **Demo humana:** explica cuatro ejemplos con el corpus seleccionado.
- **Interrumpir** o Escape: cortar audio y frenar desde la memoria de consignas.
- Selector SeG/BEAT2/MM-Conv: cambia la referencia de dinámica humana.

El micrófono no vigila continuamente ni usa una tecla global. El texto permite
continuar si el dispositivo de audio no está disponible.

## Entorno y servicios

Python aislado en `C:\Users\PC\AppData\Local\so101er-runtime`. Las versiones
instaladas se registran en `requirements_runtime.lock`. No se modificó Python global.
Se instalaron Gemini SDK, MuJoCo 3.3.7, OpenCV, audio, Whisper/CTranslate2, pyserial,
SDK Feetech y herramientas de pruebas. El controlador USB usa un protocolo STS
pequeño y comprobable sobre pyserial; no requiere instalar entrenamiento de LeRobot.

ER2 usa explícitamente API **v1beta** y razonamiento MINIMAL. La API v1 estable
devolvía 404 para este modelo. La última prueba rápida devolvió texto y gestos en
2,52 s. ElevenLabs devolvió una muestra con alineación en 1,21 s. Son mediciones
puntuales; no percentiles de latencia ni una garantía sobre el servicio gratuito.

Las claves se leen del entorno o del `.env` ya configurado en `conversacion.env`.
No se copian al proyecto ni se imprimen. La voz utiliza la voz ElevenLabs que ya
estaba configurada. La calidad/acento requiere valoración auditiva del usuario.

Whisper base se descargó a `datos/modelos/whisper_base` y funciona en CPU int8.
Transcribió correctamente la muestra sintetizada en español; la primera carga y
transcripción tardaron 3,17 s. El micrófono Realtek abrió captura mono a 16 kHz y
produjo señal durante la prueba de un segundo. Falta la prueba con la voz del usuario.

## Continuidad y sincronización

Cada turno produce un audio continuo, con las marcas de caracteres del proveedor.
Los planes de gestos se preparan antes de reproducirlo y se programan según sus
palabras. La ejecución a 50 Hz corre en un hilo separado de red, síntesis y GUI.
Hay espera inicial de planificación/síntesis. No es todavía generación infinita
por streaming; los turnos se limitan a pocas frases para contener la espera.

Si no cabe un gesto en su palabra, o el estado medido difiere de la predicción,
se omite ese gesto y se indica en el registro. La voz conserva continuidad.
No se aceleran los motores para perseguir el audio. La latencia de salida se
compensa aproximadamente con lo declarado por el dispositivo de audio; la precisión
acústica/mecánica real no se ha medido con instrumental.

## BEAT2 y MM-Conv

Se descargó una grabación española real de BEAT2 (Carlos, 2543 frames) y una de
MM-Conv (1000 frames). Se conservaron origen, SHA de referencia y método de
transformación en `datos/referencias/beat2` y `datos/referencias/mmconv`.

La transformación principal usa las rotaciones SMPL-X originales sobre un
**esqueleto humano nominal propio**. No utiliza betas ni malla corporal ni afirma
reproducir la anatomía exacta del actor. Así se evita depender del modelo corporal
registrado para el arranque. El conversor exacto con archivos SMPL-X sigue siendo
opcional y no está validado aquí. No se descargaron los corpus enteros de varios GB.

Se eligió una ventana de mayor desplazamiento de muñeca de cada grabación, sin
atribuirle emociones, referencias semánticas o ápices manuales que no se hayan anotado.
La forma cartesiana puede transformarse a un marco del SO-101 y se comprueba con IK.
Al anclar puntos y regiones, se conserva su geometría y se transfiere el perfil
temporal humano. En señalar también se aplica a la preparación, manteniendo estable
la orientación una vez alcanzado el referente. No se copian ángulos humanos al servo.

Vídeo reproducible: `salidas/demo_BEAT2_MMConv.mp4`. Muestra ambas fuentes adaptadas
a dos puntos y una región del cuadro. Son movimientos nominales en MuJoCo, no
pruebas de precisión en un brazo real ni evaluación humana de naturalidad.

## MuJoCo y procedencia sensorial

Se reactivó sustituyendo la lectura de qpos por **doce sensores jointpos declarados**.
La adquisición aplica frecuencia de 100 Hz, retardo de 20 ms, cuantización nominal
de 4096 cuentas/vuelta, ruido de 0,04 grados y sesgo nominal de 0,08. Este perfil
es de ensayo y debe identificarse con el hardware para afirmar equivalencia cuantitativa.

No se usa actuator_force como carga ni se inventan temperaturas para decisiones.
Esas capacidades están declaradas ausentes en simulación. Se eliminó el cálculo
de marcadores de señalamiento desde xpos/xmat sobre imágenes del modelo. Los
parámetros ópticos son nominales. Los planos/bases y la homografía son calibración
nominal explícita. Es necesario medirlos en el montaje real.

Las cámaras renderizadas son adquisición visual. El estado interno se usa para
simulación, inicialización física y renderizado, sin alimentar las decisiones del
controlador. La inicialización del controlador pasa por la adquisición de encoders.
La prueba de invariancia modifica qpos, qvel y fuerzas externas manteniendo iguales
sensores y memoria y comprueba que las observaciones y planes no cambian.

## USB físico

Ejecutar `DIAGNOSTICO_USB.cmd`: enumera puertos y consulta IDs 1–6 sin activar par
ni escribir EEPROM. En la prueba de hoy no había ningún brazo USB detectable.
Por eso no se ha verificado comunicación con motores ni instalado un driver de
adaptador específico: primero debe aparecer el dispositivo conectado.

Para arrancar físicamente hacen falta:

1. Dos adaptadores presentes y sus puertos asignados en `config/so101er.toml`.
2. `calibracion_izq.json` y `calibracion_der.json` medidos y verificados: IDs, cero
   de cada articulación, signo, extremos de pinza y correspondencia con el URDF.
3. Bases, plano del cuadro y cámara calibrados en el montaje real.

`calibracion_usb.ejemplo.json` es solo una plantilla y está marcada NO verificada.
La aplicación rechaza usarla. No se debe marcar verificada sin medir los valores.
El arranque real es `so101er iniciar --raiz . --real`; conectar no habilita par hasta
que ambos brazos tengan calibración y lecturas válidas. No se ha probado físicamente.

## Validación

119 pruebas pasadas, incluidas las de API falsa heredadas, sensores, invariancia,
referencias humanas reales, retargeting, formatos, protocolo USB y contratos de IA.
Las pruebas asyncio necesitaron ejecución fuera del aislamiento de red porque
Windows bloqueaba la creación del socket local del event loop, antes de la prueba.

También se probaron servicios reales: ER2 con imagen, ElevenLabs con marcas,
Whisper local, apertura de micrófono, renderizado y seguimiento en MuJoCo. Se verificó
la interfaz mediante clic al sol, región y pregunta de texto con respuesta hablada.
No hay una certificación global de los comandos históricos ni del hardware físico.

