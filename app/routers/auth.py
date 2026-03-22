"""
routers/auth.py
---------------
POST /api/v1/auth/login       — вход пользователя (основной сайт)
POST /api/v1/auth/admin-login — вход администратора (из .env)
GET  /api/v1/auth/me          — текущий пользователь
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from app.db.database import Database
from app.services.auth import AuthService, TokenPayload

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Will be set from main.py
db: Optional[Database] = None
auth_service: Optional[AuthService] = None
admin_username: str = "admin"
admin_password: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: int
    username: str
    display_name: str
    is_admin: bool = False


class MeResponse(BaseModel):
    user_id: int
    username: str
    display_name: str
    is_admin: bool = False


# ──────── Dependency: extract current user from token ────────

async def get_current_user(authorization: Optional[str] = Header(None)) -> TokenPayload:
    """Извлечь пользователя из JWT-токена в заголовке Authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Требуется авторизация")
    token = authorization[7:]
    payload = auth_service.verify_token(token)
    if payload is None:
        raise HTTPException(401, "Недействительный или просроченный токен")
    return payload


async def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[TokenPayload]:
    """Опциональная аутентификация — не выбрасывает ошибку."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return auth_service.verify_token(token)


async def require_admin(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    """Проверить, что пользователь — администратор."""
    if not user.is_admin:
        raise HTTPException(403, "Только для администраторов")
    return user


# ──────── Endpoints ────────

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Вход пользователя на основной сайт."""
    if db is None or auth_service is None:
        raise HTTPException(500, "Auth not initialized")

    user = db.get_user_by_username(req.username)
    if not user or not user.check_password(req.password):
        raise HTTPException(401, "Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(403, "Учётная запись деактивирована")

    token = auth_service.create_token(user.id, user.username, is_admin=False)
    return LoginResponse(
        token=token,
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
    )


@router.post("/admin-login", response_model=LoginResponse)
async def admin_login(req: LoginRequest):
    """Вход администратора (логин/пароль из .env)."""
    if auth_service is None:
        raise HTTPException(500, "Auth not initialized")

    if req.username != admin_username or req.password != admin_password:
        raise HTTPException(401, "Неверный логин или пароль администратора")

    token = auth_service.create_token(0, admin_username, is_admin=True)
    return LoginResponse(
        token=token,
        user_id=0,
        username=admin_username,
        display_name="Администратор",
        is_admin=True,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: TokenPayload = Depends(get_current_user)):
    """Получить данные текущего пользователя."""
    return MeResponse(
        user_id=user.user_id,
        username=user.username,
        display_name=user.username,
        is_admin=user.is_admin,
    )
