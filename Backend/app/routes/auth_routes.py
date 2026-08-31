from fastapi import APIRouter, Header
from auth_utils import _check_token

def create_auth_router(db):
    router = APIRouter()

    @router.get("/me")
    async def get_me(x_session_token: str = Header(alias="X-Session-Token", default="")):
        _check_token(x_session_token)
        # user_id, username, name, avatar — eski frontend uyumluluğu
        return {"user_id": 1, "id": 1, "username": "local", "name": "local",
                "email": "local@localhost", "avatar": ""}

    @router.get("/health/auth")
    async def health_auth(x_session_token: str = Header(alias="X-Session-Token", default="")):
        """Liveness, but only for a caller holding the app token.

        `/health` is deliberately unauthenticated (see the authz matrix's
        whitelist), which makes it useless for the one question Docker mode has
        to ask at startup: is the backend I just reached holding the SAME secret
        I am? Measured 31 Aug 2026 — a container kept alive by `restart:
        unless-stopped` outlives the shell that exported its token, answers
        `/health` happily, and then 401s every real call. Every visible startup
        signal read as fine.

        It lives here rather than beside `/health` in `main.py` on purpose: the
        authz matrix installs its sentinel into `routes.*` modules, so a
        protected endpoint declared outside them is invisible to the one test
        that proves the gate is actually called.
        """
        _check_token(x_session_token)
        return {"status": "ok", "service": "gamachine", "auth": "ok"}

    @router.post("/login")
    async def login():
        # Geriye dönük uyumluluk stub (token gerektirmez)
        return {"session_token": "local",
                "user": {"user_id": 1, "username": "local", "email": "local@localhost"}}

    @router.post("/logout")
    async def logout():
        return {"ok": True}

    @router.get("/auth/providers")
    async def get_providers():
        # Eski frontend bu shape'i bekliyordu
        return {"google": False, "github": False}

    return router
