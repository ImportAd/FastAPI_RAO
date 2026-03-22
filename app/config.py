"""config.py — загрузка конфигурации из .env файла."""
from __future__ import annotations

import os
import secrets
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
    db_path: Path = Path("data/app.db")
    defaults_path: Path = Path("data/defaults.json")

    cors_origins: List[str] = field(default_factory=lambda: ["http://localhost:8080"])

    # Auth
    jwt_secret: str = ""
    admin_username: str = "admin"
    admin_password: str = "admin"


def load_config() -> AppConfig:
    base_dir = Path(os.getenv("BASE_DIR", ".")).resolve()
    cors_raw = os.getenv("CORS_ORIGINS", "http://localhost:8080,http://localhost:8081")
    cors_origins = [s.strip() for s in cors_raw.split(",") if s.strip()]

    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret:
        jwt_secret = secrets.token_hex(32)

    return AppConfig(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        base_dir=base_dir,
        schema_path=base_dir / os.getenv("TEMPLATES_YAML_DIR", "templates_yaml"),
        word_templates_dir=base_dir / os.getenv("WORD_TEMPLATES_DIR", "word_templates"),
        generated_dir=base_dir / os.getenv("GENERATED_DIR", "generated"),
        db_path=base_dir / os.getenv("DB_PATH", "data/app.db"),
        defaults_path=base_dir / os.getenv("DEFAULTS_PATH", "data/defaults.json"),
        cors_origins=cors_origins,
        jwt_secret=jwt_secret,
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("ADMIN_PASSWORD", "admin"),
    )
