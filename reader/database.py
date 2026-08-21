import sqlite3
from typing import List, Dict, Any, Optional

DB_PATH = "lexical_hub.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                term TEXT NOT NULL,
                lemma TEXT NOT NULL,
                status TEXT NOT NULL,
                translation TEXT DEFAULT '',
                breakdown TEXT DEFAULT '',
                source TEXT DEFAULT 'Общее',
                language TEXT DEFAULT 'es',
                seen_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, lemma, language)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vocab_id INTEGER NOT NULL,
                sentence TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (vocab_id) REFERENCES vocabulary (id) ON DELETE CASCADE
            )
        """)
        # Автомиграция колонок на случай существующей БД
        try:
            conn.execute("ALTER TABLE vocabulary ADD COLUMN source TEXT DEFAULT 'Общее'")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE vocabulary ADD COLUMN language TEXT DEFAULT 'es'")
        except sqlite3.OperationalError:
            pass
        conn.commit()

def save_or_update_item(
    user_id: str,
    item_type: str,
    term: str,
    lemma: str,
    sentence: str,
    status: str,
    translation: str = "",
    breakdown: str = "",
    source: str = "Общее",
    language: str = "es"
) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, seen_count FROM vocabulary WHERE user_id = ? AND lemma = ? AND language = ?",
            (user_id, lemma, language)
        )
        row = cursor.fetchone()

        if row:
            vocab_id = row["id"]
            new_count = row["seen_count"] + 1
            cursor.execute(
                """
                UPDATE vocabulary 
                SET seen_count = ?, status = ?, 
                    translation = COALESCE(NULLIF(?, ''), translation),
                    breakdown = COALESCE(NULLIF(?, ''), breakdown),
                    source = ?
                WHERE id = ?
                """,
                (new_count, status, translation, breakdown, source, vocab_id)
            )
        else:
            cursor.execute(
                """
                INSERT INTO vocabulary (user_id, item_type, term, lemma, status, translation, breakdown, source, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, item_type, term, lemma, status, translation, breakdown, source, language)
            )
            vocab_id = cursor.lastrowid

        if sentence:
            cursor.execute(
                "INSERT INTO contexts (vocab_id, sentence) VALUES (?, ?)",
                (vocab_id, sentence)
            )
        conn.commit()
        return vocab_id

def get_user_dict_with_contexts(user_id: str, language: str = "es") -> Dict[str, Dict[str, Any]]:
    """Возвращает быстрый маппинг {lemma: info} для nlp_service при анализе текста."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, lemma, status, translation, breakdown, seen_count FROM vocabulary WHERE user_id = ? AND language = ?",
            (user_id, language)
        )
        rows = cursor.fetchall()
        
        result = {}
        for r in rows:
            result[r["lemma"]] = {
                "id": r["id"],
                "status": r["status"],
                "translation": r["translation"],
                "breakdown": r["breakdown"],
                "seen_count": r["seen_count"]
            }
        return result

def get_all_user_items(
    user_id: str,
    language: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Базовые условия фильтрации
        where_clauses = ["user_id = ?"]
        params = [user_id]

        if language and language != "all":
            where_clauses.append("language = ?")
            params.append(language)
        if source and source != "all":
            where_clauses.append("source = ?")
            params.append(source)
        if search:
            where_clauses.append("(lemma LIKE ? OR term LIKE ? OR translation LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])

        where_sql = " WHERE " + " AND ".join(where_clauses)

        # 1. Считаем общее количество подходящих записей
        cursor.execute(f"SELECT COUNT(*) as count FROM vocabulary {where_sql}", tuple(params))
        total_count = cursor.fetchone()["count"]

        # 2. Выбираем только нужную страницу
        query = f"SELECT * FROM vocabulary {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        items = cursor.fetchall()

        result = []
        for item in items:
            cursor.execute("SELECT sentence FROM contexts WHERE vocab_id = ?", (item["id"],))
            contexts = [c["sentence"] for c in cursor.fetchall()]
            result.append({
                "id": item["id"],
                "item_type": item["item_type"],
                "term": item["term"],
                "lemma": item["lemma"],
                "status": item["status"],
                "translation": item["translation"],
                "breakdown": item["breakdown"],
                "source": item["source"],
                "language": item["language"],
                "seen_count": item["seen_count"],
                "contexts": contexts
            })

        # Получаем также список уникальных источников для фильтра
        cursor.execute("SELECT DISTINCT source FROM vocabulary WHERE user_id = ? AND source != ''", (user_id,))
        sources = [row["source"] for row in cursor.fetchall()]

        return {
            "total": total_count,
            "items": result,
            "has_more": (offset + len(result)) < total_count,
            "sources": sources
        }
    
def update_status_by_id(item_id: int, status: str):
    with get_db() as conn:
        conn.execute("UPDATE vocabulary SET status = ? WHERE id = ?", (status, item_id))
        conn.commit()

def delete_item_by_id(item_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM contexts WHERE vocab_id = ?", (item_id,))
        conn.execute("DELETE FROM vocabulary WHERE id = ?", (item_id,))
        conn.commit()

def append_context_if_exists(user_id: str, lemma: str, sentence: str, language: str = "es") -> bool:
    """Добавляет контекст к существующему слову/обороту, если оно уже есть в словаре."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, seen_count FROM vocabulary WHERE user_id = ? AND lemma = ? AND language = ?",
            (user_id, lemma, language)
        )
        row = cursor.fetchone()
        if not row:
            return False

        vocab_id = row["id"]
        new_count = row["seen_count"] + 1

        cursor.execute(
            "UPDATE vocabulary SET seen_count = ? WHERE id = ?",
            (new_count, vocab_id)
        )
        if sentence:
            cursor.execute(
                "INSERT INTO contexts (vocab_id, sentence) VALUES (?, ?)",
                (vocab_id, sentence)
            )
        conn.commit()
        return True

def get_user_sources(user_id: str) -> List[str]:
    """Возвращает список всех уникальных источников пользователя."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT source FROM vocabulary WHERE user_id = ? AND source != '' ORDER BY source ASC",
            (user_id,)
        )
        return [row["source"] for row in cursor.fetchall()]