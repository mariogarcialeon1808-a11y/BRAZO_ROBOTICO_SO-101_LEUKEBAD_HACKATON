"""Ajuste de narración a la duración física de gestos completos, sin cambiar tono."""
from fractions import Fraction
import math
import numpy as np


def factor_narracion(anchors,apexes,durations):
    """Separación de ápices suficiente para incluir la recogida del gesto anterior."""
    factor=1.
    for i in range(1,len(anchors)):
        gap=anchors[i]-anchors[i-1]
        if gap<=0:raise ValueError('las anclas deben avanzar entre gestos')
        factor=max(factor,(durations[i-1]+apexes[i]-apexes[i-1]+.08)/gap)
    return factor


def estirar(audio,factor):
    if not math.isfinite(factor) or not 1<=factor<=8:
        raise ValueError('factor temporal fuera de rango')
    if factor<=1.001:return np.asarray(audio,dtype=np.int16).copy()
    import av
    graph=av.filter.Graph()
    source=graph.add_abuffer(sample_rate=24000,format='s16',layout='mono',time_base=Fraction(1,24000))
    current=source
    # Cada filtro atempo admite al menos 0.5–2; encadenar si hace falta.
    tempo=1/factor
    while tempo<.5:
        node=graph.add('atempo','0.5');current.link_to(node);current=node;tempo/=.5
    node=graph.add('atempo',str(tempo));current.link_to(node)
    sink=graph.add('abuffersink');node.link_to(sink);graph.configure()
    frame=av.AudioFrame.from_ndarray(np.asarray(audio,dtype=np.int16)[None],format='s16',layout='mono')
    frame.sample_rate=24000;frame.time_base=Fraction(1,24000);frame.pts=0
    source.push(frame);source.push(None);chunks=[]
    while True:
        try:chunks.append(sink.pull().to_ndarray().ravel())
        except (av.error.EOFError,av.error.BlockingIOError):break
    if not chunks:raise RuntimeError('el ajuste temporal no produjo audio')
    result=np.concatenate(chunks).astype(np.int16)
    # atempo puede abreviar la cola; conservar la línea temporal de las marcas.
    length=round(len(audio)*factor)
    return np.pad(result,(0,max(0,length-len(result))))[:length]
