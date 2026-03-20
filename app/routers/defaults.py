"""
routers/defaults.py
-------------------
API для системных и пользовательских значений по умолчанию.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.schemas import DefaultValueRequest, DefaultsListResponse
from app.services.defaults_store import DefaultsStore

router = APIRouter(prefix="/api/v1/defaults", tags=["defaults"])

# Will be set from main.py
defaults_store: Optional[DefaultsStore] = None

# Temporary: use 0 as user_id until auth is implemented
_DEFAULT_USER_ID = 0


@router.get("/system/{key}", response_model=DefaultsListResponse)
async def get_system_defaults(key: str):
    """Получить системные значения по умолчанию для ключа (section_id.field_name)."""
    if defaults_store is None:
        raise HTTPException(500, "Defaults store not initialized")
    items = defaults_store.get_system(key)
    return DefaultsListResponse(items=items)


@router.get("/user/{key}", response_model=DefaultsListResponse)
async def get_user_defaults(key: str):
    """Получить пользовательские значения по умолчанию."""
    if defaults_store is None:
        raise HTTPException(500, "Defaults store not initialized")
    items = defaults_store.get_user(_DEFAULT_USER_ID, key)
    return DefaultsListResponse(items=items)


@router.post("/user/{key}", response_model=DefaultsListResponse)
async def add_user_default(key: str, body: DefaultValueRequest):
    """Добавить пользовательское значение по умолчанию."""
    if defaults_store is None:
        raise HTTPException(500, "Defaults store not initialized")

    defaults_store.add_user(_DEFAULT_USER_ID, key, body.value)
    try:
        defaults_store.save()
    except Exception:
        pass

    items = defaults_store.get_user(_DEFAULT_USER_ID, key)
    return DefaultsListResponse(items=items)


@router.delete("/user/{key}/{index}")
async def delete_user_default(key: str, index: int):
    """Удалить пользовательское значение по индексу."""
    if defaults_store is None:
        raise HTTPException(500, "Defaults store not initialized")

    ok = defaults_store.delete_user_at(_DEFAULT_USER_ID, key, index)
    if not ok:
        raise HTTPException(404, "Value not found at given index")

    try:
        defaults_store.save()
    except Exception:
        pass

    items = defaults_store.get_user(_DEFAULT_USER_ID, key)
    return DefaultsListResponse(items=items)
