"""Galería de imágenes de la obra: la carpeta `obra/`, su adaptación al cuadro y el vídeo en directo.

La imagen es una consigna del operador. Cambiarla no mueve nada ni cambia la geometría del
cuadro: toda imagen se adapta a la proporción del rectángulo configurado (recortando o
añadiendo bandas), así que un punto [y, x] sigue cayendo en el mismo lugar del plano.
Aquí no hay interfaz gráfica; la ventana está en `interfaz/ventana_imagenes.py`.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import cv2
import numpy as np

EXTENSIONES = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
ESTADO = "_galeria.json"          # elección y encuadres; empieza por «_» para no contar como imagen
QUITADAS = "_quitadas"            # las imágenes quitadas se mueven aquí: nunca se borran
ANCHO = 1280                      # ancho de la imagen adaptada (a ER 2 se le manda a 768 como mucho)
PERDIDA_MAX = 0.25                # en automático se recorta si se pierde como mucho esta parte de la foto
COLOR_BANDAS = (32, 32, 32)       # bandas neutras cuando la imagen se muestra entera
EJEMPLO = "Cuadro de ejemplo"     # el paisaje sintético, siempre disponible
MODOS = ("auto", "recortar", "ajustar")


class ErrorImagen(ValueError):
    """La imagen no se puede leer o no sirve."""


# ------------------------------------------------------------------ leer y guardar
def decodificar(datos: bytes) -> np.ndarray:
    """Bytes de un archivo de imagen → BGR de 8 bits, con la orientación de la cámara aplicada y
    la transparencia sobre blanco."""
    buf = np.frombuffer(datos, np.uint8)
    if buf.size == 0:
        raise ErrorImagen("el archivo está vacío")
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)                    # aplica la orientación EXIF
    if img is None:
        raise ErrorImagen("formato no admitido (sirven PNG, JPG, BMP y WEBP)")
    crudo = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if crudo is not None and crudo.ndim == 3 and crudo.shape[2] == 4 and crudo.shape[:2] == img.shape[:2]:
        alfa = crudo[..., 3:4].astype(np.float32) / float(np.iinfo(crudo.dtype).max)
        img = np.rint(img * alfa + 255.0 * (1.0 - alfa)).astype(np.uint8)
    if min(img.shape[:2]) < 16:
        raise ErrorImagen("la imagen es demasiado pequeña")
    return img


def leer(ruta: Path) -> np.ndarray:
    """Lee una imagen de disco. `cv2.imread` no abre rutas con acentos en Windows; esto sí."""
    try:
        datos = Path(ruta).read_bytes()
    except OSError as e:
        raise ErrorImagen(f"no se puede abrir {Path(ruta).name}: {e.strerror or e}") from None
    try:
        return decodificar(datos)
    except ErrorImagen as e:
        raise ErrorImagen(f"{Path(ruta).name}: {e}") from None


def guardar(ruta: Path, img: np.ndarray, calidad: int = 95) -> None:
    ruta = Path(ruta)
    opciones = [cv2.IMWRITE_JPEG_QUALITY, calidad] if ruta.suffix.lower() in (".jpg", ".jpeg") else []
    ok, datos = cv2.imencode(ruta.suffix, img, opciones)
    if not ok:
        raise ErrorImagen(f"no se pudo codificar {ruta.name}")
    ruta.write_bytes(datos.tobytes())


# ------------------------------------------------------------------ adaptar al cuadro
def proporcion(cfg) -> float:
    """Alto / ancho del rectángulo de la obra configurado."""
    c = cfg.cuadro
    return float(np.linalg.norm(c.inf_izq - c.sup_izq) / np.linalg.norm(c.sup_der - c.sup_izq))


def perdida(img_o_proporcion, objetivo: float) -> float:
    """Parte de la imagen (0–1) que se pierde al recortarla a la proporción `objetivo`."""
    p = img_o_proporcion if np.isscalar(img_o_proporcion) else img_o_proporcion.shape[0] / img_o_proporcion.shape[1]
    return 1.0 - min(p, objetivo) / max(p, objetivo)


def ventana_recorte(alto: int, ancho: int, objetivo: float, centro=(0.5, 0.5)) -> tuple[int, int, int, int]:
    """(x0, y0, ancho, alto) del mayor recorte con la proporción `objetivo`, lo más cerca posible de
    `centro` (x, y en 0–1) sin salirse de la imagen."""
    if alto / ancho > objetivo:                                   # sobra altura
        an, al = ancho, max(1, min(alto, round(ancho * objetivo)))
    else:                                                         # sobra anchura
        an, al = max(1, min(ancho, round(alto / objetivo))), alto
    x0 = int(np.clip(round(centro[0] * ancho - an / 2), 0, ancho - an))
    y0 = int(np.clip(round(centro[1] * alto - al / 2), 0, alto - al))
    return x0, y0, an, al


def adaptar(img: np.ndarray, objetivo: float, modo: str = "auto", centro=(0.5, 0.5),
            ancho: int = ANCHO) -> tuple[np.ndarray, str]:
    """Devuelve la imagen con la proporción exacta del cuadro (ancho × ancho·objetivo) y el modo
    aplicado: «recortar» (llena el cuadro, pierde bordes), «ajustar» (entera, con bandas) o «igual».

    En «auto» recorta si se pierde poco (hasta `PERDIDA_MAX`) y, si no, la muestra entera.
    """
    if modo not in MODOS:
        raise ValueError(f"modo de encuadre desconocido: {modo!r}")
    alto_s, ancho_s = round(ancho * objetivo), ancho
    h, w = img.shape[:2]
    falta = perdida(img, objetivo)
    if modo == "auto":
        modo = "recortar" if falta <= PERDIDA_MAX else "ajustar"

    def escalar(trozo, tam):
        reduce = tam[0] < trozo.shape[1]
        return cv2.resize(trozo, tam, interpolation=cv2.INTER_AREA if reduce else cv2.INTER_CUBIC)

    if falta < 0.004:                                             # ya tiene la proporción
        return escalar(img, (ancho_s, alto_s)), "igual"
    if modo == "recortar":
        x0, y0, an, al = ventana_recorte(h, w, objetivo, centro)
        return escalar(img[y0:y0 + al, x0:x0 + an], (ancho_s, alto_s)), "recortar"
    k = min(ancho_s / w, alto_s / h)
    an, al = max(1, min(ancho_s, round(w * k))), max(1, min(alto_s, round(h * k)))
    lienzo = np.empty((alto_s, ancho_s, 3), np.uint8)
    lienzo[:] = COLOR_BANDAS
    x0, y0 = (ancho_s - an) // 2, (alto_s - al) // 2
    lienzo[y0:y0 + al, x0:x0 + an] = escalar(img, (an, al))
    return lienzo, "ajustar"


def ejemplo() -> np.ndarray:
    from .interfaz.visor import cuadro_sintetico
    return cuadro_sintetico()


# ------------------------------------------------------------------ la carpeta
class Galeria:
    """Las imágenes guardadas en la carpeta de la obra, cuál está elegida y cómo se encuadra cada una."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta)
        self._cache: dict[str, tuple[tuple, np.ndarray]] = {}

    # -- estado guardado
    def _estado(self) -> dict:
        try:
            datos = json.loads((self.carpeta / ESTADO).read_text(encoding="utf8"))
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def _guardar_estado(self, estado: dict) -> None:
        self.carpeta.mkdir(parents=True, exist_ok=True)
        temporal = self.carpeta / (ESTADO + ".tmp")
        temporal.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf8")
        temporal.replace(self.carpeta / ESTADO)

    def recuerdo(self, clave: str):
        """Preferencia de la ventana (última carpeta explorada, cámara usada), o None."""
        return self._estado().get("recuerdos", {}).get(clave)

    def recordar(self, clave: str, valor) -> None:
        estado = self._estado()
        estado.setdefault("recuerdos", {})[clave] = valor
        try:
            self._guardar_estado(estado)
        except OSError:
            pass                                                  # una preferencia no merece un error

    # -- consulta
    def nombres(self) -> list[str]:
        """Imágenes de la carpeta, por nombre. Las que empiezan por «_» no cuentan."""
        if not self.carpeta.is_dir():
            return []
        return sorted((p.name for p in self.carpeta.iterdir()
                       if p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith("_")),
                      key=str.casefold)

    def seleccion(self) -> str | None:
        """Imagen elegida, o None para el cuadro de ejemplo. Sin elección guardada vale la regla
        anterior: la foto más reciente de la carpeta."""
        nombres = self.nombres()
        estado = self._estado()
        if "actual" in estado:
            return estado["actual"] if estado["actual"] in nombres else None
        if not nombres:
            return None
        return max(nombres, key=lambda n: (self.carpeta / n).stat().st_mtime)

    def ajuste(self, nombre: str | None) -> tuple[str, tuple[float, float]]:
        a = self._estado().get("ajustes", {}).get(nombre or "", {})
        modo = a.get("modo") if a.get("modo") in MODOS else "auto"
        try:
            centro = (float(np.clip(a["centro"][0], 0, 1)), float(np.clip(a["centro"][1], 0, 1)))
        except (KeyError, IndexError, TypeError, ValueError):
            centro = (0.5, 0.5)
        return modo, centro

    def original(self, nombre: str | None) -> np.ndarray:
        """La imagen tal como está en la carpeta (None = el cuadro de ejemplo)."""
        if nombre is None:
            return ejemplo()
        ruta = self.carpeta / nombre
        try:
            info = ruta.stat()
        except OSError:
            raise ErrorImagen(f"{nombre} ya no está en la carpeta") from None
        clave = (info.st_mtime_ns, info.st_size)
        if nombre in self._cache and self._cache[nombre][0] == clave:
            return self._cache[nombre][1]
        img = leer(ruta)
        if len(self._cache) >= 3:                                 # una foto de móvil ocupa ~40 MB en memoria
            self._cache.pop(next(iter(self._cache)))
        self._cache[nombre] = (clave, img)
        return img

    def imagen(self, nombre: str | None, objetivo: float) -> tuple[np.ndarray, str]:
        """La imagen adaptada al cuadro con su encuadre guardado, y el modo aplicado."""
        modo, centro = self.ajuste(nombre)
        return adaptar(self.original(nombre), objetivo, modo, centro)

    # -- cambios
    def elegir(self, nombre: str | None) -> None:
        if nombre is not None and nombre not in self.nombres():
            raise ErrorImagen(f"{nombre} no está en la carpeta")
        estado = self._estado()
        estado["actual"] = nombre or ""
        self._guardar_estado(estado)

    def fijar_ajuste(self, nombre: str | None, modo: str, centro=(0.5, 0.5)) -> None:
        if modo not in MODOS:
            raise ValueError(f"modo de encuadre desconocido: {modo!r}")
        estado = self._estado()
        ajustes = estado.setdefault("ajustes", {})
        ajustes[nombre or ""] = {"modo": modo, "centro": [round(float(centro[0]), 4), round(float(centro[1]), 4)]}
        presentes = set(self.nombres())                           # no arrastrar encuadres de imágenes que ya no están
        estado["ajustes"] = {n: a for n, a in ajustes.items() if n == "" or n in presentes}
        self._guardar_estado(estado)

    def _libre(self, nombre: str, datos: bytes | None = None) -> tuple[str, bool]:
        """Nombre disponible en la carpeta. Si ya hay un archivo idéntico, devuelve ese (y True)."""
        base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(nombre).stem).strip(" ._") or "imagen"
        sufijo = Path(nombre).suffix.lower()
        huella = hashlib.sha1(datos).digest() if datos is not None else None
        n = 1
        while True:
            candidato = f"{base}{'' if n == 1 else f'_{n}'}{sufijo}"
            ruta = self.carpeta / candidato
            if not ruta.exists():
                return candidato, False
            if huella is not None and ruta.stat().st_size == len(datos) and \
                    hashlib.sha1(ruta.read_bytes()).digest() == huella:
                return candidato, True
            n += 1

    def anadir(self, rutas) -> tuple[list[str], list[str]]:
        """Copia imágenes de otras carpetas a la de la obra. No toca los originales.

        Devuelve (nombres en la galería, avisos). Una imagen que ya estaba no se duplica; lo que
        no se puede leer se explica y se salta.
        """
        self.carpeta.mkdir(parents=True, exist_ok=True)
        dentro, avisos = [], []
        for ruta in map(Path, rutas):
            try:
                datos = ruta.read_bytes()
                img = decodificar(datos)
            except OSError as e:
                avisos.append(f"{ruta.name}: no se puede abrir ({e.strerror or e})")
                continue
            except ErrorImagen as e:
                avisos.append(f"{ruta.name}: {e}")
                continue
            if ruta.suffix.lower() in EXTENSIONES:
                nombre, repetida = self._libre(ruta.name, datos)
                if not repetida:
                    (self.carpeta / nombre).write_bytes(datos)
            else:                                                 # otro formato legible: se guarda como PNG
                nombre, _ = self._libre(ruta.stem + ".png")
                guardar(self.carpeta / nombre, img)
            if nombre not in dentro:
                dentro.append(nombre)
        return dentro, avisos

    def instantanea(self, fotograma: np.ndarray) -> str:
        """Guarda un fotograma de vídeo como imagen nueva de la galería."""
        if fotograma is None or fotograma.ndim != 3 or min(fotograma.shape[:2]) < 16:
            raise ErrorImagen("no hay fotograma que guardar")
        self.carpeta.mkdir(parents=True, exist_ok=True)
        nombre, _ = self._libre(time.strftime("instantanea_%Y%m%d_%H%M%S.jpg"))
        guardar(self.carpeta / nombre, fotograma)
        return nombre

    def quitar(self, nombre: str) -> None:
        """Saca una imagen de la galería. No se borra: queda en la subcarpeta `_quitadas`."""
        origen = self.carpeta / nombre
        if nombre not in self.nombres():
            raise ErrorImagen(f"{nombre} no está en la carpeta")
        destino = self.carpeta / QUITADAS
        destino.mkdir(exist_ok=True)
        final = destino / nombre
        n = 2
        while final.exists():
            final = destino / f"{Path(nombre).stem}_{n}{Path(nombre).suffix}"
            n += 1
        origen.replace(final)
        self._cache.pop(nombre, None)
        estado = self._estado()
        estado.get("ajustes", {}).pop(nombre, None)
        if estado.get("actual") == nombre:
            estado["actual"] = ""
        self._guardar_estado(estado)


# ------------------------------------------------------------------ vídeo en directo
class FuenteVideo:
    """Cámara o archivo de vídeo leído en un hilo aparte. Solo guarda el último fotograma.

    Leer una cámara bloquea; hacerlo fuera del hilo de la ventana evita que la interfaz (y el
    botón PARAR) se queden esperando. Un archivo se reproduce a su ritmo y vuelve a empezar.
    """

    def __init__(self, origen, ancho: int = 1280, alto: int = 720, tras: "FuenteVideo | None" = None) -> None:
        self.origen = origen
        self._tras = tras               # fuente anterior: se espera a que suelte la cámara antes de abrir
        self.error: str | None = None
        self.abierta = False
        self._pedido = (ancho, alto)
        self._fotograma: np.ndarray | None = None
        self._numero = 0
        self._cerrojo = threading.Lock()
        self._fin = threading.Event()
        self._pausa = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, name="video-en-directo", daemon=True)
        self._hilo.start()

    @property
    def es_camara(self) -> bool:
        return isinstance(self.origen, int)

    def _abrir(self):
        if self.es_camara:
            cap = cv2.VideoCapture(self.origen, cv2.CAP_DSHOW)   # en Windows abre mucho antes que el modo por defecto
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(self.origen)
            if cap.isOpened():
                # Comprimido en la propia cámara: sin esto, a 1280×720 muchas webcams dan solo 10 imágenes/s.
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._pedido[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._pedido[1])
        else:
            cap = cv2.VideoCapture(str(self.origen))
        return cap

    def _bucle(self) -> None:
        cap = None
        try:
            if self._tras is not None:
                self._tras._hilo.join(timeout=5.0)
                self._tras = None
            if self._fin.is_set():
                return
            cap = self._abrir()
            if not cap.isOpened():
                self.error = (f"No se pudo abrir la cámara {self.origen + 1}. Comprueba que está conectada y que "
                              "no la usa otro programa." if self.es_camara
                              else f"No se pudo abrir el vídeo {Path(str(self.origen)).name}.")
                return
            self.abierta = True
            fps = cap.get(cv2.CAP_PROP_FPS) if not self.es_camara else 0.0
            periodo = 1.0 / fps if fps and 1.0 <= fps <= 120.0 else 1.0 / 25.0
            fallos, siguiente = 0, time.perf_counter()
            while not self._fin.is_set():
                if self._pausa.is_set():
                    self._fin.wait(0.05)
                    siguiente = time.perf_counter()
                    continue
                ok, fotograma = cap.read()
                if not ok or fotograma is None:
                    fallos += 1
                    if fallos > 40:
                        self.error = ("La cámara ha dejado de dar imagen." if self.es_camara
                                      else "El vídeo no se puede leer.")
                        return
                    if not self.es_camara and self._numero:      # fin del archivo: vuelve a empezar
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        siguiente = time.perf_counter()
                    else:
                        self._fin.wait(0.05)
                    continue
                fallos = 0
                if fotograma.ndim == 2:
                    fotograma = cv2.cvtColor(fotograma, cv2.COLOR_GRAY2BGR)
                with self._cerrojo:
                    self._fotograma = fotograma
                    self._numero += 1
                if not self.es_camara:                           # un archivo se reproduce a su velocidad
                    siguiente += periodo
                    espera = siguiente - time.perf_counter()
                    if espera > 0:
                        self._fin.wait(espera)
                    else:
                        siguiente = time.perf_counter()
        except Exception as e:                                   # un fallo del vídeo nunca debe tumbar la sesión
            self.error = f"Vídeo: {e}"
        finally:
            self.abierta = False
            if cap is not None:
                cap.release()

    def fotograma(self) -> tuple[int, np.ndarray | None]:
        """(número de fotograma, último fotograma BGR). El número sirve para saber si es nuevo."""
        with self._cerrojo:
            return self._numero, self._fotograma

    def pausar(self, si: bool) -> None:
        (self._pausa.set if si else self._pausa.clear)()

    @property
    def en_pausa(self) -> bool:
        return self._pausa.is_set()

    def cerrar(self, esperar: bool = True) -> None:
        """Deja de leer y suelta la cámara. Sin `esperar` vuelve al momento (la suelta el hilo)."""
        self._fin.set()
        if esperar and threading.current_thread() is not self._hilo:
            self._hilo.join(timeout=3.0)
