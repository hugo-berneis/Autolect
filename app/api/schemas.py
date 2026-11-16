"""Request/response bodies for the API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LectureCreate(BaseModel):
    title: str
    course: Optional[str] = None
    language: str = "en"
    context_topic: Optional[str] = None
    context_vocab: str = ""
    template_id: Optional[int] = None


class RenameBody(BaseModel):
    title: str


class RetagBody(BaseModel):
    course: Optional[str] = None


class TemplateBody(BaseModel):
    name: str
    content: str
    is_default: bool = False


class CourseBody(BaseModel):
    name: str
    vocabulary: str = ""
