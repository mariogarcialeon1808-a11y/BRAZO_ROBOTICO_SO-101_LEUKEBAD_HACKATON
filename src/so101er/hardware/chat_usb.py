"""Puente del chatbot al hardware: un brazo activo, sin observaciones MuJoCo."""
import json
from pathlib import Path
import numpy as np
from .alineacion import Alineacion
from .manual_usb import ManualUSB,Coordenadas
from .calibracion import BusSoloLectura,identidad
from .usb import puertos
from .prueba_base import estado

NOMBRES=('base','hombro','codo','muñeca','giro de pinza','apertura de pinza')


def datos_cal(root,port):
    path=Path(root)/'config/calibracion_rangos_usb.json'
    if not path.exists():raise ValueError(f'{port}: faltan rangos; abre CALIBRAR_USB.cmd y guárdalos')
    data=json.loads(path.read_text(encoding='utf8'))
    cal=next((c for c in data['brazos'] if c['puerto']==port),None)
    if cal is None or set(cal['rangos'])!=set(map(str,range(1,7))):raise ValueError(f'{port}: faltan rangos de motores; completa la captura')
    return cal


def incidencias(root,port,permitir_entrada_inicial=False):
    """Diagnóstico de lectura. Cada aviso indica una acción concreta del operador."""
    issues=[];bus=None
    try:
        cal=datos_cal(root,port)
        found=next((p for p in puertos() if p['puerto']==port),None)
        if not found:return [f'{port}: conecta su adaptador USB; Windows no lo detecta']
        if found['serie']!=cal['serie_usb']:return [f'{port}: el adaptador pertenece a otro brazo; revisa la asignación USB']
        try:bus=BusSoloLectura(port)
        except Exception as e:return [f'{port}: puerto ocupado o inaccesible. Sujeta el brazo, pulsa Soltar y cierra el panel de pruebas. Detalle: {e}']
        if identidad(bus)!=cal['identidad_servos']:issues.append(f'{port}: han cambiado offsets o límites; repite rangos y alineación antes de continuar')
        s=estado(bus)
        torque=[bus.leer(i,40,1)[0] for i in range(1,7)]
        if any(torque):issues.append(f'{port}: motores con par activo. Sujeta el brazo y pulsa Soltar en el controlador anterior')
        # Mediana de cinco lecturas: un valor suelto falso (los hay) no bloquea el arranque.
        temperaturas=np.median([s['temperatura']]+[estado(bus)['temperatura'] for _ in range(4)],axis=0)
        for i,temp in enumerate(temperaturas):
            if temp>=50:issues.append(f'{port}, {NOMBRES[i]} (ID {i+1}): {int(temp)} °C. Mantén el brazo sin par y espera a que baje de 50 °C')
        for i,v in enumerate(s['voltaje']):
            if not 100<=v<=135:issues.append(f'{port}, {NOMBRES[i]} (ID {i+1}): tensión {v/10:.1f} V. Revisa la alimentación antes de activar')
        try:Coordenadas(cal,s['raw'])
        except ValueError as e:
            # COM8 admite únicamente la pequeña entrada de codo explícitamente
            # autorizada al armar. El constructor vuelve a validar su magnitud.
            low=np.array([max(cal['rangos'][str(i+1)]['min_raw'],cal['identidad_servos'][i]['min_raw'])+12 for i in range(6)])
            high=np.array([min(cal['rangos'][str(i+1)]['max_raw'],cal['identidad_servos'][i]['max_raw'])-12 for i in range(6)])
            bad=np.flatnonzero((s['raw']<low)|(s['raw']>high))
            r3=cal['rangos']['3']
            automatic=port=='COM8' and list(bad)==[2] and r3['min_raw']<=s['raw'][2]<=r3['max_raw'] and abs(np.clip(s['raw'][2],low[2],high[2])-s['raw'][2])<=3*4096/360
            if permitir_entrada_inicial:
                from .manual_usb import objetivo_entrada
                try:objetivo_entrada(cal,s['raw'])
                except ValueError as entry_error:issues.append(f'{port}: {e}. Entrada inicial bloqueada: {entry_error}')
            elif not automatic:issues.append(f'{port}: {e}')
        try:
            if Alineacion.cargar(root,port,cal) is None:
                issues.append(f'{port}: falta guardar la alineación. Abre Pruebas, marca Alinear este USB, captura la postura, comprueba los seis sentidos y pulsa Guardar alineación')
        except Exception as e:issues.append(f'{port}: repite la alineación; {e}')
        other='COM8' if port=='COM7' else 'COM7'
        if any(p['puerto']==other for p in puertos()):
            other_bus=None
            try:
                other_bus=BusSoloLectura(other)
                if any(other_bus.leer(i,40,1)[0] for i in range(1,7)):
                    issues.append(f'{other}: el otro brazo tiene par activo. Sujétalo y pulsa Soltar en su controlador antes de activar {port}')
            except Exception as e:issues.append(f'{other}: no puedo comprobar que el otro brazo esté libre; cierra su controlador. Detalle: {e}')
            finally:
                if other_bus:other_bus.cerrar()
    except Exception as e:issues.append(f'{port}: lectura fallida; comprueba alimentación y cables de los servos. Detalle: {e}')
    finally:
        if bus:bus.cerrar()
    return issues


class BrazoChat:
    telemetria_temperatura=False  # La supervisa ManualUSB con medidas reales.
    # Constante nominal: lo que tarda una consigna en convertirse en movimiento (ciclo del control
    # USB + respuesta del servo). La reproducción muestrea el plan ese tiempo por delante, para que
    # el brazo real coincida con la voz como en la simulación. No es verdad del simulador.
    # Calibrada con la primera sesión real registrada (15-11-2026, 60°/s, dos brazos): con 0,06 s los
    # encoders seguían 90–100 ms por detrás del plan, con menos de 1° de resto al descontar ese retraso.
    retardo_s=.15
    def __init__(self,root,port,entrada_inicial=False,raw_esperado=None):
        self.port=port;cal=datos_cal(root,port)
        self.alineacion=Alineacion.cargar(root,port,cal)
        if self.alineacion is None:raise ValueError(f'{port}: falta alineación guardada; no se activa ningún motor')
        if entrada_inicial:self.native=ManualUSB(root,port,entrada_inicial=True,raw_esperado=raw_esperado)
        else:self.native=ManualUSB(root,port,entrada_suave=port=='COM8')
        a=self.alineacion.a_modelo(self.native.coords.low)
        b=self.alineacion.a_modelo(self.native.coords.high)
        self.low=np.minimum(a,b);self.high=np.maximum(a,b)
    def leer_articulaciones(self):
        if self.native.error:raise RuntimeError(f'{self.port}: {self.native.error}')
        return self.alineacion.a_modelo(self.native.raw_actual())
    def validar_q(self,q):
        q=np.asarray(q,float).copy()
        q[5]=np.clip(q[5],max(0,self.low[5]),min(100,self.high[5]))
        raw=self.alineacion.a_raw(q)
        for i,r in enumerate(raw):
            if not self.native.coords.low[i]-16<=r<=self.native.coords.high[i]+16:
                raise ValueError(f'{self.port}, {NOMBRES[i]} (ID {i+1}): el gesto pide {r:.0f} cuentas, fuera de {self.native.coords.low[i]:.0f}–{self.native.coords.high[i]:.0f}; ajusta el gesto o revisa su alineación')
        # Cuantización de partida: nunca se manda un objetivo fuera del margen.
        return self.alineacion.a_modelo(np.clip(raw,self.native.coords.low,self.native.coords.high))
    def enviar_objetivo(self,q):
        if self.native.entrando:return  # Solo su supervisor ejecuta la entrada lenta.
        q=self.validar_q(q);self.native.set(self.native.coords.a_ejes(self.alineacion.a_raw(q)))
    def validar_plan(self,plan,nombre=None):
        for q in plan.q[nombre] if nombre is not None else next(iter(plan.q.values())):self.validar_q(q)
    def detener(self):
        if not self.native.closed:self.native.parar()
    def desconectar(self):pass  # Soltar es una acción explícita con el brazo sujeto.
    def soltar(self):self.native.soltar()
