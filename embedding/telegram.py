import requests
import time
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import json
import os


# --- БЕЗОПАСНЫЙ ЗАПРОС С ПАУЗАМИ ---
def fetch_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            # Имитируем чтение: случайная пауза от 1 до 2 секунд перед КАЖДЫМ запросом
            print("sleep")
            time.sleep(random.uniform(1.0, 2.0)) 
            
            resp = requests.get(url, headers=headers, timeout=15)
            
            # Если Telegram вернул 429 (Too Many Requests), увеличиваем паузу
            if resp.status_code == 429:
                wait_time = 15 * (attempt + 1)
                print(f"[!] Telegram просит притормозить. Ждем {wait_time} сек...")
                time.sleep(wait_time)
                continue
                
            resp.raise_for_status()
            return resp
            
        except requests.exceptions.RequestException as e:
            wait_time = 10 * (attempt + 1)
            print(f"[!] Ошибка соединения: {e}. Повтор через {wait_time} сек (Попытка {attempt+1}/{max_retries})")
            time.sleep(wait_time)
            
    print(f"[-] Не удалось загрузить {url} после {max_retries} попыток.")
    return None

# --- 1. ПАРСЕР НОВОСТЕЙ ЗА 24 ЧАСА ---
def get_channel_posts(channel_username: str, hours: int = 24):
    headers = {"User-Agent": "Mozilla/5.0"}
    posts = []
    seen_texts = set()
    
    # Определяем режим работы
    if hours > 0:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        print(f"[{channel_username}] Собираем посты за последние {hours} ч. ...")
    else:
        cutoff_time = None
        print(f"[{channel_username}] Собираем только последнюю страницу (hours=0)...")
    
    current_url = f"https://t.me/s/{channel_username}"
    
    while current_url:
        # Используем безопасную функцию с паузами
        resp = fetch_with_retry(current_url, headers)
        if not resp:
            break
            
        soup = BeautifulSoup(resp.text, "html.parser")
        messages = soup.select("div.tgme_widget_message_wrap")
        if not messages:
            break
            
        page_posts = []
        reached_cutoff = False
        
        # Добавляем переменные для памяти (так как идем с конца в начало)
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
            
            # Если у блока ЕСТЬ дата — запоминаем её и ID (это конец альбома или одиночный пост)
            if date_el and date_el.has_attr("datetime"):
                post_date = datetime.fromisoformat(date_el["datetime"])
                current_group_date = post_date
                current_group_id = post_id
            # Если даты НЕТ — берем её из памяти (это предыдущие картинки альбома)
            else:
                post_date = current_group_date
                if not post_id:
                    post_id = current_group_id
                    post_url = f"https://t.me/{channel_username}/{post_id}" if post_id else None
            
            # Проверка лимита времени
            if cutoff_time and post_date and post_date < cutoff_time:
                reached_cutoff = True
                break 
                    
            if clean_text and clean_text not in seen_texts:
                seen_texts.add(clean_text)
                final_url = post_url if post_url else f"https://t.me/{channel_username}/{post_id}"
                
                page_posts.append({
                    "text": clean_text,
                    "url": final_url,
                    "id": post_id,
                    "date": post_date.isoformat() if post_date else None,
                    "channel": channel_username
                })
        
        posts.extend(reversed(page_posts))
        
        # ВЫХОД ИЗ ЦИКЛА:
        # Если мы дошли до старых новостей ИЛИ если запросили только 1 страницу (hours=0)
        if reached_cutoff or hours == 0:
            break 
            
        # Иначе — листаем на предыдущую страницу (в прошлое)
        first_msg = messages[0]
        first_link = first_msg.select_one("a.tgme_widget_message_date")
        if first_link:
            oldest_id_on_page = first_link["href"].rstrip("/").split("/")[-1]
            current_url = f"https://t.me/s/{channel_username}?before={oldest_id_on_page}"
        else:
            break
            
    return posts

# --- 2. ПОИСК ПОХОЖИХ НОВОСТЕЙ ---
def find_similar_news(posts, top_n=10):
    if len(posts) < 2:
        print("Слишком мало постов для сравнения.")
        return

    texts = [p["text"] for p in posts]
    
    print(f"\nЗагрузка модели и создание эмбеддингов для {len(texts)} постов...")
    model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    embeddings = model.encode(texts)
    
    print("Вычисление матрицы похожести...\n")
    sim_matrix = cosine_similarity(embeddings)
    
    results = []

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = sim_matrix[i][j]
            
            if posts[i]['channel'] == posts[j]['channel']:
                continue
            
            results.append((score, i, j))
            
    # Сортируем пары от самых похожих к наименее похожим
    results.sort(key=lambda x: x[0], reverse=True)
    
    print(f"--- ТОП-{top_n} САМЫХ ПОХОЖИХ НОВОСТЕЙ ---\n")
    for rank, (score, i, j) in enumerate(results[:top_n], 1):
        post_1 = posts[i]
        post_2 = posts[j]
        
        t1_snippet = post_1['text'].replace('\n', ' ')[:100] + "..."
        t2_snippet = post_2['text'].replace('\n', ' ')[:100] + "..."
        
        print(f"#{rank} | Похожесть: {score:.3f} ({(score*100):.1f}%)")
        print(f"[{post_1.get('channel', 'unknown')}] {post_1['url']}")
        print(f"Текст: {t1_snippet}")
        print(f"[{post_2.get('channel', 'unknown')}] {post_2['url']}")
        print(f"Текст: {t2_snippet}")
        print("-" * 60)

# --- 3. РАБОТА С ФАЙЛАМИ (JSON) ---
def save_posts(new_posts, filename="news_cache.json"):
    # 1. Загружаем старые данные (если файла нет или он пустой — создаем пустой список)
    try:
        with open(filename, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        posts = []

    # 2. Собираем все старые ссылки в быстрое множество (set)
    existing_urls = {p["url"] for p in posts}
    
    # 3. Отбираем только те новые новости, ссылок на которые еще нет в множестве
    unique_new_posts = [p for p in new_posts if p["url"] not in existing_urls]
    
    # 4. Склеиваем старое с новым и перезаписываем файл
    if unique_new_posts:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(posts + unique_new_posts, f, ensure_ascii=False, indent=4)
        print(f"[OK] Добавлено {len(unique_new_posts)} новых постов.")
    else:
        print("[OK] Новых постов не найдено, база актуальна.")

def load_posts(filename="posts_cache.json"):
    if not os.path.exists(filename):
        print(f"\n[Ошибка] Файл '{filename}' не найден!")
        return []
        
    with open(filename, "r", encoding="utf-8") as f:
        posts = json.load(f)
    print(f"\n[OK] Загружено {len(posts)} постов из файла '{filename}'")
    return posts

from sklearn.feature_extraction.text import TfidfVectorizer

# --- 4. ПОИСК И ГРУППИРОВКА СЮЖЕТОВ ---
def find_news_clusters(posts, alpha = 0.7, similarity_threshold=0.55):
    if len(posts) < 2:
        print("Слишком мало постов для сравнения.")
        return

    texts = [p["text"] for p in posts]
    
    # 1. DENSE (Смысл и синонимы)
    print(f"\nЗагрузка Dense-модели и создание эмбеддингов для {len(texts)} постов...")
    dense_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    dense_embeddings = dense_model.encode(texts)
    sim_dense = cosine_similarity(dense_embeddings)
    
    # 2. SPARSE (Точные совпадения слов)
    print("Вычисление Sparse-матрицы (TF-IDF)...")
    # Добавляем базовые русские стоп-слова
    ru_stop_words = ["а", "в", "г", "да", "для", "до", "ее", "еще", "же", "за", 
                     "и", "из", "или", "как", "на", "не", "о", "об", "от", "по", 
                     "при", "с", "у", "что", "это", "этот", "к", "но", "то", "так"]

    # Используем базовый анализатор. Он даст больший вес редким именам и названиям.
    sparse_model = TfidfVectorizer(stop_words=ru_stop_words)
    sparse_embeddings = sparse_model.fit_transform(texts)
    sim_sparse = cosine_similarity(sparse_embeddings)
    
    # 3. HYBRID (Слияние двух миров)
    print(f"Объединение матриц (Hybrid Search)... alpha={alpha}, similarity={similarity_threshold}")
    # alpha — это вес Dense-модели. 
    # 0.6 означает, что итоговая оценка на 60% состоит из смысла и на 40% из точных слов.
    sim_matrix = (alpha * sim_dense) + ((1 - alpha) * sim_sparse)
    
    used_indices = set()
    clusters = []

    for i in range(len(texts)):
        if i in used_indices:
            continue
            
        current_cluster = [(i, 1.0)]
        used_indices.add(i)
        
        # СОЗДАЕМ ПАМЯТЬ КАНАЛОВ ДЛЯ ЭТОГО СЮЖЕТА
        # И сразу добавляем туда канал-источник
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
            
            # Если новость подходит по смыслу и времени...
            if score >= similarity_threshold and time_diff_hours <= 5:
                
                channel_j = posts[j].get('channel')
                
                # НОВАЯ ПРОВЕРКА: Если этот канал УЖЕ ЕСТЬ в текущем сюжете...
                if channel_j in channels_in_cluster:
                    # Помечаем пост как использованный, чтобы он не создал дубль-сюжет потом
                    used_indices.add(j) 
                    continue # Пропускаем добавление в кластер
                    
                # Если канала еще нет в сюжете, добавляем его
                current_cluster.append((j, score))
                used_indices.add(j)
                # И записываем в память, что от этого канала новость уже взяли
                channels_in_cluster.add(channel_j)
                
        if len(current_cluster) > 1:
            clusters.append(current_cluster)

    clusters.sort(key=lambda x: len(x), reverse=True)
    
    print(f"--- НАЙДЕНО СЮЖЕТОВ: {len(clusters)} (Порог сходства: {similarity_threshold*100}%) ---\n")
    
    for rank, cluster_items in enumerate(clusters[:15], 1):
        print(f"📌 СЮЖЕТ #{rank} (Опубликовали каналов: {len(cluster_items)})")
        
        for idx, score in cluster_items:
            post = posts[idx]
            snippet = post['text'][:120].replace('\n', ' ') + "..."
            
            if score == 1.0:
                print(f"  ⭐ [ИСТОЧНИК СЮЖЕТА] | Канал: {post.get('channel', 'unknown')} | {post['url']}")
            else:
                print(f"  🔗 [СХОДСТВО: {score*100:.1f}%] | Канал: {post.get('channel', 'unknown')} | {post['url']}")
                
            print(f"     Текст: {snippet}\n")
        print("-" * 70)

# --- 3. ЗАПУСК ---
if __name__ == "__main__":
    # ---------------- РЕЖИМ РАБОТЫ ----------------
    # True = парсим Telegram, сохраняем в файл, затем ищем похожее
    # False = НЕ парсим Telegram, просто берем данные из файла и ищем похожее
    SCRAPE_NEW_DATA = False 
#     SCRAPE_NEW_DATA = False 
    FILE_NAME = "/Users/elizavetapivovarova/Documents/experiments/embedding/assets/news_cache.json"
    # ----------------------------------------------

    if SCRAPE_NEW_DATA:
            channels = [
            #      "mosnews", 
            #             "ria_novosti_russiya", 
            #             "readovkanews",
                           "varlamov_news"
            # "ostorozhno_novosti",
            # "dmitrynikotin",
            # "bbcrussian",
            # "kommersant"
                          ]
            posts = []
            hours = 24

            # Собираем данные из всех каналов
            for channel in channels:
                  posts.extend(get_channel_posts(channel, hours))

            
            print(f"\nВсего собрано текстовых постов за {hours} часа: {len(posts)}")
            save_posts(posts, FILE_NAME)
    
    # Находим похожие сюжеты
    all_posts = load_posts(FILE_NAME)
    
    if all_posts:
        # Анализируем то, что прочитали из файла
        find_news_clusters(all_posts, alpha=0.5, similarity_threshold=0.6)