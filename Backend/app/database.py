import sqlite3
import json
import os
from datetime import datetime
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Kullanıcılar
            cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT)')
            # AI Ayarları
            cursor.execute('''CREATE TABLE IF NOT EXISTS ai_configs (
                user_id INTEGER PRIMARY KEY, provider_type TEXT, model_name TEXT, api_key TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            # Geçmiş
            cursor.execute('''CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, timestamp TEXT, title TEXT,
                intent TEXT, original_code TEXT, ai_suggestion TEXT, smells TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            conn.commit()

    # --- AUTH ---
    def create_user(self, username, password):
        hashed = pwd_context.hash(password[:72])
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, hashed))
            return True
        except: return False

    def verify_user(self, username, password):
        with sqlite3.connect(self.db_path) as conn:
            user = conn.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            if user and pwd_context.verify(password[:72], user[2]): return user
            return None

    # --- AI CONFIG ---
    def save_ai_config(self, user_id, p_type, m_name, key):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT OR REPLACE INTO ai_configs (user_id, provider_type, model_name, api_key) VALUES (?, ?, ?, ?)',
                         (user_id, p_type, m_name, key))
            conn.commit()

    def get_ai_config(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT provider_type, model_name, api_key FROM ai_configs WHERE user_id = ?', (user_id,)).fetchone()
            return res if res else ("ollama", "qwen2.5-coder:7b", "")

    # --- HISTORY ---
    def save_analysis(self, user_id, title, intent, code, suggestion, smells):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('INSERT INTO history (user_id, timestamp, title, intent, original_code, ai_suggestion, smells) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), title, intent, code, suggestion, json.dumps(smells)))

    def get_user_history(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute('SELECT id, timestamp, title, intent FROM history WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()
    
    def get_analysis_detail(self, item_id):
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute('SELECT original_code, ai_suggestion, smells FROM history WHERE id = ?', (item_id,)).fetchone()
            return {"code": res[0], "suggestion": res[1], "smells": json.loads(res[2])} if res else None
    
    def delete_analysis(self, item_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM history WHERE id = ?', (item_id,))
            conn.commit()

    def rename_analysis(self, item_id, new_title):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE history SET title = ? WHERE id = ?', (new_title, item_id))
            conn.commit()