import os
import json
from news_parser import NewsGetter # Импортируем ваш класс

# НАСТРОЙКИ
ASSETS_DIR = "/Users/elizavetapivovarova/Documents/experiments/embedding/assets"
# Укажите имя файла, для которого нужно посчитать сюжеты (или оставьте None, чтобы посчитать для самого свежего)
FILE_TO_PROCESS = "news_2026-08-10.json" 
CLUSTER_FILENAME = "clusters_2026-08-10.json"

async def run_calculation():
    # 1. Инициализируем наш парсер
    getter = NewsGetter(base_dir=ASSETS_DIR, base_name="news")
    
 # 2. Определяем путь к файлу новостей
    if FILE_TO_PROCESS:
        file_path = os.path.join(ASSETS_DIR, FILE_TO_PROCESS)
    else:
        file_path = getter.get_latest_filename()
    
    if not os.path.exists(file_path):
        print(f"❌ Файл {file_path} не найден!")
        return

    print(f"--- Обработка файла: {os.path.basename(file_path)} ---")
    
    # 3. Загружаем посты
    with open(file_path, "r", encoding="utf-8") as f:
        posts = json.load(f)
    
    print(f"Загружено {len(posts)} постов. Ищем кластеры и противоречия...")
    
    # 4. Считаем кластеры (теперь они возвращают структуру с items и outliers)
    raw_clusters = getter.find_news_clusters(posts)
    print(f"Найдено сюжетов: {len(raw_clusters)}. Генерация фактов через LLM...")
    
    # 5. Обогащаем каждый сюжет фактом от LLM
    enriched_clusters = []
    
    for idx, cluster_data in enumerate(raw_clusters, 1):
        main_items = cluster_data["items"]
        outliers = cluster_data["outliers"]
        
        # Собираем тексты только основного сюжета для генерации сути
        cluster_texts = [posts[item[0]]['text'] for item in main_items]
        cluster_ids = [str(item[0]) for item in main_items]
        
        # Генерируем факт (вызываем асинхронный метод парсера)
        fact = await getter.get_cluster_fact(cluster_texts, cluster_ids)
        
        print(f"[{idx}/{len(raw_clusters)}] Сюжет сгенерирован (outliers: {len(outliers)})")
        
        # Сохраняем полную структуру в итоговый список
        enriched_clusters.append({
            "fact": fact,
            "items": main_items,
            "outliers": outliers
        })
    
    # 6. Сохраняем в файл clusters_...
    base_filename = os.path.basename(file_path)
    cluster_filename = base_filename.replace("news_", "clusters_")
    
    getter.save_clusters(enriched_clusters, cluster_filename)
    
    print(f"\n[OK] Готово! Сюжеты, факты и аутлайеры сохранены в {cluster_filename}")

import asyncio

if __name__ == "__main__":
    asyncio.run(run_calculation())