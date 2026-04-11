"""
/auth/complete/{code} endpoint rate limiting entegrasyon testleri.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

class TestOAuthCompletionRateLimitIntegration(unittest.TestCase):
    """
    FastAPI endpoint'ini mock DB ile test eder.
    """

    def setUp(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from routes.auth_routes import create_auth_router, OAUTH_COMPLETION_ATTEMPTS

        # Her test için sayacı sıfırla
        OAUTH_COMPLETION_ATTEMPTS.clear()

        mock_db = MagicMock()
        mock_db.consume_oauth_completion.return_value = "valid-session-token"
        mock_db.get_user_by_session.return_value = (1, "testuser")
        mock_db.get_user_profile.return_value = {
            "user_id": 1, "username": "testuser", "avatar": None
        }

        app = FastAPI()
        app.include_router(create_auth_router(mock_db))
        self.client = TestClient(app)
        self.mock_db = mock_db

    def test_gecerli_code_200_doner(self):
        res = self.client.post("/auth/complete/valid-code")
        self.assertEqual(res.status_code, 200)
        self.assertIn("session_token", res.json())

    def test_gecersiz_code_400_doner(self):
        self.mock_db.consume_oauth_completion.return_value = None
        res = self.client.post("/auth/complete/invalid-code")
        self.assertEqual(res.status_code, 400)

    def test_rate_limit_10_deneme_sonrasi_429(self):
        self.mock_db.consume_oauth_completion.return_value = None  # başarısız denemeler

        from routes.auth_routes import OAUTH_COMPLETION_ATTEMPTS
        OAUTH_COMPLETION_ATTEMPTS.clear()

        for i in range(10):
            res = self.client.post(f"/auth/complete/wrong-code-{i}")
            self.assertNotEqual(res.status_code, 429, f"{i+1}. deneme yanlışlıkla engellendi")

        res = self.client.post("/auth/complete/wrong-code-11")
        self.assertEqual(res.status_code, 429)

    def test_basarili_giris_sonrasi_sayac_sifirlaniyor(self):
        from routes.auth_routes import OAUTH_COMPLETION_ATTEMPTS
        OAUTH_COMPLETION_ATTEMPTS.clear()

        # 9 başarısız deneme
        self.mock_db.consume_oauth_completion.return_value = None
        for i in range(9):
            self.client.post(f"/auth/complete/bad-{i}")

        # Başarılı giriş sayacı sıfırlamalı
        self.mock_db.consume_oauth_completion.return_value = "valid-token"
        res = self.client.post("/auth/complete/good-code")
        self.assertEqual(res.status_code, 200)

        # Sayaç sıfırlandıysa tekrar 10 hakkımız var
        self.mock_db.consume_oauth_completion.return_value = None
        for i in range(10):
            res = self.client.post(f"/auth/complete/after-reset-{i}")
            self.assertNotEqual(res.status_code, 429, f"Reset sonrası {i+1}. deneme engellendi")


if __name__ == '__main__':
    unittest.main()
