# Contenido del repositorio y arranque tras clonar

Este repositorio contiene el código, pruebas, configuración nominal, dibujo de
demostración, geometría SO-101 y vídeos seleccionados. Incluye los gestos amplios,
retorno a reposo, pinzas, acompañamiento prosódico y sincronía con el reloj de audio.

## Instalación Windows, Python 3.12

```powershell
git clone https://github.com/GuillermoRosale5/so101-cuadro-gestos-publico.git
cd so101-cuadro-gestos-publico
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[integrado,dev]"
.\.venv\Scripts\python.exe -m so101er.cli iniciar --raiz . --voz local --demo
```

La demo con voz local de Windows no necesita claves de nube. Para preguntar a la
IA, configurar `GEMINI_API_KEY` en el entorno. Para usar ElevenLabs, configurar
`ELEVENLABS_API_KEY` y `ELEVENLABS_VOICE_ID`, y quitar `--voz local`. Los nombres
están en `.env.example`; copiarlo a `.env` no lo carga automáticamente: indicar
esa ruta en `[conversacion].env` de `config/so101er.toml`, o exportar las variables.

En el portátil original las claves siguen en su ubicación previa; no están aquí.
Los `.cmd` eligen el entorno del portátil, `.venv` local o `python`, en ese orden.
El dibujo se genera al arrancar si no existe. MuJoCo necesita escritorio y OpenGL.

Para el micrófono, instalar además los pesos locales de Whisper base:

```powershell
.\.venv\Scripts\python.exe tools\instalar_microfono.py
```

Descarga `Systran/faster-whisper-base` desde Hugging Face a
`datos/modelos/whisper_base`. Esa descarga no forma parte de Git.

## Datos locales y demostraciones

`datos/referencias/` conserva en el portátil las muestras SeG, BEAT2 y MM-Conv,
los motivos transformados y sus metadatos. Se excluye de Git respetando sus términos
y las exclusiones del proyecto. El catálogo de fuentes y los importadores sí están
incluidos. Consultar `REFERENCIAS_HUMANAS.md` y `ARRANQUE_INTEGRADO.md` para importarlas
desde copias obtenidas legítimamente. Los datos y pesos locales no se han borrado.

Sin esas muestras, la aplicación funciona con los gestos geométricos propios y
acompañamiento prosódico. El selector de referencias requiere instalar sus motivos.
Las pruebas de muestras reales se omiten si no están instaladas.

`demos/gestos_amplios.mp4` muestra amplitud, pinzas y retorno a reposo.
`demos/BEAT2_MMConv.mp4` muestra el retargeting a puntos y regiones. Estos vídeos
son de las etapas anteriores al acompañamiento continuo; la versión actual se
prueba en la interfaz con «Demo humana». No son una evaluación de naturalidad.

Las salidas regenerables, logs de conversaciones, cachés, entornos, secretos y pesos
quedan fuera. Se conserva un diagnóstico de la versión continua en `demos/`.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest
```

En la copia preparada para esta publicación: **223 pruebas pasadas y 4 omitidas**.
Las muestras locales no se redistribuyen. El estado de las pruebas físicas y el
problema observado en la demo de MuJoCo están en [ESTADO_ACTUAL.md](ESTADO_ACTUAL.md).

## Guardar todo en GitHub con un solo comando

`GUARDAR_EN_GITHUB.cmd`, con doble clic o desde una terminal, añade todos los cambios, los
confirma y los sube a la rama actual.

- Sin nada más, el mensaje es «Guardado del» con la fecha y la hora.
- `GUARDAR_EN_GITHUB.cmd "Lo que he cambiado"` usa ese mensaje.
- `GUARDAR_EN_GITHUB.cmd /prueba` enseña lo que haría sin confirmar ni subir nada.

La confirmación va firmada solo por el usuario de git de este equipo (`git config user.name` y
`user.email`): no añade ningún coautor. No sube calibraciones, imágenes, claves ni salidas, porque
respeta `.gitignore`; además se niega a guardar si entre los cambios aparece un archivo `.env`,
`.pem` o `.key`. Si la subida falla, lo dice: la confirmación queda hecha en el equipo y basta
con volver a ejecutarlo.
