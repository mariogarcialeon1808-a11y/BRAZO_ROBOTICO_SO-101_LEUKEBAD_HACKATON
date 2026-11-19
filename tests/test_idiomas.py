"""Idioma de la conversación: detección local, un único idioma por turno y nada de mezclas. Sin red ni hardware."""
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from so101er import idiomas as I
from so101er import aplicacion_servicios as S

CASOS = {
    'es': ['hola', 'gracias', 'explica el cuadro', '¿qué ves?', 'que ves', 'y el sol', 'dime qué hay a la izquierda',
           'cuéntame algo más', 'quién pintó esto', 'la casa', 'buenos días', 'puedes señalar el árbol',
           'vale, ahora en español', 'sí', 'háblame de los colores', 'donde esta el lago', 'me gusta mucho',
           'que significa', 'explicame la imagen', 'Hello, ¿puedes explicar el cuadro?'],
    'en': ['hello', 'thanks', 'explain the painting', 'what do you see?', 'and the sun', 'tell me what is on the left',
           'tell me more', 'who painted this', 'the house', 'good morning', 'can you point at the tree',
           'ok, now in english', 'yes', 'talk about the colours', 'where is the lake', 'i like it a lot', "what's that",
           'describe the picture', "it's beautiful", 'please continue'],
    'fr': ['bonjour', 'merci', 'explique le tableau', "qu'est-ce que tu vois ?", 'que vois-tu', 'et le soleil',
           "dis-moi ce qu'il y a à gauche", 'raconte-moi plus', 'qui a peint ça', 'la maison', 'le soleil',
           "peux-tu montrer l'arbre", "d'accord, maintenant en français", 'oui', 'parle-moi des couleurs',
           'où est le lac', "j'aime beaucoup", "c'est quoi", "décris l'image", 'non'],
    'de': ['hallo', 'danke', 'erkläre das Bild', 'was siehst du?', 'und die Sonne', 'sag mir, was links ist',
           'erzähl mir mehr', 'wer hat das gemalt', 'das Haus', 'guten Morgen', 'kannst du auf den Baum zeigen',
           'ok, jetzt auf Deutsch', 'ja', 'sprich über die Farben', 'wo ist der See', 'das gefällt mir sehr',
           'was ist das', 'beschreibe das Bild', 'es ist schön', 'nein'],
    'zh': ['你好', '谢谢', '请解释这幅画', '你看到了什么?', '太阳呢', '左边有什么', '再多说一点', '这是谁画的', '房子', '好',
           '请用中文介绍 SO-101'],
    None: ['ok', 'no', 'si', 'photo', 'image', 'robot', '123', '...', 'es', 'color', 'describe', 'こんにちは',
           'ciao come stai', 'a', '', '   '],
}


@pytest.mark.parametrize('esperado,texto', [(k, t) for k, v in CASOS.items() for t in v])
def test_detectar_reconoce_los_cuatro_idiomas_y_calla_ante_la_duda(esperado, texto):
    assert I.detectar(texto) == esperado, I.puntuar(texto)


def test_unidades_son_palabras_salvo_en_chino_que_son_caracteres():
    assert I.unidades('Observa este punto.') == [0, 8, 13] == I.unidades('Observa este punto.', 'en')
    assert I.unidades('请看 这个。', 'zh') == [0, 1, 3, 4, 5]                      # el espacio no cuenta
    assert I.ancla_de('Observa este punto del cuadro.', 'punto') == 2
    assert I.ancla_de('请看画面上的这个位置。', '这个', 'zh') == 6
    for clave in I.FRASES:
        for idioma in I.IDIOMAS:
            texto, ancla = I.frase(clave, idioma)
            assert I.detectar(texto) == idioma and 0 < ancla < len(I.unidades(texto, idioma))
    assert I.frase('punto') == ('Observa este punto del cuadro.', 2) and I.frase('region') == ('Observa esta región del cuadro.', 2)


def test_la_demo_existe_en_los_cuatro_idiomas_y_en_espanol_no_ha_cambiado():
    from so101er.aplicacion import demo_bloques
    es = demo_bloques()
    assert [b['ancla'] for b in es] == [4, 11, 14, 11] and es[0]['texto'].startswith('Este paisaje se extiende ampliamente')
    assert es[2] == {'texto': 'Ahora observa con atención la parte derecha del cuadro: este punto concreto corresponde al sol, '
                              'que se encuentra por encima de la casa.', 'tipo': 'senalar', 'brazo': 'der', 'punto': [200, 780], 'ancla': 14}
    for idioma in I.IDIOMAS:
        bloques = demo_bloques(idioma)
        assert S.validar_bloques({'bloques': [dict(b) for b in bloques]}, idioma)             # formato y anclas válidos
        assert [{k: v for k, v in b.items() if k not in ('texto', 'ancla')} for b in bloques] == \
               [{k: v for k, v in b.items() if k not in ('texto', 'ancla')} for b in es]      # los mismos gestos
        assert not I.fuera_de_idioma((b['texto'] for b in bloques), idioma)
        otros = [o for o in I.IDIOMAS if o != idioma]
        assert all(len(I.fuera_de_idioma((b['texto'] for b in bloques), o)) == 4 for o in otros)   # y en ningún otro


def test_en_idioma_solo_rechaza_lo_que_esta_claramente_en_otro():
    assert I.en_idioma('El sol amarillo ilumina la casa que está a la derecha.', 'es')
    assert not I.en_idioma('The yellow sun lights the house that is on the right.', 'es')
    assert not I.en_idioma('Le soleil jaune éclaire la maison qui est à droite.', 'en')
    assert not I.en_idioma('太阳在房子的上方。', 'fr') and I.en_idioma('太阳在房子的上方。', 'zh')
    assert not I.en_idioma('The sun is above the house.', 'zh') and not I.en_idioma('太阳 is above the house on the right', 'zh')
    assert I.en_idioma('SO-101', 'fr') and I.en_idioma('Monet, 1872.', 'es') and I.en_idioma('', 'en')     # lo dudoso pasa
    assert I.en_idioma('画面里有 SO-101 机器人。', 'zh')                                                    # un nombre propio no estorba


ANTES = '''Eres una guía de una imagen que se expresa con dos brazos SO-101.
Responde en español, en 1 a 4 bloques de una frase. Diseña texto y gesto juntos.
Cada bloque debe tener 20–30 palabras de descripción útil: los brazos hacen un gesto amplio
y vuelven a reposo antes del siguiente. Ancla el gesto en una palabra relevante cerca de la mitad de la frase.
Devuelve JSON {"bloques":[{"texto":"...","tipo":"senalar","brazo":"der","punto":[y,x],"ancla":0}]}.
Coordenadas [y,x] de 0 a 1000 SOBRE LA IMAGEN proporcionada (imagen rectificada al cuadro).
Si la imagen tiene bandas grises lisas en los bordes, son relleno: no las describas ni señales dentro de ellas.
Tipos: senalar (punto), region (region:[[ymin,xmin],[ymax,xmax]]), paisaje (abanico horizontal),
cielo (abanico elevado), camino (recorrido expresivo recto). Usa region para abarcar áreas reales.
ancla es índice de palabra separado por espacios, desde 0. No inventes objetos ni distancias 3D.
Elige brazo por posición del referente. La ejecución local decide la cinemática y sus límites.
No incluyas ángulos de motores. Para un camino curvo explica que la representación es esquemática.
Ejemplo de región: {"texto":"El campo verde ocupa la franja inferior del dibujo.","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":2}.
Para tipo region es obligatorio incluir region con cuatro números en dos pares; nunca una descripción textual.
'''


def test_las_instrucciones_en_espanol_son_las_de_siempre_y_las_demas_fijan_el_idioma():
    assert S.instrucciones_vision() == S.instrucciones_vision('es') == ANTES
    for idioma, nombre in (('en', 'inglés (English)'), ('de', 'alemán (Deutsch)'), ('fr', 'francés (Français)'), ('zh', 'chino (中文)')):
        texto = S.instrucciones_vision(idioma)
        assert f'Responde en {nombre}' in texto and 'Responde en español' not in texto and 'No mezcles idiomas' in texto
        ejemplo = json.loads(I.EJEMPLO[idioma])
        assert I.detectar(ejemplo['texto']) == idioma and S.validar_bloques({'bloques': [ejemplo]}, idioma)
    assert 'caracteres chinos' in S.instrucciones_vision('zh') and 'índice de palabra' not in S.instrucciones_vision('zh')
    assert 'índice de palabra' in S.instrucciones_vision('en')


def _bloque(texto, ancla=2):
    return {'texto': texto, 'tipo': 'senalar', 'brazo': 'der', 'punto': [200, 780], 'ancla': ancla}


DE = 'Die gelbe Sonne ist der hellste Punkt des Bildes und sie steht genau über dem kleinen Haus auf der rechten Seite.'
EN = 'The yellow sun is the brightest point of the picture and it sits just above the small house on the right.'
ES = 'El sol amarillo es el punto más brillante del cuadro y está justo encima de la casa pequeña de la derecha.'
FR = 'Le soleil jaune est le point le plus brillant du tableau et il se trouve juste au-dessus de la petite maison.'
ZH = '黄色的太阳是画面中最明亮的地方，它就在右边那座小房子的正上方。'


def test_el_ancla_cuenta_palabras_o_caracteres_y_en_chino_no_se_sale():
    assert S.validar_bloques({'bloques': [_bloque(EN, 20)]}, 'en')[0]['ancla'] == 20
    with pytest.raises(ValueError, match='ancla'):
        S.validar_bloques({'bloques': [_bloque(EN, 21)]}, 'en')
    assert S.validar_bloques({'bloques': [_bloque(ZH, 3)]}, 'zh')[0]['ancla'] == 3
    assert S.validar_bloques({'bloques': [_bloque(ZH, 400)]}, 'zh')[0]['ancla'] == len(ZH) - 1    # pasada: al último carácter
    with pytest.raises(ValueError, match='ancla'):
        S.validar_bloques({'bloques': [_bloque(ZH, 3)]}, 'es')                                    # en español sería una sola «palabra»
    marcas = [(i, i * .2) for i in range(len(ZH))]
    assert S.tiempo_ancla(ZH, 3, marcas, 10, 'zh') == pytest.approx(.6)
    assert S.tiempo_ancla('Observa este punto.', 1, [(0, 0), (8, .5), (13, 1)], 2) == .5          # como antes
    with pytest.raises(ValueError):
        S.tiempo_ancla(ZH, 3, marcas, 10, 'es')
    assert S.bloques_en_idioma(json.dumps({'bloques': [_bloque(FR)]}), 'fr')
    with pytest.raises(I.ErrorIdioma, match='francés'):
        S.bloques_en_idioma(json.dumps({'bloques': [_bloque(FR), _bloque(ES)]}), 'fr')            # una frase en otro idioma: mezcla


# ---------------------------------------------------------------- la IA
class Cliente:
    def __init__(self, *respuestas):
        self.respuestas, self.peticiones = list(respuestas), []
        self.models = self
    def generate_content(self, model, contents, config):
        self.peticiones.append(contents[1])
        return SimpleNamespace(text=self.respuestas.pop(0))


def _vision(*respuestas):
    pytest.importorskip('google.genai')
    v = S.Vision.__new__(S.Vision)
    v.client, v.modelo, v.historia = Cliente(*respuestas), 'falso', []
    return v


def _json(*textos):
    return json.dumps({'bloques': [_bloque(t) for t in textos]}, ensure_ascii=False)


def test_la_ia_recibe_el_idioma_del_turno_y_su_respuesta_se_comprueba():
    v = _vision(_json(EN))
    assert v.responder('what is that?', b'jpeg', {}, 'en')[0]['texto'] == EN
    pedido = v.client.peticiones[0]
    assert 'Responde en inglés (English)' in pedido and pedido.endswith('Petición:what is that?\nRecuerda: los campos "texto", solo en inglés.')
    v = _vision(_json(ES))
    assert v.responder('¿qué es eso?', b'jpeg', {})[0]['texto'] == ES
    assert v.client.peticiones[0].startswith(ANTES) and v.client.peticiones[0].endswith('Petición:¿qué es eso?')     # español: intacto
    v = _vision(_json(ZH))
    assert v.responder('那是什么?', b'jpeg', {}, 'zh')[0]['texto'] == ZH


def test_el_aleman_es_un_idioma_mas_de_principio_a_fin():
    assert list(I.IDIOMAS) == ['es', 'en', 'de', 'fr', 'zh'] and I.IDIOMAS['de'].propio == 'Deutsch'
    assert I.frase('punto', 'de') == ('Schauen Sie auf diesen Punkt im Bild.', 4)
    assert I.en_idioma(DE, 'de') and not I.en_idioma(DE, 'en') and not I.en_idioma(EN, 'de') and not I.en_idioma(ES, 'de')
    v = _vision(_json(DE))
    assert v.responder('was ist das?', b'jpeg', {}, 'de')[0]['texto'] == DE
    assert 'Responde en alemán (Deutsch)' in v.client.peticiones[0]
    v = _vision(_json(EN), _json(DE))                                      # contesta en inglés: se le pide en alemán
    assert v.responder('was ist das?', b'jpeg', {}, 'de')[0]['texto'] == DE
    assert 'tienen que estar en alemán' in v.client.peticiones[1]


def test_si_la_ia_contesta_en_otro_idioma_se_le_pide_que_lo_corrija():
    v = _vision(_json(ES), _json(EN))
    assert v.responder('what is that?', b'jpeg', {}, 'en')[0]['texto'] == EN
    assert 'tienen que estar en inglés' in v.client.peticiones[1] and 'Corrige solo el formato' not in v.client.peticiones[1]
    assert v.historia[-1] == {'respuesta': EN}
    v = _vision(_json(EN, ES), _json(EN, EN))                                # una sola frase fuera también cuenta
    assert [b['texto'] for b in v.responder('tell me', b'jpeg', {}, 'en')] == [EN, EN]


def test_si_insiste_en_otro_idioma_el_turno_falla_y_no_se_dice_nada():
    v = _vision(_json(ES), _json(ES))
    with pytest.raises(RuntimeError, match='no ha respondido en francés'):
        v.responder('qu’est-ce que c’est ?', b'jpeg', {}, 'fr')
    assert v.historia == []
    # Formato roto y, al repararlo, texto sin coordenadas pero en otro idioma: tampoco se narra.
    v = _vision('{"bloques": [{"texto": "x"', json.dumps({'bloques': [{'texto': ES}]}))
    with pytest.raises(RuntimeError, match='no ha respondido en inglés'):
        v.responder('what is that?', b'jpeg', {}, 'en')
    v = _vision('{"bloques": [{"texto": "x"', json.dumps({'bloques': [{'texto': EN}]}))
    assert v.responder('what is that?', b'jpeg', {}, 'en')[0]['tipo'] == 'sin_gesto'       # en el idioma correcto sí se narra


# ---------------------------------------------------------------- voz y micrófono
def test_la_voz_se_pide_en_el_idioma_del_turno(monkeypatch):
    import base64
    enviados = []
    class Respuesta:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({'audio_base64': base64.b64encode(np.zeros(240, '<i2').tobytes()).decode(),
                               'alignment': {'characters': list('太阳'), 'character_start_times_seconds': [0, .2]}}).encode()
    def abrir(peticion, timeout):
        enviados.append(json.loads(peticion.data)); return Respuesta()
    monkeypatch.setattr(S.urllib.request, 'urlopen', abrir)
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'y'})
    audio, marcas, tipo = voz.sintetizar('太阳', 'zh')
    voz.sintetizar('The sun', 'en'); voz.sintetizar('Le soleil', 'fr'); voz.sintetizar('El sol')
    assert [e['language_code'] for e in enviados] == ['zh', 'en', 'fr', 'es'] and enviados[0]['text'] == '太阳'
    assert marcas == [(0, 0.), (1, .2)] and len(audio) == 240


def test_sin_credito_en_elevenlabs_se_habla_con_la_voz_de_windows_y_se_dice(monkeypatch):
    import io
    peticiones = []
    def abrir(peticion, timeout):
        peticiones.append(1)
        cuerpo = json.dumps({'detail': {'status': 'quota_exceeded', 'message': 'You have 4 credits remaining'}}).encode()
        raise S.urllib.error.HTTPError(peticion.full_url, 401, 'Unauthorized', {}, io.BytesIO(cuerpo))
    monkeypatch.setattr(S.urllib.request, 'urlopen', abrir)
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'y'})
    dicho = []
    voz.locales['es'] = SimpleNamespace(sintetizar=lambda texto: (dicho.append(texto), (np.zeros(2400, np.int16), [(0, 0.), (3, .1)]))[1], cerrar=lambda: None)
    audio, marcas, tipo = voz.sintetizar('El sol.')
    assert len(audio) == 2400 and marcas == [(0, 0.), (3, .1)] and tipo == 'voz de Windows; ElevenLabs sin crédito'
    assert 'no tiene crédito (You have 4 credits remaining)' in voz.aviso and 'voz de Windows' in voz.aviso
    voz.aviso = None
    voz.sintetizar('Otra frase.')
    assert peticiones == [1] and dicho == ['El sol.', 'Otra frase.'] and voz.aviso is None      # ya no vuelve a preguntar ni a avisar
    monkeypatch.setattr(S, 'voz_de_windows', lambda cultura: None)
    with pytest.raises(RuntimeError, match='ElevenLabs no tiene crédito y la voz de Windows no está disponible.*francés'):
        voz.sintetizar('Le soleil.', 'fr')                              # sin voz instalada en ese idioma: lo dice y no habla


def test_otros_rechazos_de_elevenlabs_se_explican_con_su_motivo(monkeypatch):
    import io
    def abrir(peticion, timeout):
        cuerpo = json.dumps({'detail': {'status': 'invalid_api_key', 'message': 'Invalid API key'}}).encode()
        raise S.urllib.error.HTTPError(peticion.full_url, 401, 'Unauthorized', {}, io.BytesIO(cuerpo))
    monkeypatch.setattr(S.urllib.request, 'urlopen', abrir)
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'y'})
    with pytest.raises(RuntimeError, match=r'ElevenLabs ha rechazado la voz \(401\): Invalid API key'):
        voz.sintetizar('El sol.')
    assert voz.sin_credito is None and voz.aviso is None               # una clave mala no se tapa con la voz de Windows


def _eleven(monkeypatch, rechazadas=()):
    """Sustituye la llamada a ElevenLabs: apunta qué voz se pide y rechaza las que se indiquen."""
    import base64, io
    pedidas = []
    class Respuesta:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({'audio_base64': base64.b64encode(np.zeros(240, '<i2').tobytes()).decode(),
                               'alignment': {'characters': ['a'], 'character_start_times_seconds': [0]}}).encode()
    def abrir(peticion, timeout):
        voz = peticion.full_url.split('/text-to-speech/')[1].split('/')[0]
        pedidas.append((voz, json.loads(peticion.data)['language_code']))
        if voz in rechazadas:
            cuerpo = json.dumps({'detail': {'status': 'voice_not_found', 'message': 'A voice with that ID was not found'}}).encode()
            raise S.urllib.error.HTTPError(peticion.full_url, 404, 'Not Found', {}, io.BytesIO(cuerpo))
        return Respuesta()
    monkeypatch.setattr(S.urllib.request, 'urlopen', abrir)
    return pedidas


def test_cada_idioma_usa_su_voz_tabla_luego_variable_luego_la_general(monkeypatch):
    pedidas = _eleven(monkeypatch)
    claves = {'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'general', 'ELEVENLABS_VOICE_ID_FR': 'variable-fr',
              'ELEVENLABS_VOICE_ID_DE': 'variable-de'}
    voz = S.Voz(claves, voces={'de': 'tabla-de', 'zh': ' tabla-zh ', 'en': ''})
    assert [voz.voz_de(i) for i in ('es', 'en', 'de', 'fr', 'zh')] == ['general', 'general', 'tabla-de', 'variable-fr', 'tabla-zh']
    for idioma in ('de', 'fr', 'zh', 'es'):
        voz.sintetizar('texto', idioma)
    assert pedidas == [('tabla-de', 'de'), ('variable-fr', 'fr'), ('tabla-zh', 'zh'), ('general', 'es')]
    assert S.Voz(claves).voz_de('de') == 'variable-de'                     # sin tabla manda la variable
    sin_voz = S.Voz({'ELEVENLABS_API_KEY': 'x'}, voces={'en': 'solo-en'})
    assert sin_voz.voz_de('en') == 'solo-en'
    with pytest.raises(RuntimeError, match=r'falta el Voice ID de ElevenLabs para este idioma \(francés\)'):
        sin_voz.sintetizar('texto', 'fr')
    with pytest.raises(RuntimeError, match='falta la clave de ElevenLabs'):
        S.Voz({'ELEVENLABS_VOICE_ID': 'general'}).sintetizar('texto')


def test_si_la_voz_de_un_idioma_no_se_puede_usar_se_sigue_con_la_general(monkeypatch):
    pedidas = _eleven(monkeypatch, rechazadas={'voz-fr'})
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'general'}, voces={'fr': 'voz-fr', 'en': 'voz-en'})
    audio, marcas, tipo = voz.sintetizar('Le soleil.', 'fr')
    assert pedidas == [('voz-fr', 'fr'), ('general', 'fr')] and len(audio) == 240 and tipo == 'alineación ElevenLabs'
    assert 'voz de ElevenLabs para francés no se puede usar (A voice with that ID was not found)' in voz.aviso
    voz.aviso = None
    voz.sintetizar('Encore.', 'fr'); voz.sintetizar('The sun.', 'en')
    assert pedidas[2:] == [('general', 'fr'), ('voz-en', 'en')] and voz.aviso is None      # no vuelve a probar la que falla; las demás, intactas
    # Si tampoco vale la general, el problema no es la voz del idioma: se dice el rechazo original.
    pedidas = _eleven(monkeypatch, rechazadas={'voz-fr', 'general'})
    voz = S.Voz({'ELEVENLABS_API_KEY': 'x', 'ELEVENLABS_VOICE_ID': 'general'}, voces={'fr': 'voz-fr'})
    with pytest.raises(RuntimeError, match=r'ElevenLabs ha rechazado la voz \(404\)'):
        voz.sintetizar('Le soleil.', 'fr')
    assert voz.voces_fuera == set() and voz.aviso is None


def test_las_voces_por_idioma_se_leen_del_entorno_y_del_archivo_de_claves(tmp_path, monkeypatch):
    for nombre in ('ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_ID', 'ELEVENLABS_VOICE_ID_DE', 'ELEVENLABS_VOICE_ID_FR', 'ELEVENLABS_VOICE_ID_ZH'):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv('ELEVENLABS_VOICE_ID_ZH', 'del-entorno')
    archivo = tmp_path / '.env'
    archivo.write_text('ELEVENLABS_API_KEY=clave\nELEVENLABS_VOICE_ID = "general"\nELEVENLABS_VOICE_ID_DE=voz-de\n'
                       'ELEVENLABS_VOICE_ID_FR: voz-fr\nELEVENLABS_VOICE_ID_ZH=del-archivo\n', encoding='utf8')
    k = S.claves(archivo)
    assert k['ELEVENLABS_VOICE_ID'] == 'general' and k['ELEVENLABS_VOICE_ID_DE'] == 'voz-de'
    assert k['ELEVENLABS_VOICE_ID_FR'] == ''                               # una línea con «:» en vez de «=» no cuenta
    assert k['ELEVENLABS_VOICE_ID_ZH'] == 'del-entorno'                    # el entorno manda sobre el archivo
    from so101er.config import cargar
    voces = cargar().conversacion['voces']
    assert set(voces) == set(I.IDIOMAS) and all(len(v) == 20 for v in voces.values())      # una voz para cada idioma


def test_idioma_hablado_solo_cambia_si_otro_gana_con_claridad():
    elegir = I.elegir_idioma_hablado
    assert elegir({'en': .9, 'es': .05}, 'es') == 'en'
    assert elegir({'en': .5, 'es': .45}, 'es') == 'es'                # casi empate: se queda
    assert elegir({'pt': .7, 'es': .2, 'en': .02}, 'en') == 'es'      # entre los nuestros gana el español con claridad
    assert elegir({'pt': .9, 'es': .05, 'en': .04}, 'en') == 'en'     # demasiado poco para cambiar
    assert elegir({'it': .99}, 'fr') == 'fr' and elegir({}, 'zh') == 'zh'      # un idioma que no es de los nuestros no cambia nada
    assert elegir({'de': .9, 'en': .05}, 'es') == 'de'
    assert elegir({'zh': .8, 'ja': .15}, 'es') == 'zh' and elegir({'fr': .97}, 'fr') == 'fr'


def test_el_microfono_transcribe_en_el_idioma_que_decide_y_lo_devuelve():
    llamadas = []
    class Modelo:
        def __init__(self, probabilidades): self.p = probabilidades
        def detect_language(self, audio, vad_filter):
            if self.p is None: raise RuntimeError('sin estimación')
            return 'xx', 0., list(self.p.items())
        def transcribe(self, audio, language, beam_size, vad_filter, initial_prompt):
            llamadas.append((language, initial_prompt))
            return [SimpleNamespace(text=' uno '), SimpleNamespace(text=' dos ')], None
    m = S.Microfono(); audio = np.zeros(16000, np.float32)
    assert m.transcribir(np.zeros(100, np.float32), None, 'fr') == ('', 'fr')                 # nada que oír: no cambia nada
    m.modelo = Modelo({'en': .9, 'es': .05})
    assert m.transcribir(audio, None, 'es') == ('uno dos', 'en')
    m.modelo = Modelo({'zh': .95})
    assert m.transcribir(audio, None, 'en') == ('unodos', 'zh')                               # el chino no lleva espacios
    m.modelo = Modelo({'en': .5, 'es': .5})
    assert m.transcribir(audio, None, 'es') == ('uno dos', 'es')
    m.modelo = Modelo(None)
    assert m.transcribir(audio, None, 'fr') == ('uno dos', 'fr')                              # sin estimación: el de la conversación
    assert llamadas == [('en', None), ('zh', I.IDIOMAS['zh'].apunte), ('es', None), ('fr', None)]


# ---------------------------------------------------------------- la sesión
def _sesion():
    from so101er.aplicacion import SesionIntegrada
    avisos, turnos = [], []
    s = SesionIntegrada.__new__(SesionIntegrada)
    s.notificar, s.lock, s.ticket, s.cancel = avisos.append, threading.RLock(), 0, threading.Event()
    s.bloqueo = lambda: None; s.interrumpir = lambda: None
    s._turno = lambda *a: turnos.append(a)
    return s, avisos, turnos


def _espera(turnos, n):
    fin = time.perf_counter() + 2
    while len(turnos) < n and time.perf_counter() < fin:
        time.sleep(.005)
    assert len(turnos) == n


def test_la_conversacion_sigue_al_idioma_de_cada_peticion_y_no_cambia_por_dudas():
    s, avisos, turnos = _sesion()
    assert s.idioma == 'es'                                                 # español por defecto
    pasos = [('explica el cuadro', None, 'es'), ('ok', None, 'es'), ('what is on the left?', None, 'en'), ('ok', None, 'en'),
             ('', None, 'en'),                                             # un clic en el cuadro: sin texto, mismo idioma
             ('123', None, 'en'), ('et le soleil ?', None, 'fr'), ('photo', None, 'fr'), ('太阳在哪里?', None, 'zh'),
             ('lo que sea', 'en', 'en'),                                    # lo hablado trae su idioma: manda sobre el texto
             ('hola de nuevo', None, 'es')]
    for i, (texto, hablado, esperado) in enumerate(pasos, 1):
        s.enviar(texto, [] if not texto else None, idioma=hablado)
        _espera(turnos, i)
        assert s.idioma == esperado and turnos[-1][0] == texto and turnos[-1][4] == esperado, texto
    assert [a for a in avisos if a.startswith('Idioma')] == [f'Idioma de la conversación: {n}.' for n in
                                                             ('inglés', 'francés', 'chino', 'inglés', 'español')]
    assert s.fijar_idioma('fr') is True and s.fijar_idioma('fr') is False and s.fijar_idioma('it') is False and s.idioma == 'fr'


def test_con_el_control_detenido_una_peticion_no_cambia_el_idioma():
    s, avisos, turnos = _sesion()
    s.bloqueo = lambda: 'Control detenido'
    s.enviar('what is on the left?')
    assert s.idioma == 'es' and turnos == [] and avisos == ['Control detenido']


def test_el_turno_lleva_su_idioma_a_la_ia_y_a_la_voz_aunque_la_conversacion_cambie():
    from so101er.aplicacion import SesionIntegrada
    s, avisos, _ = _sesion()
    visto = {}
    s.control = SimpleNamespace(frenada=None, error=None, parar=lambda: None)
    s.real = False; s.brazos = {}; s.desplegar = lambda: 0.; s.jpeg = lambda: b''; s.estado = lambda: {}
    s.modelo, s.keys, s.dataset, s._seguimiento = 'falso', {}, 'seg', None
    def responder(texto, jpeg, estado, idioma):
        visto['ia'] = idioma; s.idioma = 'es'                               # la conversación cambia a mitad de turno
        return [{'texto': FR, 'tipo': 'sin_gesto', 'brazo': 'izq', 'ancla': 0}]
    def sintetizar(texto, idioma):
        visto['voz'] = (texto, idioma); raise RuntimeError('fin de la prueba')
    def al_momento(f, *a):                                                  # como el hilo de la voz, pero sin hilo
        f(*a)
    s.vision = SimpleNamespace(responder=responder)
    s.voz = SimpleNamespace(sintetizar=sintetizar)
    s.pool = SimpleNamespace(submit=al_momento)
    SesionIntegrada._turno(s, 'et le soleil ?', None, threading.Event(), 0, 'fr')
    assert visto == {'ia': 'fr', 'voz': (FR, 'fr')} and any('fin de la prueba' in a for a in avisos)
