import importlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from urllib.parse import parse_qs, urlparse
from pathlib import Path

from fastapi.testclient import TestClient


APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestPhase3SecurityStress(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="phase3_security_")
        self.db_path = os.path.join(self.temp_dir, "phase3_security.db")
        os.environ["DB_PATH"] = self.db_path
        os.environ["GOOGLE_CLIENT_ID"] = "test-google-client"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-google-secret"
        os.environ["GITHUB_CLIENT_ID"] = "test-github-client"
        os.environ["GITHUB_CLIENT_SECRET"] = "test-github-secret"

        for module_name in ("main", "database", "routes", "routes.auth_routes"):
            sys.modules.pop(module_name, None)

        database_module = importlib.import_module("database")

        class FakePwdContext:
            @staticmethod
            def hash(secret: str) -> str:
                return f"fake-hash::{secret}"

            @staticmethod
            def verify(secret: str, hashed: str) -> bool:
                return hashed == f"fake-hash::{secret}"

        database_module.pwd_context = FakePwdContext()
        self.app_main = importlib.import_module("main")
        self.client = TestClient(self.app_main.app)

    def tearDown(self):
        self.client.close()
        for module_name in ("main", "database", "routes", "routes.auth_routes"):
            sys.modules.pop(module_name, None)
        os.environ.pop("DB_PATH", None)
        os.environ.pop("GOOGLE_CLIENT_ID", None)
        os.environ.pop("GOOGLE_CLIENT_SECRET", None)
        os.environ.pop("GITHUB_CLIENT_ID", None)
        os.environ.pop("GITHUB_CLIENT_SECRET", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _register_and_login(self, username: str, password: str = "12345678") -> dict:
        register_res = self.client.post("/register", json={"username": username, "password": password})
        self.assertEqual(register_res.status_code, 200, register_res.text)

        login_res = self.client.post("/login", json={"username": username, "password": password})
        self.assertEqual(login_res.status_code, 200, login_res.text)
        payload = login_res.json()
        self.assertTrue(payload["session_token"])
        return payload

    @staticmethod
    def _auth_headers(session_token: str) -> dict:
        return {"X-Session-Token": session_token}

    def _create_conversation(self, user_id: int, session_token: str, title: str = "Yeni Sohbet") -> int:
        res = self.client.post(
            "/conversations",
            json={"user_id": user_id, "title": title},
            headers=self._auth_headers(session_token),
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["id"]

    def test_session_is_required_and_logout_invalidates_token(self):
        user = self._register_and_login("session_user")
        headers = self._auth_headers(user["session_token"])

        me_res = self.client.get("/me", headers=headers)
        self.assertEqual(me_res.status_code, 200, me_res.text)
        self.assertEqual(me_res.json()["user_id"], user["user_id"])

        protected_res = self.client.get(f"/conversations/{user['user_id']}", headers=headers)
        self.assertEqual(protected_res.status_code, 200, protected_res.text)

        missing_header_res = self.client.get(f"/conversations/{user['user_id']}")
        self.assertEqual(missing_header_res.status_code, 422)

        logout_res = self.client.post("/logout", headers=headers)
        self.assertEqual(logout_res.status_code, 200, logout_res.text)

        me_after_logout = self.client.get("/me", headers=headers)
        self.assertEqual(me_after_logout.status_code, 401, me_after_logout.text)

        after_logout_res = self.client.get(f"/conversations/{user['user_id']}", headers=headers)
        self.assertEqual(after_logout_res.status_code, 401, after_logout_res.text)

    def test_expired_session_is_rejected(self):
        user = self._register_and_login("expired_session_user")
        headers = self._auth_headers(user["session_token"])

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token = ?",
                ("2000-01-01 00:00:00", user["session_token"]),
            )

        expired_res = self.client.get(f"/conversations/{user['user_id']}", headers=headers)
        self.assertEqual(expired_res.status_code, 401, expired_res.text)

        expired_me = self.client.get("/me", headers=headers)
        self.assertEqual(expired_me.status_code, 401, expired_me.text)

    def test_register_rejects_weak_password_and_login_rate_limit_applies(self):
        weak_register_res = self.client.post("/register", json={"username": "weak_user", "password": "123"})
        self.assertEqual(weak_register_res.status_code, 400, weak_register_res.text)
        self.assertEqual(weak_register_res.json()["detail"], "İşlem tamamlanamadı.")

        self.client.post("/register", json={"username": "rate_limit_user", "password": "12345678"})

        for _ in range(5):
            failed_login = self.client.post("/login", json={"username": "rate_limit_user", "password": "wrong-pass"})
            self.assertEqual(failed_login.status_code, 401, failed_login.text)
            self.assertEqual(failed_login.json()["detail"], "Giriş yapılamadı.")

        throttled_login = self.client.post("/login", json={"username": "rate_limit_user", "password": "wrong-pass"})
        self.assertEqual(throttled_login.status_code, 429, throttled_login.text)
        self.assertEqual(throttled_login.json()["detail"], "Çok fazla giriş denemesi. Lütfen daha sonra tekrar deneyin.")

    def test_api_key_and_config_security_rules(self):
        user_a = self._register_and_login("config_alice")
        user_b = self._register_and_login("config_bob")
        headers_a = self._auth_headers(user_a["session_token"])
        headers_b = self._auth_headers(user_b["session_token"])

        config_save_res = self.client.post(
            "/save-ai-config",
            json={
                "user_id": user_a["user_id"],
                "provider_type": "openai",
                "model_name": "gpt-5.4-mini",
                "api_key": "sk-secret-1234567890",
                "use_multi_agent": False,
            },
            headers=headers_a,
        )
        self.assertEqual(config_save_res.status_code, 200, config_save_res.text)

        config_get_res = self.client.get(f"/get-ai-config/{user_a['user_id']}", headers=headers_a)
        self.assertEqual(config_get_res.status_code, 200, config_get_res.text)
        config_payload = config_get_res.json()
        self.assertEqual(config_payload["provider_type"], "openai")
        self.assertTrue(config_payload["has_key"])
        self.assertNotIn("api_key", config_payload)

        masked_keys_res = self.client.get(f"/api-keys/{user_a['user_id']}", headers=headers_a)
        self.assertEqual(masked_keys_res.status_code, 200, masked_keys_res.text)
        masked_payload = masked_keys_res.json()
        self.assertIn("openai", masked_payload["providers_with_keys"])
        self.assertNotIn("1234567890", masked_payload["keys"]["openai"])
        self.assertNotIn("sk-secret-1234567890", masked_payload["keys"]["openai"])

        forbidden_read = self.client.get(f"/get-ai-config/{user_a['user_id']}", headers=headers_b)
        self.assertEqual(forbidden_read.status_code, 403, forbidden_read.text)

        forbidden_keys = self.client.get(f"/api-keys/{user_a['user_id']}", headers=headers_b)
        self.assertEqual(forbidden_keys.status_code, 403, forbidden_keys.text)

        delete_res = self.client.delete(f"/api-keys/{user_a['user_id']}/openai", headers=headers_a)
        self.assertEqual(delete_res.status_code, 200, delete_res.text)

        config_after_delete = self.client.get(f"/get-ai-config/{user_a['user_id']}", headers=headers_a)
        self.assertEqual(config_after_delete.status_code, 200, config_after_delete.text)
        self.assertFalse(config_after_delete.json()["has_key"])

    def test_api_keys_are_encrypted_at_rest(self):
        user = self._register_and_login("encrypted_key_user")
        headers = self._auth_headers(user["session_token"])
        raw_key = "sk-secret-plain-db-check-123456"

        save_res = self.client.post(
            "/save-ai-config",
            json={
                "user_id": user["user_id"],
                "provider_type": "openai",
                "model_name": "gpt-5.4-mini",
                "api_key": raw_key,
                "use_multi_agent": False,
            },
            headers=headers,
        )
        self.assertEqual(save_res.status_code, 200, save_res.text)

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                "SELECT api_key FROM api_keys WHERE user_id = ? AND provider_type = ?",
                (user["user_id"], "openai"),
            ).fetchone()

        self.assertIsNotNone(row)
        stored_value = row[0]
        self.assertTrue(stored_value.startswith("enc:"))
        self.assertNotIn(raw_key, stored_value)

        get_res = self.client.get(f"/get-ai-config/{user['user_id']}", headers=headers)
        self.assertEqual(get_res.status_code, 200, get_res.text)
        self.assertTrue(get_res.json()["has_key"])

        keys_res = self.client.get(f"/api-keys/{user['user_id']}", headers=headers)
        self.assertEqual(keys_res.status_code, 200, keys_res.text)
        self.assertIn("openai", keys_res.json()["providers_with_keys"])

    def test_workspace_and_write_file_security_rules(self):
        user = self._register_and_login("workspace_user")
        headers = self._auth_headers(user["session_token"])

        workspace = Path(self.temp_dir) / "UnityProject"
        scripts_dir = workspace / "Assets" / "Scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        save_workspace_res = self.client.post(
            "/save-workspace",
            json={"user_id": user["user_id"], "path": str(workspace)},
            headers=headers,
        )
        self.assertEqual(save_workspace_res.status_code, 200, save_workspace_res.text)

        last_workspace_res = self.client.get(f"/last-workspace/{user['user_id']}", headers=headers)
        self.assertEqual(last_workspace_res.status_code, 200, last_workspace_res.text)
        self.assertEqual(last_workspace_res.json()["path"], str(workspace))

        allowed_file = scripts_dir / "PlayerController.cs"
        allowed_write_res = self.client.post(
            "/write-file",
            json={
                "file_path": str(allowed_file),
                "workspace_path": str(workspace),
                "content": "public class PlayerController {}",
            },
            headers=headers,
        )
        self.assertEqual(allowed_write_res.status_code, 200, allowed_write_res.text)
        self.assertTrue(allowed_file.exists())

        rejected_paths = [
            workspace / "Assets" / "Editor" / "Hack.cs",
            workspace / "Assets" / "ScriptsBackup" / "Hack.cs",
            workspace.parent / "OtherProject" / "Assets" / "Scripts" / "Hack.cs",
            workspace / "Assets" / "Scripts" / "Hack.txt",
        ]

        for rejected_path in rejected_paths:
            reject_res = self.client.post(
                "/write-file",
                json={
                    "file_path": str(rejected_path),
                    "workspace_path": str(workspace),
                    "content": "public class Hack {}",
                },
                headers=headers,
            )
            self.assertEqual(
                reject_res.status_code,
                403,
                f"{rejected_path} -> {reject_res.status_code} {reject_res.text}",
            )

        disabled_update_res = self.client.post(
            "/update-file",
            json={"file_path": str(allowed_file), "new_code": "public class Changed {}"},
            headers=headers,
        )
        self.assertEqual(disabled_update_res.status_code, 410, disabled_update_res.text)

    def test_oauth_urls_include_state_and_callback_rejects_invalid_state(self):
        providers_res = self.client.get("/auth/providers")
        self.assertEqual(providers_res.status_code, 200, providers_res.text)
        self.assertTrue(providers_res.json()["google"])
        self.assertTrue(providers_res.json()["github"])

        google_url_res = self.client.get("/auth/google/url")
        self.assertEqual(google_url_res.status_code, 200, google_url_res.text)

        google_url = google_url_res.json()["url"]
        query = parse_qs(urlparse(google_url).query)
        self.assertTrue(query.get("state"))
        invalid_google = self.client.get("/auth/google/callback?code=test-code&state=invalid-state")
        self.assertEqual(invalid_google.status_code, 200)
        self.assertIn("Google ile giriş doğrulanamadı", invalid_google.text)

        github_url_res = self.client.get("/auth/github/url")
        self.assertEqual(github_url_res.status_code, 200, github_url_res.text)

        github_url = github_url_res.json()["url"]
        query = parse_qs(urlparse(github_url).query)
        self.assertTrue(query.get("state"))
        invalid_github = self.client.get("/auth/github/callback?code=test-code&state=invalid-state")
        self.assertEqual(invalid_github.status_code, 200)
        self.assertIn("GitHub ile giriş doğrulanamadı", invalid_github.text)

        invalid_completion = self.client.post("/auth/complete/invalid-code")
        self.assertEqual(invalid_completion.status_code, 400, invalid_completion.text)

    def test_conversation_history_and_chat_ownership_rules(self):
        user_a = self._register_and_login("alice")
        user_b = self._register_and_login("bob")
        headers_a = self._auth_headers(user_a["session_token"])
        headers_b = self._auth_headers(user_b["session_token"])

        conv_ids = []
        for idx in range(12):
            conv_ids.append(self._create_conversation(user_a["user_id"], user_a["session_token"], f"Conv {idx}"))

        own_list_res = self.client.get(f"/conversations/{user_a['user_id']}", headers=headers_a)
        self.assertEqual(own_list_res.status_code, 200, own_list_res.text)
        self.assertEqual(len(own_list_res.json()), 12)

        forbidden_cases = [
            ("GET", f"/conversations/{user_a['user_id']}", None),
            ("GET", f"/conversations/{conv_ids[0]}/messages", None),
            ("DELETE", f"/conversations/{conv_ids[0]}", None),
            ("PUT", f"/conversations/{conv_ids[0]}", {"title": "Hacked"}),
            ("GET", f"/last-workspace/{user_a['user_id']}", None),
        ]

        for method, url, payload in forbidden_cases:
            response = self.client.request(method, url, json=payload, headers=headers_b)
            self.assertEqual(
                response.status_code,
                403,
                f"{method} {url} -> {response.status_code} {response.text}",
            )

        own_progress = self.client.get(f"/chat-progress/{conv_ids[0]}", headers=headers_a)
        self.assertEqual(own_progress.status_code, 200, own_progress.text)

        forbidden_progress = self.client.get(f"/chat-progress/{conv_ids[0]}", headers=headers_b)
        self.assertEqual(forbidden_progress.status_code, 403, forbidden_progress.text)

        invalid_token_headers = self._auth_headers("invalid-token")
        for _ in range(25):
            invalid_res = self.client.get(f"/conversations/{user_a['user_id']}", headers=invalid_token_headers)
            self.assertEqual(invalid_res.status_code, 401)

        chat_res = self.client.post(
            "/chat",
            json={
                "conversation_id": conv_ids[0],
                "message": "selam",
                "language": "tr",
                "user_id": user_a["user_id"],
                "mode": "analysis",
                "use_kb": True,
            },
            headers=headers_a,
        )
        self.assertEqual(chat_res.status_code, 200, chat_res.text)
        self.assertEqual(chat_res.json()["intent"], "GREETING")

        own_messages = self.client.get(f"/conversations/{conv_ids[0]}/messages", headers=headers_a)
        self.assertEqual(own_messages.status_code, 200, own_messages.text)
        self.assertGreaterEqual(len(own_messages.json()), 2)

        self.app_main.db.save_analysis(
            user_a["user_id"],
            "Test Analysis",
            "ANALYSIS",
            "public class A {}",
            "fixed",
            [],
        )
        history_res = self.client.get(f"/history/{user_a['user_id']}", headers=headers_a)
        self.assertEqual(history_res.status_code, 200, history_res.text)
        self.assertGreaterEqual(len(history_res.json()), 1)
        item_id = history_res.json()[0]["id"]

        own_detail = self.client.get(f"/analysis-detail/{item_id}", headers=headers_a)
        self.assertEqual(own_detail.status_code, 200, own_detail.text)
        self.assertIn("code", own_detail.json())

        forbidden_history = self.client.get(f"/history/{user_a['user_id']}", headers=headers_b)
        self.assertEqual(forbidden_history.status_code, 403, forbidden_history.text)

        forbidden_detail = self.client.get(f"/analysis-detail/{item_id}", headers=headers_b)
        self.assertEqual(forbidden_detail.status_code, 403, forbidden_detail.text)

        forbidden_analyze = self.client.post(
            "/analyze",
            json={"code": "public class Test {}", "language": "tr", "user_id": user_a["user_id"]},
            headers=headers_b,
        )
        self.assertEqual(forbidden_analyze.status_code, 403, forbidden_analyze.text)

        forbidden_chat = self.client.post(
            "/chat",
            json={
                "conversation_id": conv_ids[0],
                "message": "selam",
                "language": "tr",
                "user_id": user_a["user_id"],
                "mode": "analysis",
                "use_kb": True,
            },
            headers=headers_b,
        )
        self.assertEqual(forbidden_chat.status_code, 403, forbidden_chat.text)

        delete_history = self.client.delete(f"/history/{item_id}", headers=headers_a)
        self.assertEqual(delete_history.status_code, 200, delete_history.text)


if __name__ == "__main__":
    unittest.main()
