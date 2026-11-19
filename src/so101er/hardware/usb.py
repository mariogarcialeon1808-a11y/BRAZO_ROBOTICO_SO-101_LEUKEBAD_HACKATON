"""SO-101 por USB/TTL STS3215. Lectura y escritura mediante protocolo Feetech.

Conectar no activa par. Para mover se exige una calibración explícita por motor.
No modifica EEPROM, IDs, offsets internos ni parámetros persistentes del servo.
"""
from pathlib import Path
import json
import threading
import numpy as np


def puertos():
    from serial.tools.list_ports import comports
    return [{'puerto':p.device,'nombre':p.description,'serie':p.serial_number} for p in comports()]


def paquete(id,instruccion,params):
    body=bytes([id,len(params)+2,instruccion])+bytes(params)
    return b'\xff\xff'+body+bytes([(~sum(body))&255])


class Bus:
    def __init__(self,puerto):
        import serial
        self.serial=serial.Serial(puerto,1000000,timeout=.04,write_timeout=.04)
        self.lock=threading.Lock()

    INTENTOS=3     # una trama perdida a 1 Mbaud es normal; tres seguidas, no
    reintentos=0   # cuántas veces hubo que repetir una orden (diagnóstico)

    def _una(self,id,instruccion,params):
        self.serial.reset_input_buffer()
        self.serial.write(paquete(id,instruccion,params))
        self.serial.flush()
        if id==254:return b''
        head=self.serial.read(4)
        if len(head)!=4 or head[:2]!=b'\xff\xff' or head[2]!=id:
            raise TimeoutError(f'servo {id} sin respuesta válida')
        tail=self.serial.read(head[3])
        if len(tail)!=head[3] or ((sum(head[2:])+sum(tail))&255)!=255:
            raise IOError('checksum/respuesta de servo inválidos')
        if tail[0]:raise IOError(f'servo {id}: error {tail[0]}')
        return tail[1:-1]

    def orden(self,id,instruccion,params=()):
        """Envía una orden y devuelve su respuesta. Repite si la respuesta se pierde o llega corrupta.

        Leer y escribir un registro con el mismo valor es idempotente, así que repetir es seguro.
        Un error que comunica el propio servo no se repite: es un estado, no una trama perdida.
        """
        with self.lock:
            for intento in range(self.INTENTOS):
                try:return self._una(id,instruccion,params)
                except (TimeoutError,IOError) as e:
                    if intento==self.INTENTOS-1 or str(e).startswith(f'servo {id}: error'):raise
                    self.reintentos+=1

    def leer(self,id,registro,n):
        data=self.orden(id,2,[registro,n])
        if len(data)!=n:raise IOError(f'servo {id}: longitud de lectura incorrecta ({len(data)}, esperados {n})')
        return data
    def escribir(self,id,registro,datos):self.orden(id,3,[registro,*datos])
    def cerrar(self):self.serial.close()


class BrazoUSB:
    def __init__(self,nombre,puerto,calibracion):
        self.nombre=nombre; self.bus=Bus(puerto); self.par=False
        self.cal=json.loads(Path(calibracion).read_text(encoding='utf-8'))
        if not self.cal.get('verificada'):
            self.bus.cerrar(); raise ValueError('calibración USB no verificada')
        self.ids=self.cal['ids']; self.cero=np.array(self.cal['cero_raw'],float)
        self.signo=np.array(self.cal['signo'],float)
        self.pinza=self.cal['pinza_raw']
        if (len(self.ids)!=6 or len(set(self.ids))!=6 or self.cero.shape!=(5,)
                or self.signo.shape!=(5,) or not np.isin(self.signo,[-1,1]).all()
                or len(self.pinza)!=2 or self.pinza[0]==self.pinza[1]):
            self.bus.cerrar(); raise ValueError('calibración de motores inválida')
        self.datos=None

    def conectar(self):
        for id in self.ids:self.bus.orden(id,1)
    def leer_articulaciones(self):
        self.datos=[self.bus.leer(id,56,8) for id in self.ids]
        raw=np.array([int.from_bytes(d[:2],'little') for d in self.datos])
        q=(raw[:5]-self.cero)*360/4096*self.signo
        return np.r_[q,(raw[5]-self.pinza[0])*100/(self.pinza[1]-self.pinza[0])]
    def leer_temperatura(self):return np.array([d[7] for d in self.datos])
    def leer_carga(self):return np.array([(int.from_bytes(d[4:6],'little')&1023)/1023 for d in self.datos])
    def activar_par(self):
        q=self.leer_articulaciones()
        # Primero objetivo igual a posición medida; después par (evita salto al objetivo viejo).
        self._enviar(q)
        for id in self.ids:self.bus.escribir(id,40,[1])
        self.par=True
    def _enviar(self,q):
        q=np.asarray(q,float)
        if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('consigna USB inválida')
        raw=np.rint(np.r_[self.cero+q[:5]*4096/360/self.signo,
                          self.pinza[0]+q[5]*(self.pinza[1]-self.pinza[0])/100]).astype(int)
        if (raw<0).any() or (raw>4095).any():raise ValueError('consigna fuera del encoder físico')
        params=[42,2]
        for id,r in zip(self.ids,raw):params.extend([id,int(r)&255,int(r)>>8])
        self.bus.orden(254,0x83,params)
    def enviar_objetivo(self,q):
        if self.par:self._enviar(q)
    def desactivar_par(self):
        for id in self.ids:self.bus.escribir(id,40,[0])
        self.par=False
    def desconectar(self):self.bus.cerrar()


def diagnosticar():
    resultados=[]
    for p in puertos():
        if not any(x in p['nombre'].lower() for x in ('usb','serial','ch340','cp210')):continue
        item={**p,'servos':[]}
        try:
            b=Bus(p['puerto'])
            try:
                for id in range(1,7):
                    try:
                        b.orden(id,1); raw=b.leer(id,56,2)
                        item['servos'].append({'id':id,'posicion_raw':int.from_bytes(raw,'little')})
                    except (OSError,TimeoutError):pass
            finally:b.cerrar()
        except Exception as e:item['error']=type(e).__name__
        resultados.append(item)
    return resultados
