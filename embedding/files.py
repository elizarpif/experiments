import json
import os
from tqdm import tqdm # Библиотека для красивого прогресс-бара

# --- СЮДА ВСТАВЬТЕ ВАШУ ФУНКЦИЮ get_summary ИЗ ПРЕДЫДУЩЕГО ОТВЕТА ---
# def get_summary(text, max_length=90): ...

def process_and_save_summaries(filename="/Users/elizavetapivovarova/Documents/experiments/embedding/assets/news_cache_wo_summary.json"):
    if not os.path.exists(filename):
        print(f"Файл {filename} не найден!")
        return

    # 1. Загружаем данные
    print(f"Загрузка файла {filename}...")
    with open(filename, "r", encoding="utf-8") as f:
        posts = json.load(f)
        
    print(f"Всего постов в базе: {len(posts)}")

#     posts_to_process = [p for p in posts if "summary" not in p or not p["summary"]]
#     print(f"Постов без саммари: {len(posts_to_process)}")

#     if len(posts_to_process) == 0:
#         print("Все посты уже обработаны. Выход.")
#         return

    # 2. Генерируем саммари с прогресс-баром
    updated_count = 0
    
    # Оборачиваем список в tqdm для визуализации прогресса
    for post in tqdm(posts, desc="Генерация саммари"):
      #   # Если саммари уже есть, просто пропускаем (экономит кучу времени!)
      #   if "summary" in post and post["summary"]:
      #       continue
            
        text = post.get("text", "")
        if not text:
            post["summary"] = ""
            continue
            
        try:
            # Генерируем выжимку
            summary = get_summary(text)
            post["summary"] = summary
            updated_count += 1
            
        except Exception as e:
            print(f"\nОшибка при обработке поста {post.get('url')}: {e}")
            post["summary"] = "" # Оставляем пустым, чтобы не стопорить весь процесс

    # 3. Сохраняем обратно в файл
    print(f"\nСохранение {updated_count} новых саммари в файл...")
    
    # Перезаписываем тот же файл обновленными данными
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)
        
    print("[OK] Готово!")


from transformers import T5ForConditionalGeneration, T5Tokenizer
import torch

print("Загрузка модели суммаризации...")
# Загружаем токенизатор и модель один раз
device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
print(f"Саммаризатор работает на устройстве: {device}")

sum_tokenizer = T5Tokenizer.from_pretrained("IlyaGusev/rut5_base_sum_gazeta")
sum_model = T5ForConditionalGeneration.from_pretrained("IlyaGusev/rut5_base_sum_gazeta").to(device)

def get_summary(text, max_length=90):
    if len(text) < 450:
        return text
    # 1. Динамический паддинг: добивает только до длины самой длинной новости в батче 
    # (в нашем случае - просто обрезает длинные до 500, а короткие не трогает)
    inputs = sum_tokenizer(
        [text],
        max_length=500,
        padding=True, # Изменено здесь
        truncation=True,
        return_tensors="pt"
    ).to(device) # Перекидываем данные на то же устройство, где модель

    # 2. Обязательно передаем attention_mask!
    output_ids = sum_model.generate(
        input_ids=inputs["input_ids"],
        attention_mask=inputs["attention_mask"], # ЭТО СПАСЕТ ОТ ГАЛЛЮЦИНАЦИЙ
        max_length=max_length, # 90 токенов - это примерно 2-3 предложения, больше для выжимки не нужно
        no_repeat_ngram_size=3,
        num_beams=2, # Снизили для скорости
        early_stopping=True
    )[0]

    summary = sum_tokenizer.decode(output_ids, skip_special_tokens=True)
    return summary

# Запускаем процесс
if __name__ == "__main__":
    process_and_save_summaries()