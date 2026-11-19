AVISO 2026-11-14: documento histórico. El estado vigente del motor local está en MOTOR_GESTOS.md. MuJoCo deshabilitado por dependencias privilegiadas; no certificado para hardware.

# so101er — Contexto técnico del proyecto

> Documento vivo. Recoge el objetivo, las decisiones tomadas, lo que se ha comprobado
> en la documentación externa y el diseño técnico completo. Sirve para retomar el
> proyecto en otra sesión sin perder nada. Última actualización: 2026-11-14.

---

## 1. Objetivo

Un **guía de museo con brazos**: uno o dos brazos robóticos **SO-101** explican una obra
(por ejemplo, un cuadro) mediante **expresión corporal**, coordinada con una explicación
hablada. El movimiento debe ser **muy suave y relajado, como el de una bailarina**, y a
la vez **muy expresivo**: los brazos tienen que transmitir los conceptos que se explican
(señalar, trazar una diagonal, abarcar una zona, sugerir agua, tamaño, contraste, peso…).

Evolución del encargo (importante para entender por qué el diseño es como es):

1. **Documento original** (`prompt_so101_er2.md`): sistema de manipulación (coger/soltar,
   seguir objetos) controlado por prompts con Gemini Robotics ER 2, cámara cenital y mesa.
2. **Cambio de objetivo**: no se quiere manipular, sino *explicar con gestos*. Una IA
   narradora mira la obra y le dice a ER 2 qué señalar y con qué estilo; ER 2 decide todo
   el movimiento en tiempo real.
3. **Rediseño de trayectorias**: movimiento continuo "de bailarina", no gestos sueltos
   punto a punto.
4. **Coordinación voz–gesto**: hace falta un sistema que sincronice lo que se dice con lo
   que se gesticula. La IA de voz se añadirá más adelante; el diseño debe dejarla prevista.

Del documento original se **mantienen**: las tres capas, los dos modos (uno/dos brazos)
sin tocar código, la seguridad siempre en la capa local, el backend simulado, la consola
manual, los tests sin hardware, las fases de trabajo y la regla de **no mover hardware
real sin confirmación**. Se **eliminan** las funciones de manipulación (`coger`, `soltar`,
`seguir_objetivo`), que podrían añadirse en el futuro.

## 2. Roles del sistema

```
Cámara ──► NARRADOR (Gemini, texto+visión)
             mira la obra y escribe el guion por frases:
             texto + qué señalar + estilo expresivo
                 │
                 ├──► VOZ (pieza intercambiable; hoy "voz muda", mañana TTS o IA de voz)
                 │       da el reloj: "voy por la palabra 7", "pausa", "interrumpida", "fin"
                 │
                 └──► ER 2 (Gemini Robotics ER 2, ve la cámara)
                        localiza en la imagen lo que hay que señalar ([y, x], 0–1000)
                        y compone la coreografía de la frase llamando a funciones
                            │
                            ▼
                 CAPA 3 · LOCAL (este repositorio)
                   Director ─ Partitura ─ Compás (reloj maestro)
                   Coreógrafo por brazo (100 Hz): línea de movimiento + capas + filtro
                   Seguridad ─ Cinemática ─ Backend (simulado o LeRobot)
```

- **ER 2 decide** qué gesto, hacia dónde, cuándo y con qué carácter.
- **La capa local ejecuta**: ER 2 tarda segundos en responder y no puede mandar consignas
  de motor; la capa 3 convierte cada decisión en movimiento continuo a 100 Hz y nunca se
  queda esperando a la red.

## 3. Hechos comprobados en documentación externa (noviembre de 2026)

### 3.1 Gemini Robotics ER 2

- Se usa por la **API de Gemini** con una clave de Google AI Studio y el SDK `google-genai`.
  La clave va en `GEMINI_API_KEY` (nunca en archivos). **La clave debe estar restringida**
  en AI Studio: una clave sin restricciones devuelve **403**.
- Modelos: `gemini-robotics-er-2-preview` (estándar) y
  `gemini-robotics-er-2-streaming-preview` (Live API). ER 1.6 está retirado.
- Los puntos se devuelven como **`[y, x]` normalizados 0–1000** (ojo al orden).
- **Modo en directo (Live API)**, verificado en la página "Robotics with streaming":
  - Cliente: `genai.Client(api_key=..., http_options={"api_version": "v1beta"})`;
    conexión `client.aio.live.connect(model=..., config=types.LiveConnectConfig(...))`.
  - `response_modalities=["TEXT"]` (solo texto), `tools=[{"function_declarations": [...]}]`,
    `system_instruction`.
  - **Solo funciones bloqueantes** (`"behavior": "BLOCKING"`). Solución: nuestras funciones
    responden en milisegundos con "aceptado, en curso"; el movimiento sigue en local.
  - Vídeo: `session.send_realtime_input(video=types.Blob(data=jpeg, mime_type="image/jpeg"))`,
    **máximo 1 fotograma por segundo**. Los fotogramas solos **no** inician un turno: hay que
    acompañarlos de texto. Enviar texto mientras el modelo genera **cancela** lo que hacía
    (hay que esperar a `turn_complete` antes del siguiente aviso).
  - Texto: `session.send_client_content(turns=..., turn_complete=True)`.
  - Llamadas: `message.tool_call.function_calls` (`name`, `args`, `id`); respuesta con
    `session.send_tool_response(function_responses=[types.FunctionResponse(name, response, id)])`.
  - Sesión: **2 min con vídeo sin compresión**, conexión de ~10 min. Usar
    `context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())`,
    `session_resumption=types.SessionResumptionConfig(handle=...)` (el identificador vale 2 h)
    y el aviso `go_away` para reconectar.
- **Modo estándar**: **Interactions API** (`client.interactions.create`), no `generateContent`.
  `tools=[{"type": "function", "name", "description", "parameters"}]`; las llamadas llegan en
  `interaction.steps` (`type == "function_call"`, con `id`, `name`, `arguments`); el resultado
  se devuelve con `input=[{"type": "function_result", "name", "call_id", "result": [...]}]` y
  `previous_interaction_id`. Razonamiento: `generation_config={"thinking_level": "medium"}`.
- Pendiente de verificar al implementar la Fase 2: campo exacto del prompt de sistema en la
  Interactions API, formato de imagen en línea en el SDK y precios oficiales.
- Otros modelos listados por Google (para narrador y voz, configurables):
  `gemini-3.8-flash`, `gemini-3.8-flash-tts`, `gemini-3.8-live`.

### 3.2 LeRobot

- Última versión: **0.7.0** (2026-11-05), requiere **Python ≥ 3.12**.
- Clase del seguidor: `SOFollower` (alias `SO101Follower`), configuración
  `SOFollowerRobotConfig` (alias `SO101FollowerConfig`) con `port`, `id`, `use_degrees`,
  `max_relative_target`, `disable_torque_on_disconnect`.
- Motores `sts3215`, IDs 1–6: `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`,
  `wrist_roll`, `gripper`. Con `use_degrees=True` las cinco primeras van en grados; la
  pinza siempre en 0–100.
- Acciones y observaciones: `{"shoulder_pan.pos": float, ...}`; `get_observation()`,
  `send_action(action)`; bus con `sync_read("Present_Position")`, `sync_write("Goal_Position")`.
- Calibración: `lerobot-calibrate --robot.type=so101_follower --robot.port=... --robot.id=...`.

### 3.3 Equipo del usuario

- Windows 11, Python 3.11.9 de Microsoft Store, sin `uv` ni LeRobot.
- `GEMINI_API_KEY` no definida (hace falta a partir de la Fase 2).
- Una webcam "USB2.0 HD UVC WebCam"; COM3–COM6 son Bluetooth (brazos no conectados).
- La Fase 1 funciona con Python 3.11 y un entorno virtual normal. LeRobot (Fase 3)
  necesitará Python 3.12: se propone instalar `uv` cuando llegue ese momento
  (**pendiente de permiso**).

## 4. Convenciones

- **Unidades visibles**: milímetros, grados, segundos. La pinza va en 0–100 (% de apertura).
  Solo la cinemática usa radianes por dentro.
- **Vector de articulaciones `q`** (6 valores): `shoulder_pan, shoulder_lift, elbow_flex,
  wrist_flex, wrist_roll` en grados + `gripper` en %.
- **Mundo**: `x` a la derecha, `y` hacia delante (hacia la obra), `z` hacia arriba; la mesa
  es `z = 0`. Cada brazo tiene `base_mm` y `orientacion_grados` (giro alrededor de `z`;
  90° significa que el brazo mira hacia `+y`).
- **Imagen**: puntos `[y, x]` en 0–1000, como los da ER 2. `y` crece hacia abajo.
- **Obra ("cuadro")**: un plano definido por tres esquinas en el mundo (sup-izq, sup-der,
  inf-izq). Puede ser vertical (pared) u horizontal (sobre la mesa). Una homografía lleva
  la imagen de la cámara a coordenadas normalizadas de la obra; en simulación es la identidad.
- Idioma: nombres, mensajes y documentación en español.

## 5. Motor de movimiento (núcleo de la capa 3)

### 5.1 Por qué no "punto a punto"

Las curvas de mínimo tirón entre poses, con parada en cada una, dan un movimiento correcto
pero robótico. El motor se basa en cuatro ideas tomadas del control motor humano y de la danza:

1. **Superposición de submovimientos** (modelo de Flash y Henis): el movimiento de cada
   articulación es `q(τ) = base + Σ dₖ · S(w((τ − t₀ₖ − retardoₖ)/Tₖ))`, donde cada término
   es un "escalón suave" que aporta un desplazamiento `dₖ`.
   - `S(u) = 35u⁴ − 84u⁵ + 70u⁶ − 20u⁷` (velocidad, aceleración **y tirón** nulos en los extremos).
   - Como cada término es suave por sí solo, **la suma siempre es suave**, se solapen como
     se solapen. Cambiar de objetivo a mitad de movimiento es simplemente añadir un término
     nuevo: no hay empalmes que calcular ni paradas.
   - Los gestos encadenados se solapan: la recogida de uno se funde con la preparación del
     siguiente (coarticulación).
2. **Ritmo asimétrico**: `w(u) = u / (u + c·(1 − u))` desplaza el pico de velocidad
   (`c < 1`: ataque temprano y llegada larga y blanda).
3. **Sucesión** (port de bras): cada articulación empieza con un retardo creciente
   hombro → codo → muñeca → pinza.
4. **Bultos**: términos `B(u) = 256·u⁴(1 − u)⁴` que salen y vuelven. Se usan para el arco
   del recorrido, la anticipación, el rebase blando al llegar y los acentos de la voz.

Para **seguir un camino** (trazar, dibujar formas) se usan puntos densos con escalones
solapados al triple de su separación: la velocidad resultante es casi constante (rizado
≈ 2 %) y el reparto de tiempos sigue la **ley de los dos tercios** (la mano frena en las
curvas: `v ∝ curvatura^(−1/3)`).

### 5.2 Capas que se suman

| Capa | Reloj | Qué hace |
|---|---|---|
| Línea de gestos | tiempo gestual `τ` | Submovimientos de los gestos y acentos |
| Respiración | tiempo real | Oscilación lenta y deriva; el brazo nunca queda rígido |
| Arrastre de muñeca | tiempo real | La muñeca y el giro se retrasan respecto al movimiento, como una cinta |
| Filtro de seguridad | tiempo real | Limita velocidad, aceleración y tirón por articulación |

El **filtro de seguridad** es un seguidor de tercer orden: sigue la referencia exactamente
mientras esta respeta los límites y, si no, la alcanza con tirón limitado. Es una red de
seguridad; el planificador ya elige duraciones que caben en los límites.

### 5.3 Tiempo: compás y relojes

- **Compás**: reloj maestro `m`. En modo libre avanza a tiempo real; cuando hay voz, vale
  `m_inicio_voz + posición de la voz`.
- **Reloj de cada brazo**: `τ` persigue a `m` con un lazo suave
  (`ritmo = 1 + k·(m − τ)`, acotado y filtrado). Si la voz se detiene, el ritmo cae a cero
  con suavidad y el gesto queda suspendido; si la voz se adelanta, el ritmo sube hasta un
  máximo. Parar un brazo es llevar su ritmo a cero y después congelar su línea.
- Los gestos se programan en tiempo de compás, de modo que **dos brazos siguen la misma
  voz** sin comunicarse entre sí.

### 5.4 Cualidades expresivas (Laban)

`Cualidades`: `amplitud` (0–1), `peso` (−1 ligero … +1 firme), `tiempo` (−1 sostenido …
+1 súbito), `espacio` (−1 indirecto … +1 directo), `flujo` (−1 libre … +1 contenido),
`curvatura` (0–1), `tension` (0–1). Se traducen en: duración, asimetría del ritmo, retardos
de sucesión, anticipación, rebase, altura del arco, arrastre de muñeca y respiración.
Los **estilos con nombre** (solemne, entusiasta, misterioso, didáctico, tierno, dramático)
son conjuntos de cualidades definidos en la configuración.

### 5.5 Cinemática

- A partir del **URDF oficial** del SO-101 (`so101_new_calib.urdf`, repositorio
  TheRobotStudio/SO-ARM100). Se guarda una copia reducida solo con las articulaciones.
- Directa: cadena de transformaciones; da los puntos de todos los eslabones (para colisiones
  y dibujo), la punta y el eje de la herramienta.
- Inversa: numérica (Levenberg–Marquardt) sobre 4 articulaciones, con el giro de muñeca
  fijado. Tarea: posición de la punta (3) + elevación de la herramienta (1, prioridad baja).
  Si no hay solución devuelve `FueraDeAlcance`; no aproxima en silencio.
- **La cinemática inversa solo se usa en las poses clave**; entre ellas se interpola en el
  espacio de articulaciones (arcos naturales, sin tirones cerca de las posiciones extremas).
- Correspondencia modelo ↔ LeRobot: signo y desfase por articulación, en la configuración.

### 5.6 Gestos

Dos familias de poses:

- **Apuntar a la obra**: la punta se coloca sobre el rayo hombro → punto, a una fracción del
  alcance, con la herramienta alineada con el rayo y respetando la separación mínima con la
  obra. Sirve igual si la obra está lejos (apunta) o al alcance (se acerca sin tocar).
- **Pose expresiva**: `alcance`, `azimut`, `altura`, `elevacion`, `giro`, `pinza`, escaladas
  por la amplitud alrededor de una pose neutra.

| Función | Qué expresa |
|---|---|
| `frase_de_movimiento` | Lista de gestos de una frase, anclados a palabras, ejecutada como una sola curva |
| `senalar` | Apunta a un punto de la obra y sostiene |
| `trazar` | Recorre una línea o contorno de la obra |
| `abarcar` | Barre una zona con la pinza abierta |
| `dibujar_forma` | Círculo, espiral, onda, vertical, horizontal, zigzag, ocho; sobre la obra o en el aire |
| `ondular` | Agua, tela, luz, música |
| `elevar` / `descender` | Importancia, crecimiento, caída, peso |
| `medir` | Grande/pequeño con la apertura de la pinza |
| `contrastar` | "Por un lado… por otro" |
| `suspender` | Pausa contenida antes de una idea clave |
| `presentar`, `recoger`, `reposo` | Abrir hacia fuera, recogerse, descanso |
| `gesto_libre`, `definir_gesto` | Poses clave propuestas por ER 2; pasan por el mismo motor |
| `matizar` | Cambia energía, amplitud o tempo sin reiniciar el movimiento |
| `estado`, `parar` | Consulta y parada |

Con dos brazos: `espejo`, `canon` (uno sigue al otro con retraso) y principal + acompañante.
Los acentos de la voz no son una función: son bultos pequeños en la capa de gestos.

## 6. Coordinación voz–gesto

### 6.1 Partitura

Unidad común entre voz y gestos. Cada **frase** tiene texto, palabras con tiempos (estimados
o reales), **gestos anclados a palabras** (no a segundos), acentos y pausa posterior.
Se guarda en JSON; es la base del modo ensayo (reproducir sin internet).

### 6.2 Contrato de la voz

```
preparar(frase)  → duración y tiempos de palabra (reales o estimados)
iniciar(t), pausar(t), reanudar(t), interrumpir(t)
posicion(t)      → segundos de partitura ya dichos
estado           → inactiva | hablando | pausada | terminada | interrumpida
```

| Variante | Cuándo | Origen del tiempo |
|---|---|---|
| `VozMuda` | Fase 1–2 | Subtítulos; tiempos estimados por sílabas |
| TTS | Cuando se quiera | Posición real del audio reproducido |
| Voz externa | IA de voz futura | Otro programa avisa de su progreso por una conexión local |

**Requisito para la IA de voz futura**: el sistema debe conocer el texto **antes** de que
suene (al menos una frase por adelantado). Si la voz improvisa y solo se oye el audio, los
brazos solo pueden seguir ritmo y entonación; los gestos de señalar llegarían tarde.

### 6.3 Director

Para cada frase: prepara la voz → planifica los gestos de forma que su **ápice** caiga en la
palabra ancla menos un adelanto configurable (el gesto llega con la palabra o un instante
antes, nunca después) → verifica la seguridad → los programa en el compás → arranca la voz.
Si la preparación del primer gesto no cabe, la voz empieza un poco más tarde.
Si un gesto no cabe en su hueco, se replanifica con **menos amplitud**, nunca más rápido.

Desajustes: voz retrasada o cortada → gesto suspendido; voz adelantada → el reloj del brazo
acelera con límite; voz interrumpida → los brazos se recogen al reposo; retrasos fijos de
altavoz y motores → `compensacion_s` en la configuración.

## 7. Seguridad (siempre local)

- **Antes de aceptar un gesto** se simula su plan completo y se rechaza, con un mensaje que
  ER 2 pueda entender, si: se sale del rango de una articulación, baja de la altura mínima
  sobre la mesa, **invade la separación mínima con la obra**, **acerca dos brazos por debajo
  de la distancia mínima (se comprueban todos los eslabones, no solo las pinzas)** o hace
  coincidir a los dos brazos en la zona compartida.
- **En cada ciclo**: filtro de velocidad/aceleración/tirón, comprobación de altura, obra y
  distancia entre brazos, y vigilancia de carga, temperatura y error de seguimiento.
  Si algo falla, el brazo se detiene con suavidad y lo comunica.
- **Parada de emergencia**: `Esc` o `F12` (terminal y ventana de vídeo) detienen todo
  manteniendo la posición; segunda pulsación o `Ctrl+C` quitan el par. No pasa por el bucle
  de la IA.
- **Pérdida de conexión con ER 2**: termina la frase en curso y va al reposo.
- **Arranque**: la posición leída es el objetivo inicial (sin saltos). **Cierre**: reposo
  lento y después se quita el par.
- **Uso prolongado en museo** (añadido): la pose de reposo debe exigir poco par; la
  temperatura se vigila y, si sube, se reduce la energía y se alargan los reposos.
- **Nunca se mueve hardware real durante el desarrollo sin confirmación del usuario.**

## 8. Concurrencia

- **Un hilo por brazo** a 100 Hz (configurable) con reloj de alta resolución; en Windows se
  pide resolución de 1 ms al sistema. Mide el jitter.
- Las órdenes llegan desde otros hilos: la planificación (cinemática inversa) se hace
  **fuera** del cerrojo del brazo; solo la inserción final en la línea lo toma un instante.
- **Director** en su propio hilo. **ER 2 y la terminal** (Fase 2) en un bucle `asyncio`.
- Todo el motor es **determinista y avanzable por pasos** (`Sistema.avanzar(dt)`), lo que
  permite tests rápidos sin hilos ni esperas.

## 9. Estructura del código

```
pyproject.toml
config/so101er.toml            configuración editable
docs/CONTEXTO_TECNICO.md       este documento
src/so101er/
  config.py                    carga y validación, errores en español
  geometria.py                 obra (plano + homografía), marcos de los brazos, distancias
  cinematica/modelo.py         directa e inversa; so101.urdf reducido
  control/perfiles.py          escalón, bulto, deformación temporal
  control/linea.py             submovimientos y línea de movimiento
  control/reloj.py             compás y reloj de brazo
  control/cualidades.py        cualidades de Laban → dinámica
  control/capas.py             respiración y arrastre de muñeca
  control/filtro.py            filtro de velocidad/aceleración/tirón
  control/gestos.py            biblioteca de gestos → planes
  control/coreografo.py        motor de un brazo
  control/seguridad.py         validación de poses y planes, vigilancia
  hardware/base.py, sim.py     interfaz de brazo y brazo simulado
  sincronia/partitura.py       partitura y estimación de tiempos
  sincronia/voz.py             contrato de voz y voz muda
  sincronia/director.py        coordinación voz–gesto
  sistema.py                   ensambla todo; hilos o pasos
  interfaz/visor.py            dibujo de la escena y ventana
  interfaz/consola.py          consola manual
  cli.py                       comando so101er
tests/
```

## 10. Fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Configuración, simulación, cinemática, motor de movimiento, gestos, seguridad, partitura y reloj de voz, consola manual | **Hecha** (ver apartado 11) |
| 2 | Narrador, ER 2 (en directo y estándar), voz muda, contra la simulación | Pendiente |
| 3 | Backend real con LeRobot y calibración, un brazo | Pendiente |
| 4 | Dos brazos reales, ajuste fino de la expresividad | Pendiente |

## 11. Estado de implementación

### Fase 1 — hecha (2026-11-14)

Implementado y verificado en simulación, sin hardware ni clave de API. **74 tests pasan.**

**Qué hay**

- `so101er demo` (por pasos, con informe y vídeo), `so101er manual` (tiempo real, con
  ventana y consola), `so101er estilos`. `so101er run` avisa de que llega en la Fase 2.
- Los 14 gestos de la tabla del apartado 5.6 (todos menos `definir_gesto`, que se hará con
  ER 2), más `matizar`, `parar`, `estado` y `frase_de_movimiento` en
  `agente/herramientas.py` (`ejecutar_llamada`), que es la puerta que usará ER 2.
- Partitura, voz muda, director y compás; acentos automáticos en palabras con contenido.
- Seguridad completa en simulación; visor con la obra, los brazos y la velocidad de la punta.

**Medidas de la demostración (6 frases, 41 s, dos brazos)**

- Velocidad, aceleración y tirón máximos: 65 %, 65 % y 50 % de los límites configurados.
  El filtro de seguridad no llega a actuar.
- 12 gestos anclados; todos planificados 80 ms antes de su palabra (el adelanto configurado).
- Distancia mínima entre brazos: 245 mm (límite: 70 mm). Ninguna alerta.
- Sincronía ejecutada: desfase brazo–voz inferior a 60 ms con la voz a 0,75×, 1× y 1,2×.
- Jitter del bucle de control en Windows: medio ≈ 0,2 ms, máximo ≈ 5 ms.
- Precisión al señalar: error inferior a 15 mm sobre la obra (más la respiración).

**Detalles de implementación que no estaban en el diseño inicial**

- **Reducción automática por seguridad**: si el plan de un gesto no es seguro, se
  replanifica con el 70 % y el 45 % de amplitud, flujo contenido y sin arco; solo si
  tampoco así es seguro se rechaza. La respuesta lleva el aviso "gesto reducido…".
- **El reloj del brazo estima el ritmo del compás** (medido y filtrado). Sin esto, una voz
  más lenta de lo estimado dejaba al brazo adelantado unos 90 ms.
- **Moduladores suaves** (`Suave`, 2.º orden): energía, respiración y arrastre nunca cambian
  de golpe. Cambiarlos en seco al empezar un gesto producía picos de aceleración.
- **Duraciones conscientes del tirón**: `duracion_minima` calcula la duración de cada
  submovimiento para que quepa en velocidad, aceleración y tirón, con margen para que el
  reloj acelere hasta 1,4×. Los caminos arrancan y terminan con pasos más largos.
- **Acentos blandos**: bultos de 0,6 s o más y pocos grados; con 0,38 s eran bruscos.
- **Cuadro sintético** para la simulación (cielo, sol, montañas, lago, árbol, casa).
- **Hilos**: `sys.setswitchinterval(0.0005)` para que planificar un gesto no retrase el
  control (el pico de jitter bajó de 39 ms a 5 ms).

**Limitaciones conocidas**

- La cinemática inversa numérica tarda unos 2–10 ms por pose; un trazo largo se planifica
  en 60–160 ms. Suficiente por ahora; si con hardware el jitter molesta, la planificación
  pasará a otro proceso.
- Con dos gestos muy solapados en el mismo brazo, el movimiento se mezcla (es correcto y
  suave, pero menos legible). ER 2 deberá espaciarlos; el prompt de sistema lo indicará.
- La medida de sincronía del informe de `demo` es la planificada; la ejecutada se mide en
  los tests.
- En modo un brazo, la demostración asigna al único brazo los gestos de los dos.
- La ventana de vídeo y las teclas de emergencia se han probado arrancando y cerrando el
  programa, pero no de forma interactiva (teclado y ratón) en esta sesión.
- Nada se ha probado aún con motores reales: la suavidad final depende de la holgura y la
  vibración a baja velocidad de los servos (Fase 4).

**Entorno de desarrollo de esta sesión**

- El Python de Microsoft Store no pudo crear el entorno virtual dentro de la carpeta del
  proyecto por la longitud de la ruta; se creó en una carpeta temporal. En una carpeta de
  ruta corta, `python -m venv .venv` funciona (ver README).

### Fase 2 — escrita, pendiente de probar con la API real (2026-11-14)

Todo el código de la Fase 2 está escrito y probado con **sesiones falsas** (79 tests en
total). **No se ha podido probar contra Google**: falta `GEMINI_API_KEY`.

**Quién decide qué (con voz `live`)**

1. **La foto**: la imagen más reciente de la carpeta `obra/` es el cuadro. Se ve en MuJoCo
   y es la imagen que reciben los dos modelos (con una marca de adónde apunta cada brazo).
2. **Gemini 3.8 Live (el guía)** ve la imagen y decide **qué se dice**. Genera la voz.
   No sabe nada de gestos.
3. **El programa** retiene esa voz unos segundos (`voz.retardo_s`), trocea su transcripción
   en fragmentos de hasta 7 palabras y numera las palabras.
4. **Gemini Robotics ER 2 (el coreógrafo)** recibe cada fragmento con la imagen y decide
   **qué gesto, hacia qué punto `[y, x]`, con qué estilo y en qué palabra**. Llama a
   `frase_de_movimiento(frase_id, gestos)`.
5. **El programa** convierte cada gesto en trayectoria, comprueba la seguridad y lo ancla
   al reloj del altavoz: como reproduce él el audio, sabe con exactitud cuándo suena cada
   palabra. Si ER 2 no contesta a tiempo, los brazos marcan el ritmo por su cuenta.

Con voz `muda` no hay guía: el usuario escribe qué explicar y ER 2 redacta también el
texto (`frase_de_movimiento(texto, gestos)`), que sale en subtítulos.

**Piezas nuevas**

- `agente/herramientas.py`: 6 funciones para ER 2 (`frase_de_movimiento`, `gesto`,
  `definir_gesto`, `matizar`, `parar`, `estado`), generadas según el modo; formatos para
  la Live API (`behavior: BLOCKING`, `parameters_json_schema`) y la Interactions API.
- `agente/prompt_sistema.py`: prompts del coreógrafo (ER 2) y del guía (3.8 Live).
- `agente/er2.py`: `ER2Directo` (Live API: compresión de contexto, reanudación de sesión,
  reconexión con reenvío de contexto, los mensajes no urgentes esperan a `turn_complete`)
  y `ER2Estandar` (Interactions API).
- `agente/guia.py`: sesión de Gemini 3.8 Live (audio de salida a 24 kHz, micrófono a
  16 kHz, vídeo a 1 fps, transcripción de salida y de entrada, interrupciones).
- `sincronia/flujo.py`: `VozFlujo` (reproducción con retardo; su posición es el reloj) y
  `DirectorFlujo` (fragmentos, acentos, anclaje de gestos, gestos que llegan tarde).
- `interfaz/audio.py` (altavoz y micrófono con `sounddevice`), `interfaz/camara.py`,
  `interfaz/registro.py` (JSONL en `registros/`), `sesion.py` (`so101er run`).
- `hardware/mujoco_sim.py` y `montaje.py`: escena de MuJoCo con el modelo oficial
  (`mujoco_modelo/`, descargado de TheRobotStudio/SO-ARM100), física en tiempo real sin
  contactos y la foto como textura. `obra.py`: elige la foto y ajusta el rectángulo.

**Comprobado**

- `so101er demo --mujoco`: la demostración completa en tiempo real en MuJoCo, sin alertas;
  error de seguimiento de los actuadores ≈ 0,1°; jitter máximo ≈ 3,5 ms.
- La cinemática propia coincide con la de MuJoCo (sitio `gripperframe`) al décimo de mm.
- Con sesiones falsas: llamadas, error y corrección, reconexión con reanudación, bucle
  estándar, y voz en flujo con gestos que llegan con la palabra (entre 250 ms antes y
  50 ms después).

**Sin comprobar (necesita la clave y, para la voz, altavoz y micrófono)**

- Que Google acepte la configuración tal cual: `parameters_json_schema` en la Live API de
  ER 2, `word_timestamp` en la transcripción de salida (desactivado por defecto), etc.
- A qué ritmo entrega 3.8 Live el audio y la transcripción, y cuánto tarda ER 2 en
  responder. De eso depende `voz.retardo_s` (regla: duración de un fragmento + respuesta
  de ER 2; por defecto 4 s).
- El audio real (`sounddevice`) y el eco: por defecto el micrófono se silencia mientras
  suena la voz, así que un visitante no puede interrumpir a mitad de frase.
- La calidad de los gestos que elija ER 2 con el prompt actual.

**Cambios respecto a lo comprobado en la documentación**

- La Live API con vídeo admite 1 fotograma por segundo. A ER 2 no se le manda vídeo
  continuo: cada mensaje lleva la imagen del momento (más barato e igual de útil).
- La vigilancia de carga de motor ahora exige unos 2 s seguidos de sobrecarga: los picos
  al moverse son normales (se vio en MuJoCo).

### Cambio posterior: ER 2 compone todo el movimiento (2026-11-14)

El usuario no quiere expresiones prefabricadas: **la forma de cada movimiento la decide
ER 2 mirando la obra**. Hay dos modos, elegibles con `er2.composicion` o
`so101er run --composicion`:

- **`libre` (por defecto).** A ER 2 no se le ofrece ningún gesto con nombre. Sus funciones
  son `frase_de_movimiento(texto | frase_id, movimientos)`, `movimiento`, `matizar`,
  `parar` y `estado`. Un movimiento es `{brazo, puntos, estilo, caracter, mantener}` y
  cada punto clave es:
  - `mira: [y, x]` — el brazo apunta a ese lugar de la obra; dos `mira` seguidos sin pausa
    hacen que la punta recorra la línea entre ellos;
  - o una pose en el aire: `alcance`, `altura`, `lado`, `inclinacion`;
  - más `giro`, `pinza`, `pausa`, `duracion` y `ancla` (palabra en la que debe llegar).
  El motor (`_trayectoria` en `control/gestos.py`) solo une los puntos con suavidad, ajusta
  el ritmo entre puntos anclados a palabras y aplica la seguridad. `estilo` y `caracter`
  cambian cómo se unen los puntos, no los puntos.
- **`biblioteca` (el modo anterior, conservado en `agente/biblioteca.py`).** ER 2 elige
  entre los 14 gestos con nombre y ajusta sus parámetros.

La biblioteca de gestos sigue en `control/gestos.py`: la usan la consola manual, la
demostración sin IA y el modo `biblioteca`. Los acentos automáticos de la voz y la
respiración siguen siendo locales en los dos modos (son ritmo, no expresiones).

Otros cambios: al acabar una explicación, el reposo espera a que los brazos terminen su
movimiento (antes lo cortaba si duraba más que la frase); `frase_de_movimiento` valida
los movimientos al recibirlos, para que ER 2 vea el error en la respuesta. 82 tests.

Sin comprobar: qué movimientos compone ER 2 de verdad con este prompt y cuánto tarda en
escribirlos (más texto que antes, así que `voz.retardo_s` puede tener que subir).

### Primera prueba real con ER 2 (2026-11-14)

`so101er run --mujoco` (voz muda, composición libre) funciona contra Google con la clave
del usuario (guardada como variable de entorno de su usuario de Windows; el programa la
lee también del registro, sin reiniciar nada).

- ER 2 (`gemini-robotics-er-2-streaming-preview`) aceptó la configuración tal cual:
  `parameters_json_schema`, `behavior: BLOCKING`, compresión y reanudación de sesión.
- A «Explica este cuadro en tres frases breves» respondió con tres llamadas a
  `frase_de_movimiento`: la primera a los 4,7 s y las siguientes cada 2 s aproximadamente.
  Nuestras funciones contestaron en 22–263 ms.
- Compuso él los movimientos: localizó el sol `[200, 780]`, las montañas, el árbol
  `[450, 200]`, la casa `[600, 680]` y el estanque `[850, 500]`, repartió los brazos por
  lado y ancló los puntos a palabras. Usó casi solo puntos `mira` y una pose en el aire:
  señala bien, pero aún expresa poco con el cuerpo. Hay que afinar el prompt.
- Corregido tras la prueba: en MuJoCo la consigna a 100 Hz saturaba los actuadores (muy
  rígidos) y disparaba falsas alarmas de carga; ahora la consigna se suaviza a la
  frecuencia de la física y la carga es una media. También un error al cerrar la sesión.

### Tres cámaras y estilo teatral (2026-11-14, hecho y probado con ER 2)

**Cámaras (en MuJoCo, `hardware/mujoco_sim.py`)**

- `fija`: entre los dos brazos, a la altura del centro de la obra, mirándola (640×480,
  50° de campo vertical). **Los puntos `[y, x]` de ER 2 se dan sobre esta imagen**; la
  homografía imagen → obra se calcula de la propia cámara (`homografia_fija`).
- `izq_muneca` / `der_muneca`: en la posición de la cámara del modelo oficial
  (`so101_new_calib_camera.xml`, que trae el soporte y la carcasa pero no la cámara
  simulada), mirando a lo largo de la herramienta (70°).
- **Puntero**: una esfera de color por brazo (naranja izq, verde der) sobre la obra, donde
  la herramienta corta su plano. Se ve en las tres cámaras y en la ventana.
- Un hilo toma las tres imágenes cada 0,4 s. Cada mensaje a ER 2 lleva las tres, cada una
  con su rótulo. El guía (3.8 Live) recibe la fija.
- Dato del modelo: el eje de la herramienta es `−z` del cuerpo `gripper`; el sitio
  `gripperframe` del MJCF está girado respecto al URDF (su posición sí coincide).

**Estilo: actor que sobreexpresa, pero relajado**

- Prompt de ER 2 reescrito: gestos muy amplios, nunca quieto señalando, los dos brazos en
  todas las frases, de 5 a 9 puntos clave por brazo, emoción por tamaño y forma y no por
  velocidad; incluye un ejemplo.
- `movimiento.exageracion = 1.4`: las poses en el aire que compone ER 2 se alejan de la
  neutra ese factor. Al apuntar, el alcance por defecto sube a 0,8.
- Los movimientos compuestos son siempre relajados: `tiempo ≤ −0,2`, y por defecto con
  arcos (`curvatura ≥ 0,6`) e inercia (`flujo ≤ −0,3`).
- Respiración 1,8° y acentos mayores. Con voz muda, la frase siguiente espera a que los
  brazos acaben (`voz.espera_al_cuerpo_s`, tope de 6 s).
- **Límite blando de articulaciones** (`limite_blando` en `control/linea.py`): cerca de un
  tope la referencia se comprime con suavidad. Lo usan el coreógrafo y la verificación de
  seguridad, así que ya no se rechazan movimientos amplios por rozar un tope.

**Resultado de la prueba real** («Explica este cuadro en tres frases breves»): tres
frases, dos movimientos por frase (uno por brazo) de 4 a 6 puntos, sin rechazos ni alertas.
La primera respuesta tardó 11 s (antes 4,7 s: ahora van tres imágenes y escribe más); las
siguientes, unos 3 s cada una. ER 2 sigue usando rangos moderados (alturas 0,2–0,7): la
exageración local los amplía, pero el prompt admite más ajuste.

### Los dos brazos de una misma persona (2026-11-14, hecho y probado con ER 2)

El usuario quiere que los brazos se comporten como los de una persona, coordinados entre
sí (separar las manos, una quieta y la otra girando…), no como dos robots independientes.

- **Brazo `"ambos"`**: las dos manos a la vez, en espejo, en un espacio común (el
  "cuerpo", centrado entre las bases). Cada punto da `separacion` (0 = manos juntas en el
  centro … 1 = abiertas), `altura`, `adelante` y `desnivel` (una sube y la otra baja).
  `herramientas._mano_en_el_mundo` lo convierte en una posición por mano (`mundo` en el
  punto clave) y el motor resuelve cada brazo.
- **`circulo`** en un punto clave: la mano gira a partir de ahí (`plano` frontal,
  horizontal o lateral; `radio`, `vueltas`, `sentido`, `ratio` para achatar hasta un vaivén).
- **`repetir`**: la lista de puntos se repite como un ciclo (1–6 veces).
- **Simpatía** (`movimiento.simpatia = 0.12`): cada brazo arrastra un poco al otro
  (pan, hombro y codo), con retardo suave, como si compartieran torso.
- Prompt: sección «Son los dos brazos de una misma persona» con ejemplos.
- Cinemática inversa con jacobiano analítico: de 9 ms a 0,6 ms por pose (una frase larga
  tardaba hasta 4 s en validarse).
- Prueba real: ER 2 usó por su cuenta un `circulo` sobre el sol y `"ambos"` con
  `separacion` de 0,1 a 0,95 para «un lago… se extiende». 86 tests.

### Primera prueba de Gemini 3.8 Live (2026-11-14): conecta, pero el audio llega lento

`so101er run --mujoco --voz live --sin-microfono`:

- **Funciona**: la sesión conecta, la voz se genera, la transcripción llega, `VozFlujo` la
  trocea y ER 2 recibe los fragmentos. Tras enviarle la imagen con la petición, el guía
  describe el cuadro correcto (al principio hablaba sin verlo: se inventó otra escena).
- **Problema principal**: el audio llega a **un tercio de la velocidad real** (unos 6 s de
  voz en 30 s) y después la conexión se cae (`keepalive ping timeout`, cierre 1006). Pasa
  igual en una prueba mínima sin MuJoCo, sin hilos y sin vídeo, así que **no es de
  nuestro programa**: es el servicio en vista previa o la red del equipo. Sin saber cuál.
- **Segundo problema**: ER 2 tarda 8–11 s por fragmento (con una sola imagen), y los
  fragmentos llegan cada 2–3 s. Con un retardo de voz de 9 s todos los gestos llegaron
  tarde y se descartaron. La sincronía en directo con este diseño no está conseguida.
- Cambios hechos: el guía recibe la imagen con cada petición; con voz en directo ER 2
  recibe solo la cámara fija y se le pide brevedad; `voz.retardo_s = 9`; el registro
  guarda cada 2 s el retraso del bucle y el audio recibido y reproducido (`pulso`).
- Opciones para la voz (por decidir): (a) reproducir cada intervención solo cuando haya
  llegado entera: voz continua y ER 2 con tiempo de sobra, a costa de una espera larga;
  (b) que ER 2 escriba el texto, como en voz muda, y sintetizarlo con Gemini TTS: texto
  conocido de antemano y sincronía exacta, pero sin conversación fluida; (c) repetir la
  prueba de Live en otra red u otro momento.

### Voz sintetizada: ER 2 escribe y una voz local lo lee (2026-11-14, hecho y probado)

Decisión del usuario tras ver que Gemini 3.8 Live llega lento: **ER 2 escribe el texto y
una voz lo lee**. Es el modo por defecto (`voz.proveedor = "local"`).

- `sincronia/voz_sintetizada.py`: `VozSintetizada` cumple el contrato de voz del director.
  El audio se reproduce por el altavoz (`interfaz/audio.Altavoz`) y **la posición de la
  reproducción es el reloj de la frase**. Cada frase se empieza a sintetizar en segundo
  plano en cuanto ER 2 la encola (`precalentar`).
- **`SintetizadorWindows`** (`--voz local`): voz instalada en Windows, vía
  `sincronia/voz_windows.ps1` (System.Speech). En el equipo del usuario: «Microsoft Helena
  Desktop» (es-ES). Sin red; unos 2,7 s por frase (arranque de PowerShell). Da la marca de
  cada palabra; el motor la cuenta como bytes/32000, así que se corrige con los bytes por
  segundo del WAV y se comprueba contra el audio (`_cuadran`). Resultado: marcas a unos
  20 ms del audio real. Si no cuadran, se estiman por sílabas.
- **`SintetizadorGemini`** (`--voz tts`, `gemini-3.8-flash-tts`): funciona (devuelve WAV),
  pero tardó **11–15 s por frase** en este equipo; no da tiempos de palabra (se estiman).
- El director ya no retiene su cerrojo mientras se sintetiza la voz: antes, encolar una
  frase podía tardar hasta 10 s en contestar a ER 2.
- **Prueba real** (`so101er run --mujoco`): tres frases escritas por ER 2, dichas por la
  voz local, con los dos brazos, sin alertas. Tiempos: ER 2 tarda unos 14 s en dar la
  primera frase; la voz empieza unos 6 s después (síntesis, planificación y preparación
  del primer gesto). Unos 20 s desde la petición hasta la primera palabra.
- **No comprobado**: si el audio y los gestos se perciben sincronizados (lo juzga el
  usuario, que oye el altavoz); la calidad de la voz Helena, que es antigua y algo robótica.
- **Señales de sincronía** (pregunta del usuario): ya existen y van en los dos sentidos.
  ER 2 → local: cada punto clave lleva `ancla` (la palabra en la que debe llegar). Local →
  ER 2: respuesta a cada función, avisos, «han terminado» y las imágenes. El reloj lo tiene
  el programa local porque es quien reproduce el audio; ER 2 no puede reaccionar en
  milisegundos.
- **Ideas pendientes**: voz local más natural (Piper, también en Linux); micrófono con
  reconocimiento de voz local para hablarle al sistema (el texto iría a ER 2); mantener el
  proceso de voz abierto para bajar los 2,7 s por frase.

### Hilos que se estorbaban: paradas falsas en la sesión completa (2026-11-14, corregido)

Al repetir `so101er run --mujoco` con voz local, una pasada salió mal: los brazos se
detenían con «error de seguimiento de 16–31°», ER 2 recibía esos avisos y añadía frases
(cinco en vez de tres), y una función tardó 10 s en contestar. El equipo no estaba
saturado (i7-12700H, carga del 5 %): eran los hilos de Python compitiendo entre sí, y la
física de MuJoCo se quedaba atrás respecto a las consignas. Cambios:

- El bucle de control ya no espera en activo: duerme hasta su hora. Jitter máximo de
  1–3 ms (antes, picos de 40–90 ms).
- Las cámaras de MuJoCo se dibujan **solo cuando se pide una imagen**, no cada 0,4 s.
- La voz se sintetiza de frase en frase, no tres procesos a la vez.
- En simulación, el aviso de error de seguimiento exige 1,5 s seguidos (en hardware real
  siguen siendo 0,3 s): si la física se retrasa no es un brazo bloqueado.
- El registro guarda en cada `pulso` el jitter y las veces que la física se ha saltado
  tiempo (`saltos_fisica`).

Dos pasadas seguidas después del cambio: tres frases cada una, sin paradas; las funciones
contestan a ER 2 en 12–231 ms. En una, ER 2 pidió un giro que no cabía, recibió el error
y lo corrigió solo en la llamada siguiente. Queda un retraso puntual de unos 0,5 s en el
bucle principal al pedir las imágenes para ER 2.

### Arranque, volumen y ritmo de la sesión con voz (2026-11-14, tras ver el usuario la demo)

El usuario vio la sesión y señaló: la voz sonaba muy baja, no arrancaba con la simulación
y a ratos «se rallaba» (se quedaba como atascada). Causas y cambios:

- **Volumen**: la voz de Windows salía a −18 dBFS. `voz.volumen = 2.5` aplica ganancia
  con limitador suave (`realzar`): ahora −12 dBFS.
- **Retraso del altavoz**: el dispositivo añade 0,09–0,18 s que no se descontaban. El
  altavoz se abre con latencia baja y `VozSintetizada.posicion` resta la latencia real.
- **Síntesis instantánea**: `voz_windows.ps1 -Servidor` mantiene la voz cargada en un
  proceso abierto; cada frase tarda 0,01–0,02 s (antes 2,7 s).
- **ER 2 más rápido en la primera frase**: al pedir la explicación se manda solo la cámara
  fija (las de muñeca van en las comprobaciones), `thinking_level = "low"`
  (`er2.razonamiento_directo`; la Live API lo aceptó) y el prompt pide una primera frase
  corta. Primera llamada de ER 2 a los 3–4 s (antes 10–14 s); primera palabra unos 4–5 s
  después de pedir (antes unos 20 s).
- **La voz ya no espera hasta 4 s al primer gesto**: `voz.entrada_max_s = 2.0`. Con 1,2 s
  el primer gesto llegaba hasta 0,4 s tarde.
- **El atasco**: los movimientos duraban 8–10 s y las frases 3–4 s; la voz esperaba al
  cuerpo hasta 6 s entre frases. Ahora, al empezar una frase, lo que quedaba pendiente de
  la anterior se abandona con suavidad (lo ya en marcha termina) y el movimiento nuevo se
  funde con él; `voz.espera_al_cuerpo_s = 1.5`; y a ER 2 se le pide que el movimiento dure
  lo que la frase (3–4 puntos por brazo). Frases cada 5–6 s, sin huecos.
- ER 2 a veces añadía una frase de despedida al recibir el aviso de «han terminado»: el
  aviso ahora le pide contestar solo «hecho».
- **`so101er run --mujoco --pedir "…"`**: hace una petición y cierra al acabar.
- Coste de la rapidez: con razonamiento bajo ER 2 compone movimientos más simples (unos
  2 puntos por brazo y frase en la última prueba). Si se quiere más riqueza:
  `er2.razonamiento_directo = "medium"`, a cambio de tardar más.

### Requisitos nuevos del usuario (pendientes)

- **Conversación por voz**: el visitante habla con el sistema y este responde hablando
  (Gemini 3.8 Live con micrófono). El conjunto es una interfaz entre la persona y el
  sistema robótico: voz y movimiento como una sola respuesta.

### Siguiente

1. Con la clave: probar `so101er run --mujoco` (voz muda) y ajustar lo que la API rechace.
2. Probar `so101er run --mujoco --voz live`, medir tiempos y ajustar `retardo_s`.
3. Ajustar el prompt del coreógrafo viendo los gestos que elige.
4. Modo ensayo: guardar la partitura generada y reproducirla sin conexión.
5. Fase 3: backend real con LeRobot, cámara real y calibración.

### Plan original de la Fase 2 (referencia)

1. `agente/herramientas.py`: generar los esquemas JSON de las funciones (Live API e
   Interactions API) a partir de la tabla de gestos; añadir `definir_gesto`.
2. `agente/prompt_sistema.py`: prompt según el modo (escena, brazos, coordenadas `[y, x]`,
   estilos, reglas de seguridad, espaciar los gestos, usar `estado`).
3. `agente/narrador.py`: Gemini escribe el guion por frases a partir de la imagen.
4. `agente/live.py`: sesión Live con vídeo a 1 fps, avisos solo tras `turn_complete`,
   compresión de contexto, reanudación y reconexión.
5. `agente/estandar.py`: bucle con la Interactions API.
6. Cámara sintética para ER 2 (la obra con los brazos superpuestos) y registro de sesión.
7. Modo ensayo: guardar partitura generada y reproducirla sin conexión.

## 12. Pendiente de decidir por el usuario

- Permiso para instalar `uv` (necesario para LeRobot en la Fase 3).
- Qué cámara se montará y dónde; montaje físico de brazos y obra.
- Imagen de la obra para la simulación (por ahora se usa un cuadro sintético).
- Qué IA de voz se usará y si acepta texto por adelantado.
- `GEMINI_API_KEY` restringida, para la Fase 2.

## 13. Fuentes

- https://ai.google.dev/gemini-api/docs/robotics-overview
- https://ai.google.dev/gemini-api/docs/robotics-streaming
- https://ai.google.dev/gemini-api/docs/models
- https://huggingface.co/docs/lerobot/so101
- https://github.com/huggingface/lerobot (`src/lerobot/robots/so_follower/so_follower.py`)
- https://github.com/TheRobotStudio/SO-ARM100 (`Simulation/SO101/so101_new_calib.urdf`)

