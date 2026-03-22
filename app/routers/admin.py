"""
routers/admin.py — админ-эндпоинты: пользователи, логи, статистика, дефолты.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db.database import Database
from app.models.templates_models import DocumentTemplate
from app.routers.auth import require_admin, TokenPayload
from app.services.defaults_store import DefaultsStore

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

templates: Dict[str, DocumentTemplate] = {}
db: Optional[Database] = None
defaults_store: Optional[DefaultsStore] = None


# ──── Stats ────

class StatsResponse(BaseModel):
    total_templates: int
    total_generations: int
    successful: int
    failed: int
    avg_generation_time_ms: int

@router.get("/stats", response_model=StatsResponse)
async def get_stats(admin: TokenPayload = Depends(require_admin)):
    stats = db.get_generation_stats() if db else {}
    return StatsResponse(
        total_templates=len(templates),
        total_generations=stats.get("total_generations", 0),
        successful=stats.get("successful", 0),
        failed=stats.get("failed", 0),
        avg_generation_time_ms=stats.get("avg_generation_time_ms", 0),
    )


# ──── Logs ────

@router.get("/logs")
async def get_logs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    admin: TokenPayload = Depends(require_admin),
):
    if db is None:
        return {"documents": [], "total": 0}
    docs = db.get_all_documents(limit=limit, status=status)
    items = []
    for d in docs:
        item = d.to_dict()
        # Добавляем имя пользователя
        user = db.get_user_by_id(d.user_id)
        item["username"] = user.display_name if user else f"user#{d.user_id}"
        items.append(item)
    return {"documents": items, "total": len(items)}


@router.get("/logs/{doc_id}")
async def get_log_detail(doc_id: int, admin: TokenPayload = Depends(require_admin)):
    if db is None:
        raise HTTPException(404, "DB not available")
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    result = doc.to_dict_with_answers()
    user = db.get_user_by_id(doc.user_id)
    result["username"] = user.display_name if user else f"user#{doc.user_id}"
    return result


@router.get("/errors")
async def get_errors(limit: int = Query(20), admin: TokenPayload = Depends(require_admin)):
    if db is None:
        return {"documents": [], "total": 0}
    docs = db.get_all_documents(limit=limit, status="failed")
    items = []
    for d in docs:
        item = d.to_dict()
        user = db.get_user_by_id(d.user_id)
        item["username"] = user.display_name if user else f"user#{d.user_id}"
        items.append(item)
    return {"documents": items, "total": len(items)}


# ──── User Management ────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""

class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/users")
async def list_users(admin: TokenPayload = Depends(require_admin)):
    if db is None:
        return {"users": []}
    users = db.list_users()
    return {"users": [u.to_dict() for u in users]}

@router.post("/users")
async def create_user(req: CreateUserRequest, admin: TokenPayload = Depends(require_admin)):
    if db is None:
        raise HTTPException(500, "DB not available")
    existing = db.get_user_by_username(req.username)
    if existing:
        raise HTTPException(409, f"Пользователь '{req.username}' уже существует")
    user = db.create_user(req.username, req.password, req.display_name)
    return user.to_dict()

@router.put("/users/{user_id}")
async def update_user(user_id: int, req: UpdateUserRequest, admin: TokenPayload = Depends(require_admin)):
    if db is None:
        raise HTTPException(500, "DB not available")
    ok = db.update_user(user_id, username=req.username, display_name=req.display_name,
                        password=req.password, is_active=req.is_active)
    if not ok:
        raise HTTPException(400, "Нечего обновлять")
    user = db.get_user_by_id(user_id)
    return user.to_dict() if user else {"ok": True}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, admin: TokenPayload = Depends(require_admin)):
    if db is None:
        raise HTTPException(500, "DB not available")
    db.delete_user(user_id)
    return {"ok": True}


# ──── Default Values Management ────

@router.get("/defaults")
async def list_defaults(admin: TokenPayload = Depends(require_admin)):
    """Все системные значения по умолчанию."""
    if defaults_store is None:
        return {"defaults": {}}
    system = defaults_store.data.get("system", {})
    return {"defaults": system}

@router.put("/defaults/{key}")
async def update_default(key: str, body: dict, admin: TokenPayload = Depends(require_admin)):
    """Обновить значение по умолчанию. Body: {"values": ["val1", "val2"]}"""
    if defaults_store is None:
        raise HTTPException(500, "Defaults store not available")
    system = defaults_store.data.setdefault("system", {})
    system[key] = body.get("values", [])
    defaults_store.save()
    return {"key": key, "values": system[key]}
