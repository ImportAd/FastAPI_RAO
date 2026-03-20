"""
main.py
-------
FastAPI приложение для генерации документов.
Заменяет Telegram-бота: те же YAML-шаблоны, та же COM-генерация,
но через REST API вместо FSM.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import load_config
from app.services.templates_loader import load_templates
from app.services.defaults_store import load_defaults_store
from app.services.generation_store import load_generation_store

from app.routers import templates as templates_router
from app.routers import generate as generate_router
from app.routers import defaults as defaults_router
from app.routers import admin as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    cfg = load_config()

    # Ensure directories exist
    cfg.generated_dir.mkdir(parents=True, exist_ok=True)
    cfg.defaults_path.parent.mkdir(parents=True, exist_ok=True)

    # Load templates from YAML
    logger.info(f"Loading templates from {cfg.schema_path}")
    loaded_templates = load_templates(cfg.schema_path)
    logger.info(f"Loaded {len(loaded_templates)} templates")

    # Load stores
    defaults = load_defaults_store(cfg.defaults_path)
    gen_store = load_generation_store(cfg.generation_drafts_path)

    # Create FastAPI app
    app = FastAPI(
        title="Document Generator API",
        description="REST API для генерации документов по шаблонам. Замена Telegram-бота.",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Wire up shared state into routers
    templates_router.templates = loaded_templates
    generate_router.templates = loaded_templates
    generate_router.generation_store = gen_store
    generate_router.word_templates_dir = str(cfg.word_templates_dir)
    generate_router.generated_dir = str(cfg.generated_dir)
    defaults_router.defaults_store = defaults
    admin_router.templates = loaded_templates
    admin_router.generation_store = gen_store

    # Register routers
    app.include_router(templates_router.router)
    app.include_router(generate_router.router)
    app.include_router(defaults_router.router)
    app.include_router(admin_router.router)

    # Health check
    @app.get("/api/v1/health")
    async def health():
        return {
            "status": "ok",
            "templates_loaded": len(loaded_templates),
        }

    # Serve generated files for download (optional, for direct links)
    if cfg.generated_dir.exists():
        app.mount(
            "/files",
            StaticFiles(directory=str(cfg.generated_dir)),
            name="generated_files",
        )

    logger.info(f"App ready. {len(loaded_templates)} templates, "
                f"serving on {cfg.host}:{cfg.port}")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=True,
    )
