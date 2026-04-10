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

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from starlette.responses import FileResponse
from app.services.filename_utils import content_disposition, sanitize_custom_filename

from app.db.database import Database
from app.models.templates_models import DocumentTemplate
from app.models.schemas import GenerateRequest
from app.services.word_renderer import render_document
from app.services.business_logic import (
    apply_template_fixed_fields, apply_computed_totals, apply_computed_sum_fields,
)
from app.services.filename_utils import sanitize_custom_filename, add_suffix
from app.routers.auth import get_current_user, TokenPayload

router = APIRouter(prefix="/api/v1", tags=["generate"])

templates: Dict[str, DocumentTemplate] = {}
db: Optional[Database] = None
word_templates_dir: str = "word_templates"
generated_dir: str = "generated"

_gen_semaphore = asyncio.Semaphore(1)

FORMAKS_LD_TO_AKT = {
    # ООО
    "fm_ld_ooo":              "fm_akt_OOO",       # Постоянный
    "fm_ld_OOO_post":         "fm_akt_OOO",       # Пост+сезон
    "fm_ld_OOO_s":            "fm_akt_OOO",       # Сезонный
    # ИП до 2017
    "fm_ld_ip_do_2017":       "fm_akt_ip_do_2017", # Постоянный
    "fm_ld_IP_do_2017_post":  "fm_akt_ip_do_2017", # Пост+сезон
    "fm_ld_ip_do_2017_s":     "fm_akt_ip_do_2017", # Сезонный
    # ИП с 2017
    "ds_ld_ip_s_2017":        "fm_akt_ip_s_2017",  # Постоянный
    "fm_ld_IP_s_2017_post":   "fm_akt_ip_s_2017",  # Пост+сезон
    "fm_ld_ip_s_2017":        "fm_akt_ip_s_2017",  # Сезонный
}

FORMAKS_LD_TO_EDO = {
    # ООО
    "fm_ld_ooo":              "fm_edo_ooo",
    "fm_ld_OOO_post":         "fm_edo_ooo",
    "fm_ld_OOO_s":            "fm_edo_ooo",
    # ИП до 2017
    "fm_ld_ip_do_2017":       "fm_edo_ip_do_2017",
    "fm_ld_IP_do_2017_post":  "fm_edo_ip_do_2017",
    "fm_ld_ip_do_2017_s":     "fm_edo_ip_do_2017",
    # ИП с 2017
    "ds_ld_ip_s_2017":        "fm_edo_ip_s_2017",
    "fm_ld_IP_s_2017_post":   "fm_edo_ip_s_2017",
    "fm_ld_ip_s_2017":        "fm_edo_ip_s_2017",
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
    # Достать пользовательское имя ДО удаления _meta
    meta = answers.get("_meta") or {}
    raw_custom = meta.get("custom_filename")
    custom_filename = sanitize_custom_filename(raw_custom)

    # _meta — служебный ключ, не должен попадать в рендер-контекст
    answers.pop("_meta", None)

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
            generation_time_ms=gen_time_ms, filename=doc_path.name, 
            display_filename=custom_filename,)

    # ФОРМАКС: автоматическая генерация АКТа
    akt_filename = None
    akt_display = ""
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
            akt_display = add_suffix(custom_filename, "_АКТ") if custom_filename else ""
            if db:
                db.save_document(user_id=user.user_id, template_code=akt_tmpl.code,
                    template_title=akt_tmpl.title, answers=akt_answers, status="done",
                    filename=akt_path.name, is_auto_generated=True,
                    display_filename=akt_display)
        except Exception:
            logging.exception("Auto ACT generation failed (non-critical)")
        
    # ФОРМАКС: автоматическая генерация ЭДО
    edo_filename = None
    edo_display = ""
    edo_code = FORMAKS_LD_TO_EDO.get(req.template_code)
    if edo_code and edo_code in templates:
        try:
            edo_tmpl = templates[edo_code]
            edo_answers = copy.deepcopy(answers)
            apply_template_fixed_fields(edo_tmpl, edo_answers)
            async with _gen_semaphore:
                edo_path = await render_document(
                    template=edo_tmpl, answers=edo_answers,
                    templates_dir=word_templates_dir, output_dir=generated_dir)
            edo_filename = edo_path.name
            edo_display = add_suffix(custom_filename, "_EDO") if custom_filename else ""
            if db:
                db.save_document(user_id=user.user_id, template_code=edo_tmpl.code,
                    template_title=edo_tmpl.title, answers=edo_answers, status="done",
                    filename=edo_path.name, is_auto_generated=True,
                    display_filename=edo_display)
        except Exception:
            logging.exception("Auto EDO generation failed (non-critical)")

    result = {
        "status": "ok", "filename": doc_path.name,
        "generation_time_ms": gen_time_ms,
        "document_id": doc_record.id if doc_record else None,
    }
    if akt_filename:
        result["akt_filename"] = akt_filename
        if akt_display:
            result["akt_display_filename"] = akt_display
    if edo_filename:
        result["edo_filename"] = edo_filename
        if edo_display:
            result["edo_display_filename"] = edo_display
    return result


@router.get("/download/{filename}")
async def download_file(filename: str, 
                        display: str | None = Query(None),
                        user: TokenPayload = Depends(get_current_user),
                        ):
    file_path = Path(generated_dir) / filename
    if not file_path.exists():
        raise HTTPException(404, "Файл не найден")
    # Если фронт явно передал display — санитизируем; иначе ищем в БД
    display_name = ""
    if display:
        display_name = sanitize_custom_filename(display)
    if not display_name and db:
        # Найти запись по filename
        from sqlite3 import Row  # noqa
        conn = db._conn()
        try:
            row = conn.execute(
                "SELECT display_filename FROM documents WHERE filename = ? LIMIT 1",
                (filename,),
            ).fetchone()
            if row and row["display_filename"]:
                display_name = row["display_filename"]
        finally:
            conn.close()

    if not display_name:
        display_name = filename

    response = FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response.headers["Content-Disposition"] = content_disposition(display_name)
    return response
