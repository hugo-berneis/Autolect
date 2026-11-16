"""Course + remembered-vocabulary storage.

Vocabulary is remembered per course so it does not have to be retyped before
each lecture (passed to Whisper's initial prompt and to Claude in later phases).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from ..auth import get_current_user
from ..db import get_session
from ..models import Course
from .schemas import CourseBody

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.get("", response_model=list[Course])
def list_courses(
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> list[Course]:
    stmt = select(Course).where(Course.user_id == user).order_by(col(Course.name))
    return list(session.exec(stmt).all())


@router.put("", response_model=Course)
def upsert_course(
    body: CourseBody,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Course:
    """Create a course or update its remembered vocabulary (keyed by name)."""
    existing = session.exec(
        select(Course).where(Course.user_id == user, Course.name == body.name)
    ).first()
    if existing is None:
        existing = Course(user_id=user, name=body.name, vocabulary=body.vocabulary)
    else:
        existing.vocabulary = body.vocabulary
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


@router.get("/{name}", response_model=Course)
def get_course(
    name: str,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Course:
    course = session.exec(
        select(Course).where(Course.user_id == user, Course.name == name)
    ).first()
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course
