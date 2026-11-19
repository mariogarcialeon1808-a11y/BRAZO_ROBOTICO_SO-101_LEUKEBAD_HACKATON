"""Preparación automática y avisos concretos antes del chatbot con USB real."""
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import time


class Preparador:
    def __init__(self,root,parent=None,calibrar_callback=None,chat_callback=None,soltar_callback=None,parar_callback=None):
        import tkinter as tk
        from tkinter import ttk
        from .interfaz.embebido import ventana
        self.tk=tk;self.root=Path(root);self.ui=ventana(parent);self.ui.title('SO-101 · Preparación automática del chatbot REAL')
        self.calibrar_callback=calibrar_callback;self.chat_callback=chat_callback
        self.soltar_callback=soltar_callback
        self.parar_callback=parar_callback
        self.habilitado=parent is None
        self.diagnostico_lock=threading.Lock()
        self.ui.geometry('820x450');self.ui.minsize(760,420)
        self.port=tk.StringVar(value='COM7');self.armado=tk.BooleanVar(value=False)
        self.events=queue.Queue();self.fin=threading.Event();self.owner=None;self.child=None
        self.lanzando=False;self.closed=False;self.cancelado=False
        self.recursos=None
        self.fallo_arranque=False
        ttk.Label(self.ui,text='Chatbot real · cuadro virtual delante',font=('Segoe UI',17,'bold')).pack(pady=12)
        ttk.Label(self.ui,text='Sin cámara. El modelo recibe el dibujo; las acciones usan encoders reales. Elige uno o ambos brazos.').pack()
        self.selector=ttk.Combobox(self.ui,textvariable=self.port,values=['COM7','COM8','Ambos'],state='readonly',width=16)
        self.selector.pack(pady=10)
        self.distancia=tk.StringVar();self.lado=tk.StringVar(value='COM7 a mi izquierda');self.montaje_ok=tk.BooleanVar(value=False)
        try:
            from .hardware.dual_usb import cargar_montaje
            m=cargar_montaje(root);self.distancia.set(str(m['distancia_mm']/10))
            self.lado.set('COM7 a mi izquierda' if m['com7_izquierda'] else 'COM7 a mi derecha');self.montaje_ok.set(True)
            self.port.set('Ambos')
        except (ValueError,OSError):pass
        mount=ttk.LabelFrame(self.ui,text='Solo para Ambos · colocación real de las bases');mount.pack(fill='x',padx=14,pady=4)
        ttk.Label(mount,text='Distancia entre centros (cm):').pack(side='left',padx=6)
        self.distance_entry=ttk.Entry(mount,textvariable=self.distancia,width=7);self.distance_entry.pack(side='left')
        self.side_selector=ttk.Combobox(mount,textvariable=self.lado,values=['COM7 a mi izquierda','COM7 a mi derecha'],state='readonly',width=24);self.side_selector.pack(side='left',padx=8)
        self.mount_check=ttk.Checkbutton(mount,text='Bases fijas, misma altura y orientadas en paralelo hacia delante',variable=self.montaje_ok);self.mount_check.pack(side='left')
        self.text=tk.Text(self.ui,height=9,wrap='word',font=('Segoe UI',11));self.text.pack(fill='both',expand=True,padx=14,pady=6)
        ttk.Checkbutton(self.ui,text='Preparado: recorrido libre y montaje comprobado; en modo individual, el otro brazo está apartado. Arrancar al estar listo.',
                        variable=self.armado).pack(anchor='w',padx=14,pady=6)
        ttk.Label(self.ui,text='En Ambos se permite una retirada inicial lenta hacia el interior, de hasta 3° por articulación, comprobada antes de activar. No busca topes ni cambia rangos.',wraplength=1000).pack(padx=14)
        row=ttk.Frame(self.ui);row.pack(pady=8)
        ttk.Button(row,text='Preparar y arrancar',command=self.preparar_un_boton).pack(side='left',padx=6)
        ttk.Button(row,text='Abrir alineación y pruebas',command=self.alinear).pack(side='left',padx=6)
        ttk.Button(row,text='Cancelar / detener',command=self.cancelar).pack(side='left',padx=6)
        ttk.Button(row,text='Soltar seleccionados (sujétalos)',command=self.soltar).pack(side='left',padx=6)
        ttk.Label(self.ui,text='Preparar y arrancar confirma que el otro brazo está apartado. Reutiliza la alineación guardada; solo se comprueba una vez por montaje.',wraplength=780).pack(padx=14,pady=8)
        self.hilo=threading.Thread(target=self._vigilar,daemon=True,name='preflight-solo-lectura');self.hilo.start()
        self.ui.after(100,self.poll);self.ui.protocol('WM_DELETE_WINDOW',self.cerrar)
        self.ui.bind('<Escape>',lambda e:self.cancelar())
    def mostrar(self,message):
        print(message,flush=True)
        self.text.delete('1.0','end');self.text.insert('end',message)
    def pausar(self):
        self.habilitado=False;self.armado.set(False)
        # Esperar a que el lector cierre el USB antes de prestarlo a otra pestaña.
        with self.diagnostico_lock:
            while not self.events.empty():self.events.get()

    def _vigilar(self):
        while not self.fin.is_set():
            with self.diagnostico_lock:
                if self.habilitado:self._diagnosticar()
            self.fin.wait(3)

    def _diagnosticar(self):
        from .hardware.chat_usb import incidencias
        if not self.fin.is_set():
            # Tk solo se consulta en el hilo principal: esta copia se publica en poll.
            port=getattr(self,'port_publicado','COM7')
            if self.habilitado and self.owner is None and not self.lanzando:
                if self.child is not None and self.child.poll() is None:
                    messages=['Termina y guarda la alineación en Pruebas. Después sujeta/suelta cualquier brazo activo y cierra esa ventana. Volveré a comprobar automáticamente.']
                else:
                    if port=='Ambos':
                        from .hardware.dual_usb import incidencias_dual
                        messages=incidencias_dual(self.root)
                    else:messages=incidencias(self.root,port)
                    try:
                        from .config import cargar
                        from .aplicacion_servicios import claves
                        cfg=cargar(self.root/'config/so101er.toml');keys=claves(cfg.conversacion.get('env'))
                        if not (keys['GEMINI_API_KEY'] or keys['GOOGLE_API_KEY']):messages.append('IA: configura GEMINI_API_KEY en el entorno o el .env indicado en conversacion.env')
                        if not keys['ELEVENLABS_API_KEY'] or not keys['ELEVENLABS_VOICE_ID']:messages.append('Voz: configura ELEVENLABS_API_KEY y ELEVENLABS_VOICE_ID en ese entorno o .env')
                    except Exception as e:messages.append('Configuración de servicios: '+str(e))
                self.events.put((port,messages))
    def preparar_un_boton(self):
        self.fallo_arranque=False
        if self.owner:self.mostrar('Ya hay un brazo activo. Sujétalo y suéltalo antes de preparar otro.');return
        try:
            from .hardware.chat_usb import datos_cal
            from .hardware.alineacion import Alineacion
            if self.port.get()=='Ambos':
                from .hardware.dual_usb import guardar_montaje
                guardar_montaje(self.root,self.distancia.get().replace(',','.'),self.lado.get()=='COM7 a mi izquierda',self.montaje_ok.get())
            alignment=True
            for port in ('COM7','COM8') if self.port.get()=='Ambos' else (self.port.get(),):
                cal=datos_cal(self.root,port)
                try:a=Alineacion.cargar(self.root,port,cal)
                except ValueError:a=None
                if a is None:alignment=None;break
            if alignment is None:
                self.armado.set(False)
                self.mostrar('Primera puesta en marcha: falta comprobar la referencia y los sentidos UNA VEZ. Abro el asistente sin par. Guarda la alineación y vuelve a Preparar y arrancar; después se reutiliza automáticamente.')
                self.alinear();return
            self.cancelado=False;self.armado.set(True)
            self.mostrar('Alineación guardada cargada. Comprobando USB, rangos y temperatura; el chatbot arrancará si todo está correcto.')
        except Exception as e:self.armado.set(False);self.mostrar(str(e))

    def alinear(self):
        if self.owner:self.mostrar('Sujeta y suelta primero el brazo activo.');return
        self.armado.set(False)
        if self.calibrar_callback:self.calibrar_callback('COM7' if self.port.get()=='Ambos' else self.port.get());return
        if self.child is not None and self.child.poll() is None:return
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
        self.child=subprocess.Popen([sys.executable,'-m','so101er.pruebas_modelo','--raiz',str(self.root)],env=env,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def cancelar(self):
        self.cancelado=True
        self.armado.set(False)
        if self.parar_callback:self.parar_callback()
        elif self.owner and not self.owner.native.closed:self.owner.native.parar()
        self.mostrar('Arranque cancelado. Si el brazo estaba activo mantiene par: sujétalo y pulsa Soltar.')
    def soltar(self):
        self.armado.set(False)
        if self.owner is None:
            self.pausar()
            try:
                from .hardware.dual_usb import recuperar_sin_par
                recuperar_sin_par(self.root,('COM7','COM8') if self.port.get()=='Ambos' else (self.port.get(),))
                self.mostrar('Par cero comprobado en los motores seleccionados. Puedes volver a preparar.')
            except Exception as e:self.mostrar('No se confirmó soltar: '+str(e))
            finally:self.habilitado=True
            return
        if self.owner:
            try:
                if not self.owner.native.closed:
                    if self.soltar_callback:self.soltar_callback()
                    else:self.owner.soltar()
                self.owner=None;self.lanzando=False;self.mostrar('Par desactivado. Puedes elegir el otro brazo.')
            except Exception as e:self.mostrar('No se confirmó la desactivación: '+str(e))
    def iniciar(self,port):
        self.lanzando=True;self.cancelado=False;self.armado.set(False)
        try:
            from .aplicacion import preparar_recursos
            self.mostrar('Cargando visor 3D, IA y referencias antes de activar motores…')
            self.ui.update_idletasks()
            if self.recursos is not None and not self.recursos.usado:self.recursos.vista.cerrar()
            self.recursos=preparar_recursos(self.root,port)
            from .hardware.chat_usb import BrazoChat
            if port=='Ambos':
                from .hardware.dual_usb import GrupoReal
                self.owner=GrupoReal(self.root);self.owner.activar()
            else:self.owner=BrazoChat(self.root,port)
            self.mostrar(port+': activado. Esperando, si hace falta, la pequeña entrada inicial suave. PARAR cancela.')
            self.ui.after(100,self.esperar_entrada)
        except Exception as e:
            if self.owner and self.owner.native.closed:self.owner=None
            self.fallo_arranque=True
            self.lanzando=False;self.mostrar('No se pudo iniciar: '+str(e)+'. Revisa el aviso; no se cambiarán límites automáticamente.')
    def esperar_entrada(self):
        if not self.owner:return
        if self.cancelado:self.mostrar('Arranque cancelado. Sujeta y pulsa Soltar antes de continuar.');return
        if self.owner.native.error:
            self.mostrar('DETENIDO: '+self.owner.native.error+'. Sujeta y pulsa Soltar.');return
        if self.owner.native.entrando:self.ui.after(100,self.esperar_entrada);return
        self.ui.after(100,self.abrir_chat)
    def abrir_chat(self):
        if not self.owner or self.cancelado:return
        if self.chat_callback:
            try:self.chat_callback(self.owner)
            except Exception as e:self.mostrar('No se pudo abrir el chatbot: '+str(e)+'. Sujeta y suelta si hay par.')
            return
        try:
            from .aplicacion import iniciar
            self.ui.withdraw()
            iniciar(self.root,real=True,brazo_real=self.owner,demo=False,recursos=self.recursos)
        except Exception as e:self.mostrar('Chatbot detenido: '+str(e)+'. Si el brazo está con par, sujétalo y pulsa Soltar.')
        finally:
            self.ui.deiconify();self.lanzando=False
            if self.owner and self.owner.native.closed:self.owner=None
    def poll(self):
        if self.closed:return
        self.port_publicado=self.port.get()
        self.selector.config(state='disabled' if self.owner or self.armado.get() else 'readonly')
        busy=bool(self.owner or self.armado.get())
        self.distance_entry.config(state='disabled' if busy else 'normal')
        self.side_selector.config(state='disabled' if busy else 'readonly')
        self.mount_check.config(state='disabled' if busy else 'normal')
        while not self.events.empty():
            port,messages=self.events.get()
            if not self.habilitado or port!=self.port.get() or self.owner or self.lanzando:continue
            if getattr(self,'fallo_arranque',False):continue
            self.mostrar('\n\n'.join(messages) if messages else port+': comprobaciones correctas. Pulsa Preparar y arrancar para abrir el chatbot real.')
            if not messages and self.armado.get():self.iniciar(port)
        self.ui.after(100,self.poll)
    def cerrar(self):
        self.armado.set(False)
        if self.owner and not self.owner.native.closed:
            self.owner.native.parar();self.mostrar('Sujeta el brazo y pulsa Soltar antes de cerrar.');return
        self.closed=True;self.fin.set();self.ui.destroy()
        if self.recursos is not None and not self.recursos.usado:self.recursos.vista.cerrar()
    def run(self):self.ui.mainloop()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raiz',default='.')
    Preparador(parser.parse_args().raiz).run()
