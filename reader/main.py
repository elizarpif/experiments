from pathlib import Path
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
import os
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # подгрузит переменные из .env в окружение

from database import (
    init_db,
    get_user_dict_with_contexts,
    save_or_update_item,
    get_all_user_items,
    update_status_by_id,
    delete_item_by_id,
)

from nlp_service import MultilingualNLPService
from schemas import AnalyzeRequest, SaveItemRequest, ExplainRequest

nlp_service = None

# Подключение к бесплатному Gemini API через совместимый протокол
client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=os.getenv("GEMINI_TOKEN")
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nlp_service
    init_db()
    nlp_service = MultilingualNLPService()
    yield


from auth import router as auth_router, get_current_user
from database import init_db, get_user_dict_with_contexts

app = FastAPI(title="Spanish Lexical Hub", lifespan=lifespan)

app.include_router(auth_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
def get_ui():
    return FileResponse(STATIC_DIR / "index.html")

@app.post("/api/analyze")
def analyze_text(
    payload: AnalyzeRequest,
    user_id: str = Depends(get_current_user)
    ):
    user_dict = get_user_dict_with_contexts(user_id, language=payload.language)
    phrases, rare_words = nlp_service.process_chapter(
        text=payload.text,
        user_id=user_id,
        user_dict=user_dict,
        language=payload.language
    )
    return {"phrases": phrases, "rare_words": rare_words}

class ExplainRequest(BaseModel):
    text: str
    sentence: str = ""
    lemma: str = ""
    item_type: str = "word"
    language: str = "es"  # "es" или "en"

class ExplainResponse(BaseModel):
    translation: str
    breakdown: str


class SaveItemRequest(BaseModel):
    user_id: str
    item_type: str
    term: str
    lemma: str
    context_sentence: str = ""
    status: str
    translation: str = ""
    breakdown: str = ""
    source: str = "Общее"
    language: str = "es"

@app.post("/api/explain", response_model=ExplainResponse)
def explain_text(payload: ExplainRequest):
    term = payload.text.strip()
    sentence = payload.sentence.strip() if payload.sentence else ""
    lemma = payload.lemma.strip()
    is_phrase = payload.item_type == "phrase"
    lang_name = "английского" if payload.language == "en" else "испанского"
    lang_code = "АНГЛИЙСКИЙ" if payload.language == "en" else "ИСПАНСКИЙ"

    if is_phrase:
        system_prompt = (
            f"Ты — профессиональный филолог и переводчик художественной литературы с {lang_name} языка на русский.\n"
            f"Разбери {lang_code} ОБОРОТ / ИДИОМУ в контексте предложения.\n\n"
            "Выведи результат СТРОГО по шаблону:\n"
            "RESULT:\n"
            "ПЕРЕВОД: <2-3 точных литературных перевода на русский язык через запятую>\n"
            "СОСТАВ: Буквально: <буквальное значение компонентов>. Переносное значение: <образный смысл фразеологизма>."
        )
    else:
        system_prompt = (
            f"Ты — профессиональный филолог и переводчик художественной литературы с {lang_name} языка на русский.\n"
            f"Разбери отдельное {lang_code} СЛОВО в контексте предложения.\n\n"
            "Выведи результат СТРОГО по шаблону:\n"
            "RESULT:\n"
            "ПЕРЕВОД: <2-3 точных литературных перевода на русский язык через запятую>\n"
            "СОСТАВ: Корень/базовое слово + реальные суффиксы/приставки с их смысловым оттенком."
        )

    user_prompt = (
        f"Контекст: «{sentence}»\n"
        f"Целевой элемент ({payload.language}): «{term}» (исходная форма: «{lemma}»)"
    )

    try:
        response = client.chat.completions.create(
            model="gemini-3.5-flash-lite",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=300
        )
        
        full_text = response.choices[0].message.content or ""
        res_block = full_text.split("RESULT:")[-1] if "RESULT:" in full_text else full_text
        
        trans_match = re.search(r"ПЕРЕВОД\s*[:\-]\s*(.+)", res_block, flags=re.IGNORECASE)
        break_match = re.search(r"СОСТАВ\s*[:\-]\s*(.+)", res_block, flags=re.IGNORECASE)

        translation = trans_match.group(1).strip().strip("*").strip() if trans_match else ""
        breakdown = break_match.group(1).strip().strip("*").strip() if break_match else ""

        if not translation and not breakdown:
            translation = res_block.strip()

        return ExplainResponse(translation=translation, breakdown=breakdown)
    except Exception as e:
        return ExplainResponse(translation=f"Ошибка Gemini API: {e}", breakdown="")

@app.post("/api/vocab/save")
def save_vocabulary_item(payload: SaveItemRequest):
    item_id = save_or_update_item(
        user_id=payload.user_id,
        item_type=payload.item_type,
        term=payload.term,
        lemma=payload.lemma,
        sentence=payload.context_sentence,
        status=payload.status,
        translation=payload.translation,
        breakdown=payload.breakdown,
        source=payload.source,
        language=payload.language
    )
    return {"status": "ok", "item_id": item_id}

@app.get("/api/vocab/{user_id}")
def get_user_vocabulary(
    user_id: str,
    language: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    return get_all_user_items(
        user_id=user_id,
        language=language,
        source=source,
        search=search,
        limit=limit,
        offset=offset
    )

@app.patch("/api/vocab/{item_id}/status")
def update_item_status(item_id: int, status: str):
    update_status_by_id(item_id, status)
    return {"status": "ok"}

@app.delete("/api/vocab/{item_id}")
def delete_vocabulary_item(item_id: int):
    delete_item_by_id(item_id)
    return {"status": "deleted"}

from database import get_user_sources  # не забудьте импортировать

@app.get("/api/sources/{user_id}")
def get_sources_list(user_id: str):
    sources = get_user_sources(user_id)
    return {"user_id": user_id, "sources": sources}