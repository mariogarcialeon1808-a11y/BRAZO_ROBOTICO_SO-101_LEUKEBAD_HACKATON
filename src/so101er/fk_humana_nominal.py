"""FK de rotaciones SMPL-X sobre una antropometría NOMINAL propia, sin malla.

Conserva rotaciones registradas; no reproduce betas/forma corporal ni posiciones
exactas del actor. Alternativa explícita al modelo SMPL-X sujeto a registro.
Solo se usa offline como referencia de gesto, jamás como sensor del robot.
"""
import numpy as np
from .convertir_smplx import NOMBRES,leer_parametros

PADRES=(-1,0,0,0,1,2,3,4,5,6,7,8,9,9,9,12,13,14,16,17,18,19)
OFFSETS=np.array([[0,0,0],[.09,-.09,0],[-.09,-.09,0],[0,.11,0],
 [0,-.4,0],[0,-.4,0],[0,.12,0],[0,-.4,0],[0,-.4,0],[0,.12,0],
 [0,0,.12],[0,0,.12],[0,.14,0],[.08,.06,0],[-.08,.06,0],[0,.12,0],
 [.10,0,0],[-.10,0,0],[.28,0,0],[-.28,0,0],[.26,0,0],[-.26,0,0]])


def rotacion(v):
    v=np.asarray(v,float); theta=np.linalg.norm(v)
    if theta<1e-10:return np.eye(3)
    x,y,z=v/theta
    k=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+np.sin(theta)*k+(1-np.cos(theta))*(k@k)


def convertir_nominal(path,salida):
    poses,trans,_=leer_parametros(path)
    xyz=np.zeros((len(poses),22,3)); rotations=np.zeros((len(poses),22,3,3))
    for t,p in enumerate(poses):
        for j,parent in enumerate(PADRES):
            local=rotacion(p[j*3:j*3+3])
            rotations[t,j]=local if parent<0 else rotations[t,parent]@local
            xyz[t,j]=trans[t] if parent<0 else xyz[t,parent]+rotations[t,parent]@OFFSETS[j]
    import hashlib
    from pathlib import Path
    np.savez_compressed(salida,joints_xyz=xyz,joint_names=np.array(NOMBRES),
                        conversion=np.array('FK antropometría nominal; NO forma corporal SMPL-X exacta'),
                        source_sha256=np.array(hashlib.sha256(Path(path).read_bytes()).hexdigest()))
