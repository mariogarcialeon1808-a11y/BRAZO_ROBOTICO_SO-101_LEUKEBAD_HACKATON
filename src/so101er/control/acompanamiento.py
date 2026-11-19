"""Acompañamiento prosódico entre gestos referenciales, sin inventar referentes."""
from dataclasses import replace
import math
import numpy as np
from .semantico import Intencion,Trayectoria
from .escenico import pose_reposo,validar


def suave(s):return s**3*(10+s*(-15+6*s))


# Formas de acento: desplazamiento articular (base, hombro, codo, muñeca, giro) y apertura de pinza. La primera es la
# de siempre. Las demás existen para que el relleno entre gestos no sea siempre el mismo movimiento: van hacia dentro,
# hacia fuera, con giro de muñeca o sin abrir la pinza.
FORMAS_ACENTO=(((6.,10.,-8.,-14.,12.),75.),((-9.,7.,-12.,9.,-22.),0.),((13.,13.,-5.,-6.,0.),30.),
               ((0.,15.,-15.,-9.,28.),0.),((-5.,8.,5.,-17.,-16.),50.),((10.,5.,-13.,6.,32.),0.))


def acento(motor,brazo,duracion,pico,forma=0):
    """Gesto breve cerca del cuerpo, con salida y regreso suaves a reposo. `forma` elige cuál de FORMAS_ACENTO."""
    rest=pose_reposo(motor,brazo)
    side=1 if brazo=='izq' else -1
    desplazamiento,pinza=FORMAS_ACENTO[forma%len(FORMAS_ACENTO)]
    target=rest+np.array([side*desplazamiento[0],desplazamiento[1],desplazamiento[2],desplazamiento[3],side*desplazamiento[4],pinza])
    # La pinza acompaña al habla; los gestos principales conservan sus extremos 0/100.
    if pico<.75 or duracion-pico<.75:raise ValueError('acento demasiado rápido')
    # La pinza abre lo que sus límites permiten en este pulso (75 % como mucho). Con un perfil más
    # lento el acento se hace con menos apertura en vez de descartarse y dejar los brazos quietos.
    lim=motor.cfg.limites;lado=min(pico,duracion-pico)
    cabe=.95*min(lim.velocidad[5]*lado/1.875,lim.aceleracion[5]*lado**2/5.78,lim.tiron[5]*lado**3/60)
    target[5]=rest[5]+max(0.,min(pinza-rest[5],cabe))
    times=np.linspace(0,duracion,math.ceil(duracion*motor.cfg.frecuencia_hz)+1)
    out=np.empty((len(times),6));left=times<=pico
    out[left]=rest+suave(times[left,None]/pico)*(target-rest)
    out[~left]=target+suave((times[~left,None]-pico)/(duracion-pico))*(rest-target)
    poses={n:out.copy() if n==brazo else np.repeat(pose_reposo(motor,n)[None],len(times),axis=0) for n in motor.marcos}
    validar(motor,times,poses)
    frame=motor.marcos[brazo]
    p0,e0=motor.modelo.punta(rest[:5]);p1,e1=motor.modelo.punta(target[:5])
    g=Intencion('extension',brazo,(tuple(frame.a_mundo(p0)),tuple(frame.a_mundo(p1))),
                (tuple(frame.dir_a_mundo(e0)),tuple(frame.dir_a_mundo(e1))))
    return Trayectoria(times,poses,0.,pico,g,0.,0.,inicio_retorno=pico,reposo_al_final=True)


SIMPATIA=np.array([4.2,7.,-5.6,-9.8,8.4])   # grados; 0,7 × el acento. El brazo libre se inclina, no señala nada
PINZA_SIMPATIA=45.


def acompanar(motor,plan,escala=1.,comprobar=None):
    """El brazo que no hace el gesto lo acompaña y vuelve, en vez de esperar inmóvil.

    En la demostración cada brazo pasaba quieto el 41–48 % del tiempo de voz, con pausas de
    hasta 7 s mientras el otro gesticulaba. Aquí sube con el trazo del otro brazo, se sostiene
    y regresa con su recogida: empieza y acaba exactamente donde estaba, así que no altera la
    continuidad entre planes. No apunta a ningún referente. Solo consignas, constantes y la
    validación de siempre; si el movimiento no cabe (límites, mesa, separación o rangos del
    brazo real, con `comprobar`), prueba a media amplitud y, si tampoco, deja el plan como estaba.
    """
    t=np.asarray(plan.tiempos,float);total=float(t[-1])
    cima=float(plan.fin_trazo);baja=float(plan.inicio_retorno) if plan.inicio_retorno is not None else cima
    baja=max(baja,cima)
    if cima<.75 or total-baja<.75:return plan
    quietos=[n for n,q in plan.q.items() if float(np.ptp(q[:,:5],axis=0).max())<1e-6 and float(np.ptp(q[:,5]))<1e-6]
    if not quietos or len(quietos)==len(plan.q):return plan
    w=np.where(t<=cima,suave(np.clip(t/cima,0,1)),np.where(t<baja,1.,1-suave(np.clip((t-baja)/(total-baja),0,1))))[:,None]
    for factor in (escala,escala/2):
        poses={n:q.copy() for n,q in plan.q.items()}
        for n in quietos:
            side=1 if n=='izq' else -1
            delta=np.r_[SIMPATIA*[side,1,1,1,side]*factor,(PINZA_SIMPATIA-poses[n][0,5])*min(1.,factor)]
            poses[n]=poses[n]+w*delta
        candidato=replace(plan,q=poses)
        try:
            validar(motor,t,poses)
            if comprobar is not None:comprobar(candidato)
            return candidato
        except ValueError:continue
    return plan


def preparar_antes(motor,plan,extra):
    """Repartir la preparación desde el comienzo de la voz, preservando el ápice."""
    t=plan.tiempos.copy();prep=plan.inicio_trazo
    if extra<=0 or prep<=0:return plan
    t=np.where(t<=prep,t*(prep+extra)/prep,t+extra)
    result=replace(plan,tiempos=t,inicio_trazo=prep+extra,fin_trazo=plan.fin_trazo+extra,
                   inicio_retorno=plan.inicio_retorno+extra if plan.inicio_retorno is not None else None)
    validar(motor,result.tiempos,result.q)
    return result


def recoger_hasta(motor,plan,extra):
    """Recogida continua para huecos demasiado cortos para un acento nuevo."""
    if extra<=0 or plan.inicio_retorno is None:return plan
    begin=plan.inicio_retorno;duration=plan.tiempos[-1]-begin
    times=np.where(plan.tiempos<=begin,plan.tiempos,
                   begin+(plan.tiempos-begin)*(duration+extra)/duration)
    result=replace(plan,tiempos=times)
    validar(motor,result.tiempos,result.q)
    return result


def energia(audio,frecuencia=24000):
    """Envolvente de voz generada, no señal de un sensor privilegiado."""
    size=round(.04*frecuencia);n=len(audio)//size
    if not n:return np.zeros(0),np.zeros(0)
    x=np.asarray(audio[:n*size],float).reshape(n,size)/32768
    rms=np.sqrt(np.mean(x*x,axis=1))
    score=np.convolve(rms,np.ones(5)/5,mode='same') if n>=5 else rms
    return (np.arange(n)+.5)*size/frecuencia,score


def solo_acentos(motor,audio,duracion,comprobar=None,primero=0):
    """Acentos para una frase sin gesto principal: los brazos no se quedan quietos mientras se habla.

    Misma regla que los huecos de `completar`: un pulso cada 2,6 s aproximadamente, en el pico de voz
    de su tramo, alternando de brazo (`primero` dice por cuál se empieza), con el otro acompañando.
    Devuelve ([(inicio, plan)], cuántos).
    """
    if duracion<1.8:return [],0
    times,score=energia(audio)
    n=max(1,round(duracion/2.6));n=min(n,max(1,int(duracion/1.8)));length=duracion/n
    output=[]
    for i in range(n):
        a=i*length
        candidates=np.flatnonzero((times>=a+.8)&(times<=a+length-.8))
        peak=float(times[candidates[np.argmax(score[candidates])]]-a) if len(candidates) else length/2
        side=list(motor.marcos)[(primero+i)%len(motor.marcos)]
        try:pulse=acento(motor,side,length,peak,primero+i)        # cada acento, una forma distinta
        except ValueError:
            try:pulse=acento(motor,side,length,length/2)
            except ValueError:continue
        output.append((a,acompanar(motor,pulse,.6,comprobar)))
    return output,len(output)


def completar(motor,principales,audio,duracion,comprobar=None):
    """Conservar todos los gestos y sus ápices; llenar huecos durante el habla.

    Los acentos no apuntan a objetos ni sustituyen significados: son pulsos de
    acompañamiento. Cada uno vuelve a reposo. Nada se añade mientras se escucha.
    En cada gesto y cada acento el brazo libre acompaña (ver `acompanar`).
    """
    if not principales:return [],{'acentos':0,'huecos_antes_s':0.,'huecos_despues_s':0.}
    primary=list(principales)
    start,plan=primary[0]
    if start>0:primary[0]=(0.,preparar_antes(motor,plan,start))
    times,score=energia(audio)
    output=[];count=0;before=0.;after=0.;pulsos=set()
    def fill(begin,end):
        nonlocal count,before,after
        gap=end-begin
        if gap<=.01:return
        before+=gap
        if gap<1.8:
            s,p=output[-1];output[-1]=(s,recoger_hasta(motor,p,gap));return
        n=max(1,round(gap/2.6));n=min(n,max(1,int(gap/1.8)))
        length=gap/n
        for i in range(n):
            a=begin+i*length
            candidates=np.flatnonzero((times>=a+.8)&(times<=a+length-.8))
            peak=float(times[candidates[np.argmax(score[candidates])]]-a) if len(candidates) else length/2
            side=list(motor.marcos)[count%len(motor.marcos)]
            try:
                pulse=acento(motor,side,length,peak,count)
            except ValueError:
                try:pulse=acento(motor,side,length,length/2)
                except ValueError:after+=length;continue
            output.append((a,pulse));pulsos.add(id(pulse));count+=1
    for start,plan in primary:
        if output:fill(output[-1][0]+output[-1][1].tiempos[-1],start)
        output.append((start,plan))
    finish=output[-1][0]+output[-1][1].tiempos[-1]
    if finish<duracion:fill(finish,duracion)
    # El brazo libre acompaña sobre los tiempos DEFINITIVOS. Añadirlo antes de alargar la preparación
    # o la recogida dejaba un quiebro de velocidad en el empalme y el turno entero fallaba con
    # «actuación supera límites de movimiento». `acompanar` valida y, si no cabe, deja el plan intacto.
    output=[(s,acompanar(motor,p,.6 if id(p) in pulsos else 1.,comprobar)) for s,p in output]
    return output,{'acentos':count,'huecos_antes_s':before,'huecos_despues_s':after}
