"""
routers/templates.py
--------------------
GET /api/v1/templates        — дерево категорий
GET /api/v1/templates/{code} — детальная структура шаблона
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Dict

from app.models.templates_models import DocumentTemplate
from app.models.schemas import (
    CategoryGroup,
    FieldSchema,
    SectionSchema,
    SubcategoryGroup,
    TableColumnSchema,
    TableDefSchema,
    TemplateDetailSchema,
    TemplateListItem,
    TemplatesTreeResponse,
)
from app.services.business_logic import COMPUTED_FIELD_NAMES

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

# Will be set from main.py on startup
templates: Dict[str, DocumentTemplate] = {}


def _build_tree() -> TemplatesTreeResponse:
    """Строит дерево категория → подкатегория → шаблоны."""
    cat_order: list[str] = []
    cat_map: dict[str, dict[str, list[TemplateListItem]]] = {}

    for code, tmpl in templates.items():
        cat = (tmpl.ui.category or "").strip() or "Без категории"
        sub = (tmpl.ui.subcategory or "").strip() or "Общее"

        if cat not in cat_map:
            cat_order.append(cat)
            cat_map[cat] = {}

        if sub not in cat_map[cat]:
            cat_map[cat][sub] = []

        cat_map[cat][sub].append(TemplateListItem(
            code=tmpl.code,
            name=tmpl.name,
            menu_title=tmpl.ui.menu_title,
            description=tmpl.ui.description,
        ))

    categories = []
    for cat_name in sorted(cat_order, key=str.casefold):
        subs = cat_map[cat_name]
        subcategories = []
        for sub_name in sorted(subs.keys(), key=str.casefold):
            items = sorted(subs[sub_name], key=lambda t: t.menu_title.casefold())
            subcategories.append(SubcategoryGroup(name=sub_name, templates=items))
        categories.append(CategoryGroup(name=cat_name, subcategories=subcategories))

    return TemplatesTreeResponse(categories=categories)


def _template_to_detail(tmpl: DocumentTemplate) -> TemplateDetailSchema:
    """Преобразует DocumentTemplate в детальную схему для фронтенда."""
    sections = []
    for sec in tmpl.sections:
        fields = []
        for f in sec.fields:
            field_defs = tmpl.get_field_default_items(sec.id, f.name)
            fields.append(FieldSchema(
                name=f.name,
                label=f.label,
                type=f.type,
                required=f.required,
                default=f.default,
                hint=f.hint,
                date_handler=f.date_handler,
                text_handler=f.text_handler,
                left_options=f.left_options,
                right_options=f.right_options,
                field_defaults=field_defs,
            ))

        table_schema = None
        if sec.table:
            cols = [
                TableColumnSchema(
                    name=c.name,
                    label=c.label,
                    type=c.type,
                    hint=c.hint,
                    normalizer=c.normalizer,
                )
                for c in sec.table.columns
            ]
            table_schema = TableDefSchema(
                min_rows=sec.table.min_rows,
                max_rows=sec.table.max_rows,
                allow_dynamic_rows=sec.table.allow_dynamic_rows,
                columns=cols,
            )

        sections.append(SectionSchema(
            id=sec.id,
            title=sec.title,
            fields=fields,
            table=table_schema,
        ))

    return TemplateDetailSchema(
        code=tmpl.code,
        name=tmpl.name,
        menu_title=tmpl.ui.menu_title,
        description=tmpl.ui.description,
        category=tmpl.ui.category,
        subcategory=tmpl.ui.subcategory,
        sections=sections,
        computed_fields=sorted(COMPUTED_FIELD_NAMES),
        skip_fields=tmpl.skip_fields or [],
    )


@router.get("", response_model=TemplatesTreeResponse)
async def list_templates():
    """Дерево шаблонов: категории → подкатегории → шаблоны."""
    return _build_tree()


@router.get("/{code}", response_model=TemplateDetailSchema)
async def get_template(code: str):
    """Полная структура конкретного шаблона."""
    tmpl = templates.get(code)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{code}' not found")
    return _template_to_detail(tmpl)
