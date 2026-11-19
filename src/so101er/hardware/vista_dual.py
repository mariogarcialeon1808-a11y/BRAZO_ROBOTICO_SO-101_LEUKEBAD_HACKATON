"""Render conjunto de poses calculadas desde encoders. Sin física ni feedback."""
class VistaDual:
    def __init__(self,cfg,imagen):
        import mujoco as mj
        from .mujoco_sim import MundoMuJoCo
        self.world=MundoMuJoCo(cfg,['izq','der'],imagen)
        self.renderer=mj.Renderer(self.world.modelo,480,640)
        self.camera=mj.MjvCamera();self.camera.lookat[:]=[0,.15,.22]
        self.camera.distance=max(1.2,cfg.brazos['der'].base_mm[0]/1000*3)
        self.camera.azimuth=110;self.camera.elevation=-22
    def foto(self,poses):
        import cv2
        for n,q in poses.items():self.world.colocar(n,q)
        self.renderer.update_scene(self.world.datos,camera=self.camera)
        return cv2.cvtColor(self.renderer.render(),cv2.COLOR_RGB2BGR)
    def cambiar_imagen(self,imagen):
        """Otra foto en el dibujo. Llamar desde el mismo hilo que `foto`."""
        import mujoco as mj
        from .mujoco_sim import subir_textura
        subir_textura(mj,self.renderer,self.world.modelo,self.world.cambiar_imagen(imagen))
    def cerrar(self):self.renderer.close();self.world.cerrar()
