"""Conversión offline de NPZ SMPL-X (BEAT2/MM-Conv) a posiciones humanas.

Requiere smplx, torch y archivos del modelo corporal obtenidos por el usuario.
Los pesos corporales no se redistribuyen ni se descargan automáticamente.
"""
from pathlib import Path
import numpy as np

NOMBRES = ('Pelvis','LeftHip','RightHip','Spine1','LeftKnee','RightKnee','Spine2',
           'LeftAnkle','RightAnkle','Spine3','LeftFoot','RightFoot','Neck',
           'LeftCollar','RightCollar','Head','LeftShoulder','RightShoulder',
           'LeftElbow','RightElbow','LeftWrist','RightWrist')


def leer_parametros(path):
    with np.load(path,allow_pickle=False) as f:
        if 'poses' not in f.files:
            raise ValueError("requiere NPZ SMPL-X con poses [T,165]; no acepta HumanML3D 263D")
        poses=np.array(f['poses'],dtype=np.float32)
        n=len(poses)
        trans=np.array(f['trans'],dtype=np.float32) if 'trans' in f.files else np.zeros((n,3),np.float32)
        betas=np.array(f['betas'],dtype=np.float32) if 'betas' in f.files else np.zeros(10,np.float32)
    if (poses.ndim!=2 or poses.shape[1]!=165 or n<3 or trans.shape!=(n,3)
            or betas.ndim not in (1,2) or betas.shape[-1]<10
            or (betas.ndim==2 and betas.shape[0] not in (1,n))
            or not all(np.isfinite(x).all() for x in (poses,trans,betas))):
        raise ValueError("parámetros SMPL-X inválidos")
    return poses,trans,betas


def convertir(path, modelo_dir, salida, genero='neutral'):
    import torch
    import smplx
    if genero not in ('neutral','male','female'): raise ValueError("género inválido")
    if not Path(modelo_dir).is_dir(): raise ValueError("falta carpeta de modelo corporal SMPL-X")
    poses,trans,betas=leer_parametros(path)
    model=smplx.create(str(modelo_dir),model_type='smplx',gender=genero,use_pca=False,ext='npz',
                       num_betas=10,flat_hand_mean=True).eval()
    output=[]
    with torch.no_grad():
        for start in range(0,len(poses),128):
            stop=min(start+128,len(poses)); p=torch.from_numpy(poses[start:stop])
            b=np.repeat(betas[None],stop-start,axis=0) if betas.ndim==1 else (
                np.repeat(betas,stop-start,axis=0) if len(betas)==1 else betas[start:stop])
            result=model(global_orient=p[:,:3],body_pose=p[:,3:66],jaw_pose=p[:,66:69],
                         leye_pose=p[:,69:72],reye_pose=p[:,72:75],
                         left_hand_pose=p[:,75:120],right_hand_pose=p[:,120:165],
                         betas=torch.from_numpy(b[:,:10].copy()),
                         expression=torch.zeros((stop-start,10)),
                         transl=torch.from_numpy(trans[start:stop]))
            output.append(result.joints[:,:22].cpu().numpy())
    np.savez_compressed(salida,joints_xyz=np.concatenate(output),joint_names=np.array(NOMBRES),
                        source_sha256=np.array(__import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()))


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archivo'); p.add_argument('--modelo-dir',required=True)
    p.add_argument('--salida',required=True); p.add_argument('--genero',default='neutral')
    args=p.parse_args(); convertir(args.archivo,args.modelo_dir,args.salida,args.genero)


if __name__=='__main__': main()
