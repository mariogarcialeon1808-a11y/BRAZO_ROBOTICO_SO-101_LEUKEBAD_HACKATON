"""Importación offline de movimiento humano y adaptación a consignas sensoriales.

No carga pesos ni ejecuta código de terceros. BVH -> FK humano -> muñeca relativa
al hombro -> motivo normalizado. El esqueleto humano nunca se usa como estado robot.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from .semantico import Intencion, unidad


def leer_bvh(path):
    """FK de BVH con canales intrínsecos en el orden declarado. Unidades nativas."""
    text = Path(path).read_text(encoding="utf-8-sig")
    hierarchy, motion = text.split("MOTION", 1)
    tokens = iter(re.findall(r"[^\s{}]+|[{}]", hierarchy))
    names, parents, offsets, channels = [], [], [], []
    if next(tokens) != "HIERARCHY" or next(tokens) != "ROOT":
        raise ValueError("BVH sin raíz")
    def node(parent, name):
        idx = len(names)
        names.append(name); parents.append(parent); offsets.append(None); channels.append([])
        if next(tokens) != "{": raise ValueError("jerarquía BVH inválida")
        for token in tokens:
            if token == "}": break
            if token == "OFFSET": offsets[idx] = np.array([float(next(tokens)) for _ in range(3)])
            elif token == "CHANNELS": channels[idx] = [next(tokens) for _ in range(int(next(tokens)))]
            elif token == "JOINT": node(idx,next(tokens))
            elif token == "End":
                if next(tokens) != "Site": raise ValueError("End Site inválido")
                node(idx,name+"_end")
            else: raise ValueError(f"token BVH desconocido: {token}")
        if offsets[idx] is None: raise ValueError("OFFSET ausente")
    node(-1,next(tokens))
    header = re.match(r"\s*Frames:\s*(\d+)\s*Frame\s+Time:\s*([\d.eE+-]+)\s*",motion)
    if header is None: raise ValueError("cabecera de movimiento BVH inválida")
    n, dt = int(header[1]), float(header[2])
    values = np.fromstring(motion[header.end():],sep=" ")
    nc = sum(map(len,channels))
    if n<2 or n>100000 or not np.isfinite(dt) or dt<=0 or len(values)!=n*nc or not np.isfinite(values).all():
        raise ValueError("muestras BVH inválidas")
    values = values.reshape(n,nc)
    transforms = np.zeros((n,len(names),4,4))
    cursor = 0
    for i, cc in enumerate(channels):
        local = np.repeat(np.eye(4)[None],n,axis=0)
        local[:,:3,3] = offsets[i]
        for channel in cc:
            axis = "XYZ".find(channel[0])
            if axis<0 or channel[1:] not in ("position","rotation"):
                raise ValueError(f"canal BVH inválido: {channel}")
            op = np.repeat(np.eye(4)[None],n,axis=0)
            if channel.endswith("position"): op[:,axis,3]=values[:,cursor]
            else:
                angle=np.radians(values[:,cursor]); c,s=np.cos(angle),np.sin(angle)
                a,b=(axis+1)%3,(axis+2)%3
                op[:,a,a]=c; op[:,a,b]=-s; op[:,b,a]=s; op[:,b,b]=c
            local=local@op; cursor+=1
        transforms[:,i]=local if parents[i]<0 else transforms[:,parents[i]]@local
    if len(set(names)) != len(names): raise ValueError("nombres de articulación repetidos")
    return np.arange(n)*dt, names, transforms[:,:,:3,3]


@dataclass(frozen=True)
class Motivo:
    id: str
    fuente: str
    licencia: str
    sha256: str
    etiquetas: tuple[str,...]
    perfil: tuple[float,...]
    forma: tuple

    def guardar(self,path):
        from dataclasses import asdict
        Path(path).write_text(json.dumps(asdict(self),ensure_ascii=False,indent=2),encoding="utf-8")

    @staticmethod
    def cargar(path):
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        m=Motivo(**data)
        validar_perfil(m.perfil)
        forma=np.array(m.forma,float)
        if forma.shape!=(33,3) or not np.isfinite(forma).all(): raise ValueError("forma inválida")
        if not m.fuente or not m.licencia or not m.sha256: raise ValueError("procedencia ausente")
        return m


def validar_perfil(values):
    p=np.asarray(values,float)
    if p.shape!=(17,) or not np.isfinite(p).all() or p[0]!=0 or p[-1]!=1 or (np.diff(p)<0).any():
        raise ValueError("perfil temporal inválido: 17 valores monótonos entre 0 y 1")
    return p


def extraer(path, *, id, fuente, licencia, etiquetas, hombro, muneca,
            inicio=0, fin=None, fps=None):
    """Recorte explícito de un trazo. NPZ admite SOLO joints_xyz + joint_names.

    SMPL-X poses/263D HumanML3D no son coordenadas; necesitan conversión upstream.
    No se carga pickle ni se adivinan unidades o índices de articulaciones.
    """
    path=Path(path)
    if not fuente or not licencia: raise ValueError("se requiere procedencia y licencia")
    if path.suffix.lower()=='.bvh': times,names,joints=leer_bvh(path)
    elif path.suffix.lower()=='.npz':
        with np.load(path,allow_pickle=False) as f:
            if not {'joints_xyz','joint_names'}.issubset(f.files):
                raise ValueError("requiere joints_xyz y joint_names; convierte antes SMPL-X con su modelo corporal")
            joints=np.array(f['joints_xyz'],float); names=f['joint_names'].tolist()
        if fps is None or not np.isfinite(fps) or fps<=0: raise ValueError("falta FPS válido")
        times=np.arange(len(joints))/fps
    else: raise ValueError("formato no soportado")
    if joints.shape!=(len(times),len(names),3) or not np.isfinite(joints).all(): raise ValueError("joints inválidos")
    if hombro not in names or muneca not in names: raise ValueError("articulaciones no encontradas")
    fin=len(times) if fin is None else fin
    if not isinstance(inicio,int) or not isinstance(fin,int) or not 0<=inicio<fin-2<=len(times)-2:
        raise ValueError("recorte de trazo inválido")
    xyz=(joints[:,names.index(muneca)]-joints[:,names.index(hombro)])[inicio:fin]
    t=times[inicio:fin]; t=(t-t[0])/(t[-1]-t[0])
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xyz,axis=0),axis=1))]
    if lengths[-1]<1e-6: raise ValueError("clip estático: sin perfil de movimiento")
    profile=np.interp(np.linspace(0,1,17),t,lengths/lengths[-1])
    # Forma relativa normalizada, aún en ejes del dataset. Se exige transformación explícita.
    shape=np.column_stack([np.interp(np.linspace(0,1,33),t,xyz[:,i]) for i in range(3)])
    shape-=shape[0]
    shape/=max(np.max(np.linalg.norm(shape,axis=1)),1e-6)
    return Motivo(id,fuente,licencia,hashlib.sha256(path.read_bytes()).hexdigest(),tuple(etiquetas),
                  tuple(profile),tuple(map(tuple,shape)))


def adaptar(motivo: Motivo, objetivo: Intencion) -> Intencion:
    """Transfiere ritmo; conserva la geometría y el eje exigidos por el referente.

    Señalar/recorrer permanecen exactos. Para retargeting de la FORMA completa se
    utiliza forma_en_marco con una transformación y escala expresivas explícitas.
    """
    validar_perfil(motivo.perfil)
    return replace(objetivo,perfil_tiempo=tuple(motivo.perfil))


class Biblioteca:
    """Catálogo ligero, cargado una vez. Etiquetas explícitas, sin inferir emociones."""
    def __init__(self, archivos):
        self.motivos = [Motivo.cargar(p) for p in archivos]
        ids = [m.id for m in self.motivos]
        if len(set(ids)) != len(ids): raise ValueError("identificadores duplicados")

    def elegir(self, etiquetas):
        etiquetas = set(etiquetas)
        candidatos = [m for m in self.motivos if etiquetas.intersection(m.etiquetas)]
        if not candidatos: raise LookupError("sin motivo compatible; mantener gesto procedural")
        return min(candidatos,key=lambda m:(-len(etiquetas.intersection(m.etiquetas)),m.id))


def forma_en_marco(motivo, centro_mm, marco, escala_mm, eje, brazo):
    """Retargeting cartesiano de muñeca, no copia de ángulos humanos al SO-101.

    Una transformación ortonormal explícita evita adivinar qué eje del dataset es arriba.
    La salida debe pasar por compilar y puede rechazarse por alcance/orientación.
    """
    shape=np.asarray(motivo.forma,float); frame=np.asarray(marco,float)
    center=np.asarray(centro_mm,float); scale=np.asarray(escala_mm,float)
    if (shape.shape!=(33,3) or frame.shape!=(3,3) or center.shape!=(3,) or scale.shape!=(3,)
            or not all(np.isfinite(x).all() for x in (shape,frame,center,scale))
            or not np.allclose(frame.T@frame,np.eye(3),atol=1e-6) or np.linalg.det(frame)<.999
            or (scale<=0).any()): raise ValueError("marco o escala inválidos")
    points=center+(shape*scale)@frame.T
    axes=tuple(tuple(unidad(eje)) for _ in points)
    return Intencion('extension',brazo,tuple(map(tuple,points)),axes,
                     perfil_tiempo=tuple(motivo.perfil))
