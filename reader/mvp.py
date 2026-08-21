import os
import urllib.request
import spacy
from spacy.matcher import Matcher

nlp = spacy.load("es_core_news_md")

FREQ_FILE = "spanish_top50k.txt"
if not os.path.exists(FREQ_FILE):
    print("⏳ Скачивание словаря частотности...")
    url = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt"
    urllib.request.urlretrieve(url, FREQ_FILE)

# Берем Топ-16000 словоформ — это честные A1-B2 (включая все спряжения и цвета)
COMMON_VOCAB = set()
if os.path.exists(FREQ_FILE):
    with open(FREQ_FILE, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 16000:  # 16k словоформ отсекают всю бытовую базу
                break
            word = line.strip().split()[0].lower()
            COMMON_VOCAB.add(word)

# Идиоматические глаголы
IDIOMATIC_VERBS = {
    "dar", "hacer", "tomar", "echar", "poner", "tener", "romper",
    "sostener", "chasquear", "perder", "quedar", "tragar", "asomar"
}

def clean_text(text: str) -> str:
    cleaned = text.replace("-\n", "").replace("-\t", "")
    cleaned = cleaned.replace("-res-ponde—", "responde—")
    cleaned = cleaned.replace("des-conocido", "desconocido")
    cleaned = cleaned.replace("fiereci-lla", "fierecilla")
    cleaned = cleaned.replace("когда", "cuando")
    cleaned = cleaned.replace("как будто", "como si")
    return cleaned

import re

# Регулярка для отрезания слитных местоимений (hacerlo -> hacer, viéndolo -> viendo)
CLITIC_SUFFIXES = re.compile(r"(.*?)(lo|la|los|las|me|te|se|nos|os|les|le)$", re.IGNORECASE)

def normalize_spanish_word(word: str) -> list[str]:
    """Возвращает варианты слова: оригинал, без ударения, без местоимений."""
    variants = [word.lower()]
    
    # 1. Снимаем клитики (eliminarlo -> eliminar, diciéndolo -> diciendo)
    match = CLITIC_SUFFIXES.match(word.lower())
    if match and len(match.group(1)) >= 3:
        root = match.group(1)
        variants.append(root)
        # Восстановление глаголов после снятия ударения: viéndo -> viendo, dicié -> decir
        root_deacc = root.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
        variants.append(root_deacc)
        if root_deacc.endswith(("ando", "iendo")):
            variants.extend([root_deacc[:-4] + "ar", root_deacc[:-5] + "er", root_deacc[:-5] + "ir"])

    # 2. Нормализация vosotros-форм: devolvéis -> devolver, comprendéis -> comprender
    if word.endswith(("éis", "áis", "ís")):
        base = word.replace("éis", "er").replace("áis", "ar").replace("ís", "ir")
        variants.append(base)
        
    return variants

def create_matcher(vocab):
    matcher = Matcher(vocab)
    
    # Идиомы: Глагол + Артикль/Местоимение + Существительное
    matcher.add("EXPRESION_VERBAL", [[
        {"LEMMA": {"IN": list(IDIOMATIC_VERBS)}},
        {"POS": {"IN": ["DET", "PRON", "ADP"]}, "OP": "*"},
        {"POS": "NOUN"}
    ]])
    
    # Наречные обороты
    matcher.add("LOCUCION_A", [[
        {"LOWER": "a"},
        {"POS": {"IN": ["NOUN", "ADJ", "ADV"]}, "IS_ALPHA": True}
    ]])
    
    return matcher

def analyze_chapter(raw_text: str):
    text = clean_text(raw_text)
    doc = nlp(text)
    matcher = create_matcher(nlp.vocab)
    matches = matcher(doc)

    # 1. Фразы и идиомы
    phrases = []
    seen_phrases = set()
    for match_id, start, end in matches:
        span = doc[start:end]
        if span.text.lower() in ["asoman un par", "da dos", "poner a mi derecha"]:
            continue
            
        base = " ".join(t.lemma_ for t in span).lower()
        if base in seen_phrases or len(span) < 2:
            continue
        seen_phrases.add(base)
        phrases.append({
            "base": base,
            "text": span.text,
            "context": span.sent.text.strip().replace("\n", " ")
        })

    # 2. Редкие слова
    rare_words = []
    seen_lemmas = set()
    
    for token in doc:
        word = token.text.lower()
        lemma = token.lemma_.lower()
        
        # Пропускаем стоп-слова, пунктуацию, имена и короткие слова
        if (
            not token.is_alpha 
            or len(word) < 4
            or token.ent_type_
            or token.pos_ not in ["NOUN", "ADJ", "VERB"]
        ):
            continue

        # Получаем все грамматические вариации слова
        variants = normalize_spanish_word(word) + normalize_spanish_word(lemma)
        
        # Если хотя бы один вариант есть в частотном словаре — это базовое слово
        if any(v in COMMON_VOCAB for v in variants):
            continue
            
        if lemma in seen_lemmas:
            continue
            
        seen_lemmas.add(lemma)
        rare_words.append({
            "word": token.text,
            "lemma": token.lemma_,
            "pos": token.pos_,
            "context": token.sent.text.strip().replace("\n", " ")
        })

    return phrases, rare_words

def print_study_guide(phrases, rare_words):
    print("=" * 65)
    print("📖 GUÍA DE LECTURA: VOCABULARIO Y EXPRESIONES CLAVE")
    print("=" * 65)
    
    print("\n✨ 1. PALABRAS RARAS Y LITERARIAS (Редкие слова B2/C1/C2):")
    print("-" * 65)
    for i, item in enumerate(rare_words, 1):
        print(f"{i}. 🔸 {item['word'].upper()} (базовая: {item['lemma']}) — [{item['pos']}]")
        print(f"   Контекст: \"{item['context']}\"")
    
    print("\n\n🎯 2. EXPRESIONES Y FRASES HECHAS (Обороты и идиомы):")
    print("-" * 65)
    for i, item in enumerate(phrases, 1):
        print(f"{i}. 🔹 {item['base'].upper()} (в тексте: «{item['text']}»)")
        print(f"   Контекст: \"{item['context']}\"")

if __name__ == "__main__":
    my_spanish_text = """
    —Matar al Rey de los Demonios no es la única alternativa -res-ponde—. La niebla solo se levantará cuando se rompan las condiciones del pacto...; lo que quiere decir que, si devolvéis aquello que habéis pedido, es decir, a vuestro padre, el pacto quedará deshecho, y las puertas entre los mundos se cerrarán.
—Eso no podemos hacerlo.
No. No voy a devolver a mi padre al Infierno.
Dante asiente y una sonrisa juguetona asoma a sus labios, una
sonrisa que me gustaría borrar de un buen bofetón.
—Muy bien, pues si no quieres optar por el camino fácil, fiereci-lla, entonces la alternativa es, efectivamente, la que teníais pensada: matar al Rey de los Demonios; pues ni vosotras ni él protegisteis vuestra integridad mediante una cláusula. —La sonrisa de Dantalion se acentúa aún más—. Pero ¿cómo matarán los ratones a un gato des-conocido? ¿Y cómo lo harán cuando el gato ya conoce el escondrijo por el que se mueven? Porque los pactos, brujas, funcionan en ambas direcciones, y si matarlo a él puede cerrar las puertas del Infiern....
Rhiannon traga saliva.
—Si alguna de nosotras muere — reflexiona—, se levantará la niebla.
Dantalion da dos palmadas, en un aplauso insulso.
-  ¡Bingo!
-  Estamos acorraladas —murmura Circe—. Estamos dentro de una Jaula, y lo único que podemos hacer es esperar a que el demonio nos fulmine.
Dantalion chasquea la lengua.
—No te preocupes, niña, pues ahí es donde entro yo. —Parece triunfante, como si acabara de ganar una partida de ajedrez contra nosotras—. ¿Comprendéis ahora mi oferta? Puedo deciros, ahora mismo, quién es exactamente el Rey de los Demonios y cómo lo podéis encontrar. Puedo, incluso, ayudaros a eliminarlo. Creedme; es poderoso, pero no tanto como un día lo fue Bael.
Por su sonrisa felina asoman un par de colmillos afilados.
-  ¿Y a cambio? —pregunto yo, viéndolo venir.
-  A cambio... —Dantalion se levanta de su asiento y se pone a mi derecha, posando una mano sobre el respaldo de mi silla. Incómoda con la diferencia de altura, me levanto también, y mis hermanas me imitan. Le sostengo la mirada al demonio, una mirada verde y relampagueante en la que puedo observar destellos de color naranja—. A cambio, fierecilla, vendrás al Infierno. Conmigo.    """

    phrases, rare_words = analyze_chapter(my_spanish_text)
    print_study_guide(phrases, rare_words)