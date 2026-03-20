"""
templates_models.py
-------------------
Набор dataclass-моделей для описания структуры шаблонов документов.
Перенесено из Telegram-бота без изменений логики.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TemplateUI:
    menu_title: str
    description: str = ""
    category: str = ""
    subcategory: str = ""


@dataclass(frozen=True)
class TemplateField:
    name: str
    label: str
    type: str = "text"
    required: bool = True
    default: Optional[str] = None
    word_tag: Optional[str] = None
    hint: Optional[str] = None
    output_format: Optional[str] = None
    left_options: Optional[List[str]] = None
    right_options: Optional[List[str]] = None
    date_handler: Optional[str] = None
    word_tags: Optional[Dict[str, str]] = None
    text_handler: Optional[str] = None
    derive_handler: Optional[str] = None
    source_table: Optional[str] = None


@dataclass(frozen=True)
class TableColumn:
    name: str
    label: str
    type: str = "text"
    word_tag: Optional[str] = None
    hint: Optional[str] = None
    output_format: Optional[str] = None
    normalizer: Optional[str] = None


@dataclass(frozen=True)
class TableDef:
    anchor_type: str = "text"
    anchor_value: str = ""
    row_template: int = 2
    allow_dynamic_rows: bool = True
    min_rows: int = 1
    max_rows: int = 50
    columns: List[TableColumn] = field(default_factory=list)


@dataclass(frozen=True)
class TemplateSection:
    id: str
    title: str
    fields: List[TemplateField] = field(default_factory=list)
    table: Optional[TableDef] = None


@dataclass
class DocumentTemplate:
    code: str
    name: str
    file: str
    ui: TemplateUI
    sections: List[TemplateSection] = field(default_factory=list)
    output_name: Optional[str] = None
    skip_fields: List[str] = field(default_factory=list)
    fixed_fields: Dict[str, Dict[str, str]] = field(default_factory=dict)
    field_defaults: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return (self.ui.menu_title or self.name or self.code).strip()

    @property
    def description(self) -> str:
        return (self.ui.description or "").strip()

    def get_section(self, section_id: str) -> Optional[TemplateSection]:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def get_table_section(self, section_id: str) -> Optional[TemplateSection]:
        s = self.get_section(section_id)
        return s if (s and s.table is not None) else None

    def get_field(self, section_id: str, field_name: str) -> TemplateField:
        section = self.get_section(section_id)
        if not section:
            raise KeyError(f"Section {section_id!r} not found")
        for f in section.fields:
            if f.name == field_name:
                return f
        raise KeyError(f"Field {field_name!r} not found in section {section_id!r}")

    def get_fixed_value(self, section_id: str, field_name: str) -> Optional[str]:
        sec = self.fixed_fields.get(section_id) or {}
        v = sec.get(field_name)
        return str(v) if v is not None else None

    def get_field_default_items(self, section_id: str, field_name: str) -> List[str]:
        sec = self.field_defaults.get(section_id) or {}
        items = sec.get(field_name) or []
        return [str(it).strip() for it in items if str(it).strip()]
