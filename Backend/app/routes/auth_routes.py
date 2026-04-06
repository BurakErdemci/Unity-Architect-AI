import logging
import os
from collections import defaultdict, deque
from time import time
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from oauth_pages import oauth_error_page, oauth_success_page
from schemas import AuthRequest


logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
OAUTH_REDIRECT_BASE = "http://127.0.0.1:8000"
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 5
FAILED_LOGIN_ATTEMPTS = defaultdict(deque)


def create_auth_router(db):
    router = APIRouter()

    def _validate_auth_request(req: AuthRequest) -> tuple[str, str]:
        username = req.username.strip()
        password = req.password
        if len(username) < 3 or len(username) > 50:
            raise HTTPException(400, "İşlem tamamlanamadı.")
        if len(password) < 8 or len(password) > 128:
            raise HTTPException(400, "İşlem tamamlanamadı.")
        return username, password

    def _rate_limit_key(request: Request, username: str) -> str:
        client_ip = request.client.host if request.client else "unknown"
        return f"{client_ip}:{username.lower()}"

    def _prune_attempts(key: str):
        now = time()
        attempts = FAILED_LOGIN_ATTEMPTS[key]
        while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        return attempts

    def _register_failed_attempt(key: str):
        attempts = _prune_attempts(key)
        attempts.append(time())

    def _clear_failed_attempts(key: str):
        FAILED_LOGIN_ATTEMPTS.pop(key, None)

    @router.get("/")
    async def health():
        return {"status": "ok"}

    @router.post("/register")
    async def register(req: AuthRequest):
        username, password = _validate_auth_request(req)
        if db.create_user(username, password):
            return {"status": "success"}
        raise HTTPException(400, "Kayıt işlemi tamamlanamadı.")

    @router.post("/login")
    async def login(req: AuthRequest, request: Request):
        username, password = _validate_auth_request(req)
        rate_limit_key = _rate_limit_key(request, username)
        attempts = _prune_attempts(rate_limit_key)
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(429, "Çok fazla giriş denemesi. Lütfen daha sonra tekrar deneyin.")

        user = db.verify_user(username, password)
        if user:
            _clear_failed_attempts(rate_limit_key)
            session_token = db.create_session(user[0])
            return {"user_id": user[0], "username": user[1], "session_token": session_token}
        _register_failed_attempt(rate_limit_key)
        raise HTTPException(401, "Giriş yapılamadı.")

    @router.post("/logout")
    async def logout(x_session_token: str | None = Header(default=None)):
        if x_session_token:
            db.delete_session(x_session_token)
        return {"status": "success"}

    @router.get("/auth/google/url")
    async def google_auth_url():
        if not GOOGLE_CLIENT_ID:
            raise HTTPException(500, "Google ile giriş şu anda kullanılamıyor.")
        redirect_uri = f"{OAUTH_REDIRECT_BASE}/auth/google/callback"
        state = db.create_oauth_state("google")
        url = (
            "https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={GOOGLE_CLIENT_ID}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            "&response_type=code"
            "&scope=openid%20email%20profile"
            "&access_type=offline"
            "&prompt=consent"
            f"&state={quote(state, safe='')}"
        )
        return {"url": url}

    @router.get("/auth/github/url")
    async def github_auth_url():
        if not GITHUB_CLIENT_ID:
            raise HTTPException(500, "GitHub ile giriş şu anda kullanılamıyor.")
        redirect_uri = f"{OAUTH_REDIRECT_BASE}/auth/github/callback"
        state = db.create_oauth_state("github")
        url = (
            "https://github.com/login/oauth/authorize?"
            f"client_id={GITHUB_CLIENT_ID}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            "&scope=user:email"
            f"&state={quote(state, safe='')}"
        )
        return {"url": url}

    @router.get("/auth/google/callback", response_class=HTMLResponse)
    async def google_callback(code: str = "", state: str = ""):
        if not code:
            return oauth_error_page("Google ile giriş tamamlanamadı.")
        if not db.consume_oauth_state("google", state):
            return oauth_error_page("Google ile giriş doğrulanamadı.")
        try:
            redirect_uri = f"{OAUTH_REDIRECT_BASE}/auth/google/callback"
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return oauth_error_page("Google ile giriş tamamlanamadı.")

                user_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                user_info = user_resp.json()

            oauth_id = user_info.get("id", "")
            email = user_info.get("email", "")
            name = user_info.get("name", email.split("@")[0])
            avatar = user_info.get("picture", "")
            user_id, username = db.find_or_create_oauth_user("google", oauth_id, name, email, avatar)
            session_token = db.create_session(user_id)
            return oauth_success_page(user_id, username, email, avatar, session_token)
        except Exception as exc:
            logger.error(f"Google OAuth hatası: {exc}")
            return oauth_error_page("Google ile giriş tamamlanamadı.")

    @router.get("/auth/github/callback", response_class=HTMLResponse)
    async def github_callback(code: str = "", state: str = ""):
        if not code:
            return oauth_error_page("GitHub ile giriş tamamlanamadı.")
        if not db.consume_oauth_state("github", state):
            return oauth_error_page("GitHub ile giriş doğrulanamadı.")
        try:
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    data={
                        "code": code,
                        "client_id": GITHUB_CLIENT_ID,
                        "client_secret": GITHUB_CLIENT_SECRET,
                    },
                    headers={"Accept": "application/json"},
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    return oauth_error_page("GitHub ile giriş tamamlanamadı.")

                user_resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                user_info = user_resp.json()

                email = user_info.get("email", "")
                if not email:
                    emails_resp = await client.get(
                        "https://api.github.com/user/emails",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    emails = emails_resp.json()
                    if isinstance(emails, list):
                        primary = next((item for item in emails if item.get("primary")), None)
                        email = primary["email"] if primary else (emails[0]["email"] if emails else "")

            oauth_id = str(user_info.get("id", ""))
            name = user_info.get("login", "github_user")
            avatar = user_info.get("avatar_url", "")
            user_id, username = db.find_or_create_oauth_user("github", oauth_id, name, email, avatar)
            session_token = db.create_session(user_id)
            return oauth_success_page(user_id, username, email, avatar, session_token)
        except Exception as exc:
            logger.error(f"GitHub OAuth hatası: {exc}")
            return oauth_error_page("GitHub ile giriş tamamlanamadı.")

    return router
