"""Ventana simple: elegir USB/motor, moverlo a mano y guardar sus rangos."""
from datetime import datetime,timezone
import json
from pathlib import Path
from .hardware.calibracion import Monitor,CapturaRangos,comprobar_muestra,guardar_atomicamente

NOMBRES=('1 · Giro de base','2 · Hombro','3 · Codo','4 · Inclinación muñeca','5 · Giro muñeca','6 · Pinza')


def cargar_guardados(root):
    """({puerto: brazo}, fecha) de los rangos completos guardados, o ({}, None) si no hay o no se leen."""
    try:data=json.loads((Path(root)/'config/calibracion_rangos_usb.json').read_text(encoding='utf8'))
    except (OSError,ValueError):return {},None
    try:
        brazos={b['puerto']:b for b in data['brazos'] if set(b['rangos'])==set(map(str,range(1,7)))}
        fecha=datetime.fromisoformat(data['fecha_utc']).astimezone().strftime('%d-%m-%Y a las %H:%M')
    except (KeyError,TypeError,ValueError):return {},None
    return brazos,fecha


class Asistente:
    def __init__(self,root,abrir_modelo=True,parent=None,autoconectar=True,guardado_callback=None):
        import tkinter as tk
        from tkinter import ttk
        self.root=Path(root);self.tk=tk;self.ttk=ttk;self.closed=False;self.abrir_modelo=abrir_modelo
        self.guardado_callback=guardado_callback
        from .interfaz.embebido import ventana
        self.ui=ventana(parent);self.ui.title('SO-101 · Calibración manual · Rangos USB')
        self.ui.geometry('800x640');self.ui.minsize(720,580)
        self.monitor=Monitor() if autoconectar else None;self.samples={};self.capturas={};self.inicio_mostrado=False
        # Los rangos guardados se cargan al abrir: no hay que recorrerlos otra vez. Un motor con rango
        # guardado no se vuelve a registrar hasta que se pide con «Reiniciar rango de este motor».
        self.guardados,self.fecha_guardada=cargar_guardados(root);self.congelados=set();self.no_valen={}
        self.port=tk.StringVar();self.motor=tk.StringVar(value=NOMBRES[0])
        self.status=tk.StringVar(value='Buscando los dos USB…')
        ttk.Label(self.ui,text='Mueve a mano el motor seleccionado',font=('Segoe UI',16,'bold')).pack(pady=(12,5))
        ttk.Label(self.ui,text='Los motores deben estar sueltos: mueve el brazo a mano. Aquí el programa solo lee.').pack()
        self.progreso=tk.StringVar(value='0 de 12 motores recorridos')
        ttk.Label(self.ui,textvariable=self.progreso).pack(pady=2)
        row=ttk.Frame(self.ui);row.pack(fill='x',padx=18,pady=12)
        ttk.Label(row,text='Brazo / USB').pack(side='left',padx=(0,8))
        self.ports=ttk.Combobox(row,textvariable=self.port,state='readonly',width=12)
        self.ports.pack(side='left',padx=(0,20))
        ttk.Label(row,text='Motor').pack(side='left',padx=(0,8))
        self.motors=ttk.Combobox(row,textvariable=self.motor,values=NOMBRES,state='readonly',width=25)
        self.motors.pack(side='left')
        ttk.Label(self.ui,text='Recorre despacio su rango a mano, sin forzar los topes.\nSe registran los extremos solo del motor seleccionado. Cambia de motor y repite.',
                  font=('Segoe UI',11),justify='center').pack(pady=4)
        self.position=ttk.Label(self.ui,text='—',font=('Consolas',30,'bold'));self.position.pack(pady=4)
        self.info=ttk.Label(self.ui,text='Esperando lecturas');self.info.pack()
        self.bar=tk.Canvas(self.ui,width=700,height=48,background='#f4f5f6',highlightthickness=0)
        self.bar.pack(padx=18,pady=8,fill='x')
        columns=('usb','motor','min','max','recorrido','estado')
        self.table=ttk.Treeview(self.ui,columns=columns,show='headings',height=12,selectmode='browse')
        for c,label,width in zip(columns,('USB','Motor','Mínimo','Máximo','Recorrido (°)','Estado'),(65,190,85,85,110,170)):
            self.table.heading(c,text=label);self.table.column(c,width=width,anchor='center')
        self.table.pack(fill='both',expand=True,padx=18,pady=6)
        self.table.bind('<<TreeviewSelect>>',self.seleccionar_fila)
        buttons=ttk.Frame(self.ui);buttons.pack(pady=8)
        ttk.Button(buttons,text='Reiniciar rango de este motor',command=self.reiniciar).pack(side='left',padx=8)
        ttk.Button(buttons,text='Guardar rangos',command=self.guardar).pack(side='left',padx=8)
        ttk.Label(self.ui,text='Un brazo cada vez. Mantén las pinzas separadas. Los gestos automáticos no se activan aquí.',
                  foreground='#8e4b00',wraplength=750).pack(padx=18)
        ttk.Label(self.ui,textvariable=self.status,wraplength=750).pack(fill='x',padx=18,pady=(6,12))
        self.ui.protocol('WM_DELETE_WINDOW',self.cerrar);self.ui.after(100,self.poll)

    def indice(self):return NOMBRES.index(self.motor.get())

    def seleccionar_fila(self,event):
        selection=self.table.selection()
        if selection:
            port,index=selection[0].rsplit('_',1)
            self.port.set(port);self.motor.set(NOMBRES[int(index)])

    def reiniciar(self):
        capture=self.capturas.get(self.port.get())
        if capture:
            capture.reiniciar(self.indice());self.congelados.discard((self.port.get(),self.indice()))
            self.status.set('Rango reiniciado para el motor seleccionado: recórrelo de extremo a extremo y pulsa Guardar rangos.')

    def precargar(self,capture):
        """Pone en una captura recién abierta los rangos guardados de ese brazo, si siguen valiendo."""
        saved=self.guardados.get(capture.puerto)
        if not saved:return
        if saved.get('serie_usb')!=capture.serie or saved.get('identidad_servos')!=capture.meta:
            # Otro adaptador en ese puerto, o servos con offset o límites internos distintos: esos rangos ya no describen este brazo.
            self.no_valen[capture.puerto]='los rangos guardados son de otro adaptador o de servos con otros ajustes internos; hay que recorrerlos de nuevo'
            return
        for key,r in saved['rangos'].items():
            capture.rangos[int(key)-1]={**r,'ultimo_t':None,'ultimo_raw':None}
            self.congelados.add((capture.puerto,int(key)-1))

    def sin_conectar(self):
        """Brazos con rangos guardados cuyo USB no está conectado ahora: se conservan tal cual."""
        return {port:b for port,b in getattr(self,'guardados',{}).items() if port not in self.capturas}

    def hay_cambios(self):
        """True si algún motor se ha vuelto a recorrer, o se ha reiniciado, respecto a lo guardado."""
        return any(set(c.rangos)!={i for p,i in self.congelados if p==port} or len(c.rangos)!=6 for port,c in self.capturas.items())

    def documento(self):
        return {'version':1,'fecha_utc':datetime.now(timezone.utc).isoformat(),
                'verificada':False,'montaje_verificado':False,
                'metodo':'extremos de encoders movidos manualmente, sin escrituras de motor',
                'aviso':'Rangos observados; falta comprobar referencia URDF, sentidos y montaje antes de gestos automáticos.',
                'brazos':[capture.exportar() for capture in self.capturas.values()]+list(self.sin_conectar().values())}

    def guardar(self):
        try:
            if not self.capturas:raise ValueError('todavía no hay lecturas USB')
            resto=Asistente.sin_conectar(self)
            if getattr(self,'congelados',None) and not Asistente.hay_cambios(self):
                self.status.set('No hay nada nuevo que guardar: los rangos guardados siguen valiendo. Para repetir un motor, elígelo y pulsa «Reiniciar rango de este motor».')
                return
            completos=len(self.capturas)+len(resto)==2 and all(len(c.rangos)==6 and
                        all(r['max_raw']-r['min_raw']>=150 for r in c.rangos.values()) for c in self.capturas.values())
            count=sum(sum(r['max_raw']-r['min_raw']>=150 for r in c.rangos.values()) for c in self.capturas.values())+6*len(resto)
            target=self.root/'config'/('calibracion_rangos_usb.json' if completos else 'calibracion_rangos_usb.borrador.json')
            guardar_atomicamente(target,self.documento())
            if completos and hasattr(self,'congelados'):
                # Lo recién guardado pasa a ser «lo guardado»: ya no se registra más hasta que se pida.
                self.guardados,self.fecha_guardada=cargar_guardados(self.root)
                self.congelados={(port,i) for port,c in self.capturas.items() for i in c.rangos}
            self.status.set(f'Guardados {count}/12 motores. '+('Rangos listos para alinear.' if completos else 'Es progreso parcial: termina los otros motores. No se sustituyen los rangos completos anteriores.'))
            if completos and self.guardado_callback:self.guardado_callback();return
            if completos and self.abrir_modelo:
                import subprocess,sys,os
                env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
                self.monitor.cerrar()
                subprocess.Popen([sys.executable,'-m','so101er.pruebas_modelo','--raiz',str(self.root)],
                                 env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.cerrar()
        except Exception as e:self.status.set('No se pudo guardar: '+str(e))

    def poll(self):
        if self.closed:return
        if self.monitor is None:
            self.info.config(text='Lectura pausada: vuelve a esta pestaña para registrar rangos.')
            self.ui.after(100,self.poll);return
        self.samples,errors=self.monitor.leer()
        names=sorted(self.samples);self.ports.config(values=names)
        if not self.port.get() and names:self.port.set(names[0])
        for port,sample in self.samples.items():
            capture=self.capturas.get(port)
            if capture is None:
                capture=self.capturas[port]=CapturaRangos(port,sample['serie'],sample['identidad']);self.precargar(capture)
        sample=self.samples.get(self.port.get());i=self.indice()
        if sample:
            try:
                comprobar_muestra(sample);capture=self.capturas[self.port.get()]
                if (self.port.get(),i) not in self.congelados:capture.observar(i,sample)   # un rango guardado no se toca
                self.position.config(text=str(sample['raw'][i]))
                self.info.config(text=f"{self.port.get()} · serie {sample['serie']} · {sample['temperaturas'][i]} °C · PAR DESACTIVADO")
                r=capture.rangos[i];width=max(100,self.bar.winfo_width()-40)
                x=lambda raw:20+raw/4095*width
                self.bar.delete('all');self.bar.create_line(20,24,20+width,24,fill='#c8c8c8',width=8)
                self.bar.create_line(x(r['min_raw']),24,x(r['max_raw']),24,fill='#41a66c',width=10)
                self.bar.create_oval(x(sample['raw'][i])-5,18,x(sample['raw'][i])+5,30,fill='#d88218',outline='')
                self.bar.create_text(20,43,text='0');self.bar.create_text(20+width,43,text='4095')
            except Exception as e:self.info.config(text='REGISTRO DETENIDO: '+str(e));self.position.config(text='—')
        else:
            self.info.config(text='USB no disponible; no se registran valores antiguos.');self.position.config(text='—')
        for port,capture in self.capturas.items():
            for j in range(6):
                r=capture.rangos.get(j);key=f'{port}_{j}'
                estado='—' if not r else 'guardado' if (port,j) in self.congelados else 'recorrido ahora, sin guardar'
                values=(port,NOMBRES[j],r['min_raw'] if r else '—',r['max_raw'] if r else '—',
                        round((r['max_raw']-r['min_raw'])*360/4096,1) if r else '—',estado)
                if self.table.exists(key):self.table.item(key,values=values)
                else:self.table.insert('','end',iid=key,values=values)
        resto=self.sin_conectar()
        for port,saved in resto.items():                      # guardado, pero con su USB sin conectar ahora
            for j in range(6):
                r=saved['rangos'][str(j+1)];key=f'{port}_{j}'
                values=(port,NOMBRES[j],r['min_raw'],r['max_raw'],round((r['max_raw']-r['min_raw'])*360/4096,1),'guardado · USB sin conectar')
                if self.table.exists(key):self.table.item(key,values=values)
                else:self.table.insert('','end',iid=key,values=values)
        count=sum(sum(r['max_raw']-r['min_raw']>=150 for r in c.rangos.values()) for c in self.capturas.values())+6*len(resto)
        previos=len(self.congelados)+6*len(resto)
        if count==12 and previos==12:
            self.progreso.set(f'12 de 12 motores con rango guardado el {self.fecha_guardada}. No hace falta recorrerlos otra vez.')
        else:
            self.progreso.set(f'{count} de 12 motores con rango'+(f' ({previos} guardados de antes)' if previos else '')+' · termina los 6 de COM7 y los 6 de COM8')
        if errors:self.status.set('USB: '+'; '.join(f'{k}: {v}' for k,v in errors.items()))
        elif not self.capturas:self.status.set('Buscando los dos USB… Si no aparecen, cierra y vuelve a abrir esta ventana.')
        elif not self.inicio_mostrado:
            if self.no_valen:self.status.set(' '.join(f'{port}: {motivo}.' for port,motivo in self.no_valen.items()))
            elif previos:self.status.set('Rangos guardados cargados. Para repetir uno, elige el motor, pulsa «Reiniciar rango de este motor», recórrelo y guarda.')
            else:self.status.set('Elige brazo y motor, muévelo a mano y pulsa Guardar cuando termines.')
            self.inicio_mostrado=True
        self.ui.after(100,self.poll)

    def cerrar(self):
        if self.closed:return
        self.closed=True
        if self.monitor:self.monitor.cerrar()
        self.ui.destroy()

    def run(self):self.ui.mainloop()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raiz',default='.')
    parser.add_argument('--solo-rangos',action='store_true')
    args=parser.parse_args();Asistente(args.raiz,abrir_modelo=not args.solo_rangos).run()
