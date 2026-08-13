import html
import json
import logging
import traceback
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

import os
import glob
from datetime import datetime

# Ваш класс агрегатора
from news_parser import NewsGetter

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

import openai
client = openai.AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama" # Ключ тут не важен, но библиотека требует, чтобы он был не пустой
)

# Определяем путь к папке, где лежит текущий скрипт
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Путь к папке assets (всегда рядом со скриптом)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Безопасно считываем токен и ID
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEVELOPER_CHAT_ID = os.getenv("DEVELOPER_CHAT_ID")

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения!")

CHANNELS = [
    "mosnews", "ria_novosti_russiya", "readovkanews", 
    "varlamov_news", "ostorozhno_novosti", "dmitrynikotin", 
    "bbcrussian", "kommersant"
]

class NewsBot:
    def __init__(self, token):
        self.token = token
        self.help_msg = (
            "🤖 <b>Привет! Я бот-агрегатор новостей.</b>\n\n"
            "Я читаю Telegram-каналы, нахожу дубликаты, убираю воду "
            "и выдаю вам только самую суть главных сюжетов дня.\n\n"
            "Команды:\n"
            "/get_news - получить Топ-5 сюжетов\n"
            "/get_news [число] - получить нужное количество (например: /get_news 3)\n"
            "/help - справка"
        )
        

        # Флаг для контроля первого запуска
        self.is_first_run = True

        self.llm_cache = {}
        
        # 1. Загружаем нейросети
        logger.info("Инициализация NewsGetter...")
        self.news_app = NewsGetter(ASSETS_DIR, "news")

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ ФАЙЛОВ ---
    def get_today_filename(self):
        """Возвращает путь к файлу с текущей датой в папке assets"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(ASSETS_DIR, f"news_{current_date}.json")

    def get_latest_filename(self):
        """Находит самый свежий файл новостей в папке assets"""
        # Ищем все файлы news_*.json внутри нашей папки assets
        search_pattern = os.path.join(ASSETS_DIR, "news_*.json")
        files = glob.glob(search_pattern)
        
        if not files:
            return self.get_today_filename()
            
        # Сортировка по имени отлично работает для формата YYYY-MM-DD
        return max(files)

    
    # --- ФОНОВАЯ ЗАДАЧА (Теперь она асинхронная) ---
    async def scheduled_scraping(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("Начат плановый фоновый сбор новостей...")

        daily_filename = self.get_today_filename()
        self.news_app.cache_file = daily_filename

        try:
            # УМНЫЙ СТАРТ: Если это первый запуск после включения бота
            if self.is_first_run:
                self.is_first_run = False # Сразу снимаем флаг
                
                # Проверяем, не собирали ли мы УЖЕ новости именно СЕГОДНЯ
                if os.path.exists(daily_filename):
                    existing_posts = self.news_app.load_posts()
                    if len(existing_posts) > 0:
                        logger.info(f"Сегодняшняя база ({daily_filename}) уже существует. Пропускаем сбор.")
                        return 
                else:
                    logger.info(f"Файл {daily_filename} не найден. Начинаем сбор...")
            
            # Стандартный парсинг (сработает, если базы нет, либо через 24 часа)
            await self.news_app.process_news(CHANNELS, hours=24, scrape_new=True)
            logger.info("Плановый сбор успешно завершен!")
        except Exception as e:
            logger.error(f"Ошибка при фоновом сборе: {e}")

    # --- КОМАНДЫ БОТА (Везде добавлено async и await) ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        await update.message.reply_text(f"Привет, {user.first_name}!\n\n{self.help_msg}", parse_mode=ParseMode.HTML)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(self.help_msg, parse_mode=ParseMode.HTML)

    # --- КОМАНДА /get_news ---
    async def get_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # 1. Определение лимита
        limit = 5
        if context.args:
            try:
                limit = int(context.args[0])
                if limit < 1: limit = 1
                elif limit > 15: limit = 15
            except ValueError:
                await update.message.reply_text("⚠️ Пожалуйста, укажите число. Например: /get_news 3")
                return

        # Используем effective_chat, чтобы бот не падал, даже если update.message пришел пустым
        chat_id = update.effective_chat.id
        msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Достаю данные из базы...")
        
        # 2. Находим свежий файл новостей
        latest_news_file = self.news_app.get_latest_filename() 
        self.news_app.cache_file = latest_news_file
        
        # 3. Вычисляем имя файла кластеров
        base_name = os.path.basename(latest_news_file)
        cluster_filename = base_name.replace("news_", "clusters_")
        
        # 4. Загружаем обогащенные данные (уже с фактами внутри!)
        clusters_data = self.news_app.load_clusters(cluster_filename)
        all_posts = self.news_app.load_posts()
        
        if not clusters_data:
            await msg.edit_text("🤷‍♀️ База сюжетов пуста или еще не рассчитана.")
            return
            
        try:
            await msg.delete()
        except Exception:
            pass
        
        # 5. Формирование ответа (Берем данные прямо из словаря cluster_data)
        header = f"📊 <b>Найдено сюжетов за сутки: {len(clusters_data)}</b>\nВывожу Топ-{min(limit, len(clusters_data))}:\n\n"
        
        message_chunks = []
        current_chunk = header
        
        for rank, cluster_data in enumerate(clusters_data[:limit], 1):
            # Теперь данные уже готовы!
            dry_fact = cluster_data.get("fact", "Нет описания")
            items = cluster_data.get("items", []) # это список кортежей [(idx, score), ...]
            
            sources_lines = []
            for idx_data in items:
                idx = idx_data[0] # берем индекс поста
                post = all_posts[idx]
                
                channel_name = post.get('channel', 'unknown')
                snippet = post['text'][:120].replace('\n', ' ').strip()
                sources_lines.append(f"🔹 <a href='{post['url']}'><b>{channel_name}</b></a>: <i>{snippet}...</i>")
            
            sources_html = "\n\n".join(sources_lines)
        
            # Достаем "сомнительные" новости, если они есть
            outliers = cluster_data.get("outliers", [])
            outlier_html = ""
            if outliers:
                outlier_html = "\n\n⚠️ <b>Возможно, тоже об этом:</b>\n"
                for idx_data in outliers:
                    idx = idx_data[0]
                    p = all_posts[idx]
                    outlier_html += f"🔹 <a href='{p['url']}'>{p['channel']}</a> <i>(скор: {idx_data[1]:.2f})</i>\n"

            cluster_text = (
                f"📌 <b>Сюжет #{rank}</b>\n\n"
                f"🔥 <b>СУТЬ: {dry_fact}</b>\n\n"
                f"📰 <b>Написали ({len(items)}):</b>\n{sources_html}"
                f"{outlier_html}"
                f"\n〰️〰️〰️〰️〰️〰️〰️〰️\n\n"
            )
            
            if len(current_chunk) + len(cluster_text) > 4000:
                message_chunks.append(current_chunk) 
                current_chunk = cluster_text         
            else:
                current_chunk += cluster_text        
                
        if current_chunk:
            message_chunks.append(current_chunk)
            
        for chunk in message_chunks:
            await update.message.reply_text(
                chunk, 
                parse_mode=ParseMode.HTML, 
                disable_web_page_preview=True 
            )

    # --- ОБРАБОТЧИК ОШИБОК ---
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = ''.join(tb_list)
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        message = (
            f'An exception was raised while handling an update\n'
            f'<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n'
            f'<pre>{html.escape(tb_string)}</pre>'
        )
        await context.bot.send_message(chat_id=DEVELOPER_CHAT_ID, text=message[-4096:], parse_mode=ParseMode.HTML)

    # --- ЗАПУСК ---
    def run(self):
        logger.info("Сборка приложения бота...")
        
        # Новый синтаксис запуска для версии 20+
        application = Application.builder().token(self.token).build()

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("get_news", self.get_news))
        application.add_error_handler(self.error_handler)

        # Фоновая задача: 86400 секунд (24 часа), старт через 10 секунд
        application.job_queue.run_repeating(self.scheduled_scraping, interval=86400, first=10)

        logger.info("Бот запущен и готов к работе!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)




if __name__ == '__main__':
    bot = NewsBot(TOKEN)
    bot.run()