"""Cara del robot: página local con ojos, subtítulos y la imagen que se explica.

Es solo salida de conversación: nada del control la lee ni espera por ella (AGENTS.md).
Cada método encola y vuelve; el trabajo se hace en un hilo propio. Ninguna excepción sale
de aquí: se avisa una vez con `notificar` y la sesión sigue exactamente igual.
"""
import functools
import os
from pathlib import Path
import queue
import threading
import time

PREDETERMINADO = {'activa': True, 'puerto': 8765, 'desfase_ms': 0, 'imagen': True, 'espejo': False}
ERROR_S = 4.            # la cara roja dura esto y vuelve a reposo
RELOJ_S = .1
PENDIENTE_S = .04       # con frases o gestos por empezar se mira el reloj más a menudo
NEUTRA = {'lado': 0, 'vertical': 0, 'animo': 'neutro'}


def leer_seccion(raiz, nombre, predeterminado):
    """Sección `[nombre]` de config/so101er.toml (o la incluida), sobre `predeterminado`. Nunca lanza."""
    import tomllib
    valores = dict(predeterminado)
    for ruta in (Path(raiz) / 'config/so101er.toml', Path(__file__).parents[1] / 'predeterminado.toml'):
        try:
            with open(ruta, 'rb') as f:
                valores.update(tomllib.load(f).get(nombre, {}))
            break
        except (OSError, tomllib.TOMLDecodeError, AttributeError, TypeError, ValueError):
            continue
    return valores


def apagada(variable):
    return os.environ.get(variable, '').strip().lower() in ('0', 'false', 'no', 'off')


def crear(raiz, imagen, notificar=print):
    """`Cara` si `[cara] activa` (y no `SO101_CARA=0`); si no, o si algo falla, `CaraNula`."""
    try:
        cfg = leer_seccion(raiz, 'cara', PREDETERMINADO)
        if apagada('SO101_CARA') or not cfg['activa']:
            return CaraNula()
        cara = Cara(imagen, notificar, int(cfg['puerto']), float(cfg['desfase_ms']), bool(cfg['imagen']))
        cara.espejo = bool(cfg.get('espejo', False))
        notificar(f'Cara del robot en http://127.0.0.1:{cara.puerto}/ (ABRIR_CARA.cmd).')
        return cara
    except Exception as e:
        try:
            notificar('Cara del robot no disponible: ' + str(e))
        except Exception:
            pass
        return CaraNula()


class CaraNula:
    """Misma API, no hace nada. Falsa en `if c:`, así los enganches ni siquiera la llaman."""

    def __bool__(self):
        return False

    def pensando(self, texto_usuario=''): pass
    def escuchando(self, activo): pass
    def error(self, texto): pass
    def hablar(self, texto, marks, escala, audio, reloj, bloques): pass
    def frase(self, clave, texto, marks, audio, reloj, inicio, bloques=(), duracion=None): pass
    def gesto(self, reloj, inicio, fin, lado=0, vertical=0, animo='neutro'): pass
    def imagen_nueva(self, imagen): pass
    def callar(self, interrumpido=False): pass
    def cerrar(self): pass


def _seguro(metodo):
    @functools.wraps(metodo)
    def envoltura(self, *args, **kwargs):
        try:
            metodo(self, *args, **kwargs)
        except Exception as e:
            self._aviso(metodo.__name__, e)
    return envoltura


class Cara:
    def __init__(self, imagen, notificar=print, puerto=8765, desfase_ms=0., mostrar_imagen=True):
        from .servidor import Bus, Servidor
        self.notificar = notificar
        self.avisados = set()
        self.imagen = imagen
        self.con_imagen = mostrar_imagen
        self.mostrar_imagen = mostrar_imagen and imagen is not None
        self.espejo = False            # true: el público ve la cara de frente y los brazos quedan cruzados respecto a ella
        self.frases = {}               # clave -> frase de un turno que suena por frases
        self.gestos = []               # (reloj, inicio, fin, mirada) de los gestos de los brazos
        self.mirada = dict(NEUTRA)
        self.desfase_ms = desfase_ms
        self.obra_v = int(time.time())
        self._jpeg = None
        self.bus = Bus()
        self.servidor = Servidor(self.bus, self._obra, puerto)
        self.puerto = self.servidor.puerto
        self.cola = queue.Queue()
        self.id = 0
        self.activo = None             # (id, reloj, duración) del turno que suena
        self.estado = 'IDLE'
        self.error_hasta = 0.
        self.usuario = (None, 0.)
        self.cerrada = False
        self.hilo = threading.Thread(target=self._bucle, name='cara', daemon=True)
        self.hilo.start()

    # --- API: solo encola -------------------------------------------------
    @_seguro
    def pensando(self, texto_usuario=''):
        self.cola.put(('pensando', (texto_usuario or '').strip()))

    @_seguro
    def escuchando(self, activo):
        self.cola.put(('escuchando', bool(activo)))

    @_seguro
    def error(self, texto):
        self.cola.put(('error', str(texto)))

    @_seguro
    def hablar(self, texto, marks, escala, audio, reloj, bloques):
        self.cola.put(('hablar', (texto, list(marks or []), escala, audio, reloj, list(bloques or []))))

    @_seguro
    def frase(self, clave, texto, marks, audio, reloj, inicio, bloques=(), duracion=None):
        """Una frase de un turno que se dice frase a frase.

        `reloj` es el del altavoz de todo el turno e `inicio`, el instante de ese reloj en que la frase empieza
        a sonar: la cara la saca en ese momento, no antes. Se puede llamar dos veces con la misma `clave`:
        primero con la voz que haya llegado (y `duracion` estimada) y después con toda; si ya está sonando,
        se corrige en marcha.
        """
        self.cola.put(('frase', (clave, texto, list(marks or []), audio, reloj, float(inicio), list(bloques or []), duracion)))

    @_seguro
    def gesto(self, reloj, inicio, fin, lado=0, vertical=0, animo='neutro'):
        """Un gesto de los brazos, de `inicio` a `fin` en `reloj`: la cara mira hacia él y toma su ánimo."""
        self.cola.put(('gesto', (reloj, float(inicio), float(fin), {'lado': int(lado), 'vertical': int(vertical), 'animo': str(animo)})))

    @_seguro
    def imagen_nueva(self, imagen):
        """La imagen que se explica ha cambiado (otra de la galería, una instantánea, el directo)."""
        self.cola.put(('imagen', imagen))

    @_seguro
    def callar(self, interrumpido=False):
        self.cola.put(('callar', bool(interrumpido)))

    @_seguro
    def cerrar(self):
        if self.cerrada:
            return
        self.cerrada = True
        self.cola.put(('cerrar', None))
        self.servidor.cerrar()       # síncrono (≤0,1 s): una sesión nueva puede abrir el mismo puerto

    # --- hilo de la cara --------------------------------------------------
    def _aviso(self, donde, e):
        clave = (donde, type(e).__name__)
        if clave in self.avisados:
            return
        self.avisados.add(clave)
        try:
            self.notificar(f'Cara del robot ({donde}): {e}')
        except Exception:
            pass

    def _obra(self):
        if self._jpeg is None and self.imagen is not None:
            import cv2
            img = self.imagen
            lado = max(img.shape[:2])
            if lado > 1600:
                k = 1600 / lado
                img = cv2.resize(img, (round(img.shape[1] * k), round(img.shape[0] * k)), interpolation=cv2.INTER_AREA)
            self._jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()
        return self._jpeg

    def _estado(self, estado, texto=None):
        if estado == self.estado and texto is None:
            return
        self.estado = estado
        self.bus.publicar('estado', {'estado': estado, **({'texto': texto} if texto else {})})

    def _terminar(self, interrumpido):
        if self.activo is not None:
            self.bus.publicar('fin', {'id': self.activo[0], 'interrumpido': interrumpido})
            self.activo = None

    def _bucle(self):
        siguiente = 0.
        while True:
            vivo = self.activo or self.frases or self.gestos
            espera = max(0., siguiente - time.monotonic()) if vivo else .5
            try:
                op, datos = self.cola.get(timeout=espera)
            except queue.Empty:
                op = None
            except Exception as e:
                self._aviso('cola', e)
                time.sleep(.1)
                op = None
            if op == 'cerrar':
                return
            try:
                if op:
                    self._procesar(op, datos)
                if (self.activo or self.frases or self.gestos) and time.monotonic() >= siguiente:
                    pendiente = self.gestos or any(f['id'] is None for f in self.frases.values())
                    siguiente = time.monotonic() + (PENDIENTE_S if pendiente else RELOJ_S)
                    self._empezar_frases()
                    self._mirar()
                    if self.activo:
                        self._tic()
                if self.estado == 'ERROR' and time.monotonic() > self.error_hasta and not self.activo:
                    self._estado('IDLE')
            except Exception as e:
                self._aviso(op or 'reloj', e)

    def _soltar(self):
        """Olvida las frases y gestos de un turno que ya no sigue, y devuelve la mirada al frente."""
        self.frases.clear()
        self.gestos.clear()
        if self.mirada != NEUTRA:
            self.mirada = dict(NEUTRA)
            self.bus.publicar('mirada', self.mirada)

    def _publicar_frase(self, f):
        from .tiempos import turno
        evento = turno(f['id'], f['texto'], f['marks'], 1., f['audio'], f['bloques'] if self.mostrar_imagen else [], self.obra_v,
                       duracion=f['duracion'])
        evento['desfase_ms'] = self.desfase_ms
        evento['rev'] = f['rev']
        self.bus.publicar('turno', evento)
        reloj, inicio = f['reloj'], f['inicio']
        self.activo = (f['id'], lambda: reloj() - inicio, evento['duracion'])

    def _empezar_frases(self):
        """Saca cada frase pendiente cuando el altavoz llega a su comienzo. La anterior termina sin cortarse."""
        for f in sorted((f for f in self.frases.values() if f['id'] is None), key=lambda f: f['inicio']):
            try:
                pos = float(f['reloj']())
            except Exception:
                return             # aún no hay reloj DAC
            if pos < f['inicio'] - PENDIENTE_S:
                return
            self._terminar(False)
            self.id += 1
            f['id'] = self.id
            self._publicar_frase(f)
            self._estado('TALKING')

    def _mirar(self):
        """La mirada sigue al gesto de los brazos que está en curso; sin gesto, vuelve al frente."""
        actual, quedan = NEUTRA, []
        for g in self.gestos:
            reloj, inicio, fin, mirada = g
            try:
                pos = float(reloj())
            except Exception:
                quedan.append(g)
                continue
            if pos < fin:
                quedan.append(g)
                if pos >= inicio:
                    actual = mirada
        self.gestos = quedan
        if actual != self.mirada:
            self.mirada = dict(actual)
            self.bus.publicar('mirada', self.mirada)

    def _procesar(self, op, datos):
        if op == 'frase':
            clave, texto, marks, audio, reloj, inicio, bloques, duracion = datos
            previa = self.frases.get(clave)
            f = {'texto': texto, 'marks': marks, 'audio': audio, 'reloj': reloj, 'inicio': inicio, 'bloques': bloques,
                 'duracion': duracion, 'id': previa['id'] if previa else None, 'rev': previa['rev'] + 1 if previa else 0}
            self.frases[clave] = f
            if f['id'] is not None and self.activo and self.activo[0] == f['id']:
                self._publicar_frase(f)          # ya está sonando: llegan los tiempos definitivos
            return
        if op == 'gesto':
            self.gestos.append(datos)
            return
        if op == 'imagen':
            self.imagen, self._jpeg = datos, None
            self.obra_v = int(time.time() * 1000) % 1_000_000_000
            self.mostrar_imagen = self.con_imagen and datos is not None
            return
        if op in ('pensando', 'escuchando', 'error', 'hablar', 'callar'):
            self._soltar()                       # cualquiera de estos cierra el turno por frases anterior
        if op == 'pensando':
            self._terminar(True)
            texto, (anterior, cuando) = datos, self.usuario
            if texto and (texto != anterior or time.monotonic() - cuando > 20):
                self.usuario = (texto, time.monotonic())
                self.bus.publicar('usuario', {'texto': texto})
            self._estado('THINKING')
        elif op == 'escuchando':
            self._terminar(True)
            self._estado('LISTENING' if datos else 'IDLE')
        elif op == 'error':
            self._terminar(True)
            self.error_hasta = time.monotonic() + ERROR_S
            self._estado('ERROR', datos[:200])
        elif op == 'hablar':
            from .tiempos import turno
            texto, marks, escala, audio, reloj, bloques = datos
            self._terminar(True)
            self.id += 1
            evento = turno(self.id, texto, marks, escala, audio, bloques if self.mostrar_imagen else [], self.obra_v)
            evento['desfase_ms'] = self.desfase_ms
            self.bus.publicar('turno', evento)
            self.activo = (self.id, reloj, evento['duracion'])
            self._estado('TALKING')
        elif op == 'callar':
            self._terminar(datos)
            if self.estado != 'ERROR':
                self._estado('IDLE')

    def _tic(self):
        id_, reloj, duracion = self.activo
        try:
            pos = float(reloj())
        except Exception:
            return               # aún no hay reloj DAC: se espera sin fallar
        if pos <= duracion + 5:
            self.bus.publicar('reloj', {'id': id_, 'pos': round(pos, 3)})
