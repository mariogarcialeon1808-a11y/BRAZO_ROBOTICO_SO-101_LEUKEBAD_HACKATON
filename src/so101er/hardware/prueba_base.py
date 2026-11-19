"""Prueba directa del giro de base: encoders reales, un solo servo, sin IK."""
import json
from pathlib import Path
import time
import numpy as np
from .usb import Bus,puertos
from .calibracion import BusSoloLectura,identidad

CUENTAS_GRADO=4096/360


def parametros_barrido(inicio,manual,firmware,amplitud=35.):
    if not 0<amplitud<=35:raise ValueError('amplitud máxima de prueba: 35 grados')
    lo=max(manual['min_raw'],firmware['min_raw'])+64
    hi=min(manual['max_raw'],firmware['max_raw'])-64
    delta=round(amplitud*CUENTAS_GRADO)
    if lo>=hi or inicio-delta<lo or inicio+delta>hi:
        raise ValueError('la postura actual no deja margen para el barrido; no se activó el motor')
    return int(lo),int(hi),delta


class BusBase(Bus):
    """Solo permite escribir RAM del servo 1, con límites y velocidad impuestos."""
    limites=None
    def orden(self,id,instruccion,params=()):
        if instruccion not in (1,2):
            if instruccion!=3 or id!=1:raise ValueError('solo se permite escribir la base, ID 1')
            p=list(params);reg=p[0] if p else -1
            if reg==40 and len(p)==2 and p[1] in (0,1):pass
            elif reg==41 and len(p)==8:
                target=p[2]+256*p[3];speed=p[6]+256*p[7]
                if (self.limites is None or not self.limites[0]<=target<=self.limites[1]
                    or not 1<=p[1]<=5 or p[4:6]!=[0,0] or not 1<=speed<=92):
                    raise ValueError('objetivo, aceleración o velocidad fuera del límite de prueba')
            elif (reg==41 and len(p)==2) or (reg==44 and len(p)==5):
                if self.leer(1,40,1)[0]!=0:raise ValueError('restaurar ajustes requiere par desactivado')
            else:raise ValueError('registro de escritura no autorizado en esta prueba')
        return super().orden(id,instruccion,params)


def estado(bus):
    rows=[bus.leer(i,56,8) for i in range(1,7)]
    return {'raw':np.array([int.from_bytes(r[:2],'little') for r in rows]),
            # Velocidad medida por el servo, en cuentas/s (registro 58; el bit 15 es el sentido).
            'velocidad':np.array([int.from_bytes(r[2:4],'little')&0x7FFF for r in rows]),
            'carga':np.array([int.from_bytes(r[4:6],'little')&1023 for r in rows]),
            'temperatura':np.array([r[7] for r in rows]),'voltaje':np.array([r[6] for r in rows])}


def comprobar_estado(current,initial,other,other_initial,goal):
    if max(current['temperatura'])>=50:raise RuntimeError('temperatura de 50 °C o superior')
    if (current['voltaje']<100).any() or (current['voltaje']>135).any():raise RuntimeError('tensión fuera del margen de prueba')
    if current['carga'][0]>250:raise RuntimeError('carga elevada en el giro de base')
    if abs(current['raw'][0]-goal)>6*CUENTAS_GRADO:raise RuntimeError('la base no sigue la consigna')
    if max(abs(current['raw'][1:]-initial['raw'][1:]))>45:raise RuntimeError('otra articulación cambió de postura')
    if max(abs(other['raw']-other_initial['raw']))>45:raise RuntimeError('el brazo apartado se ha movido')


def ejecutar(root,cancel,notificar,puerto='COM7',amplitud=35.):
    """No interpreta estos rangos como una calibración del URDF ni del montaje."""
    root=Path(root);record=json.loads((root/'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
    arms={a['puerto']:a for a in record['brazos']}
    if set(arms)!={'COM7','COM8'} or puerto not in arms:raise ValueError('se necesitan las dos capturas originales')
    other_port=next(p for p in arms if p!=puerto)
    connected={p['puerto']:p for p in puertos()}
    for port,a in arms.items():
        if connected.get(port,{}).get('serie')!=a['serie_usb']:raise ValueError('el USB no corresponde al brazo calibrado')
        if set(a['rangos'])!=set(map(str,range(1,7))):raise ValueError('faltan rangos de algún motor')
    report={'puerto_activo':puerto,'servo_activo':1,'amplitud_solicitada_grados':amplitud,
            'paso_corto_superado':False,'barrido_superado':False,'escrituras_otro_brazo':0}
    active=None;other_bus=None;attempted=False;original=None;error=None
    try:
        active=BusBase(puerto);other_bus=BusSoloLectura(other_port)
        for p,bus in ((puerto,active),(other_port,other_bus)):
            if identidad(bus)!=arms[p]['identidad_servos']:raise ValueError('han cambiado los ajustes de un servo')
            if any(bus.leer(i,40,1)[0] for i in range(1,7)):raise ValueError('hay otro controlador o motores con par activo')
        initial=estado(active);other_initial=estado(other_bus);start=int(initial['raw'][0])
        lo,hi,delta=parametros_barrido(start,arms[puerto]['rangos']['1'],arms[puerto]['identidad_servos'][0],amplitud)
        active.limites=(lo,hi);original=active.leer(1,41,7)
        comprobar_estado(initial,initial,other_initial,other_initial,start)
        cancel.wait(.2);stable=estado(active)
        if max(abs(stable['raw']-initial['raw']))>8:raise RuntimeError('el brazo no está quieto; no se activó el motor')
        if cancel.is_set():raise RuntimeError('prueba cancelada')
        def command(raw):
            raw=int(round(raw));active.escribir(1,41,[5,raw&255,raw>>8,0,0,91,0])
        # Objetivo medido antes de par: no se persigue una posición antigua.
        command(start);attempted=True;active.escribir(1,40,[1])
        report['inicio_raw']=start;report['limites_raw']=[lo,hi]
        samples=[];cursor=start
        def tramo(target):
            nonlocal cursor
            distance=abs(target-cursor)/CUENTAS_GRADO
            duration=max(1.5,1.875*distance/8.)
            beginning=time.monotonic();last=beginning
            while True:
                now=time.monotonic()
                if cancel.is_set():raise RuntimeError('parada solicitada')
                if now-last>.18:raise RuntimeError('el controlador perdió su frecuencia de actualización')
                last=now;s=min((now-beginning)/duration,1.)
                smooth=s**3*(10+s*(-15+6*s));goal=cursor+(target-cursor)*smooth
                command(goal)
                current=estado(active);opposite=estado(other_bus)
                comprobar_estado(current,initial,opposite,other_initial,goal)
                samples.append([now,int(current['raw'][0]),int(round(goal))])
                notificar({'angulo_relativo':round((int(current['raw'][0])-start)/CUENTAS_GRADO,1)})
                if s>=1:break
                cancel.wait(.02)
            # Comprobar asentamiento antes de dar por alcanzado el objetivo.
            for _ in range(15):
                if cancel.wait(.02):raise RuntimeError('parada solicitada')
                current=estado(active);opposite=estado(other_bus)
                comprobar_estado(current,initial,opposite,other_initial,target)
            if abs(int(current['raw'][0])-target)>1.5*CUENTAS_GRADO:raise RuntimeError('no se alcanzó el objetivo de prueba')
            cursor=target
        notificar('Prueba corta: 3° y regreso. Solo gira la base.')
        tramo(start+round(3*CUENTAS_GRADO));tramo(start)
        report['paso_corto_superado']=True
        notificar(f'Prueba corta correcta. Barrido lento de ±{amplitud:g}° y regreso al inicio.')
        tramo(start+delta);tramo(start-delta);tramo(start)
        report['barrido_superado']=True
        report['fin_raw']=int(estado(active)['raw'][0])
        report['error_retorno_grados']=abs(report['fin_raw']-start)/CUENTAS_GRADO
        report['error_seguimiento_max_grados']=max(abs(p-g) for _,p,g in samples)/CUENTAS_GRADO
        report['recorrido_medido_grados']=(max(p for _,p,_ in samples)-min(p for _,p,_ in samples))/CUENTAS_GRADO
    except Exception as e:error=str(e)
    finally:
        if active is not None and attempted:
            try:
                active.escribir(1,40,[0])
                report['par_final_base']=int(active.leer(1,40,1)[0])
                if original is not None:
                    active.escribir(1,41,[original[0]]);active.escribir(1,44,list(original[3:7]))
            except Exception as e:
                report['fallo_desactivacion']=str(e)
                error=(error+'; ' if error else '')+'NO SE PUDO CONFIRMAR PAR DESACTIVADO: '+str(e)
        for bus in (active,other_bus):
            if bus is not None:bus.cerrar()
        report['error']=error
        output=root/'salidas/diagnostico';output.mkdir(parents=True,exist_ok=True)
        (output/f'prueba_base_{puerto}.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    if error:raise RuntimeError(error)
    notificar('Prueba terminada. Base en el inicio y par desactivado. COM8 no recibió órdenes de movimiento.' if puerto=='COM7'
              else 'Prueba terminada. Base en el inicio y par desactivado.')
    return report
