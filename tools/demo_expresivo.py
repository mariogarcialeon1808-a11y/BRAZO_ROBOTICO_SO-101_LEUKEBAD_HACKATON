"""Verificación visual y sensorial de amplitud, pinzas y retorno a reposo."""
from pathlib import Path
from dataclasses import replace
import json
import cv2
import numpy as np
from so101er.config import cargar
from so101er.control.semantico import MotorGestos,ejemplos
from so101er.control.escenico import pose_reposo,ensanchar_abanico,compilar_actuacion
from so101er.control.referencias import Motivo,adaptar
from so101er.hardware.mujoco_sim import MundoMuJoCo
from so101er import obra


def main():
    root=Path(__file__).resolve().parents[1];cfg=cargar(root/'config/so101er.toml')
    img=obra.preparar(cfg,root/'obra');motor=MotorGestos(cfg)
    world=MundoMuJoCo(cfg,cfg.brazos_activos,img)
    arms={n:world.brazo(n,pose_reposo(motor)) for n in motor.marcos}
    out=root/'salidas/expresivo';out.mkdir(parents=True,exist_ok=True)
    writer=cv2.VideoWriter(str(out/'demo_amplitud_reposo_pinzas.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(960,640))
    world.modelo.vis.global_.offwidth=960;world.modelo.vis.global_.offheight=600
    renderer=world.mj.Renderer(world.modelo,600,960)
    cam=world.mj.MjvCamera();cam.lookat[:]=[0,.22,.28];cam.distance=1.65;cam.azimuth=108;cam.elevation=-18
    clip=Motivo.cargar(root/'datos/referencias/beat2/motivo_beat2.json')
    report=[]
    try:
        for name,g,_ in ejemplos(motor):
            if name in ('paisaje','cielo'):g=ensanchar_abanico(motor,g)
            g=replace(adaptar(clip,g),preparacion_s=.8,duracion_s=.3 if name=='punto' else 1.8,mantener_s=.2)
            plan=compilar_actuacion(motor,g,{n:b.leer_articulaciones() for n,b in arms.items()},
                                   bilateral=name in ('paisaje','cielo'))
            max_error=0.;saved=False
            for t in np.arange(0,plan.tiempos[-1]+.8,.04):
                command=plan.muestra(float(t))
                for n,q in command.items():arms[n].enviar_objetivo(q)
                for _ in range(20):world.paso_fisico()
                measured={n:b.leer_articulaciones() for n,b in arms.items()}
                max_error=max(max_error,max(np.max(abs(measured[n][:5]-command[n][:5])) for n in command))
                renderer.update_scene(world.datos,camera=cam)
                image=cv2.cvtColor(renderer.render(),cv2.COLOR_RGB2BGR)
                frame=np.zeros((640,960,3),np.uint8);frame[40:]=image
                phase='REPOSO' if t>=plan.tiempos[-1] else 'RECOGIDA' if t>=plan.inicio_retorno else 'GESTO AMPLIO'
                text=f'{name.upper()} | {phase} | pinzas {command["izq"][5]:.0f}% / {command["der"][5]:.0f}%'
                cv2.putText(frame,text,(14,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(245,245,245),1,cv2.LINE_AA)
                writer.write(frame)
                if not saved and t>=plan.fin_trazo:
                    cv2.imwrite(str(out/f'{name}_extendido.png'),frame);saved=True
            home_error=max(float(np.max(abs(measured[n]-pose_reposo(motor)))) for n in arms)
            report.append({'gesto':name,'error_seguimiento_max_grados':float(max_error),
                           'error_reposo_max_grados_pct':home_error,'duracion_s':float(plan.tiempos[-1])})
    finally:writer.release();renderer.close();world.cerrar()
    (out/'verificacion.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    assert max(r['error_seguimiento_max_grados'] for r in report)<25
    assert max(r['error_reposo_max_grados_pct'] for r in report)<2


if __name__=='__main__':main()
