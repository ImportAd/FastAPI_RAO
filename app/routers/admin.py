"""
routers/admin.py
----------------
Админские эндпоинты: логи генераций, статистика, ошибки.
"""
from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.templates_models import DocumentTemplate
from app.models.schemas import (
    GenerationLogEntry,
    GenerationLogsResponse,
    StatsResponse,
)
from app.services.generation_store import GenerationStore

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Will be set from main.py
templates: Dict[str, DocumentTemplate] = {}
generation_store: Optional[GenerationStore] = None


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Общая статистика."""
    total_gen = 0
    successful = 0
    failed = 0
    processing = 0

    if generation_store is not None:
        drafts = generation_store.data.get("drafts") or {}
        total_gen = len(drafts)
        for d in drafts.values():
            if not isinstance(d, dict):
                continue
            status = str(d.get("status", ""))
            if status == "done":
                successful += 1
            elif status == "failed":
                failed += 1
            elif status == "processing":
                processing += 1

    return StatsResponse(
        total_templates=len(templates),
        total_generations=total_gen,
        successful=successful,
        failed=failed,
        processing=processing,
    )


@router.get("/logs", response_model=GenerationLogsResponse)
async def get_logs(
    status: Optional[str] = Query(None, description="Filter by status: ready/processing/done/failed"),
    template_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Журнал генераций с фильтрацией."""
    if generation_store is None:
        return GenerationLogsResponse(drafts=[], total=0)

    raw_drafts = generation_store.data.get("drafts") or {}

    entries = []
    for draft_id, d in raw_drafts.items():
        if not isinstance(d, dict):
            continue
        if status and d.get("status") != status:
            continue
        if template_code and d.get("template_code") != template_code:
            continue

        entries.append(GenerationLogEntry(
            draft_id=str(draft_id),
            user_id=d.get("user_id"),
            template_code=str(d.get("template_code", "")),
            status=str(d.get("status", "")),
            attempts=int(d.get("attempts", 0)),
            last_error=str(d.get("last_error", "")),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        ))

    # Sort by updated_at descending
    entries.sort(key=lambda e: e.updated_at, reverse=True)
    total = len(entries)

    return GenerationLogsResponse(
        drafts=entries[offset: offset + limit],
        total=total,
    )


@router.get("/logs/{draft_id}")
async def get_log_detail(draft_id: str):
    """Детали конкретного черновика генерации."""
    if generation_store is None:
        raise HTTPException(404, "Generation store not available")

    draft = generation_store.get_draft(draft_id)
    if draft is None:
        raise HTTPException(404, f"Draft '{draft_id}' not found")

    return draft


@router.get("/errors", response_model=GenerationLogsResponse)
async def get_errors(limit: int = Query(20, ge=1, le=100)):
    """Последние ошибки генерации."""
    if generation_store is None:
        return GenerationLogsResponse(drafts=[], total=0)

    raw_drafts = generation_store.data.get("drafts") or {}

    entries = []
    for draft_id, d in raw_drafts.items():
        if not isinstance(d, dict):
            continue
        if d.get("status") != "failed":
            continue
        entries.append(GenerationLogEntry(
            draft_id=str(draft_id),
            user_id=d.get("user_id"),
            template_code=str(d.get("template_code", "")),
            status="failed",
            attempts=int(d.get("attempts", 0)),
            last_error=str(d.get("last_error", "")),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
        ))

    entries.sort(key=lambda e: e.updated_at, reverse=True)
    return GenerationLogsResponse(
        drafts=entries[:limit],
        total=len(entries),
    )
