# Recursos de terceros

La cinemática nominal y los recursos visuales SO-101 proceden de
[TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100), directorio
`Simulation/SO101`. Se conserva su licencia Apache 2.0 en
`licenses/SO-ARM100-Apache-2.0.txt`.

`src/so101er/cinematica/so101.urdf` es una reducción a articulaciones del URDF de
origen. Los recursos de `src/so101er/mujoco_modelo/` se integran en una escena de
dos brazos con cuadro y adquisición por sensores declarados; la escena construida
por la aplicación añade esos elementos. No se cambia la autoría de los recursos.

Los corpus SeG, BEAT2 y MM-Conv y los pesos de reconocimiento de voz se obtienen
por separado bajo sus propios términos. No se redistribuyen aquí sus muestras,
motivos derivados ni pesos. El catálogo de procedencia y los conversores propios
sí están incluidos. Ver `docs/GITHUB.md` y `datos/fuentes_gestos.json`.

Las dependencias Python conservan las licencias de sus proyectos. No se asigna
automáticamente una licencia de esas dependencias al código propio del repositorio.
