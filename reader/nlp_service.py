import os
import re
import urllib.request
import spacy
from spacy.matcher import Matcher
from database import append_context_if_exists

FREQ_FILE = "spanish_top50k.txt"
IDIOMATIC_VERBS = {
    "dar", "hacer", "tomar", "echar", "poner", "tener", "romper",
    "sostener", "chasquear", "perder", "quedar", "tragar", "asomar"
}
CLITIC_SUFFIXES = re.compile(r"(.*?)(lo|la|los|las|me|te|se|nos|os|les|le)$", re.IGNORECASE)

class SpanishNLPService:
    def __init__(self):
        self.nlp = spacy.load("es_core_news_md")
        self.common_vocab = self._load_frequency_vocab()
        self.matcher = self._create_matcher()

    def _load_frequency_vocab(self) -> set[str]:
        if not os.path.exists(FREQ_FILE):
            url = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt"
            urllib.request.urlretrieve(url, FREQ_FILE)

        vocab = set()
        if os.path.exists(FREQ_FILE):
            with open(FREQ_FILE, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 16000:
                        break
                    vocab.add(line.strip().split()[0].lower())
        return vocab

    def _create_matcher(self) -> Matcher:
        matcher = Matcher(self.nlp.vocab)
        matcher.add("EXPRESION_VERBAL", [[
            {"LEMMA": {"IN": list(IDIOMATIC_VERBS)}},
            {"POS": {"IN": ["DET", "PRON", "ADP"]}, "OP": "*"},
            {"POS": "NOUN"}
        ]])
        matcher.add("LOCUCION_A", [[
            {"LOWER": "a"},
            {"POS": {"IN": ["NOUN", "ADJ", "ADV"]}, "IS_ALPHA": True}
        ]])
        return matcher

    def normalize_word(self, word: str) -> list[str]:
        variants = [word.lower()]
        match = CLITIC_SUFFIXES.match(word.lower())
        if match and len(match.group(1)) >= 3:
            root = match.group(1)
            variants.append(root)
            root_deacc = root.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
            variants.append(root_deacc)
            if root_deacc.endswith(("ando", "iendo")):
                variants.extend([root_deacc[:-4] + "ar", root_deacc[:-5] + "er", root_deacc[:-5] + "ir"])
        if word.endswith(("éis", "áis", "ís")):
            variants.append(word.replace("éis", "er").replace("áis", "ar").replace("ís", "ir"))
        return variants

    def clean_text(self, text: str) -> str:
        return text.replace("-\n", "").replace("-\t", "")

    def process_chapter(self, text: str, user_id: str, user_dict: dict) -> tuple[list, list]:
        clean = self.clean_text(text)
        doc = self.nlp(clean)
        
        # 1. Поиск идиом
        phrases = []
        seen_phrases = set()
        for match_id, start, end in self.matcher(doc):
            span = doc[start:end]
            if span.text.lower() in ["asoman un par", "da dos", "poner a mi derecha", "tener sentido"]:
                continue
            lemma = " ".join(t.lemma_ for t in span).lower()
            if lemma in seen_phrases or len(span) < 2:
                continue
            seen_phrases.add(lemma)
            sentence = span.sent.text.strip().replace("\n", " ")
            
            # Автоматически докидываем контекст в БД, если слово уже отслеживается
            updated_dict_info = append_context_if_exists(user_id, lemma, sentence)
            dict_info = updated_dict_info if updated_dict_info else user_dict.get(lemma)

            phrases.append({
                "lemma": lemma,
                "original": span.text,
                "sentence": sentence,
                "dict_info": dict_info
            })

        # 2. Поиск редких слов
        rare_words = []
        seen_lemmas = set()
        for token in doc:
            word = token.text.lower()
            lemma = token.lemma_.lower()
            
            if (
                not token.is_alpha 
                or len(word) < 4
                or token.ent_type_
                or token.pos_ not in ["NOUN", "ADJ", "VERB"]
                or lemma in seen_lemmas
            ):
                continue
                
            variants = self.normalize_word(word) + self.normalize_word(lemma)
            if any(v in self.common_vocab for v in variants):
                continue
                
            seen_lemmas.add(lemma)
            sentence = token.sent.text.strip().replace("\n", " ")
            
            # Автоматически докидываем контекст в БД
            updated_dict_info = append_context_if_exists(user_id, lemma, sentence)
            dict_info = updated_dict_info if updated_dict_info else user_dict.get(lemma)

            rare_words.append({
                "word": token.text,
                "lemma": lemma,
                "pos": token.pos_,
                "sentence": sentence,
                "dict_info": dict_info
            })

        return phrases, rare_words