"""Aplicación integrada: cuadro, Gemini, audio, micro y control local sensorial."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np

from .config import cargar
from .control.semantico import MotorGestos,ejemplos
from .control.referencias import Motivo,adaptar
from .control.anclaje import senalar_plano,barrer_region
from .control.reproduccion import ControlLocal
from .control import calculo_aparte,expresion
from .control.escenico import pose_reposo,pose_trabajo,transicion,ensanchar_abanico,compilar_actuacion
from .aplicacion_servicios import claves,Vision,Voz,Microfono,tiempo_ancla
from .idiomas import DEMO,IDIOMAS,POR_DEFECTO,ancla_de,detectar,frase,unidades


def cargar_motivos(root):
    result={}
    for dataset in ('seg','beat2','mmconv'):
        result[dataset]=[]
        for f in (Path(root)/'datos/referencias'/dataset).glob('*.json'):
            try:result[dataset].append(Motivo.cargar(f))
            except (ValueError,TypeError,KeyError):pass
    return result


ESTIRADO_MAX=1.35   # la voz no se ralentiza más que esto para esperar a los brazos
VELOCIDAD_RETORNO=30.   # °/s como mucho en la vuelta a punto cero
# Paradas tras las que el operador puede pedir la vuelta a punto cero sin soltar los brazos.
# Temperatura, tensión, comunicaciones o una postura insegura siguen exigiendo soltar.
PARADAS_RECUPERABLES=('carga indicada','no sigue la consigna','error de seguimiento')


def encajar_en_la_voz(gestos,maximo=ESTIRADO_MAX):
    """Renuncia a los gestos que obligarían a frenar la voz más de `maximo`.

    `gestos` son (instante del ancla en la voz, ápice dentro del plan, plan), en orden.
    Antes un factor mayor de 8 hacía fallar el turno entero («factor temporal fuera de rango»).
    Cada plan acaba en reposo y el siguiente parte de él, así que quitar uno no rompe la continuidad.
    Devuelve (gestos que quedan, factor de ralentización necesario, cuántos se han quitado).
    """
    from .sincronia.ritmo import factor_narracion
    gestos=list(gestos);quitados=0
    def necesario():
        return factor_narracion([a for a,_,_ in gestos],[p for _,p,_ in gestos],[g.tiempos[-1] for _,_,g in gestos])
    scale=necesario()
    while scale>maximo and len(gestos)>1:
        peor=max(range(1,len(gestos)),key=lambda i:(gestos[i-1][2].tiempos[-1]+gestos[i][1]-gestos[i-1][1])
                 /(gestos[i][0]-gestos[i-1][0]))
        del gestos[peor];quitados+=1;scale=necesario()
    return gestos,scale,quitados


def aplicar_perfil(cfg,v):
    """Límites de planificación para `v` °/s, en la misma proporción que la simulación (150°/s, 600°/s²)."""
    cfg.limites.velocidad[:]=v;cfg.limites.aceleracion[:]=4*v;cfg.limites.tiron[:]=40*v
    cfg.limites.velocidad[5]=max(60.,v)
    return v


def perfil_real(cfg,root):
    """Límites de planificación de los brazos reales, de `[real] velocidad_grados_s`. Devuelve los °/s."""
    from .hardware.manual_usb import velocidad_real
    return aplicar_perfil(cfg,velocidad_real(root))


def preparar_recursos(root,port):
    """Todo el trabajo pesado antes de activar el primer motor."""
    from types import SimpleNamespace
    from . import obra
    from .hardware.chat_usb import datos_cal
    from .hardware.alineacion import Alineacion
    import sounddevice
    from google import genai
    cfg=cargar(Path(root)/'config/so101er.toml');cfg.frecuencia_hz=50
    if port=='Ambos':
        from .hardware.dual_usb import cargar_montaje,aplicar_montaje
        aplicar_montaje(cfg,cargar_montaje(root))
    else:
        cfg.modo='uno';cfg.brazo='izq';cfg.simulado=False;cfg.brazos['izq'].base_mm=np.zeros(3)
    perfil_real(cfg,root)
    imagen,imagen_nombre=obra.preparar_adaptada(cfg,Path(root)/'obra');motor=MotorGestos(cfg)
    if port=='Ambos':
        from .hardware.vista_dual import VistaDual
        vista=VistaDual(cfg,imagen)
        poses={n:Alineacion.cargar(root,cfg.brazos[n].puerto,datos_cal(root,cfg.brazos[n].puerto)).q for n in cfg.brazos_activos}
        vista.foto(poses)
    else:
        from .pruebas_modelo import Modelo
        vista=Modelo();vista.foto(Alineacion.cargar(root,port,datos_cal(root,port)).q,0)
    # La escena de la pantalla 3D se compila aquí, con los motores aún sin par: hacerlo después deja
    # sin atender el bucle USB de los brazos hasta 0,8 s («pico de latencia»).
    exhibicion=None
    try:
        from .hardware.pantalla import MundoDeExhibicion
        exhibicion=MundoDeExhibicion(cfg,cfg.brazos_activos,imagen)
    except Exception:pass                                    # sin ella, la pantalla 3D la compila al abrirse
    return SimpleNamespace(cfg=cfg,imagen=imagen,imagen_nombre=imagen_nombre,motor=motor,motivos=cargar_motivos(root),exhibicion=exhibicion,
                           keys=claves(cfg.conversacion.get('env')),vista=vista,usado=False)


class SesionIntegrada:
    # Imagen en directo y ventanas de exhibición. Son consignas y dibujo: nada de esto decide un movimiento.
    directo=None              # FuenteVideo cuando el cuadro es una cámara o un vídeo en directo
    directo_rotulo=''
    imagen_rotulo_libre=None  # nombre de una imagen que no está en la galería (el último fotograma del directo)
    en_turno=0                # turnos en curso: mientras se explica, el cuadro muestra la imagen analizada
    audio_actual=None
    idioma=POR_DEFECTO        # idioma de la conversación; cada turno se queda con el que había al empezar
    por_frases=False          # turno frase a frase (lo activa la configuración al crear la sesión)
    calculo=None              # proceso aparte que calcula los gestos del turno frase a frase
    cara=None                 # cara del robot en una página aparte (so101er.cara). Solo salida: el control no la lee
    plegar_al_acabar=False    # los brazos reales vuelven a punto cero al terminar cada respuesta ([real] de la configuración)
    _imagen_cara=None
    vista_aparte=None         # pantalla de exhibición (escena, imagen y cara), abierta a petición
    exhibicion=None
    _directo_cache=(None,None)

    def __init__(self,root,ventana=True,voz='elevenlabs',modelo='gemini-robotics-er-2-preview',
                 imagen=None,real=False,notificar=print,brazo_real=None,recursos=None):
        self.root=Path(root);self.notificar=notificar;self.closed=False
        self.real=real;self.liberado=False;self.plegado=None;self.desplegado=not real;self.velocidad=None
        self.cfg=recursos.cfg if recursos else cargar(self.root/'config/so101er.toml');self.cfg.frecuencia_hz=50
        if real:
            if brazo_real is None:raise ValueError('Usa CHATBOT_REAL.cmd: primero se comprueba y activa un único brazo alineado')
            if hasattr(brazo_real,'brazos'):
                from .hardware.dual_usb import aplicar_montaje
                aplicar_montaje(self.cfg,brazo_real.montaje)
            else:
                self.cfg.modo='uno';self.cfg.brazo='izq';self.cfg.simulado=False
                self.cfg.brazos['izq'].base_mm=np.zeros(3)
            self.velocidad=perfil_real(self.cfg,self.root)
        if imagen:self.cfg.cuadro.imagen=str(Path(imagen).resolve())
        from . import obra
        from .galeria import Galeria,proporcion
        # La imagen siempre llega con la proporción del rectángulo configurado: cambiarla no toca la geometría.
        self.galeria=Galeria(self.root/'obra');self.proporcion=proporcion(self.cfg)
        if recursos:self.imagen,self.imagen_nombre=recursos.imagen,getattr(recursos,'imagen_nombre',None)
        else:self.imagen,self.imagen_nombre=obra.preparar_adaptada(self.cfg,self.root/'obra')
        self.motor=recursos.motor if recursos else MotorGestos(self.cfg);self.mundo=None
        if real:
            self.brazos=brazo_real.brazos if hasattr(brazo_real,'brazos') else {'izq':brazo_real}
            rests={}
            for n,b in self.brazos.items():
                raw=np.clip(b.alineacion.raw,b.native.coords.low,b.native.coords.high)
                rests[n]=b.alineacion.a_modelo(raw)
            if len(rests)==1:self.motor.reposo_real=next(iter(rests.values()))
            else:self.motor.reposos_reales=rests
            self._fijar_postura_trabajo(rests)
        else:
            from .hardware.mujoco_sim import MundoMuJoCo
            self.mundo=MundoMuJoCo(self.cfg,self.cfg.brazos_activos,self.imagen)
            initial={n:pose_reposo(self.motor) for n in self.motor.marcos}
            self.brazos={n:self.mundo.brazo(n,q) for n,q in initial.items()}
            self.mundo.iniciar(ventana=ventana)
        self.control=ControlLocal(self.motor,self.brazos);self._seguimiento=None
        if real:self._abrir_seguimiento()
        if real and ventana:
            try:
                from .hardware.proyeccion import Proyeccion
                self.mundo=Proyeccion(self.cfg,self.imagen,self.brazos)
            except Exception as e:self.notificar('Vista 3D no disponible: '+str(e))
        self.keys=recursos.keys if recursos else claves(self.cfg.conversacion.get('env'))
        self.vision=None;self.modelo=modelo;self.voz=Voz(self.keys,voz,self.cfg.conversacion.get('voces'));self.micro=Microfono()
        self.cancel=threading.Event();self.ticket=0;self.lock=threading.RLock()
        self.audio_actual=None
        self.pool=ThreadPoolExecutor(2,thread_name_prefix='voz-adelantada')
        self.motivos=recursos.motivos if recursos else cargar_motivos(self.root)
        self.dataset='beat2' if self.motivos['beat2'] else 'seg'
        self.exhibicion=getattr(recursos,'exhibicion',None)   # escena de la pantalla 3D, compilada antes de dar par
        self.por_frases=bool(self.cfg.conversacion.get('por_frases',True))
        self.preparar_calculo()
        if recursos:recursos.usado=True
        from .cara import crear,leer_seccion
        self.cara=crear(self.root,self.imagen,self.notificar);self._imagen_cara=self.imagen
        self.plegar_al_acabar=bool(real and leer_seccion(self.root,'real',{'punto_cero_tras_respuesta':True})['punto_cero_tras_respuesta'])

    def _abrir_seguimiento(self):
        """Guarda plan y encoders de cada ciclo con plan activo. Solo diagnóstico: nada lo lee para decidir."""
        names=list(self.brazos);nombre=time.strftime('seguimiento_%Y%m%d_%H%M%S.csv')
        def fila(now,t,esperado,measured):
            try:
                if self._seguimiento is None:   # el archivo se crea con el primer movimiento, no al abrir la sesión
                    folder=self.root/'salidas/diagnostico';folder.mkdir(parents=True,exist_ok=True)
                    self._seguimiento=open(folder/nombre,'w',encoding='utf8',buffering=1<<16)
                    self._seguimiento.write('t,t_plan,'+','.join(f'{n}_{k}{j}' for n in names for k in ('plan','medido') for j in range(1,6))+'\n')
                self._seguimiento.write(f'{now:.3f},{t:.3f},'+','.join(f'{v:.2f}' for n in names for a in (esperado[n],measured[n]) for v in a[:5])+'\n')
            except (OSError,ValueError):self.control.registro=None
        self.control.registro=fila

    def _cerrar_seguimiento(self):
        f,self._seguimiento=self._seguimiento,None
        if f is not None:
            self.control.registro=None
            try:f.close()
            except OSError:pass

    def _informar_carga(self):
        """Carga máxima que han medido los servos desde el último aviso. Solo informa; no decide nada."""
        if not self.real:return
        from .hardware.chat_usb import NOMBRES
        partes=[]
        for b in self.brazos.values():
            native=getattr(b,'native',None);pico=getattr(native,'carga_pico',None)
            if pico is None:continue
            bruta=getattr(native,'carga_bruta_pico',None)
            i=int(np.argmax(pico));texto=f'{b.port} {NOMBRES[i]} {int(pico[i])}'
            if bruta is not None:texto+=f' (indicada {int(np.max(bruta))})'
            partes.append(texto);native.carga_pico=None;native.carga_bruta_pico=None
        if partes:self.notificar('Carga máxima del turno, descontada la velocidad (el control se detiene a 450): '+', '.join(partes)+'.')

    def _fijar_postura_trabajo(self,plegados):
        """Reposo entre gestos = postura en el aire de la simulación, si el brazo real llega a ella.

        Con el reposo en la postura plegada de la alineación (apoyada en los topes) cada gesto
        tenía que desplegar y volver a plegar el brazo entero, y los acentos no cabían.
        Solo calibración, consignas y FK nominal; si no se puede validar, se conserva lo anterior.
        """
        try:
            trabajo=pose_trabajo(self.motor)
            reposos={n:b.validar_q(trabajo) for n,b in self.brazos.items()}
            plan=transicion(self.motor,plegados,reposos)
            for n,b in self.brazos.items():b.validar_plan(plan,n)
        except Exception as e:
            self.notificar('Postura de trabajo no disponible, se usa la plegada: '+str(e));self.desplegado=True;return
        self.plegado={n:q.copy() for n,q in plegados.items()}
        if len(reposos)==1:self.motor.reposo_real=next(iter(reposos.values()))
        else:self.motor.reposos_reales=reposos

    def _mover_a(self,destino,aviso):
        """Programa una transición validada desde lo medido. Devuelve el instante en que acaba."""
        plan=transicion(self.motor,self.inicio_plan(),destino)
        for n,b in self.brazos.items():b.validar_plan(plan,n)
        self.control.programar(plan)
        self.notificar(f'{aviso} ({plan.tiempos[-1]:.0f} s)…')
        return time.perf_counter()+float(plan.tiempos[-1])

    def fijar_velocidad(self,v):
        """Cambia en caliente el perfil de los brazos reales. Es una consigna del operador."""
        if not self.real or self.liberado:return
        from .hardware.manual_usb import VELOCIDAD_BASE,VELOCIDAD_MAXIMA
        v=float(np.clip(v,VELOCIDAD_BASE,VELOCIDAD_MAXIMA))
        self.interrumpir()
        with self.lock:
            aplicar_perfil(self.cfg,v);self.velocidad=v
            for b in self.brazos.values():b.native.vel=v   # misma cifra para la rampa USB y el perfil del servo
        self.notificar(f'Perfil de {v:.0f}°/s'+(' (el de la simulación).' if v>=VELOCIDAD_MAXIMA else '. La simulación va a 150°/s.'))

    def desplegar(self):
        """La primera vez lleva los brazos de la postura plegada a la de trabajo. 0 si no hace falta."""
        if self.desplegado or self.plegado is None:return 0.
        return self._mover_a({n:pose_reposo(self.motor,n) for n in self.brazos},'Desplegando a la postura de trabajo')

    def volver_a_cero(self):
        """Lleva los brazos, despacio, a punto cero: la postura de referencia de la alineación.

        Sirve en cualquier momento (interrumpe lo que esté haciendo) y también tras una parada por
        carga o por seguimiento: la reconoce y vuelve sin tener que soltar y preparar de nuevo. El
        recorrido se valida entero antes de moverse y todas las protecciones siguen activas.
        """
        if not self.real or self.liberado or self.plegado is None:return
        self.interrumpir()
        with self.lock:
            self.cancel=threading.Event();cancel=self.cancel
        def run():
            try:
                parada=self.control.error
                if parada:
                    if not any(k in parada for k in PARADAS_RECUPERABLES):
                        self.notificar('Tras esta parada no se puede volver a punto cero: '+parada+'. Sujeta los brazos y pulsa Soltar.');return
                    for b in self.brazos.values():b.native.reanudar()
                    self.control.reanudar()
                    self.notificar('Parada reconocida: '+parada+'.')
                while self.control.frenada is not None:
                    if self.control.error or cancel.wait(.02):return
                self.desplegado=False
                aplicar_perfil(self.cfg,min(self.velocidad or 20.,VELOCIDAD_RETORNO))
                try:fin=self._mover_a(self.plegado,'Volviendo a punto cero')
                finally:aplicar_perfil(self.cfg,self.velocidad or 20.)
                while time.perf_counter()<fin+.3:
                    if self.control.error or cancel.wait(.02):return
                self.notificar('Brazos en punto cero. Puedes seguir preguntando, o sujetarlos y pulsar Soltar.')
            except Exception as e:self.notificar('No se pudo volver a punto cero: '+str(e))
        threading.Thread(target=run,daemon=True).start()

    plegar=volver_a_cero   # nombre anterior

    def interrumpir(self):
        with self.lock:
            self.cancel.set();self.ticket+=1
            import sounddevice as sd
            if self.audio_actual is not None:self.audio_actual.cerrar();self.audio_actual=None
            sd.stop();self.control.parar()
            if self.cara:self.cara.callar(True)

    def estado(self):
        return {n:[round(float(v),1) for v in q] for n,q in self.control.medir().items()}

    def inicio_plan(self):
        measured=self.control.medir()
        return {n:self.brazos[n].validar_q(q) if self.real else q for n,q in measured.items()}

    def jpeg(self,seleccion=None):
        """La imagen para la IA. Con `seleccion`, lleva dibujado en naranja el recuadro o el punto que ha marcado el operador."""
        import cv2
        img=self.imagen
        width=min(768,img.shape[1]);img=cv2.resize(img,(width,round(img.shape[0]*width/img.shape[1])),interpolation=cv2.INTER_AREA)
        if seleccion:
            img=img.copy();alto,ancho=img.shape[:2];naranja=(0,140,255)
            def pixel(p):return int(round(p[1]/1000*ancho)),int(round(p[0]/1000*alto))
            if seleccion.get('region'):cv2.rectangle(img,pixel(seleccion['region'][0]),pixel(seleccion['region'][1]),naranja,3,cv2.LINE_AA)
            else:cv2.circle(img,pixel(seleccion['punto']),max(10,ancho//40),naranja,3,cv2.LINE_AA)
        return cv2.imencode('.jpg',img)[1].tobytes()

    @staticmethod
    def nota_seleccion(seleccion):
        """Lo que se añade a la petición para que la IA sepa qué ha marcado el operador en la imagen. Vacío sin selección."""
        if not seleccion:return ''
        if seleccion.get('region'):
            (y0,x0),(y1,x1)=seleccion['region']
            return (f'\nEl usuario ha marcado en la imagen, con un recuadro naranja, la región [[{y0:.0f},{x0:.0f}],[{y1:.0f},{x1:.0f}]] '
                    '(coordenadas [y,x] de 0 a 1000). La petición se refiere a esa región: responde solo sobre lo que hay dentro de ella, '
                    'con detalle, y si usas senalar o region hazlo dentro de ese recuadro. El recuadro naranja no forma parte de la imagen: '
                    'es solo la marca del usuario. No lo describas ni lo nombres.')
        y,x=seleccion['punto']
        return (f'\nEl usuario ha señalado en la imagen, con un círculo naranja, el punto [{y:.0f},{x:.0f}] (coordenadas [y,x] de 0 a 1000). '
                'La petición se refiere a lo que hay en ese punto y justo a su alrededor: responde solo sobre eso, con detalle, '
                'y si usas senalar hazlo sobre ese punto. El círculo naranja no forma parte de la imagen: es solo la marca del usuario. '
                'No lo describas ni lo nombres; describe lo que hay debajo de él.')

    def rotulo_imagen(self):
        """Nombre de la imagen cargada, para mostrarlo."""
        from .galeria import EJEMPLO
        if self.directo is not None:return self.directo_rotulo+' en directo'
        return (self.imagen_nombre or self.imagen_rotulo_libre or
                (Path(self.cfg.cuadro.imagen).name if self.cfg.cuadro.imagen else EJEMPLO))

    def imagen_en_uso(self):
        """Nombre en la galería, None si es el cuadro de ejemplo o False si la imagen vino de fuera."""
        if self.directo is not None or self.imagen_rotulo_libre:return False
        return self.imagen_nombre if (self.imagen_nombre or not self.cfg.cuadro.imagen) else False

    # ---- vídeo en directo como imagen del cuadro
    def usar_directo(self,fuente,rotulo):
        """El cuadro pasa a ser el vídeo en directo de `fuente` (una cámara o un archivo). Consigna del operador.

        La cámara es un sensor real. La imagen que recibe la IA, y sobre la que se señala, es la del
        instante de cada pregunta; mientras se explica, el cuadro muestra esa imagen detenida. La
        geometría del cuadro no cambia: el fotograma se adapta a su proporción como cualquier foto.
        """
        if self.closed:raise RuntimeError('la sesión está cerrada')
        if fuente is None or fuente.error:raise ValueError(fuente.error if fuente is not None else 'no hay vídeo')
        self.interrumpir()
        with self.lock:
            vieja,self.directo=self.directo,fuente;self.directo_rotulo=rotulo
            self.imagen_nombre=None;self.imagen_rotulo_libre=None;self.cfg.cuadro.imagen=''
            if self.vision is not None:self.vision.historia.clear()
        if vieja is not None and vieja is not fuente:vieja.cerrar(esperar=False)
        self._congelar_directo()
        self.notificar(rotulo+' en directo. Cada pregunta usa la imagen de ese momento; mientras se explica, el cuadro la muestra detenida.')

    def _congelar_directo(self,fuente=None):
        """La imagen de la sesión pasa a ser el fotograma actual del directo, adaptado al cuadro."""
        fuente=fuente or self.directo
        if fuente is None:return
        _,fotograma=fuente.fotograma()
        if fotograma is None:return
        from .galeria import adaptar
        self.imagen=adaptar(fotograma,self.proporcion)[0]

    def soltar_directo(self):
        """Deja el directo y devuelve su fuente sin cerrarla. El cuadro se queda con la última imagen."""
        with self.lock:fuente,self.directo=self.directo,None
        if fuente is None:return None
        self._congelar_directo(fuente);self.imagen_rotulo_libre='Última imagen del directo'
        return fuente

    def imagen_pantalla(self):
        """(clave, imagen BGR) de lo que debe verse en el cuadro ahora. Solo para dibujar.

        Con directo y sin nadie hablando, el último fotograma; si no, la imagen cargada (la foto, o el
        fotograma que se está explicando). La clave cambia cuando cambia la imagen.
        """
        fuente=self.directo
        if fuente is not None and not self.en_turno and not fuente.error:
            numero,fotograma=fuente.fotograma()
            if fotograma is not None:
                clave=(id(fuente),numero);cache=self._directo_cache
                if cache[0]!=clave:
                    from .galeria import adaptar
                    cache=self._directo_cache=(clave,adaptar(fotograma,self.proporcion,ancho=1024)[0])
                return cache
        imagen=self.imagen
        return id(imagen),imagen

    def nivel_voz(self):
        """Volumen (0–1) de la voz que suena ahora, o None si no habla. Solo anima la cara."""
        from .interfaz.cara import nivel_de_voz
        return nivel_de_voz(self.audio_actual)

    def expresion_cara(self):
        """(estado, mirada) de la cara del robot, para que la de la Pantalla 3D haga lo mismo. None si no hay cara."""
        c=self.cara
        return (c.estado,dict(c.mirada)) if c else None

    # ---- pantalla de exhibición
    def _poses_para_dibujar(self):
        """Articulaciones según los encoders, para la pantalla. Un brazo que no se puede leer va como None."""
        poses={}
        for n,b in self.brazos.items():
            try:poses[n]=b.leer_articulaciones()
            except Exception:poses[n]=None
        return poses

    def abrir_pantalla(self):
        """Ventana aparte para enseñar: la escena de MuJoCo con los brazos según sus encoders, el
        cuadro con la imagen cargada o el vídeo en directo, y la cara en una esquina. Es una vista:
        nada la lee para decidir, y cerrarla no detiene ni suelta nada."""
        if self.closed or self.vista_aparte is not None:return False
        from .hardware.pantalla import PantallaAparte
        self.vista_aparte=PantallaAparte(self.cfg,list(self.brazos),self._poses_para_dibujar,self.imagen_pantalla,self.nivel_voz,
                                         exhibicion=self.exhibicion,expresion=self.expresion_cara)
        return True

    def cerrar_pantalla(self):
        vista,self.vista_aparte=self.vista_aparte,None
        if vista is not None:vista.cerrar()

    def cambiar_imagen(self,imagen,nombre=None):
        """Sustituye la imagen de la obra con la sesión abierta. Es una consigna del operador.

        No mueve los brazos ni cambia la geometría: la imagen debe traer ya la proporción del
        cuadro (`galeria.adaptar`), de modo que cada punto [y, x] sigue en el mismo sitio del
        plano. Corta la explicación en curso, que hablaba de la imagen anterior, y vacía el
        contexto de la IA. Las vistas 3D son solo dibujo: si no se actualizan, se avisa y se sigue.
        """
        from .galeria import perdida
        if self.closed:raise RuntimeError('la sesión está cerrada')
        if imagen is None or imagen.ndim!=3 or imagen.shape[2]!=3 or perdida(imagen,self.proporcion)>.01:
            raise ValueError('la imagen no tiene la proporción del cuadro')
        self.interrumpir()
        anterior=self.soltar_directo()                      # una foto fija sustituye al directo y suelta la cámara
        if anterior is not None:anterior.cerrar(esperar=False)
        with self.lock:
            self.imagen=imagen;self.imagen_nombre=nombre;self.imagen_rotulo_libre=None
            self.cfg.cuadro.imagen=str(self.galeria.carpeta/nombre) if nombre else ''
            if self.vision is not None:self.vision.historia.clear()
        for vista in (self.mundo,getattr(self,'vista_panel',None)):
            cambiar=getattr(vista,'cambiar_imagen',None)
            if cambiar is None:continue
            try:cambiar(imagen)
            except Exception as e:self.notificar('La vista 3D conserva la imagen anterior: '+str(e))
        self.notificar('Imagen cargada: '+self.rotulo_imagen()+'. La conversación empieza de nuevo con ella.')

    def plan_gesto(self,b,desde=None):
        """Gesto de un bloque. `desde` es la postura de partida prevista; sin ella, la medida ahora."""
        measured=desde if desde is not None else self.inicio_plan()
        if b['tipo']=='senalar':g=senalar_plano(self.motor,b['punto'],b['brazo'],measured)
        elif b['tipo']=='region':g=barrer_region(self.motor,b['region'],b['brazo'],measured)
        else:
            name={'paisaje':'paisaje','cielo':'cielo','camino':'camino'}[b['tipo']]
            g=next(g for n,g,_ in ejemplos(self.motor) if n==name)
            # Las demos definen un marco local por brazo. Transformar explícitamente si cambia la mano.
            if b['brazo']!=g.brazo:
                old,new=self.motor.marcos[g.brazo],self.motor.marcos[b['brazo']]
                g=replace(g,brazo=b['brazo'],puntos_mm=tuple(map(tuple,new.a_mundo(old.a_base(g.puntos_mm)))),
                          ejes=tuple(map(tuple,new.dir_a_mundo(old.dir_a_base(g.ejes)))))
        if b['tipo'] in ('paisaje','cielo'):g=ensanchar_abanico(self.motor,g)
        choices=self.motivos.get(self.dataset,[])
        if choices:g=adaptar(choices[0],g)
        return replace(g,ancla=b.get('ancla',0))

    def bloqueo(self):
        """Motivo por el que no se puede mover ahora, o None. No consulta a la IA ni mueve nada."""
        if self.real and self.liberado:return 'Brazo sin par. Vuelve a Preparar y arrancar para moverlo.'
        if self.control.error:
            return ('Control detenido, no se consulta a la IA: '+self.control.error+
                    '. Pulsa Volver a punto cero para recuperarlos, o sujétalos, pulsa Soltar y vuelve a Preparar.')
        return None

    def fijar_idioma(self,idioma):
        """Cambia el idioma de la conversación. Devuelve True si ha cambiado. Es una consigna: no mueve nada."""
        if idioma not in IDIOMAS or idioma==self.idioma:return False
        self.idioma=idioma
        self.notificar('Idioma de la conversación: '+IDIOMAS[idioma].nombre+'.')
        return True

    def enviar(self,texto,bloques=None,idioma=None,seleccion=None):
        """Lanza un turno. El idioma de la conversación se decide aquí, una vez y en local.

        `idioma` lo da quien ya lo sabe (el reconocimiento de voz); si no, se deduce del texto
        escrito. Un texto del que no se puede asegurar el idioma no lo cambia. El turno se lleva
        ese idioma consigo: instrucciones a la IA, comprobación de su respuesta, anclas y voz usan
        el mismo, aunque la conversación cambie mientras tanto.
        """
        motivo=self.bloqueo()
        if motivo:self.notificar(motivo);return
        self.fijar_idioma(idioma or (detectar(texto) if texto else None))
        self.interrumpir()
        with self.lock:
            self.cancel=threading.Event();cancel=self.cancel;ticket=self.ticket
        # `seleccion`: {'region': [[y0,x0],[y1,x1]]} o {'punto': [y,x]} que el operador ha marcado en la imagen. Es una consigna.
        args=(texto,bloques,cancel,ticket,self.idioma)+((seleccion,) if seleccion else ())
        threading.Thread(target=self._turno,args=args,daemon=True).start()

    PAUSA_FRASES=.18      # silencio entre una frase y la siguiente
    MARGEN_GESTO=.35      # del instante en que se termina de calcular un gesto a su primer movimiento
    MARGEN_ACENTO=.7      # lo mismo para los acentos, que se calculan varios seguidos
    RETRASO_MAX=2.5       # hasta este retraso respecto a su palabra un gesto se hace siempre; con más, solo si llega antes de acabar su frase
    SEPARACION_MAX=1.5    # entre los ápices de los dos conceptos de una frase: con más, el plan de los dos brazos se alarga demasiado

    def preparar_calculo(self):
        """Arranca, si hace falta, el proceso que calcula los gestos mientras los brazos se mueven."""
        if self.por_frases and self.calculo is None and not self.closed:self.calculo=calculo_aparte.Calculador()

    def _calcular(self,funcion,*args):
        """Un cálculo de gestos, fuera del programa si se puede: así no le quita el turno a quien atiende los brazos."""
        return self.calculo(funcion,*args) if self.calculo is not None else funcion(*args)

    def _acompanado(self,funcion,args,comprobar,si_no):
        """Plan con el brazo libre acompañando, a amplitud entera o media según quepa en el brazo real; `si_no` si no cabe."""
        for escala in (1.,.5):
            candidato=self._calcular(funcion,self.motor,*args,escala)
            if comprobar is None:return candidato
            try:comprobar(candidato);return candidato
            except ValueError:continue
        return si_no

    def _movimiento(self,b,inicio,calcular=None,con_otro=True):
        """Plan de un bloque de tipo «gesto»: un movimiento de la biblioteca y, si lo pide, otro a la vez en el otro brazo."""
        biblioteca=expresion.disponibles()
        principal=biblioteca[b['movimiento']]['movimiento']
        otro=biblioteca[b['otro']]['movimiento'] if con_otro and b.get('otro') in biblioteca else None
        hacer=calcular or (lambda funcion,*args:funcion(*args))
        return hacer(calculo_aparte.movimiento,self.motor,b['brazo'],principal,otro,inicio)

    def _segundo(self,b,inicio,comprobar=None):
        """Plan del segundo movimiento de un bloque, el del otro brazo, o None si no lo lleva o no cabe.

        Se calcula aparte del principal para poder poner después cada uno en su palabra.
        """
        biblioteca=expresion.disponibles()
        companero=next((n for n in self.brazos if n!=b['brazo']),None)
        if companero is None or b.get('otro') not in biblioteca or expresion.de_dos_brazos(biblioteca[b['otro']]):return None,None
        if b['tipo']=='gesto' and expresion.de_dos_brazos(biblioteca[b['movimiento']]):return None,None
        if b['tipo'] in ('paisaje','cielo'):return None,None
        try:
            plan=self._calcular(calculo_aparte.movimiento,self.motor,companero,biblioteca[b['otro']]['movimiento'],None,inicio)
            if comprobar:comprobar(plan)
            return plan,companero
        except Exception:return None,None

    @staticmethod
    def rotulo_movimiento(b):
        """Para el registro de la sesión: qué movimientos de la biblioteca lleva un bloque. Vacío si no lleva ninguno."""
        biblioteca=expresion.disponibles()
        if b.get('tipo')=='gesto':texto=f" · {b['movimiento']} {biblioteca[b['movimiento']]['nombre']} ({b['brazo']})"
        elif b.get('otro') in biblioteca:texto=f" · {b['tipo']} ({b['brazo']})"
        else:return ''
        if b.get('otro') in biblioteca:texto+=f" + {b['otro']} {biblioteca[b['otro']]['nombre']}"
        return texto

    def _cara_del_turno(self,texto):
        """La cara, avisada de que empieza un turno y con la imagen que se va a explicar. Falsa si no hay cara."""
        c=self.cara
        if c:
            imagen=getattr(self,'imagen',None)
            if imagen is not self._imagen_cara:c.imagen_nueva(imagen);self._imagen_cara=imagen
            c.pensando(texto)
        return c

    def _turno(self,texto,bloques,cancel,ticket,idioma=None,seleccion=None):
        if self.por_frases:self._turno_por_frases(texto,bloques,cancel,ticket,idioma,seleccion)
        else:self._turno_entero(texto,bloques,cancel,ticket,idioma,seleccion)
        self._a_punto_cero_tras_la_respuesta(cancel,ticket)

    def _a_punto_cero_tras_la_respuesta(self,cancel,ticket):
        """La postura final de cada respuesta es punto cero: los brazos reales se pliegan, despacio, al acabar.

        Dentro de la respuesta cada movimiento sale de la postura de trabajo y vuelve a ella; plegar en cada
        gesto añadiría varios segundos a cada uno. La petición siguiente los despliega mientras la IA piensa, y
        si llega antes de que acaben de plegarse, lo interrumpe y despliega desde donde estén. Es el mismo
        recorrido validado del botón «Volver a punto cero», a la misma velocidad reducida.
        """
        if not (self.plegar_al_acabar and self.real and self.plegado is not None) or self.liberado:return
        try:
            while self.control.frenada is not None:
                if cancel.wait(.02):return
            with self.lock:                                  # con el cerrojo: una petición nueva no planifica a medias con el perfil lento
                if ticket!=self.ticket or cancel.is_set() or self.control.error:return
                self.desplegado=False
                aplicar_perfil(self.cfg,min(self.velocidad or 20.,VELOCIDAD_RETORNO))
                try:fin=self._mover_a(self.plegado,'Volviendo a punto cero')
                finally:aplicar_perfil(self.cfg,self.velocidad or 20.)
            while time.perf_counter()<fin+.3:
                if self.control.error or cancel.wait(.02):return
            self.notificar('Brazos en punto cero.')
        except Exception as e:
            self.notificar('No se pudo volver a punto cero: '+str(e))

    def _turno_por_frases(self,texto,bloques,cancel,ticket,idioma=None,seleccion=None):
        """Turno frase a frase: empieza a hablar con la primera frase mientras se preparan las demás.

        Antes no sonaba nada hasta tener la respuesta entera, toda la voz y todos los gestos (unos 9 s).
        Aquí la IA entrega cada frase en cuanto la escribe, la voz llega por trozos y suena con el primero,
        y cada gesto se compila mientras suena su propia frase o la anterior. No hay silencio inicial: si
        un gesto no llega a tiempo a su palabra (pasa sobre todo en la primera frase), llega algo después;
        si llegaría muy tarde, se omite.

        Todo va sobre un único reloj, el del altavoz, igual que antes. Cada gesto y cada acento acaba en
        reposo y el siguiente parte de él; antes de ejecutar un plan se comprueba con los encoders que el
        brazo está donde el plan empieza. La predicción es causal: consignas planificadas, nunca física.
        """
        from .sincronia.reproductor import Reproductor
        player=None;idioma=idioma or self.idioma;c=None
        # cola: (inicio, plan, es_acento) por orden; ocupado: hasta cuándo dura lo ya entregado al control; fin_gestos: fin del último gesto en cola.
        marcha={'cola':[],'ocupado':0.,'fin_gestos':0.,'fin_audio':0.,'acentos':0,'omitidos':0,'frases':0,'error':None,'hecho':False,'despliegue':0.,
                't0':time.perf_counter(),'primera':None,'retrasos':[]}
        with self.lock:self.en_turno+=1
        try:
            if self.directo is not None:self._congelar_directo()
            c=self._cara_del_turno(texto)
            while self.control.frenada is not None:
                if cancel.wait(.02):return
            marcha['despliegue']=self.desplegar()       # la primera vez los brazos se despliegan mientras tanto
            if bloques is None:
                self.notificar('Interpretando el cuadro…')
                if self.vision is None:self.vision=Vision(self.keys,self.modelo)
                contexto=('Usamos una imagen virtual como consigna, sin cámara del entorno. Describe solo esa imagen. ' if self.real else '')
                # Si el operador ha marcado algo en la imagen, la IA lo ve dibujado y la petición se lo dice.
                imagen_ia=self.jpeg(seleccion) if seleccion else self.jpeg()
                fuente=self.vision.por_bloques(contexto+texto+self.nota_seleccion(seleccion),imagen_ia,self.estado(),idioma)
            else:fuente=iter(bloques)
            if cancel.is_set():return
            marcha['reposo']=({n:pose_reposo(self.motor,n) for n in self.brazos} if marcha['despliegue'] else self.inicio_plan())
            # El altavoz arranca ya, vacío: el primer trozo de voz sonará en cuanto llegue, sin esperar a nada más.
            player=Reproductor(np.zeros(0,np.int16),previo_s=.12,abierto=True)
            with self.lock:
                if ticket!=self.ticket or cancel.is_set():return
                self.audio_actual=player
            player.iniciar()
            def producir():
                try:
                    for b in fuente:
                        if cancel.is_set():return
                        if self.real and len(self.brazos)==1:b={**b,'brazo':'izq'}
                        self._frase(b,idioma,player,marcha,cancel)
                except Exception as e:marcha['error']=e
                finally:
                    marcha['hecho']=True;player.cerrar_entrada()
            threading.Thread(target=producir,daemon=True,name='frases').start()
            while True:
                if marcha['error'] is not None:raise marcha['error']
                if marcha['despliegue'] and time.perf_counter()>=marcha['despliegue']+.3:
                    self.desplegado=True;marcha['despliegue']=0.
                position=player.posicion()
                with self.lock:
                    if ticket!=self.ticket or cancel.is_set():return
                    cola=marcha['cola']
                    while cola and position>=cola[0][0]:
                        start,plan,_=cola.pop(0)
                        # Si el estado medido difiere de la predicción, no ejecutar el plan desfasado.
                        measured=self.control.medir()
                        mismatch=max(np.max(abs(measured[n][:5]-plan.q[n][0,:5])) for n in measured)
                        if mismatch<=5:
                            self.control.programar(plan,start,reloj=player.posicion)
                            marcha['ocupado']=max(marcha['ocupado'],start+float(plan.tiempos[-1]))
                        else:self.notificar('Gesto omitido: inicio medido distinto de la predicción')
                    fin=marcha['hecho'] and not cola and position>=max(marcha['fin_audio']+.15,marcha['ocupado'])
                if fin:break
                if player.terminado.is_set() and not marcha['hecho']:
                    raise RuntimeError('el dispositivo de audio interrumpió la reproducción')
                if self.control.error:raise RuntimeError(self.control.error)
                if cancel.wait(.01):return
            if self._seguimiento is not None:
                try:self._seguimiento.flush()
                except (OSError,ValueError):pass
            if marcha['omitidos']:
                self.notificar(f"{marcha['omitidos']} gesto(s) omitido(s): a {self.cfg.limites.velocidad[0]:.0f}°/s habrían llegado con su frase ya terminada.")
            if marcha['frases']:
                self.notificar(f"Acompañamiento continuo: {marcha['acentos']} acentos entre gestos.")
                self.notificar(f"Conceptos gráficos: {marcha.get('graficos',0)} de {marcha['frases']} frases.")
            if marcha['primera'] is not None:
                tarde=[r for r in marcha['retrasos'] if r>.15]
                self.notificar(f"Primera palabra a los {marcha['primera']:.1f} s"+
                               (f"; {len(tarde)} gesto(s) algo después de su palabra (hasta {max(tarde):.1f} s)." if tarde else '.'))
            self.notificar('Listo. Puedes preguntar, señalar o marcar una región.')
        except Exception as e:
            if not cancel.is_set():self.control.parar();self.notificar('Error: '+str(e))
            if c and not cancel.is_set():c.error(str(e))
        finally:
            if c and ticket==self.ticket:c.callar()            # un turno antiguo no calla al nuevo
            with self.lock:self.en_turno-=1
            self._informar_carga()
            if player is not None:
                player.cerrar()
                with self.lock:
                    if self.audio_actual is player:self.audio_actual=None

    def _frase(self,b,idioma,player,marcha,cancel):
        """Prepara una frase: su voz, que suena desde el primer trozo, su gesto y los acentos que lo rodean.

        El gesto se coloca en cuanto la voz ha dado el instante de su palabra, sin esperar al resto de la
        frase, y puede empezar antes de que suene su frase, sobre el final de la anterior: a 110°/s solo
        llegar al ápice lleva unos 2 s. Los acentos que aún no han empezado le ceden el sitio. Al tener
        la frase entera se añaden acentos en los ratos que quedan libres. Cada plan empieza y acaba en reposo.
        """
        texto=b['texto'];voz={'inicio':None,'marcas':()}
        c=self.cara;clave=(id(marcha),marcha.get('numero',0));marcha['numero']=clave[1]+1
        def al_trozo(muestras,marcas=None):
            t=player.anadir(muestras,self.PAUSA_FRASES if voz['inicio'] is None and marcha['frases'] else 0.)
            if marcas is not None:voz['marcas']=marcas
            if voz['inicio'] is None:
                voz['inicio']=t
                # La cara saca la frase cuando empiece a sonar, con la voz que haya; el resto llega después.
                if c:c.frase(clave,texto,list(marcas or ()),np.array(muestras),player.posicion,t,[b],duracion=len(texto)*.062)
                if marcha['primera'] is None:                # cuánto se ha tardado en empezar a hablar, para el registro
                    try:falta=max(0.,t-player.posicion())
                    except RuntimeError:falta=0.
                    marcha['primera']=time.perf_counter()-marcha['t0']+falta
        sintesis=self.pool.submit(self.voz.sintetizar,texto,idioma,al_trozo)
        comprobar=None
        if self.real:
            def comprobar(p):
                for n,arm in self.brazos.items():arm.validar_plan(p,n)
        def posicion():
            try:return player.posicion()
            except RuntimeError:return 0.
        def suelo(ini,margen):
            """Lo más pronto que puede empezar un plan nuevo, en el reloj de esta frase: ni antes de ahora ni sobre lo que se está ejecutando."""
            ahora=posicion();desde=max(marcha['ocupado']-ini,ahora+margen-ini)
            despliegue=marcha['despliegue']
            if despliegue:desde=max(desde,ahora+despliegue+.35-time.perf_counter()-ini)
            return desde
        solo=None                                           # el gesto se compila mientras llega la voz
        if b['tipo']=='sin_gesto':
            self.notificar('La IA devolvió texto sin coordenadas utilizables: esta frase se narra sin gesto.')
        else:
            try:
                if b['tipo']=='gesto':solo=self._movimiento(b,marcha['reposo'],self._calcular,con_otro=False)
                else:
                    g=self.plan_gesto(b,marcha['reposo'])
                    g=replace(g,preparacion_s=.8,duracion_s=.3 if b['tipo']=='senalar' else 1.8,mantener_s=.2)
                    solo=self._calcular(calculo_aparte.gesto,self.motor,g,marcha['reposo'],len(self.brazos)==2 and b['tipo'] in ('paisaje','cielo'))
                if comprobar:comprobar(solo)
            except Exception as e:
                self.notificar('Gesto omitido: '+str(e));solo=None
        segundo,companero=self._segundo(b,marcha['reposo'],comprobar) if solo is not None else (None,None)
        if solo is not None:
            palabra=b.get('ancla',0)
            try:letra=unidades(texto,idioma)[palabra]
            except IndexError:letra=0
            while not sintesis.done():                      # hasta que la voz haya pasado por la palabra del gesto
                marcas=voz['marcas']
                if voz['inicio'] is not None and len(marcas) and marcas[-1][0]>letra:break
                if cancel.wait(.02):return
            if sintesis.done():audio,marcas,_=sintesis.result();dur=len(audio)/24000
            else:marcas=list(voz['marcas']);dur=0.
            if cancel.is_set() or voz['inicio'] is None:return
            ini=voz['inicio']
            try:ancla=tiempo_ancla(texto,palabra,marcas,dur,idioma)
            except ValueError:ancla=dur/2
            apex=solo.inicio_trazo if b['tipo']=='senalar' else (solo.inicio_trazo+solo.fin_trazo)/2
            unico,apex_unico=solo,apex                       # el principal solo, por si con los dos brazos no llega a tiempo
            # Cuándo acaba la frase: lo que dure la voz o, si aún está llegando, lo que apunta su ritmo.
            if dur:fin_frase=dur
            elif len(marcas) and marcas[-1][0]>0:fin_frase=marcas[-1][1]*len(texto)/marcas[-1][0]
            else:fin_frase=len(texto.split())/2.25
            if segundo is not None:
                # El otro brazo lleva su propio concepto, con el ápice en su palabra. Si la voz aún no ha llegado
                # a ella, su instante se estima por el ritmo que lleva la frase.
                delta=0.
                if 'ancla_otro' in b:
                    try:
                        letra2=unidades(texto,idioma)[b['ancla_otro']]
                        if dur or (len(marcas) and marcas[-1][0]>=letra2):t2=tiempo_ancla(texto,b['ancla_otro'],marcas,dur,idioma)
                        else:t2=marcas[-1][1]*letra2/max(marcas[-1][0],1)
                        delta=float(np.clip(t2-ancla,-self.SEPARACION_MAX,self.SEPARACION_MAX))
                    except (IndexError,ValueError):delta=0.
                try:
                    junto=self._calcular(calculo_aparte.fundido,self.motor,solo,segundo,b['brazo'],companero,apex,expresion.apice(segundo),delta)
                    if float(np.ptp(junto.q[companero],axis=0).max())>1e-6:      # caben los dos juntos
                        if comprobar:comprobar(junto)
                        apex+=float(junto.inicio_trazo)-float(solo.inicio_trazo);solo=junto
                except Exception:pass
            adelanto=float(self.cfg.voz.get('adelanto_expresivo_s',.22))
            start=ancla-apex-adelanto
            # Hueco corto antes del gesto: mejor una preparación más lenta, con el mismo ápice, que esperar quieto.
            lento=None
            with self.lock:previsto=max(suelo(ini,self.MARGEN_GESTO+.3),marcha['fin_gestos']-ini)
            if 0<start-previsto<1.8:
                try:
                    lento=self._calcular(calculo_aparte.alargado,self.motor,solo,start-previsto)
                    if comprobar:comprobar(lento)
                except Exception:lento=None
            puesto=None
            with self.lock:
                antes=max(suelo(ini,self.MARGEN_GESTO),marcha['fin_gestos']-ini);retraso=antes-start
                def tarde(retraso,apice):
                    # Un gesto con retraso sigue valiendo mientras su ápice caiga dentro de la frase que ilustra.
                    return retraso>self.RETRASO_MAX and antes+apice>fin_frase-.3
                if tarde(retraso,apex) and solo is not unico:
                    # Los dos conceptos juntos no llegan: se intenta con el principal solo, que es más corto.
                    solo,apex,lento=unico,apex_unico,None
                    start=ancla-apex-adelanto;retraso=antes-start
                if tarde(retraso,apex):marcha['omitidos']+=1
                else:
                    if lento is not None and previsto>=antes:inicio,puesto=previsto,lento
                    else:inicio,puesto=max(start,antes),solo
                    cola=marcha['cola']                      # los acentos que coincidirían con el gesto le ceden el sitio
                    fuera=[x for x in cola if x[2] and x[0]+float(x[1].tiempos[-1])>ini+inicio+1e-6]
                    for x in fuera:cola.remove(x)
                    marcha['acentos']-=len(fuera)
                    cola.append((ini+inicio,puesto,False));cola.sort(key=lambda x:x[0])
                    marcha['fin_gestos']=ini+inicio+float(puesto.tiempos[-1]);marcha['retrasos'].append(max(0.,retraso))
                    marcha['reposo']={n:q[-1].copy() for n,q in puesto.q.items()}   # de ahí parte el gesto siguiente
                    if c:                                    # la cara mira hacia el gesto y toma su ánimo mientras dura
                        from .cara.expresiones import de_bloque
                        vuelta=puesto.inicio_retorno if puesto.inicio_retorno is not None else puesto.tiempos[-1]
                        c.gesto(player.posicion,ini+inicio,ini+inicio+float(vuelta),**de_bloque(b,getattr(c,'espejo',False)))
            if puesto is not None:
                # El brazo libre acompaña al gesto. Se calcula con el gesto ya en la cola, para no retrasarlo,
                # y lo sustituye si aún no ha empezado: dura lo mismo y empieza y acaba en las mismas posturas.
                try:completo=self._acompanado(calculo_aparte.acompanado,(puesto,),comprobar,None)
                except Exception:completo=None
                if completo is not None:
                    with self.lock:
                        for i,x in enumerate(marcha['cola']):
                            if x[1] is puesto:marcha['cola'][i]=(x[0],completo,False);break
        audio,marcas,kind=sintesis.result()
        aviso_voz,self.voz.aviso=getattr(self.voz,'aviso',None),None
        if aviso_voz:self.notificar(aviso_voz)
        if cancel.is_set() or voz['inicio'] is None:return
        self.notificar(texto+' ['+self.dataset+'; '+kind+']'+self.rotulo_movimiento(b))
        if c:c.frase(clave,texto,marcas,audio,player.posicion,voz['inicio'],[b])        # ahora con toda la voz y sus tiempos
        ini=voz['inicio'];dur=len(audio)/24000
        # Acentos en los ratos de esta frase en que los brazos no tienen nada: no esperan quietos mientras se habla.
        with self.lock:
            a=max(0.,suelo(ini,self.MARGEN_ACENTO));ventanas=[]
            for s,p,_ in marcha['cola']:
                if s-ini-a>=1.8:ventanas.append((a,min(s-ini,dur)))
                a=max(a,s-ini+float(p.tiempos[-1]))
            if dur-a>=1.8:ventanas.append((a,dur))
        pulsos=[]
        for a,z in ventanas:
            if z-a<1.8:continue
            try:nuevos=self._calcular(calculo_aparte.acentos,self.motor,audio[int(a*24000):int(z*24000)],z-a,marcha['acentos']+len(pulsos))
            except Exception:continue
            for s,p in nuevos:
                if comprobar:                               # nada que el brazo no pueda hacer llega a la cola
                    try:comprobar(p)
                    except Exception:continue
                pulsos.append((ini+a+s,p,True))
        with self.lock:
            ahora=posicion();pulsos=[x for x in pulsos if x[0]>=ahora+.03]     # lo que ya llegaría tarde no se ejecuta
            marcha['cola'].extend(pulsos);marcha['cola'].sort(key=lambda x:x[0]);marcha['acentos']+=len(pulsos)
            marcha['fin_audio']=max(marcha['fin_audio'],ini+dur);marcha['frases']+=1
            marcha['graficos']=marcha.get('graficos',0)+expresion.bloque_grafico(b)

    def _turno_entero(self,texto,bloques,cancel,ticket,idioma=None,seleccion=None):
        """El turno de siempre: no suena nada hasta tener la respuesta entera, toda la voz y todos los gestos."""
        player=None;idioma=idioma or self.idioma;c=None
        with self.lock:self.en_turno+=1
        try:
            if self.directo is not None:self._congelar_directo()
            c=self._cara_del_turno(texto)
            while self.control.frenada is not None:
                if cancel.wait(.02):return
            # Los brazos se despliegan mientras la IA y la voz trabajan: no añade espera.
            fin_despliegue=self.desplegar()
            if bloques is None:
                self.notificar('Interpretando el cuadro…')
                if self.vision is None:self.vision=Vision(self.keys,self.modelo)
                contexto=('Usamos una imagen virtual como consigna, sin cámara del entorno. Describe solo esa imagen. ' if self.real else '')
                imagen_ia=self.jpeg(seleccion) if seleccion else self.jpeg()
                bloques=self.vision.responder(contexto+texto+self.nota_seleccion(seleccion),imagen_ia,self.estado(),idioma)
            if cancel.is_set():return
            if self.real and len(self.brazos)==1:bloques=[{**b,'brazo':'izq'} for b in bloques]
            # Un único audio continuo por turno elimina huecos de síntesis entre frases.
            # La red y la compilación terminan antes de comprometer su reproducción.
            texto_completo=' '.join(b['texto'] for b in bloques)
            # La voz se sintetiza mientras se compilan los gestos: compilar no depende del audio, solo
            # su colocación en el tiempo. La espera es la mayor de las dos, no la suma.
            sintesis=self.pool.submit(self.voz.sintetizar,texto_completo,idioma)
            while self.control.frenada is not None:
                if cancel.wait(.02):return
            compiled=[]; word_offset=0; available=-100.; lead=0.
            # Predicción causal desde encoders iniciales + consignas planificadas.
            # No es una lectura de encoders futuros ni utiliza la física del simulador.
            # Durante el despliegue se parte de su destino, ya validado; antes de ejecutar cada plan
            # se comprueba con encoders que el brazo está de verdad ahí.
            predicted=({n:pose_reposo(self.motor,n) for n in self.brazos} if fin_despliegue else self.inicio_plan())
            for b in bloques:
                if cancel.is_set():return
                anchor=word_offset+b.get('ancla',0)
                word_offset+=len(unidades(b['texto'],idioma))   # palabras, o caracteres en chino
                if b['tipo']=='sin_gesto':
                    self.notificar('La IA devolvió texto sin coordenadas utilizables: este bloque se narra sin mover los brazos.');continue
                try:
                    if b['tipo']=='gesto':plan=self._movimiento(b,predicted)
                    else:
                        g=self.plan_gesto(b)
                        g=replace(g,preparacion_s=.8,duracion_s=.3 if b['tipo']=='senalar' else 1.8,mantener_s=.2)
                        plan=compilar_actuacion(self.motor,g,predicted,bilateral=len(self.brazos)==2 and b['tipo'] in ('paisaje','cielo'))
                        if b['tipo'] in ('senalar','region','camino') and b.get('otro') in expresion.disponibles() and len(self.brazos)==2:
                            # Mientras este brazo señala o recorre, el otro dibuja un movimiento de la biblioteca.
                            plan=expresion.con_otro(self.motor,plan,b['brazo'],expresion.disponibles()[b['otro']]['movimiento'],predicted,
                                                    plan.inicio_trazo if b['tipo']=='senalar' else (plan.inicio_trazo+plan.fin_trazo)/2)
                    if self.real:
                        for n,arm in self.brazos.items():arm.validar_plan(plan,n)
                    apex=plan.inicio_trazo if b['tipo']=='senalar' else (plan.inicio_trazo+plan.fin_trazo)/2
                    compiled.append((anchor,apex,plan))
                    predicted={n:q[-1].copy() for n,q in plan.q.items()}
                except Exception as e:
                    self.notificar('Gesto omitido: '+str(e))
            audio,marks,kind=sintesis.result()
            aviso_voz,self.voz.aviso=getattr(self.voz,'aviso',None),None
            if aviso_voz:self.notificar(aviso_voz)
            if cancel.is_set():return
            while fin_despliegue and time.perf_counter()<fin_despliegue+.3:
                if self.control.error:raise RuntimeError(self.control.error)
                if cancel.wait(.02):return
            if fin_despliegue:self.desplegado=True
            duration=len(audio)/24000
            scheduled=[(tiempo_ancla(texto_completo,index,marks,duration,idioma),apex,plan) for index,apex,plan in compiled]
            if scheduled:
                from .sincronia.ritmo import factor_narracion,estirar
                scheduled,scale,sobran=encajar_en_la_voz(scheduled)
                if sobran:
                    self.notificar(f'{sobran} gesto(s) omitido(s): a {self.cfg.limites.velocidad[0]:.0f}°/s no da tiempo a hacerlos y volver a reposo sin frenar la voz.')
                if scale>1.001:
                    audio=estirar(audio,scale);duration=len(audio)/24000
                    self.notificar('La narración adapta su ritmo a la extensión y la vuelta a reposo.')
                anticipation=float(self.cfg.voz.get('adelanto_expresivo_s',.22))
                scheduled=[(anchor*scale-apex-anticipation,plan) for anchor,apex,plan in scheduled]
                from .control.acompanamiento import completar
                def cabe_en_el_brazo(plan):
                    for n,b in self.brazos.items():b.validar_plan(plan,n)
                scheduled,coverage=completar(self.motor,scheduled,audio,duration,comprobar=cabe_en_el_brazo if self.real else None)
                if self.real:
                    for _,plan in scheduled:
                        for n,b in self.brazos.items():b.validar_plan(plan,n)
                self.notificar(f'Acompañamiento continuo: {coverage["acentos"]} acentos entre gestos.')
                lead=max(0,-scheduled[0][0])
                available=scheduled[-1][0]+scheduled[-1][1].tiempos[-1]
            from .sincronia.reproductor import Reproductor
            player=Reproductor(audio,previo_s=lead+.12)
            with self.lock:
                if ticket!=self.ticket or cancel.is_set():return
                self.audio_actual=player
            player.iniciar()
            if c:c.hablar(texto_completo,marks,locals().get('scale',1.),audio,player.posicion,bloques)
            self.notificar(texto_completo+' ['+self.dataset+'; '+kind+']'+''.join(self.rotulo_movimiento(b) for b in bloques))
            next_plan=0
            end=max(duration+.15,available if scheduled else 0)
            while player.posicion()<end:
                position=player.posicion()
                with self.lock:
                    if ticket!=self.ticket or cancel.is_set():return
                    if next_plan<len(scheduled) and position>=scheduled[next_plan][0]:
                        start,plan=scheduled[next_plan]
                        # Si el estado medido difiere de la predicción, no ejecutar el plan desfasado.
                        measured=self.control.medir()
                        mismatch=max(np.max(abs(measured[n][:5]-plan.q[n][0,:5])) for n in measured)
                        if mismatch<=5:self.control.programar(plan,start,reloj=player.posicion)
                        else:self.notificar('Gesto omitido: inicio medido distinto de la predicción')
                        next_plan+=1
                if player.terminado.is_set() and player.cursor<len(player.track):
                    raise RuntimeError('el dispositivo de audio interrumpió la reproducción')
                if self.control.error:raise RuntimeError(self.control.error)
                if cancel.wait(.01):return
            if self._seguimiento is not None:
                try:self._seguimiento.flush()
                except (OSError,ValueError):pass
            self.notificar('Listo. Puedes preguntar, señalar o marcar una región.')
        except Exception as e:
            if not cancel.is_set():self.control.parar();self.notificar('Error: '+str(e))
            if c and not cancel.is_set():c.error(str(e))
        finally:
            if c and ticket==self.ticket:c.callar()            # un turno antiguo no calla al nuevo
            with self.lock:self.en_turno-=1
            self._informar_carga()
            if player is not None:
                player.cerrar()
                with self.lock:
                    if self.audio_actual is player:self.audio_actual=None

    def cerrar(self):
        if self.closed:return
        self.closed=True;self.interrumpir();self.control.cerrar();self.voz.cerrar();self._cerrar_seguimiento()
        if self.cara:self.cara.cerrar()
        if self.micro.stream:self.micro.terminar()
        self.pool.shutdown(wait=False,cancel_futures=True)
        if self.calculo is not None:self.calculo.cerrar()
        fuente,self.directo=self.directo,None
        if fuente is not None:fuente.cerrar(esperar=False)
        self.cerrar_pantalla()
        if self.exhibicion is not None:
            try:self.exhibicion.cerrar()
            except Exception:pass
            self.exhibicion=None
        if self.mundo:self.mundo.cerrar()
        if getattr(self,'vista_panel',None):self.vista_panel.cerrar();self.vista_panel=None
        for b in self.brazos.values():b.desconectar()

    def soltar_real(self):
        if not self.real or self.liberado:return
        self.interrumpir();self.control.cerrar();self._cerrar_seguimiento()
        errors=[]
        for b in self.brazos.values():
            try:b.soltar()
            except Exception as e:errors.append(b.port+': '+str(e))
        if errors:raise RuntimeError('; '.join(errors))
        self.liberado=True
        self.notificar('Brazos sin par. Ya puedes cerrar o preparar otra sesión.')

    def bailar(self,nombre):
        if not self.real or self.liberado:return
        if self.control.error:self.notificar(self.bloqueo());return
        self.interrumpir()
        with self.lock:self.cancel=threading.Event()   # corta también un plegado en curso
        try:
            from .hardware.alineacion import plan_real
            from .pruebas_modelo import gestos_para_inicio,muestra
            from .control.escenico import validar
            from .control.semantico import Trayectoria
            from types import SimpleNamespace
            measured=self.inicio_plan()
            plans={n:plan_real(nombre,measured[n],b.alineacion,b.native.coords,self.motor.modelo,gestos_para_inicio(nombre,measured[n]),velocidad=self.velocidad or 20.)
                   for n,b in self.brazos.items()}
            ends={n:p[-1][0]+p[-1][1] for n,p in plans.items()};end=max(ends.values())*1.05
            times=np.linspace(0,end,int(np.ceil(end*50))+1)
            poses={n:np.array([muestra(p,t/end*ends[n]) for t in times]) for n,p in plans.items()}
            validar(self.motor,times,poses)
            plan=Trayectoria(times,poses,0.,end,SimpleNamespace(tipo='prueba'),0.,0.)
            for n,b in self.brazos.items():b.validar_plan(plan,n)
            self.control.programar(plan)
            self.notificar(nombre+': '+', '.join(b.port for b in self.brazos.values())+f' · {end:.1f} s · regreso a la postura de inicio')
        except Exception as e:self.notificar('Baile bloqueado antes de mover: '+str(e))


def demo_bloques(idioma=POR_DEFECTO):
    """La demostración de cuatro frases sobre el cuadro de ejemplo, en el idioma de la conversación.
    Los gestos son los mismos en todos; cambia el texto y la palabra a la que se ancla cada uno."""
    gestos=({'tipo':'paisaje','brazo':'izq'},{'tipo':'cielo','brazo':'der'},
            {'tipo':'senalar','brazo':'der','punto':[200,780]},{'tipo':'region','brazo':'izq','region':[[380,180],[600,400]]})
    return [{'texto':texto,**gesto,'ancla':ancla_de(texto,palabra,idioma)} for (texto,palabra),gesto in zip(DEMO[idioma],gestos)]


# Lo que se pregunta a la IA cuando se marca algo en la imagen y se pulsa preguntar sin escribir nada.
PREGUNTA_SELECCION={
    'es':('Explícame con detalle lo que hay en la zona que he marcado.','Explícame con detalle lo que hay en el punto que he señalado.'),
    'en':('Explain in detail what is in the area I have marked.','Explain in detail what is at the point I have marked.'),
    'de':('Erkläre mir genau, was in dem markierten Bereich zu sehen ist.','Erkläre mir genau, was an dem markierten Punkt zu sehen ist.'),
    'fr':("Explique-moi en détail ce qu'il y a dans la zone que j'ai marquée.","Explique-moi en détail ce qu'il y a au point que j'ai marqué."),
    'zh':('请详细讲解我标出的这个区域里有什么。','请详细讲解我标出的这个位置有什么。'),
}


def pregunta_seleccion(idioma,seleccion):
    """La pregunta por defecto sobre lo marcado, en el idioma de la conversación."""
    region,punto=PREGUNTA_SELECCION.get(idioma,PREGUNTA_SELECCION[POR_DEFECTO])
    return region if seleccion.get('region') else punto


def demo_biblioteca():
    """Una conversación de ejemplo con movimientos de la biblioteca, sin pasar por la IA. En español."""
    # Cada frase lleva dos conceptos, uno por brazo y cada uno en su palabra; al menos uno de los dos es gráfico.
    frases=(('Hola, bienvenido al punto de información, donde le indicamos el camino paso a paso.','paso','E12','izq','Hola,','M20'),
            ('El ayuntamiento está muy cerca, a unos cinco minutos caminando desde aquí mismo.','cerca,','M25','der','caminando','E20'),
            ('Siga recto por esta calle hasta llegar al final, donde está la plaza mayor.','recto','E04','izq','final,','M07'),
            ('En la plaza gire a la derecha y cruce el puente que pasa sobre el río.','gire','E05','der','río.','E10'),
            ('Verá enseguida el ayuntamiento, un edificio muy alto con una torre en el centro.','alto','E08','izq','torre','E16'),
            ('Abre de nueve a dos y hoy no necesita cita previa para entrar.','nueve','M12','der','Abre','M15'))
    return [{'texto':texto,'tipo':'gesto','brazo':brazo,'movimiento':movimiento,'ancla':ancla_de(texto,palabra,POR_DEFECTO),
             'otro':otro,'ancla_otro':ancla_de(texto,palabra_otro,POR_DEFECTO)} for texto,palabra,movimiento,brazo,palabra_otro,otro in frases]


def iniciar(root,imagen=None,modelo='gemini-robotics-er-2-preview',voz='elevenlabs',demo=False,real=False,brazo_real=None,parent=None,recursos=None):
    import tkinter as tk
    from tkinter import ttk,filedialog
    import cv2
    from .interfaz.embebido import ventana
    ui=ventana(parent);ui.title('SO-101 · Cuadro, voz y gestos');ui.geometry('900x860')
    events=queue.Queue()
    session=SesionIntegrada(root,ventana=parent is None,voz=voz,modelo=modelo,imagen=imagen,real=real,notificar=events.put,brazo_real=brazo_real,recursos=recursos)
    if real:ui.title('SO-101 · CHATBOT REAL '+brazo_real.port+' · cuadro virtual sin cámara')
    from .interfaz.ventana_imagenes import VentanaImagenes,foto_tk
    from .galeria import EJEMPLO
    # El lienzo tiene la proporción del cuadro: la imagen se ve sin deformar y los clics caen donde se ve.
    pw=560 if parent is not None else 800;ph=round(pw*session.proporcion)
    images=ttk.Frame(ui);images.pack(pady=8)
    canvas=tk.Canvas(images,width=pw,height=ph);canvas.pack(side='left')
    obra_en_lienzo=canvas.create_image(0,0,anchor='nw')
    clave_obra=[None]
    def pintar_obra():
        """Pone en el lienzo lo que toca ver en el cuadro: la imagen cargada o el vídeo en directo."""
        clave,imagen=session.imagen_pantalla()
        if clave==clave_obra[0]:return False
        clave_obra[0]=clave
        session._photo=foto_tk(tk,cv2.resize(imagen,(pw,ph),interpolation=cv2.INTER_AREA))
        canvas.itemconfigure(obra_en_lienzo,image=session._photo)
        return imagen
    pintar_obra()
    live=None
    if parent is not None and real:
        try:
            if recursos:session.vista_panel=recursos.vista
            elif len(session.brazos)>1:
                from .hardware.vista_dual import VistaDual
                session.vista_panel=VistaDual(session.cfg,session.imagen)
            else:
                from .pruebas_modelo import Modelo
                session.vista_panel=Modelo()
            live=ttk.Label(images);live.pack(side='left',padx=10)
        except Exception as e:events.put('No se pudo abrir la vista 3D: '+str(e))
    # Imágenes: una ventana emergente para recorrer la carpeta, añadir fotos o tomar una instantánea de vídeo.
    barra=ttk.Frame(ui);barra.pack(fill='x',padx=20,pady=(0,8))
    rotulo=tk.StringVar(value='Imagen: '+session.rotulo_imagen())
    # Selección sobre la imagen: un punto o un recuadro que acompaña a la siguiente pregunta a la IA.
    seleccion=[None]
    def quitar_seleccion():
        seleccion[0]=None;canvas.delete('seleccion')
    emergente=[None]
    def usar_imagen(nombre,imagen):
        session.cambiar_imagen(imagen,nombre)
        try:session.galeria.elegir(nombre)
        except Exception as e:events.put('La elección no se guardó para la próxima sesión: '+str(e))
        quitar_seleccion()
        pintar_obra();rotulo.set('Imagen: '+session.rotulo_imagen())
    def usar_directo(fuente,nombre):
        session.usar_directo(fuente,nombre)
        quitar_seleccion()
        pintar_obra();rotulo.set('Imagen: '+session.rotulo_imagen())
    def abrir_imagenes():
        if emergente[0] is not None and not emergente[0].cerrada:emergente[0].traer_al_frente();return
        try:emergente[0]=VentanaImagenes(ui,session.galeria,session.proporcion,session.imagen_en_uso,usar_imagen,
                                         al_directo=usar_directo,tomar_directo=session.soltar_directo)
        except Exception as e:events.put('No se pudo abrir la ventana de imágenes: '+str(e))
    ttk.Button(barra,text='Imágenes…',command=abrir_imagenes).pack(side='left')
    ttk.Label(barra,textvariable=rotulo).pack(side='left',padx=10)
    # Pantalla de exhibición: ventana aparte con la escena de MuJoCo, el cuadro (foto o vídeo) y la cara.
    def pantalla_3d():
        try:
            if session.vista_aparte is None:
                if session.abrir_pantalla():boton_pantalla.config(text='Cerrar pantalla 3D')
            else:session.cerrar_pantalla();boton_pantalla.config(text='Pantalla 3D')
        except Exception as e:events.put('No se pudo abrir la pantalla 3D: '+str(e))
    boton_pantalla=ttk.Button(barra,text='Pantalla 3D',command=pantalla_3d);boton_pantalla.pack(side='right')
    def abrir_cara():
        # La cara del robot es una página que sirve este programa: se abre en su propia ventana del navegador.
        import webbrowser
        try:webbrowser.open_new(f'http://127.0.0.1:{session.cara.puerto}/')
        except Exception as e:events.put('No se pudo abrir la cara: '+str(e))
    if session.cara:ttk.Button(barra,text='Cara',command=abrir_cara).pack(side='right',padx=(0,6))
    # Idioma de la conversación: sigue solo al de cada petición; aquí se ve y, si hace falta, se elige a mano.
    propios={i.propio:codigo for codigo,i in IDIOMAS.items()}
    idioma_visto=tk.StringVar(value=IDIOMAS[session.idioma].propio)
    selector_idioma=ttk.Combobox(barra,textvariable=idioma_visto,values=list(propios),state='readonly',width=9)
    selector_idioma.pack(side='right',padx=(2,14))
    selector_idioma.bind('<<ComboboxSelected>>',lambda e:session.fijar_idioma(propios[idioma_visto.get()]))
    ttk.Label(barra,text='Idioma:').pack(side='right')
    # Frase a frase: empieza a hablar con la primera frase. Sin marcar, el turno de antes (todo preparado y luego suena).
    rapido=tk.BooleanVar(value=session.por_frases)
    def frase_a_frase():
        session.por_frases=rapido.get();session.preparar_calculo()
    ttk.Checkbutton(barra,text='Frase a frase',variable=rapido,command=frase_a_frase).pack(side='right',padx=(0,14))
    row=ttk.Frame(ui);row.pack(fill='x',padx=20)
    mode=tk.StringVar(value='region');ttk.Radiobutton(row,text='Marcar punto',variable=mode,value='punto').pack(side='left')
    ttk.Radiobutton(row,text='Marcar región',variable=mode,value='region').pack(side='left')
    ttk.Button(row,text='Quitar selección',command=quitar_seleccion).pack(side='left',padx=(6,0))
    data=tk.StringVar(value=session.dataset)
    choice=ttk.Combobox(row,textvariable=data,values=[k for k,v in session.motivos.items() if v],state='readonly',width=15)
    choice.pack(side='left',padx=20);choice.bind('<<ComboboxSelected>>',lambda e:setattr(session,'dataset',data.get()))
    def demo_run():
        if session.rotulo_imagen()!=EJEMPLO:events.put('La demo humana describe el cuadro de ejemplo, no la imagen cargada.')
        session.enviar('',demo_bloques(session.idioma))
    ttk.Button(row,text='Demo humana',command=demo_run).pack(side='left')
    # Conversación de ejemplo con los movimientos de la biblioteca (direcciones, horario), sin pasar por la IA.
    ttk.Button(row,text='Demo biblioteca',command=lambda:session.enviar('',demo_biblioteca(),idioma=POR_DEFECTO)).pack(side='left',padx=(6,0))
    ttk.Button(row,text='Interrumpir',command=session.interrumpir).pack(side='left',padx=10)
    if real:
        for name in ('Saludo','Abanico'):
            ttk.Button(row,text=name+(' ambos' if len(session.brazos)==2 else ''),command=lambda n=name:session.bailar(n)).pack(side='left',padx=3)
    entry=ttk.Entry(ui,font=('Segoe UI',13));entry.pack(fill='x',padx=20,pady=12)
    def send():
        text=entry.get().strip();marcado=seleccion[0]
        if not text and marcado:text=pregunta_seleccion(session.idioma,marcado)      # solo la selección: se pide que la explique
        if text:
            entry.delete(0,'end');events.put('Tú: '+text+(' [sobre lo marcado en la imagen]' if marcado else ''))
            session.enviar(text,seleccion=marcado);quitar_seleccion()
    entry.bind('<Return>',lambda e:send())
    actions=ttk.Frame(ui);actions.pack()
    ttk.Button(actions,text='Preguntar a la IA',command=send).pack(side='left',padx=5)
    if real:
        def soltar():
            try:session.soltar_real()
            except Exception as e:events.put('No se confirmó soltar: '+str(e))
        if session.plegado is not None:
            ttk.Button(actions,text='Volver a punto cero',command=session.volver_a_cero).pack(side='left',padx=5)
        ttk.Button(actions,text='Soltar ambos (sujétalos)' if len(session.brazos)>1 else 'Soltar brazo (sujétalo)',command=soltar).pack(side='left',padx=5)
    recording=[False]
    def mic():
        try:
            if not recording[0]:
                session.interrumpir();session.micro.empezar();recording[0]=True
                if session.cara:session.cara.escuchando(True)
                micbutton.config(text='Terminar grabación');events.put('Escuchando (máximo 20 s).')
            else:
                audio=session.micro.terminar();recording[0]=False;micbutton.config(text='Hablar por micro')
                if session.cara:session.cara.escuchando(False)
                def recognize():
                    try:
                        # El reconocimiento decide a la vez el texto y el idioma: la conversación sigue al que se ha hablado.
                        text,hablado=session.micro.transcribir(audio,Path(root)/'datos/modelos/whisper',session.idioma)
                        marcado=seleccion[0]
                        if text:
                            events.put('Tú: '+text+(' [sobre lo marcado en la imagen]' if marcado else ''))
                            session.enviar(text,idioma=hablado,seleccion=marcado);ui.after(0,quitar_seleccion)
                        else:events.put('No se detectó voz; inténtalo de nuevo.')
                    except Exception as e:events.put('Micrófono: '+str(e))
                threading.Thread(target=recognize,daemon=True).start()
        except Exception as e:events.put('Micrófono: '+str(e))
    micbutton=ttk.Button(actions,text='Hablar por micro',command=mic);micbutton.pack(side='left',padx=5)
    # Las voces de ElevenLabs se usan una vez ahora, en segundo plano: la primera vez de cada una tarda más de 10 s.
    threading.Thread(target=session.voz.preparar,daemon=True,name='preparar-voces').start()
    if real:
        # La velocidad es lo que más separa a los brazos reales de la simulación: se elige aquí, sin editar archivos.
        opciones={'20°/s':20.,'60°/s':60.,'90°/s':90.,'110°/s':110.,'130°/s':130.,'150°/s (simulación)':150.}
        actual=next((k for k,v in opciones.items() if v==session.velocidad),f'{session.velocidad:.0f}°/s')
        opciones.setdefault(actual,session.velocidad)
        speed=tk.StringVar(value=actual)
        ttk.Label(actions,text='Velocidad:').pack(side='left',padx=(12,2))
        selector=ttk.Combobox(actions,textvariable=speed,values=list(opciones),state='readonly',width=20)
        selector.pack(side='left');selector.bind('<<ComboboxSelected>>',lambda e:session.fijar_velocidad(opciones[speed.get()]))
    log=tk.Text(ui,height=7,wrap='word',font=('Segoe UI',10));log.pack(fill='both',expand=True,padx=20,pady=8)
    # Marcar en la imagen no dice nada por sí solo: deja la zona seleccionada para la pregunta siguiente, que se
    # hace por texto o por voz (o, sin escribir nada, con «Preguntar a la IA»). Así la IA explica justo eso.
    drag=[None]
    def down(e):
        drag[0]=[float(np.clip(e.y/ph*1000,0,1000)),float(np.clip(e.x/pw*1000,0,1000))]
        quitar_seleccion()
    def motion(e):
        if mode.get()=='region' and drag[0]:
            canvas.delete('seleccion')
            canvas.create_rectangle(drag[0][1]*pw/1000,drag[0][0]*ph/1000,e.x,e.y,outline='orange',width=3,tags='seleccion')
    def up(e):
        if drag[0] is None:return
        p=[float(np.clip(e.y/ph*1000,0,1000)),float(np.clip(e.x/pw*1000,0,1000))]
        inicio,drag[0]=drag[0],None
        canvas.delete('seleccion')
        if mode.get()=='region':
            region=[np.minimum(inicio,p).tolist(),np.maximum(inicio,p).tolist()]
            if min(np.array(region[1])-region[0])<15:return            # un recuadro diminuto es un clic sin querer
            seleccion[0]={'region':region}
            canvas.create_rectangle(region[0][1]*pw/1000,region[0][0]*ph/1000,region[1][1]*pw/1000,region[1][0]*ph/1000,
                                    outline='orange',width=3,tags='seleccion')
        else:
            seleccion[0]={'punto':p};x,y=p[1]*pw/1000,p[0]*ph/1000
            canvas.create_oval(x-12,y-12,x+12,y+12,outline='orange',width=3,tags='seleccion')
            canvas.create_line(x-18,y,x+18,y,fill='orange',width=2,tags='seleccion');canvas.create_line(x,y-18,x,y+18,fill='orange',width=2,tags='seleccion')
        events.put('Zona marcada. Pregunta por ella con texto o por voz, o pulsa «Preguntar a la IA» sin escribir nada para que la explique.')
    canvas.bind('<ButtonPress-1>',down);canvas.bind('<B1-Motion>',motion);canvas.bind('<ButtonRelease-1>',up)
    ui.bind('<Escape>',lambda e:session.interrumpir())
    last_error=[None]
    last_view_error=[None]
    last_notices={}
    vista_cerrada=[False]
    # Todo lo que se muestra queda también en un archivo: sin él no hay rastro de una sesión real.
    diario=None
    try:
        carpeta=Path(root)/'salidas/diagnostico';carpeta.mkdir(parents=True,exist_ok=True)
        diario=open(carpeta/time.strftime('sesion_%Y%m%d_%H%M%S.log'),'a',encoding='utf8',buffering=1)
    except OSError:pass
    def anotar(text):
        log.insert('end',text+'\n');log.see('end')
        if diario is not None:
            try:diario.write(time.strftime('%H:%M:%S ')+text+'\n')
            except (OSError,ValueError):pass
    def poll():
        if session.closed:return
        while not events.empty():anotar(events.get())
        for b in session.brazos.values():
            warning=getattr(getattr(b,'native',None),'aviso',None)
            if warning and warning!=last_notices.get(b.port):
                events.put(b.port+': '+warning);last_notices[b.port]=warning
        if idioma_visto.get()!=IDIOMAS[session.idioma].propio:idioma_visto.set(IDIOMAS[session.idioma].propio)
        # El cuadro del lienzo y el de la vista pequeña siguen a la imagen: foto cargada o vídeo en directo.
        fuente=session.directo
        if fuente is not None and fuente.error:
            events.put(fuente.error+' Se deja el directo; queda la última imagen.')
            session.soltar_directo();fuente.cerrar(esperar=False)
        nueva=pintar_obra()
        if nueva is not False:
            if rotulo.get()!='Imagen: '+session.rotulo_imagen():rotulo.set('Imagen: '+session.rotulo_imagen())
            panel=getattr(session,'vista_panel',None)
            if live is not None and hasattr(panel,'cambiar_imagen'):
                try:panel.cambiar_imagen(nueva)
                except Exception:pass                        # la vista pequeña es solo dibujo
        if session.vista_aparte is not None and session.vista_aparte.cerrada.is_set():
            motivo=session.vista_aparte.error;session.cerrar_pantalla()
            boton_pantalla.config(text='Pantalla 3D')
            events.put('Pantalla 3D cerrada'+(': '+motivo if motivo else '')+'. Los brazos no cambian por ello.')
        if live is not None and not session.liberado:
            try:
                poses=session.control.medir()
                img=(session.vista_panel.foto(poses) if len(poses)>1 else
                     session.vista_panel.foto(next(iter(poses.values())),0,session.motor.reposo_real))
                session._photo_modelo=tk.PhotoImage(data=cv2.imencode('.png',cv2.resize(img,(440,309)))[1].tobytes())
                live.config(image=session._photo_modelo)
                last_view_error[0]=None
            except Exception as e:
                message='Vista de encoders: '+str(e)
                if message!=last_view_error[0]:events.put(message);last_view_error[0]=message
        if session.control.error:ui.title('SO-101 · DETENIDO: '+session.control.error)
        elif last_error[0] is not None:   # parada reconocida con Volver a punto cero
            last_error[0]=None;ui.title('SO-101 · CHATBOT REAL '+brazo_real.port+' · cuadro virtual sin cámara')
        if session.control.error and session.control.error!=last_error[0]:
            last_error[0]=session.control.error;session.interrumpir()
            events.put('DETENIDO: '+session.control.error+'. Pulsa Volver a punto cero para recuperarlo, o sujeta y suelta el brazo.')
        if real and session.mundo and session.mundo.cerrado and not vista_cerrada[0]:
            vista_cerrada[0]=True;session.interrumpir()
            events.put('Vista 3D cerrada: movimiento detenido. El brazo mantiene par; sujétalo y pulsa Soltar.')
        ui.after(100,poll)
    def close():
        if real and not session.liberado:
            session.interrumpir();events.put('Sujeta el brazo y pulsa Soltar brazo antes de cerrar.');return
        session.cerrar();ui.destroy()
    ui.protocol('WM_DELETE_WINDOW',close);poll()
    events.put('Cuadro listo. Pregunta por texto o micro; haz clic o arrastra para indicar referencias.')
    if real:events.put('REAL: '+', '.join(b.port for b in session.brazos.values())+'. Cuadro virtual delante; no se observa el entorno. Perfil de '+f'{session.velocidad:.0f}'+'°/s. PARAR detiene toda la sesión.')
    if real and session.plegado is not None:
        events.put('En cada petición los brazos se despliegan a la postura de trabajo y, al acabar la respuesta, vuelven solos a punto cero.'
                   if session.plegar_al_acabar else
                   'En la primera petición los brazos se despliegan a la postura de trabajo. Antes de soltar, pulsa Volver a punto cero.')
    if demo:ui.after(1200,demo_run)
    ui.mainloop()
    return session

