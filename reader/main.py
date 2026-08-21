from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
from deep_translator import GoogleTranslator

from database import (
    init_db,
    get_user_dict_with_contexts,
    save_or_update_item,
    get_all_user_items,
    update_status_by_id,
    delete_item_by_id,
)
from nlp_service import SpanishNLPService
from schemas import AnalyzeRequest, SaveItemRequest, TranslateRequest

nlp_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nlp_service
    init_db()
    nlp_service = SpanishNLPService()
    yield

app = FastAPI(title="Spanish Lexical Hub", lifespan=lifespan)

STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"

@app.get("/", response_class=HTMLResponse)
def get_ui():
    return FileResponse(STATIC_INDEX)

@app.post("/api/analyze")
def analyze_text(payload: AnalyzeRequest):
    user_dict = get_user_dict_with_contexts(payload.user_id)
    phrases, rare_words = nlp_service.process_chapter(payload.text, payload.user_id, user_dict)
    return {"phrases": phrases, "rare_words": rare_words}

# @app.post("/api/translate")
# def translate_text(payload: TranslateRequest):
#     try:
#         translated = GoogleTranslator(source=payload.source_lang, target=payload.target_lang).translate(payload.text)
#         return {"translated": translated}
#     except Exception as e:
#         return {"translated": f"Ошибка перевода: {e}"}

from openai import OpenAI
from schemas import TranslateRequest

# Локальный клиент Ollama
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"  # Ollama не требует ключ, но поле не должно быть пустым
)

@app.post("/api/translate")
def translate_text(payload: TranslateRequest):
    term = payload.text.strip()
    sentence = payload.sentence.strip() if hasattr(payload, "sentence") and payload.sentence else ""
    # Если на фронтенде передается лемма, используем её, иначе пробуем spaCy
    lemma = getattr(payload, "lemma", None)
    if not lemma and nlp_service:
        doc = nlp_service.nlp(term)
        lemma = doc[0].lemma_ if len(doc) > 0 else term

    system_prompt = (
        "You are an expert Spanish-to-Russian literary translator specializing in fantasy and fiction.\n"
        "You will be given a target word, its grammatical lemma (base form), and the sentence context.\n\n"
        "Instructions:\n"
        "1. Use the lemma to anchor the root meaning (e.g., lemma 'fiera' = wild beast/ferocious creature).\n"
        "2. Understand how the word functions in the scene (tone, relationship between characters, genre).\n"
        "3. Provide 3-4 vivid, natural Russian translations that fit this exact context.\n\n"
        "Format: Return ONLY the comma-separated Russian translations. Nothing else."
    )

    user_prompt = (
        f"Context sentence: \"{sentence}\"\n"
        f"Target word: \"{term}\"\n"
        f"Base lemma: \"{lemma}\""
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:7b",  # Крайне рекомендуется переключить на 7b
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=60
        )
        translated = response.choices[0].message.content.strip().strip('"').strip('.')
        return {"translated": translated}
    except Exception as e:
        return {"translated": f"Ошибка: {e}"}
    
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
    )
    return {"status": "ok", "item_id": item_id}

@app.get("/api/vocab/{user_id}")
def get_user_vocabulary(user_id: str):
    items = get_all_user_items(user_id)
    return {"user_id": user_id, "total": len(items), "items": items}

@app.patch("/api/vocab/{item_id}/status")
def update_item_status(item_id: int, status: str):
    update_status_by_id(item_id, status)
    return {"status": "ok"}

@app.delete("/api/vocab/{item_id}")
def delete_vocabulary_item(item_id: int):
    delete_item_by_id(item_id)
    return {"status": "deleted"}

