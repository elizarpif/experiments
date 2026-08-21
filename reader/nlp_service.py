import os
import re
import urllib.request
import spacy
from spacy.matcher import Matcher
from database import append_context_if_exists

# Файлы частотных словарей
FREQ_FILES = {
    "es": {
        "file": "spanish_top50k.txt",
        "url": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt",
        "cutoff": 16000  # отсекаем топ-16k для испанского (уровень B2)
    },
    "en": {
        "file": "english_top50k.txt",
        "url": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/en/en_50k.txt",
        "cutoff": 20000  # отсекаем топ-20k для английского (уровень C1)
    }
}

SPANISH_IDIOMATIC_VERBS = {
    "dar", "hacer", "tomar", "echar", "poner", "tener", "romper",
    "sostener", "chasquear", "perder", "quedar", "tragar", "asomar"
}

ENGLISH_IDIOMATIC_VERBS = {
    "take", "make", "give", "keep", "hold", "set", "catch", "break", "lose", "pay", "draw"
}

CLITIC_SUFFIXES_ES = re.compile(r"(.*?)(lo|la|los|las|me|te|se|nos|os|les|le)$", re.IGNORECASE)


class MultilingualNLPService:
    def __init__(self):
        # 1. Загрузка spaCy моделей
        self.nlp_models = {
            "es": spacy.load("es_core_news_md"),
            "en": spacy.load("en_core_web_sm")
        }
        
        # 2. Загрузка частотных словарей
        self.vocabs = {
            "es": self._load_frequency_vocab("es"),
            "en": self._load_frequency_vocab("en")
        }
        
        # 3. Настройка матчеров
        self.matchers = {
            "es": self._create_spanish_matcher(),
            "en": self._create_english_matcher()
        }

    def _load_frequency_vocab(self, lang: str) -> set[str]:
        cfg = FREQ_FILES[lang]
        filepath = cfg["file"]
        if not os.path.exists(filepath):
            try:
                urllib.request.urlretrieve(cfg["url"], filepath)
            except Exception as e:
                print(f"Не удалось скачать частотный словарь для {lang}: {e}")
                return set()

        vocab = set()
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= cfg["cutoff"]:
                        break
                    parts = line.strip().split()
                    if parts:
                        vocab.add(parts[0].lower())
        return vocab

    def _create_spanish_matcher(self) -> Matcher:
        matcher = Matcher(self.nlp_models["es"].vocab)
        matcher.add("ES_EXPRESION_VERBAL", [[
            {"LEMMA": {"IN": list(SPANISH_IDIOMATIC_VERBS)}},
            {"POS": {"IN": ["DET", "PRON", "ADP"]}, "OP": "*"},
            {"POS": "NOUN"}
        ]])
        matcher.add("ES_LOCUCION_A", [[
            {"LOWER": "a"},
            {"POS": {"IN": ["NOUN", "ADJ", "ADV"]}, "IS_ALPHA": True}
        ]])
        return matcher

    def _create_english_matcher(self) -> Matcher:
        matcher = Matcher(self.nlp_models["en"].vocab)
        matcher.add("EN_VERBAL_IDIOM", [[
            {"LEMMA": {"IN": list(ENGLISH_IDIOMATIC_VERBS)}},
            {"POS": {"IN": ["DET", "PRON", "ADP"]}, "OP": "*"},
            {"POS": "NOUN"}
        ]])
        return matcher

    def normalize_word(self, word: str, lang: str) -> list[str]:
        word_clean = word.lower()
        variants = [word_clean]
        
        if lang == "es":
            match = CLITIC_SUFFIXES_ES.match(word_clean)
            if match and len(match.group(1)) >= 3:
                root = match.group(1)
                variants.append(root)
                root_deacc = root.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o")
                variants.append(root_deacc)
                if root_deacc.endswith(("ando", "iendo")):
                    variants.extend([root_deacc[:-4] + "ar", root_deacc[:-5] + "er", root_deacc[:-5] + "ir"])
            if word_clean.endswith(("éis", "áis", "ís")):
                variants.append(word_clean.replace("éis", "er").replace("áis", "ar").replace("ís", "ir"))
        return variants

    def clean_text(self, text: str) -> str:
        return text.replace("-\n", "").replace("-\t", "").replace("—\n", "")

    def _extract_english_phrasals(self, doc) -> list[dict]:
        """Извлекает английские фразовые глаголы через синтаксические связи (VERB + prt)."""
        phrasals = []
        for token in doc:
            if token.pos_ == "VERB":
                for child in token.children:
                    if child.dep_ == "prt":  # частица фразового глагола: off, out, up, down, away
                        original = f"{token.text} {child.text}"
                        lemma = f"{token.lemma_} {child.lemma_}".lower()
                        sentence = token.sent.text.strip().replace("\n", " ")
                        phrasals.append({
                            "original": original,
                            "lemma": lemma,
                            "sentence": sentence
                        })
        return phrasals

    def process_chapter(self, text: str, user_id: str, user_dict: dict, language: str = "es") -> tuple[list, list]:
        lang = language if language in self.nlp_models else "es"
        nlp = self.nlp_models[lang]
        common_vocab = self.vocabs[lang]
        matcher = self.matchers[lang]

        clean = self.clean_text(text)
        doc = nlp(clean)

        # --------------------------------------------------
        # 1. Поиск оборотов, идиом и фразовых глаголов
        # --------------------------------------------------
        phrases = []
        seen_phrases = set()

        # А) Поиск через шаблоны (Matcher)
        for _, start, end in matcher(doc):
            span = doc[start:end]
            if span.text.lower() in ["asoman un par", "da dos", "poner a mi derecha", "tener sentido", "make sense", "take care"]:
                continue
            lemma = " ".join(t.lemma_ for t in span).lower()
            if lemma in seen_phrases or len(span) < 2:
                continue
            seen_phrases.add(lemma)
            sentence = span.sent.text.strip().replace("\n", " ")

            updated = append_context_if_exists(user_id, lemma, sentence, language=lang)
            dict_info = updated if updated else user_dict.get(lemma)

            phrases.append({
                "lemma": lemma,
                "original": span.text,
                "sentence": sentence,
                "dict_info": dict_info
            })

        # Б) Для английского добавляем фразовые глаголы (VERB + particle)
        if lang == "en":
            for phrasal in self._extract_english_phrasals(doc):
                lemma = phrasal["lemma"]
                if lemma in seen_phrases:
                    continue
                seen_phrases.add(lemma)
                sentence = phrasal["sentence"]

                updated = append_context_if_exists(user_id, lemma, sentence, language=lang)
                dict_info = updated if updated else user_dict.get(lemma)

                phrases.append({
                    "lemma": lemma,
                    "original": phrasal["original"],
                    "sentence": sentence,
                    "dict_info": dict_info
                })

        # --------------------------------------------------
        # 2. Поиск редких слов (C1/C2)
        # --------------------------------------------------
        rare_words = []
        seen_lemmas = set()
        min_len = 4 if lang == "es" else 3

        for token in doc:
            word = token.text.lower()
            lemma = token.lemma_.lower()

            if (
                not token.is_alpha
                or len(word) < min_len
                or token.ent_type_  # пропускаем имена собственные и локации
                or token.pos_ not in ["NOUN", "ADJ", "VERB", "ADV"]
                or lemma in seen_lemmas
            ):
                continue

            variants = self.normalize_word(word, lang) + self.normalize_word(lemma, lang)
            if any(v in common_vocab for v in variants):
                continue

            seen_lemmas.add(lemma)
            sentence = token.sent.text.strip().replace("\n", " ")

            updated = append_context_if_exists(user_id, lemma, sentence, language=lang)
            dict_info = updated if updated else user_dict.get(lemma)

            rare_words.append({
                "word": token.text,
                "lemma": lemma,
                "pos": token.pos_,
                "sentence": sentence,
                "dict_info": dict_info
            })

        return phrases, rare_words