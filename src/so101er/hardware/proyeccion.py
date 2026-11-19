"""Vista humana de encoders reales. Nunca es fuente de acciones ni percepción."""
import threading
import time


class Proyeccion:
    def __init__(self,cfg,imagen,brazos):
        import mujoco.viewer
        from .mujoco_sim import MundoMuJoCo
        self.world=MundoMuJoCo(cfg,list(brazos),imagen);self.brazos=brazos
        self.fin=threading.Event();self.usuario_cerro=False;self.error=None
        for n,b in brazos.items():self.world.colocar(n,b.leer_articulaciones())
        self.viewer=mujoco.viewer.launch_passive(self.world.modelo,self.world.datos,show_left_ui=False,show_right_ui=False)
        with self.viewer.lock():
            self.viewer.cam.lookat[:]=[0,.2,.3];self.viewer.cam.distance=1.5
            self.viewer.cam.azimuth=108;self.viewer.cam.elevation=-18
        self.hilo=threading.Thread(target=self._loop,daemon=True,name='solo-render-encoders');self.hilo.start()
    def _loop(self):
        try:
            while not self.fin.is_set():
                if not self.viewer.is_running():self.usuario_cerro=True;break
                # No se ejecuta la física ni se leen qpos/xpos para decidir acciones.
                with self.viewer.lock():
                    for n,b in self.brazos.items():self.world.colocar(n,b.leer_articulaciones())
                self.viewer.sync();self.fin.wait(.05)
        except Exception as e:self.error=str(e)  # Un fallo de render no decide acciones físicas.
        finally:self.fin.set()
    def cambiar_imagen(self,imagen):
        """Otra foto en el dibujo de la vista. No interviene en ninguna decisión."""
        if self.fin.is_set():return
        with self.viewer.lock():tex=self.world.cambiar_imagen(imagen)
        self.viewer.update_texture(tex)
    @property
    def cerrado(self):return self.usuario_cerro
    def cerrar(self):
        self.fin.set();self.hilo.join(2);self.viewer.close();self.world.cerrar()
