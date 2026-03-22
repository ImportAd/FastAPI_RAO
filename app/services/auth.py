"""
services/auth.py
----------------
JWT-аутентификация для основного сайта и админки.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Optional
from dataclasses import dataclass

# Простая JWT-реализация без внешних зависимостей
import base64


@dataclass
class TokenPayload:
    user_id: int
    username: str
    is_admin: bool = False
    exp: int = 0  # unix timestamp


class AuthService:
    def __init__(self, secret_key: str, token_ttl: int = 86400 * 7):
        """
        secret_key: секрет для подписи токенов
        token_ttl: время жизни токена в секундах (по умолчанию 7 дней)
        """
        self._secret = secret_key
        self._ttl = token_ttl

    def create_token(self, user_id: int, username: str, is_admin: bool = False) -> str:
        """Создать JWT-токен."""
        payload = {
            "user_id": user_id,
            "username": username,
            "is_admin": is_admin,
            "exp": int(time.time()) + self._ttl,
        }
        return self._encode_jwt(payload)

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """Проверить и декодировать JWT-токен."""
        try:
            payload = self._decode_jwt(token)
            if not payload:
                return None
            if payload.get("exp", 0) < time.time():
                return None
            return TokenPayload(
                user_id=payload["user_id"],
                username=payload["username"],
                is_admin=payload.get("is_admin", False),
                exp=payload.get("exp", 0),
            )
        except Exception:
            return None

    def _encode_jwt(self, payload: dict) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        h = self._b64(json.dumps(header))
        p = self._b64(json.dumps(payload))
        sig = self._sign(f"{h}.{p}")
        return f"{h}.{p}.{sig}"

    def _decode_jwt(self, token: str) -> Optional[dict]:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h, p, sig = parts
        if not hmac.compare_digest(self._sign(f"{h}.{p}"), sig):
            return None
        payload_bytes = base64.urlsafe_b64decode(p + "==")
        return json.loads(payload_bytes)

    def _sign(self, data: str) -> str:
        sig = hmac.new(self._secret.encode(), data.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    def _b64(self, data: str) -> str:
        return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()
