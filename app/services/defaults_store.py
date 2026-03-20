from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


"""
-------------------
Персистентное JSON-хранилище системных и пользовательских значений по умолчанию.

Файл содержит два верхнеуровневых словаря: "system" и "users". Системные
значения инициализируются из `DEFAULT_SYSTEM`. Пользовательские значения
хранятся под ключами-идентификаторами пользователей и могут изменяться
во время работы бота.

API предоставляет методы получения, добавления/удаления и загрузки
хранилища с диска.
"""


# ---- System defaults (pre-filled for all users) ----
# Keys are "<section_id>.<field_or_column_name>"
DEFAULT_SYSTEM: Dict[str, List[str]] = {
    # Table section 'objects'
    "objects.tariff": ["base", "optimum", "smart", "special", "simple", "gusli"],
    # For category we store display strings; abbreviation is parsed from '(XXX)'
    "objects.category": [
        "аттракционы (АТР)",
        "бытовое обслуживание (БО)",
        "гостиницы (ГЦ)",
        "здравоохранение (ЗДР)",
        "игровые заведения (ИЗ)",
        "кинотеатры (КН)",
        "клубы (КЛ)",
        "концертный зал (КЗ)",
        "общепит (РН)",
        "парки (ПК)",
        "пляжи (ПЛ)",
        "санаторно-курортные заведения (СКЗ)",
        "спортивные клубы (СК)",
        "торговля (ТО)",
        "торгово-развлекательный комплекс (ТРЦ)",
        "учреждения здравоохранения (ЗДР)",
    ],
    # payment_terms: start empty; users can add their own
    "objects.payment_terms": [],
}


def _field_key(section_id: str, field_name: str) -> str:
    """Сформировать ключ хранилища для пары раздел/поле."""
    return f"{section_id}.{field_name}"


@dataclass
class DefaultsStore:
    """JSON-основанное хранилище значений по умолчанию.

        Структура данных:
            {
                "system": { "<field_key>": [ ... ] },
                "users":  { "<user_id>": { "<field_key>": [ ... ] } }
            }
    """

    path: Path
    data: Dict[str, Any]

    # ---------- persistence ----------

    def save(self) -> None:
        """Сохранить текущее состояние `data` в JSON-файл по `path`."""
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---------- internal ----------

    def _ensure_user(self, user_id: int) -> Dict[str, Any]:
        """Вернуть словарь данных для данного пользователя, создав его при необходимости."""
        users = self.data.setdefault("users", {})
        ukey = str(user_id)
        u = users.get(ukey)
        if not isinstance(u, dict):
            u = {}
            users[ukey] = u
        return u

    # ---------- getters ----------


    def get_system(self, section_id: str, field_name: str = None) -> List[str]:
        """Получить системные значения по умолчанию для раздела/поля.

        Поддерживается два варианта вызова: (`section_id`, `field_name`) или
        единый строковый ключ с точкой в `section_id`.
        """
        system = self.data.setdefault("system", DEFAULT_SYSTEM)

        if field_name is None:
            key = str(section_id)
        else:
            key = _field_key(str(section_id), str(field_name))

        items = system.get(key)
        if isinstance(items, list):
            return [str(x) for x in items]
        return []


    def get_user(self, user_id: int, section_id: str, field_name: str = None) -> List[str]:
        """Получить пользовательские значения по умолчанию для `user_id` и раздела/поля."""
        u = self._ensure_user(user_id)

        if field_name is None:
            key = str(section_id)
        else:
            key = _field_key(str(section_id), str(field_name))

        items = u.get(key)
        if isinstance(items, list):
            return [str(x) for x in items]
        return []


    def add_user(self, user_id: int, section_id: str, field_name: str, value: str = None) -> None:
        """Добавить пользовательское значение по умолчанию.

                Поддерживаются два стиля вызова для обратной совместимости:
                    - `add_user(user_id, "objects", "tariff", "base")`
                    - `add_user(user_id, "objects.tariff", "base")`
        """
        # mode: (user_id, key, value)
        if value is None:
            key = str(section_id)
            value = str(field_name or "")
        else:
            key = _field_key(str(section_id), str(field_name))

        value = (value or "").strip()
        if not value:
            return

        u = self._ensure_user(user_id)
        items = u.setdefault(key, [])
        if not isinstance(items, list):
            items = []
            u[key] = items

        if value not in items:
            items.append(value)


    def delete_user_at(self, user_id: int, section_id: str, field_name: str, idx: int = None) -> bool:
        """Удалить пользовательское значение по индексу.

        Стиль вызова совместим с `add_user`. Возвращает True при успешном
        удалении, False при ошибке или неверном индексе.
        """
        if idx is None:
            # mode: (user_id, key, idx) => section_id=key, field_name=idx
            key = str(section_id)
            try:
                idx = int(field_name)
            except Exception:
                return False
        else:
            key = _field_key(str(section_id), str(field_name))

        u = self._ensure_user(user_id)
        items = u.get(key)
        if not isinstance(items, list):
            return False
        if idx < 0 or idx >= len(items):
            return False
        try:
            items.pop(idx)
            return True
        except Exception:
            return False


def load_defaults_store(path: Union[str, Path]) -> DefaultsStore:
    """Загрузить или создать `DefaultsStore`, привязанный к JSON-файлу.

    Если файл отсутствует — будет создан с предустановленной структурой
    `DEFAULT_SYSTEM`.
    """
    p = Path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("defaults json not a dict")
        except Exception:
            data = {}
    else:
        data = {}

    # ensure structure
    data.setdefault("system", DEFAULT_SYSTEM)
    data.setdefault("users", {})

    store = DefaultsStore(path=p, data=data)
    # persist once if file didn't exist
    if not p.exists():
        store.save()
    return store


    # ---------- helpers for special fields ----------

_ABBR_RE = __import__("re").compile(r"\(([^)]+)\)\s*$")


def extract_abbr(value: str) -> str:
    """Извлечь аббревиатуру в круглых скобках в конце строки.

    Пример: 'Текст (АББР)' -> 'АББР'. Если скобок нет — возвращается
    обрезанная входная строка.
    """
    v = (value or "").strip()
    m = _ABBR_RE.search(v)
    return m.group(1).strip() if m else v
