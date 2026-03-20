"""
schemas.py
----------
Pydantic-модели для API (запросы и ответы).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ──────────── Templates ────────────

class FieldSchema(BaseModel):
    name: str
    label: str
    type: str = "text"
    required: bool = True
    default: Optional[str] = None
    hint: Optional[str] = None
    date_handler: Optional[str] = None
    text_handler: Optional[str] = None
    left_options: Optional[List[str]] = None
    right_options: Optional[List[str]] = None
    field_defaults: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TableColumnSchema(BaseModel):
    name: str
    label: str
    type: str = "text"
    hint: Optional[str] = None
    normalizer: Optional[str] = None

    class Config:
        from_attributes = True


class TableDefSchema(BaseModel):
    min_rows: int = 1
    max_rows: int = 50
    allow_dynamic_rows: bool = True
    columns: List[TableColumnSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True


class SectionSchema(BaseModel):
    id: str
    title: str
    fields: List[FieldSchema] = Field(default_factory=list)
    table: Optional[TableDefSchema] = None

    class Config:
        from_attributes = True


class TemplateDetailSchema(BaseModel):
    code: str
    name: str
    menu_title: str
    description: str
    category: str
    subcategory: str
    sections: List[SectionSchema]
    computed_fields: List[str] = Field(default_factory=list)
    skip_fields: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TemplateListItem(BaseModel):
    code: str
    name: str
    menu_title: str
    description: str


class SubcategoryGroup(BaseModel):
    name: str
    templates: List[TemplateListItem]


class CategoryGroup(BaseModel):
    name: str
    subcategories: List[SubcategoryGroup]


class TemplatesTreeResponse(BaseModel):
    categories: List[CategoryGroup]


# ──────────── Generate ────────────

class GenerateRequest(BaseModel):
    template_code: str
    answers: Dict[str, Any]


# ──────────── Defaults ────────────

class DefaultValueRequest(BaseModel):
    value: str


class DefaultsListResponse(BaseModel):
    items: List[str]


# ──────────── Admin ────────────

class GenerationLogEntry(BaseModel):
    draft_id: str
    user_id: Optional[int] = None
    template_code: str
    status: str
    attempts: int = 0
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""


class GenerationLogsResponse(BaseModel):
    drafts: List[GenerationLogEntry]
    total: int


class StatsResponse(BaseModel):
    total_templates: int
    total_generations: int
    successful: int
    failed: int
    processing: int


class ErrorResponse(BaseModel):
    detail: str
