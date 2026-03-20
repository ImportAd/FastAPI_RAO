"""
config.py
---------
Загрузка конфигурации из .env файла.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AppConfig:
    host: str = "0.0.0.0"
    port: int = 8000

    base_dir: Path = Path(".")
    schema_path: Path = Path("templates_yaml")
    word_templates_dir: Path = Path("word_templates")
    generated_dir: Path = Path("generated")
    defaults_path: Path = Path("data/defaults.json")
    generation_drafts_path: Path = Path("data/generation_drafts.json")

    cors_origins: List[str] = field(default_factory=lambda: ["http://localhost:8080"])
    admin_secret: str = ""


def load_config() -> AppConfig:
    base_dir = Path(os.getenv("BASE_DIR", ".")).resolve()

    cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:8080")
    cors_origins = [s.strip() for s in cors_raw.split(",") if s.strip()]

    return AppConfig(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        base_dir=base_dir,
        schema_path=base_dir / os.getenv("TEMPLATES_YAML_DIR", "templates_yaml"),
        word_templates_dir=base_dir / os.getenv("WORD_TEMPLATES_DIR", "word_templates"),
        generated_dir=base_dir / os.getenv("GENERATED_DIR", "generated"),
        defaults_path=base_dir / os.getenv("DEFAULTS_PATH", "data/defaults.json"),
        generation_drafts_path=base_dir / os.getenv("GENERATION_DRAFTS_PATH", "data/generation_drafts.json"),
        cors_origins=cors_origins,
        admin_secret=os.getenv("ADMIN_SECRET", ""),
    )
