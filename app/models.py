"""SQLModel tables.

Every table carries a `user_id` so multi-user can be added later without
breaking saved lectures (single user for now — see `auth.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel

DEFAULT_USER = "default"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LectureStatus(str, Enum):
    recording = "recording"
    processing = "processing"
    ready = "ready"
    error = "error"


class Course(SQLModel, table=True):
    """A course tag with remembered vocabulary (acronyms, names, terms) so it
    does not have to be retyped per lecture."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default=DEFAULT_USER, index=True)
    name: str = Field(index=True)
    vocabulary: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)


class Template(SQLModel, table=True):
    """An editable notes-prompt template. The adaptive format is the default."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default=DEFAULT_USER, index=True)
    name: str
    content: str
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


class Lecture(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(default=DEFAULT_USER, index=True)
    title: str = Field(index=True)
    course: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    status: LectureStatus = Field(default=LectureStatus.recording)

    duration_sec: float = Field(default=0.0)
    language: str = Field(default="en")
    context_topic: Optional[str] = Field(default=None)
    context_vocab: str = Field(default="")
    template_id: Optional[int] = Field(default=None, foreign_key="template.id")

    audio_path: Optional[str] = Field(default=None)
    audio_format: Optional[str] = Field(default=None)  # "wav" | "opus"
    audio_bytes: int = Field(default=0)

    notes_markdown: str = Field(default="")
    summary: str = Field(default="")

    # usage / cost accounting (populated in phase d)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cached_tokens: int = Field(default=0)
    est_cost_usd: float = Field(default=0.0)
    disk_bytes: int = Field(default=0)


class TranscriptSegment(SQLModel, table=True):
    """Compact transcript rows. No word-level timestamps unless needed later."""

    id: Optional[int] = Field(default=None, primary_key=True)
    lecture_id: int = Field(foreign_key="lecture.id", index=True)
    seq: int = Field(default=0)
    start_sec: float = Field(default=0.0)
    end_sec: float = Field(default=0.0)
    text: str = Field(default="")
