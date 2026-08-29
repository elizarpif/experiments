import time
import random
import re
from playwright.sync_api import sync_playwright
from ebooklib import epub

# ================= НАСТРОЙКИ =================
SLUG = "94231--rezero-kara-hajimeru-isekai-seikatsu-outo-no-ichinichi-hen"
BOOK_URL = f"https://ranobelib.me/ru/book/{SLUG}?section=chapters"

EPUB_TITLE = "Re:Zero — Тома 29-30"
EPUB_AUTHOR = "Tappei Nagatsuki"
OUTPUT_FILE = "ReZero_Vol29_30.epub"

# Фильтрация
START_VOL = 29
END_VOL = 30
START_CHAPTER = 41

DELAY_MIN = 2.0
DELAY_MAX = 4.0
# ============================================

def parse_vol_and_ch(text, url=""):
    """Извлекает номер тома и главы из текста ссылки или из URL."""
    vol, ch = None, None
    
    # 1. Пробуем распарсить из текста
    v_match = re.search(r"[Тт]ом\s*(\d+)", text)
    c_match = re.search(r"[Гг]лава\s*([\d\.]+)", text)
    
    if v_match:
        vol = int(v_match.group(1))
    if c_match:
        ch = float(c_match.group(1))
        
    # 2. Если в тексте не было, берем из URL (.../read/v24/c69)
    if vol is None or ch is None:
        url_match = re.search(r"/v(\d+)/c([\d\.]+)", url)
        if url_match:
            vol = int(url_match.group(1))
            ch = float(url_match.group(2))
            
    return vol, ch

def format_chapter_html(title: str, text_content: str) -> str:
    paragraphs = text_content.split("\n")
    body_p = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
    
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <style>
        body {{ font-family: sans-serif; line-height: 1.6; padding: 4%; }}
        h1 {{ text-align: center; margin-bottom: 1.5em; }}
        p {{ text-indent: 1.5em; margin: 0.6em 0; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {body_p}
</body>
</html>"""

# def handle_age_modal(page):
#     """Закрывает окно подтверждения 18+."""
#     try:
#         # Убрали 'Войти', добавили специфичные для 18+ тексты
#         btn = page.locator("button:has-text('18'), button:has-text('Мне есть 18'), button:has-text('Да, мне есть 18')")
#         for i in range(btn.count()):
#             if btn.nth(i).is_visible(timeout=1000):
#                 print("Нажимаем подтверждение 18+...")
#                 btn.nth(i).click()
#                 time.sleep(1.5)
#                 break
#     except Exception:
#         pass
def handle_age_modal(page):
    """Закрывает окно подтверждения 18+ и ставит галочку 'Больше не показывать'."""
    try:
        # Ищем кнопку подтверждения, чтобы понять, открыто ли окно
        btn = page.locator("button:has-text('Мне есть 18+')")
        
        if btn.first.is_visible(timeout=2000):
            print("Обнаружено окно 18+. Отключаем его повторное появление...")
            
            # Ищем текст чекбокса и кликаем по нему
            checkbox_label = page.locator("text='Больше не показывать'")
            if checkbox_label.first.is_visible():
                checkbox_label.first.click()
                time.sleep(0.5)
            
            # Нажимаем саму кнопку подтверждения
            btn.first.click()
            time.sleep(1.5)
    except Exception:
        pass

def collect_all_chapters_via_dom(page):
    """Скроллит страницу и внутренние контейнеры для сбора всех ссылок из виртуального списка."""
    chapters_dict = {}
    last_count = 0
    unchanged_steps = 0
    max_scrolls = 150 # Увеличили количество скроллов для больших списков

    print("Начинаем сканирование списка глав скроллом...")
    
    # Кликаем 18+ один раз перед циклом
    handle_age_modal(page)
    
    # Наводим мышь в центр страницы для надежного скролла контейнеров
    page.mouse.move(page.viewport_size['width'] / 2, page.viewport_size['height'] / 2)

    for step in range(max_scrolls):
        # Собираем все видимые ссылки на чтение
        links = page.query_selector_all("a[href*='/read/']")
        
        for link in links:
            href = link.get_attribute("href")
            text = link.inner_text().strip()
            
            if href and '/read/v' in href:
                if not href.startswith("http"):
                    href = f"https://ranobelib.me{href}"
                
                if href not in chapters_dict:
                    clean_title = " ".join(text.split())
                    vol, ch = parse_vol_and_ch(clean_title, href)
                    if vol is not None and ch is not None:
                        chapters_dict[href] = {
                            "vol": vol,
                            "ch": ch,
                            "title": clean_title if clean_title else f"Том {vol} Глава {ch}",
                            "url": href
                        }

        current_count = len(chapters_dict)
        if current_count == last_count:
            unchanged_steps += 1
        else:
            unchanged_steps = 0
            last_count = current_count

        # Если за 8 скроллов ничего нового не появилось — дошли до конца
        if unchanged_steps >= 8 and current_count > 0:
            break

        # Универсальный скролл: мотаем окно и все скроллящиеся div-блоки
        page.evaluate('''
            let scrollers = document.querySelectorAll('div');
            for (let s of scrollers) {
                if (s.scrollHeight > s.clientHeight && getComputedStyle(s).overflowY !== 'hidden') {
                    s.scrollTop += 1200;
                }
            }
            window.scrollBy(0, 1200);
        ''')
        time.sleep(0.4)

    return list(chapters_dict.values())

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = context.new_page()

        print(f"Открываем страницу: {BOOK_URL}")
        page.goto(BOOK_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # 1. Собираем главы через улучшенный DOM-скроллинг
        all_chapters = collect_all_chapters_via_dom(page)
        print(f"Всего собрано уникальных глав: {len(all_chapters)}")

        # 2. Фильтрация глав
        target_chapters = []
        for ch in all_chapters:
            vol = ch["vol"]
            num = ch["ch"]

            if START_VOL <= vol <= END_VOL:
                if vol == START_VOL and num < START_CHAPTER:
                    continue
                target_chapters.append(ch)

        # Сортируем в хронологическом порядке (по тому, затем по главе)
        target_chapters.sort(key=lambda x: (x["vol"], x["ch"]))

        if not target_chapters:
            print("[!] Главы по заданному фильтру не найдены. Проверьте диапазон томов.")
            browser.close()
            return

        print(f"\nОтобрано для скачивания: {len(target_chapters)} глав.")
        print(f"Старт:  {target_chapters[0]['title']}")
        print(f"Финиш:  {target_chapters[-1]['title']}\n")

        # 3. Инициализация книги EPUB
        book = epub.EpubBook()
        book.set_identifier(f"rezero-vol-{START_VOL}-{END_VOL}")
        book.set_title(EPUB_TITLE)
        book.set_language("ru")
        book.add_author(EPUB_AUTHOR)

        epub_chapters = []

        # 4. Скачивание текста глав
        for idx, ch in enumerate(target_chapters, 1):
            print(f"[{idx}/{len(target_chapters)}] Скачиваем: {ch['title']}...")
            
            page.goto(ch["url"], wait_until="domcontentloaded", timeout=60000)
            handle_age_modal(page)

            # Ждем появления блока с текстом
            try:
                page.wait_for_selector(".reader-container, .text-content, [class*='reader-content'], div[class*='reader']", timeout=8000)
                time.sleep(1.0)
            except Exception:
                time.sleep(1.5)

            # Извлечение текста
            content_el = page.query_selector(".reader-container, .text-content, [class*='reader-content'], div[class*='reader']")
            if content_el:
                chapter_text = content_el.inner_text()
            else:
                chapter_text = page.locator("body").inner_text()

            # Добавляем страницу в EPUB
            ch_item = epub.EpubHtml(
                title=ch["title"],
                file_name=f"chapter_{idx:03d}.xhtml",
                lang="ru"
            )
            ch_item.content = format_chapter_html(ch["title"], chapter_text)
            
            book.add_item(ch_item)
            epub_chapters.append(ch_item)

            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        browser.close()

        # 5. Сборка EPUB
        book.toc = tuple(epub_chapters)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav"] + epub_chapters

        print(f"\nСохранение файла '{OUTPUT_FILE}'...")
        epub.write_epub(OUTPUT_FILE, book)
        print(f"Книга успешно сохранена в '{OUTPUT_FILE}'!")

if __name__ == "__main__":
    run()