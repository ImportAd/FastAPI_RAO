"""
routers/documents.py
--------------------
GET  /api/v1/documents          — список документов текущего пользователя
GET  /api/v1/documents/{id}     — детали документа (с answers для повторного заполнения)
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db.database import Database
from app.routers.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

db: Optional[Database] = None


class DocumentListItem(BaseModel):
    id: int
    template_code: str
    template_title: str
    status: str
    generation_time_ms: int
    filename: str
    display_filename: str = ""
    created_at: str


class DocumentDetail(BaseModel):
    id: int
    template_code: str
    template_title: str
    status: str
    generation_time_ms: int
    filename: str
    display_filename: str = ""
    created_at: str
    answers: dict  # Полный снимок полей для повторного заполнения


class DocumentsListResponse(BaseModel):
    documents: List[DocumentListItem]
    total: int


@router.get("", response_model=DocumentsListResponse)
async def list_my_documents(
    limit: int = 50,
    user: TokenPayload = Depends(get_current_user),
):
    """Список документов текущего пользователя (без auto-generated)."""
    if db is None:
        raise HTTPException(500, "DB not initialized")
    docs = db.get_user_documents(user.user_id, limit=limit, include_auto=False)
    items = [
        DocumentListItem(
            id=d.id,
            template_code=d.template_code,
            template_title=d.template_title,
            status=d.status,
            generation_time_ms=d.generation_time_ms,
            filename=d.filename,
            display_filename=d.display_filename,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return DocumentsListResponse(documents=items, total=len(items))


@router.get("/recent", response_model=DocumentsListResponse)
async def recent_documents(
    user: TokenPayload = Depends(get_current_user),
):
    """Последние 5 документов для главной страницы."""
    if db is None:
        raise HTTPException(500, "DB not initialized")
    docs = db.get_user_documents(user.user_id, limit=5, include_auto=False)
    items = [
        DocumentListItem(
            id=d.id,
            template_code=d.template_code,
            template_title=d.template_title,
            status=d.status,
            generation_time_ms=d.generation_time_ms,
            filename=d.filename,
            display_filename=d.display_filename,
            created_at=d.created_at,
        )
        for d in docs
    ]
    return DocumentsListResponse(documents=items, total=len(items))


@router.delete("")
async def delete_my_documents(
    user: TokenPayload = Depends(get_current_user),
):
    """Удалить все документы текущего пользователя."""
    if db is None:
        raise HTTPException(500, "DB not initialized")
    count = db.delete_user_documents(user.user_id)
    return {"ok": True, "deleted": count}


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """Детали документа с answers (для повторного заполнения)."""
    if db is None:
        raise HTTPException(500, "DB not initialized")
    doc = db.get_document(doc_id)
    if doc is None:
        raise HTTPException(404, "Документ не найден")
    # Проверяем, что документ принадлежит пользователю (или это админ)
    if doc.user_id != user.user_id and not user.is_admin:
        raise HTTPException(403, "Нет доступа к этому документу")
    return DocumentDetail(
        id=doc.id,
        template_code=doc.template_code,
        template_title=doc.template_title,
        status=doc.status,
        generation_time_ms=doc.generation_time_ms,
        filename=doc.filename,
        display_filename=doc.display_filename,
        created_at=doc.created_at,
        answers=doc.answers,
    )
