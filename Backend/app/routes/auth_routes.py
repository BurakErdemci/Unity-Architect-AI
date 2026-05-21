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
