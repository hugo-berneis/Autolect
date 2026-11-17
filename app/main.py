"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .api import courses, library, templates, upload, ws
from .config import settings
from .db import engine
from .notes.base import NotesProvider
from .notes.claude_provider import ClaudeNotesProvider
from .notes.engine import NotesEngine
from .transcription.base import TranscriptionProvider
from .transcription.faster_whisper_provider import FasterWhisperProvider
from .transcription.worker import LiveTranscriber

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def make_provider() -> TranscriptionProvider:
    return FasterWhisperProvider(
        model=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        device_fallback=settings.whisper_device_fallback,
        beam_size=settings.whisper_beam_size,
    )


def make_notes_provider() -> NotesProvider:
    return ClaudeNotesProvider(
        live_model=settings.live_model,
        final_model=settings.final_model,
        api_key=settings.anthropic_api_key,
        use_batch_for_final=settings.use_batch_api_for_final,
    )


def create_app() -> FastAPI:
    settings.ensure_dirs()
    transcriber = LiveTranscriber(
        provider=make_provider(),
        session_factory=lambda: Session(engine),
    )
    notes_engine = NotesEngine(
        provider=make_notes_provider(),
        session_factory=lambda: Session(engine),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await transcriber.start()
        try:
            yield
        finally:
            await transcriber.stop()

    app = FastAPI(title="autolect", version="0.1.0", lifespan=lifespan)
    app.state.transcriber = transcriber
    app.state.notes_engine = notes_engine

    app.include_router(library.router)
    app.include_router(templates.router)
    app.include_router(courses.router)
    app.include_router(upload.router)
    app.include_router(ws.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


app = create_app()
