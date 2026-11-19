"""Transformación calibrada encoder ↔ URDF, sin dependencia del simulador."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .calibracion import guardar_atomicamente


def huella(cal):
    data={k:cal[k] for k in ('serie_usb','identidad_servos','rangos')}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()


class Alineacion:
    def __init__(self,cal,raw,q,signos=None):
        self.cal=cal;self.raw=np.asarray(raw,float).copy();self.q=np.asarray(q,float).copy()
        self.signos=np.array(signos if signos is not None else [1]*6,float)
        span=cal['rangos']['6']['max_raw']-cal['rangos']['6']['min_raw']
        if (self.raw.shape!=(6,) or self.q.shape!=(6,) or self.signos.shape!=(6,) or span<100
            or not np.isfinite(self.raw).all() or not np.isfinite(self.q).all()
            or (self.raw<0).any() or (self.raw>4095).any()
            or not np.isin(self.signos,[-1,1]).all()):raise ValueError('referencia de alineación inválida')
        self.escala=np.r_[np.full(5,360/4096),100/span]
    def a_modelo(self,raw):return self.q+(np.asarray(raw,float)-self.raw)*self.escala*self.signos
    def a_raw(self,q):
        q=np.asarray(q,float)
        if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('pose del modelo inválida')
        return self.raw+(q-self.q)/(self.escala*self.signos)
    def invertir(self,i):self.signos[i]*=-1
    def guardar(self,root,puerto,comprobados):
        if len(comprobados)!=6 or not all(comprobados):raise ValueError('comprueba manualmente los seis sentidos antes de guardar')
        from ..cinematica.modelo import Cinematica
        model=Cinematica()
        if (self.q[:5]<model.lim_inf).any() or (self.q[:5]>model.lim_sup).any() or not 0<=self.q[5]<=100:
            raise ValueError('referencia fuera del modelo')
        data={'verificada':True,'metodo':'postura y sentidos confirmados visualmente por operador',
              'huella':huella(self.cal),'raw_referencia':self.raw.tolist(),'q_modelo_referencia':self.q.tolist(),
              'signos':self.signos.tolist(),'serie_usb':self.cal['serie_usb']}
        guardar_atomicamente(Path(root)/'config'/f'alineacion_{puerto}.json',data)
    @classmethod
    def cargar(cls,root,puerto,cal):
        path=Path(root)/'config'/f'alineacion_{puerto}.json'
        if not path.exists():return None
        data=json.loads(path.read_text(encoding='utf8'))
        if not data.get('verificada') or data.get('huella')!=huella(cal):
            raise ValueError('alineación antigua o distinta de estos rangos/servos; repítela')
        return cls(cal,data['raw_referencia'],data['q_modelo_referencia'],data['signos'])


def plan_real(nombre,inicio,alineacion,coords,kin,gestos,velocidad=20.):
    """Valida antes de emitir nada. Toda la geometría es FK nominal de consignas."""
    cursor=np.asarray(inicio,float).copy();t=0.;plans=[]
    for target in [*gestos[nombre],inicio]:
        target=np.asarray(target,float).copy()
        grip_bounds=sorted([alineacion.a_modelo(coords.low)[5],alineacion.a_modelo(coords.high)[5]])
        target[5]=np.clip(target[5],max(0,grip_bounds[0]),min(100,grip_bounds[1]))
        a=alineacion.a_raw(cursor);b=alineacion.a_raw(target)
        # Esta conversión valida también límites físicos observados/heredados.
        coords.a_raw(coords.a_ejes(a));coords.a_raw(coords.a_ejes(b))
        if (target[:5]<kin.lim_inf).any() or (target[:5]>kin.lim_sup).any():raise ValueError('baile fuera del URDF')
        for s in np.linspace(0,1,101):
            q=cursor+(target-cursor)*s;points=kin.puntos(q)
            if np.min(points[3:,2])<5 or np.min(points[4:,2])<25:
                raise ValueError('esta transición acercaría el brazo a la mesa; ajusta la postura primero')
        duration=max(1.5,1.875*max(abs(b[:5]-a[:5]))/(4096/360)/velocidad,
                     1.875*abs(b[5]-a[5])/(4096/360)/60.)
        plans.append((t,duration,cursor.copy(),target.copy()));t+=duration;cursor=target
    return plans
