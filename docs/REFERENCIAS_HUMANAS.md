# Referencias humanas y anclaje espacial

Esta etapa añade un importador offline, motivos normalizados y dos formas de
adaptación al SO-101. No entrena una policy ni ejecuta EMAGE en la GPU del portátil.
No todos estos recursos son datasets de emociones: distinguimos semántica,
dinámica del movimiento y relación con referentes espaciales.

## Estado verificado al 14 de noviembre de 2026

| Fuente | Aportación | Estado local |
|---|---|---|
| [SeG / Semantic Gesticulator](https://github.com/LuMen-ze/Semantic-Gesticulator-Official) | Gestos con etiquetas semánticas y BVH | Dos clips reales descargados e importados; retargeting y compilación probados |
| [BEAT2](https://huggingface.co/datasets/haiyangliu0/BEAT2) | Variación y relación habla/movimiento; EMAGE es un modelo | Conversor SMPL-X escrito, sin dataset ni archivos corporales instalados; inferencia de conversión aún no validada |
| [Grounded Gestures 2025](https://groundedgestures.github.io/) | Referencia espacial + conversación | Excluido de la biblioteca activa: su página muestra botones Data/Code sin enlace operativo |
| [MM-Conv / SGS-HSI 2026](https://huggingface.co/datasets/hsi-workshop/referential-gesture-challenge) | Movimientos asociados a objetivo 3D, mano y tiempos | Fuente alternativa más reciente identificada; pendiente de revisión de términos y conversión de clips |

Catálogo comprobable: `datos/fuentes_gestos.json`. SeG tiene licencia de investigación
no comercial y restricciones de redistribución. Se guarda el PDF original y el XLSX
de etiquetas junto a las dos muestras privadas en `datos/referencias/seg/`; esa carpeta
y las salidas están excluidas de Git. No inferir la licencia de los datos de una
licencia del código. Los modelos corporales SMPL-X tienen sus propios términos.

## Transformación

1. BVH: leer jerarquía, offsets y orden real de canales; calcular FK humana.
2. SMPL-X: convertir parámetros con un modelo corporal explícito, después obtener XYZ.
3. Seleccionar muñeca y hombro por nombre y un recorte temporal explícito del trazo.
4. Restar hombro a muñeca para eliminar traslación global; normalizar forma y extraer
   progreso temporal por longitud recorrida. Es información de referencia offline.
5. Crear una `Intencion` con posición y eje adaptados al robot; compilar desde encoders.

Los ángulos humanos NO se copian a los motores. `forma_en_marco()` permite trasladar,
rotar y escalar una forma mediante un marco ortonormal y escala por eje explícitos.
La forma conserva el sistema de coordenadas de origen hasta esa transformación;
no se adivina cuál es su eje vertical. `MotorGestos.compilar()` puede rechazarla
por orientación, alcance o separación. El montaje SO-101 no admite toda pose humana.

Para objetivos exactos, `adaptar()` transfiere solo el perfil temporal y conserva los
puntos y ejes de la consigna. Un polinomio de Bernstein monótono suaviza ese perfil;
por tanto se transfiere una aproximación del ritmo, no la velocidad capturada exacta.
El retiming posterior puede alargarlo para respetar límites. En un señalamiento
estático el perfil no añade oscilaciones: el eje debe seguir señalando el objetivo.

`control/anclaje.py` ofrece señalamiento a píxel de plano calibrado, barrido de región
rectangular y recorrido con posición/eje independientes. La imagen debe estar
rectificada al plano configurado o la homografía debe corresponder a la cámara real.
No obtiene profundidad física de una fotografía. Las coordenadas del corpus no se
utilizan como estimaciones del entorno real.

## Demostraciones

Desde el proyecto instalado en modo editable:

```powershell
so101er gestos --referencia datos/referencias/seg/ARMS_ENCOMPASS-1.json --salida salidas/gestos_humanos
python examples/retarget_seg.py
```

La primera demostración adapta el ritmo de SeG a los cuatro objetivos procedurales.
La segunda transforma realmente la FORMA de dos muñecas humanas al espacio nominal
de un SO-101: escala lateral de 1 mm y de 15 mm en los otros ejes. Esa compresión
es deliberada para mantener un eje de herramienta realizable. Es una demostración
conservadora; no reproduce el cuerpo entero ni valida naturalidad humana.
Ambas exportan HTML y JSON y mantienen el segundo brazo en apoyo comprobado.

Los recortes iniciales de SeG están registrados en el catálogo (frames 50:135 y
30:95). Se eligieron por inspección cinemática, sin afirmar anotación de ápice
humano, emoción o sincronización con palabras. Necesitan revisión visual humana.

## Importar más referencias

```powershell
so101er importar-movimiento clip.bvh --id mi_clip --fuente "fuente original" --licencia "términos aplicables" --hombro LeftShoulder --muneca LeftWrist --inicio 30 --fin 95 --etiquetas extension --salida motivo.json
```

Cada motivo conserva fuente, licencia y SHA-256 del archivo que se procesó. No se
asigna una emoción si no hay una anotación que la sustente. `Biblioteca.elegir()`
usa coincidencia explícita de etiquetas; no hay todavía recuperación semántica
aprendida. El selector de texto/imagen deberá elegir de este catálogo en otra etapa.

Para BEAT2 y los NPZ compatibles de MM-Conv, con `smplx`, `torch` y modelos corporales
obtenidos legítimamente e instalados:

```powershell
python -m so101er.convertir_smplx clip.npz --modelo-dir RUTA_MODELOS --genero neutral --salida joints.npz
so101er importar-movimiento joints.npz --id beat_clip --fuente BEAT2 --licencia "términos del recurso" --hombro LeftShoulder --muneca LeftWrist --fps 30 --salida beat_clip.json
```

El conversor admite `poses[T,165]`, `trans[T,3]` y betas; conserva los primeros diez
coeficientes de forma. No admite indiscriminadamente cualquier variante SMPL-X ni
263D HumanML3D. Los NPZ de XYZ se cargan sin pickle. La conversión corporal completa
no se ha probado con los archivos reales del modelo porque no están instalados.

## Pruebas y límites

95 pruebas pasaron y un módulo opcional de Google se omitió en la batería completa.
Las pruebas nuevas verifican FK BVH con rotaciones/traslación conocidas, importación,
procedencia, retargeting, perfil temporal, objetivos visuales distintos, región,
validación de formatos y los dos clips reales de SeG. Después se amplió la prueba
de esos clips para comprobar también la forma adaptada al SO-101.
No se han usado motores ni se ha medido la naturalidad mediante valoración humana.

La fuente sensorial del controlador no cambia: consignas, encoders proporcionados,
calibración y FK nominal. Los datos humanos son referencias de movimiento; los
objetivos de los datasets quedan offline. En particular, no se debe conectar el
scene graph privilegiado de un simulador al planificador desplegado.
