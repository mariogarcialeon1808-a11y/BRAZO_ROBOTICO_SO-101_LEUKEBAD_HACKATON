"""Cara del chatbot, dibujo en la ventana de MuJoCo y vídeo en directo como imagen del cuadro. Sin hardware."""
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from so101er import galeria as g
from so101er.config import cargar
from so101er.interfaz.cara import Cara, nivel_de_voz

OBJETIVO = 440 / 700


# ---------------------------------------------------------------- cara
def test_la_cara_esta_quieta_en_silencio_y_mueve_boca_y_ojos_al_hablar():
    cara = Cara()
    for i in range(100):
        cara.paso(i * .05, None)
    assert cara.clave() == (0, 0, 0)                           # cinco segundos en silencio: ni un gesto
    reposo = cara.imagen(160)
    assert reposo.shape == (160, 160, 3) and reposo.dtype == np.uint8
    claves, bocas = set(), []
    for i in range(160):                                       # ocho segundos hablando, con el volumen subiendo y bajando
        cara.paso(5 + i * .05, .5 + .5 * np.sin(i * .9))
        claves.add(cara.clave()); bocas.append(cara.boca)
    assert max(bocas) > .8 and min(bocas[5:]) < .25            # la boca sigue a la voz
    assert any(c[1] > 0 for c in claves)                       # parpadea
    assert max(c[2] for c in claves) > 4 and min(c[2] for c in claves) < -4     # mira a los lados
    cara.paso(13.0, 1.); abierta = cara.imagen(160)
    assert np.abs(abierta.astype(int) - reposo).sum() > 20000  # se ve distinta con la boca abierta
    def azul(img):                                             # píxeles del color de la cara (RGB): ojos y boca
        return (img[..., 1] > 150) & (img[..., 2] > 180) & (img[..., 0] < 140)
    assert azul(abierta[116:140, 60:100]).mean() > .15 and not azul(reposo[116:140, 60:100]).any()     # en reposo no hay boca
    assert azul(reposo[40:100]).mean() > .15                   # y los ojos son los de la cara del robot
    for i in range(20):
        cara.paso(13.05 + i * .05, None)
    assert cara.clave() == (0, 0, 0)                           # al callar vuelve al reposo en menos de un segundo
    np.testing.assert_array_equal(cara.imagen(160), reposo)



def test_la_cara_de_la_esquina_hace_lo_mismo_que_la_de_la_pagina():
    def tras(estado, nivel, gesto=None):
        cara = Cara()
        for i in range(40):
            cara.paso(i * .05, nivel, estado, gesto)
        cara.parpadeo = cara.mirada = 0.
        return cara
    def centro_de_los_ojos(cara):
        img = cara.imagen(176)
        ys, xs = np.nonzero((img[..., 1] > 150) & (img[:118].sum() > 0) & (np.arange(176)[:, None] < 118))
        return xs.mean(), ys.mean()
    frente = centro_de_los_ojos(tras('TALKING', .5))
    derecha = centro_de_los_ojos(tras('TALKING', .5, {'lado': 1, 'vertical': 0, 'animo': 'neutro'}))
    arriba = centro_de_los_ojos(tras('TALKING', .5, {'lado': 0, 'vertical': 1, 'animo': 'neutro'}))
    assert derecha[0] > frente[0] + 8 and arriba[1] < frente[1] - 5           # mira hacia el brazo que gesticula, y arriba
    for lado in (-1, 1):                                                       # y cabe entera aunque mire a un lado
        img = tras('TALKING', .5, {'lado': lado, 'vertical': 0, 'animo': 'atento'}).imagen(176)
        assert img[:, [0, -1]].max() < 60
    alegre, serio = tras('TALKING', .5, {'animo': 'alegre'}), tras('TALKING', .5, {'animo': 'serio'})
    assert alegre.p['happy'] > .5 and alegre.color[1] == 255 and serio.p['lidIn'] > .1 and tras('TALKING', .5).p['lidIn'] == 0
    pensando, error = tras('THINKING', None), tras('ERROR', None)
    assert pensando.estado == 'THINKING' and pensando.p['lookX'] == 70 and pensando.clave() == (0, 0, 0)
    assert tuple(error.color) == (255., 60., 60.) and error.imagen(64)[..., 0].max() > 200            # roja
    assert tras('IDLE', .5).estado == 'TALKING' and tras(None, None).estado == 'IDLE'                 # con voz, habla
    assert tras('IDLE', None, {'lado': 1, 'animo': 'alegre'}).p == tras(None, None).p                 # sin hablar, el gesto no cuenta


def _reproductor(posicion, previo=2400):
    voz = np.r_[np.zeros(12000), 8000 * np.sin(np.arange(12000) * .3)].astype(np.int16)     # medio segundo callada, medio hablando
    return SimpleNamespace(track=np.r_[np.zeros(previo, np.int16), voz], previo=previo, frecuencia=24000,
                           cerrado=False, posicion=lambda: posicion)


def test_el_nivel_de_voz_sale_de_lo_que_suena_en_ese_instante():
    assert nivel_de_voz(None) is None
    assert nivel_de_voz(_reproductor(-.05)) is None            # aún en el silencio previo
    assert nivel_de_voz(_reproductor(.25)) == 0                # la voz está callada en ese tramo
    assert nivel_de_voz(_reproductor(.75)) > .6                # y aquí suena
    assert nivel_de_voz(_reproductor(1.2)) is None             # ya terminó
    cerrado = _reproductor(.75); cerrado.cerrado = True
    assert nivel_de_voz(cerrado) is None
    def sin_reloj():
        raise RuntimeError('el dispositivo aún no ha dado reloj DAC')
    sin = _reproductor(0); sin.posicion = sin_reloj
    assert nivel_de_voz(sin) is None


# ---------------------------------------------------------------- pantalla de exhibición
def test_recuadro_de_la_cara_en_la_esquina_superior_derecha():
    from so101er.hardware.pantalla import MARGEN, poner_cara, recuadro_cara
    izquierda, arriba, lado = recuadro_cara(1280, 800)
    assert lado == 176 and izquierda + lado == 1280 - MARGEN and arriba == MARGEN
    assert recuadro_cara(1920, 2000)[2] == 240 and recuadro_cara(400, 300)[2] == 110       # ni enorme ni diminuta
    assert recuadro_cara(100, 80) is None                                                  # imagen minúscula: sin cara
    lienzo = np.full((800, 1280, 3), 99, np.uint8)
    poner_cara(lienzo, Cara())
    dentro = lienzo[arriba:arriba + lado, izquierda:izquierda + lado]
    assert (dentro != 99).all(axis=2).mean() > .95                                         # la cara ocupa su recuadro…
    assert ((dentro[..., 1] > 150) & (dentro[..., 2] > 180) & (dentro[..., 0] < 140)).mean() > .1      # …con los ojos azules del robot
    fuera = lienzo.copy(); fuera[arriba:arriba + lado, izquierda:izquierda + lado] = 99
    assert (fuera == 99).all()                                                             # y nada más se toca
    assert (poner_cara(np.zeros((80, 100, 3), np.uint8), Cara()) == 0).all()


def test_la_escena_dibuja_brazos_cuadro_y_cara_sin_ventana():
    pytest.importorskip('mujoco')
    from so101er.hardware.pantalla import Escena, recuadro_cara
    cfg = cargar()
    try:
        escena = Escena(cfg, ['izq', 'der'], g.adaptar(g.ejemplo(), OBJETIVO)[0], 640, 400)
    except Exception as e:
        pytest.skip(f'sin contexto gráfico: {e}')
    try:
        x, y, lado = recuadro_cara(640, 400)
        escena.colocar({'izq': np.zeros(6), 'der': None})                 # un brazo sin lectura conserva su postura
        callada = escena.fotograma(None, 0.).astype(int)
        assert callada.shape == (400, 640, 3)
        assert np.abs(escena.fotograma(None, 1.).astype(int) - callada).max() == 0          # en silencio, imagen idéntica
        for i in range(8):
            hablando = escena.fotograma(1., 1.05 + i * .05).astype(int)
        cambio = np.abs(hablando - callada).sum(axis=2) > 60
        assert cambio[y:y + lado, x:x + lado].mean() > .01                # la boca se ha movido...
        fuera = cambio.copy(); fuera[y:y + lado, x:x + lado] = False
        assert not fuera.any()                                            # ...y solo cambia la cara
        roja = np.zeros((round(g.ANCHO * OBJETIVO), g.ANCHO, 3), np.uint8); roja[..., 2] = 255
        assert escena.cuadro('roja', roja, ahora=10.) is True
        assert escena.cuadro('roja', roja, ahora=11.) is False            # la misma imagen no se vuelve a subir
        assert escena.cuadro('otra', roja, ahora=10.01) is False          # ni más deprisa que el límite
        con_foto = escena.fotograma(1., 1.45).astype(int)
        nuevo = np.abs(con_foto - hablando).sum(axis=2) > 60
        nuevo[y:y + lado, x:x + lado] = False
        assert nuevo.mean() > .03 and (con_foto[nuevo][:, 2] > con_foto[nuevo][:, 1] + 40).mean() > .8      # el cuadro es rojo (BGR)
        escena.girar(100, 0); escena.acercar(2)
        assert np.abs(escena.fotograma(1., 1.5).astype(int) - con_foto).mean() > 1         # la vista se puede mover
        escena.girar(0, -10000); escena.acercar(-100)
        assert escena.camara.elevation == 20 and escena.camara.distance == 4               # con topes
    finally:
        escena.cerrar()


def test_la_escena_preparada_se_reutiliza_sin_volver_a_compilar():
    pytest.importorskip('mujoco')
    from so101er.hardware import pantalla
    cfg = cargar(); imagen = g.adaptar(g.ejemplo(), OBJETIVO)[0]
    preparada = pantalla.MundoDeExhibicion(cfg, ['izq', 'der'], imagen)          # esto es lo que tarda: se hace antes de dar par
    compilaciones = []
    original = pantalla.MundoDeExhibicion
    class Espia(original):
        def __init__(self, *a, **k):
            compilaciones.append(1); super().__init__(*a, **k)
    pantalla.MundoDeExhibicion = Espia
    try:
        roja = np.zeros((round(g.ANCHO * OBJETIVO), g.ANCHO, 3), np.uint8); roja[..., 2] = 255
        for _ in range(2):                                             # abrir, cerrar y volver a abrir la ventana
            try:
                escena = pantalla.Escena(cfg, ['izq', 'der'], roja, 320, 200, exhibicion=preparada)
            except Exception as e:
                pytest.skip(f'sin contexto gráfico: {e}')
            assert escena.mundo is preparada.mundo
            foto = escena.fotograma(None, 0.).astype(int)
            assert ((foto[..., 2] > foto[..., 1] + 60) & (foto[..., 2] > 150)).mean() > .02       # se dibuja con la imagen de ahora
            escena.cerrar()
        assert compilaciones == []
        assert preparada.mundo.modelo.ngeom > 0                        # y sigue viva tras cerrar la ventana
    finally:
        pantalla.MundoDeExhibicion = original
        preparada.cerrar()


# ---------------------------------------------------------------- directo
class FuenteFalsa:
    def __init__(self, origen=0):
        self.origen, self.error, self.cerrada, self.numero, self.en_pausa = origen, None, False, 0, False
        self.cuadro = None
    def poner(self, valor):
        self.numero += 1; self.cuadro = np.full((480, 640, 3), valor, np.uint8)
    def fotograma(self): return self.numero, self.cuadro
    def pausar(self, si): self.en_pausa = si
    def cerrar(self, esperar=True): self.cerrada = True


def _sesion():
    from so101er.aplicacion import SesionIntegrada
    avisos, llamadas = [], []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.closed, s.notificar, s.lock, s.proporcion = False, avisos.append, threading.RLock(), OBJETIVO
    s.cfg = cargar(); s.galeria = g.Galeria('obra'); s.imagen, s.imagen_nombre = g.adaptar(g.ejemplo(), OBJETIVO)[0], None
    s.interrumpir = lambda: llamadas.append('interrumpir'); s.vision = SimpleNamespace(historia=['algo']); s.mundo = None
    return s, avisos, llamadas


def test_el_directo_es_la_imagen_del_cuadro_y_se_detiene_mientras_se_explica():
    s, avisos, llamadas = _sesion()
    clave0, img0 = s.imagen_pantalla()
    assert img0 is s.imagen and s.imagen_pantalla()[0] == clave0          # foto fija: la clave no cambia
    camara = FuenteFalsa(); camara.poner(50)
    s.usar_directo(camara, 'Cámara 1')
    assert s.rotulo_imagen() == 'Cámara 1 en directo' and s.imagen_en_uso() is False
    assert llamadas == ['interrumpir'] and s.vision.historia == [] and int(s.imagen[0, 0, 0]) == 50
    clave1, vivo = s.imagen_pantalla()
    assert vivo.shape == (round(1024 * OBJETIVO), 1024, 3) and int(vivo[0, 0, 0]) == 50
    assert s.imagen_pantalla()[1] is vivo                                 # mismo fotograma: no se vuelve a adaptar
    camara.poner(90)
    clave2, vivo = s.imagen_pantalla()
    assert clave2 != clave1 and int(vivo[0, 0, 0]) == 90                  # sigue a la cámara
    # Empieza un turno: la imagen de la sesión (la que ve la IA) es la de ese instante y el cuadro la mantiene.
    s.en_turno = 1; s._congelar_directo(); camara.poner(200)
    clave3, parada = s.imagen_pantalla()
    assert parada is s.imagen and int(parada[0, 0, 0]) == 90 and parada.shape[1] == g.ANCHO
    jpeg = cv2.imdecode(np.frombuffer(s.jpeg(), np.uint8), cv2.IMREAD_COLOR)
    assert abs(int(jpeg[10, 10, 0]) - 90) < 4 and jpeg.shape[1] == 768
    s.en_turno = 0
    assert int(s.imagen_pantalla()[1][0, 0, 0]) == 200                    # al acabar vuelve el directo
    camara.error = 'La cámara ha dejado de dar imagen.'
    assert s.imagen_pantalla()[1] is s.imagen                             # con la cámara caída, la última imagen cargada


def test_soltar_el_directo_o_cargar_una_foto_libera_la_camara():
    s, avisos, llamadas = _sesion()
    camara = FuenteFalsa(); camara.poner(70)
    s.usar_directo(camara, 'Cámara 1'); camara.poner(120)
    assert s.soltar_directo() is camara and not camara.cerrada            # se devuelve abierta: la ventana sigue con ella
    assert s.directo is None and int(s.imagen[0, 0, 0]) == 120 and s.rotulo_imagen() == 'Última imagen del directo'
    assert s.imagen_en_uso() is False and s.soltar_directo() is None
    s.usar_directo(camara, 'Cámara 1')
    otra = FuenteFalsa(1); otra.poner(10)
    s.usar_directo(otra, 'clip.mp4')
    assert camara.cerrada and not otra.cerrada and s.rotulo_imagen() == 'clip.mp4 en directo'      # una fuente sustituye a la otra
    s.cambiar_imagen(g.adaptar(g.ejemplo(), OBJETIVO)[0], None)
    assert otra.cerrada and s.directo is None and s.rotulo_imagen() == g.EJEMPLO and s.imagen_en_uso() is None
    rota = FuenteFalsa(); rota.error = 'No se pudo abrir la cámara 1.'
    with pytest.raises(ValueError, match='No se pudo abrir'):
        s.usar_directo(rota, 'Cámara 1')
    s.closed = True
    with pytest.raises(RuntimeError):
        s.usar_directo(FuenteFalsa(), 'Cámara 1')


def test_el_turno_cuenta_cuando_se_esta_explicando():
    from so101er.aplicacion import SesionIntegrada
    s, avisos, llamadas = _sesion()
    visto = []
    s.control = SimpleNamespace(frenada=None, error=None, parar=lambda: None)
    s.real = False; s.brazos = {}
    def desplegar():
        visto.append(s.en_turno); raise RuntimeError('fin de la prueba')
    s.desplegar = desplegar
    camara = FuenteFalsa(); camara.poner(33); s.directo = camara
    SesionIntegrada._turno(s, 'hola', None, threading.Event(), 0)
    assert visto == [1] and s.en_turno == 0 and int(s.imagen[0, 0, 0]) == 33    # se congela al empezar; se libera aunque falle
    assert any('fin de la prueba' in a for a in avisos)


# ---------------------------------------------------------------- ventana
def test_la_ventana_entrega_el_video_y_lo_recupera_sin_reabrir_la_camara(raiz, tmp_path):
    from so101er.interfaz.ventana_imagenes import VentanaImagenes
    entregas, en_sesion = [], [None]
    def al_directo(fuente, rotulo):
        entregas.append(rotulo); en_sesion[0] = fuente
    def tomar():
        fuente, en_sesion[0] = en_sesion[0], None
        return fuente
    v = VentanaImagenes(raiz, g.Galeria(tmp_path / 'obra'), OBJETIVO, lambda: None, lambda n, i: None,
                        al_directo=al_directo, tomar_directo=tomar)
    try:
        camara = FuenteFalsa(); v.fuente = camara                    # como si «Vídeo en directo» hubiera abierto la cámara
        v.directo(); assert entregas == [] and 'no hay imagen' in v.aviso.get()      # sin imagen aún, no se entrega
        camara.poner(80); camara.en_pausa = True
        v.directo()
        assert entregas == ['Cámara 1'] and en_sesion[0] is camara and not camara.cerrada and not camara.en_pausa
        assert not v.en_video and 'en directo' in v.aviso.get()
        v.entrar_video()                                              # vuelve a por el vídeo: lo recupera de la sesión
        assert v.fuente is camara and en_sesion[0] is None and not camara.cerrada and v.origen.get() == 'Cámara 1'
        v.salir_video()
        assert camara.cerrada                                         # si no se entrega de nuevo, se suelta la cámara
    finally:
        v.cerrar()


def test_sin_sesion_que_admita_directo_no_hay_boton(raiz, tmp_path):
    from so101er.interfaz.ventana_imagenes import VentanaImagenes
    v = VentanaImagenes(raiz, g.Galeria(tmp_path / 'obra'), OBJETIVO, lambda: None, lambda n, i: None)
    try:
        textos = [c.cget('text') for c in v.barra_video.winfo_children() if 'text' in c.keys()]
        assert 'Usar en directo' not in textos and 'Tomar instantánea y usarla' in textos
    finally:
        v.cerrar()
