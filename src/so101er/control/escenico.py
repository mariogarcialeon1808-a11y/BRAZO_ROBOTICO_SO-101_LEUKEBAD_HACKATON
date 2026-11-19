"""Amplitud escénica, pinzas y recogida. Solo consignas, encoders y FK nominal."""
from dataclasses import replace
import math
import numpy as np
from .semantico import unidad
from ..cinematica.modelo import FueraDeAlcance


def pose_trabajo(motor):
    """Postura de reposo en el aire, nominal, con pinza cerrada. No es una lectura sensorial.

    Es la de la simulación: los gestos salen de ella y vuelven a ella en poco recorrido.
    """
    q=motor.modelo.inversa([motor.modelo.eje_pan[0]+150,0,180])
    return np.r_[q,0.]


def pose_reposo(motor,nombre=None):
    """Reposo entre gestos: el del brazo real si se ha fijado, o la postura de trabajo nominal."""
    if hasattr(motor,'reposos_reales'):
        if nombre is None:raise ValueError('indica el brazo para su reposo real')
        return np.asarray(motor.reposos_reales[nombre],float).copy()
    if hasattr(motor,'reposo_real'):return np.asarray(motor.reposo_real,float).copy()
    return pose_trabajo(motor)


def transicion(motor,inicio,destino):
    """Movimiento articular suave de todos los brazos entre dos posturas, validado entero.

    Solo consignas, encoders de partida y FK nominal. Lanza ValueError si el recorrido
    toca límites, mesa, obra o al otro brazo: no se emite nada en ese caso.
    """
    from types import SimpleNamespace
    from .semantico import Trayectoria,inicio_nominal
    lim=motor.cfg.limites
    a={n:inicio_nominal(motor.modelo,q) for n,q in inicio.items()}
    b={n:np.asarray(destino[n],float) for n in a}
    duration=1.2
    for n in a:
        d=abs(b[n]-a[n])
        duration=max(duration,float(np.max(1.875*d/lim.velocidad)),
                     float(np.sqrt(np.max(5.78*d/lim.aceleracion))),
                     float(np.cbrt(np.max(60*d/lim.tiron))))
    duration*=1.2
    for _ in range(5):
        t=np.linspace(0,duration,math.ceil(duration*motor.cfg.frecuencia_hz)+1)
        s=(t/duration)[:,None];smooth=s**3*(10+s*(-15+6*s))
        poses={n:a[n]+smooth*(b[n]-a[n]) for n in a}
        try:
            validar(motor,t,poses)
            return Trayectoria(t,poses,0.,duration,SimpleNamespace(tipo='transicion'),0.,0.)
        except ValueError as e:
            if 'movimiento' not in str(e):raise
            duration*=1.25
    raise ValueError('no se pudo ajustar la transición')


def ampliar(motor,g,fraccion=.92):
    """Alargar manteniendo dirección del referente; nunca modificar el píxel objetivo."""
    frame=motor.marcos[g.brazo];model=motor.modelo
    points=frame.a_base(np.asarray(g.puntos_mm,float))
    axes=frame.dir_a_base(np.asarray(g.ejes,float))
    extent=model.alcance_max*fraccion
    out=[]
    for p in points:
        direction=unidad(p-model.hombro)
        out.append(model.hombro+direction*extent)
    if g.tipo=='recorrer':
        # Mantener rectitud/paralelismo: alargar la curva, no proyectarla sobre una esfera.
        direction=unidad(points[-1]-points[0]);v=points[-1]-model.hombro
        dot=float(v@direction)
        delta=-dot+math.sqrt(max(0,dot*dot+extent*extent-float(v@v)))
        endpoint=points[-1]+direction*delta
        out=endpoint+3.*(points-points[-1])
    pinzas=tuple(np.linspace(0.,100.,len(points))) if g.tipo!='senalar' else ()
    return replace(g,puntos_mm=tuple(map(tuple,frame.a_mundo(out))),
                   pinza=0. if g.tipo=='senalar' else 100.,pinzas=pinzas)


def ensanchar_abanico(motor,g):
    """Apertura hacia fuera: 65 grados de recorrido por brazo, sin cruzar el centro."""
    frame=motor.marcos[g.brazo];model=motor.modelo
    points=frame.a_base(np.asarray(g.puntos_mm,float))
    axes=frame.dir_a_base(np.asarray(g.ejes,float))
    center=np.mean([m.pos for m in motor.marcos.values()],axis=0)
    side=1. if frame.rot[:,1]@(frame.pos-center)>=0 else -1.
    result=[];directions=[]
    for u,p,e in zip(np.linspace(0,1,len(points)),points,axes):
        angle=np.radians(side*(5+65*u))
        radius=np.linalg.norm((p-model.hombro)[:2])
        result.append(model.hombro+np.array([radius*np.cos(angle),radius*np.sin(angle),p[2]-model.hombro[2]]))
        elevation=np.arcsin(np.clip(e[2],-1,1))
        directions.append([np.cos(angle)*np.cos(elevation),np.sin(angle)*np.cos(elevation),np.sin(elevation)])
    return replace(g,puntos_mm=tuple(map(tuple,frame.a_mundo(result))),
                   ejes=tuple(map(tuple,frame.dir_a_mundo(directions))))


def validar(motor,tiempos,poses):
    lim=motor.cfg.limites
    for n,q in poses.items():
        # La interpolación de un extremo exacto puede excederlo ~1e-13 grados.
        if ((q[:,:5]<motor.modelo.lim_inf-1e-6).any() or (q[:,:5]>motor.modelo.lim_sup+1e-6).any()
                or (q[:,5]<-1e-6).any() or (q[:,5]>100+1e-6).any()):
            raise ValueError('actuación fuera de límites articulares')
        v=np.diff(q,axis=0)/np.diff(tiempos)[:,None]
        a=np.diff(v,axis=0)/np.diff((tiempos[1:]+tiempos[:-1])/2)[:,None]
        j=np.diff(a,axis=0)/np.diff(tiempos[1:-1])[:,None]
        if max(np.max(abs(v)/lim.velocidad),np.max(abs(a)/lim.aceleracion),np.max(abs(j)/lim.tiron))>1.005:
            raise ValueError('actuación supera límites de movimiento')
    for i in range(len(tiempos)):
        chains={n:motor.seguridad.cadena_mundo(n,q[i]) for n,q in poses.items()}
        for n,q in poses.items():
            problem=motor.seguridad.problema_pose(n,q[i],chains[n])
            if problem:raise ValueError(problem)
        problem=motor.seguridad.problema_par(chains)
        if problem:raise ValueError(problem)


def recoger(motor,plan):
    """Añade retorno de AMBOS brazos al reposo, sin alterar el trazo expresivo."""
    rests={n:pose_reposo(motor,n) for n in plan.q};lim=motor.cfg.limites
    duration=1.2
    for n,q in plan.q.items():
        d=abs(rests[n]-q[-1])
        duration=max(duration,float(np.max(1.875*d/lim.velocidad)),
                     float(np.sqrt(np.max(5.78*d/lim.aceleracion))),
                     float(np.cbrt(np.max(60*d/lim.tiron))))
    duration*=1.2
    for _ in range(5):
        t=np.linspace(0,duration,math.ceil(duration*motor.cfg.frecuencia_hz)+1)
        s=(t/duration)[:,None];smooth=s**3*(10+s*(-15+6*s))
        poses={n:np.vstack([q,q[-1]+smooth[1:]*(rests[n]-q[-1])]) for n,q in plan.q.items()}
        times=np.r_[plan.tiempos,plan.tiempos[-1]+t[1:]]
        try:
            validar(motor,times,poses)
            return replace(plan,tiempos=times,q=poses,inicio_retorno=float(plan.tiempos[-1]),
                           reposo_al_final=True)
        except ValueError as e:
            if 'movimiento' not in str(e):raise
            duration*=1.25
    raise ValueError('no se pudo ajustar la recogida')


def compilar_actuacion(motor,g,estado,bilateral=False):
    """El mayor alcance de la banda 86–94 % que conserva geometría y separación."""
    error=None
    for fraction in (.94,.92,.90,.88,.86):
        try:
            wide=ampliar(motor,g,fraction)
            plan=motor.compilar(wide,estado)
            if bilateral and len(motor.marcos)==2:
                old=motor.marcos[g.brazo]
                other=next(n for n in motor.marcos if n!=g.brazo)
                frame=motor.marcos[other]
                local=old.a_base(np.asarray(wide.puntos_mm));local[:,1]*=-1
                axes=old.dir_a_base(np.asarray(wide.ejes));axes[:,1]*=-1
                companion=replace(wide,brazo=other,puntos_mm=tuple(map(tuple,frame.a_mundo(local))),
                                  ejes=tuple(map(tuple,frame.dir_a_mundo(axes))))
                second=motor.compilar(companion,estado)
                total=max(plan.tiempos[-1],second.tiempos[-1])*1.02
                times=np.linspace(0,total,math.ceil(total*motor.cfg.frecuencia_hz)+1)
                poses={}
                for n,p in ((g.brazo,plan),(other,second)):
                    poses[n]=np.array([p.muestra(t/total*p.tiempos[-1])[n] for t in times])
                plan=replace(plan,tiempos=times,q=poses,
                             inicio_trazo=plan.inicio_trazo*total/plan.tiempos[-1],
                             fin_trazo=plan.fin_trazo*total/plan.tiempos[-1])
                validar(motor,times,poses)
            return recoger(motor,plan)
        except (FueraDeAlcance,ValueError) as exc:error=exc
    raise ValueError(f'no cabe el gesto extendido con su regreso: {error}')
