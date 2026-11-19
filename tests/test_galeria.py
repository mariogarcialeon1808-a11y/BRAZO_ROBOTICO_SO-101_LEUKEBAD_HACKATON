"""Galería de imágenes: adaptación al cuadro, carpeta, vídeo y cambio de imagen en caliente. Sin hardware."""
import json
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from so101er import galeria as g
from so101er.config import cargar

OBJETIVO = 440 / 700            # alto / ancho del rectángulo configurado


def _foto(alto, ancho, marca=True):
    """Degradado con una franja roja a la izquierda y otra azul arriba, para saber qué se recortó."""
    img = np.zeros((alto, ancho, 3), np.uint8)
    img[..., 1] = np.linspace(40, 200, ancho, dtype=np.uint8)[None, :]
    if marca:
        img[:, : ancho // 10] = (0, 0, 255)
        img[: alto // 10, :] = (255, 0, 0)
    return img


def _jpeg(ruta, img):
    g.guardar(ruta, img)
    return ruta


# ---------------------------------------------------------------- adaptar
def test_proporcion_del_cuadro_configurado():
    assert g.proporcion(cargar()) == pytest.approx(OBJETIVO)


@pytest.mark.parametrize('alto,ancho,esperado', [(478, 760, 'igual'), (480, 640, 'recortar'), (720, 1280, 'recortar'),
                                                 (800, 800, 'ajustar'), (1600, 1200, 'ajustar'), (300, 2000, 'ajustar')])
def test_adaptar_da_siempre_la_proporcion_exacta_y_elige_recortar_o_bandas(alto, ancho, esperado):
    salida, modo = g.adaptar(_foto(alto, ancho), OBJETIVO)
    assert modo == esperado and salida.shape == (round(g.ANCHO * OBJETIVO), g.ANCHO, 3) and salida.dtype == np.uint8
    assert g.perdida(salida, OBJETIVO) < .002
    bandas = np.all(salida == g.COLOR_BANDAS, axis=2)
    assert bandas.any() == (esperado == 'ajustar')
    if esperado == 'ajustar' and alto >= ancho:                # bandas a los lados; la foto entera en el centro
        assert bandas[:, :50].all() and bandas[:, -50:].all() and not bandas[:, g.ANCHO // 2].any()


def test_recortar_respeta_el_centro_elegido_sin_salirse():
    foto = _foto(1000, 1000)                                   # cuadrada: sobra altura
    arriba, _ = g.adaptar(foto, OBJETIVO, 'recortar', (.5, 0.))
    abajo, _ = g.adaptar(foto, OBJETIVO, 'recortar', (.5, 1.))
    assert arriba[5, g.ANCHO // 2, 0] > 200 and abajo[5, g.ANCHO // 2, 0] < 50     # la franja azul solo arriba
    assert g.ventana_recorte(1000, 1000, OBJETIVO, (.5, 0.)) == (0, 0, 1000, 629)
    assert g.ventana_recorte(1000, 1000, OBJETIVO, (.5, 5.)) == (0, 371, 1000, 629)
    assert g.ventana_recorte(400, 1000, OBJETIVO, (0., .5)) == (0, 0, 636, 400)
    with pytest.raises(ValueError):
        g.adaptar(foto, OBJETIVO, 'estirar')


def test_una_imagen_pequena_se_amplia_y_una_enorme_se_reduce():
    assert g.adaptar(_foto(63, 100), OBJETIVO)[0].shape[1] == g.ANCHO
    assert g.adaptar(_foto(3000, 4000), OBJETIVO)[0].shape[1] == g.ANCHO


# ---------------------------------------------------------------- leer
def test_leer_admite_acentos_transparencia_y_grises(tmp_path):
    carpeta = tmp_path / 'Imágenes de la cámara ñ'
    carpeta.mkdir()
    g.guardar(carpeta / 'paisaje nº1.jpg', _foto(120, 200))
    assert g.leer(carpeta / 'paisaje nº1.jpg').shape == (120, 200, 3)
    rgba = np.zeros((40, 60, 4), np.uint8); rgba[:, :30] = (0, 0, 255, 255)      # mitad roja opaca, mitad transparente
    g.guardar(carpeta / 'logo.png', rgba)
    logo = g.leer(carpeta / 'logo.png')
    assert logo.shape == (40, 60, 3) and tuple(logo[20, 10]) == (0, 0, 255) and tuple(logo[20, 50]) == (255, 255, 255)
    g.guardar(carpeta / 'gris.png', np.full((40, 60), 128, np.uint8))
    assert g.leer(carpeta / 'gris.png').shape == (40, 60, 3)


def test_leer_explica_lo_que_no_sirve(tmp_path):
    (tmp_path / 'nota.jpg').write_text('esto no es una imagen')
    (tmp_path / 'vacia.png').write_bytes(b'')
    g.guardar(tmp_path / 'punto.png', np.zeros((4, 4, 3), np.uint8))
    for nombre, motivo in (('nota.jpg', 'formato no admitido'), ('vacia.png', 'vacío'), ('punto.png', 'pequeña'),
                           ('no_esta.png', 'no se puede abrir')):
        with pytest.raises(g.ErrorImagen, match=motivo):
            g.leer(tmp_path / nombre)


def test_la_orientacion_de_la_camara_se_aplica(tmp_path):
    # JPEG apaisado con la etiqueta EXIF «girar 90°», como las fotos de móvil hechas en vertical.
    datos = cv2.imencode('.jpg', _foto(100, 200))[1].tobytes()
    tiff = b'II*\x00\x08\x00\x00\x00' + b'\x01\x00' + b'\x12\x01\x03\x00\x01\x00\x00\x00\x06\x00\x00\x00' + b'\x00\x00\x00\x00'
    exif = b'Exif\x00\x00' + tiff
    con_exif = datos[:2] + b'\xff\xe1' + (len(exif) + 2).to_bytes(2, 'big') + exif + datos[2:]
    assert g.decodificar(datos).shape[:2] == (100, 200)
    assert g.decodificar(con_exif).shape[:2] == (200, 100)


# ---------------------------------------------------------------- carpeta
def test_sin_eleccion_guardada_vale_la_foto_mas_reciente_y_luego_la_elegida(tmp_path):
    import os
    galeria = g.Galeria(tmp_path / 'obra')
    assert galeria.nombres() == [] and galeria.seleccion() is None
    (tmp_path / 'obra').mkdir()
    _jpeg(tmp_path / 'obra/b.jpg', _foto(100, 160)); _jpeg(tmp_path / 'obra/A.png', _foto(100, 160))
    _jpeg(tmp_path / 'obra/_oculta.png', _foto(100, 160)); (tmp_path / 'obra/notas.txt').write_text('x')
    os.utime(tmp_path / 'obra/b.jpg', (time.time() + 60,) * 2)
    assert galeria.nombres() == ['A.png', 'b.jpg'] and galeria.seleccion() == 'b.jpg'
    galeria.elegir('A.png')
    assert g.Galeria(tmp_path / 'obra').seleccion() == 'A.png'
    galeria.elegir(None)                                       # el cuadro de ejemplo también se recuerda
    assert g.Galeria(tmp_path / 'obra').seleccion() is None
    with pytest.raises(g.ErrorImagen):
        galeria.elegir('no_esta.jpg')
    (tmp_path / 'obra' / g.ESTADO).write_text('{ roto')        # un estado ilegible no impide trabajar
    assert galeria.seleccion() == 'b.jpg' and galeria.ajuste('b.jpg') == ('auto', (.5, .5))


def test_anadir_copia_sin_duplicar_ni_pisar_y_explica_lo_que_falla(tmp_path):
    fuera = tmp_path / 'Mis fotos'; fuera.mkdir(); otra = tmp_path / 'otra'; otra.mkdir()
    a = _jpeg(fuera / 'sala.jpg', _foto(100, 160))
    distinta = _jpeg(otra / 'sala.jpg', _foto(120, 160))       # mismo nombre, otra foto
    tif = fuera / 'plano.tif'; cv2.imencode('.tif', _foto(90, 160))[1].tofile(str(tif))
    (fuera / 'roto.png').write_bytes(b'no')
    galeria = g.Galeria(tmp_path / 'obra')
    dentro, avisos = galeria.anadir([a, a, distinta, tif, fuera / 'roto.png', fuera / 'falta.jpg'])
    assert dentro == ['sala.jpg', 'sala_2.jpg', 'plano.png']
    assert len(avisos) == 2 and 'roto.png' in avisos[0] and 'falta.jpg' in avisos[1]
    assert galeria.nombres() == ['plano.png', 'sala.jpg', 'sala_2.jpg']
    assert galeria.anadir([a])[0] == ['sala.jpg'] and len(galeria.nombres()) == 3      # ya estaba: no se duplica
    assert a.exists() and galeria.original('sala_2.jpg').shape[0] == 120


def test_encuadre_instantanea_y_quitar(tmp_path):
    galeria = g.Galeria(tmp_path / 'obra')
    nombre = galeria.instantanea(_foto(480, 640))
    assert nombre.startswith('instantanea_') and nombre.endswith('.jpg') and galeria.nombres() == [nombre]
    otra = galeria.instantanea(_foto(480, 640))
    assert otra != nombre                                       # dos en el mismo segundo no se pisan
    with pytest.raises(g.ErrorImagen):
        galeria.instantanea(None)
    galeria.fijar_ajuste(nombre, 'ajustar')
    assert galeria.imagen(nombre, OBJETIVO)[1] == 'ajustar' and galeria.imagen(otra, OBJETIVO)[1] == 'recortar'
    galeria.fijar_ajuste(nombre, 'recortar', (.5, .2))
    assert galeria.ajuste(nombre) == ('recortar', (.5, .2))
    galeria.elegir(nombre); galeria.recordar('camara', 1)
    galeria.quitar(nombre)
    assert galeria.nombres() == [otra] and (tmp_path / 'obra' / g.QUITADAS / nombre).is_file()   # no se borra
    assert galeria.seleccion() is None and galeria.ajuste(nombre) == ('auto', (.5, .5)) and galeria.recuerdo('camara') == 1
    estado = json.loads((tmp_path / 'obra' / g.ESTADO).read_text(encoding='utf8'))
    assert estado['actual'] == '' and nombre not in estado['ajustes']


def test_preparar_adaptada_no_cambia_el_rectangulo(tmp_path):
    from so101er import obra
    cfg = cargar()
    antes = [cfg.cuadro.sup_izq.copy(), cfg.cuadro.sup_der.copy(), cfg.cuadro.inf_izq.copy()]
    img, nombre = obra.preparar_adaptada(cfg, tmp_path / 'obra')
    assert nombre is None and g.perdida(img, OBJETIVO) < .002 and cfg.cuadro.imagen == ''      # cuadro de ejemplo
    galeria = g.Galeria(tmp_path / 'obra'); foto = galeria.instantanea(_foto(900, 600))        # vertical
    img, nombre = obra.preparar_adaptada(cfg, tmp_path / 'obra')
    assert nombre == foto and g.perdida(img, OBJETIVO) < .002 and cfg.cuadro.imagen.endswith(foto)
    for a, b in zip(antes, [cfg.cuadro.sup_izq, cfg.cuadro.sup_der, cfg.cuadro.inf_izq]):
        np.testing.assert_array_equal(a, b)
    cfg.cuadro.imagen = str(tmp_path / 'no_existe.png')        # ruta a mano que no se puede leer: cuadro de ejemplo
    img, nombre = obra.preparar_adaptada(cfg, tmp_path / 'obra')
    assert nombre is None and cfg.cuadro.imagen == '' and g.perdida(img, OBJETIVO) < .002


# ---------------------------------------------------------------- vídeo
def _espera(condicion, limite=8.):
    fin = time.perf_counter() + limite
    while time.perf_counter() < fin:
        if condicion():
            return True
        time.sleep(.02)
    return False


def test_fuente_de_video_lee_un_archivo_en_bucle_y_se_cierra(tmp_path):
    ruta = tmp_path / 'clip.avi'
    salida = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*'MJPG'), 50, (160, 120))
    if not salida.isOpened():
        pytest.skip('este OpenCV no puede escribir vídeo de prueba')
    for i in range(6):
        salida.write(np.full((120, 160, 3), 40 * i, np.uint8))
    salida.release()
    fuente = g.FuenteVideo(str(ruta))
    try:
        assert _espera(lambda: fuente.fotograma()[0] >= 9), fuente.error       # más fotogramas que el archivo: vuelve a empezar
        numero, fotograma = fuente.fotograma()
        assert fotograma.shape == (120, 160, 3) and fuente.error is None and not fuente.es_camara
        fuente.pausar(True); time.sleep(.15); n = fuente.fotograma()[0]; time.sleep(.2)
        assert fuente.en_pausa and fuente.fotograma()[0] == n                  # congelado
        relevo = g.FuenteVideo(str(ruta), tras=fuente)                         # espera a que la anterior suelte
        fuente.cerrar(esperar=False)
        assert _espera(lambda: relevo.fotograma()[0] >= 1), relevo.error
        relevo.cerrar()
        assert not relevo._hilo.is_alive() and not fuente._hilo.is_alive()
    finally:
        fuente.cerrar()


def test_fuente_de_video_que_no_abre_lo_dice_sin_lanzar(tmp_path):
    fuente = g.FuenteVideo(str(tmp_path / 'no_existe.mp4'))
    assert _espera(lambda: fuente.error is not None) and 'no_existe.mp4' in fuente.error
    assert fuente.fotograma() == (0, None)
    fuente.cerrar()


# ---------------------------------------------------------------- cambio en caliente
def _sesion():
    from so101er.aplicacion import SesionIntegrada
    avisos, llamadas = [], []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.closed, s.notificar, s.lock, s.proporcion = False, avisos.append, threading.RLock(), OBJETIVO
    s.cfg = cargar(); s.galeria = g.Galeria('obra'); s.imagen, s.imagen_nombre = g.adaptar(g.ejemplo(), OBJETIVO)[0], None
    s.interrumpir = lambda: llamadas.append('interrumpir')
    s.vision = SimpleNamespace(historia=[{'usuario': 'explica el sol'}])
    s.mundo = SimpleNamespace(cambiar_imagen=lambda img: llamadas.append(('mundo', img.shape)))
    def falla(img):
        raise RuntimeError('sin contexto gráfico')
    s.vista_panel = SimpleNamespace(cambiar_imagen=falla)
    return s, avisos, llamadas


def test_cambiar_imagen_corta_el_turno_vacia_el_contexto_y_no_toca_el_cuadro():
    s, avisos, llamadas = _sesion()
    rectangulo = [s.cfg.cuadro.sup_izq.copy(), s.cfg.cuadro.sup_der.copy(), s.cfg.cuadro.inf_izq.copy()]
    assert s.imagen_en_uso() is None and s.rotulo_imagen() == g.EJEMPLO
    nueva = g.adaptar(_foto(480, 640), OBJETIVO)[0]
    s.cambiar_imagen(nueva, 'sala.jpg')
    assert s.imagen is nueva and s.imagen_en_uso() == 'sala.jpg' and s.rotulo_imagen() == 'sala.jpg'
    assert s.vision.historia == [] and llamadas == ['interrumpir', ('mundo', nueva.shape)]
    assert any('conserva la imagen anterior: sin contexto gráfico' in a for a in avisos)        # la vista no impide el cambio
    assert any('Imagen cargada: sala.jpg' in a for a in avisos)
    for a, b in zip(rectangulo, [s.cfg.cuadro.sup_izq, s.cfg.cuadro.sup_der, s.cfg.cuadro.inf_izq]):
        np.testing.assert_array_equal(a, b)
    jpeg = cv2.imdecode(np.frombuffer(s.jpeg(), np.uint8), cv2.IMREAD_COLOR)                     # lo que recibe ER 2
    assert jpeg.shape[1] == 768 and g.perdida(jpeg, OBJETIVO) < .003
    s.cambiar_imagen(g.adaptar(g.ejemplo(), OBJETIVO)[0], None)
    assert s.imagen_en_uso() is None and s.cfg.cuadro.imagen == ''
    s.cfg.cuadro.imagen = 'C:/fuera/foto.png'
    assert s.imagen_en_uso() is False and s.rotulo_imagen() == 'foto.png'


def test_cambiar_imagen_rechaza_otra_proporcion_y_una_sesion_cerrada():
    s, avisos, llamadas = _sesion()
    with pytest.raises(ValueError, match='proporción'):
        s.cambiar_imagen(_foto(800, 800), 'cuadrada.jpg')
    with pytest.raises(ValueError):
        s.cambiar_imagen(None)
    assert llamadas == [] and s.imagen_nombre is None
    s.closed = True
    with pytest.raises(RuntimeError, match='cerrada'):
        s.cambiar_imagen(g.adaptar(_foto(480, 640), OBJETIVO)[0], 'sala.jpg')


def test_la_escena_3d_cambia_de_foto_sin_recompilar():
    mj = pytest.importorskip('mujoco')
    from so101er.hardware.mujoco_sim import MundoMuJoCo
    cfg = cargar()
    mundo = MundoMuJoCo(cfg, ['izq', 'der'], g.adaptar(g.ejemplo(), OBJETIVO)[0])
    try:
        m = mundo.modelo
        tex = mj.mj_name2id(m, mj.mjtObj.mjOBJ_TEXTURE, 'obra')
        alto, ancho, inicio = int(m.tex_height[tex]), int(m.tex_width[tex]), int(m.tex_adr[tex])
        roja = np.zeros((round(g.ANCHO * OBJETIVO), g.ANCHO, 3), np.uint8); roja[..., 2] = 255      # BGR
        assert mundo.cambiar_imagen(roja) == tex
        datos = m.tex_data[inicio:inicio + alto * ancho * 3].reshape(alto, ancho, 3)
        assert (datos[..., 0] == 255).all() and (datos[..., 1:] == 0).all()                        # RGB en la textura
        assert m.nq == mundo.datos.qpos.size                                                       # el modelo es el mismo
    finally:
        mundo.cerrar()


def test_la_vista_conjunta_dibuja_la_foto_nueva():
    pytest.importorskip('mujoco')
    from so101er.hardware.vista_dual import VistaDual
    cfg = cargar()
    poses = {'izq': np.zeros(6), 'der': np.zeros(6)}
    try:
        vista = VistaDual(cfg, g.adaptar(g.ejemplo(), OBJETIVO)[0])
    except Exception as e:
        pytest.skip(f'sin contexto gráfico: {e}')
    try:
        antes = vista.foto(poses).astype(int)
        roja = np.zeros((round(g.ANCHO * OBJETIVO), g.ANCHO, 3), np.uint8); roja[..., 2] = 255
        vista.cambiar_imagen(roja)
        despues = vista.foto(poses).astype(int)
        cambio = np.abs(despues - antes).sum(axis=2) > 60
        assert cambio.mean() > .03                                 # el cuadro del dibujo ha cambiado...
        assert (despues[cambio][:, 2] > despues[cambio][:, 1] + 40).mean() > .8   # ...y ahora es rojo
    finally:
        vista.cerrar()


# ---------------------------------------------------------------- ventana
def test_ventana_recorre_la_carpeta_aplica_y_recuerda_el_encuadre(raiz, tmp_path):
    from so101er.interfaz.ventana_imagenes import VentanaImagenes
    galeria = g.Galeria(tmp_path / 'obra')
    a = galeria.instantanea(_foto(480, 640)); (tmp_path / 'obra' / a).rename(tmp_path / 'obra/a.jpg')
    b = galeria.instantanea(_foto(900, 600)); (tmp_path / 'obra' / b).rename(tmp_path / 'obra/b.jpg')
    (tmp_path / 'obra/c.png').write_bytes(b'rota')
    usadas, en_uso = [], [None]
    def al_usar(nombre, imagen):
        usadas.append((nombre, imagen.shape)); en_uso[0] = nombre
    v = VentanaImagenes(raiz, galeria, OBJETIVO, lambda: en_uso[0], al_usar)
    try:
        assert v.entradas == [None, 'a.jpg', 'b.jpg', 'c.png'] and v.nombre is None and 'EN USO' in v.info.get()
        v.mover(-1)                                             # da la vuelta: la última, que no se puede leer
        assert v.nombre == 'c.png' and v.adaptada is None and 'disabled' in v.boton_usar.state()
        v.usar(); assert usadas == []
        v.mover(1); v.mover(1)
        assert v.nombre == 'a.jpg' and v.modo == 'recortar' and '640×480' in v.info.get() and 'EN USO' not in v.info.get()
        v.usar()
        assert usadas == [('a.jpg', (round(g.ANCHO * OBJETIVO), g.ANCHO, 3))] and 'EN USO' in v.info.get()
        v.cambiar_encuadre()                                    # recortada → entera
        assert v.modo == 'ajustar' and galeria.ajuste('a.jpg')[0] == 'ajustar' and 'Usar esta imagen' in v.aviso.get()
        v.cambiar_encuadre()
        # Arrastrar hacia abajo sube el recorte (se ve más de la parte de arriba de la foto).
        v._pulsar(SimpleNamespace(x=100, y=100)); v._arrastrar(SimpleNamespace(x=100, y=160)); v._soltar(SimpleNamespace(x=100, y=160))
        modo, centro = galeria.ajuste('a.jpg')
        assert modo == 'recortar' and centro[0] == .5 and centro[1] < .5
        v.mover(1)
        assert v.nombre == 'b.jpg' and v.modo == 'ajustar'      # vertical: entera con bandas
        v._pulsar(SimpleNamespace(x=10, y=10)); assert v._arrastre is None                       # sin recorte no se arrastra
    finally:
        v.cerrar()
    assert v.cerrada


def test_ventana_toma_una_instantanea_del_video_y_la_carga(raiz, tmp_path):
    from so101er.interfaz import ventana_imagenes as modulo
    ruta = tmp_path / 'clip.avi'
    salida = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*'MJPG'), 25, (320, 240))
    if not salida.isOpened():
        pytest.skip('este OpenCV no puede escribir vídeo de prueba')
    for _ in range(5):
        salida.write(_foto(240, 320))
    salida.release()
    galeria = g.Galeria(tmp_path / 'obra')
    usadas = []
    v = modulo.VentanaImagenes(raiz, galeria, OBJETIVO, lambda: None, lambda n, img: usadas.append(n))
    try:
        v.barra_galeria.pack_forget(); v.barra_video.pack()     # como «Vídeo en directo», pero con un archivo en vez de la cámara
        v._abrir_fuente(str(ruta))
        assert v.en_video
        v.mover(1); v.usar(); assert usadas == []               # en vídeo las flechas y «Usar» no hacen nada
        v.instantanea(); assert 'no hay imagen' in v.aviso.get() or usadas      # aún sin fotograma: lo dice
        assert _espera(lambda: v.fuente is None or v.fuente.fotograma()[1] is not None)
        if v.en_video:
            v.pausa(); assert v.fuente.en_pausa
            v.instantanea()
        assert not v.en_video and len(usadas) == 1 and usadas[0].startswith('instantanea_')
        assert galeria.nombres() == usadas and v.nombre == usadas[0]
        assert galeria.original(usadas[0]).shape == (240, 320, 3)               # se guarda el fotograma entero
    finally:
        v.cerrar()
