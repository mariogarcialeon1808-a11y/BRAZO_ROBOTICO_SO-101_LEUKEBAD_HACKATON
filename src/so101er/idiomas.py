"""Idioma de la conversación: español, inglés, alemán, francés y chino. Todo local y sin dependencias.

Hay un único idioma por turno y se decide aquí, en este equipo, antes de llamar a nadie:

- Texto escrito → `detectar`. Si no está claro (una palabra que vale en dos idiomas, un número,
  un idioma que no es de los nuestros), devuelve None y la conversación sigue en el que estaba.
- Voz → `elegir_idioma_hablado`, con las probabilidades que da el modelo local de reconocimiento.
- Respuesta de la IA → `en_idioma` comprueba que cada frase está en el idioma del turno antes de
  que se sintetice o se mueva nada. No se traduce: la IA escribe directamente en ese idioma, y si
  no lo hace se le pide que lo corrija o el turno falla, pero nunca se dice una mezcla.

No se traduce en local a propósito: traducir la respuesta cambiaría el orden de las palabras y
con él la palabra a la que está anclado cada gesto.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

POR_DEFECTO = "es"


@dataclass(frozen=True)
class Idioma:
    codigo: str
    nombre: str           # en español, para avisos e instrucciones a la IA
    propio: str           # como se llama a sí mismo, para el selector
    eleven: str           # language_code de ElevenLabs
    whisper: str          # código del modelo de reconocimiento
    cultura: str          # prefijo de las voces de Windows
    por_caracteres: bool = False      # el ancla cuenta caracteres en vez de palabras
    apunte: str | None = None         # texto de arranque para el reconocimiento de voz


IDIOMAS = {
    "es": Idioma("es", "español", "Español", "es", "es", "es-"),
    "en": Idioma("en", "inglés", "English", "en", "en", "en-"),
    "de": Idioma("de", "alemán", "Deutsch", "de", "de", "de-"),
    "fr": Idioma("fr", "francés", "Français", "fr", "fr", "fr-"),
    "zh": Idioma("zh", "chino", "中文", "zh", "zh", "zh-", por_caracteres=True, apunte="以下是普通话的句子。"),
}


class ErrorIdioma(ValueError):
    """Un texto no está en el idioma del turno."""


# ------------------------------------------------------------------ unidades del ancla
def unidades(texto: str, idioma: str = POR_DEFECTO) -> list[int]:
    """Posición en el texto de cada unidad a la que se puede anclar un gesto.

    En español, inglés y francés son las palabras separadas por espacios (como siempre). En chino
    no hay espacios entre palabras: cada carácter que no sea un espacio es una unidad.
    """
    patron = r"\S" if IDIOMAS[idioma].por_caracteres else r"\S+"
    return [m.start() for m in re.finditer(patron, texto)]


def ancla_de(texto: str, fragmento: str, idioma: str = POR_DEFECTO) -> int:
    """Índice de la unidad donde empieza `fragmento` dentro de `texto`."""
    posicion = texto.index(fragmento)
    return max(0, sum(1 for inicio in unidades(texto, idioma) if inicio <= posicion) - 1)


# ------------------------------------------------------------------ detección en texto
def _conjunto(palabras: str) -> frozenset[str]:
    return frozenset(palabras.split())


PALABRAS = {
    "es": _conjunto("""
        el la los las un una unos unas de del al y o pero porque que qué como cómo cuando cuándo donde dónde
        quien quién cual cuál cuales es son está están estoy estás eres soy somos era fue ser estar hay tiene
        tienen tengo tienes puedes puede pueden puedo podemos quiero quieres quiere queremos hacer hace hacen
        haz dime dinos di explica explícame explicar cuenta cuéntame describe descríbeme muestra muéstrame
        enseña enséñame señala mira ver veo ves vemos esto esta este estos estas eso esa ese aquí ahí allí
        muy más menos también tampoco sí no ni ya aún todavía ahora luego después antes hoy siempre nunca con
        sin para por sobre entre hasta desde hacia en mi mis tu tus su sus nuestro nuestra me te se nos le les
        lo yo tú él ella nosotros ellos ellas usted ustedes hola buenas buenos días tardes noches adiós gracias
        favor vale bien mal cuadro pintura imagen foto fotografía dibujo obra color colores arriba abajo
        izquierda derecha centro fondo cielo sol árbol casa montaña montañas lago persona personas gente cosa
        cosas algo nada todo todos toda todas otra otro vez mismo parte lado significa pintó cuánto cuántos
        cuántas robot brazo brazos a habla hablas hablar español otra sabes sabe dices dice decir ayuda
        gusta gustan mucho mucha muchos muchas poco bonito bonita grande pequeño bueno buena nuevo nueva
        creo pienso parece puede fueron había tenía quiero gustaría podría podrías cuál cuáles porqué
        """),
    "en": _conjunto("""
        the a an and or but because that what which who whom whose how when where why is are am was were be
        been being have has had do does did can could will would shall should may might must i you he she it
        we they me him her us them my your his its our their this these those here there very more less also
        too not no yes if then than so just now today always never with without for from to of in on at by
        about into over under between up down left right hello hi hey goodbye bye thanks thank please
        good bad well picture painting image photo photograph drawing artwork color colour colors colours sky
        sun tree house mountain mountains lake person people thing things something nothing everything all
        other another same part side explain tell show describe point look see mean means meaning painted
        many much robot arm arms english speak talk say know help let want like love think looks seems
        big small nice beautiful new old really maybe could would there's
        """),
    "fr": _conjunto("""
        le la les un une des du de au aux et ou mais parce que qui quoi quel quelle quels quelles comment
        quand où pourquoi est sont suis es êtes sommes était être avoir a ont ai as avons avez fait faire
        fais peux peut pouvez pouvons veux veut voulez dis dites explique expliquez expliquer raconte montre
        montrez décris décrivez regarde regardez voir vois voit voyez ce cet cette ces ceci cela ça ici là
        très plus moins aussi oui non ne pas ni déjà encore maintenant puis après avant toujours jamais avec
        sans pour par sur sous entre depuis vers dans en mon ma mes ton ta tes son sa ses notre nos votre vos
        leur leurs je tu il elle on nous vous ils elles me te se lui moi toi bonjour salut bonsoir revoir
        merci plaît plait accord bien mal tableau peinture image photo photographie dessin œuvre oeuvre
        couleur couleurs haut bas gauche droite centre fond ciel soleil arbre maison montagne montagnes lac
        personne personnes gens chose choses quelque rien tout tous toute toutes autre même partie côté
        signifie combien robot bras français parle parlez parler sais savez dire aide y si
        aime aimes beaucoup peu joli jolie grand grande petit petite beau belle nouveau nouvelle bon bonne
        crois pense semble pourrais pourriez voudrais chose
        """),
}
PALABRAS["de"] = _conjunto("""
    der die das den dem des ein eine einen einem einer eines und oder aber weil dass was wer wie wann wo warum
    welche welcher welches ist sind bin bist seid war waren sein haben hat habe hast habt hatte kann kannst
    können könnt will willst wollen möchte möchtest soll sollen muss müssen wird werden ich du er sie es wir
    ihr mich mir dich dir ihn ihm uns euch mein meine dein deine sein seine unser unsere dies diese dieser
    dieses diesen hier dort da sehr mehr weniger auch nicht nein ja kein keine wenn dann als so nur jetzt
    heute immer nie mit ohne für von zu zum zur aus bei nach vor über unter zwischen auf an am im in um bis
    oben unten links rechts mitte hallo tschüss danke bitte guten gute morgen tag abend nacht gut schlecht
    bild gemälde foto zeichnung kunstwerk farbe farben himmel sonne baum haus berg berge see person leute
    mensch menschen ding dinge etwas nichts alles alle andere anderen gleiche teil seite erkläre erklären
    erklär erzähl erzähle erzählen zeig zeige zeigen beschreibe beschreiben schau schaue schauen sieh siehst
    sehe sehen sieht bedeutet gemalt viele viel roboter arm arme deutsch sprich sprechen sag sage sagen weiß
    weißt hilf hilfe mag gefällt denke glaube scheint groß klein schön neu alt wirklich vielleicht noch
    einmal gibt man also doch mal bitte
    """)
# «si» también es español (condicional) y «a» también inglés y francés: pertenecer a varios no decide nada.
PALABRAS["es"] |= _conjunto("si son")
PALABRAS["fr"] |= _conjunto("son")
PALABRAS["en"] |= _conjunto("son")

LETRAS = {"es": ("ñ¿¡", 2.0, "áíóú", 1.0), "fr": ("çœæ", 2.0, "èêëîïôûùâà", 1.0), "de": ("ßäö", 2.0, "ü", 1.0)}
ELISION_FR = frozenset("l d j qu c n s m t jusqu lorsqu puisqu".split())
CONTRACCION_EN = frozenset("s t re ll m ve d".split())
TERMINACIONES = {
    "es": ("ción", "ciones", "dad", "ando", "iendo", "mente"),
    "en": ("ing", "ly", "ness", "ful", "ght"),
    "fr": ("eau", "eaux", "eux", "oir", "ais", "ait", "ez", "ée", "ées"),
    "de": ("ung", "ungen", "keit", "heit", "lich", "isch", "chen", "schaft"),
}
_PALABRA = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)*")


def _han(c: str) -> bool:
    return "一" <= c <= "鿿" or "㐀" <= c <= "䶿"


def _recuento(texto: str) -> tuple[int, int, int]:
    """(caracteres chinos, kana japoneses, letras de otros alfabetos)."""
    han = sum(1 for c in texto if _han(c))
    kana = sum(1 for c in texto if "぀" <= c <= "ヿ")
    letras = sum(1 for c in texto if c.isalpha() and not _han(c) and not "぀" <= c <= "ヿ")
    return han, kana, letras


def puntuar(texto: str) -> dict[str, float]:
    """Indicios de español, inglés y francés en un texto. Solo sirve para comparar entre ellos."""
    texto = texto.lower().replace("’", "'").replace("`", "'")
    puntos = {k: 0.0 for k in PALABRAS}
    for idioma, (fuertes, peso_fuerte, suaves, peso_suave) in LETRAS.items():
        puntos[idioma] += min(4.0, peso_fuerte * sum(texto.count(c) for c in fuertes))
        puntos[idioma] += min(3.0, peso_suave * sum(texto.count(c) for c in suaves))
    for palabra in _PALABRA.findall(texto):
        trozos = palabra.split("'")
        if len(trozos) > 1:
            if trozos[0] in ELISION_FR:                           # l'arbre, c'est, qu'est-ce
                puntos["fr"] += 2.0
            elif trozos[-1] in CONTRACCION_EN:                    # it's, don't, we're
                puntos["en"] += 1.5
        for trozo in trozos:
            conocida = False
            for idioma, lista in PALABRAS.items():
                if trozo in lista:
                    puntos[idioma] += 1.0
                    conocida = True
            if not conocida and len(trozo) > 3:
                for idioma, finales in TERMINACIONES.items():
                    if trozo.endswith(finales):
                        puntos[idioma] += 0.4
    return puntos


def detectar(texto: str, minimo: float = 1.0) -> str | None:
    """Idioma de un texto entre los cuatro, o None si no se puede asegurar.

    None no es un error: significa «no cambies de idioma por esto». `minimo` es cuántos indicios
    hacen falta: uno basta para seguir a quien escribe «hello»; para rechazar una respuesta se piden más.
    """
    han, kana, letras = _recuento(texto)
    if han and not kana and han / (han + letras) >= 0.25:
        return "zh"
    if kana or not letras:
        return None
    orden = sorted(puntuar(texto).items(), key=lambda par: -par[1])
    (mejor, p1), (_, p2) = orden[0], orden[1]
    return mejor if p1 >= minimo and p1 - p2 >= max(0.8, 0.15 * p1) else None


def en_idioma(texto: str, idioma: str) -> bool:
    """False solo si el texto está claramente en otro idioma. Lo dudoso se da por bueno."""
    han, kana, letras = _recuento(texto)
    if idioma == "zh":
        return (han + letras == 0) or (han > 0 and not kana and han / (han + letras) >= 0.5)
    if han + kana > max(1, 0.05 * letras):                        # caracteres chinos en una frase que no es china
        return False
    hallado = detectar(texto, minimo=3.0)                         # hacen falta varios indicios para rechazar
    return hallado is None or hallado == idioma


def fuera_de_idioma(textos, idioma: str) -> list[str]:
    """Los textos que no están en el idioma del turno."""
    return [t for t in textos if not en_idioma(t, idioma)]


# ------------------------------------------------------------------ idioma hablado
def elegir_idioma_hablado(probabilidades: dict[str, float], actual: str = POR_DEFECTO) -> str:
    """Idioma en que se va a transcribir lo hablado.

    `probabilidades` es lo que estima el modelo local para cada idioma que conoce (casi cien).
    Solo se comparan los cuatro nuestros, y solo se cambia si otro gana con claridad: una frase
    corta o con ruido no debe cambiar el idioma de la conversación.
    """
    nuestras = {k: float(probabilidades.get(v.whisper, 0.0)) for k, v in IDIOMAS.items()}
    total = sum(nuestras.values())
    mejor = max(nuestras, key=nuestras.get)
    if mejor != actual and total > 0 and nuestras[mejor] >= 0.15 and nuestras[mejor] / total >= 0.6:
        return mejor
    return actual


# ------------------------------------------------------------------ textos que dice el programa
FRASES = {
    "punto": {"es": ("Observa este punto del cuadro.", "punto"), "en": ("Look at this point in the picture.", "point"),
              "de": ("Schauen Sie auf diesen Punkt im Bild.", "Punkt"),
              "fr": ("Regardez ce point du tableau.", "point"), "zh": ("请看画面上的这个位置。", "这个")},
    "region": {"es": ("Observa esta región del cuadro.", "región"), "en": ("Look at this area of the picture.", "area"),
               "de": ("Schauen Sie auf diesen Bereich im Bild.", "Bereich"),
               "fr": ("Regardez cette zone du tableau.", "zone"), "zh": ("请看画面上的这片区域。", "这片")},
}


def frase(clave: str, idioma: str = POR_DEFECTO) -> tuple[str, int]:
    """(texto, ancla) de una frase fija del programa en el idioma del turno."""
    texto, palabra = FRASES[clave][idioma]
    return texto, ancla_de(texto, palabra, idioma)


DEMO = {
    "es": (("Este paisaje se extiende ampliamente ante nosotros, desde el árbol de la izquierda hasta la casa de la derecha, con el lago en primer plano.", "ampliamente"),
           ("Si levantamos la mirada, por encima de las montañas encontramos el cielo azul; a la derecha destaca el sol amarillo que ilumina la escena.", "cielo"),
           ("Ahora observa con atención la parte derecha del cuadro: este punto concreto corresponde al sol, que se encuentra por encima de la casa.", "sol,"),
           ("Por último, a la izquierda, el movimiento del brazo abarca esta región del paisaje, donde el árbol se recorta delante de las montañas y el campo.", "región")),
    "en": (("This landscape stretches out wide before us, from the tree on the left to the house on the right, with the lake in the foreground.", "wide"),
           ("If we look up, above the mountains we find the blue sky; on the right the yellow sun stands out, lighting the whole scene.", "sky"),
           ("Now look closely at the right side of the picture: this particular point is the sun, which sits just above the house.", "sun"),
           ("Finally, on the left, the movement of the arm takes in this region of the landscape, where the tree stands out against the mountains and the field.", "region")),
    "de": (("Diese Landschaft breitet sich weit vor uns aus, vom Baum auf der linken Seite bis zum Haus auf der rechten, mit dem See im Vordergrund.", "weit"),
           ("Wenn wir den Blick heben, finden wir über den Bergen den blauen Himmel; rechts leuchtet die gelbe Sonne, die die ganze Szene erhellt.", "Himmel"),
           ("Schauen Sie nun aufmerksam auf die rechte Seite des Bildes: Dieser Punkt hier ist die Sonne, die genau über dem Haus steht.", "Sonne"),
           ("Zum Schluss, auf der linken Seite, umfasst die Bewegung des Arms diesen Bereich der Landschaft, wo sich der Baum vor den Bergen und dem Feld abhebt.", "Bereich")),
    "fr": (("Ce paysage s'étend largement devant nous, de l'arbre à gauche jusqu'à la maison à droite, avec le lac au premier plan.", "largement"),
           ("Si nous levons les yeux, au-dessus des montagnes nous trouvons le ciel bleu ; à droite se détache le soleil jaune qui éclaire la scène.", "ciel"),
           ("Observez maintenant avec attention la partie droite du tableau : ce point précis correspond au soleil, qui se trouve au-dessus de la maison.", "soleil"),
           ("Enfin, à gauche, le mouvement du bras couvre cette région du paysage, où l'arbre se découpe devant les montagnes et le champ.", "région")),
    "zh": (("这片风景在我们面前宽广地展开，从左边的树一直延伸到右边的房子，前景是一片湖水。", "宽广"),
           ("如果我们抬头看，在群山的上方是蓝色的天空；右边是明亮的黄色太阳，照亮了整个画面。", "天空"),
           ("现在请仔细看画面的右侧：这个位置就是太阳，它就在房子的上方。", "太阳"),
           ("最后，在左边，手臂的动作划过风景中的这片区域，那里的树映衬在群山和田野之前。", "区域")),
}


# ------------------------------------------------------------------ instrucciones a la IA
EJEMPLO = {
    "es": '{"texto":"El campo verde ocupa la franja inferior del dibujo.","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":2}',
    "en": '{"texto":"The green field fills the lower strip of the drawing.","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":2}',
    "de": '{"texto":"Das grüne Feld füllt den unteren Streifen der Zeichnung.","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":2}',
    "fr": '{"texto":"Le champ vert occupe la bande inférieure du dessin.","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":2}',
    "zh": '{"texto":"绿色的田野占据了画面下方的整条地带。","tipo":"region","brazo":"izq","region":[[600,50],[950,950]],"ancla":3}',
}


def instrucciones(idioma: str = POR_DEFECTO) -> dict[str, str]:
    """Las partes de las instrucciones a la IA que dependen del idioma del turno.

    En español son, letra por letra, las que había antes de que existieran los idiomas.
    """
    i = IDIOMAS[idioma]
    if idioma == "es":
        responde = "Responde en español, en 1 a 4 bloques de una frase. Diseña texto y gesto juntos."
    else:
        responde = (f"Responde en {i.nombre} ({i.propio}), en 1 a 4 bloques de una frase. Diseña texto y gesto juntos.\n"
                    f'Todos los campos "texto" van escritos íntegramente en {i.nombre}, aunque estas instrucciones, el '
                    f"contexto o parte de la petición estén en otro idioma. No mezcles idiomas ni añadas traducciones.")
    if i.por_caracteres:
        longitud = ("Cada bloque debe tener 35–55 caracteres chinos de descripción útil, en caracteres simplificados: "
                    "los brazos hacen un gesto amplio")
        ancla = ("ancla es el índice, desde 0, del carácter donde empieza la palabra relevante, contando todos los "
                 "caracteres del texto salvo los espacios.")
    else:
        longitud = "Cada bloque debe tener 20–30 palabras de descripción útil: los brazos hacen un gesto amplio"
        ancla = "ancla es índice de palabra separado por espacios, desde 0."
    return {"responde": responde, "longitud": longitud, "ancla": ancla, "ejemplo": EJEMPLO[idioma]}
