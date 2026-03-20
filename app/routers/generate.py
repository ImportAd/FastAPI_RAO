"""
routers/generate.py
-------------------
POST /api/v1/generate — генерация DOCX документа
"""
from __future__ import annotations

import copy
import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models.templates_models import DocumentTemplate
from app.models.schemas import GenerateRequest
from app.services.word_renderer import render_document
from app.services.business_logic import (
    apply_template_fixed_fields,
    apply_computed_totals,
    apply_computed_sum_fields,
)
from app.services.generation_store import GenerationStore

router = APIRouter(prefix="/api/v1", tags=["generate"])

# Will be set from main.py
templates: Dict[str, DocumentTemplate] = {}
generation_store: Optional[GenerationStore] = None
word_templates_dir: str = "word_templates"
generated_dir: str = "generated"


@router.post("/generate")
async def generate_document(req: GenerateRequest):
    """
    Генерация DOCX документа.
    
    Принимает code шаблона и заполненные ответы,
    применяет вычисляемые поля, генерирует документ через COM Word,
    возвращает файл для скачивания.
    """
    template = templates.get(req.template_code)
    if not template:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{req.template_code}' not found",
        )

    answers = copy.deepcopy(req.answers)

    # Применяем бизнес-логику (как в боте)
    apply_template_fixed_fields(template, answers)
    apply_computed_totals(answers)
    apply_computed_sum_fields(answers)

    # Сохраняем черновик для логирования
    draft_id = None
    if generation_store is not None:
        try:
            draft_id = generation_store.upsert_draft(
                user_id=0,  # в веб-версии пока без авторизации
                template_code=template.code,
                answers=answers,
            )
            generation_store.mark_attempt_started(draft_id)
        except Exception:
            logging.exception("Failed to save generation draft")

    # Генерация документа через COM Word
    try:
        doc_path = await render_document(
            template=template,
            answers=answers,
            templates_dir=word_templates_dir,
            output_dir=generated_dir,
        )
    except Exception as e:
        logging.exception("Document generation failed")

        if draft_id and generation_store:
            try:
                generation_store.mark_failed(draft_id, str(e))
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при формировании документа: {str(e)}",
        )

    # Отмечаем успех
    if draft_id and generation_store:
        try:
            generation_store.mark_done(draft_id)
        except Exception:
            pass

    return FileResponse(
        path=str(doc_path),
        filename=doc_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
