import os
import json
import time
import logging
from datetime import datetime, timedelta, timezone

import asyncio
import glob

import requests
from bs4 import BeautifulSoup
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from transformers import T5ForConditionalGeneration, T5Tokenizer

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)

ASSETS_DIR = "/Users/elizavetapivovarova/Documents/experiments/embedding/assets"

import openai
client = openai.AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


class NewsGetter:
    def __init__(self, base_dir, base_name="news"):
        self.base_dir = base_dir
        self.base_name = base_name
        self.cache_file = os.path.join(self.base_dir, f"{self.base_name}.json")
        self.llm_cache = {}

        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        logging.info(f"Инициализация NewsGetter. Устройство: {self.device}")

        logging.info("Загрузка модели суммаризации (T5)...")
        self.sum_tokenizer = T5Tokenizer.from_pretrained("IlyaGusev/rut5_base_sum_gazeta")
        self.sum_model = T5ForConditionalGeneration.from_pretrained("IlyaGusev/rut5_base_sum_gazeta").to(self.device)

        logging.info("Загрузка моделей для кластеризации (MiniLM, CrossEncoder)...")
        self.dense_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        self.cross_model = CrossEncoder("cointegrated/rubert-base-cased-nli-threeway")

        logging.info("Все модели успешно загружены!")

    async def get_cluster_fact(self, texts, cluster_ids):
        cache_key = tuple(sorted(cluster_ids))
        if cache_key in self.llm_cache:
            return self.llm_cache[cache_key]

        combined_text = "\n\n".join([t[:300] for t in texts])
        prompt = f"Ты новостной редактор. Напиши ОДНО предложение о сути события: {combined_text}"

        try:
            response = await client.chat.completions.create(
                model="qwen2.5:1.5b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            fact = response.choices[0].message.content.strip()
            self.llm_cache[cache_key] = fact
            return fact
        except Exception:
            return "Суть не определена."

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ---
    def _fetch_with_retry(self, url, headers, max_retries=3):
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 429:
                    wait_time = 15 * (attempt + 1)
                    logging.warning(f"Telegram просит притормозить (429). Ждем {wait_time} сек...")
                    time.sleep(wait_time)
                    continue
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                wait_time = 10 * (attempt + 1)
                logging.warning(f"Ошибка соединения: {e}. Повтор через {wait_time} сек...")
                time.sleep(wait_time)
        logging.error(f"Не удалось загрузить {url}")
        return None

    def _clean_text_for_nli(self, text):
        """Очищает текст от рекламного мусора Telegram каналов перед проверкой на противоречия"""
        if not text:
            return ""
        junk_markers = ['🇷🇺', '✔', '🎉', '🔗', '🌐', '❗️', 'Подписывайтесь', 'Подпишись', 'Мы в Telegram']
        cleaned = text
        for marker in junk_markers:
            cleaned = cleaned.split(marker)[0]
        return cleaned.strip()[:300]

    def get_summary(self, text, max_length=90):
        if len(text) < 450:
            return text

        inputs = self.sum_tokenizer(
            [text],
            max_length=500,
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(self.device)

        output_ids = self.sum_model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_length=max_length,
            no_repeat_ngram_size=3,
            num_beams=2,
            early_stopping=True
        )[0]

        return self.sum_tokenizer.decode(output_ids, skip_special_tokens=True)

    # --- ПАРСИНГ И РАБОТА С БАЗОЙ ---
    def get_channel_posts(self, channel_username: str, hours: int = 24):
        headers = {"User-Agent": "Mozilla/5.0"}
        posts = []
        seen_texts = set()

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours) if hours > 0 else None
        logging.info(f"[{channel_username}] Собираем посты за последние {hours} ч...")

        current_url = f"https://t.me/s/{channel_username}"

        while current_url:
            resp = self._fetch_with_retry(current_url, headers)
            if not resp:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            messages = soup.select("div.tgme_widget_message_wrap")
            if not messages:
                break

            page_posts = []
            reached_cutoff = False
            current_group_date = None
            current_group_id = None

            for msg in reversed(messages):
                text_block = msg.select_one("div.tgme_widget_message_text")
                raw_text = text_block.get_text(" ", strip=True) if text_block else ""
                clean_text = " ".join(raw_text.split())

                link_el = msg.select_one("a.tgme_widget_message_date")
                post_url = link_el["href"] if link_el else None
                post_id = post_url.rstrip("/").split("/")[-1] if post_url else None

                date_el = msg.select_one("time")
                post_date = None

                if date_el and date_el.has_attr("datetime"):
                    post_date = datetime.fromisoformat(date_el["datetime"])
                    current_group_date = post_date
                    current_group_id = post_id
                else:
                    post_date = current_group_date
                    if not post_id:
                        post_id = current_group_id
                        post_url = f"https://t.me/{channel_username}/{post_id}" if post_id else None

                if cutoff_time and post_date and post_date < cutoff_time:
                    reached_cutoff = True
                    break

                if clean_text and clean_text not in seen_texts:
                    seen_texts.add(clean_text)
                    final_url = post_url if post_url else f"https://t.me/{channel_username}/{post_id}"

                    summary = self.get_summary(clean_text)

                    page_posts.append({
                        "text": clean_text,
                        "summary": summary,
                        "url": final_url,
                        "id": post_id,
                        "date": post_date.isoformat() if post_date else None,
                        "channel": channel_username,
                    })

            posts.extend(reversed(page_posts))

            if reached_cutoff or hours == 0:
                break

            first_msg = messages[0]
            first_link = first_msg.select_one("a.tgme_widget_message_date")
            if first_link:
                oldest_id_on_page = first_link["href"].rstrip("/").split("/")[-1]
                current_url = f"https://t.me/s/{channel_username}?before={oldest_id_on_page}"
            else:
                break

        return posts

    def save_posts(self, new_posts):
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                posts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            posts = []

        existing_urls = {p["url"] for p in posts}
        unique_new_posts = [p for p in new_posts if p["url"] not in existing_urls]

        if unique_new_posts:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(posts + unique_new_posts, f, ensure_ascii=False, indent=4)
            logging.info(f"Добавлено {len(unique_new_posts)} новых постов.")
        else:
            logging.info("Новых постов не найдено, база актуальна.")

    def load_posts(self):
        if not os.path.exists(self.cache_file):
            logging.error(f"Файл '{self.cache_file}' не найден!")
            return []
        with open(self.cache_file, "r", encoding="utf-8") as f:
            posts = json.load(f)
        logging.info(f"Загружено {len(posts)} постов из кэша.")
        return posts

    # --- КЛАСТЕРИЗАЦИЯ И ПОИСК СЮЖЕТОВ ---
    def find_news_clusters(self, posts, alpha=0.8, similarity_threshold=0.6, contradiction_threshold=0.88):
        if len(posts) < 2:
            return []

        texts = [p["text"] for p in posts]

        logging.info("Вычисление Dense-эмбеддингов (MiniLM)...")
        dense_embeddings = self.dense_model.encode(texts)
        sim_dense = cosine_similarity(dense_embeddings)

        logging.info("Вычисление Sparse-эмбеддингов (TF-IDF)...")
        ru_stop_words = ["а", "в", "г", "да", "для", "до", "ее", "еще", "же", "за",
                         "и", "из", "или", "как", "на", "не", "о", "об", "от", "по",
                         "при", "с", "у", "что", "это", "этот", "к", "но", "то", "так"]
        sparse_model = TfidfVectorizer(stop_words=ru_stop_words)
        sparse_embeddings = sparse_model.fit_transform(texts)
        sim_sparse = cosine_similarity(sparse_embeddings)

        logging.info("Объединение матриц (Hybrid Search)...")
        sim_matrix = (alpha * sim_dense) + ((1 - alpha) * sim_sparse)

        used_indices = set()
        clusters = []

        # Получаем правильный индекс класса противоречия
        id2label = self.cross_model.model.config.id2label
        contradiction_idx = 2
        for idx, label in id2label.items():
            if 'contradiction' in label.lower():
                # ИСПРАВЛЕНО (п.6): id2label может отдавать строковые ключи после
                # сериализации конфига — приводим явно к int, иначе
                # probs[contradiction_idx] упадёт с TypeError на индексации тензора.
                contradiction_idx = int(idx)
                break

        for i in range(len(texts)):
            if i in used_indices:
                continue

            current_cluster = [(i, 1.0)]
            current_outliers = []  # Сюда складываем противоречивые/спорные новости
            used_indices.add(i)
            channels_in_cluster = {posts[i].get('channel')}

            for j in range(i + 1, len(texts)):
                if j in used_indices:
                    continue

                score = float(sim_matrix[i][j])

                date_i = posts[i].get('date')
                date_j = posts[j].get('date')
                time_diff_hours = 0.0

                if date_i and date_j:
                    try:
                        di = datetime.fromisoformat(date_i.replace('Z', '+00:00'))
                        dj = datetime.fromisoformat(date_j.replace('Z', '+00:00'))
                        time_diff_hours = abs((di - dj).total_seconds()) / 3600.0
                    except Exception:
                        pass

                if score >= similarity_threshold and time_diff_hours <= 5:
                    text_a_short = self._clean_text_for_nli(posts[i].get('summary') or posts[i]['text'])
                    text_b_short = self._clean_text_for_nli(posts[j].get('summary') or posts[j]['text'])

                    logits = self.cross_model.predict([(text_a_short, text_b_short)], convert_to_tensor=True)
                    probs = torch.softmax(logits, dim=-1)[0]
                    contradiction_prob = float(probs[contradiction_idx])

                    if contradiction_prob > contradiction_threshold:
                        current_outliers.append((j, score, contradiction_prob))
                        # ИСПРАВЛЕНО (п.5, регрессия): пост-outlier тоже нужно
                        # пометить использованным. Раньше эта строка отсутствовала —
                        # пост, отсеянный как противоречащий, на следующей итерации
                        # внешнего цикла (i дойдёт до j) сам становился источником
                        # нового, по сути дублирующего кластера.
                        used_indices.add(j)
                        logging.debug(
                            f"[Cross-Encoder Outlier] Противоречие: "
                            f"{posts[i]['channel']} vs {posts[j]['channel']} ({contradiction_prob*100:.1f}%)"
                        )
                        continue

                    channel_j = posts[j].get('channel')
                    if channel_j in channels_in_cluster:
                        # ИСПРАВЛЕНО (п.5, тот же класс бага): дубликат из уже
                        # представленного в кластере канала не добавляем в основной
                        # список, но ОБЯЗАТЕЛЬНО помечаем used — иначе он тоже
                        # всплывёт как источник нового кластера позже.
                        used_indices.add(j)
                        continue

                    current_cluster.append((j, score))
                    used_indices.add(j)
                    channels_in_cluster.add(channel_j)

            if len(current_cluster) > 1:
                clusters.append({
                    "items": current_cluster,
                    "outliers": current_outliers
                })

        clusters.sort(key=lambda c: len(c["items"]), reverse=True)
        return clusters

    def get_today_filename(self):
        current_date = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.base_dir, f"{self.base_name}_{current_date}.json")

    def get_latest_filename(self):
        search_pattern = os.path.join(self.base_dir, f"{self.base_name}_*.json")
        files = glob.glob(search_pattern)
        return max(files) if files else self.get_today_filename()

    def save_clusters(self, clusters, filename):
        full_path = os.path.join(self.base_dir, filename) if not os.path.isabs(filename) else filename
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(clusters, f, ensure_ascii=False, indent=4)

    def load_clusters(self, filename):
        full_path = os.path.join(self.base_dir, filename) if not os.path.isabs(filename) else filename
        if not os.path.exists(full_path):
            return None
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # --- МЕТОД ДЛЯ УДОБНОГО ВЫЗОВА ИЗ БОТА ---
    def process_news(self, channels, hours=24, scrape_new=True):
        if scrape_new:
            all_new_posts = []
            for channel in channels:
                all_new_posts.extend(self.get_channel_posts(channel, hours))
            self.save_posts(all_new_posts)

            all_posts = self.load_posts()
            clusters = self.find_news_clusters(all_posts)

            enriched_data = []

            loop = asyncio.get_event_loop()
            for cluster in clusters:
                # ИСПРАВЛЕНО (п.3): find_news_clusters теперь возвращает словари
                # {"items": [...], "outliers": [...]}, а не плоский список кортежей —
                # нужно явно брать cluster["items"] и распаковывать (idx, score),
                # а не идти по cluster напрямую (это итерировало бы по ключам
                # словаря "items"/"outliers").
                cluster_items = cluster["items"]
                cluster_indices = [idx for idx, score in cluster_items]
                cluster_texts = [all_posts[idx]['text'] for idx in cluster_indices]

                # ИСПРАВЛЕНО (п.2): get_cluster_fact ждёт cluster_ids вторым
                # аргументом (используется как ключ кэша) — раньше вызывалась без
                # него и падала с TypeError.
                fact = loop.run_until_complete(
                    self.get_cluster_fact(cluster_texts, cluster_indices)
                )

                enriched_data.append({
                    "fact": fact,
                    "items": cluster_items,
                    "outliers": cluster.get("outliers", []),
                })

            cluster_file = os.path.basename(self.cache_file).replace("news_", "clusters_")
            self.save_clusters(enriched_data, cluster_file)
            return enriched_data

        else:
            base_filename = os.path.basename(self.cache_file)
            cluster_filename = base_filename.replace("news_", "clusters_")
            return self.load_clusters(cluster_filename)


# --- ЗАПУСК ---
if __name__ == "__main__":
    CHANNELS = [
        "mosnews", "ria_novosti_russiya", "readovkanews",
        "varlamov_news", "ostorozhno_novosti", "dmitrynikotin",
        "bbcrussian", "kommersant"
    ]
    SCRAPE_NEW_DATA = False

    # ИСПРАВЛЕНО (п.1): конструктор ждёт (base_dir, base_name) — раньше сюда
    # передавалось "news_cache.json" как base_dir, из-за чего cache_file
    # собирался в несуществующий путь "news_cache.json/news_2026-08-08.json".
    # base_dir теперь — папка ASSETS_DIR, base_name — имя файла без расширения.
    news_getter = NewsGetter(base_dir=ASSETS_DIR, base_name="news_cache")

    clusters = news_getter.process_news(channels=CHANNELS, hours=24, scrape_new=SCRAPE_NEW_DATA)
    all_posts = news_getter.load_posts()

    print(f"\n--- НАЙДЕНО СЮЖЕТОВ: {len(clusters)} ---\n")

    for rank, cluster in enumerate(clusters[:15], 1):
        # ИСПРАВЛЕНО (п.4): clusters теперь — список словарей
        # {"fact": ..., "items": [(idx, score), ...], "outliers": [...]}, а не
        # плоский список кортежей (idx, score). Раньше
        # "for idx, score in cluster_items" пыталось распаковать словарь и падало.
        items = cluster["items"]
        fact = cluster.get("fact", "")

        print(f"📌 СЮЖЕТ #{rank} (Опубликовали каналов: {len(items)})")
        if fact:
            print(f"   Суть: {fact}")

        for idx, score in items:
            post = all_posts[idx]
            snippet = post['text'][:120].replace('\n', ' ') + "..."

            if score == 1.0:
                print(f"  ⭐ [ИСТОЧНИК СЮЖЕТА] | Канал: {post.get('channel')} | {post['url']}")
            else:
                print(f"  🔗 [СХОДСТВО: {score*100:.1f}%] | Канал: {post.get('channel')} | {post['url']}")
            print(f"     Текст: {snippet}\n")
        print("-" * 70)