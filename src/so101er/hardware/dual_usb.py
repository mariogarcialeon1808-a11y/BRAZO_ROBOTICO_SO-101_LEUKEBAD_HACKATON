"""Dos USB reales, montaje medido y propiedad conjunta del par. Sin simulador."""
import json
from pathlib import Path
import numpy as np
from .calibracion import guardar_atomicamente,BusSoloLectura
from .prueba_base import estado
from .chat_usb import BrazoChat,incidencias,datos_cal
from .alineacion import Alineacion


def recuperar_sin_par(root,ports):
    """Acción explícita con brazos apoyados: solo desactiva par, nunca posiciones."""
    from .usb import Bus,puertos
    from .manual_usb import desactivar_verificado
    errors=[]
    for port in ports:
        bus=None
        try:
            cal=datos_cal(root,port)
            if next((p['serie'] for p in puertos() if p['puerto']==port),None)!=cal['serie_usb']:
                raise ValueError('el adaptador no corresponde a este brazo')
            bus=Bus(port)
            for i in range(1,7):
                try:desactivar_verificado(bus,i)
                except Exception as e:errors.append(port+': '+str(e))
        except Exception as e:errors.append(port+': '+str(e))
        finally:
            if bus:bus.cerrar()
    if errors:raise RuntimeError('; '.join(errors))


def guardar_montaje(root,separacion_cm,com7_izquierda,confirmado):
    distance=float(separacion_cm)*10
    if not confirmado:raise ValueError('confirma bases fijas, a la misma altura, en paralelo y orientadas hacia el cuadro')
    if not np.isfinite(distance) or not 150<=distance<=2000:raise ValueError('indica la distancia entre centros de las bases, en cm (15–200)')
    data={'version':1,'distancia_mm':distance,'com7_izquierda':bool(com7_izquierda),
          'bases_paralelas_misma_altura':True,'origen':'medida y colocación confirmadas por operador'}
    guardar_atomicamente(Path(root)/'config/montaje_dual.json',data)
    return data


def cargar_montaje(root):
    path=Path(root)/'config/montaje_dual.json'
    if not path.exists():raise ValueError('Dos brazos: falta medir y guardar la separación de bases en la pestaña 3')
    d=json.loads(path.read_text(encoding='utf8'));distance=float(d['distancia_mm'])
    if (not np.isfinite(distance) or not 150<=distance<=2000 or
        not d.get('bases_paralelas_misma_altura') or type(d.get('com7_izquierda')) is not bool):
        raise ValueError('montaje dual inválido: comprueba distancia, lado y orientación de las bases')
    return d


def aplicar_montaje(cfg,montaje):
    d=montaje['distancia_mm'];left='COM7' if montaje['com7_izquierda'] else 'COM8'
    cfg.modo='dos';cfg.simulado=False
    for n,x,p in [('izq',-d/2,left),('der',d/2,'COM8' if left=='COM7' else 'COM7')]:
        cfg.brazos[n].base_mm=np.array([x,0.,0.]);cfg.brazos[n].orientacion_grados=90.;cfg.brazos[n].puerto=p
    # Margen geométrico conservador para pinzas y error de seguimiento.
    # No es un sensor de contacto ni una certificación del montaje.
    cfg.limites.distancia_min_brazos_mm=max(160.,cfg.limites.distancia_min_brazos_mm)


def incidencias_dual(root):
    messages=[]
    try:cargar_montaje(root)
    except Exception as e:messages.append(str(e))
    for port in ('COM7','COM8'):messages.extend(incidencias(root,port,permitir_entrada_inicial=True))
    return list(dict.fromkeys(messages))


class EstadoGrupo:
    def __init__(self,owner):self.owner=owner
    @property
    def closed(self):return all(b.native.closed for b in self.owner.brazos.values())
    @property
    def entrando(self):return any(b.native.entrando for b in self.owner.brazos.values())
    @property
    def error(self):
        return next((b.port+': '+b.native.error for b in self.owner.brazos.values() if b.native.error),None)
    def parar(self):
        for b in self.owner.brazos.values():
            if not b.native.closed:b.native.parar()


class GrupoReal:
    def __init__(self,root):
        self.root=Path(root);self.montaje=cargar_montaje(root)
        self.brazos={};self.port='COM7 + COM8';self.native=EstadoGrupo(self)

    def activar(self):
        # Todas las comprobaciones y lecturas antes de activar el primer servo.
        issues=incidencias_dual(self.root)
        if issues:raise ValueError('\n'.join(issues))
        from ..config import cargar
        from ..control.semantico import MotorGestos
        cfg=cargar(self.root/'config/so101er.toml');aplicar_montaje(cfg,self.montaje)
        from .manual_usb import objetivo_entrada
        motor=MotorGestos(cfg);chains={};paths={};initial={}
        for n in cfg.brazos_activos:
            port=cfg.brazos[n].puerto;bus=BusSoloLectura(port)
            try:raw=estado(bus)['raw']
            finally:bus.cerrar()
            a=Alineacion.cargar(self.root,port,datos_cal(self.root,port));q=a.a_modelo(raw)
            target=objetivo_entrada(a.cal,raw);initial[n]=raw.copy();paths[n]=[]
            for s in np.linspace(0,1,11):
                q=a.a_modelo(raw+(target-raw)*s)
                # Solo esta transición inicial admite la incertidumbre entre
                # el extremo observado y el nominal URDF. Mesa/separación iguales.
                problem=motor.seguridad.problema_pose(n,q,margen_articular=3.)
                if problem:raise ValueError(port+': '+problem)
                paths[n].append(motor.seguridad.cadena_mundo(n,q))
            problem=motor.seguridad.problema_pose(n,a.a_modelo(target))
            if problem:raise ValueError(port+': '+problem)
        # Comprobar combinaciones de progreso: ambos USB no son un reloj duro.
        for left in paths['izq']:
            for right in paths['der']:
                problem=motor.seguridad.problema_par({'izq':left,'der':right})
                if problem:raise ValueError(problem)
        try:
            for n in cfg.brazos_activos:
                self.brazos[n]=BrazoChat(self.root,cfg.brazos[n].puerto,entrada_inicial=True,raw_esperado=initial[n])
        except Exception:
            self.native.parar()
            # No soltar un brazo ya activado de improviso. El propietario conserva
            # referencias para que el usuario pueda sujetar y pulsar Soltar ambos.
            raise

    def soltar(self):
        errors=[]
        for b in self.brazos.values():
            if b.native.closed:continue
            try:b.soltar()
            except Exception as e:errors.append(b.port+': '+str(e))
        if errors:raise RuntimeError('; '.join(errors))
