"""Cálculo de gestos en otro proceso, para hacerlo mientras los brazos se mueven.

Compilar un gesto ocupa un núcleo entre 0,3 y 1,5 s. En el turno frase a frase eso ocurre mientras
suena y se gesticula la frase anterior. Hecho en un hilo del programa le quita el turno a los demás
hilos de Python: en simulación la física avanzó 1,1 s en 2,7 s (medido el 15-11-2026) y el control se
detuvo con «error de seguimiento >25 grados»; con los brazos reales, el hilo que los atiende se
retrasa. En otro proceso no compite con nadie.

Solo viajan consignas y constantes (el motor de gestos, la intención, la postura de partida prevista y
el audio generado de la frase). Ninguna medida de sensores ni estado del simulador sale ni entra.
Si el otro proceso no arranca o se cae, el cálculo se hace en el propio programa, cediendo el paso a
los demás hilos más a menudo.
"""
from __future__ import annotations

import sys
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import _RemoteTraceback


def calentar():
    """Carga en el otro proceso lo que hará falta, para que el primer gesto no pague el arranque."""
    from . import acompanamiento, escenico  # noqa: F401
    return True


def gesto(motor, intencion, inicio, bilateral):
    from .escenico import compilar_actuacion
    return compilar_actuacion(motor, intencion, inicio, bilateral=bilateral)


def movimiento(motor, brazo, principal, otro, inicio, delta=0.0):
    """Plan de un movimiento de la biblioteca (y, si se da, de otro en el otro brazo, `delta` s después)."""
    from .expresion import plan
    return plan(motor, brazo, principal, inicio, otro, delta)


def fundido(motor, plan_a, plan_b, brazo_a, brazo_b, apice_a, apice_b, delta):
    """Los dos planes en uno, cada brazo con su ápice. Si juntos no caben, queda el del brazo principal."""
    from .expresion import fundir
    try:
        return fundir(motor, plan_a, plan_b, brazo_a, brazo_b, apice_a, apice_b, delta)
    except ValueError:
        return plan_a


def acompanado(motor, plan, escala):
    """El plan con el brazo libre acompañando (el propio plan si no cabe). La comprobación del brazo real se hace fuera."""
    from .acompanamiento import acompanar
    return acompanar(motor, plan, escala)


def alargado(motor, plan, extra):
    """El plan con la preparación repartida en `extra` segundos más: mismo ápice, salida más lenta."""
    from .acompanamiento import preparar_antes
    return preparar_antes(motor, plan, extra)


def acentos(motor, audio, duracion, primero):
    from .acompanamiento import solo_acentos
    return solo_acentos(motor, audio, duracion, None, primero)[0]


class Calculador:
    """Ejecuta una de las funciones de este módulo en otro proceso y devuelve su resultado."""

    INTERVALO_CEDIENDO = 0.0005        # s; el de Python es 0,005. Con este la física simulada no se retrasa

    def __init__(self) -> None:
        self.fuera = 0                 # cálculos hechos en el otro proceso
        self.dentro = 0                # cálculos hechos en este, por no tener el otro
        self._cerrojo = threading.Lock()
        self._arranque = None
        try:
            self._pool = ProcessPoolExecutor(1)
            self._arranque = self._pool.submit(calentar)
        except Exception:
            self._pool = None

    def listo(self, espera_s: float = 0.0) -> bool:
        """¿Está el otro proceso en marcha? Espera hasta `espera_s` a que termine de arrancar."""
        if self._pool is None or self._arranque is None:
            return False
        try:
            return bool(self._arranque.result(timeout=espera_s))
        except Exception:
            if self._arranque.done():   # arrancó mal: no se vuelve a intentar
                self._descartar()
            return False

    def __call__(self, funcion, *args):
        """`funcion(*args)`. Los errores del cálculo (un gesto que no cabe) salen igual que si se hiciera aquí."""
        if self.listo(8.0):
            try:
                resultado = self._pool.submit(funcion, *args).result(timeout=30)
            except Exception as error:
                if isinstance(error.__cause__, _RemoteTraceback):
                    raise                  # error del propio cálculo, ocurrido en el otro proceso
                self._descartar()          # el otro proceso no ha podido (caído, cerrado, tarda demasiado): se hace aquí
            else:
                self.fuera += 1
                return resultado
        self.dentro += 1
        with self._cerrojo:            # aquí mismo, dejando pasar a los demás hilos diez veces más a menudo
            previo = sys.getswitchinterval()
            sys.setswitchinterval(self.INTERVALO_CEDIENDO)
            try:
                return funcion(*args)
            finally:
                sys.setswitchinterval(previo)

    def _descartar(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

    def cerrar(self) -> None:
        self._descartar()
