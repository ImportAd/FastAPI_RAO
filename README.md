# Document Generator — Backend

REST API для генерации документов по шаблонам.  
Замена Telegram-бота: те же YAML-шаблоны, та же COM-генерация Word, но через HTTP API.

## Требования

- **Windows** с установленным Microsoft Office (Word) — для COM-автоматизации
- **Python 3.10+**
- Библиотека `pywin32` (устанавливается автоматически из requirements.txt)

## Быстрый старт

```powershell
# 1. Создать виртуальное окружение
python -m venv venv
venv\Scripts\activate

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Скопировать конфигурацию
copy .env.example .env

# 4. Скопировать шаблоны из бота
#    - YAML-файлы → templates_yaml/
#    - DOCX-файлы → word_templates/

# 5. Запустить сервер
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Или через `start.bat`.

## API-эндпоинты

### Шаблоны
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/templates` | Дерево: категории → подкатегории → шаблоны |
| GET | `/api/v1/templates/{code}` | Полная структура шаблона (секции, поля, таблицы) |

### Генерация
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/v1/generate` | Генерация DOCX документа |

### Значения по умолчанию
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/defaults/system/{key}` | Системные дефолты |
| GET | `/api/v1/defaults/user/{key}` | Пользовательские дефолты |
| POST | `/api/v1/defaults/user/{key}` | Добавить пользовательский дефолт |
| DELETE | `/api/v1/defaults/user/{key}/{index}` | Удалить пользовательский дефолт |

### Админка
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/admin/stats` | Статистика генераций |
| GET | `/api/v1/admin/logs` | Журнал генераций |
| GET | `/api/v1/admin/logs/{draft_id}` | Детали черновика |
| GET | `/api/v1/admin/errors` | Последние ошибки |

### Служебное
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/v1/health` | Проверка состояния сервера |

## Swagger документация

После запуска доступна по адресу: `http://localhost:8000/docs`

## Структура проекта

```
backend/
├── app/
│   ├── main.py                        # FastAPI приложение
│   ├── config.py                      # Конфигурация из .env
│   ├── models/
│   │   ├── templates_models.py        # Dataclass-модели шаблонов (из бота)
│   │   └── schemas.py                 # Pydantic-схемы API
│   ├── routers/
│   │   ├── templates.py               # GET /templates
│   │   ├── generate.py                # POST /generate
│   │   ├── defaults.py                # Значения по умолчанию
│   │   └── admin.py                   # Админские эндпоинты
│   └── services/
│       ├── templates_loader.py        # Загрузчик YAML (из бота)
│       ├── word_renderer.py           # COM-генерация Word (из бота)
│       ├── business_logic.py          # Вычисляемые поля (из бота)
│       ├── defaults_store.py          # JSON-хранилище дефолтов (из бота)
│       └── generation_store.py        # JSON-хранилище черновиков (из бота)
├── templates_yaml/                    # YAML-шаблоны (скопировать из бота)
├── word_templates/                    # DOCX-шаблоны (скопировать из бота)
├── generated/                         # Выходные файлы
├── data/                              # JSON-хранилища
├── requirements.txt
├── .env.example
├── start.bat
└── README.md
```

## Пример запроса генерации

```json
POST /api/v1/generate
Content-Type: application/json

{
  "template_code": "fm_ld_ip_do_2017",
  "answers": {
    "fields": {
      "contract": {
        "ld_num": "123456",
        "ld_day": "15.03.2026",
        "day": "15.03.2026",
        "dov_num": "232-01/2026-АД",
        "dov_date": "14.01.2026",
        "ip_fio": "Иванов Иван Иванович",
        "ip_cer": "12",
        "ip_cer_num": "345678",
        "ip_date": "01.05.2015",
        "punkt": "3.1",
        "prilog_num": "1",
        "object": "план БТИ, договор аренды и т.п.",
        "dg_day": "01.04.2026",
        "doc": "",
        "ip_stamp_abbr": "М.П."
      },
      "licensee_footer": {
        "address": "г. Москва, ул. Пушкина, д. 1",
        "pocht": "г. Москва, ул. Пушкина, д. 1",
        "ogrn": "1234567890123",
        "inn": "1234567890",
        "raschet_schet": "40702810000000000001",
        "bank": "ПАО Сбербанк",
        "bik": "044525225",
        "kor_schet": "30101810400000000225",
        "mail": "test@example.com",
        "phone": "+7 (999) 123-45-67"
      }
    },
    "tables": {
      "objects": [
        {
          "punkt": "1",
          "name": "Кафе «Ромашка»",
          "address": "г. Москва, ул. Ленина, д. 5",
          "area": "120",
          "staf": "500",
          "sum": "60000",
          "reg": "1.2",
          "set": "1.0",
          "period_fee": "72000"
        }
      ]
    }
  }
}
```

Ответ: DOCX файл для скачивания.
