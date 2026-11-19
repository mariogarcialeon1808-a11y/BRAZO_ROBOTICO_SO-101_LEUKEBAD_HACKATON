"""Calibración manual desde encoders. Este asistente no envía órdenes de motor."""
from datetime import datetime,timezone
import json
from pathlib import Path
import threading
import time
import numpy as np
from .usb import Bus,puertos


class BusSoloLectura(Bus):
    def orden(self,id,instruccion,params=()):
        if instruccion not in (1,2):raise RuntimeError('asistente exclusivamente de lectura')
        return super().orden(id,instruccion,params)


def identidad(bus):
    def word(id,reg):return int.from_bytes(bus.leer(id,reg,2),'little')
    return [{'id':i,'modelo_raw':word(i,3),'min_raw':word(i,9),'max_raw':word(i,11),
             'offset_raw':word(i,31),'modo':bus.leer(i,33,1)[0]} for i in range(1,7)]


class Monitor:
    def __init__(self):
        self.lock=threading.Lock();self.fin=threading.Event();self.datos={};self.errores={}
        self.hilo=threading.Thread(target=self._bucle,daemon=True,name='calibracion-encoders')
        self.hilo.start()

    def _bucle(self):
        buses={}
        try:
            for port in puertos():
                if not any(k in port['nombre'].lower() for k in ('usb','ch34','cp210')):continue
                bus=None
                try:
                    bus=BusSoloLectura(port['puerto']);meta=identidad(bus)
                    buses[port['puerto']]=(bus,port,meta)
                except Exception as e:
                    if bus:bus.cerrar()
                    with self.lock:self.errores[port['puerto']]=str(e)
            while not self.fin.is_set():
                for name,(bus,port,meta) in buses.items():
                    if self.fin.is_set():break
                    try:
                        rows=[bus.leer(i,56,8) for i in range(1,7)]
                        torque=[bus.leer(i,40,1)[0] for i in range(1,7)]
                        sample={**port,'identidad':meta,'raw':[int.from_bytes(r[:2],'little') for r in rows],
                                'temperaturas':[r[7] for r in rows],'voltajes_raw':[r[6] for r in rows],
                                'par':torque,'t':time.monotonic()}
                        with self.lock:self.datos[name]=sample;self.errores.pop(name,None)
                    except Exception as e:
                        with self.lock:self.errores[name]=str(e);self.datos.pop(name,None)
                self.fin.wait(.035)
        finally:
            for bus,_,_ in buses.values():bus.cerrar()

    def leer(self):
        with self.lock:return dict(self.datos),dict(self.errores)

    def cerrar(self):self.fin.set();self.hilo.join(4)


def comprobar_muestra(sample):
    if time.monotonic()-sample['t']>.5:raise ValueError('lectura antigua: comprueba el USB')
    if any(sample['par']):raise ValueError('hay motores con par: no moverlos a mano; detén el otro controlador')
    if max(sample['temperaturas'])>=55:raise ValueError('temperatura alta: deja enfriar el brazo')
    raw=np.asarray(sample['raw'],float)
    if raw.shape!=(6,) or not np.isfinite(raw).all() or (raw<0).any() or (raw>4095).any():
        raise ValueError('lectura de encoder fuera de rango')
    return raw


class CapturaRangos:
    def __init__(self,puerto,serie,meta):
        self.puerto=puerto;self.serie=serie;self.meta=meta
        self.rangos={}

    def _raw(self,sample):
        if sample['puerto']!=self.puerto or sample['serie']!=self.serie:
            raise ValueError('la lectura pertenece a otro brazo')
        if sample['identidad']!=self.meta:raise ValueError('los ajustes de los servos han cambiado')
        return comprobar_muestra(sample)

    def observar(self,i,sample):
        if i not in range(6):raise ValueError('motor desconocido')
        raw=self._raw(sample)
        value=int(raw[i]);previous=self.rangos.get(i)
        if previous is None:self.rangos[i]={'min_raw':value,'max_raw':value,'muestras':1,'ultimo_t':sample['t'],'ultimo_raw':value}
        elif sample['t']!=previous['ultimo_t'] or value!=previous['ultimo_raw']:
            previous.update(min_raw=min(previous['min_raw'],value),max_raw=max(previous['max_raw'],value),
                            muestras=previous['muestras']+1,ultimo_t=sample['t'],ultimo_raw=value)

    def reiniciar(self,i):self.rangos.pop(i,None)

    def exportar(self):
        ranges={str(i+1):{k:v for k,v in r.items() if not k.startswith('ultimo_')} for i,r in self.rangos.items()}
        # Un rango amplio no demuestra alineación cinemática ni confirma topes físicos.
        # Este archivo no se hace pasar por la calibración URDF que exige BrazoUSB.
        return {'puerto':self.puerto,'serie_usb':self.serie,'identidad_servos':self.meta,
                'rangos':ranges,'referencia_modelo_verificada':False}


def guardar_atomicamente(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        suffix=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        path.with_name(path.stem+'.anterior_'+suffix+path.suffix).write_bytes(path.read_bytes())
    temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
    temporary.replace(path)
