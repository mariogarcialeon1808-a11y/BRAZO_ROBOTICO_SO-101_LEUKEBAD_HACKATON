"""Simulación en MuJoCo: los brazos SO-101 oficiales, la obra con textura y tres cámaras.

La física corre en tiempo real, sin contactos (el solver va rápido). Los
brazos se mueven con los actuadores de posición del modelo oficial, que
imitan a los servos STS3215: lo que se ve es cómo seguiría un brazo real
las consignas del sistema.

Cámaras (lo que ve ER 2):
- "fija": entre los dos brazos, mirando a la obra. Los puntos [y, x] se dan en ella.
- "muneca_izq" / "muneca_der": la cámara integrada en la muñeca de cada brazo.
Sin marcadores privilegiados sobre las imágenes que recibe el actor.
"""
from __future__ import annotations

import math
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..cinematica.modelo import ARTICULACIONES
from ..config import Config

DIR_MODELO = Path(__file__).resolve().parents[1] / "mujoco_modelo"
NOMBRES = ARTICULACIONES + ("gripper",)
PINZA_RAD = (-0.174533, 1.74533)
COLOR_PUNTERO = {"izq": [1.0, 0.55, 0.1, 1.0], "der": [0.2, 0.95, 0.3, 1.0]}
ANCHO, ALTO, FOVY_FIJA, FOVY_MUNECA = 640, 480, 50.0, 70.0


class ErrorMuJoCo(RuntimeError):
    pass


def _mujoco() -> Any:
    try:
        import mujoco
        return mujoco
    except ImportError:
        raise ErrorMuJoCo("Falta MuJoCo. Instálalo con: pip install -e \".[mujoco]\"") from None


def _quat(mj: Any, ex: np.ndarray, ey: np.ndarray, ez: np.ndarray) -> np.ndarray:
    q = np.zeros(4)
    mj.mju_mat2Quat(q, np.column_stack([ex, ey, ez]).flatten())
    return q


def subir_textura(mj: Any, renderer: Any, modelo: Any, tex: int) -> None:
    """Vuelve a subir una textura cambiada al contexto gráfico de un `Renderer` (desde su hilo)."""
    renderer._gl_context.make_current()
    mj.mjr_uploadTexture(modelo, renderer._mjr_context, tex)


def _camara_de_muneca(mj: Any) -> tuple[np.ndarray, np.ndarray]:
    """Posición y orientación de la cámara de muñeca en el cuerpo de la pinza.

    Está donde el modelo oficial coloca la cámara y mira a lo largo de la herramienta."""
    # Montaje óptico nominal, independiente de la pose del solver.
    return np.array([0.0, -0.025, -0.065]), np.array([1.0, 0.0, 0.0, 0.0])


class MundoMuJoCo:
    def __init__(self, cfg: Config, nombres: list[str], imagen: np.ndarray) -> None:
        mj = self.mj = _mujoco()
        self.cfg, self.nombres = cfg, nombres
        self.cerrojo = threading.Lock()
        escena = mj.MjSpec()
        escena.option.timestep = 0.002
        escena.option.disableflags |= int(mj.mjtDisableBit.mjDSBL_CONTACT)      # sin contactos
        escena.visual.global_.azimuth, escena.visual.global_.elevation = 110, -18
        escena.visual.global_.offwidth, escena.visual.global_.offheight = ANCHO, ALTO
        escena.visual.headlight.ambient = [0.45, 0.45, 0.45]
        escena.visual.headlight.diffuse = [0.7, 0.7, 0.7]
        escena.stat.center = [0.0, 0.25, 0.3]
        escena.stat.extent = 0.9

        # La obra: la foto como textura, con la cara vista hacia los brazos.
        self._tmp = tempfile.TemporaryDirectory(prefix="so101er_")
        ruta_tex = Path(self._tmp.name) / "obra.png"
        alto, ancho = imagen.shape[:2]
        escala = 1024 / max(alto, ancho)
        cv2.imwrite(str(ruta_tex), cv2.resize(imagen, (max(int(ancho * escala), 2), max(int(alto * escala), 2))))
        escena.add_texture(name="obra", type=mj.mjtTexture.mjTEXTURE_2D, file=str(ruta_tex))
        material = escena.add_material(name="obra")
        material.textures[int(mj.mjtTextureRole.mjTEXROLE_RGB)] = "obra"
        c = cfg.cuadro
        self._origen = c.sup_izq / 1000.0
        self._u, self._v = (c.sup_der - c.sup_izq) / 1000.0, (c.inf_izq - c.sup_izq) / 1000.0
        ex, ey = self._u / np.linalg.norm(self._u), -self._v / np.linalg.norm(self._v)
        ez = self._normal = np.cross(ex, ey)
        quat = _quat(mj, ex, ey, ez)
        centro = self._centro = self._origen + 0.5 * self._u + 0.5 * self._v
        medio = [float(np.linalg.norm(self._u)) / 2, float(np.linalg.norm(self._v)) / 2]
        escena.worldbody.add_geom(name="obra", type=mj.mjtGeom.mjGEOM_BOX, size=[medio[0], medio[1], 0.004],
                                  pos=centro - ez * 0.005, quat=quat, material="obra")
        escena.worldbody.add_geom(name="marco", type=mj.mjtGeom.mjGEOM_BOX,
                                  size=[medio[0] + 0.02, medio[1] + 0.02, 0.006],
                                  pos=centro - ez * 0.016, quat=quat, rgba=[0.25, 0.17, 0.1, 1])
        escena.worldbody.add_geom(name="mesa", type=mj.mjtGeom.mjGEOM_BOX, size=[0.6, 0.45, 0.01],
                                  pos=[0, 0.2, -0.011], rgba=[0.32, 0.3, 0.28, 1])
        escena.worldbody.add_light(pos=[0, -0.5, 1.6], dir=[0, 0.5, -1])

        # Cámara fija: entre los brazos, mirando al centro de la obra.
        bases = np.mean([cfg.brazos[n].base_mm for n in nombres], axis=0) / 1000.0
        self._cam_pos = np.array([bases[0], bases[1], centro[2]]) + ez * 0.14
        adelante = centro - self._cam_pos
        adelante /= np.linalg.norm(adelante)
        derecha = np.cross(adelante, ey)
        derecha /= np.linalg.norm(derecha)
        arriba = np.cross(derecha, adelante)
        self._cam_rot = np.column_stack([derecha, arriba, -adelante])
        escena.worldbody.add_camera(name="fija", pos=self._cam_pos, quat=_quat(mj, derecha, arriba, -adelante),
                                    fovy=FOVY_FIJA)

        # Punteros: una marca de color sobre la obra donde apunta cada brazo.
        for n in nombres:
            cuerpo = escena.worldbody.add_body(name=f"puntero_{n}", mocap=True, pos=[0, 0, -1])
            cuerpo.add_geom(type=mj.mjtGeom.mjGEOM_SPHERE, size=[0.011, 0, 0], rgba=COLOR_PUNTERO[n])

        pos_cam, quat_cam = _camara_de_muneca(mj)
        for n in nombres:
            brazo = mj.MjSpec.from_file(str(DIR_MODELO / "so101_new_calib_camera.xml"))
            brazo.body("gripper").add_camera(name="muneca", pos=pos_cam, quat=quat_cam, fovy=FOVY_MUNECA)
            b = cfg.brazos[n]
            a = math.radians(b.orientacion_grados) / 2
            marco = escena.worldbody.add_frame(pos=b.base_mm / 1000.0, quat=[math.cos(a), 0, 0, math.sin(a)])
            escena.attach(brazo, prefix=f"{n}_", frame=marco)
        for n in nombres:
            for j in NOMBRES:
                escena.add_sensor(name=f"encoder_{n}_{j}", type=mj.mjtSensor.mjSENS_JOINTPOS,
                                  objtype=mj.mjtObj.mjOBJ_JOINT, objname=f"{n}_{j}")
        self.modelo = escena.compile()
        self.datos = mj.MjData(self.modelo)
        from .sensores import Encoders
        self._encoders = {n: Encoders(i+1) for i,n in enumerate(nombres)}
        self._sensores = {n: [self.modelo.sensor(f"encoder_{n}_{j}").adr[0] for j in NOMBRES]
                          for n in nombres}
        self._qpos, self._ctrl, self._sitio, self._mocap, self._pinza = {}, {}, {}, {}, {}
        for n in nombres:
            self._qpos[n] = [self.modelo.joint(f"{n}_{j}").qposadr[0] for j in NOMBRES]
            self._ctrl[n] = [self.modelo.actuator(f"{n}_{j}").id for j in NOMBRES]
            self._sitio[n] = self.modelo.site(f"{n}_gripperframe").id
            self._pinza[n] = self.modelo.body(f"{n}_gripper").id
            self._mocap[n] = int(self.modelo.body(f"puntero_{n}").mocapid[0])
        self.camaras = ["fija"] + [f"{n}_muneca" for n in nombres]
        # Las consignas llegan a 100 Hz; la física va a 500 Hz. Sin suavizar, cada escalón satura
        # el actuador (es muy rígido) y la carga instantánea no significa nada.
        self._objetivo = np.zeros(self.modelo.nu)

        self.visor: Any = None
        self._fin = threading.Event()
        self._hilo: threading.Thread | None = None
        self._hilo_camaras: threading.Thread | None = None
        self._render: Any = None
        self._fotos: dict[str, np.ndarray] = {}
        self._foto_pedida, self._foto_lista = threading.Event(), threading.Event()
        self.saltos = 0                 # veces que la física no ha podido seguir el tiempo real
        self.subtitulo = ""

    # ------------------------------------------------------------ conversión
    @staticmethod
    def a_rad(q: np.ndarray) -> np.ndarray:
        r = np.radians(q[:6].astype(float))
        r[5] = PINZA_RAD[0] + (PINZA_RAD[1] - PINZA_RAD[0]) * float(np.clip(q[5], 0, 100)) / 100.0
        return r

    @staticmethod
    def a_grados(r: np.ndarray) -> np.ndarray:
        q = np.degrees(r)
        q[5] = (r[5] - PINZA_RAD[0]) / (PINZA_RAD[1] - PINZA_RAD[0]) * 100.0
        return q

    def colocar(self, nombre: str, q: np.ndarray) -> None:
        """Pone un brazo en una pose (sin física): pose inicial."""
        with self.cerrojo:
            r = self.a_rad(q)
            self.datos.qpos[self._qpos[nombre]] = r
            self.datos.ctrl[self._ctrl[nombre]] = r
            self._objetivo[self._ctrl[nombre]] = r
            self.mj.mj_forward(self.modelo, self.datos)
            self._encoders[nombre].history.clear()
            self._encoders[nombre].last = -1e9
            self._adquirir_sensores()
            self._punteros()

    # ------------------------------------------------------------ cámaras
    def homografia_fija(self) -> np.ndarray:
        """Imagen de la cámara fija (x, y en 0–1000) → obra normalizada (0–1)."""
        f = 0.5 * ALTO / math.tan(math.radians(FOVY_FIJA) / 2)
        esquinas = [self._origen, self._origen + self._u, self._origen + self._u + self._v, self._origen + self._v]
        pix = []
        for p in esquinas:
            pc = self._cam_rot.T @ (p - self._cam_pos)
            pix.append([(ANCHO / 2 + f * pc[0] / -pc[2]) / ANCHO * 1000.0, (ALTO / 2 - f * pc[1] / -pc[2]) / ALTO * 1000.0])
        return cv2.getPerspectiveTransform(np.array(pix, np.float32),
                                           np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32))

    def cambiar_imagen(self, imagen: np.ndarray) -> int:
        """Cambia la foto de la obra en la escena ya compilada. Solo es dibujo: no toca la física.

        La textura conserva su tamaño, así que la imagen debe traer la proporción del cuadro.
        Devuelve el número de textura, para que quien dibuja la suba a su tarjeta gráfica.
        """
        mj, m = self.mj, self.modelo
        tex = mj.mj_name2id(m, mj.mjtObj.mjOBJ_TEXTURE, "obra")
        if tex < 0 or int(m.tex_nchannel[tex]) != 3:
            raise ErrorMuJoCo("la escena no tiene una textura de obra que se pueda cambiar")
        alto, ancho = int(m.tex_height[tex]), int(m.tex_width[tex])
        rgb = cv2.cvtColor(cv2.resize(imagen, (ancho, alto), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        inicio = int(m.tex_adr[tex])
        with self.cerrojo:
            m.tex_data[inicio:inicio + alto * ancho * 3] = rgb.ravel()
        if self.visor is not None:
            self.visor.update_texture(tex)
        if self._render is not None and self._hilo_camaras is None:
            subir_textura(mj, self._render, m, tex)
        return tex

    def _punteros(self) -> None:
        """Coloca la marca de cada brazo donde su herramienta corta el plano de la obra."""
        # No se dibujan marcas derivadas del estado privilegiado sobre imágenes del actor.
        return

    def _adquirir_sensores(self):
        for n, sensor in self._encoders.items():
            sensor.adquirir(float(self.datos.time), self.a_grados(self.datos.sensordata[self._sensores[n]]))
    def capturar(self) -> dict[str, np.ndarray]:
        """Toma una imagen (BGR) de cada cámara. Debe llamarse siempre desde el mismo hilo."""
        if self._render is None:
            self._render = self.mj.Renderer(self.modelo, ALTO, ANCHO)
        fotos = {}
        for nombre in self.camaras:
            with self.cerrojo:
                self._render.update_scene(self.datos, camera=nombre)
            fotos[nombre] = cv2.cvtColor(self._render.render(), cv2.COLOR_RGB2BGR)
        self._fotos = fotos
        return fotos

    def fotos(self) -> dict[str, np.ndarray]:
        """Imágenes de las cámaras, tomadas ahora. Con hilo de cámaras, se las pide a él (el
        dibujo debe hacerse siempre en el mismo hilo); sin él, las toma quien llama."""
        if self._hilo_camaras is None:
            return self.capturar()
        self._foto_lista.clear()
        self._foto_pedida.set()
        self._foto_lista.wait(timeout=2.0)
        return self._fotos or self.capturar()

    def _bucle_camaras(self) -> None:
        # Solo se dibuja cuando se pide una imagen: dibujar sin parar cargaba el equipo.
        while not self._fin.is_set():
            if not self._foto_pedida.wait(timeout=0.3):
                continue
            self._foto_pedida.clear()
            try:
                self.capturar()
            except Exception:
                pass
            self._foto_lista.set()
        self._render = None

    # ------------------------------------------------------------ tiempo real
    def iniciar(self, ventana: bool = True, camaras: bool = False) -> None:
        if ventana:
            import mujoco.viewer
            self.visor = mujoco.viewer.launch_passive(self.modelo, self.datos, show_left_ui=False,
                                                      show_right_ui=False)
            with self.visor.lock():
                self.visor.cam.lookat[:] = [0.0, 0.25, 0.3]
                self.visor.cam.distance, self.visor.cam.azimuth, self.visor.cam.elevation = 1.65, 108, -16
        self._fin.clear()
        self._hilo = threading.Thread(target=self._bucle, name="mujoco", daemon=True)
        self._hilo.start()
        if camaras:
            self._hilo_camaras = threading.Thread(target=self._bucle_camaras, name="camaras", daemon=True)
            self._hilo_camaras.start()

    def paso_fisico(self) -> None:
        """Un paso de la física (llamar con el cerrojo tomado)."""
        d, paso = self.datos, self.modelo.opt.timestep
        d.ctrl[:] += (self._objetivo - d.ctrl) * min(1.0, paso / 0.012)
        self.mj.mj_step(self.modelo, d)
        self._adquirir_sensores()

    def _bucle(self) -> None:
        mj, paso = self.mj, self.modelo.opt.timestep
        t_sim, t0 = 0.0, time.perf_counter()
        texto_previo = None
        while not self._fin.is_set():
            real = time.perf_counter() - t0
            if real - t_sim > 0.25:               # tras un bloqueo: no intentar recuperar
                t_sim = real - 0.02
                self.saltos += 1
            with self.cerrojo:
                while t_sim < real:
                    self.paso_fisico()
                    t_sim += paso
                self._punteros()
            if self.visor is not None:
                if not self.visor.is_running():
                    self._fin.set()
                    break
                if self.subtitulo != texto_previo and hasattr(self.visor, "set_texts"):
                    try:
                        self.visor.set_texts((mj.mjtFontScale.mjFONTSCALE_150, mj.mjtGridPos.mjGRID_BOTTOM,
                                              self.subtitulo, ""))
                    except Exception:
                        pass
                    texto_previo = self.subtitulo
                self.visor.sync()
            time.sleep(0.008)

    @property
    def cerrado(self) -> bool:
        return self._fin.is_set()

    def cerrar(self) -> None:
        self._fin.set()
        for hilo in (self._hilo, self._hilo_camaras):
            if hilo is not None:
                hilo.join(timeout=1.5)
        if self.visor is not None:
            try:
                self.visor.close()
            except Exception:
                pass

    def brazo(self, nombre: str, q_inicial: np.ndarray) -> "BrazoMuJoCo":
        self.colocar(nombre, q_inicial)
        return BrazoMuJoCo(self, nombre)


class BrazoMuJoCo:
    """Un brazo de la escena de MuJoCo, con la misma interfaz que el real."""

    def __init__(self, mundo: MundoMuJoCo, nombre: str) -> None:
        self.mundo, self.nombre = mundo, nombre
        self._par = True
        self.telemetria_carga = False
        self.telemetria_temperatura = False
        # En simulación, si el equipo va cargado la física se retrasa: no es un brazo bloqueado.
        self.tiempo_error_s = 1.5

    def conectar(self) -> None:
        self._par = True

    def desconectar(self) -> None:
        pass

    def activar_par(self) -> None:
        self.enviar_objetivo(self.leer_articulaciones())
        self._par = True

    def desactivar_par(self) -> None:
        self._par = False

    def leer_articulaciones(self) -> np.ndarray:
        m = self.mundo
        with m.cerrojo:
            return m._encoders[self.nombre].leer(float(m.datos.time))

    def enviar_objetivo(self, q: np.ndarray) -> None:
        if not self._par:
            return
        m = self.mundo
        r = m.a_rad(np.asarray(q, float))
        with m.cerrojo:
            m._objetivo[m._ctrl[self.nombre]] = r

    def leer_carga(self) -> np.ndarray:
        m = self.mundo
        with m.cerrojo:
            raise NotImplementedError("sin sensor de carga equivalente calibrado")

    def leer_temperatura(self) -> np.ndarray:
        raise NotImplementedError("sin termómetro simulado equivalente")


class CamaraMuJoCo:
    """Las tres cámaras de la escena, en el formato que usan los agentes."""

    def __init__(self, mundo: MundoMuJoCo) -> None:
        self.mundo = mundo

    @staticmethod
    def _jpeg(img: np.ndarray, ancho: int | None = None) -> bytes:
        if ancho and img.shape[1] != ancho:
            img = cv2.resize(img, (ancho, int(img.shape[0] * ancho / img.shape[1])))
        ok, datos = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            raise RuntimeError("no se pudo codificar el fotograma")
        return datos.tobytes()

    def jpeg(self) -> bytes:
        """Imagen de la cámara fija (la que ve también el guía)."""
        return self._jpeg(self.mundo.fotos()["fija"])

    def imagenes(self) -> list[tuple[str, bytes]]:
        fotos = self.mundo.fotos()
        salida = [("Cámara fija, frente a la obra. Los puntos [y, x] se dan sobre ESTA imagen. Las marcas de "
                   "color indican adónde apunta cada brazo (naranja: izq; verde: der).", self._jpeg(fotos["fija"]))]
        for n in self.mundo.nombres:
            salida.append((f"Cámara de la muñeca del brazo '{n}': lo que ve su mano ahora.",
                           self._jpeg(fotos[f"{n}_muneca"], 384)))
        return salida





