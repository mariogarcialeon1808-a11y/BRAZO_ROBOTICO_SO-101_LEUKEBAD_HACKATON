"""Adquisición causal de encoders equivalentes a lectura de servo.

Perfil nominal de ensayo (no identificado aún con hardware): 100 Hz, 20 ms de
retardo, resolución 4096 cuentas/vuelta, ruido 0.04 grados y sesgo fijo 0.08.
No recibe estados del simulador: únicamente canales sensordata declarados.
"""
from collections import deque
import numpy as np


class Encoders:
    def __init__(self,seed=1):
        self.rng=np.random.default_rng(seed)
        self.bias=self.rng.normal(0,.08,6)
        self.history=deque(maxlen=100)
        self.last=-1e9

    def adquirir(self,t,q):
        if t-self.last<.009999: return
        q=np.asarray(q,float)
        if q.shape!=(6,) or not np.isfinite(q).all(): raise ValueError('encoder inválido')
        measured=q+self.bias+self.rng.normal(0,.04,6)
        measured=np.round(measured/(360/4096))*(360/4096)
        measured[5]=np.clip(measured[5],0,100)
        self.history.append((float(t),measured)); self.last=t

    def leer(self,t):
        if not self.history: raise RuntimeError('sin adquisición sensorial inicial')
        candidates=[q for ts,q in self.history if ts<=t-.02]
        return (candidates[-1] if candidates else self.history[0][1]).copy()
