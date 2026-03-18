import sqlite3
import json
import os
from datetime import datetime
from passlib.context import CryptContext
from typing import List, Dict, Any, Optional, Tuple

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Kullanıcılar
            cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT)')
            # AI Ayarları
            cursor.execute('''CREATE TABLE IF NOT EXISTS ai_configs (
                user_id INTEGER PRIMARY KEY, provider_type TEXT, model_name TEXT, api_key TEXT, use_multi_agent INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            
            # Migration: Add use_multi_agent column to existing tables
            try:
                cursor.execute("ALTER TABLE ai_configs ADD COLUMN use_multi_agent INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass # Sütun zaten var
            # Eski Geçmiş (geriye uyumluluk)
            cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp TEXT, title TEXT,
                intent TEXT, original_code TEXT, ai_suggestion TEXT, smells TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            # --- YENİ: Sohbetler ---
            cursor.execute('''CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT DEFAULT 'Yeni Sohbet',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            # --- YENİ: Mesajlar ---
            cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                smells_json TEXT DEFAULT '[]',
                timestamp TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE)''')
            conn.commit()

    # ===================== AUTH =====================
    def create_user(self, username: str, password: str) -> bool:
        hashed = pwd_context.hash(password[:72])
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, hashed))
            return True
        except Exception:
            return False

    def verify_user(self, username: str, password: str) -> Optional[Tuple]:
        with sqlite3.connect(self.db_path) as conn:
            user = conn.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            if user and pwd_context.verify(password[:72], user[2]):
                return user
            return None

    # ===================== AI CONFIG =====================
    def save_ai_config(self, user_id: int, p_type: str, m_name: str, key: str, use_multi_agent: bool = True) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT OR REPLACE INTO ai_configs (user_id, provider_type, model_name, api_key, use_multi_agent) VALUES (?, ?, ?, ?, ?)',
                         (user_id, p_type, m_name, key, 1 if use_multi_agent else 0))
            conn.commit()

    def get_ai_config(self, user_id: int) -> Tuple[str, str, str, bool]:
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT provider_type, model_name, api_key, use_multi_agent FROM ai_configs WHERE user_id = ?', (user_id,)).fetchone()
            if res:
                return (res[0], res[1], res[2], bool(res[3]))
            return ("ollama", "qwen2.5-coder:7b", "", True)

    # ===================== ESKİ GEÇMİŞ (Geriye Uyumluluk) =====================
    def save_analysis(self, user_id: int, title: str, intent: str, code: str, suggestion: str, smells: list) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT INTO history (user_id, timestamp, title, intent, original_code, ai_suggestion, smells) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), title, intent, code, suggestion, json.dumps(smells)))

    def get_user_history(self, user_id: int) -> List[Tuple]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT id, timestamp, title, intent FROM history WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    def get_analysis_detail(self, item_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT original_code, ai_suggestion, smells FROM history WHERE id = ?', (item_id,)).fetchone()
            return {"code": res[0], "suggestion": res[1], "smells": json.loads(res[2])} if res else None

    def delete_analysis(self, item_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM history WHERE id = ?', (item_id,))
            conn.commit()

    def rename_analysis(self, item_id: int, new_title: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE history SET title = ? WHERE id = ?', (new_title, item_id))
            conn.commit()

    # ===================== YENİ: SOHBETLER =====================
    def create_conversation(self, user_id: int, title: str = "Yeni Sohbet") -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)',
                (user_id, title, now, now)
            )
            conn.commit()
            return cursor.lastrowid

    def get_user_conversations(self, user_id: int) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                'SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC',
                (user_id,)
            ).fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def rename_conversation(self, conv_id: int, new_title: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?', (new_title, now, conv_id))
            conn.commit()

    def delete_conversation(self, conv_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('DELETE FROM messages WHERE conversation_id = ?', (conv_id,))
            conn.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
            conn.commit()

    # ===================== YENİ: MESAJLAR =====================
    def add_message(self, conversation_id: int, role: str, content: str, smells: list = None) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        smells_json = json.dumps(smells) if smells else "[]"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                'INSERT INTO messages (conversation_id, role, content, smells_json, timestamp) VALUES (?, ?, ?, ?, ?)',
                (conversation_id, role, content, smells_json, now)
            )
            # Sohbetin updated_at'ini güncelle
            conn.execute('UPDATE conversations SET updated_at = ? WHERE id = ?', (now, conversation_id))
            conn.commit()
            return cursor.lastrowid

    def get_conversation_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                'SELECT id, role, content, smells_json, timestamp FROM messages WHERE conversation_id = ? ORDER BY id ASC',
                (conversation_id,)
            ).fetchall()
            return [
                {"id": r[0], "role": r[1], "content": r[2], "smells": json.loads(r[3]), "timestamp": r[4]}
                for r in rows
            ]

    # ===================== WORKSPACE =====================
    def _ensure_workspace_table(self):
        """Workspace tablosunu oluştur (mevcut DB'lerle geriye uyumlu)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            conn.commit()

    def save_workspace(self, user_id: int, path: str) -> None:
        """Kullanıcının workspace yolunu kaydet/güncelle."""
        self._ensure_workspace_table()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            # Aynı kullanıcı + aynı path var mı?
            existing = conn.execute(
                'SELECT id FROM workspaces WHERE user_id = ? AND path = ?', (user_id, path)
            ).fetchone()
            if existing:
                conn.execute(
                    'UPDATE workspaces SET last_accessed = ? WHERE id = ?', (now, existing[0])
                )
            else:
                conn.execute(
                    'INSERT INTO workspaces (user_id, path, last_accessed) VALUES (?, ?, ?)',
                    (user_id, path, now)
                )
            conn.commit()

    def get_last_workspace(self, user_id: int) -> Optional[str]:
        """Kullanıcının en son açtığı workspace yolunu döndürür."""
        self._ensure_workspace_table()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                'SELECT path FROM workspaces WHERE user_id = ? ORDER BY last_accessed DESC, id DESC LIMIT 1',
                (user_id,)
            ).fetchone()
            return row[0] if row else None