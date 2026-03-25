"""
main.py — FastAPI приложение. Аутентификация, история документов, генерация.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from starlette.middleware import Middleware
from starlette.responses import Response

from app.config import load_config
from app.db.database import Database
from app.services.auth import AuthService
from app.services.templates_loader import load_templates
from app.services.defaults_store import load_defaults_store

from app.routers import templates as templates_router
from app.routers import generate as generate_router
from app.routers import defaults as defaults_router
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import documents as documents_router
from app.routers import reports as reports_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    cfg = load_config()
    cfg.generated_dir.mkdir(parents=True, exist_ok=True)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.defaults_path.parent.mkdir(parents=True, exist_ok=True)

    # Core services
    logger.info(f"Loading templates from {cfg.schema_path}")
    loaded_templates = load_templates(cfg.schema_path)
    logger.info(f"Loaded {len(loaded_templates)} templates")

    db = Database(cfg.db_path)
    auth = AuthService(cfg.jwt_secret)
    defaults = load_defaults_store(cfg.defaults_path)

    # FastAPI
    app = FastAPI(title="Document Generator API", version="2.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=cfg.cors_origins,
        allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )

    # Wire shared state
    auth_router.db = db
    auth_router.auth_service = auth
    auth_router.admin_username = cfg.admin_username
    auth_router.admin_password = cfg.admin_password

    templates_router.templates = loaded_templates
    generate_router.templates = loaded_templates
    generate_router.db = db
    generate_router.word_templates_dir = str(cfg.word_templates_dir)
    generate_router.generated_dir = str(cfg.generated_dir)

    defaults_router.defaults_store = defaults

    documents_router.db = db

    admin_router.templates = loaded_templates
    admin_router.db = db
    admin_router.defaults_store = defaults

    reports_router._reports_path = cfg.base_dir / "data" / "reports.json"

    # Register routers
    app.include_router(auth_router.router)
    app.include_router(templates_router.router)
    app.include_router(generate_router.router)
    app.include_router(defaults_router.router)
    app.include_router(documents_router.router)
    app.include_router(admin_router.router)
    app.include_router(reports_router.router)

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "templates_loaded": len(loaded_templates)}
    
     # --- No-cache middleware ---
    @app.middleware("http")
    async def no_cache_static(request, call_next):
        response = await call_next(request)
        if request.url.path.endswith(('.js', '.html')):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    # Static files
    if cfg.generated_dir.exists():
        app.mount("/files", StaticFiles(directory=str(cfg.generated_dir)), name="generated")

    admin_static = cfg.base_dir / "static" / "admin"
    if admin_static.exists():
        app.mount("/admin", StaticFiles(directory=str(admin_static), html=True), name="admin_app")

    main_static = cfg.base_dir / "static" / "main"
    if main_static.exists():
        app.mount("/", StaticFiles(directory=str(main_static), html=True), name="main_app")

    logger.info(f"Ready: {len(loaded_templates)} templates, auth enabled, DB at {cfg.db_path}")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    cfg = load_config()
    uvicorn.run("app.main:app", host=cfg.host, port=cfg.port, reload=True)
