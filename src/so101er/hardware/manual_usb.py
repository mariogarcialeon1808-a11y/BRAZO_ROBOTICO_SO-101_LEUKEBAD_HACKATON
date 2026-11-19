"""Control articular nativo: sensores reales, un USB activo y consignas acotadas."""
import json
import threading
import time
from pathlib import Path
import numpy as np
from .usb import Bus,puertos
from .calibracion import identidad
from .prueba_base import estado,CUENTAS_GRADO


class Coordenadas:
    def __init__(self,cal,raw):
        records=cal['rangos'];meta=cal['identidad_servos']
        self.low=np.array([max(records[str(i+1)]['min_raw'],meta[i]['min_raw'])+12 for i in range(6)],float)
        self.high=np.array([min(records[str(i+1)]['max_raw'],meta[i]['max_raw'])-12 for i in range(6)],float)
        if np.any(self.low>=self.high):raise ValueError('rangos no válidos')
        self.home=np.asarray(raw,float)
        # El margen interior es para objetivos, no para rechazar la lectura de
        # un brazo apoyado en su extremo físico. Hasta 4 cuentas de cuantización.
        if np.any(self.home<self.low-16) or np.any(self.home>self.high+16):
            names=('base','hombro','codo','muñeca','giro de pinza','apertura de pinza')
            bad=np.flatnonzero((self.home<self.low)|(self.home>self.high))
            details='; '.join(f'{names[i]} (ID {i+1}): encoder {self.home[i]:.0f}, permitido {self.low[i]:.0f}–{self.high[i]:.0f}' for i in bad)
            raise ValueError('No se activa: '+details+'. Con el brazo sin par, aparta esa articulación unos grados del tope y vuelve a activar.')
        self.home=np.clip(self.home,self.low,self.high)
    def a_ejes(self,raw):
        q=(np.asarray(raw,float)-self.home)/CUENTAS_GRADO
        q[5]=(raw[5]-self.low[5])*100/(self.high[5]-self.low[5]);return q
    def a_raw(self,q):
        q=np.asarray(q,float)
        if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('consigna inválida')
        raw=self.home+q*CUENTAS_GRADO
        raw[5]=self.low[5]+q[5]*(self.high[5]-self.low[5])/100
        if np.any(raw<self.low-16) or np.any(raw>self.high+16):raise ValueError('el movimiento no cabe en los rangos guardados')
        return np.clip(raw,self.low,self.high)


def objetivo_entrada(cal,raw):
    """Pequeña retirada conocida del extremo; jamás busca topes ni los amplía."""
    raw=np.asarray(raw,float);records=cal['rangos'];meta=cal['identidad_servos']
    if raw.shape!=(6,) or not np.isfinite(raw).all():raise ValueError('lectura inicial inválida')
    lo=np.array([max(records[str(i+1)]['min_raw'],meta[i]['min_raw'])+12 for i in range(6)],float)
    hi=np.array([min(records[str(i+1)]['max_raw'],meta[i]['max_raw'])-12 for i in range(6)],float)
    if np.any(lo>=hi):raise ValueError('rangos incompatibles')
    target=raw.copy()
    for i,r in enumerate(raw):
        # Cuatro cuentas solo de tolerancia en la lectura de partida. Los
        # objetivos permanecen estrictamente dentro de los rangos guardados.
        if r<max(records[str(i+1)]['min_raw'],meta[i]['min_raw'])-4 or r>min(records[str(i+1)]['max_raw'],meta[i]['max_raw'])+4:
            raise ValueError(f'ID {i+1}: postura inicial fuera del rango observado/firmware')
        if r<lo[i]:target[i]=min(hi[i],lo[i]+12)
        elif r>hi[i]:target[i]=max(lo[i],hi[i]-12)
    if np.max(abs(target-raw))>3*CUENTAS_GRADO:raise ValueError('la entrada inicial necesita más de 3 grados')
    Coordenadas(cal,target)
    return target


def desactivar_verificado(bus,i):
    last=None
    for _ in range(3):
        try:
            if bus.leer(i,40,1)[0]:bus.escribir(i,40,[0])
            if not bus.leer(i,40,1)[0]:return
            last='par sigue activo'
        except Exception as e:last=str(e)
        time.sleep(.08)
    raise RuntimeError(f'ID {i}: no se confirmó par cero: {last}')


NOMBRES=('base','hombro','codo','muñeca','giro de pinza','apertura de pinza')

# Perfil que se escribe en cada servo (registro 41: aceleración, en unidades de
# 100 cuentas/s²; registro 46: velocidad máxima, en cuentas/s). El servo persigue
# la consigna con un perfil trapezoidal y siempre va por detrás v²/(2·a). Con
# aceleración 5 y la misma velocidad máxima que la rampa de consigna, la pinza
# (60°/s) quedaba hasta 27° por detrás y el control la daba por bloqueada.
ACELERACION=(15,15,15,15,15,60)      # a la velocidad base (20°/s; pinza 60°/s); crece con el cuadrado de la velocidad
MARGEN_VELOCIDAD=1.5                 # el servo puede ir algo más rápido que la rampa, para alcanzarla
DESFASE_MAX=8*CUENTAS_GRADO          # consigna − encoder tolerado de forma sostenida
DESFASE_TIEMPO=.25                   # s seguidos por encima de DESFASE_MAX antes de detener
DESFASE_INMEDIATO=20*CUENTAS_GRADO   # por encima de esto se detiene en la misma lectura
VELOCIDAD_BASE=20.                   # °/s de las articulaciones del perfil de pruebas
VELOCIDAD_PINZA=60.                  # °/s mínimos de la apertura de pinza
VELOCIDAD_MAXIMA=150.                # la de la simulación; el programa no acepta más


def velocidad_real(root):
    """°/s de las articulaciones de los brazos reales: `[real] velocidad_grados_s` de config/so101er.toml.

    Es una consigna del operador, no una medida. Sin ese valor (o si no es válido) se usa el
    perfil de pruebas de 20°/s. La misma cifra limita la planificación de gestos y este control.
    """
    import tomllib
    try:
        with open(Path(root)/'config/so101er.toml','rb') as f:v=float(tomllib.load(f).get('real',{}).get('velocidad_grados_s',VELOCIDAD_BASE))
    except (OSError,ValueError,TypeError,AttributeError,tomllib.TOMLDecodeError):return VELOCIDAD_BASE
    return float(np.clip(v,VELOCIDAD_BASE,VELOCIDAD_MAXIMA)) if np.isfinite(v) else VELOCIDAD_BASE


CARGA_MAX=450            # carga neta (0–1000) que detiene, confirmada en tres lecturas seguidas
VELOCIDAD_LIBRE=3072.    # cuentas/s del STS3215 sin carga (45 rpm): a esa velocidad usa todo su ciclo de trabajo
DESCUENTO_VELOCIDAD=.8   # parte de ese ciclo de trabajo que se descuenta; el resto queda como margen


def carga_neta(s):
    """Carga indicada menos la que corresponde a la velocidad MEDIDA del servo. Solo sensores.

    La «carga» del STS3215 es el ciclo de trabajo de su motor: sube con el esfuerzo, pero también
    con la velocidad aunque nada se le oponga. En los brazos (15-11-2026) una pinza abriéndose en
    el aire a ~137°/s indicaba 452–484 y los hombros a 100–128°/s, 408–464; a 60°/s nunca se pasó
    de 450. Con el servo parado o bloqueado el descuento es cero: contra un obstáculo protege
    igual que antes. Sin lectura de velocidad se usa la carga tal cual.
    """
    carga=np.asarray(s['carga'],float);v=s.get('velocidad')
    if v is None:return carga
    v=np.minimum(np.abs(np.asarray(v,float)),VELOCIDAD_LIBRE)
    return np.maximum(0.,carga-DESCUENTO_VELOCIDAD*1000.*v/VELOCIDAD_LIBRE)


def anomalia(s):
    """Describe la primera medida de telemetría fuera de margen, o None. Solo sensores."""
    # La temperatura no se mira lectura a lectura: los servos dan valores sueltos imposibles
    # (57–142 °C entre dos lecturas de ~30 °C). La vigila `_loop` con la mediana de ~2 s.
    v=np.asarray(s['voltaje']);bad=np.flatnonzero((v<100)|(v>135))
    if bad.size:
        i=int(bad[0]);return f'{NOMBRES[i]} (ID {i+1}) con tensión {v[i]/10:.1f} V'
    load=carga_neta(s)
    if load.max()>CARGA_MAX:
        i=int(np.argmax(load));return f'{NOMBRES[i]} (ID {i+1}) con carga {int(np.asarray(s["carga"])[i])}'
    return None


TEMPERATURA_MAX=55        # °C sostenidos que detienen: mediana de las últimas lecturas, no un valor suelto
TEMPERATURA_ARRANQUE=50   # °C con los que no se activa
TEMPERATURA_MUESTRAS=90   # ~2 s de lecturas


def temperatura_fiable(bus,lecturas=5):
    """Temperatura de cada servo como mediana de varias lecturas seguidas: un valor suelto falso no cuenta."""
    return np.median([estado(bus)['temperatura'] for _ in range(lecturas)],axis=0)


def estado_confirmado(bus):
    """Lectura de sensores; una anomalía de tensión o carga solo cuenta si persiste en tres lecturas seguidas."""
    data=estado(bus)
    first=anomalia(data)
    if first is None:return data,None
    for _ in range(2):  # No se emiten consignas entre estas lecturas.
        data=estado(bus)
        if anomalia(data) is None:
            return data,f'lectura de telemetría aislada descartada tras comprobarla: {first}'
    return data,None


class ManualUSB:
    def __init__(self,root,port,entrada_suave=False,entrada_inicial=False,raw_esperado=None):
        data=json.loads((Path(root)/'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
        cal=next(c for c in data['brazos'] if c['puerto']==port)
        if next((p['serie'] for p in puertos() if p['puerto']==port),None)!=cal['serie_usb']:
            raise ValueError('el adaptador no corresponde a esta captura')
        self.bus=Bus(port);self.port=port;self.lock=threading.RLock();self.stop=threading.Event()
        self.active=[];self.error=None;self.closed=False;self.settings={}
        try:
            if identidad(self.bus)!=cal['identidad_servos']:raise ValueError('los ajustes de los servos cambiaron')
            if any(self.bus.leer(i,40,1)[0] for i in range(1,7)):raise ValueError('ya hay motores activados por otro controlador')
            first=estado(self.bus)
            if max(temperatura_fiable(self.bus))>=TEMPERATURA_ARRANQUE:raise ValueError('temperatura alta antes del arranque')
            if (first['voltaje']<100).any() or (first['voltaje']>135).any():raise ValueError('tensión fuera de margen antes del arranque')
            raw=first['raw'].astype(float);safe=raw.copy()
            if raw_esperado is not None and max(abs(raw-np.asarray(raw_esperado)))>4:
                raise ValueError('la postura cambió después de comprobar la entrada inicial; vuelve a preparar')
            self.entrando=False;self.speed=227;self.entry_start=time.monotonic()
            self.vel=velocidad_real(root)
            try:
                self.coords=Coordenadas(cal,raw);safe=np.clip(raw,self.coords.low,self.coords.high)
            except ValueError:
                if entrada_inicial:
                    safe=objetivo_entrada(cal,raw);self.coords=Coordenadas(cal,safe)
                    self.entrando=True;self.speed=11
                else:
                    if not entrada_suave or port!='COM8':raise
                    safe=self._entrada_codo(cal,raw)
                    self.coords=Coordenadas(cal,safe);self.entrando=True;self.speed=11
            self.measured=raw.copy();self.cmd=safe.copy();self.target=self.cmd.copy()
            time.sleep(.15)
            if max(abs(estado(self.bus)['raw']-self.measured))>8:raise ValueError('mantén el brazo quieto antes de activar')
            for i,r in enumerate(self.cmd,1):
                self.settings[i]=self.bus.leer(i,41,7)
                self._write(i,r)
            self.enviado=(self.speed,*np.rint(self.cmd).astype(int))
            for i in range(1,7):
                self.active.append(i)
                try:
                    self.bus.escribir(i,40,[1]);time.sleep(.08)
                    if not self.bus.leer(i,40,1)[0]:raise RuntimeError('el par no se activó')
                except Exception as e:raise RuntimeError(f'{port}, ID {i}: fallo al activar par: {e}') from e
            self.thread=threading.Thread(target=self._loop,daemon=True,name='manual-usb-'+port);self.thread.start()
        except Exception:
            if not self.active:self.bus.cerrar()
            else:
                failures=[]
                for i in self.active:
                    try:desactivar_verificado(self.bus,i)
                    except Exception:failures.append(i)
                self.bus.cerrar()
                if failures:raise RuntimeError('falló la activación y no se confirmó soltar motores '+str(failures)+'; sujeta el brazo y desconecta su alimentación')
            raise

    @staticmethod
    def _entrada_codo(cal,raw):
        low=np.array([max(cal['rangos'][str(i+1)]['min_raw'],cal['identidad_servos'][i]['min_raw'])+12 for i in range(6)])
        high=np.array([min(cal['rangos'][str(i+1)]['max_raw'],cal['identidad_servos'][i]['max_raw'])-12 for i in range(6)])
        bad=np.flatnonzero((raw<low)|(raw>high))
        if list(bad)!=[2]:raise ValueError('entrada suave disponible solo para el codo de COM8')
        safe=np.clip(raw,low,high)
        # Entrar algo más que el margen para absorber la banda muerta del
        # servo, manteniendo siempre la corrección total por debajo de 3°.
        budget=max(0,3*CUENTAS_GRADO-abs(safe[2]-raw[2]))
        inset=min(12,budget)
        safe[2]+=inset if raw[2]<low[2] else -inset
        safe[2]=float(np.clip(safe[2],low[2],high[2]))
        observed=cal['rangos']['3']
        if not observed['min_raw']<=raw[2]<=observed['max_raw'] or abs(safe[2]-raw[2])>3*CUENTAS_GRADO:
            raise ValueError('la corrección necesaria supera 3 grados o los rangos observados')
        return safe

    _desfase_desde=None   # instante en que la consigna y el encoder empezaron a diferir de más
    carga_pico=None       # carga neta máxima por servo desde el último informe (solo diagnóstico)
    carga_bruta_pico=None # lo mismo, tal como la indica el servo
    _temperaturas=None    # últimas lecturas de temperatura, para su mediana

    vel=VELOCIDAD_BASE    # °/s de las articulaciones; __init__ lo lee de la configuración

    def _rampa(self):
        """°/s a los que avanza la consigna de cada servo hacia su objetivo."""
        # Por encima del perfil de pruebas la rampa deja un margen sobre la planificación,
        # para que la consigna alcance al plan en vez de acumular retraso.
        v=self.vel*(1.25 if self.vel>VELOCIDAD_BASE else 1.)
        return np.array([v]*5+[max(VELOCIDAD_PINZA,v)])

    def _desfases(self):
        """(sostenido, inmediato) en cuentas: lo que recorre la consigna en 0,2 s y en 0,4 s, con un mínimo.

        Medido en los brazos: el encoder va unos 0,1 s por detrás de la consigna que recibe el servo.
        Un umbral fijo en grados daría paradas falsas al subir la velocidad; uno en tiempo no.
        """
        v=float(self._rampa()[0])*CUENTAS_GRADO
        return max(DESFASE_MAX,.2*v),max(DESFASE_INMEDIATO,.4*v)

    def _perfil(self,i):
        """(aceleración, velocidad máxima) que se escribe en el servo `i` (1–6)."""
        if self.speed!=227:return 5,self.speed      # entrada lenta inicial: perfil conservador, sin margen
        v=float(self._rampa()[i-1])
        base=VELOCIDAD_PINZA if i==6 else VELOCIDAD_BASE
        acel=int(np.clip(round(ACELERACION[i-1]*(v/base)**2),ACELERACION[i-1],254))
        return acel,int(min(3400,round(v*CUENTAS_GRADO*MARGEN_VELOCIDAD)))

    def _write(self,i,raw):
        r=int(round(raw));acel,speed=self._perfil(i)
        self.bus.escribir(i,41,[acel,r&255,r>>8,0,0,speed&255,speed>>8])

    def _write_all(self,raw):
        # SYNC_WRITE Feetech: misma trama para los seis objetivos RAM, sin
        # seis esperas de respuesta. El seguimiento se confirma leyendo encoders.
        key=(self.speed,*np.rint(raw).astype(int))
        if key==getattr(self,'enviado',None):return
        params=[41,7]
        for i,value in enumerate(raw,1):
            r=int(round(value));acel,speed=self._perfil(i)
            params.extend([i,acel,r&255,r>>8,0,0,speed&255,speed>>8])
        self.bus.orden(254,0x83,params)
        self.enviado=key

    def set(self,q):
        with self.lock:
            if self.error:raise RuntimeError(self.error)
            if self.entrando:raise RuntimeError('entrada inicial suave en curso; espera a que termine')
            self.target=self.coords.a_raw(q)

    def ejes(self):
        with self.lock:return self.coords.a_ejes(self.measured.copy())

    def parar(self):
        with self.lock:self.target=np.clip(self.measured,self.coords.low,self.coords.high)

    def reanudar(self):
        """Reconoce una parada: la consigna pasa a ser lo que miden los encoders y el control sigue.

        Solo a petición del operador. Todas las comprobaciones siguen activas: si la causa
        persiste (un obstáculo, un servo que no sigue), se vuelve a detener.
        """
        with self.lock:
            self.cmd=np.clip(self.measured,self.coords.low,self.coords.high);self.target=self.cmd.copy()
            self._desfase_desde=None;self.enviado=None;self.error=None

    def raw_actual(self):
        with self.lock:return self.measured.copy()

    def _loop(self):
        last=time.monotonic()
        while not self.stop.is_set():
            now=time.monotonic();dt=now-last;last=now
            try:
                # La adquisición no retiene el candado de la copia de estado:
                # el visor y el controlador de gestos no deben esperar al USB.
                data,notice=estado_confirmado(self.bus)
                if notice:self.aviso=notice
                with self.lock:
                    self.measured=data['raw'].astype(float)
                    names=NOMBRES
                    carga=np.asarray(data['carga'],float);neta=carga_neta(data)
                    self.carga_pico=neta.copy() if self.carga_pico is None else np.maximum(self.carga_pico,neta)
                    self.carga_bruta_pico=carga.copy() if self.carga_bruta_pico is None else np.maximum(self.carga_bruta_pico,carga)
                    if self._temperaturas is None:
                        import collections
                        self._temperaturas=collections.deque(maxlen=TEMPERATURA_MUESTRAS)
                    self._temperaturas.append(np.asarray(data['temperatura'],float))
                    if len(self._temperaturas)>=TEMPERATURA_MUESTRAS//3:
                        calor=np.median(self._temperaturas,axis=0);i=int(np.argmax(calor))
                        if calor[i]>=TEMPERATURA_MAX:
                            raise RuntimeError(f'{self.port}, {names[i]} (ID {i+1}): {calor[i]:.0f} °C sostenidos. Sujeta y suelta el brazo; espera a que baje de 50 °C')
                    if (data['voltaje']<100).any() or (data['voltaje']>135).any():raise RuntimeError('tensión fuera de margen')
                    # Seguimiento, solo con encoders: consigna emitida frente a posición medida.
                    lag=abs(self.cmd-self.measured);i=int(np.argmax(lag));worst=float(lag[i])
                    sostenido,inmediato=self._desfases()
                    if worst>inmediato:
                        raise RuntimeError(f'{self.port}, {names[i]} (ID {i+1}): no sigue la consigna ({worst/CUENTAS_GRADO:.0f}° de desfase). Detén, comprueba obstáculos y revisa su alineación')
                    if worst>sostenido:
                        # Un desfase breve es el retraso normal del servo al acelerar; solo detiene si persiste.
                        if self._desfase_desde is None:self._desfase_desde=now
                        elif now-self._desfase_desde>=DESFASE_TIEMPO:
                            raise RuntimeError(f'{self.port}, {names[i]} (ID {i+1}): no sigue la consigna ({worst/CUENTAS_GRADO:.0f}° de desfase durante {now-self._desfase_desde:.2f} s). Detén, comprueba obstáculos y revisa su alineación')
                    else:self._desfase_desde=None
                    if max(neta)>CARGA_MAX:
                        i=int(np.argmax(neta));detalle=f' ({neta[i]:.0f} descontada su velocidad)' if neta[i]!=carga[i] else ''
                        raise RuntimeError(f'{self.port}, {names[i]} (ID {i+1}): carga indicada {int(carga[i])}{detalle}. Sujeta y suelta; comprueba que no fuerza un tope ni un objeto')
                    if self.error:
                        raise RuntimeError(self.error)
                    if self.entrando:
                        inside=np.all(self.measured>=self.coords.low)&np.all(self.measured<=self.coords.high)
                        if inside and max(abs(self.measured-self.target))<=10:self.entrando=False;self.speed=227
                        elif time.monotonic()-self.entry_start>20:raise RuntimeError('el codo no entró en rango; sujeta y suelta el brazo')
                    elapsed=max(dt,time.monotonic()-now)
                    self.ciclo_ms=elapsed*1000
                    if elapsed>=1.:raise RuntimeError(f'lecturas interrumpidas: {elapsed*1000:.0f} ms (máximo 1000 ms). Movimiento detenido; revisa USB/alimentación y reinicia tras soltar el brazo')
                    if elapsed>.2:self.aviso=f'pico de latencia de {elapsed*1000:.0f} ms; movimiento limitado, sin recuperar el tiempo de golpe'
                    step=self._rampa()*CUENTAS_GRADO*min(dt,.04)
                    self.cmd+=np.clip(self.target-self.cmd,-step,step)
                    self._write_all(self.cmd)
            except Exception as e:
                with self.lock:self.error=str(e);self.target=self.cmd.copy()
            self.stop.wait(.02)

    def soltar(self):
        self.stop.set();self.thread.join(3)
        if self.thread.is_alive():raise RuntimeError('el controlador aún no se ha detenido')
        errors=[]
        for i in self.active:
            try:
                desactivar_verificado(self.bus,i)
                old=self.settings[i];self.bus.escribir(i,41,[old[0]]);self.bus.escribir(i,44,list(old[3:7]))
            except Exception as e:errors.append(f'{i}: {e}')
        if errors:raise RuntimeError('no se confirmó soltar: '+'; '.join(errors))
        self.active=[];self.bus.cerrar();self.closed=True
