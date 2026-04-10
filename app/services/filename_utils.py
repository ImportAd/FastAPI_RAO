"""filename_utils.py — санитизация пользовательских имён файлов."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote
from typing import Optional

# Запрещённые символы (Windows + Unix) + управляющие
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
# Зарезервированные имена Windows
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_LEN = 150  # без расширения


def sanitize_custom_filename(raw: Optional[str]) -> str:
    """Очистить пользовательское имя файла.

    Возвращает имя с расширением .docx или пустую строку, если входное пустое/мусор.
    """
    if not raw:
        return ""
    s = str(raw).strip()
    if not s:
        return ""

    # Нормализация unicode (NFC) — кириллица в одной форме
    s = unicodedata.normalize("NFC", s)

    # Убрать путь-сепараторы и управляющие
    s = _FORBIDDEN.sub("", s)

    # Убрать ведущие точки/пробелы
    s = s.lstrip(". ").rstrip(". ")
    if not s:
        return ""

    # Отделить расширение
    if "." in s:
        stem, _, ext = s.rpartition(".")
        if not stem:
            stem, ext = s, ""
    else:
        stem, ext = s, ""

    # Принудительно .docx
    ext = "docx"

    # Зарезервированные Windows имена
    if stem.upper() in _WIN_RESERVED:
        stem = f"_{stem}"

    # Лимит длины
    if len(stem) > MAX_LEN:
        stem = stem[:MAX_LEN].rstrip(". ")

    if not stem:
        return ""

    return f"{stem}.{ext}"


def add_suffix(filename: str, suffix: str) -> str:
    """Добавить суффикс к имени перед расширением. 'foo.docx' + '_АКТ' → 'foo_АКТ.docx'."""
    if not filename:
        return ""
    if "." in filename:
        stem, _, ext = filename.rpartition(".")
        return f"{stem}{suffix}.{ext}"
    return f"{filename}{suffix}"


def content_disposition(display_name: str) -> str:
    """RFC 5987 заголовок для имени с не-ASCII символами."""
    # ASCII fallback
    ascii_fallback = display_name.encode("ascii", "replace").decode("ascii").replace("?", "_")
    quoted = quote(display_name, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quoted}'