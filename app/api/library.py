"""Library API: list/search/get/rename/re-tag/delete lectures, download notes
and transcript, and (stubbed until later phases) re-transcribe / regenerate.
"""
from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_
from sqlmodel import Session, col, delete, select

from ..transcription import offline

from ..auth import get_current_user
from ..db import get_session
from ..models import Lecture, LectureStatus, TranscriptSegment, utcnow
from .schemas import LectureCreate, RenameBody, RetagBody

router = APIRouter(prefix="/api/lectures", tags=["lectures"])


def _get_owned(session: Session, lecture_id: int, user: str) -> Lecture:
    lecture = session.get(Lecture, lecture_id)
    if lecture is None or lecture.user_id != user:
        raise HTTPException(status_code=404, detail="Lecture not found")
    return lecture


@router.post("", response_model=Lecture, status_code=201)
def create_lecture(
    body: LectureCreate,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Lecture:
    lecture = Lecture(
        user_id=user,
        title=body.title,
        course=body.course,
        language=body.language,
        context_topic=body.context_topic,
        context_vocab=body.context_vocab,
        template_id=body.template_id,
        status=LectureStatus.recording,
    )
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return lecture


@router.get("", response_model=list[Lecture])
def list_lectures(
    q: str | None = Query(default=None, description="Search title, course, transcript"),
    course: str | None = Query(default=None, description="Filter by exact course tag"),
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> list[Lecture]:
    stmt = select(Lecture).where(Lecture.user_id == user)
    if course:
        stmt = stmt.where(Lecture.course == course)
    if q:
        like = f"%{q}%"
        seg_subq = select(TranscriptSegment.lecture_id).where(
            col(TranscriptSegment.text).like(like)
        )
        stmt = stmt.where(
            or_(
                col(Lecture.title).like(like),
                col(Lecture.course).like(like),
                col(Lecture.id).in_(seg_subq),
            )
        )
    stmt = stmt.order_by(col(Lecture.created_at).desc())
    return list(session.exec(stmt).all())


@router.get("/{lecture_id}", response_model=Lecture)
def get_lecture(
    lecture_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Lecture:
    return _get_owned(session, lecture_id, user)


@router.patch("/{lecture_id}/rename", response_model=Lecture)
def rename_lecture(
    lecture_id: int,
    body: RenameBody,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Lecture:
    lecture = _get_owned(session, lecture_id, user)
    lecture.title = body.title
    lecture.updated_at = utcnow()
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return lecture


@router.patch("/{lecture_id}/retag", response_model=Lecture)
def retag_lecture(
    lecture_id: int,
    body: RetagBody,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Lecture:
    lecture = _get_owned(session, lecture_id, user)
    lecture.course = body.course
    lecture.updated_at = utcnow()
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return lecture


@router.delete("/{lecture_id}", status_code=204)
def delete_lecture(
    lecture_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> None:
    lecture = _get_owned(session, lecture_id, user)
    session.exec(
        delete(TranscriptSegment).where(TranscriptSegment.lecture_id == lecture_id)
    )
    session.delete(lecture)
    session.commit()


@router.get("/{lecture_id}/notes.md", response_class=PlainTextResponse)
def download_notes(
    lecture_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> PlainTextResponse:
    lecture = _get_owned(session, lecture_id, user)
    filename = f"{_slug(lecture.title)}.md"
    return PlainTextResponse(
        content=lecture.notes_markdown or "",
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{lecture_id}/transcript", response_class=PlainTextResponse)
def download_transcript(
    lecture_id: int,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> PlainTextResponse:
    lecture = _get_owned(session, lecture_id, user)
    segs = session.exec(
        select(TranscriptSegment)
        .where(TranscriptSegment.lecture_id == lecture_id)
        .order_by(col(TranscriptSegment.seq))
    ).all()
    lines = [f"[{_ts(s.start_sec)}] {s.text}".rstrip() for s in segs]
    filename = f"{_slug(lecture.title)}.txt"
    return PlainTextResponse(
        content="\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{lecture_id}/retranscribe")
async def retranscribe(
    lecture_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> dict:
    lecture = _get_owned(session, lecture_id, user)
    if not lecture.audio_path or not os.path.exists(lecture.audio_path):
        raise HTTPException(status_code=400, detail="No saved audio for this lecture")
    transcriber = request.app.state.transcriber
    count = await asyncio.to_thread(
        offline.retranscribe,
        lecture.audio_path,
        transcriber.provider,
        transcriber.session_factory,
        lecture_id,
    )
    return {"lecture_id": lecture_id, "segments": count}


@router.post("/{lecture_id}/regenerate")
async def regenerate_notes(
    lecture_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> dict:
    lecture = _get_owned(session, lecture_id, user)
    has_transcript = session.exec(
        select(TranscriptSegment.id).where(TranscriptSegment.lecture_id == lecture_id)
    ).first()
    if not has_transcript:
        raise HTTPException(status_code=400, detail="No transcript to generate notes from")
    engine = request.app.state.notes_engine
    regenerated = await engine.finalize(lecture_id)
    return {"lecture_id": lecture_id, "regenerated": regenerated}


def _ts(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _slug(title: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    return (keep.replace(" ", "_") or "lecture")[:80]
