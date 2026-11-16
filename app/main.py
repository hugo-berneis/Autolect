"""FastAPI application factory."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import courses, library, templates
from .config import settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    settings.ensure_dirs()
    app = FastAPI(title="autolect", version="0.1.0")

    app.include_router(library.router)
    app.include_router(templates.router)
    app.include_router(courses.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the bare frontend. Mounted last so API routes and /docs win.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


app = create_app()
