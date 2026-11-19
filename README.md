# SO-101: cuadro, conversación y gestos humanos

**Estado de desarrollo y comprobaciones actuales:** [ESTADO_ACTUAL.md](docs/ESTADO_ACTUAL.md).

**Dos brazos reales:** selector **Ambos**, montaje medido, vista conjunta y
saludo coordinado. [Uso y perfil vigente](docs/DOS_BRAZOS_REALES.md).
Este perfil sustituye las limitaciones históricas de un único USB activo.

**Programa único con pestañas: `ABRIR_SO101.cmd`.**
[Guía sencilla desde cero: rangos, postura, pruebas y chatbot](docs/GUIA_INICIAL.md).
Los accesos anteriores de calibración, pruebas y chatbot abren la misma ventana.
La calibración manual se hace primero; la alineación relaciona después los encoders
con la postura 3D. Los datos guardados se reutilizan en los próximos arranques.

**Imágenes y vídeo en directo:** en la pestaña 4, **Imágenes…** abre una ventana para
recorrer las fotos de `obra/`, añadir otras, encuadrarlas o tomar una instantánea de la
cámara. Cada imagen se adapta sola al cuadro. La cámara también puede quedar **en directo**
como imagen del cuadro, y **Pantalla 3D** abre una ventana aparte con la escena, esa imagen y
una cara mínima que mueve ojos y boca al hablar. [Uso y límites](docs/IMAGENES.md).

**Cinco idiomas:** español, inglés, alemán, francés y chino, cada uno con su voz. La conversación sigue al idioma de cada
petición, escrita o hablada, y se decide en este equipo; la respuesta de la IA se comprueba
antes de decirla, para que nunca se mezclen. [Cómo funciona](docs/IDIOMAS.md).

**Respuesta rápida:** empieza a hablar con la primera frase, a los 2–3,5 s de preguntar (antes
9–10 s), mientras prepara las demás. La casilla **Frase a frase** de la pestaña 4 permite volver
al turno de antes. [Qué cambia y qué falta por comprobar](docs/RESPUESTA_RAPIDA.md).

**Biblioteca de movimientos:** además de los cinco gestos de siempre, la IA puede pedir 72
movimientos nuevos para direcciones, tráfico, trámites, cantidades, tiempo y trato, con un segundo
movimiento en el otro brazo. Cada frase lleva dos conceptos, uno por brazo y cada uno en su
palabra, y al menos uno dibuja lo que se dice. **Demo biblioteca**, en la pestaña 4, enseña seis.
[Protocolo y reglas](docs/PROTOCOLO_EXPRESIVO.md) ·
[Registro de movimientos y conceptos](docs/REGISTRO_EXPRESIVO.md).

**Cara del robot:** una página con ojos, subtítulos sincronizados y la imagen que se explica, en
su propia ventana (botón **Cara** de la pestaña 4 o `ABRIR_CARA.cmd`). Mira hacia el brazo que
gesticula y cambia de ánimo con lo que se dice. De Javier García Pavón. [Guía](docs/CARA.md).

**Guardar en GitHub:** `GUARDAR_EN_GITHUB.cmd` añade, confirma y sube todo con un solo comando,
firmado con tu usuario de git. [Detalles](docs/GITHUB.md).

**USB real con preparación automática:** `CHATBOT_REAL.cmd`.
[Funcionamiento, avisos y requisitos](docs/CHATBOT_REAL.md). Sin alineación guardada
del brazo elegido no se activa par. Usa un dibujo virtual, sin cámara del entorno.

[Instalación desde GitHub y contenido incluido](docs/GITHUB.md).

USB físico: [ventana sencilla para registrar rangos manuales](docs/CALIBRACION_USB.md),
con `CALIBRAR_USB.cmd`. No activa motores ni habilita todavía los gestos reales.
[Panel con ejes, dos danzas y prueba física limitada de COM7](docs/PRUEBAS_MODELO.md):
`PRUEBAS_SO101.cmd`.

**Habla más continua:** acentos entre gestos, recogidas sin esperas y reloj de
salida del altavoz. El ápice se adelanta 220 ms a su palabra.
[Funcionamiento y comprobación](docs/GESTOS_CONTINUOS.md).

**Perfil amplio:** abanicos con ambos brazos, extensión aproximada del 90–94 %,
retorno a reposo tras cada gesto y pinzas 0–100 %. Señalar mantiene la pinza cerrada.
[Detalles del perfil y su validación](docs/GESTOS_AMPLIOS.md).


Aplicación para dos brazos, con MuJoCo, ER2, voz ElevenLabs y reconocimiento
local por micrófono. **INICIAR_SO101.cmd**, en la carpeta superior, abre el programa
único de configuración y chatbot real. **INICIAR_SIMULACION.cmd** conserva la
demostración separada sin hardware.

La ventana permite preguntar por texto/micro, señalar haciendo clic y barrer regiones
arrastrando un rectángulo. El selector cambia entre referencias SeG, BEAT2 y MM-Conv.
Escape interrumpe voz y movimiento. El visor MuJoCo muestra los dos brazos y el cuadro.

**Estado:** simulación, servicios y controlador USB implementados. La ventana indica
qué rangos y alineaciones están guardados para cada brazo. Cada montaje requiere
comprobación manual antes de activar movimientos reales.
Las rotaciones de BEAT2/MM-Conv se convierten con una antropometría humana nominal,
no con la malla exacta del actor. Los recursos se almacenan para uso local de investigación.

[Arranque, funcionamiento, mediciones y límites](docs/ARRANQUE_INTEGRADO.md)

- Vídeo: `salidas/demo_BEAT2_MMConv.mp4`.
- Diagnóstico USB sin activar motores: `DIAGNOSTICO_USB.cmd`.
- Configuración: `config/so101er.toml`.
- Entorno aislado: `C:\Users\PC\AppData\Local\so101er-runtime`. Al haberse creado desde
  Codex, Windows lo guarda en realidad en `%LOCALAPPDATA%\Packages\OpenAI.Codex_*\LocalCache\Local\so101er-runtime`;
  `ENTORNO_PYTHON.cmd` lo busca en los dos sitios, luego `.venv`, y avisa si ninguno tiene
  las dependencias. Lo usan todos los `.cmd`.
- Dependencias instaladas: `requirements_runtime.lock`.

```powershell
# Entorno ya instalado en este portátil
& C:\Users\PC\AppData\Local\so101er-runtime\Scripts\python.exe -m so101er.cli iniciar --raiz .
# En otro entorno Windows, desde esta carpeta:
python -m pip install -e ".[integrado,dev]"
so101er iniciar --raiz .
python -m pytest
```

Las claves se leen del .env previamente configurado; no se guardan en este proyecto.
La simulación usa jointpos declarados y adquisición con ruido/sesgo/retardo, sin
leer verdad interna como entrada del controlador. El perfil sensorial es nominal.
La validación geométrica no certifica las condiciones de un montaje físico.

Los comandos y documentos de fases anteriores se conservan por reproducibilidad.
Su estado histórico queda sustituido por el documento de arranque integrado.

