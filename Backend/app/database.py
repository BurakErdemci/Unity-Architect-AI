import sqlite3
import json
import os
import secrets
from contextlib import closing
from datetime import datetime, timedelta
import bcrypt
from typing import List, Dict, Any, Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.session_ttl_minutes = int(os.environ.get("SESSION_TTL_MINUTES", "1440"))
        self._fernet = self._build_fernet()
        self._create_tables()

    def _build_fernet(self) -> Fernet:
        # 1. Explicit env var — CI veya ileri kullanıcı override'ı
        env_key = os.environ.get("API_KEY_ENCRYPTION_KEY")
        if env_key:
            return Fernet(env_key.encode("utf-8"))

        # 2. OS keystore — Windows Credential Manager / macOS Keychain
        #    Key asla DB dizinine yazılmaz, OS'un güvenli deposunda tutulur
        try:
            import keyring
            _KR_SERVICE = "unity-architect-ai"
            _KR_USER = "fernet-key"

            stored = keyring.get_password(_KR_SERVICE, _KR_USER)
            if stored:
                return Fernet(stored.encode("utf-8"))

            # Eski dosya tabanlı key varsa keystore'a migrate et
            db_dir = os.path.dirname(self.db_path) or "."
            legacy_path = os.path.join(db_dir, "api_key_fernet.key")
            if os.path.exists(legacy_path):
                with open(legacy_path, "rb") as f:
                    key = f.read().strip()
                keyring.set_password(_KR_SERVICE, _KR_USER, key.decode("utf-8"))
                try:
                    os.remove(legacy_path)
                except OSError:
                    pass
                return Fernet(key)

            # İlk kurulum: yeni key üret, keystore'a kaydet
            key = Fernet.generate_key()
            keyring.set_password(_KR_SERVICE, _KR_USER, key.decode("utf-8"))
            return Fernet(key)

        except Exception:
            pass

        # 3. Fallback: keyring kullanılamıyorsa dosya tabanlı (eski davranış)
        db_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        key_path = os.path.join(db_dir, "api_key_fernet.key")

        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass

        return Fernet(key)

    def _encrypt_api_key(self, api_key: str) -> str:
        encrypted = self._fernet.encrypt(api_key.encode("utf-8")).decode("utf-8")
        return f"enc:{encrypted}"

    def _decrypt_api_key(self, stored_value: str) -> str:
        if not stored_value:
            return ""
        if not stored_value.startswith("enc:"):
            return stored_value
        token = stored_value[4:].encode("utf-8")
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken:
            return ""

    def _create_tables(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.cursor()
            # Kullanıcılar
            cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, email TEXT, avatar_url TEXT, oauth_provider TEXT, oauth_id TEXT)')
            # Migration: OAuth alanlarını mevcut tabloya ekle
            for col, col_type in [("email", "TEXT"), ("avatar_url", "TEXT"), ("oauth_provider", "TEXT"), ("oauth_id", "TEXT")]:
                try:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass
            # AI Ayarları
            cursor.execute('''CREATE TABLE IF NOT EXISTS ai_configs (
                user_id INTEGER PRIMARY KEY, provider_type TEXT, model_name TEXT, api_key TEXT, use_multi_agent INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            
            # Migration: Add use_multi_agent column to existing tables
            try:
                cursor.execute("ALTER TABLE ai_configs ADD COLUMN use_multi_agent INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass # Sütun zaten var
            try:
                cursor.execute("ALTER TABLE ai_configs ADD COLUMN force_claude_coder INTEGER DEFAULT 0")
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
            # API Key Kasası — provider başına kalıcı key saklama
            cursor.execute('''CREATE TABLE IF NOT EXISTS api_keys (
                user_id INTEGER NOT NULL,
                provider_type TEXT NOT NULL,
                api_key TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider_type),
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id))''')
            try:
                cursor.execute("ALTER TABLE sessions ADD COLUMN expires_at TEXT")
            except sqlite3.OperationalError:
                pass
            cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL
            )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS oauth_completions (
                code TEXT PRIMARY KEY,
                session_token TEXT NOT NULL,
                created_at TEXT NOT NULL
            )''')
            conn.commit()
        self._backfill_session_expiry()

    def _backfill_session_expiry(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            rows = conn.execute(
                "SELECT token, created_at FROM sessions WHERE expires_at IS NULL OR expires_at = ''"
            ).fetchall()
            for token, created_at in rows:
                try:
                    created_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    created_dt = datetime.now()
                expires_at = (created_dt + timedelta(minutes=self.session_ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (expires_at, token))
            conn.commit()

    # ===================== AUTH =====================
    def create_user(self, username: str, password: str) -> bool:
        hashed = bcrypt.hashpw(password[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        try:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, hashed))
            return True
        except Exception:
            return False

    def verify_user(self, username: str, password: str) -> Optional[Tuple]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            user = conn.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,)).fetchone()
            if user and bcrypt.checkpw(password[:72].encode("utf-8"), user[2].encode("utf-8")):
                return user
            return None

    def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                'SELECT id, username, email, avatar_url FROM users WHERE id = ?',
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "user_id": row[0],
                "username": row[1],
                "email": row[2] or "",
                "avatar": row[3] or "",
            }

    # ===================== SESSION =====================
    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now_dt = datetime.now()
        now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        expires_at = (now_dt + timedelta(minutes=self.session_ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
            conn.execute(
                'INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
                (token, user_id, now, expires_at)
            )
            conn.commit()
        return token

    def get_user_by_session(self, token: str) -> Optional[Tuple[int, str]]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                '''SELECT users.id, users.username
                   FROM sessions
                   JOIN users ON users.id = sessions.user_id
                   WHERE sessions.token = ? AND sessions.expires_at >= ?''',
                (token, now)
            ).fetchone()
            conn.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
            conn.commit()
            return (row[0], row[1]) if row else None

    def delete_session(self, token: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
            conn.commit()

    # ===================== OAUTH STATE =====================
    def create_oauth_state(self, provider: str) -> str:
        state = secrets.token_urlsafe(32)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('DELETE FROM oauth_states WHERE created_at < ?', ((datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),))
            conn.execute(
                'INSERT INTO oauth_states (state, provider, created_at) VALUES (?, ?, ?)',
                (state, provider, now)
            )
            conn.commit()
        return state

    def consume_oauth_state(self, provider: str, state: str) -> bool:
        if not state:
            return False
        cutoff = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                'SELECT state FROM oauth_states WHERE state = ? AND provider = ? AND created_at >= ?',
                (state, provider, cutoff)
            ).fetchone()
            if not row:
                return False
            conn.execute('DELETE FROM oauth_states WHERE state = ?', (state,))
            conn.commit()
            return True

    def create_oauth_completion(self, session_token: str) -> str:
        code = secrets.token_urlsafe(24)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cutoff = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('DELETE FROM oauth_completions WHERE created_at < ?', (cutoff,))
            conn.execute(
                'INSERT INTO oauth_completions (code, session_token, created_at) VALUES (?, ?, ?)',
                (code, session_token, now)
            )
            conn.commit()
        return code

    def consume_oauth_completion(self, code: str) -> Optional[str]:
        if not code:
            return None
        cutoff = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                'SELECT session_token FROM oauth_completions WHERE code = ? AND created_at >= ?',
                (code, cutoff)
            ).fetchone()
            if not row:
                return None
            conn.execute('DELETE FROM oauth_completions WHERE code = ?', (code,))
            conn.commit()
            return row[0]

    # ===================== OAUTH =====================
    def find_or_create_oauth_user(self, oauth_provider: str, oauth_id: str, username: str, email: str = None, avatar_url: str = None) -> Tuple[int, str]:
        """OAuth ile giriş yapan kullanıcıyı bul veya oluştur. (user_id, username) döner."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            # Mevcut OAuth kullanıcısı var mı?
            user = conn.execute(
                'SELECT id, username FROM users WHERE oauth_provider = ? AND oauth_id = ?',
                (oauth_provider, oauth_id)
            ).fetchone()
            if user:
                return (user[0], user[1])

            # Yeni kullanıcı oluştur — username çakışmasını önle
            base_username = username
            suffix = 0
            while True:
                existing = conn.execute('SELECT id FROM users WHERE username = ?', (base_username,)).fetchone()
                if not existing:
                    break
                suffix += 1
                base_username = f"{username}_{suffix}"

            conn.execute(
                'INSERT INTO users (username, password_hash, email, avatar_url, oauth_provider, oauth_id) VALUES (?, ?, ?, ?, ?, ?)',
                (base_username, "", email, avatar_url, oauth_provider, oauth_id)
            )
            conn.commit()
            new_user = conn.execute('SELECT id, username FROM users WHERE oauth_provider = ? AND oauth_id = ?', (oauth_provider, oauth_id)).fetchone()
            return (new_user[0], new_user[1])

    # ===================== AI CONFIG =====================
    def save_ai_config(self, user_id: int, p_type: str, m_name: str, key: str, use_multi_agent: bool = True, force_claude_coder: bool = False) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('INSERT OR REPLACE INTO ai_configs (user_id, provider_type, model_name, api_key, use_multi_agent, force_claude_coder) VALUES (?, ?, ?, ?, ?, ?)',
                         (user_id, p_type, m_name, key, 1 if use_multi_agent else 0, 1 if force_claude_coder else 0))
            conn.commit()

    def get_ai_config(self, user_id: int) -> Tuple[str, str, str, bool, bool]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            res = conn.execute('SELECT provider_type, model_name, api_key, use_multi_agent, force_claude_coder FROM ai_configs WHERE user_id = ?', (user_id,)).fetchone()
            if res:
                return (res[0], res[1], res[2], bool(res[3]), bool(res[4]))
            return ("kb", "unity-kb-v1", "", False, False)

    # ===================== API KEY KASASI =====================
    def save_api_key(self, user_id: int, provider_type: str, api_key: str) -> None:
        """Provider için API key'i kaydet/güncelle."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        encrypted_key = self._encrypt_api_key(api_key)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                'INSERT OR REPLACE INTO api_keys (user_id, provider_type, api_key, updated_at) VALUES (?, ?, ?, ?)',
                (user_id, provider_type, encrypted_key, now)
            )
            conn.commit()

    def get_api_key(self, user_id: int, provider_type: str) -> Optional[str]:
        """Provider için kaydedilmiş API key'i getir."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                'SELECT api_key FROM api_keys WHERE user_id = ? AND provider_type = ?',
                (user_id, provider_type)
            ).fetchone()
            if not row:
                return None
            api_key = self._decrypt_api_key(row[0])
            if api_key and not row[0].startswith("enc:"):
                self.save_api_key(user_id, provider_type, api_key)
            return api_key or None

    def get_all_api_keys(self, user_id: int) -> Dict[str, str]:
        """Kullanıcının tüm provider key'lerini döndür. {provider_type: masked_key}"""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            rows = conn.execute(
                'SELECT provider_type, api_key FROM api_keys WHERE user_id = ?',
                (user_id,)
            ).fetchall()
            result = {}
            for provider_type, stored_key in rows:
                api_key = self._decrypt_api_key(stored_key)
                if api_key:
                    result[provider_type] = api_key
                    if not stored_key.startswith("enc:"):
                        self.save_api_key(user_id, provider_type, api_key)
            return result

    def delete_api_key(self, user_id: int, provider_type: str) -> None:
        """Provider için kaydedilmiş API key'i sil."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                'DELETE FROM api_keys WHERE user_id = ? AND provider_type = ?',
                (user_id, provider_type)
            )
            conn.commit()

    # ===================== ESKİ GEÇMİŞ (Geriye Uyumluluk) =====================
    def save_analysis(self, user_id: int, title: str, intent: str, code: str, suggestion: str, smells: list) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('INSERT INTO history (user_id, timestamp, title, intent, original_code, ai_suggestion, smells) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), title, intent, code, suggestion, json.dumps(smells)))

    def get_user_history(self, user_id: int) -> List[Tuple]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            return conn.execute('SELECT id, timestamp, title, intent FROM history WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()

    def get_analysis_detail(self, item_id: int) -> Optional[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            res = conn.execute('SELECT original_code, ai_suggestion, smells FROM history WHERE id = ?', (item_id,)).fetchone()
            return {"code": res[0], "suggestion": res[1], "smells": json.loads(res[2])} if res else None

    def get_analysis_owner(self, item_id: int) -> Optional[int]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute('SELECT user_id FROM history WHERE id = ?', (item_id,)).fetchone()
            return row[0] if row else None

    def delete_analysis(self, item_id: int) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('DELETE FROM history WHERE id = ?', (item_id,))
            conn.commit()

    def rename_analysis(self, item_id: int, new_title: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('UPDATE history SET title = ? WHERE id = ?', (new_title, item_id))
            conn.commit()

    # ===================== YENİ: SOHBETLER =====================
    def create_conversation(self, user_id: int, title: str = "Yeni Sohbet") -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.execute(
                'INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)',
                (user_id, title, now, now)
            )
            conn.commit()
            return cursor.lastrowid

    def get_user_conversations(self, user_id: int) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            rows = conn.execute(
                'SELECT id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC',
                (user_id,)
            ).fetchall()
            return [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

    def get_conversation_owner(self, conv_id: int) -> Optional[int]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute('SELECT user_id FROM conversations WHERE id = ?', (conv_id,)).fetchone()
            return row[0] if row else None

    def rename_conversation(self, conv_id: int, new_title: str) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?', (new_title, now, conv_id))
            conn.commit()

    def delete_conversation(self, conv_id: int) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.execute('DELETE FROM messages WHERE conversation_id = ?', (conv_id,))
            conn.execute('DELETE FROM conversations WHERE id = ?', (conv_id,))
            conn.commit()

    # ===================== YENİ: MESAJLAR =====================
    def add_message(self, conversation_id: int, role: str, content: str, smells: list = None) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        smells_json = json.dumps(smells) if smells else "[]"
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            cursor = conn.execute(
                'INSERT INTO messages (conversation_id, role, content, smells_json, timestamp) VALUES (?, ?, ?, ?, ?)',
                (conversation_id, role, content, smells_json, now)
            )
            # Sohbetin updated_at'ini güncelle
            conn.execute('UPDATE conversations SET updated_at = ? WHERE id = ?', (now, conversation_id))
            conn.commit()
            return cursor.lastrowid

    def get_conversation_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
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
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                'SELECT path FROM workspaces WHERE user_id = ? ORDER BY last_accessed DESC, id DESC LIMIT 1',
                (user_id,)
            ).fetchone()
            return row[0] if row else None
