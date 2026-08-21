import sqlite3

DB_FILE = "user_vocab.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 1. Создание таблиц, если базы ещё нет
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                term TEXT NOT NULL,
                lemma TEXT NOT NULL,
                translation TEXT DEFAULT '',
                status TEXT DEFAULT 'learning',
                seen_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, lemma)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                sentence TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES vocabulary_items(id) ON DELETE CASCADE,
                UNIQUE(item_id, sentence)
            )
        """)

        # 2. Авто-миграция для существующей базы: добавляем translation, если её нет
        cursor.execute("PRAGMA table_info(vocabulary_items)")
        columns = [column[1] for column in cursor.fetchall()]
        if "translation" not in columns:
            cursor.execute("ALTER TABLE vocabulary_items ADD COLUMN translation TEXT DEFAULT ''")

        conn.commit()

def append_context_if_exists(user_id: str, lemma: str, sentence: str) -> dict | None:
    if not sentence:
        return None
        
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status, translation FROM vocabulary_items WHERE user_id = ? AND lemma = ?", (user_id, lemma.lower()))
        row = cursor.fetchone()
        if not row:
            return None
            
        item_id, status, translation = row
        cursor.execute("""
            INSERT OR IGNORE INTO item_contexts (item_id, sentence)
            VALUES (?, ?)
        """, (item_id, sentence.strip()))
        
        cursor.execute("""
            UPDATE vocabulary_items 
            SET seen_count = (SELECT COUNT(*) FROM item_contexts WHERE item_id = ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (item_id, item_id))
        conn.commit()
        
        cursor.execute("SELECT sentence FROM item_contexts WHERE item_id = ? ORDER BY added_at ASC", (item_id,))
        contexts = [r[0] for r in cursor.fetchall()]
        
        return {
            "id": item_id,
            "status": status,
            "translation": translation,
            "seen_count": len(contexts),
            "contexts": contexts
        }

def save_or_update_item(user_id: str, item_type: str, term: str, lemma: str, sentence: str, status: str, translation: str = "") -> int:
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vocabulary_items (user_id, item_type, term, lemma, status, translation)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, lemma) DO UPDATE SET
                status = excluded.status,
                translation = COALESCE(NULLIF(excluded.translation, ''), vocabulary_items.translation),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """, (user_id, item_type, term, lemma.lower(), status, translation))
        
        item_id = cursor.fetchone()[0]
        
        if sentence:
            cursor.execute("""
                INSERT OR IGNORE INTO item_contexts (item_id, sentence)
                VALUES (?, ?)
            """, (item_id, sentence.strip()))
            
        cursor.execute("""
            UPDATE vocabulary_items 
            SET seen_count = (SELECT COUNT(*) FROM item_contexts WHERE item_id = ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (item_id, item_id))
        
        conn.commit()
        return item_id

def get_user_dict_with_contexts(user_id: str) -> dict:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.id, v.lemma, v.status, v.translation, c.sentence 
            FROM vocabulary_items v
            LEFT JOIN item_contexts c ON v.id = c.item_id
            WHERE v.user_id = ?
        """, (user_id,))
        
        result = {}
        for row in cursor.fetchall():
            lemma = row["lemma"]
            if lemma not in result:
                result[lemma] = {
                    "id": row["id"],
                    "status": row["status"],
                    "translation": row["translation"],
                    "contexts": []
                }
            if row["sentence"]:
                result[lemma]["contexts"].append(row["sentence"])
                
        for item in result.values():
            item["seen_count"] = len(item["contexts"])
            
        return result

def get_all_user_items(user_id: str) -> list[dict]:
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, item_type, term, lemma, status, translation, created_at, updated_at
            FROM vocabulary_items 
            WHERE user_id = ? 
            ORDER BY updated_at DESC
        """, (user_id,))
        items = [dict(r) for r in cursor.fetchall()]
        
        for item in items:
            cursor.execute("SELECT sentence FROM item_contexts WHERE item_id = ? ORDER BY added_at ASC", (item["id"],))
            item["contexts"] = [r[0] for r in cursor.fetchall()]
            item["seen_count"] = len(item["contexts"])
            
        return items

def update_status_by_id(item_id: int, status: str):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE vocabulary_items SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, item_id))
        conn.commit()

def delete_item_by_id(item_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM vocabulary_items WHERE id = ?", (item_id,))
        conn.commit()