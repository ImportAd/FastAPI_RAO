from __future__ import annotations

"""templates_loader.py
-------------------
Загрузка YAML-схем шаблонов в объекты `templates_models.DocumentTemplate`.

Поддерживаемые варианты источника:
- путь до одного YAML-файла
- путь до директории с YAML-файлами (*.yml, *.yaml)

Поддерживаемые варианты разметки внутри YAML:
- один документ YAML (один шаблон)
- несколько документов в одном файле через `---`
- обёртка вида `{templates: [ ... ]}`

Совместимость:
- если в ваших моделях есть новые поля (skip_fields/fixed_fields/field_defaults,
  TableColumn.normalizer), они будут заполнены; если полей нет — ключи в YAML
  будут проигнорированы.
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import yaml

from app.models.templates_models import (
    DocumentTemplate,
    TableColumn,
    TableDef,
    TemplateField,
    TemplateSection,
    TemplateUI,
)

SchemaPath = Union[str, Path]


# ----------------- helpers -----------------


def _strip_placeholder_ellipses(text: str) -> str:
    """Удаляет одиночные строки '...' — такие плейсхолдеры ломают yaml.safe_load_all."""
    lines: List[str] = []
    for line in text.splitlines():
        if line.strip() == "...":
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def _as_bool(v: Any, default: bool = True) -> bool:
    if v is None:
        return default
    return bool(v)


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _as_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, list):
        out: List[str] = []
        for it in v:
            if it is None:
                continue
            s = str(it).strip()
            if s:
                out.append(s)
        return out
    try:
        s = str(v).strip()
        return [s] if s else []
    except Exception:
        return []


def _as_fixed_fields(v: Any) -> Dict[str, Dict[str, str]]:
    """fixed_fields: {section_id: {field_name: value}}"""
    if not isinstance(v, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for sec_id, fields in v.items():
        if not isinstance(fields, dict):
            continue
        sec_key = str(sec_id)
        sec_map: Dict[str, str] = {}
        for fname, fval in fields.items():
            if fval is None:
                continue
            sec_map[str(fname)] = str(fval)
        if sec_map:
            out[sec_key] = sec_map
    return out


def _as_field_defaults(v: Any) -> Dict[str, Dict[str, List[str]]]:
    """field_defaults: {section_id: {field_name: [v1, v2, ...]}}"""
    if not isinstance(v, dict):
        return {}
    out: Dict[str, Dict[str, List[str]]] = {}
    for sec_id, fields in v.items():
        if not isinstance(fields, dict):
            continue
        sec_key = str(sec_id)
        sec_map: Dict[str, List[str]] = {}
        for fname, items in fields.items():
            sec_map[str(fname)] = _as_str_list(items)
        if sec_map:
            out[sec_key] = sec_map
    return out


def _model_accepts(model_cls: Any, field_name: str) -> bool:
    # dataclass
    fields = getattr(model_cls, "__dataclass_fields__", None)
    if isinstance(fields, dict):
        return field_name in fields
    # fallback
    return hasattr(model_cls, field_name)


def _parse_ui(raw: Dict[str, Any]) -> TemplateUI:
    ui = raw.get("ui") or {}

    # Для удобства можно задавать category/subcategory прямо в YAML в блоке `ui`.
    # Если не заданы — используем дефолты, чтобы старые шаблоны работали без правок.
    category = str(ui.get("category") or "").strip() or "Без категории"
    subcategory = str(ui.get("subcategory") or "").strip() or "Общее"

    return TemplateUI(
        menu_title=str(ui.get("menu_title") or raw.get("name") or raw.get("code") or ""),
        description=str(ui.get("description") or ""),
        category=category,
        subcategory=subcategory,
    )


def _parse_field(raw: Dict[str, Any]) -> TemplateField:
    kwargs: Dict[str, Any] = dict(
        name=str(raw["name"]),
        label=str(raw.get("label") or raw["name"]),
        type=str(raw.get("type") or "text"),
        required=_as_bool(raw.get("required"), default=True),
        default=raw.get("default"),
        word_tag=raw.get("word_tag"),
        hint=raw.get("hint"),
        output_format=raw.get("output_format"),
    )

    # --- Обработчики дат ---
    if _model_accepts(TemplateField, "date_handler"):
        dh = raw.get("date_handler")
        if dh is not None:
            kwargs["date_handler"] = str(dh)

    # word_tags: универсальный словарь тегов (даты: day/month/year, ФИО: full/short,
    # итоги: sum_num/kop/sum_words)
    if _model_accepts(TemplateField, "word_tags"):
        wt = raw.get("word_tags")
        if isinstance(wt, dict):
            kwargs["word_tags"] = {str(k): str(v) for k, v in wt.items() if v is not None}

    
    # --- Новое: split multi-select options ---
    if _model_accepts(TemplateField, "left_options"):
        lo = raw.get("left_options")
        if isinstance(lo, list):
            kwargs["left_options"] = [str(x) for x in lo if x is not None]

    if _model_accepts(TemplateField, "right_options"):
        ro = raw.get("right_options")
        if isinstance(ro, list):
            kwargs["right_options"] = [str(x) for x in ro if x is not None]


    # --- Обработчики текста (ФИО и т.п.) ---
    if _model_accepts(TemplateField, "text_handler"):
        th = raw.get("text_handler")
        if th is not None:
            kwargs["text_handler"] = str(th)

    # --- Вычисляемые поля (derived) ---
    if _model_accepts(TemplateField, "derive_handler"):
        dh2 = raw.get("derive_handler")
        if dh2 is not None:
            kwargs["derive_handler"] = str(dh2)
    if _model_accepts(TemplateField, "source_table"):
        st = raw.get("source_table")
        if st is not None:
            kwargs["source_table"] = str(st)

    return TemplateField(**kwargs)


def _parse_table(raw: Dict[str, Any]) -> TableDef:
    cols_raw = raw.get("columns") or []
    columns: List[TableColumn] = []
    for c in cols_raw:
        if not isinstance(c, dict) or not c.get("name"):
            continue

        col_kwargs: Dict[str, Any] = dict(
            name=str(c["name"]),
            label=str(c.get("label") or c["name"]),
            type=str(c.get("type") or "text"),
            word_tag=c.get("word_tag"),
            hint=c.get("hint"),
            output_format=c.get("output_format"),
        )
        if _model_accepts(TableColumn, "normalizer"):
            col_kwargs["normalizer"] = c.get("normalizer")

        columns.append(TableColumn(**col_kwargs))

    return TableDef(
        anchor_type=str(raw.get("anchor_type") or "text"),
        anchor_value=str(raw.get("anchor_value") or ""),
        row_template=_as_int(raw.get("row_template"), default=2),
        allow_dynamic_rows=_as_bool(raw.get("allow_dynamic_rows"), default=True),
        min_rows=_as_int(raw.get("min_rows"), default=1),
        max_rows=_as_int(raw.get("max_rows"), default=50),
        columns=columns,
    )


def _parse_section(raw: Dict[str, Any]) -> TemplateSection:
    fields_raw = raw.get("fields") or []
    fields: List[TemplateField] = [_parse_field(f) for f in fields_raw if isinstance(f, dict)]

    table = None
    if isinstance(raw.get("table"), dict):
        table = _parse_table(raw["table"])

    return TemplateSection(
        id=str(raw["id"]),
        title=str(raw.get("title") or raw["id"]),
        fields=fields,
        table=table,
    )


def _parse_template(raw: Dict[str, Any]) -> DocumentTemplate:
    sections_raw = raw.get("sections") or []
    sections: List[TemplateSection] = [_parse_section(s) for s in sections_raw if isinstance(s, dict)]

    tpl_kwargs: Dict[str, Any] = dict(
        code=str(raw["code"]),
        name=str(raw.get("name") or raw["code"]),
        file=str(raw["file"]),
        ui=_parse_ui(raw),
        sections=sections,
        output_name=raw.get("output_name") or raw.get("output") or None,
    )

    # опциональные поля (если добавлены в вашу модель)
    if _model_accepts(DocumentTemplate, "skip_fields"):
        tpl_kwargs["skip_fields"] = _as_str_list(raw.get("skip_fields"))
    if _model_accepts(DocumentTemplate, "fixed_fields"):
        tpl_kwargs["fixed_fields"] = _as_fixed_fields(raw.get("fixed_fields"))
    if _model_accepts(DocumentTemplate, "field_defaults"):
        tpl_kwargs["field_defaults"] = _as_field_defaults(raw.get("field_defaults"))

    return DocumentTemplate(**tpl_kwargs)


def _extract_templates_from_docs(docs: Iterable[Any], source: Path) -> List[Tuple[str, DocumentTemplate]]:
    out: List[Tuple[str, DocumentTemplate]] = []

    for d in docs:
        if not isinstance(d, dict):
            continue

        # вариант: {templates: [ ... ]}
        if isinstance(d.get("templates"), list):
            for item in d["templates"]:
                if isinstance(item, dict) and item.get("code") and item.get("file"):
                    tpl = _parse_template(item)
                    out.append((str(source), tpl))
            continue

        # вариант: один шаблон в документе
        if d.get("code") and d.get("file"):
            tpl = _parse_template(d)
            out.append((str(source), tpl))
            continue

    return out


def _iter_schema_files(path: Path) -> List[Path]:
    """Вернуть список YAML-файлов в директории (стабильно отсортированный)."""
    exts = {".yml", ".yaml"}
    files = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() in exts]
    files.sort(key=lambda p: p.name.lower())
    return files


def _load_from_file(path: Path) -> List[Tuple[str, DocumentTemplate]]:
    text = _strip_placeholder_ellipses(path.read_text(encoding="utf-8"))
    docs = list(yaml.safe_load_all(text))
    return _extract_templates_from_docs(docs, source=path)


# ----------------- public API -----------------


def load_templates(schema_path: SchemaPath) -> Dict[str, DocumentTemplate]:
    """Загрузить шаблоны.

    `schema_path` может быть:
    - YAML-файлом (внутри — один/несколько документов)
    - директорией (внутри — набор *.yml/*.yaml, каждый может содержать несколько документов)

    Возвращает mapping: template_code -> DocumentTemplate.
    """
    root = Path(schema_path)
    if not root.exists():
        raise FileNotFoundError(f"YAML schema not found: {root}")

    items: List[Tuple[str, DocumentTemplate]] = []

    if root.is_dir():
        files = _iter_schema_files(root)
        if not files:
            raise ValueError(f"No YAML files (*.yml/*.yaml) found in directory: {root}")
        for f in files:
            items.extend(_load_from_file(f))
    else:
        items.extend(_load_from_file(root))

    templates: Dict[str, DocumentTemplate] = {}
    seen_from: Dict[str, str] = {}

    for src, tpl in items:
        if tpl.code in templates:
            raise ValueError(
                "Duplicate template code {code!r}: found in {a} and {b}".format(
                    code=tpl.code,
                    a=seen_from.get(tpl.code, "<unknown>"),
                    b=src,
                )
            )
        templates[tpl.code] = tpl
        seen_from[tpl.code] = src

    if not templates:
        raise ValueError(f"No valid templates found in {root}")

    return templates
