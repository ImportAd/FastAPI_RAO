"""
routers/generate.py — генерация DOCX с аутентификацией, трекингом времени, ФОРМАКС dual gen.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.db.database import Database
from app.models.templates_models import DocumentTemplate
from app.models.schemas import GenerateRequest
from app.services.word_renderer import render_document
from app.services.business_logic import (
    apply_template_fixed_fields, apply_computed_totals, apply_computed_sum_fields,
)
from app.routers.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1", tags=["generate"])

templates: Dict[str, DocumentTemplate] = {}
db: Optional[Database] = None
word_templates_dir: str = "word_templates"
generated_dir: str = "generated"

_gen_semaphore = asyncio.Semaphore(1)

FORMAKS_LD_TO_AKT = {
    "fm_ld_ip_do_2017": "fm_akt_ip_do_2017",
    "fm_ld_ip_do_2017_s": "fm_akt_ip_do_2017",
    "fm_ld_ip_s_2017": "fm_akt_ip_s_2017",
    "fm_ld_ip_s_2017_s": "fm_akt_ip_s_2017",
    "fm_ld_ooo": "fm_akt_OOO",
    "fm_ld_ooo_s": "fm_akt_OOO",
}


@router.post("/generate")
async def generate_document(req: GenerateRequest, user: TokenPayload = Depends(get_current_user)):
    template = templates.get(req.template_code)
    if not template:
        raise HTTPException(404, f"Template '{req.template_code}' not found")

    answers = copy.deepcopy(req.answers)
    apply_template_fixed_fields(template, answers)
    apply_computed_totals(answers)
    apply_computed_sum_fields(answers)

    async with _gen_semaphore:
        t0 = time.perf_counter()
        try:
            doc_path = await render_document(
                template=template, answers=answers,
                templates_dir=word_templates_dir, output_dir=generated_dir,
            )
            gen_time_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:
            gen_time_ms = int((time.perf_counter() - t0) * 1000)
            logging.exception("Generation failed")
            if db:
                db.save_document(user_id=user.user_id, template_code=template.code,
                    template_title=template.title, answers=answers, status="failed",
                    error_text=str(e)[:1000], generation_time_ms=gen_time_ms)
            raise HTTPException(500, f"Ошибка генерации: {e}")

    doc_record = None
    if db:
        doc_record = db.save_document(
            user_id=user.user_id, template_code=template.code,
            template_title=template.title, answers=answers, status="done",
            generation_time_ms=gen_time_ms, filename=doc_path.name)

    # ФОРМАКС: автоматическая генерация АКТа
    akt_filename = None
    akt_code = FORMAKS_LD_TO_AKT.get(req.template_code)
    if akt_code and akt_code in templates:
        try:
            akt_tmpl = templates[akt_code]
            akt_answers = copy.deepcopy(answers)
            apply_template_fixed_fields(akt_tmpl, akt_answers)
            async with _gen_semaphore:
                akt_path = await render_document(
                    template=akt_tmpl, answers=akt_answers,
                    templates_dir=word_templates_dir, output_dir=generated_dir)
            akt_filename = akt_path.name
            if db:
                db.save_document(user_id=user.user_id, template_code=akt_tmpl.code,
                    template_title=akt_tmpl.title, answers=akt_answers, status="done",
                    filename=akt_path.name, is_auto_generated=True)
        except Exception:
            logging.exception("Auto ACT generation failed (non-critical)")

    result = {
        "status": "ok", "filename": doc_path.name,
        "generation_time_ms": gen_time_ms,
        "document_id": doc_record.id if doc_record else None,
    }
    if akt_filename:
        result["akt_filename"] = akt_filename
    return result


@router.get("/download/{filename}")
async def download_file(filename: str, user: TokenPayload = Depends(get_current_user)):
    file_path = Path(generated_dir) / filename
    if not file_path.exists():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path=str(file_path), filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
