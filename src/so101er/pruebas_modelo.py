"""Banco de pruebas: modelo nominal con ejes, danzas y prueba USB independiente."""
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np

JOINTS=('Base','Hombro','Codo','Muñeca','Giro pinza','Apertura pinza')

def pose_para_vista(dispositivo,q):
    """Los ejes nativos relativos NO son ángulos URDF ni una estimación de pose."""
    return np.asarray(q,float).copy() if dispositivo=='Simulación' else None
DANZAS={
 'Abanico':[[-35,0,0,15,-15,0],[35,0,0,-10,15,100],[-35,0,0,15,-15,40],[0,0,0,0,0,0]],
 'Saludo':[[0,-10,10,20,-20,100],[0,5,-5,-20,20,0],[0,-10,10,20,-20,100],[0,0,0,0,0,0]],
}


def gestos_para_inicio(nombre,inicio):
    if nombre!='Saludo':return DANZAS
    q=np.asarray(inicio,float)
    targets=[]
    for delta in ([0,8,-12,20,-15],[0,8,-12,20,15],[0,8,-12,20,-15]):
        target=q.copy();target[:5]+=delta;target[5]=100.;targets.append(target)
    return {'Saludo':targets}


def secuencia(nombre,inicio):
    """Referencias nominales explícitas; conserva el punto de inicio y regreso."""
    current=np.asarray(inicio,float).copy();plans=[];t=0.
    for target in [*DANZAS[nombre],inicio]:
        target=np.asarray(target,float)
        duration=max(1.2,1.875*float(np.max(abs(target[:5]-current[:5])))/18,
                     1.875*abs(target[5]-current[5])/60)
        plans.append((t,duration,current.copy(),target.copy()));t+=duration;current=target
    return plans


def muestra(plans,t):
    for start,duration,a,b in plans:
        if t<=start+duration:
            s=float(np.clip((t-start)/duration,0,1));u=s**3*(10+s*(-15+6*s))
            return a+(b-a)*u
    return plans[-1][3].copy()


class Modelo:
    """MuJoCo solo renderiza consignas. Su verdad interna no llega al controlador USB."""
    def __init__(self):
        import mujoco as mj
        from .hardware.mujoco_sim import DIR_MODELO
        from .cinematica.modelo import Cinematica
        self.mj=mj;self.kin=Cinematica()
        self.model=mj.MjModel.from_xml_path(str(DIR_MODELO/'so101_new_calib_camera.xml'))
        self.model.vis.global_.offwidth=800;self.model.vis.global_.offheight=600
        self.model.vis.headlight.ambient[:]=[.35,.35,.35]
        self.model.vis.headlight.diffuse[:]=[.6,.6,.6]
        self.data=mj.MjData(self.model);self.ghost_data=mj.MjData(self.model)
        self.renderer=mj.Renderer(self.model,450,640)
        self.camera=mj.MjvCamera();self.camera.lookat[:]=[.13,0,.18]
        self.camera.distance=.78;self.camera.azimuth=120;self.camera.elevation=-18
        self.options=mj.MjvOption()
    def foto(self,q,axis,ghost=None):
        import cv2
        from .hardware.mujoco_sim import MundoMuJoCo
        mj=self.mj;self.data.qpos[:]=MundoMuJoCo.a_rad(q)
        mj.mj_forward(self.model,self.data)
        self.renderer.update_scene(self.data,camera=self.camera,scene_option=self.options)
        image=cv2.cvtColor(self.renderer.render(),cv2.COLOR_RGB2BGR)
        if ghost is not None:
            ghost=np.asarray(ghost,float)
            if ghost.shape!=(6,) or not np.isfinite(ghost).all():raise ValueError('referencia visual inválida')
            # Dos pasadas exclusivas de render. La sombra no cambia consignas,
            # calibraciones ni entradas del controlador.
            self.ghost_data.qpos[:]=MundoMuJoCo.a_rad(ghost);mj.mj_forward(self.model,self.ghost_data)
            self.renderer.update_scene(self.ghost_data,camera=self.camera,scene_option=self.options)
            ref=cv2.cvtColor(self.renderer.render(),cv2.COLOR_RGB2GRAY)
            blue=np.stack([ref,np.rint(ref*.65).astype(np.uint8),np.rint(ref*.10).astype(np.uint8)],axis=-1)
            mask=ref>8
            image[mask]=np.rint(image[mask]*.65+blue[mask]*.35).astype(np.uint8)
            self.renderer.update_scene(self.data,camera=self.camera,scene_option=self.options)
        # Guías sobre la vista humana; nunca se envían al actor ni al USB.
        # El origen/ejes salen de consignas y URDF. La cámara solo proyecta el dibujo.
        frame=self.kin.marcos(q)[min(axis,4)];p=frame[:3,3]/1000
        scene=self.renderer.scene
        eye=np.mean([c.pos for c in scene.camera],axis=0)
        forward=np.mean([c.forward for c in scene.camera],axis=0);forward/=np.linalg.norm(forward)
        up=np.mean([c.up for c in scene.camera],axis=0);up/=np.linalg.norm(up)
        right=np.cross(forward,up);f=225/np.tan(np.radians(self.model.vis.global_.fovy)/2)
        def project(point):
            relative=point-eye;depth=relative@forward
            return tuple(np.rint([320+f*(relative@right)/depth,225-f*(relative@up)/depth]).astype(int))
        for k,color in enumerate(((30,30,255),(40,225,40),(255,150,40))):
            end=project(p+.09*frame[:3,k]);cv2.arrowedLine(image,project(p),end,color,3,cv2.LINE_AA,tipLength=.2)
            cv2.putText(image,'XYZ'[k],end,cv2.FONT_HERSHEY_SIMPLEX,.6,color,2,cv2.LINE_AA)
        return image
    def cerrar(self):self.renderer.close()


class Panel:
    def __init__(self,root,parent=None,abrir_rangos_callback=None):
        import tkinter as tk
        from tkinter import ttk
        from .interfaz.embebido import ventana
        self.tk=tk;self.root=Path(root);self.ui=ventana(parent);self.ui.title('SO-101 · Pruebas con ejes y danzas')
        self.abrir_rangos_callback=abrir_rangos_callback
        self.visible=parent is None
        self.ui.geometry('1140x900');self.ui.minsize(1000,800)
        self.modelo=Modelo();self.q=np.zeros(6);self.dance=None;self.focus=0;self.updating=False
        from .interfaz.referencia import cargar
        self.zero_reference=cargar(self.root,self.modelo.kin)
        self.cancel=threading.Event();self.worker=None;self.events=queue.Queue();self.closed=False
        self.native=None;self.device=tk.StringVar(value='Simulación')
        self.alignment=None;self.draft=None;self.monitor=None;self.edit=tk.BooleanVar(value=False)
        self.entry=tk.BooleanVar(value=False);self.checked=[tk.BooleanVar(value=False) for _ in range(6)]
        self.shadow=tk.BooleanVar(value=True);self.ghost_mode=tk.StringVar(value='Cero operativo')
        self.sim_reference=self.zero_reference.copy();self.rangos_child=None
        self.status=tk.StringVar(value='Vista previa. Los deslizadores y las danzas solo mueven el modelo.')
        ttk.Label(self.ui,text='Modelo, articulaciones y secuencias de prueba',font=('Segoe UI',16,'bold')).pack(pady=10)
        selector=ttk.Combobox(self.ui,textvariable=self.device,values=['Simulación','COM7','COM8'],state='readonly',width=22)
        selector.pack();selector.bind('<<ComboboxSelected>>',lambda e:self.cambiar_dispositivo())
        body=ttk.Frame(self.ui);body.pack(fill='both',expand=True,padx=12)
        left=ttk.Frame(body);left.pack(side='left',fill='both',expand=True)
        self.picture=ttk.Label(left);self.picture.pack(pady=5)
        self.drag=None
        self.picture.bind('<ButtonPress-1>',lambda e:setattr(self,'drag',(e.x,e.y)))
        self.picture.bind('<B1-Motion>',self.orbitar)
        ttk.Label(left,text='Rojo X · Verde Y · Azul Z. Ejes locales de la articulación seleccionada.').pack()
        self.viewnote=tk.StringVar(value='Vista nominal URDF; no es el cero operativo recogido.')
        ttk.Label(left,textvariable=self.viewnote,foreground='#8e4b00',wraplength=630).pack(pady=5)
        row=ttk.Frame(left);row.pack(fill='x',pady=3)
        ttk.Checkbutton(row,text='Sombra azul',variable=self.shadow).pack(side='left')
        ttk.Combobox(row,textvariable=self.ghost_mode,values=['Cero operativo','Referencia guardada','Objetivo mandado'],state='readonly',width=23).pack(side='left',padx=8)
        ttk.Button(row,text='Calibrar rangos con barras',command=self.abrir_rangos).pack(side='left',padx=5)
        ttk.Checkbutton(left,text='Alinear este USB sin mover motores',variable=self.edit,command=self.editar_alineacion).pack(anchor='w')
        ttk.Label(left,text='1. Pon el dibujo como el brazo y pulsa Esta es la postura.\n2. Mueve cada parte a mano. Si el dibujo va al revés, pulsa su ±.\n3. Marca Coincide y guarda. Hazlo una vez por brazo.',justify='left').pack(anchor='w',pady=4)
        row=ttk.Frame(left);row.pack(fill='x')
        ttk.Button(row,text='Usar postura de referencia',command=self.recogida_orientativa).pack(side='left',padx=3)
        ttk.Button(row,text='Esta es la postura',command=self.capturar_alineacion).pack(side='left',padx=3)
        ttk.Button(row,text='Guardar alineación',command=self.guardar_alineacion).pack(side='left',padx=3)
        row=ttk.Frame(left);row.pack(fill='x',pady=5)
        for i,name in enumerate(JOINTS):
            cell=ttk.Frame(row);cell.pack(side='left',padx=2)
            ttk.Button(cell,text=f'{i+1} ±',width=5,command=lambda j=i:self.invertir(j)).pack()
            ttk.Checkbutton(cell,text='Coincide',variable=self.checked[i]).pack()
        right=ttk.Frame(body);right.pack(side='right',fill='y',padx=(8,0))
        self.variables=[];self.readouts=[];self.sliders=[];self.refdots=[]
        low=np.r_[self.modelo.kin.lim_inf,0];high=np.r_[self.modelo.kin.lim_sup,100]
        for i,name in enumerate(JOINTS):
            label=ttk.Label(right,text=name);label.pack(anchor='w')
            row=ttk.Frame(right);row.pack(fill='x')
            var=tk.DoubleVar(value=0);self.variables.append(var)
            column=ttk.Frame(row);column.pack(side='left')
            slider=ttk.Scale(column,from_=low[i],to=high[i],variable=var,orient='horizontal',length=220,
                             command=lambda v,j=i:self.mover(j,float(v)))
            slider.pack();slider.bind('<Button-1>',lambda e,j=i:setattr(self,'focus',j))
            dot=tk.Canvas(column,width=220,height=12,highlightthickness=0)
            dot.pack();self.refdots.append(dot)
            self.sliders.append(slider)
            value=ttk.Label(row,text='0.0',width=6);value.pack(side='left');self.readouts.append(value)
        actions=ttk.Frame(right);actions.pack(fill='x',pady=12)
        for name in DANZAS:ttk.Button(actions,text=name,command=lambda n=name:self.bailar(n)).pack(side='left',padx=3)
        ttk.Button(right,text='Volver a la postura inicial',command=self.cero).pack(fill='x',pady=4)
        ttk.Separator(right).pack(fill='x',pady=12)
        ttk.Label(right,text='USB · Control del brazo elegido',font=('Segoe UI',11,'bold')).pack(anchor='w')
        ttk.Label(right,text='Deslizadores y bailes sobre el USB activo.\nGrados respecto a la postura de activación.\nVelocidad limitada a 20°/s.').pack(anchor='w',pady=5)
        self.clear=tk.BooleanVar(value=False)
        ttk.Checkbutton(right,text='Otro brazo apartado y recorrido libre',variable=self.clear).pack(anchor='w')
        ttk.Checkbutton(right,text='COM8: entrada suave del codo (≤3°)',variable=self.entry).pack(anchor='w')
        self.button=ttk.Button(right,text='Activar brazo seleccionado',command=self.conectar);self.button.pack(fill='x',pady=5)
        ttk.Button(right,text='Soltar brazo (sujétalo primero)',command=self.soltar).pack(fill='x',pady=3)
        self.usb=ttk.Label(right,text='Sin movimiento físico iniciado');self.usb.pack(anchor='w')
        tk.Button(right,text='PARAR · Esc',background='#ad2020',foreground='white',font=('Segoe UI',13,'bold'),command=self.parar).pack(fill='x',pady=12)
        ttk.Label(right,text='● azul: posición de referencia\nLa marca no mueve el robot.',foreground='#166aa3').pack(anchor='w')
        import cv2
        thumb=cv2.resize(self.modelo.foto(self.zero_reference,0),(164,115))
        self.reference_photo=tk.PhotoImage(data=cv2.imencode('.png',thumb)[1].tobytes())
        self.mini=ttk.Frame(left,relief='solid',borderwidth=1)
        ttk.Label(self.mini,image=self.reference_photo).pack()
        ttk.Label(self.mini,text='Referencia fija · cero operativo',font=('Segoe UI',8)).pack()
        self.mini.place(in_=self.picture,relx=1,x=-8,y=8,anchor='ne')
        ttk.Label(self.ui,textvariable=self.status,wraplength=1040,font=('Segoe UI',10)).pack(fill='x',padx=16,pady=10)
        self.ui.bind('<Escape>',lambda e:self.parar());self.ui.protocol('WM_DELETE_WINDOW',self.cerrar)
        self.ui.after(50,self.tick)

    def cal_actual(self):
        data=json.loads((self.root/'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
        return next(c for c in data['brazos'] if c['puerto']==self.device.get())

    def abrir_rangos(self):
        if self.native:self.status.set('Sujeta y suelta el brazo antes de abrir la calibración de rangos.');return
        if getattr(self,'abrir_rangos_callback',None):self.abrir_rangos_callback();return
        if self.rangos_child is not None and self.rangos_child.poll() is None:return
        if self.monitor:self.monitor.cerrar();self.monitor=None
        self.edit.set(False);self.draft=None
        import subprocess,sys,os
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
        self.rangos_child=subprocess.Popen([sys.executable,'-m','so101er.calibracion_usb','--raiz',str(self.root),'--solo-rangos'],
                                         env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.status.set('Calibrador de barras abierto: elige motor, recórrelo a mano y guarda. Cierra esa ventana antes de activar USB aquí.')

    def orbitar(self,event):
        if self.drag:
            x,y=self.drag;self.modelo.camera.azimuth+=(event.x-x)*.4
            self.modelo.camera.elevation=float(np.clip(self.modelo.camera.elevation-(event.y-y)*.4,-80,70))
            self.drag=(event.x,event.y)

    def actual_modelo(self):
        return self.alignment.a_modelo(self.native.raw_actual()) if self.alignment else self.native.ejes()

    def enviar_modelo(self,q):
        if self.alignment:
            q=np.asarray(q,float)
            if (q[:5]<self.modelo.kin.lim_inf).any() or (q[:5]>self.modelo.kin.lim_sup).any() or not 0<=q[5]<=100:
                raise ValueError('consigna fuera del modelo')
            native_q=self.native.coords.a_ejes(self.alignment.a_raw(q))
            self.native.set(native_q)
        else:self.native.set(q)

    def editar_alineacion(self):
        if self.rangos_child is not None and self.rangos_child.poll() is None:
            self.edit.set(False);self.status.set('Cierra primero el calibrador de barras para liberar los USB.');return
        if self.native:
            self.edit.set(False);self.status.set('Sujeta y suelta el brazo antes de alinearlo a mano.');return
        if self.device.get()=='Simulación':
            self.edit.set(False);self.status.set('Selecciona COM7 o COM8 para alinear.');return
        self.dance=None;self.draft=None
        if self.monitor:self.monitor.cerrar();self.monitor=None
        if self.edit.get():
            from .hardware.calibracion import Monitor
            self.monitor=Monitor()
            for c in self.checked:c.set(False)
            for i,s in enumerate(self.sliders):
                s.config(from_=self.modelo.kin.lim_inf[i] if i<5 else 0,
                         to=self.modelo.kin.lim_sup[i] if i<5 else 100,state='normal')
            if self.alignment:
                from .hardware.alineacion import Alineacion
                a=self.alignment
                self.draft=Alineacion(self.cal_actual(),a.raw,a.q,a.signos)
                for s in self.sliders:s.config(state='disabled')
                self.status.set('Revisión de alineación guardada: amarillo sigue encoders y azul conserva su referencia. No necesitas recapturar si coincide. Recogida orientativa permite reajustar desde cero.')
            else:self.status.set('Ajusta SOLO el dibujo hasta que coincida con el brazo físico, incluida la pinza. Luego Capturar postura.')
        else:
            for s in self.sliders:s.config(state='disabled')

    def muestra_pasiva(self):
        if not self.monitor:raise ValueError('activa primero Alinear este USB')
        from .hardware.calibracion import comprobar_muestra
        samples,errors=self.monitor.leer();sample=samples.get(self.device.get())
        if sample is None:raise ValueError('esperando USB: '+str(errors))
        comprobar_muestra(sample);cal=self.cal_actual()
        if sample['serie']!=cal['serie_usb'] or sample['identidad']!=cal['identidad_servos']:
            raise ValueError('el dispositivo no coincide con sus rangos')
        return sample

    def capturar_alineacion(self):
        try:
            if not self.edit.get():raise ValueError('marca Alinear este USB antes de capturar')
            from .hardware.alineacion import Alineacion
            sample=self.muestra_pasiva()
            self.draft=Alineacion(self.cal_actual(),sample['raw'],self.q)
            for s in self.sliders:s.config(state='disabled')
            for c in self.checked:c.set(False)
            self.status.set('Referencia capturada. Mueve cada eje A MANO, invierte ± si el modelo gira al revés y marca Coincide.')
        except Exception as e:self.status.set(str(e))

    def recogida_orientativa(self):
        if not self.edit.get() or self.native:return
        self.draft=None;self.q=self.zero_reference.copy()
        for s in self.sliders:s.config(state='normal')
        for c in self.checked:c.set(False)
        self.status.set('Solo referencia visual aproximada. Ajusta los seis ejes hasta que coincidan con tu brazo antes de Capturar.')

    def invertir(self,i):
        if not self.edit.get() or self.draft is None:self.status.set('Captura primero la postura de referencia.');return
        self.draft.invertir(i);self.checked[i].set(False)

    def guardar_alineacion(self):
        try:
            if self.draft is None:raise ValueError('falta capturar una postura conocida')
            self.muestra_pasiva()
            self.draft.guardar(self.root,self.device.get(),[c.get() for c in self.checked])
            self.alignment=self.draft;self.draft=None;self.edit.set(False)
            if self.monitor:self.monitor.cerrar();self.monitor=None
            self.status.set('Alineación guardada para '+self.device.get()+'. Activa este brazo o alinea el otro. Ningún motor fue activado.')
        except Exception as e:self.status.set(str(e))

    def mover(self,i,value):
        if self.updating:return
        if self.worker and self.worker.is_alive():return
        self.dance=None;self.q[i]=value;self.focus=i
        if self.edit.get():return
        if self.device.get()!='Simulación':
            if not self.native:self.status.set('Pulsa Activar brazo seleccionado antes de probar los controles.');return
            try:self.enviar_modelo(self.q);self.status.set('Control real '+self.native.port+' · objetivo dentro de rangos medidos.')
            except Exception as e:self.status.set(str(e))
            return
        self.status.set('Vista previa por articulación. No se envían estos ángulos al USB.')

    def bailar(self,name):
        if self.worker and self.worker.is_alive():return
        if self.device.get()!='Simulación':
            if not self.native or not self.alignment or self.edit.get():
                self.status.set('Baile bloqueado: activa el USB con su alineación guardada y sal de Alinear.');return
            try:
                from .hardware.alineacion import plan_real
                origin=self.actual_modelo()
                plans=plan_real(name,origin,self.alignment,self.native.coords,self.modelo.kin,gestos_para_inicio(name,origin))
                self.dance=(time.monotonic(),plans);self.status.set(name+' en '+self.native.port+'; regreso a su postura inicial.')
            except Exception as e:self.status.set('Baile no iniciado: '+str(e))
            return
        self.dance=(time.monotonic(),secuencia(name,self.q.copy()))
        self.status.set(f'{name}: secuencia de ejemplo en el modelo. Regresa a la postura inicial.')

    def cero(self):
        if self.worker and self.worker.is_alive():return
        if self.native:
            self.dance=None;self.q=self.native.coords.a_ejes(self.native.coords.home)
            if self.alignment:self.q=self.alignment.a_modelo(self.native.coords.home)
            try:self.enviar_modelo(self.q)
            except Exception as e:self.status.set(str(e))
            return
        if self.device.get()!='Simulación':return
        now=self.q.copy();duration=max(1.2,1.875*max(abs(now[:5]))/18)
        self.dance=(time.monotonic(),[(0.,duration,now,np.zeros(6))])

    def prueba(self):
        if self.worker and self.worker.is_alive():return
        if not self.clear.get():self.status.set('Aparta COM8 del barrido y confirma la casilla antes de iniciar.');return
        self.dance=None;self.cancel=threading.Event();self.button.config(state='disabled')
        def run():
            try:
                for remaining in range(5,0,-1):
                    self.events.put(f'COM7 comenzará en {remaining} s. Parar/Esc cancela.')
                    if self.cancel.wait(1):raise RuntimeError('prueba cancelada antes del movimiento')
                from .hardware.prueba_base import ejecutar
                ejecutar(self.root,self.cancel,self.events.put)
            except Exception as e:self.events.put('Prueba detenida: '+str(e))
            finally:self.events.put({'terminado':True})
        self.worker=threading.Thread(target=run,daemon=True,name='prueba-base-com7');self.worker.start()

    def parar(self):
        self.dance=None;self.cancel.set()
        if self.native:self.native.parar();self.q=self.actual_modelo()
        self.status.set('Movimiento detenido. El brazo mantiene par para no caer; sujétalo antes de Soltar.')

    def cambiar_dispositivo(self):
        if self.native:
            self.device.set(self.native.port);self.status.set('Sujeta y suelta el brazo activo antes de cambiar a otro.');return
        if self.monitor:self.monitor.cerrar();self.monitor=None
        self.edit.set(False);self.draft=None;self.alignment=None
        self.dance=None;self.clear.set(False);self.q=np.zeros(6)
        if self.device.get()!='Simulación':
            try:
                from .hardware.alineacion import Alineacion
                self.alignment=Alineacion.cargar(self.root,self.device.get(),self.cal_actual())
            except Exception as e:self.status.set(str(e))
        low=np.r_[self.modelo.kin.lim_inf,0];high=np.r_[self.modelo.kin.lim_sup,100]
        for i,s in enumerate(self.sliders):s.config(from_=low[i],to=high[i],state='normal' if self.device.get()=='Simulación' else 'disabled')
        self.status.set('Seleccionado '+self.device.get()+'. Activar toma la postura actual sin saltar a otra pose.')

    def conectar(self):
        if self.native or self.device.get()=='Simulación':return
        if self.rangos_child is not None and self.rangos_child.poll() is None:self.status.set('Cierra primero el calibrador de barras para liberar los USB.');return
        if self.edit.get():self.status.set('Termina y guarda la alineación antes de activar.');return
        if not self.clear.get():self.status.set('Aparta el otro brazo y confirma la casilla.');return
        try:
            from .hardware.alineacion import Alineacion
            self.alignment=Alineacion.cargar(self.root,self.device.get(),self.cal_actual())
            from .hardware.manual_usb import ManualUSB
            self.native=ManualUSB(self.root,self.device.get(),entrada_suave=self.entry.get());self.q=self.actual_modelo()
            bounds=np.array([self.native.coords.a_ejes(self.native.coords.low),self.native.coords.a_ejes(self.native.coords.high)])
            if self.alignment:
                bounds=np.sort(np.array([self.alignment.a_modelo(self.native.coords.low),self.alignment.a_modelo(self.native.coords.high)]),axis=0)
                bounds[0]=np.maximum(bounds[0],np.r_[self.modelo.kin.lim_inf,0])
                bounds[1]=np.minimum(bounds[1],np.r_[self.modelo.kin.lim_sup,100])
            for i,s in enumerate(self.sliders):s.config(from_=bounds[0,i],to=bounds[1,i],state='normal')
            self.status.set('USB activo: '+self.device.get()+('. Correspondencia URDF cargada.' if self.alignment else '. Sin alineación: solo ejes relativos.'))
        except Exception as e:self.status.set('No se activa: '+str(e))

    def soltar(self):
        if not self.native:return
        self.dance=None
        try:self.native.soltar();self.native=None;self.cambiar_dispositivo();self.status.set('Par desactivado; puedes cambiar de brazo.')
        except Exception as e:self.status.set(str(e))

    def tick(self):
        if self.closed:return
        if not self.visible:self.ui.after(100,self.tick);return
        try:
            while not self.events.empty():
                event=self.events.get()
                if isinstance(event,str):self.status.set(event)
                elif 'angulo_relativo' in event:self.usb.config(text=f"Base real respecto al inicio: {event['angulo_relativo']:+.1f}°")
                elif event.get('terminado'):self.button.config(state='normal')
            if self.dance:
                start,plans=self.dance;elapsed=time.monotonic()-start;self.q=muestra(plans,elapsed)
                if self.native:self.enviar_modelo(self.q)
                if elapsed>=plans[-1][0]+plans[-1][1]:self.dance=None
            if self.native:
                values=self.actual_modelo()
                self.usb.config(text=('Encoders → URDF: ' if self.alignment else 'Grados relativos: ')+' / '.join(f'{v:.0f}' for v in values))
                if self.native.error:self.dance=None;self.status.set('DETENIDO: '+self.native.error)
            self.updating=True
            for i,v in enumerate(self.variables):v.set(float(self.q[i]));self.readouts[i].config(text=f'{self.q[i]:.1f}')
            from .interfaz.referencia import posicion_marca
            for i,dot in enumerate(self.refdots):
                dot.delete('all')
                if self.native and not self.alignment and not self.edit.get():continue
                mark=posicion_marca(self.zero_reference[i],float(self.sliders[i].cget('from')),float(self.sliders[i].cget('to')),dot.winfo_width())
                if mark:
                    x,outside=mark;dot.create_oval(x-4,2,x+4,10,fill='#2677b4' if not outside else '',outline='#2677b4',width=2)
            self.updating=False
            import cv2
            visual=pose_para_vista(self.device.get(),self.q)
            if self.edit.get():
                visual=self.q.copy()
                if self.draft:
                    sample=self.muestra_pasiva();visual=self.draft.a_modelo(sample['raw']);self.q=visual.copy()
                    self.viewnote.set('Lectura real con alineación en revisión. Comprueba cada eje a mano.')
            elif self.native and self.alignment:
                visual=self.actual_modelo();self.viewnote.set('Pose estimada desde encoders y alineación manual de '+self.native.port)
            ghost=None
            if self.shadow.get() and visual is not None:
                if self.ghost_mode.get()=='Objetivo mandado':
                    if self.native or self.device.get()=='Simulación':ghost=self.q.copy()
                elif self.ghost_mode.get()=='Cero operativo':ghost=self.zero_reference.copy()
                elif self.draft:ghost=self.draft.q.copy()
                elif self.alignment:ghost=self.alignment.q.copy()
                elif self.device.get()=='Simulación':ghost=self.sim_reference.copy()
            if self.device.get()=='Simulación':self.viewnote.set('Amarillo: modelo simulado. Azul: '+self.ghost_mode.get().lower()+'. Sin lectura física.')
            elif visual is not None:
                detail=('cero operativo indicado' if self.ghost_mode.get()=='Cero operativo' else
                        ('referencia capturada, sin guardar' if self.draft else 'referencia guardada') if self.ghost_mode.get()=='Referencia guardada' else
                        ('objetivo mandado' if ghost is not None else 'sin objetivo de motor: solo lectura'))
                source=('Amarillo: ajuste manual del dibujo, aún sin lectura real. ' if self.edit.get() and not self.draft else
                        'Amarillo: encoders, alineación en revisión. ' if self.draft else 'Amarillo: pose estimada desde encoders. ')
                self.viewnote.set(source+('Azul: '+detail+'.' if ghost is not None else 'Sin sombra: oculta o referencia no disponible.'))
            if visual is None:
                self.picture.config(image='',text='VISTA FÍSICA SIN ALINEAR\n\n0° = postura al activar este brazo.\nPuede estar completamente recogido.\n\nEsos valores NO son el cero del URDF.\n\nControl manual disponible con encoders reales.\nFalta registrar una postura conocida y comprobar\nel sentido de las cinco articulaciones.',font=('Segoe UI',14),anchor='center')
            else:
                self.photo=self.tk.PhotoImage(data=cv2.imencode('.png',self.modelo.foto(visual,self.focus,ghost))[1].tobytes())
                self.picture.config(image=self.photo,text='')
        except Exception as e:self.dance=None;self.status.set('Panel: '+str(e))
        self.ui.after(90,self.tick)

    def cerrar(self):
        if self.native:self.parar();self.status.set('Sujeta el brazo y pulsa Soltar antes de cerrar la ventana.');return
        self.cancel.set();self.dance=None
        if self.monitor:self.monitor.cerrar();self.monitor=None
        if self.worker and self.worker.is_alive():
            self.status.set('Esperando confirmación de par desactivado antes de cerrar…');self.ui.after(150,self.cerrar);return
        self.closed=True;self.modelo.cerrar();self.ui.destroy()

    def run(self):self.ui.mainloop()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raiz',default='.')
    Panel(parser.parse_args().raiz).run()
