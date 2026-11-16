"""Application configuration. All settings come from .env (see .env.example).

No secrets live in code. Fields not used until later phases are included here so
the .env surface is stable from the start.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- storage ---
    data_dir: Path = Path("data")
    db_path: Path = Path("data/autolect.db")
    audio_dir: Path = Path("data/audio")

    # --- auth (enforced in phase e) ---
    app_password: str = "changeme"
    session_secret: str = "dev-secret-change-me"
    login_rate_limit_per_min: int = 5

    # --- transcription / faster-whisper (phase c) ---
    # Benchmarked on M4: `small` on `mps` (int8) runs ~1.6x realtime with
    # proper casing/punctuation; cpu `small` (1.2x) is the fallback.
    whisper_model: str = "small"
    whisper_device: str = "mps"
    whisper_compute_type: str = "int8"
    whisper_device_fallback: str = "cpu"
    whisper_beam_size: int = 1

    # --- notes / Claude (phase d) ---
    anthropic_api_key: str = ""
    live_model: str = "claude-haiku-4-5"
    final_model: str = "claude-sonnet-4-6"
    notes_update_interval_sec: int = 60
    min_new_words_for_update: int = 25
    per_lecture_budget_usd: float = 2.0
    use_batch_api_for_final: bool = False

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
