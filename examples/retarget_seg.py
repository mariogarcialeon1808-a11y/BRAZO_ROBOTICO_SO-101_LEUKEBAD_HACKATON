"""Dos clips SeG -> demostración geométrica conservadora del SO-101, sin motores.

Ejecutar desde la raíz del proyecto tras instalarlo en modo editable.
"""
from pathlib import Path
import numpy as np
from so101er.config import cargar
from so101er.control.semantico import MotorGestos,ejemplos
from so101er.control.referencias import Motivo,forma_en_marco
from so101er.gestos_demo import exportar


def main():
    root=Path(__file__).resolve().parents[1]
    cfg=cargar(root/'config/so101er.toml')
    motor=MotorGestos(cfg); _,_,enc=ejemplos(motor)[0]
    frame=motor.marcos['izq']
    cases=[]
    for file in sorted((root/'datos/referencias/seg').glob('*.json')):
        m=Motivo.cargar(file)
        # Dataset X=lateral, Y=vertical, Z=adelante. Base SO-101 x=adelante.
        # Limitamos lateralidad a 1 mm porque no hay libertad de yaw independiente.
        g=forma_en_marco(m,frame.a_mundo([motor.modelo.eje_pan[0]+235,0,220]),
                        frame.rot@np.array([[0,0,1],[1,0,0],[0,1,0]]),
                        [1,15,15],frame.dir_a_mundo([1,0,0]),'izq')
        cases.append((m.id+' · forma humana adaptada',g,enc))
    if not cases: raise RuntimeError('faltan las muestras locales de SeG')
    print(exportar(cfg,root/'salidas/formas_humanas',casos=cases))


if __name__=='__main__': main()
