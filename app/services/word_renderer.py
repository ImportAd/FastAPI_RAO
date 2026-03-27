from __future__ import annotations

# asyncio: запуск блокирующей синхронной генерации в исполнителе (executor)
import asyncio
# time: вспомогательные средства для измерения времени/логирования, используемые при COM-вызовах
import difflib
import time
# Десятичная математика для денежных значений
from decimal import Decimal, InvalidOperation
# Утилиты для работы с путями к директориям шаблонов и выходных файлов
from pathlib import Path
# аннотации типов
from typing import Any, Dict, List, Optional, Union

# pythoncom / win32com: COM-автоматизация для управления Word в Windows
# Эти модули доступны только на Windows с установленным pywin32
try:
    import pythoncom
    import win32com.client
    _HAS_COM = True
except ImportError:
    _HAS_COM = False
# регулярные выражения для разбора дат и чисел
import re

# --- Морфология (опционально) для преобразования в родительный падеж ---
try:
    import pymorphy2  # type: ignore
    _MORPH = pymorphy2.MorphAnalyzer()
except Exception:
    _MORPH = None

from app.models.templates_models import DocumentTemplate




"""
-----------------
Синхронные вспомогательные функции для заполнения Word (.docx), обёрнутые
в асинхронный интерфейс. Модуль использует COM-автоматизацию для открытия
.docx-шаблона, замены тегов и заполнения таблиц, после чего сохраняет
готовый файл в папку `generated/`.

Примечания:
- Модуль использует `pythoncom`/`win32com.client` и поэтому работает
    только на Windows с установленным Microsoft Word.
"""

# Константы Word (из win32com.client.constants),
# чтобы не тянуть constants и не завязываться на рантайм.
WD_REPLACE_ALL = 2       # wdReplaceAll
WD_FIND_CONTINUE = 1     # wdFindContinue

MONTHS_RU_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


# ---------- Склонение в родительный падеж (RU) ----------


_WORD_RE = re.compile(
    r"^(?P<prefix>[^A-Za-zА-Яа-яЁё-]*)(?P<core>[A-Za-zА-Яа-яЁё-]+)(?P<suffix>[^A-Za-zА-Яа-яЁё-]*)$"
)


def _preserve_case(src: str, out: str) -> str:
    """Сохранить регистр исходного слова (примерно)."""
    if not out:
        return out
    if src.isupper():
        return out.upper()
    if src[:1].isupper():
        return out[:1].upper() + out[1:]
    return out


def _heuristic_genitive_word(word: str) -> str:
    """Простой fallback-склонятель для частых русских форм.

    Используется как запасной вариант, если pymorphy2 не установлен.
    """
    w = word
    low = w.lower()

    # Не трогаем короткие аббревиатуры/коды
    if w.isupper() and len(w) <= 6:
        return w

    # Частые неизменяемые фамилии/формы
    if low.endswith(("ко", "енко", "их", "ых", "го")):
        return w

    # прилагательные: -ый/-ий/-ой -> -ого
    if low.endswith(("ый", "ий", "ой")):
        return _preserve_case(w, low[:-2] + "ого")
    # -ая -> -ой
    if low.endswith("ая"):
        return _preserve_case(w, low[:-2] + "ой")
    # -яя -> -ей
    if low.endswith("яя"):
        return _preserve_case(w, low[:-2] + "ей")
    # -ое/-ее -> -ого
    if low.endswith(("ое", "ее")):
        return _preserve_case(w, low[:-2] + "ого")

    # существительные/имена:
    if low.endswith("а"):
        prev = low[-2:-1]
        repl = "и" if prev in "гкхжчшщ" else "ы"
        return _preserve_case(w, low[:-1] + repl)
    if low.endswith("я"):
        return _preserve_case(w, low[:-1] + "и")
    if low.endswith("ь") or low.endswith("й"):
        return _preserve_case(w, low[:-1] + "я")

    # типичные фамилии: Иванов/Петров -> Иванова/Петрова
    if low.endswith(("ов", "ев", "ин", "ын")):
        return _preserve_case(w, low + "а")

    # на согласную: директор -> директора
    if low[-1:] and low[-1:] in "бвгджзйклмнпрстфхцчшщ":
        return _preserve_case(w, low + "а")

    return w


def _word_to_genitive(word: str) -> str:
    """Склонить слово в родительный падеж (gent), сохранив регистр и пунктуацию."""
    m = _WORD_RE.match(word)
    if not m:
        return word

    prefix = m.group("prefix")
    core = m.group("core")
    suffix = m.group("suffix")

    if core.isupper() and len(core) <= 6:
        return prefix + core + suffix

    if _MORPH is not None:
        try:
            p = _MORPH.parse(core)[0]
            inf = p.inflect({"gent"})
            if inf is not None:
                out = _preserve_case(core, inf.word)
                return prefix + out + suffix
        except Exception:
            pass

    out = _heuristic_genitive_word(core)
    return prefix + out + suffix


def _phrase_to_genitive(text: str) -> str:
    """Склонить фразу в родительный падеж.

    Подходит для должностей:
      "Генеральный директор" -> "Генерального директора"
    """
    parts = [p for p in (text or "").strip().split() if p]
    if not parts:
        return ""
    return " ".join(_word_to_genitive(p) for p in parts)


def _fio_to_genitive(fio: str) -> str:
    """Склонить ФИО в родительный падеж (Иванов Иван Иванович -> Иванова Ивана Ивановича)."""
    fio = " ".join((fio or "").strip().split())
    parts = fio.split(" ") if fio else []
    if len(parts) != 3:
        return _phrase_to_genitive(fio)
    return " ".join(_word_to_genitive(p) for p in parts)


def _org_form_to_abbr(text: str) -> str:
    """Превратить развёрнутую форму собственности в аббревиатуру.

    Поддерживает:
    - уже введённую аббревиатуру (ООО/ЗАО/АО/...)
    - "... (ООО)" — берём аббревиатуру из скобок
    - развёрнутый текст — ищем по ключевым фразам
    - неизвестное/с ошибками — собираем аббревиатуру по первым буквам значимых слов
    """
    t = " ".join((text or "").strip().split())
    if not t:
        return ""

    # Если уже ввели аббревиатуру
    up = t.upper()
    if up in {"ООО", "ЗАО", "ОАО", "АО", "ПАО", "ИП", "АНО", "НКО"}:
        return up

    # Если внутри скобок есть аббревиатура — берём её
    m = re.search(r"\(([A-Za-zА-Яа-яЁё]{2,6})\)", t)
    if m:
        cand = m.group(1).upper()
        if cand in {"ООО", "ЗАО", "ОАО", "АО", "ПАО", "ИП", "АНО", "НКО"}:
            return cand

    low = t.lower().replace("ё", "е")
    mapping = {
        "общество с ограниченной ответственностью": "ООО",
        "закрытое акционерное общество": "ЗАО",
        "открытое акционерное общество": "ОАО",
        "акционерное общество": "АО",
        "публичное акционерное общество": "ПАО",
        "индивидуальный предприниматель": "ИП",
        "автономная некоммерческая организация": "АНО",
        "некоммерческая организация": "НКО",
    }
    for k, ab in mapping.items():
        if k in low:
            return ab

    # Если похоже на одну из известных фраз — возьмём ближайшую
    best = None
    best_ratio = 0.0
    for k, ab in mapping.items():
        r = difflib.SequenceMatcher(None, low, k).ratio()
        if r > best_ratio:
            best_ratio = r
            best = ab
    if best is not None and best_ratio >= 0.83:
        return best

    # fallback: первые буквы значимых слов
    stop = {"с", "и", "в", "во", "на", "по", "к", "ко", "от", "для"}
    words = [w for w in re.split(r"\s+", low) if w and w not in stop]
    abbr = "".join(w[:1] for w in words[:6]).upper()
    return abbr

# ---------- Числа прописью (RU) ----------

def _plural_ru(n: int, one: str, two_four: str, five: str) -> str:
    """Выбор формы слова по числу (русские 1/2-4/5-0)."""
    n = abs(int(n))
    n10 = n % 10
    n100 = n % 100
    if 11 <= n100 <= 14:
        return five
    if n10 == 1:
        return one
    if 2 <= n10 <= 4:
        return two_four
    return five


_UNITS_M = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_UNITS_F = ["ноль", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_TEENS = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

_GROUPS = [
    ("", "", "", "m"),  # units
    ("тысяча", "тысячи", "тысяч", "f"),
    ("миллион", "миллиона", "миллионов", "m"),
    ("миллиард", "миллиарда", "миллиардов", "m"),
    ("триллион", "триллиона", "триллионов", "m"),
]


def _triad_to_words(triad: int, gender: str) -> list[str]:
    """Число 0..999 -> слова (без группы)."""
    triad = int(triad)
    if triad == 0:
        return []

    words: list[str] = []
    h = triad // 100
    t = (triad // 10) % 10
    u = triad % 10

    if h:
        words.append(_HUNDREDS[h])

    if t == 1:
        words.append(_TEENS[u])
        return words

    if t:
        words.append(_TENS[t])

    if u:
        units = _UNITS_F if gender == "f" else _UNITS_M
        words.append(units[u])

    return words


def int_to_words_ru(n: int, *, gender: str = "m") -> str:
    """Целое число -> слова (русский), без валюты."""
    n = int(n)
    if n == 0:
        return "ноль"

    words: list[str] = []
    sign = ""
    if n < 0:
        sign = "минус "
        n = abs(n)

    triads: list[int] = []
    while n > 0:
        triads.append(n % 1000)
        n //= 1000

    for idx in range(len(triads) - 1, -1, -1):
        triad = triads[idx]
        if triad == 0:
            continue

        group_one, group_two, group_five, group_gender = _GROUPS[idx] if idx < len(_GROUPS) else ("", "", "", "m")
        g = group_gender if idx > 0 else gender

        part = _triad_to_words(triad, g)
        if not part:
            continue

        words.extend(part)

        if idx > 0:
            words.append(_plural_ru(triad, group_one, group_two, group_five))

    return sign + " ".join([w for w in words if w]).strip()


def money_to_words_ru(rub: int, kop: int, *, capitalize: bool = True) -> str:
    """Money to words: keep only integer part, no currency/kop text."""
    rub_i = int(rub)
    _ = kop  # ignored by design; keep signature for backwards compatibility

    out = int_to_words_ru(rub_i, gender="m").strip()
    if capitalize and out:
        out = out[0].upper() + out[1:]
    return out

async def render_document(
    template: DocumentTemplate,
    answers: Dict[str, Any],
    templates_dir: Union[str, Path] = "word_templates",
    output_dir: Union[str, Path] = "generated",
) -> Path:
    """
    Асинхронная обёртка над синхронной COM-генерацией.
    Внутри используем run_in_executor, чтобы не блокировать event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        _render_sync,
        template,
        answers,
        Path(templates_dir),
        Path(output_dir),
    )


def split_ddmmyyyy(date_str: str) -> tuple[str, str, str]:
    """
    Разбирает строку формата 01.05.2025 (дд.мм.гггг) на:
    (день с ведущим нулём, месяц прописью (в родительном падеже), год).
    Если формат кривой — возвращаем (исходная_строка, "", "").
    """
    if not date_str:
        return "", "", ""

    m = re.match(r"\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\s*$", date_str)
    if not m:
        # Не рушим всё, просто возвращаем как есть в день.
        return date_str.strip(), "", ""

    day_raw, month_raw, year = m.groups()
    day = day_raw.zfill(2)

    try:
        month_num = int(month_raw)
    except ValueError:
        return day, month_raw, year

    month_name = MONTHS_RU_GENITIVE.get(month_num, month_raw)
    return day, month_name, year

def _parse_money(value: Any) -> Optional[Decimal]:
    """Парсим деньги из строки (best-effort).

    Поддерживает варианты:
      - 1890
      - 1 890 / 1\u00A0890 / 1\u202F890
      - 1 890,50 / 1 890.50
      - '1890 руб.' / '1 890 ₽'
    Возвращает Decimal(….) с 2 знаками или None, если не получилось распарсить.
    """
    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    # нормализуем пробелы (включая NBSP и тонкий пробел)
    s = s.replace("\u00A0", " ").replace("\u202F", " ")

    # извлечь первую подходящую по шаблону числовую часть
    m = re.search(r"[-+]?\d[\d\s\u00A0\u202F]*(?:[\.,]\d+)?", s)
    if not m:
        return None

    num = m.group(0)

    # убрать любые пробелы внутри числа
    num = re.sub(r"[\s\u00A0\u202F]", "", num)

    # нормализовать десятичный разделитель
    if "," in num and "." in num:
        # считаем, что запятые — разделители тысяч
        num = num.replace(",", "")
    else:
        num = num.replace(",", ".")

    try:
        return Decimal(num).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None

def compute_totals_from_table(
    answers: Dict[str, Any],
    table_id: str,
    fee_column: str = "period_fee",
) -> tuple[str, str, int, int]:
    """Подсчитать сумму по таблице answers['tables'][table_id].

    Возвращает:
      (rub_str, kop_str, rub_int, kop_int)

    Никогда не возвращает None — если данных нет, вернёт 0/00.
    """
    tables = answers.get("tables") or {}
    rows = tables.get(table_id) or []
    if not rows:
        return "0", "00", 0, 0

    total = Decimal("0.00")
    parsed_any = False

    for row in rows:
        try:
            raw = row.get(fee_column)
        except Exception:
            continue

        val = _parse_money(raw)
        if val is None:
            continue

        total += val
        parsed_any = True

    if not parsed_any:
        return "0", "00", 0, 0

    total = total.quantize(Decimal("0.01"))
    rub_i = int(total)
    kop_i = int((total - Decimal(rub_i)) * 100)

    return str(rub_i), f"{kop_i:02d}", rub_i, kop_i


def compute_totals_from_objects(answers: Dict[str, Any]) -> tuple[str, str]:
    """Back-compat: сумма по таблице 'objects'."""
    rub_s, kop_s, _rub_i, _kop_i = compute_totals_from_table(answers, "objects")
    return rub_s, kop_s

def _render_sync(
    template: DocumentTemplate,
    answers: Dict[str, Any],
    templates_dir: Path,
    output_dir: Path,
) -> Path:
    """
    Синхронная функция, которая:
    - открывает Word;
    - заполняет теги;
    - заполняет таблицы;
    - сохраняет готовый DOCX.
    ВАЖНО: вызывается в отдельном потоке, поэтому тут CoInitialize/CoUninitialize.
    """
    if not _HAS_COM:
        raise RuntimeError(
            "COM automation (pywin32) is not available. "
            "Document generation requires Windows with MS Office installed."
        )
    pythoncom.CoInitialize()
    try:
        templates_dir = templates_dir.resolve()
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        template_path = templates_dir / template.file
        if not template_path.exists():
            raise FileNotFoundError(f"Template DOCX not found: {template_path}")

        out_name = f"{template.code}_{int(time.time())}.docx"
        output_path = output_dir / out_name

        # Запускаем Word
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False

        doc = word.Documents.Open(str(template_path))
        try:
            # 1) Текстовые теги {{TAG}}
            tag_map = build_tag_mapping(template, answers)
            replace_tags_in_doc(doc, tag_map)

            # 2) Таблицы (sections с table != None)
            fill_tables_in_doc(doc, template, answers)

            # 3) Сохраняем результат
            doc.SaveAs(str(output_path))  # Word сам поймёт формат из расширения .docx
        finally:
            doc.Close(False)
            word.Quit()

        return output_path
    finally:
        pythoncom.CoUninitialize()


# ---------- Подсчёт суммы по таблице ----------



def _split_date_ru_genitive(value: str) -> tuple[str, str, str]:
    """
    Разбить дату формата дд.мм.гггг на (день, месяц_словом_в_род_падеже, год).
    Если формат неверный — возвращает пустые строки.
    """
    if not value:
        return "", "", ""
    m = re.match(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$", str(value))
    if not m:
        return "", "", ""
    day_i = int(m.group(1))
    month_i = int(m.group(2))
    year_s = m.group(3)
    day_s = f"{day_i:02d}"
    month_s = MONTHS_RU_GENITIVE.get(month_i, "")
    return day_s, month_s, year_s


def _fio_to_short(value: str) -> str:
    """
    Преобразовать 'Фамилия Имя Отчество' -> 'Фамилия И.О.'
    Если отчества нет — 'Фамилия И.'
    """
    s = (value or "").strip()
    if not s:
        return ""
    parts = [p for p in s.split() if p]
    if not parts:
        return ""
    last = parts[0]
    initials = ""
    if len(parts) >= 2 and parts[1]:
        initials += parts[1][0].upper() + "."
    if len(parts) >= 3 and parts[2]:
        initials += parts[2][0].upper() + "."
    if initials:
        return f"{last} {initials}".strip()
    return last


def build_tag_mapping(
    template: DocumentTemplate,
    answers: Dict[str, Any],
) -> Dict[str, str]:
    """
    Собираем словарь замен для текстовых тегов.

    Поддерживаем:
    - Обычные поля: word_tag -> значение
    - Даты:
        * date_handler = None / "raw"  -> подставляем как есть в word_tag
        * date_handler = "split_ru_genitive" -> ввод "дд.мм.гггг" разбивается на три тега
          (day/month/year), месяц словом в род.падеже, год полностью.
    - Текстовые обработчики:
        * text_handler = "fio_full_and_initials" -> записывает полное ФИО в word_tag (или word_tags.full),
          а сокращённый формат "Фамилия И.О." — в word_tags.short.
    - Вычисляемые поля:
        * derive_handler = "totals_from_table" -> считает сумму по таблице source_table
          и заполняет теги из word_tags: sum_num/kop/sum_words
    """
    mapping: Dict[str, str] = {}

    fields_answers: Dict[str, Any] = answers.get("fields") or {}

    for section in template.sections:
        sec_data = fields_answers.get(section.id) or {}
        for field in section.fields:
            raw_val = sec_data.get(field.name)

            # --- Split multi-select: два тега (left/right) ---
            if isinstance(raw_val, dict):
                tags = getattr(field, "word_tags", None) or {}
                left_tag = (tags.get("left") or "").strip()
                right_tag = (tags.get("right") or "").strip()
                if left_tag:
                    mapping[left_tag] = str(raw_val.get("left") or "")
                if right_tag:
                    mapping[right_tag] = str(raw_val.get("right") or "")
                # если есть общий тег — можно положить туда склейку для читаемости
                if field.word_tag:
                    l = str(raw_val.get("left") or "")
                    r = str(raw_val.get("right") or "")
                    mapping[field.word_tag] = (l + " / " + r).strip(" /")
                continue

            value = "" if raw_val is None else str(raw_val)

            # --- обработка дат ---
            date_handler = (getattr(field, "date_handler", None) or "").strip().lower()
            if date_handler in ("split_ru_genitive", "split"):
                tags = getattr(field, "word_tags", None) or {}
                day_tag = (tags.get("day") or "").strip()
                month_tag = (tags.get("month") or "").strip()
                year_tag = (tags.get("year") or "").strip()

                d, m, y = _split_date_ru_genitive(value)
                if day_tag:
                    mapping[day_tag] = d
                if month_tag:
                    mapping[month_tag] = m
                if year_tag:
                    mapping[year_tag] = y

                # Если в шаблоне есть ещё и общий тег — тоже подставим исходную дату
                if field.word_tag:
                    mapping[field.word_tag] = value
                continue

            # raw/None -> обычная подстановка (ниже)
            # --- обработка ФИО ---
            text_handler = (getattr(field, "text_handler", None) or "").strip().lower()
            if text_handler in ("fio_full_and_initials", "fio_short"):
                tags = getattr(field, "word_tags", None) or {}
                full_tag = (tags.get("full") or field.word_tag or "").strip()
                short_tag = (tags.get("short") or tags.get("initials") or tags.get("abbr") or "").strip()
                gen_tag = (tags.get("gen") or tags.get("gen_full") or "").strip()
                gen_short_tag = (tags.get("gen_short") or tags.get("gen_initials") or "").strip()

                if full_tag:
                    mapping[full_tag] = value
                elif field.word_tag:
                    mapping[field.word_tag] = value

                if short_tag:
                    mapping[short_tag] = _fio_to_short(value)

                # Дополнительно: родительный падеж (если теги заданы в YAML)
                if gen_tag:
                    mapping[gen_tag] = _fio_to_genitive(value)
                if gen_short_tag:
                    mapping[gen_short_tag] = _fio_to_short(_fio_to_genitive(value))
                continue

            # --- Должность: именительный + родительный ---
            if text_handler in ("position_nom_and_gen", "dol_nom_and_gen"):
                tags = getattr(field, "word_tags", None) or {}
                nom_tag = (tags.get("nom") or field.word_tag or "").strip()
                gen_tag = (tags.get("gen") or "").strip()
                if nom_tag:
                    mapping[nom_tag] = value
                if gen_tag:
                    mapping[gen_tag] = _phrase_to_genitive(value)
                continue

            # --- Форма собственности: развёрнуто + аббревиатура ---
            if text_handler in ("org_form_full_and_abbr", "org_form"):
                tags = getattr(field, "word_tags", None) or {}
                full_tag = (tags.get("full") or field.word_tag or "").strip()
                abbr_tag = (tags.get("abbr") or tags.get("short") or tags.get("initials") or "").strip()

                if full_tag:
                    mapping[full_tag] = value
                if abbr_tag:
                    mapping[abbr_tag] = _org_form_to_abbr(value)
                continue

            # --- вычисляемые поля (итоги по таблице) ---
            derive_handler = (getattr(field, "derive_handler", None) or "").strip().lower()
            if derive_handler in ("totals_from_table", "totals"):
                tags = getattr(field, "word_tags", None) or {}

                # id таблицы-источника (например: objects_a / objects_b)
                source_table = (getattr(field, "source_table", None) or "objects").strip()
                rub_s, kop_s, rub_i, kop_i = compute_totals_from_table(answers, source_table)
                words = money_to_words_ru(rub_i, kop_i, capitalize=True)

                sum_tag = (tags.get("sum_num") or tags.get("rub") or tags.get("sum_rub") or "").strip()
                kop_tag = (tags.get("kop") or tags.get("sum_kop") or "").strip()
                words_tag = (tags.get("sum_words") or tags.get("words") or "").strip()

                # если теги не заданы — пробуем использовать word_tag как sum_num
                if not sum_tag and field.word_tag:
                    sum_tag = str(field.word_tag).strip()

                if sum_tag:
                    mapping[sum_tag] = rub_s
                if kop_tag:
                    mapping[kop_tag] = kop_s
                if words_tag:
                    mapping[words_tag] = words
                continue

            # --- обычная подстановка ---
            if field.word_tag:
                mapping[field.word_tag] = value

    # --- computed totals (таблица objects) ---
    # Back-compat: если в шаблоне используются старые теги TOTAL_FEE_*
    rub, kop = compute_totals_from_objects(answers)
    mapping.setdefault("{{TOTAL_FEE_RUB}}", rub)
    mapping.setdefault("{{TOTAL_FEE_KOP}}", kop)

    # --- другие "фиксированные" поля (если есть) ---
    safety_total = (fields_answers.get("all") or {}).get("safety_total")
    if safety_total is not None:
        mapping["{{SAFETY_TOTAL}}"] = str(safety_total)

    # Legacy cleanup for RAO LD templates where RIGHT_TEXT is no longer used.
    if (template.code or "").strip().lower() in {"rao_ld_ip_do_2017", "rao_ld_ip_s_2017", "rao_ld_ooo"}:
        mapping.setdefault("{{RIGHT_TEXT}}", "")

    return mapping



# ---------- Поиск/замена в тексте документа ----------

def _replace_in_range(rng, search: str, repl: str) -> bool:
    """
    Выполняет Find/Replace в заданном диапазоне rng.
    """
    f = rng.Find
    f.ClearFormatting()
    f.Replacement.ClearFormatting()

    return bool(
        f.Execute(
            FindText=search,
            MatchCase=False,
            MatchWholeWord=False,
            MatchWildcards=False,
            MatchSoundsLike=False,
            MatchAllWordForms=False,
            Forward=True,
            Wrap=WD_FIND_CONTINUE,
            Format=False,
            ReplaceWith=repl,
            Replace=WD_REPLACE_ALL,
        )
    )


def replace_tags_in_doc(doc, tag_map: Dict[str, str]) -> None:
    """
    Для каждого тега делаем Find/Replace:
    - в основном тексте;
    - во всех StoryRanges;
    - во всех надписях/фигурах (TextBox).
    """
    if not tag_map:
        return

    for search, repl in tag_map.items():
        # 1) основной текст
        _replace_in_range(doc.Content, search, repl)

        # 2) все “истории” документа (колонтитулы, примечания и т.д.)
        for sr in doc.StoryRanges:
            r = sr
            while r is not None:
                _replace_in_range(r, search, repl)
                try:
                    r = r.NextStoryRange
                except Exception:
                    r = None

        # 3) надписи/фигуры (TextBox и т.п.)
        for shp in doc.Shapes:
            try:
                if shp.TextFrame.HasText:
                    _replace_in_range(shp.TextFrame.TextRange, search, repl)
            except Exception:
                # На всякий случай игнорируем странные объекты
                pass


# ---------- Работа с таблицами ----------


def fill_tables_in_doc(
    doc,
    template: DocumentTemplate,
    answers: Dict[str, Any],
) -> None:
    """
    Заполняем табличные секции.
    Для каждой секции с table:
      - ищем таблицу по anchor;
      - добавляем нужное число строк;
      - заполняем ячейки по колонкам.
    """
    tables_answers: Dict[str, List[Dict[str, Any]]] = answers.get("tables") or {}

    if not tables_answers:
        return

    for section in template.sections:
        if not section.table:
            continue

        rows_data: List[Dict[str, Any]] = tables_answers.get(section.id) or []
        if not rows_data:
            continue

        table_desc = section.table

        tbl = find_table_by_anchor(doc, table_desc.anchor_type, table_desc.anchor_value)
        if tbl is None:
            # Таблица не найдена – просто пропускаем
            continue

        fill_table_rows(tbl, table_desc, rows_data)



def find_table_by_anchor(doc, anchor_type: str, anchor_value: str):
    """
    Поиск таблицы по "якорю".

    Поддерживаемые anchor_type:
    - "text": якорная строка (фраза) внутри таблицы / рядом с таблицей.
    - "tag": якорный тег вида {{OBJ_CATEGORY}} внутри таблицы (надёжнее для разных версий Word).

    Логика:
    1) Ищем таблицу, где anchor_value содержится в tbl.Range.Text.
    2) Fallback: ищем anchor_value в тексте документа и берём первую таблицу после него.
    """
    at = (anchor_type or "text").strip().lower()
    av = (anchor_value or "").strip()
    if not av:
        return None

    def _contains(hay: str, needle: str) -> bool:
        try:
            return needle.lower() in hay.lower()
        except Exception:
            return False

    if at in ("text", "tag"):
        # 1) ищем внутри таблиц
        for tbl in doc.Tables:
            try:
                t = tbl.Range.Text or ""
                if _contains(t, av):
                    return tbl
            except Exception:
                continue

        # 2) fallback: ищем в документе и берём ближайшую таблицу после
        rng = doc.Content.Duplicate
        find = rng.Find
        find.ClearFormatting()
        find.Text = av

        found = find.Execute(Forward=True, Wrap=WD_FIND_CONTINUE)
        if found:
            pos = rng.Start
            candidate = None
            for tbl in doc.Tables:
                if tbl.Range.Start >= pos:
                    if candidate is None or tbl.Range.Start < candidate.Range.Start:
                        candidate = tbl
            return candidate

    return None

def _get_cell_by_rc(tbl, row_idx: int, col_idx: int):
    """Получить ячейку таблицы по (row, col) без обращения к tbl.Rows(i).

    В таблицах Word с вертикально объединёнными ячейками обращение tbl.Rows(i)
    может падать даже для строк без объединений. Этот helper избегает Rows(i).
    """
    # Быстрый путь (обычно работает для не-merged строк)
    try:
        return tbl.Cell(row_idx, col_idx)
    except Exception:
        pass

    # Fallback: перебор всех ячеек диапазона таблицы
    try:
        for cell in tbl.Range.Cells:
            try:
                if int(cell.RowIndex) == int(row_idx) and int(cell.ColumnIndex) == int(col_idx):
                    return cell
            except Exception:
                continue
    except Exception:
        return None

    return None


def fill_table_rows(tbl, table_desc, rows_data: List[Dict[str, Any]]) -> None:
    """
    Заполнение строк таблицы:
    - начиная с row_template;
    - по колонкам из table_desc.columns (по порядку).

    Важно: не используем tbl.Rows(i), т.к. Word COM может падать на таблицах
    с вертикально объединёнными ячейками (merged) в шапке.
    """
    template_row_idx = int(table_desc.row_template or 1)  # 1-based
    columns = table_desc.columns or []

    # Сколько строк нужно, чтобы вместить все данные
    needed_rows = template_row_idx - 1 + len(rows_data)

    # Добавляем недостающие строки в конец таблицы
    try:
        while tbl.Rows.Count < needed_rows:
            tbl.Rows.Add()
    except Exception:
        # Если Word не дал добавить строку — продолжаем с тем, что есть
        pass

    # Заполняем
    for i, row_data in enumerate(rows_data):
        row_idx = template_row_idx + i

        for col_idx, column in enumerate(columns, start=1):
            cell = _get_cell_by_rc(tbl, row_idx, col_idx)
            if cell is None:
                # Скорее всего, таблица короче/у неё другая структура — прекращаем заполнение строки
                break

            val_raw = (row_data or {}).get(column.name, "")
            val_s = "" if val_raw is None else str(val_raw)

            # Нормализаторы (могут задаваться в YAML)
            norm_id = (getattr(column, "normalizer", None) or "").strip()
            tag = (column.word_tag or "").strip()

            if norm_id == "area_m2" or column.name == "area" or tag == "{{OBJ_AREA}}":
                v = val_s.strip()
                if v and not v.lower().endswith("кв.м."):
                    val_s = f"{v} кв.м."

            if norm_id == "category_code" or column.name == "category" or tag == "{{OBJ_CATEGORY}}":
                m2 = re.search(r"\(([^()]{1,10})\)\s*$", val_s.strip())
                if m2:
                    val_s = m2.group(1).strip()

            # Ошибка на конкретной ячейке не валит генерацию целиком
            try:
                cell.Range.Text = val_s
            except Exception:
                continue
