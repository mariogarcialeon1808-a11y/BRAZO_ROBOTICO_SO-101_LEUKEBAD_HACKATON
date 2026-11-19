"""Ejecución local independiente de red/voz. Solo sensores y memoria de consignas."""
import threading
import time
import numpy as np


class ControlLocal:
    def __init__(self,motor,brazos):
        self.motor=motor;self.brazos=brazos;self.lock=threading.RLock()
        self.cmd=self.medir()
        for n,b in brazos.items():
            if hasattr(b,'validar_q'):self.cmd[n]=b.validar_q(self.cmd[n])
        self.previo={n:q.copy() for n,q in self.cmd.items()}
        self.vel={n:np.zeros(6) for n in self.cmd}
        self.plan=None;self.inicio=0;self.reloj=None;self.fin=threading.Event();self.error=None
        self.frenada=None;self.jitter=[]
        self.registro=None   # opcional: función(now,t_plan,esperado,medido) para diagnóstico; no decide nada
        self.adelanto=max((float(getattr(b,'retardo_s',0.)) for b in brazos.values()),default=0.)
        self.hilo=threading.Thread(target=self._bucle,name='control-sensorial',daemon=True)
        self.hilo.start()

    def medir(self):return {n:b.leer_articulaciones() for n,b in self.brazos.items()}

    def programar(self,plan,inicio=None,reloj=None):
        with self.lock:
            if self.error:raise RuntimeError(self.error)
            self.plan=plan;self.inicio=time.perf_counter() if inicio is None else inicio;self.reloj=reloj;self.frenada=None

    def parar(self):
        with self.lock:
            self.plan=None;self.reloj=None
            lim=self.motor.cfg.limites
            dur=max(.3,*[float(np.max(1.5*abs(v)/lim.aceleracion)) for v in self.vel.values()],
                    *[float(np.sqrt(np.max(6*abs(v)/lim.tiron))) for v in self.vel.values()])
            self.frenada=(time.perf_counter(),dur,{n:q.copy() for n,q in self.cmd.items()},
                          {n:v.copy() for n,v in self.vel.items()})

    def reanudar(self):
        """Reconoce una parada y vuelve a controlar desde lo que miden los encoders. Solo a petición del operador."""
        with self.lock:
            cmd=self.medir()
            for n,b in self.brazos.items():
                if hasattr(b,'validar_q'):cmd[n]=b.validar_q(cmd[n])
            self.cmd=cmd;self.previo={n:q.copy() for n,q in cmd.items()}
            self.vel={n:np.zeros(6) for n in cmd};self.plan=None;self.reloj=None;self.frenada=None;self.error=None

    def _bucle(self):
        period=.02;deadline=time.perf_counter();last=deadline
        while not self.fin.is_set():
            if self.error:
                self.fin.wait(period);continue
            now=time.perf_counter();dt=max(now-last,.001);last=now
            try:
                with self.lock:
                    target={n:q.copy() for n,q in self.cmd.items()};esperado=target
                    if self.plan is not None:
                        t=(self.reloj() if self.reloj else now)-self.inicio
                        # Se emite la consigna de dentro de `adelanto` s; el brazo debe estar donde dice el plan AHORA.
                        target=self.plan.muestra(t+self.adelanto)
                        esperado=self.plan.muestra(t) if self.adelanto else target
                    elif self.frenada:
                        start,dur,q,v=self.frenada;s=min(max((now-start)/dur,0),1)
                        target={n:q[n]+v[n]*dur*(s-s**3+.5*s**4) for n in q}
                        if s>=1:self.frenada=None
                    chains={}
                    for n,q in target.items():
                        chains[n]=self.motor.seguridad.cadena_mundo(n,q)
                        problem=self.motor.seguridad.problema_pose(n,q,chains[n])
                        if problem:raise RuntimeError(f'{getattr(self.brazos[n],"port",n)}: {problem}')
                    problem=self.motor.seguridad.problema_par(chains)
                    if problem:raise RuntimeError(problem)
                    # Seguimiento medido, también en MuJoCo a través de encoders declarados.
                    measured=self.medir()
                    if len(measured)>1 and any(hasattr(b,'detener') for b in self.brazos.values()):
                        # Ambos estados observados y las combinaciones de envío
                        # secuencial: nunca usar poses internas del renderizador.
                        observed={n:self.motor.seguridad.cadena_mundo(n,q) for n,q in measured.items()}
                        for c in (observed,{**observed,'izq':chains['izq']},{**observed,'der':chains['der']}):
                            problem=self.motor.seguridad.problema_par(c)
                            if problem:raise RuntimeError(problem)
                    for n,q in target.items():
                        if np.max(abs(measured[n][:5]-esperado[n][:5]))>25:
                            i=int(np.argmax(abs(measured[n][:5]-esperado[n][:5])))
                            names=('base','hombro','codo','muñeca','giro de pinza')
                            raise RuntimeError(f'{getattr(self.brazos[n],"port",n)}, {names[i]} (ID {i+1}): error de seguimiento >25 grados; detén y comprueba que no haya obstáculos y que su alineación sea correcta')
                        b=self.brazos[n]
                        if getattr(b,'telemetria_temperatura',True) and np.max(b.leer_temperatura())>60:
                            raise RuntimeError('temperatura excesiva')
                        self.vel[n]=(q-self.cmd[n])/dt;self.previo[n]=self.cmd[n];self.cmd[n]=q
                        b.enviar_objetivo(q)
                    if self.registro is not None and self.plan is not None:self.registro(now,t,esperado,measured)
                self.jitter.append(dt-period)
                if len(self.jitter)>3000:self.jitter=self.jitter[-2000:]
            except Exception as e:
                self.error=str(e)
                # Sostener la última consigna emitida; no leer verdad física ni continuar planes viejos.
                with self.lock:self.plan=None;self.frenada=None;self.vel={n:np.zeros(6) for n in self.cmd}
                for b in self.brazos.values():
                    if hasattr(b,'detener'):
                        try:b.detener()
                        except Exception:pass
            deadline+=period
            if deadline<time.perf_counter():deadline=time.perf_counter()
            self.fin.wait(max(0,deadline-time.perf_counter()))

    def cerrar(self):
        self.parar();time.sleep(.35);self.fin.set();self.hilo.join(2)
