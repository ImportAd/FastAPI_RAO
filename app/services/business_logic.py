"""
business_logic.py
-----------------
Бизнес-логика обработки ответов перед генерацией документа.
Перенесено из bot.py — вычисляемые поля, итоги, фиксированные значения.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from app.models.templates_models import DocumentTemplate
from app.services.word_renderer import _parse_money, money_to_words_ru


# Поля, которые всегда вычисляются автоматически
COMPUTED_FIELD_NAMES: set = {
    "total_sum_num",
    "total_kop",
    "total_sum_words",
    "totals_a",
    "totals_b",
}


def _field_key(section_id: str, field_name: str) -> str:
    return f"{section_id}.{field_name}"


def _get_auto_fields(answers: Dict[str, Any]) -> set:
    meta = answers.setdefault("_meta", {})
    auto_list = meta.get("auto_fields") or []
    if isinstance(auto_list, set):
        return auto_list
    if isinstance(auto_list, list):
        return set(str(x) for x in auto_list)
    return set()


def _set_auto_fields(answers: Dict[str, Any], auto: set) -> None:
    meta = answers.setdefault("_meta", {})
    meta["auto_fields"] = sorted(auto)
    answers["_meta"] = meta


def apply_template_fixed_fields(template: DocumentTemplate, answers: Dict[str, Any]) -> None:
    """Записать фиксированные поля из YAML в answers.fields."""
    fields = answers.setdefault("fields", {})
    for sec_id, sec_map in (template.fixed_fields or {}).items():
        sec = fields.setdefault(sec_id, {})
        for fname, value in (sec_map or {}).items():
            sec.setdefault(fname, value)
        fields[sec_id] = sec
    answers["fields"] = fields


def compute_totals_from_answers(answers: Dict[str, Any]) -> tuple:
    """Подсчитать сумму и копейки по колонке period_fee в таблице 'objects'."""
    tables = answers.get("tables") or {}
    rows = tables.get("objects") or []
    if not rows:
        return None, None

    total = Decimal("0.00")
    has_any = False

    for row in rows:
        val = _parse_money(row.get("period_fee"))
        if val is None:
            continue
        total += val
        has_any = True

    if not has_any:
        return None, None

    total = total.quantize(Decimal("0.01"))
    rub = int(total)
    kop = int((total - Decimal(rub)) * 100)
    return str(rub), f"{kop:02d}"


def apply_computed_totals(answers: Dict[str, Any]) -> None:
    """Авто-итоги по таблице объектов → answers.fields['totals']."""
    total_rub, total_kop = compute_totals_from_answers(answers)
    if total_rub is None and total_kop is None:
        return

    fields = answers.setdefault("fields", {})
    auto = _get_auto_fields(answers)

    def _set_auto(section_id: str, field_name: str, value: str) -> None:
        k = _field_key(section_id, field_name)
        existing = (fields.get(section_id, {}) or {}).get(field_name)
        if existing is None or str(existing).strip() == "" or k in auto:
            sec = fields.setdefault(section_id, {})
            sec[field_name] = value
            fields[section_id] = sec
            auto.add(k)

    if total_rub is not None:
        _set_auto("totals", "total_sum_num", str(total_rub))
    if total_kop is not None:
        try:
            kop_i = int(str(total_kop).strip())
            kop_s = f"{kop_i:02d}"
        except Exception:
            kop_i = 0
            kop_s = str(total_kop)
        _set_auto("totals", "total_kop", kop_s)
    else:
        kop_i = 0

    try:
        rub_i = int(str(total_rub).strip()) if total_rub is not None else 0
    except Exception:
        rub_i = 0

    words = money_to_words_ru(rub_i, kop_i, capitalize=True)
    _set_auto("totals", "total_sum_words", words)

    _set_auto_fields(answers, auto)
    answers["fields"] = fields


def apply_computed_sum_fields(answers: Dict[str, Any]) -> None:
    """Auto-fill sum_words/kop from sum in any section that has it."""
    fields = answers.setdefault("fields", {})
    auto = _get_auto_fields(answers)

    def _set_auto(section_id: str, field_name: str, value: str) -> None:
        k = _field_key(section_id, field_name)
        existing = (fields.get(section_id, {}) or {}).get(field_name)
        if existing is None or str(existing).strip() == "" or k in auto:
            sec = fields.setdefault(section_id, {})
            sec[field_name] = value
            fields[section_id] = sec
            auto.add(k)

    for section_id, sec_data in (fields or {}).items():
        if not isinstance(sec_data, dict):
            continue
        raw_sum = sec_data.get("sum")
        if raw_sum is None:
            continue
        raw_str = str(raw_sum).strip()
        if not raw_str:
            continue
        dec = _parse_money(raw_str)
        if dec is None:
            continue
        dec = dec.quantize(Decimal("0.01"))
        rub_i = int(dec)
        kop_i = int((dec - Decimal(rub_i)) * 100)
        kop_s = f"{kop_i:02d}"
        words = money_to_words_ru(rub_i, kop_i, capitalize=True)
        _set_auto(section_id, "kop", kop_s)
        _set_auto(section_id, "sum_words", words)

    _set_auto_fields(answers, auto)
    answers["fields"] = fields


def build_steps(template: DocumentTemplate) -> list:
    """Собрать список шагов заполнения для шаблона (используется фронтендом)."""
    steps = []
    skip = set(template.skip_fields or [])
    for section in template.sections:
        for field in section.fields:
            if field.name in skip:
                continue
            if field.name in COMPUTED_FIELD_NAMES:
                continue
            if template.get_fixed_value(section.id, field.name) is not None:
                continue
            steps.append({
                "kind": "field",
                "section_id": section.id,
                "field_name": field.name,
            })
        if section.table:
            steps.append({"kind": "table", "section_id": section.id})
    return steps
