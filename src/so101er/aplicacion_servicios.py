"""Servicios de visión/diálogo, voz alineada y micrófono de la aplicación."""
from pathlib import Path
import base64
import io
import json
import os
import re
import threading
import urllib.request
import wave
import numpy as np

from .idiomas import IDIOMAS,POR_DEFECTO,ErrorIdioma,elegir_idioma_hablado,fuera_de_idioma,instrucciones,unidades


def claves(ruta=None):
    names=('GEMINI_API_KEY','GOOGLE_API_KEY','ELEVENLABS_API_KEY','ELEVENLABS_VOICE_ID')+tuple(
        'ELEVENLABS_VOICE_ID_'+codigo.upper() for codigo in IDIOMAS)     # una voz por idioma, si se quiere
    result={k:os.getenv(k,'') for k in names}
    if ruta and Path(ruta).is_file():
        for line in Path(ruta).read_text(encoding='utf-8-sig').splitlines():
            k,sep,v=line.partition('='); k=k.strip()
            if sep and k in result and not result[k]:result[k]=v.strip().strip('"').strip("'")
    return result


def aplanar(valor):
    """Los números de una lista con cualquier anidamiento, en orden. Lo que no sea número o lista se ignora."""
    if isinstance(valor,(list,tuple)):return [n for v in valor for n in aplanar(v)]
    return [valor] if isinstance(valor,(int,float)) and not isinstance(valor,bool) else []


def bloques_completos(texto):
    """Los objetos JSON ya terminados dentro de la lista "bloques" de una respuesta que aún se está escribiendo."""
    i=texto.find('[',texto.find('"bloques"')) if '"bloques"' in texto else -1
    if i<0:return []
    salida=[];prof=0;ini=None;cadena=False;escape=False
    for j in range(i+1,len(texto)):
        c=texto[j]
        if cadena:
            if escape:escape=False
            elif c=='\\':escape=True
            elif c=='"':cadena=False
            continue
        if c=='"':cadena=True
        elif c=='{':
            if prof==0:ini=j
            prof+=1
        elif c=='}':
            prof-=1
            if prof==0 and ini is not None:salida.append(texto[ini:j+1]);ini=None
        elif c==']' and prof==0:break
    return salida


def validar_bloques(data,idioma=POR_DEFECTO):
    blocks=data.get('bloques') if isinstance(data,dict) else None
    if not isinstance(blocks,list) or not 1<=len(blocks)<=6:raise ValueError('respuesta sin bloques válidos')
    for b in blocks:
        if not isinstance(b,dict) or not isinstance(b.get('texto'),str) or not 1<=len(b['texto'])<=500:
            raise ValueError('texto de bloque inválido')
        if 'grafico' in b or 'apoyo' in b:
            # Lo que escribe la IA: «grafico» (el movimiento que dibuja el concepto) y «apoyo» (el segundo concepto), cada
            # uno con su palabra. Dentro del programa son «movimiento» y «otro».
            from .control import expresion
            biblioteca=expresion.disponibles()
            if b.get('tipo')=='gesto' and 'movimiento' not in b:
                grafico,apoyo,ancla_apoyo=b.get('grafico'),b.get('apoyo'),b.get('ancla_apoyo')
                if grafico not in biblioteca and apoyo in biblioteca:      # solo vale el de apoyo: pasa a ser el principal
                    grafico,apoyo=apoyo,None
                    if type(ancla_apoyo)==int:b['ancla']=ancla_apoyo
                b['movimiento']=grafico
                if apoyo is not None:
                    b['otro']=apoyo
                    if ancla_apoyo is not None:b['ancla_otro']=ancla_apoyo
            elif b.get('tipo') in ('senalar','region','camino') and 'otro' not in b and b.get('grafico') is not None:
                b['otro']=b['grafico']
                if b.get('ancla_grafico') is not None:b['ancla_otro']=b['ancla_grafico']
            for campo in ('grafico','apoyo','ancla_apoyo','ancla_grafico'):b.pop(campo,None)
        if b.get('tipo')=='gesto':
            # Un movimiento de la biblioteca (docs/PROTOCOLO_EXPRESIVO.md) y, si aporta, otro a la vez en el otro brazo.
            from .control import expresion
            biblioteca=expresion.disponibles()
            if b.get('movimiento') not in biblioteca:raise ValueError('movimiento desconocido')
            otro=b.get('otro')
            if otro is not None and (otro not in biblioteca or expresion.de_dos_brazos(biblioteca[otro])
                                     or expresion.de_dos_brazos(biblioteca[b['movimiento']])):
                b.pop('otro')                                     # el segundo movimiento no vale: se hace solo el principal
        elif b.get('tipo') not in ('senalar','region','paisaje','cielo','camino'):raise ValueError('gesto desconocido')
        elif b.get('otro') is not None:
            # Mientras un brazo señala o recorre, el otro puede dibujar un movimiento de un brazo de la biblioteca.
            from .control import expresion
            biblioteca=expresion.disponibles()
            if b['tipo'] in ('paisaje','cielo') or b['otro'] not in biblioteca or expresion.de_dos_brazos(biblioteca[b['otro']]):b.pop('otro')
        if b.get('brazo') not in ('izq','der'):raise ValueError('brazo desconocido')
        from .geometria import validar_punto
        if b['tipo']=='senalar':validar_punto(b.get('punto'))
        if b['tipo']=='region':
            value=b.get('region')
            if isinstance(value,dict):
                if all(k in value for k in ('ymin','xmin','ymax','xmax')):
                    value=[value[k] for k in ('ymin','xmin','ymax','xmax')]
                elif all(k in value for k in ('y_min','x_min','y_max','x_max')):
                    value=[value[k] for k in ('y_min','x_min','y_max','x_max')]
            numeros=aplanar(value)
            # La IA anida a veces mal los cuatro números ([ymin, xmin, [ymax, xmax]]). Si son cuatro, valen igual.
            region=np.array(numeros,float) if len(numeros)==4 else np.array(value,float)
            if region.shape==(4,):region=region.reshape(2,2)
            if region.shape!=(2,2):raise ValueError('región inválida')
            for p in region:validar_punto(p)
            region=np.array([region.min(axis=0),region.max(axis=0)])
            if (region[1]<=region[0]).any():raise ValueError('región sin área')
            b['region']=region.tolist()
        anchor=b.get('ancla',0);units=len(unidades(b['texto'],idioma))
        if IDIOMAS[idioma].por_caracteres and type(anchor)==int and units:
            # Contar caracteres no es el fuerte de la IA: un ancla algo pasada se lleva al último carácter.
            anchor=b['ancla']=min(max(anchor,0),units-1)
        if type(anchor)!=int or not 0<=anchor<units:raise ValueError('ancla inválida')
        # La palabra del segundo movimiento. Si falta o no vale, los dos movimientos coinciden en el tiempo.
        if 'otro' not in b or type(b.get('ancla_otro'))!=int or not 0<=b['ancla_otro']<units:b.pop('ancla_otro',None)
    return blocks


INSTRUCCIONES_VISION='''Eres una guía de una imagen que se expresa con dos brazos SO-101.
«RESPONDE»
«LONGITUD»
y vuelven a reposo antes del siguiente. Ancla el gesto en una palabra relevante cerca de la mitad de la frase.
Devuelve JSON {"bloques":[{"texto":"...","tipo":"senalar","brazo":"der","punto":[y,x],"ancla":0}]}.
Coordenadas [y,x] de 0 a 1000 SOBRE LA IMAGEN proporcionada (imagen rectificada al cuadro).
Si la imagen tiene bandas grises lisas en los bordes, son relleno: no las describas ni señales dentro de ellas.
Tipos: senalar (punto), region (region:[[ymin,xmin],[ymax,xmax]]), paisaje (abanico horizontal),
cielo (abanico elevado), camino (recorrido expresivo recto). Usa region para abarcar áreas reales.
«ANCLA» No inventes objetos ni distancias 3D.
Elige brazo por posición del referente. La ejecución local decide la cinemática y sus límites.
No incluyas ángulos de motores. Para un camino curvo explica que la representación es esquemática.
Ejemplo de región: «EJEMPLO».
Para tipo region es obligatorio incluir region con cuatro números en dos pares; nunca una descripción textual.
'''


def biblioteca_ia():
    """Lista de movimientos de la biblioteca que se añade a las instrucciones. Vacía si no hay registro."""
    from .control import expresion
    return expresion.texto_para_ia()


def instrucciones_vision(idioma=POR_DEFECTO):
    """Instrucciones para la IA en el idioma del turno. En español, las de siempre."""
    partes=instrucciones(idioma);texto=INSTRUCCIONES_VISION
    for marca,clave in (('«RESPONDE»','responde'),('«LONGITUD»','longitud'),('«ANCLA»','ancla'),('«EJEMPLO»','ejemplo')):
        texto=texto.replace(marca,partes[clave])
    return texto


def bloques_en_idioma(texto_json,idioma):
    """Bloques válidos y escritos en el idioma del turno. `ErrorIdioma` si alguna frase está en otro."""
    blocks=validar_bloques(json.loads(texto_json),idioma)
    otras=fuera_de_idioma((b['texto'] for b in blocks),idioma)
    if otras:raise ErrorIdioma('texto que no está en '+IDIOMAS[idioma].nombre+': '+otras[0][:80])
    return blocks


class Vision:
    def __init__(self,keys,modelo='gemini-robotics-er-2-preview'):
        from google import genai
        key=keys['GEMINI_API_KEY'] or keys['GOOGLE_API_KEY']
        if not key:raise RuntimeError('falta GEMINI_API_KEY; configura el archivo .env')
        self.client=genai.Client(api_key=key,http_options={'api_version':'v1beta','timeout':25000})
        self.modelo=modelo; self.historia=[]

    def responder(self,texto,jpeg,estado,idioma=POR_DEFECTO):
        """Bloques de texto y gesto, escritos en `idioma`. Nunca devuelve frases en otro idioma:
        si la IA no lo respeta se le pide una vez que lo corrija y, si sigue igual, el turno falla."""
        from google.genai import types
        nombre=IDIOMAS[idioma].nombre;prompt=instrucciones_vision(idioma)+biblioteca_ia()
        recordatorio='' if idioma==POR_DEFECTO else '\nRecuerda: los campos "texto", solo en '+nombre+'.'
        context=json.dumps(self.historia[-6:],ensure_ascii=False)
        response=self.client.models.generate_content(model=self.modelo,
            contents=[types.Part.from_bytes(data=jpeg,mime_type='image/jpeg'),
                      prompt+'\nContexto:'+context+'\nEstado sensorial:'+json.dumps(estado)+'\nPetición:'+texto+recordatorio],
            config=types.GenerateContentConfig(response_mime_type='application/json',temperature=.35,
                         max_output_tokens=900,
                         thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)))
        self.ultima_respuesta=response.text
        try:blocks=bloques_en_idioma(response.text,idioma)
        except (ValueError,TypeError) as error:
            if isinstance(error,ErrorIdioma):
                arreglo=('\nLos campos "texto" de este JSON tienen que estar en '+nombre+'. Reescríbelos enteros en '+nombre+
                         ', conserva tipo, brazo y coordenadas, y recalcula ancla. Error: ')
            else:arreglo='\nCorrige solo el formato de este JSON. Error: '
            repair=self.client.models.generate_content(model=self.modelo,
                contents=[types.Part.from_bytes(data=jpeg,mime_type='image/jpeg'),prompt+arreglo+str(error)+'\n'+response.text],
                config=types.GenerateContentConfig(response_mime_type='application/json',temperature=0.,max_output_tokens=900,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)))
            self.ultima_respuesta=repair.text
            en_otro=RuntimeError('la IA no ha respondido en '+nombre+' ni al pedírselo otra vez; no se dice nada. Repite la petición')
            try:blocks=bloques_en_idioma(repair.text,idioma)
            except ErrorIdioma:raise en_otro from error
            except (ValueError,TypeError):
                raw=json.loads(repair.text);candidates=raw.get('bloques',[]) if isinstance(raw,dict) else []
                blocks=[{'texto':b['texto'],'tipo':'sin_gesto','brazo':'izq','ancla':0}
                        for b in candidates if isinstance(b,dict) and isinstance(b.get('texto'),str) and 1<=len(b['texto'])<=500]
                if not 1<=len(blocks)<=6:raise ValueError('la IA no devolvió texto ni coordenadas válidos') from error
                if fuera_de_idioma((b['texto'] for b in blocks),idioma):raise en_otro from error
        self.historia.extend([{'usuario':texto},{'respuesta':' '.join(b['texto'] for b in blocks)}])
        return blocks


def _por_bloques(self,texto,jpeg,estado,idioma=POR_DEFECTO):
    """Como `responder`, pero entrega cada bloque en cuanto la IA termina de escribirlo, para empezar
    a hablar con el primero. Mantiene la misma garantía: ninguna frase en otro idioma llega a decirse.

    Un bloque con las coordenadas mal se narra sin gesto en vez de pedir la respuesta otra vez. Una
    frase en otro idioma detiene la entrega: se pide el resto corregido y, si insiste, el turno falla.
    """
    from google.genai import types
    nombre=IDIOMAS[idioma].nombre;prompt=instrucciones_vision(idioma)+biblioteca_ia()
    recordatorio='' if idioma==POR_DEFECTO else '\nRecuerda: los campos "texto", solo en '+nombre+'.'
    context=json.dumps(self.historia[-6:],ensure_ascii=False)
    ajustes=dict(response_mime_type='application/json',max_output_tokens=900,
                 thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL))
    imagen=types.Part.from_bytes(data=jpeg,mime_type='image/jpeg')
    entregados=[];acumulado='';en_otro=None
    def uno(crudo):
        """Bloque válido a partir de su JSON; sin gesto si solo falla el gesto; ErrorIdioma si el texto está en otro idioma."""
        dato=json.loads(crudo)
        try:bloque=validar_bloques({'bloques':[dato]},idioma)[0]
        except (ValueError,TypeError):
            if not isinstance(dato,dict) or not isinstance(dato.get('texto'),str) or not 1<=len(dato['texto'])<=500:raise
            bloque={'texto':dato['texto'],'tipo':'sin_gesto','brazo':'izq','ancla':0}
        if fuera_de_idioma([bloque['texto']],idioma):raise ErrorIdioma('texto que no está en '+nombre+': '+bloque['texto'][:80])
        return bloque
    try:
        flujo=self.client.models.generate_content_stream(model=self.modelo,
            contents=[imagen,prompt+'\nContexto:'+context+'\nEstado sensorial:'+json.dumps(estado)+'\nPetición:'+texto+recordatorio],
            config=types.GenerateContentConfig(temperature=.35,**ajustes))
        for trozo in flujo:
            acumulado+=trozo.text or ''
            if en_otro is not None:continue                       # ya se sabe que hay que corregir: solo se termina de leer
            listos=bloques_completos(acumulado)
            while len(entregados)<min(len(listos),6):
                try:bloque=uno(listos[len(entregados)])
                except ErrorIdioma as error:en_otro=error;break
                except (ValueError,TypeError):listos.pop(len(entregados));continue     # bloque inservible: se salta
                entregados.append(bloque);yield bloque
        self.ultima_respuesta=acumulado
        if en_otro is None and not entregados:
            # Nada reconocible por el camino (otra forma de JSON): se trata la respuesta entera, como siempre.
            try:
                for bloque in bloques_en_idioma(acumulado,idioma):entregados.append(bloque);yield bloque
            except ErrorIdioma as error:en_otro=error
            except (ValueError,TypeError) as error:
                raise ValueError('la IA no devolvió texto ni coordenadas válidos') from error
        if en_otro is not None:
            repair=self.client.models.generate_content(model=self.modelo,
                contents=[imagen,prompt+'\nLos campos "texto" de este JSON tienen que estar en '+nombre+'. Reescríbelos enteros en '+nombre+
                          ', conserva tipo, brazo y coordenadas, y recalcula ancla. Error: '+str(en_otro)+'\n'+acumulado],
                config=types.GenerateContentConfig(temperature=0.,**ajustes))
            self.ultima_respuesta=repair.text
            fallo=RuntimeError('la IA no ha respondido en '+nombre+' ni al pedírselo otra vez; no se dice nada más. Repite la petición')
            try:corregidos=[uno(crudo) for crudo in bloques_completos(repair.text)]
            except (ValueError,TypeError):raise fallo from en_otro
            for bloque in corregidos[len(entregados):6]:entregados.append(bloque);yield bloque
            if not entregados:raise fallo from en_otro
    finally:
        if entregados:self.historia.extend([{'usuario':texto},{'respuesta':' '.join(b['texto'] for b in entregados)}])


Vision.por_bloques=_por_bloques


def voz_de_windows(cultura):
    """Nombre de una voz instalada en Windows para esa cultura («en-», «fr-»…), o None."""
    import subprocess
    try:
        salida=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
            'Add-Type -AssemblyName System.Speech;(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()|'
            'Where-Object{$_.Enabled}|ForEach-Object{$_.VoiceInfo.Culture.Name+"|"+$_.VoiceInfo.Name}'],
            capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout
    except (OSError,subprocess.SubprocessError):return None
    for linea in salida.splitlines():
        codigo,_,nombre=linea.partition('|')
        if codigo.lower().startswith(cultura.lower()) and nombre.strip():return nombre.strip()
    return None


def motivo_http(error):
    """(estado, mensaje) legibles de un rechazo HTTP. ElevenLabs explica el motivo en el cuerpo de la respuesta."""
    estado,mensaje='',''
    try:
        detalle=json.loads(error.read().decode('utf8','replace')).get('detail')
        if isinstance(detalle,dict):estado,mensaje=str(detalle.get('status') or detalle.get('code') or ''),str(detalle.get('message') or '')
        elif detalle:mensaje=str(detalle)
    except (ValueError,OSError,AttributeError):pass
    return estado,mensaje or str(error)


class Voz:
    def __init__(self,keys,proveedor='elevenlabs',voces=None):
        """`voces` es la tabla [conversacion.voces] de la configuración: {código de idioma: Voice ID}."""
        self.keys=keys;self.proveedor=proveedor;self.local=None;self.locales={}
        self.voces={str(k):str(v).strip() for k,v in (voces or {}).items() if str(v).strip()}
        self.voces_fuera=set()    # idiomas cuya voz propia esta cuenta no puede usar: van con la general
        self.sin_credito=None     # motivo por el que ElevenLabs dejó de servir en esta sesión
        self.aviso=None           # algo que contar al operador una vez; lo recoge la sesión
        if proveedor=='local':
            from .sincronia.voz_sintetizada import SintetizadorWindows
            self.local=self.locales[POR_DEFECTO]=SintetizadorWindows()

    def _local(self,idioma):
        """Voz de Windows para ese idioma. Solo hay las que estén instaladas en el equipo."""
        if idioma not in self.locales:
            from .sincronia.voz_sintetizada import SintetizadorWindows
            nombre=voz_de_windows(IDIOMAS[idioma].cultura)
            if not nombre:raise RuntimeError('no hay ninguna voz de Windows instalada en '+IDIOMAS[idioma].nombre+'; usa la voz de ElevenLabs')
            self.locales[idioma]=SintetizadorWindows(voz=nombre)
        return self.locales[idioma]

    def sintetizar(self,texto,idioma=POR_DEFECTO,al_trozo=None):
        """Audio de `texto` leído en `idioma`: el mismo idioma en que se pidió el texto a la IA.

        Con `al_trozo`, ElevenLabs entrega la voz por trozos y se llama a `al_trozo(muestras, marcas)` con
        cada uno según llega (el primero, en unas décimas de segundo); `marcas` son las de toda la frase
        hasta ese momento. Las demás voces lo llaman una vez con todo. Devuelve siempre el audio completo
        y sus marcas.
        """
        if al_trozo is None:return self._sintetizar(texto,idioma,None)
        entregado=[False]
        def trozo(muestras,marcas):
            entregado[0]=True;al_trozo(muestras,marcas)
        resultado=self._sintetizar(texto,idioma,trozo)
        if not entregado[0]:al_trozo(resultado[0],resultado[1])
        return resultado

    def _sintetizar(self,texto,idioma,al_trozo):
        if self.local:
            audio,marks=self._local(idioma).sintetizar(texto)
            # Las marcas de SAPI son offsets de caracteres. Si faltan, se declara estimación.
            return audio,marks,'SAPI' if marks else 'estimación'
        if self.sin_credito:return self._de_windows(texto,idioma)
        if not self.keys.get('ELEVENLABS_API_KEY'):raise RuntimeError('falta la clave de ElevenLabs; selecciona voz local')
        voice,general=self.voz_de(idioma),self.keys.get('ELEVENLABS_VOICE_ID','')
        if not voice:raise RuntimeError('falta el Voice ID de ElevenLabs para este idioma ('+IDIOMAS[idioma].nombre+')')
        try:audio,marks=self._pedir(voice,texto,idioma,al_trozo)
        except urllib.error.HTTPError as error:
            estado,mensaje=motivo_http(error)
            if 'quota' in estado.lower():return self._sin_credito(mensaje,texto,idioma)
            rechazo=RuntimeError(f'ElevenLabs ha rechazado la voz ({error.code}): {mensaje}')
            if voice==general or not general:raise rechazo from None
            # Puede ser que esta cuenta no tenga acceso a la voz propia de este idioma: se prueba con la general.
            try:audio,marks=self._pedir(general,texto,idioma,al_trozo)
            except urllib.error.HTTPError as otro:
                estado2,mensaje2=motivo_http(otro)
                if 'quota' in estado2.lower():return self._sin_credito(mensaje2,texto,idioma)
                raise rechazo from None                           # tampoco con la general: el problema no es la voz
            self.voces_fuera.add(idioma)
            self.aviso=('La voz de ElevenLabs para '+IDIOMAS[idioma].nombre+' no se puede usar ('+mensaje+
                        '). Se usa la voz general hasta que reinicies el programa.')
        return audio,marks,'alineación ElevenLabs'

    def preparar(self):
        """Usa una vez cada voz de ElevenLabs, en segundo plano, con una sílaba.

        La primera petición con una voz de la biblioteca tarda de 10 a 13 s (medido el 15-11-2026); las
        siguientes, medio segundo. Hacerla al abrir la sesión evita que esa espera caiga en la primera
        frase de cada idioma. Gasta unos pocos créditos por sesión y cualquier fallo se ignora.
        """
        if self.local or self.sin_credito or not self.keys.get('ELEVENLABS_API_KEY'):return []
        silabas={'es':'Sí.','en':'Yes.','de':'Ja.','fr':'Oui.','zh':'好。'}
        def una(voice,idioma):
            try:self._pedir(voice,silabas.get(idioma,'A.'),idioma)
            except Exception:pass
        hilos=[]
        for voice,idioma in {self.voz_de(i):i for i in IDIOMAS if self.voz_de(i)}.items():
            hilos.append(threading.Thread(target=una,args=(voice,idioma),daemon=True,name='voz-preparada'));hilos[-1].start()
        return hilos

    def voz_de(self,idioma):
        """Voice ID de ElevenLabs para un idioma: primero la tabla [conversacion.voces] de la configuración,
        después la variable ELEVENLABS_VOICE_ID_<CÓDIGO> y, si no hay ninguna, la voz general."""
        general=self.keys.get('ELEVENLABS_VOICE_ID','')
        if idioma in self.voces_fuera:return general
        return self.voces.get(idioma) or self.keys.get('ELEVENLABS_VOICE_ID_'+idioma.upper()) or general

    def _pedir(self,voice,texto,idioma,al_trozo=None):
        """(audio, marcas) de ElevenLabs. Con `al_trozo`, por trozos: cada uno se entrega según llega."""
        url=(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}/'+('stream/' if al_trozo else '')+
             'with-timestamps?output_format=pcm_24000')
        request=urllib.request.Request(url,json.dumps({'text':texto,'model_id':'eleven_flash_v2_5',
            'language_code':IDIOMAS[idioma].eleven}).encode(),headers={'xi-api-key':self.keys['ELEVENLABS_API_KEY'],
                                                    'Content-Type':'application/json'})
        partes=[];marks=[];index=[0]
        def anotar(data):
            a=data.get('normalized_alignment') or data.get('alignment') or {}
            for char,t in zip(a.get('characters') or [],a.get('character_start_times_seconds') or []):
                marks.append((index[0],float(t)));index[0]+=len(char)
        with urllib.request.urlopen(request,timeout=25) as r:
            if al_trozo is None:
                data=json.load(r);partes.append(np.frombuffer(base64.b64decode(data['audio_base64']),dtype='<i2'));anotar(data)
            else:
                resto=b''
                for linea in r:                                   # una línea JSON por trozo de medio segundo
                    if not linea.strip():continue
                    data=json.loads(linea);crudo=resto+base64.b64decode(data.get('audio_base64') or '')
                    resto=crudo[len(crudo)//2*2:];muestras=np.frombuffer(crudo[:len(crudo)//2*2],dtype='<i2')
                    anotar(data)
                    if len(muestras):
                        partes.append(muestras);al_trozo(muestras,marks)
        audio=np.concatenate(partes).copy() if partes else np.zeros(0,np.int16)
        return audio,marks

    def _sin_credito(self,mensaje,texto,idioma):
        # Sin crédito: el robot no se queda mudo. Se sigue con la voz de Windows hasta reiniciar el programa.
        self.sin_credito=mensaje
        self.aviso='ElevenLabs no tiene crédito ('+mensaje+'). Se usa la voz de Windows hasta que reinicies el programa.'
        return self._de_windows(texto,idioma)

    def _de_windows(self,texto,idioma):
        """Voz instalada en Windows, como relevo de ElevenLabs. Da el instante de cada palabra."""
        try:audio,marks=self._local(idioma).sintetizar(texto)
        except Exception as e:
            raise RuntimeError('ElevenLabs no tiene crédito y la voz de Windows no está disponible: '+str(e)) from None
        return audio,marks,'voz de Windows; ElevenLabs sin crédito'

    def cerrar(self):
        for local in self.locales.values():local.cerrar()


def tiempo_ancla(texto,index,marks,duracion,idioma=POR_DEFECTO):
    words=unidades(texto,idioma)
    if not 0<=index<len(words):raise ValueError('ancla fuera de frase')
    char=words[index]
    if marks:
        # SAPI: marcas discretas por palabra; ElevenLabs: por carácter.
        return min(marks,key=lambda m:abs(m[0]-char))[1]
    return duracion*char/max(len(texto),1)


class Microfono:
    def __init__(self):self.stream=None;self.chunks=[];self.modelo=None;self.lock=threading.Lock()
    def empezar(self):
        import sounddevice as sd
        self.chunks=[]
        def callback(data,frames,t,status):
            with self.lock:
                if sum(len(c) for c in self.chunks)<16000*20:self.chunks.append(data.copy())
        self.stream=sd.InputStream(samplerate=16000,channels=1,dtype='float32',callback=callback)
        self.stream.start()
    def terminar(self):
        if self.stream:self.stream.abort();self.stream.close();self.stream=None
        with self.lock:return np.concatenate(self.chunks).ravel() if self.chunks else np.zeros(0,np.float32)
    def transcribir(self,audio,carpeta,actual=POR_DEFECTO):
        """(texto, idioma) de lo hablado. Todo en este equipo.

        El idioma se elige entre los cuatro con lo que estima el propio modelo, y solo cambia
        respecto a `actual` si otro gana con claridad. Después se transcribe forzando ese idioma:
        el texto y el idioma de la conversación salen de la misma decisión.
        """
        if len(audio)<1600:return '',actual
        if self.modelo is None:
            from faster_whisper import WhisperModel
            local=Path(carpeta).parent/'whisper_base'
            if not (local/'model.bin').is_file():raise RuntimeError('modelo local Whisper base no instalado')
            self.modelo=WhisperModel(str(local),device='cpu',compute_type='int8',local_files_only=True)
        idioma=actual
        try:idioma=elegir_idioma_hablado(dict(self.modelo.detect_language(audio=audio,vad_filter=True)[2]),actual)
        except Exception:pass                                # sin estimación se sigue en el idioma de la conversación
        i=IDIOMAS[idioma]
        segments,_=self.modelo.transcribe(audio,language=i.whisper,beam_size=3,vad_filter=True,initial_prompt=i.apunte)
        return ('' if i.por_caracteres else ' ').join(s.text.strip() for s in segments),idioma

