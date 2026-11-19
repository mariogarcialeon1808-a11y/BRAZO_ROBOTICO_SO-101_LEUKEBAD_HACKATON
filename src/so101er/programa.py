"""Programa único: rangos, alineación, preparación y conversación."""
import json
from pathlib import Path


class Programa:
    def __init__(self,root):
        import tkinter as tk
        from tkinter import ttk
        from .calibracion_usb import Asistente
        from .pruebas_modelo import Panel
        from .chatbot_real import Preparador
        self.root=Path(root);self.ui=tk.Tk();self.ui.title('SO-101 · Configuración y chatbot')
        self.ui.geometry('1280x980');self.ui.minsize(1100,850)
        self.closed=False;self.changing=False;self.current=0;self.session=None
        self.progress=tk.StringVar();self.notice=tk.StringVar(value='Empieza en 1. Rangos. Los motores no se activan durante la calibración manual.')
        ttk.Label(self.ui,text='SO-101 · Prepara los dos brazos paso a paso',font=('Segoe UI',17,'bold')).pack(pady=(10,2))
        ttk.Label(self.ui,textvariable=self.progress).pack(pady=3)
        top=ttk.Frame(self.ui);top.pack(fill='x',padx=14,pady=4)
        ttk.Label(top,textvariable=self.notice,wraplength=1000).pack(side='left',fill='x',expand=True)
        ttk.Button(top,text='PARAR',command=self.parar).pack(side='right')
        self.book=ttk.Notebook(self.ui);self.book.pack(fill='both',expand=True,padx=10,pady=6)
        self.pages=[ttk.Frame(self.book) for _ in range(4)]
        for page,title in zip(self.pages,('1 · Rangos','2 · Postura y alineación','3 · Preparar y probar','4 · Chatbot')):self.book.add(page,text=title)
        self.rangos=Asistente(root,abrir_modelo=False,parent=self.pages[0],autoconectar=False,guardado_callback=self.rangos_guardados)
        self.panel=Panel(root,parent=self.pages[1],abrir_rangos_callback=lambda:self.book.select(0))
        self.prep=Preparador(root,parent=self.pages[2],calibrar_callback=self.ir_alineacion,
                            chat_callback=self.abrir_chat,soltar_callback=self.soltar_chat,parar_callback=self.parar)
        ttk.Label(self.pages[3],text='El chatbot aparecerá aquí cuando termines la preparación de un brazo.\nVe a la pestaña 3 y pulsa Preparar y arrancar.',font=('Segoe UI',13),justify='center').pack(pady=70)
        self.book.bind('<<NotebookTabChanged>>',self.cambiar)
        self.ui.bind('<Escape>',lambda e:self.parar());self.ui.protocol('WM_DELETE_WINDOW',self.cerrar)
        # Se abre en la primera pestaña que de verdad hace falta: con rangos y postura guardados, la 3.
        inicial=self.pestana_inicial();self.current=inicial
        self.changing=True;self.book.select(inicial);self.changing=False
        self.activar(inicial);self.ui.after(500,self.actualizar_estado)

    def estado_guardado(self,port):
        """(pestaña que ese brazo necesita o None, texto) según lo que hay guardado. Solo lee archivos."""
        from .hardware.alineacion import Alineacion
        from .hardware.chat_usb import datos_cal
        try:cal=datos_cal(self.root,port)
        except Exception:return 0,port+': faltan los rangos (pestaña 1)'
        try:alineacion=Alineacion.cargar(self.root,port,cal)
        except Exception:return 1,port+': rangos guardados; repite la postura (pestaña 2)'
        if alineacion is None:return 1,port+': rangos guardados; falta la postura (pestaña 2)'
        return None,port+': rangos y postura guardados'

    def pestana_inicial(self):
        pendientes=[tab for tab,_ in map(self.estado_guardado,('COM7','COM8')) if tab is not None]
        return min(pendientes) if pendientes else 2

    def nativo_panel_activo(self):return self.panel.native is not None and not self.panel.native.closed
    def nativo_chat_activo(self):return self.prep.owner is not None and not self.prep.owner.native.closed

    def cambiar(self,event=None):
        if self.changing or self.closed:return
        target=self.book.index(self.book.select())
        if target==self.current:return
        blocked=(self.nativo_panel_activo() and target!=1) or (self.nativo_chat_activo() and target in (0,1))
        if blocked:
            self.notice.set('El brazo tiene par. Sujétalo y pulsa Soltar en la pestaña actual antes de ir a la calibración.')
            self.changing=True;self.book.select(self.current);self.changing=False;return
        if self.current==0 and self.rangos.monitor:
            self.rangos.monitor.cerrar();self.rangos.monitor=None
        if self.current==1:
            self.panel.dance=None
            if self.panel.monitor:self.panel.monitor.cerrar();self.panel.monitor=None
        self.prep.pausar()
        self.current=target;self.activar(target)

    def activar(self,index):
        from .hardware.calibracion import Monitor
        self.panel.visible=index==1
        if index==0:
            if self.rangos.monitor is None:self.rangos.monitor=Monitor()
            self.notice.set('1. Sin par: elige COM7 y un motor. Muévelo a mano por su recorrido. Repite con los 12 motores y guarda.')
        elif index==1:
            # Si cambiaron rangos, no reutilizar una transformación antigua.
            if self.panel.device.get()!='Simulación':
                from .hardware.alineacion import Alineacion
                try:self.panel.alignment=Alineacion.cargar(self.root,self.panel.device.get(),self.panel.cal_actual())
                except Exception as e:
                    self.panel.alignment=None;self.panel.draft=None;self.panel.edit.set(False);self.panel.status.set(str(e))
            if self.panel.edit.get() and self.panel.monitor is None:self.panel.monitor=Monitor()
            self.notice.set('2. La miniatura y la bolita azul indican la postura de referencia. Iguala el dibujo al brazo, captura, comprueba los sentidos a mano y guarda cada USB.')
        elif index==2:
            self.prep.habilitado=True
            if self.prep.owner and self.prep.owner.native.closed:self.prep.owner=None;self.prep.lanzando=False
            self.notice.set('3. Elige COM7, COM8 o Ambos. Para Ambos, registra la separación real de bases. Preparar y arrancar comprueba los datos guardados.')
        else:self.notice.set('4. Habla, escribe o prueba los bailes. PARAR detiene todos los brazos preparados; sujétalos antes de Soltar.')

    def rangos_guardados(self):
        self.notice.set('Rangos de los 12 motores guardados. Ahora comprobamos la postura en el modelo.')
        self.book.select(1)

    def ir_alineacion(self,port):
        self.prep.armado.set(False);self.book.select(1)
        if not self.nativo_panel_activo():
            self.panel.device.set(port);self.panel.cambiar_dispositivo()
            if self.panel.alignment is None:self.panel.q=self.panel.zero_reference.copy()

    def abrir_chat(self,owner):
        from .aplicacion import iniciar
        if self.session:
            if not self.session.liberado and not self.session.closed:raise RuntimeError('sujeta y suelta la sesión anterior')
            self.session.cerrar()
        for child in self.pages[3].winfo_children():child.destroy()
        self.session=iniciar(self.root,real=True,brazo_real=owner,parent=self.pages[3],recursos=self.prep.recursos)
        self.book.select(3)

    def soltar_chat(self):
        if self.session and not self.session.closed and not self.session.liberado:self.session.soltar_real()
        elif self.prep.owner:self.prep.owner.soltar()

    def parar(self):
        self.prep.armado.set(False);self.prep.cancelado=True;self.panel.dance=None
        if self.session and not self.session.closed:self.session.interrumpir()
        elif self.prep.owner and not self.prep.owner.native.closed:self.prep.owner.native.parar()
        if self.nativo_panel_activo():self.panel.parar()
        self.notice.set('Movimiento detenido. Si hay par, sujeta el brazo antes de pulsar Soltar. No se libera de improviso.')

    def actualizar_estado(self):
        if self.closed:return
        self.progress.set(' · '.join(self.estado_guardado(port)[1] for port in ('COM7','COM8')))
        self.ui.after(1000,self.actualizar_estado)

    def cerrar(self):
        if self.nativo_panel_activo() or self.nativo_chat_activo():self.parar();return
        self.closed=True
        if self.session:self.session.cerrar()
        self.rangos.cerrar();self.panel.cerrar();self.prep.cerrar();self.ui.destroy()

    def run(self):self.ui.mainloop()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raiz',default='.')
    parser.add_argument('--arrancar',action='store_true',help='Autoriza activar motores con el montaje guardado y abrir el chatbot')
    parser.add_argument('--brazo',choices=['COM7','COM8','Ambos'],default='Ambos')
    parser.add_argument('--demo',action='store_true',help='Con --arrancar: al abrir el chatbot lanza la demostración de cuatro frases')
    parser.add_argument('--velocidad',type=float,help='Con --arrancar: °/s de esta sesión (20–150), sin cambiar la configuración')
    args=parser.parse_args();programa=Programa(args.raiz)
    if args.arrancar:
        programa.prep.port.set(args.brazo);programa.book.select(2)
        programa.ui.after(800,programa.prep.preparar_un_boton)
        if args.demo or args.velocidad:
            def cuando_abra():
                s=programa.session
                if programa.closed or programa.prep.fallo_arranque or programa.prep.cancelado:return
                if s is None or s.closed:programa.ui.after(500,cuando_abra);return
                if args.velocidad:s.fijar_velocidad(args.velocidad)
                if args.demo:
                    from .aplicacion import demo_bloques
                    programa.ui.after(3000,lambda:s.enviar('',demo_bloques()))
            programa.ui.after(1500,cuando_abra)
    programa.run()
