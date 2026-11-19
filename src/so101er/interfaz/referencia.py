"""Referencia visual indicada por el operador; no es una calibración de encoders."""
import json
from pathlib import Path
import numpy as np

DEFAULT=np.array([-3.2,-100.,96.8,-95.,2.8,0.])


def cargar(root,kin):
    path=Path(root)/'config/pose_cero_operativa.json'
    q=np.asarray(json.loads(path.read_text(encoding='utf8'))['q_modelo'] if path.exists() else DEFAULT,float)
    if q.shape!=(6,) or not np.isfinite(q).all():raise ValueError('referencia visual inválida')
    low=np.r_[kin.lim_inf,0];high=np.r_[kin.lim_sup,100]
    if (q<low-.1).any() or (q>high+.1).any():raise ValueError('la referencia visual sale del modelo')
    return np.clip(q,low,high)


def posicion_marca(value,low,high,width):
    if high<=low:return None
    x=8+float(np.clip((value-low)/(high-low),0,1))*max(1,width-16)
    return x,not low<=value<=high
