"""Vídeo reproducible de referencias BEAT2/MM-Conv sobre puntos y regiones."""
from pathlib import Path
from dataclasses import replace
import json
import cv2
import numpy as np
from so101er.config import cargar
from so101er.control.semantico import MotorGestos,ejemplos
from so101er.control.escenico import pose_reposo,compilar_actuacion
from so101er.control.anclaje import senalar_plano,barrer_region
from so101er.control.referencias import Motivo,adaptar
from so101er.hardware.mujoco_sim import MundoMuJoCo
from so101er import obra


def main():
    root=Path(__file__).resolve().parents[1];cfg=cargar(root/'config/so101er.toml')
    img=obra.preparar(cfg,root/'obra');motor=MotorGestos(cfg)
    mundo=MundoMuJoCo(cfg,cfg.brazos_activos,img)
    initial={n:pose_reposo(motor) for n in motor.marcos}
    arms={n:mundo.brazo(n,q) for n,q in initial.items()}
    output=root/'salidas';output.mkdir(exist_ok=True)
    writer=cv2.VideoWriter(str(output/'demo_BEAT2_MMConv.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(1280,520))
    if not writer.isOpened():raise RuntimeError('no se pudo crear vídeo')
    renderer=mundo.mj.Renderer(mundo.modelo,480,640)
    camera=mundo.mj.MjvCamera();camera.lookat[:]=[0,.25,.3]
    camera.distance=1.35;camera.azimuth=108;camera.elevation=-18
    report=[]
    try:
        for source in ('beat2','mmconv'):
            clip=Motivo.cargar(root/'datos/referencias'/source/f'motivo_{source}.json')
            for label,side,target in [('sol','der',[260,720]),('arbol','izq',[450,250]),
                                     ('region','izq',[[380,180],[580,400]])]:
                observed={n:b.leer_articulaciones() for n,b in arms.items()}
                g=(barrer_region(motor,target,side,observed) if label=='region'
                   else senalar_plano(motor,target,side,observed))
                g=replace(adaptar(clip,g),duracion_s=1.2,preparacion_s=.8,mantener_s=.2)
                plan=compilar_actuacion(motor,g,observed)
                for t in np.arange(0,plan.tiempos[-1]+.8,.04):
                    for n,q in plan.muestra(float(t)).items():arms[n].enviar_objetivo(q)
                    for _ in range(20):mundo.paso_fisico()
                    renderer.update_scene(mundo.datos,camera=camera)
                    view=cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR)
                    image=cv2.resize(img,(640,480));color=(0,190,255)
                    if label=='region':
                        a,b=np.array(target)*[.48,.64]
                        cv2.rectangle(image,(int(a[1]),int(a[0])),(int(b[1]),int(b[0])),color,3)
                    else:
                        y,x=np.array(target)*[.48,.64];cv2.circle(image,(int(x),int(y)),14,color,3)
                    frame=np.zeros((520,1280,3),np.uint8);frame[40:,:640]=image;frame[40:,640:]=view
                    cv2.putText(frame,f'{source.upper()} -> SO-101 | {label} | FK humana nominal',
                                (12,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1,cv2.LINE_AA)
                    writer.write(frame)
                report.append({'fuente':source,'referente':label,'objetivo':target,
                               'duracion_s':float(plan.tiempos[-1]),'error_ik_mm':plan.error_posicion_mm})
    finally:writer.release();renderer.close();mundo.cerrar()
    (output/'demo_BEAT2_MMConv.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

