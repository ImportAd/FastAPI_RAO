"""
routers/reports.py
------------------
POST /api/v1/reports       — сохранить сообщение о проблеме
GET  /api/v1/reports       — список всех сообщений (для админки)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

# Path to reports JSON (will be set from main.py)
_reports_path: Optional[Path] = None


class ReportRequest(BaseModel):
    message: str
    page: Optional[str] = None  # На какой странице была проблема
    template_code: Optional[str] = None


class ReportEntry(BaseModel):
    id: str
    message: str
    page: Optional[str] = None
    template_code: Optional[str] = None
    created_at: str
    resolved: bool = False


class ReportsResponse(BaseModel):
    reports: List[ReportEntry]
    total: int


def _load_reports() -> list:
    if _reports_path is None or not _reports_path.exists():
        return []
    try:
        data = json.loads(_reports_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_reports(reports: list) -> None:
    if _reports_path is None:
        return
    _reports_path.parent.mkdir(parents=True, exist_ok=True)
    _reports_path.write_text(
        json.dumps(reports, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.post("", response_model=ReportEntry)
async def create_report(req: ReportRequest):
    """Сохранить сообщение о проблеме."""
    reports = _load_reports()
    entry = {
        "id": uuid4().hex[:12],
        "message": req.message.strip(),
        "page": req.page,
        "template_code": req.template_code,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "resolved": False,
    }
    reports.append(entry)
    _save_reports(reports)
    return ReportEntry(**entry)


@router.get("", response_model=ReportsResponse)
async def list_reports(
    resolved: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Список всех сообщений о проблемах."""
    reports = _load_reports()
    if resolved is not None:
        reports = [r for r in reports if r.get("resolved") == resolved]
    reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    total = len(reports)
    entries = [ReportEntry(**r) for r in reports[:limit]]
    return ReportsResponse(reports=entries, total=total)


@router.post("/{report_id}/resolve")
async def resolve_report(report_id: str):
    """Отметить проблему как решённую."""
    reports = _load_reports()
    for r in reports:
        if r.get("id") == report_id:
            r["resolved"] = True
            _save_reports(reports)
            return {"ok": True}
    return {"ok": False, "detail": "Not found"}
