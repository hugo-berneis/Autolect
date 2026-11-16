"""Fallback: upload an existing recording (e.g. iPhone Voice Memo .m4a).

It is transcoded to the same 16 kHz mono WAV as live recordings, creates a
lecture, and lands in the library. Transcription/notes run in later phases.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from ..audio import wav
from ..audio.transcode import TranscodeError, transcode_to_wav16k
from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..models import Lecture, LectureStatus

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=Lecture, status_code=201)
async def upload_recording(
    title: str = Form(...),
    course: str | None = Form(None),
    language: str = Form("en"),
    context_topic: str | None = Form(None),
    context_vocab: str = Form(""),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> Lecture:
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    lecture = Lecture(
        user_id=user,
        title=title,
        course=course,
        language=language,
        context_topic=context_topic,
        context_vocab=context_vocab,
        status=LectureStatus.processing,
    )
    session.add(lecture)
    session.commit()
    session.refresh(lecture)

    suffix = Path(file.filename or "audio").suffix or ".bin"
    tmp = settings.audio_dir / f"upload_{lecture.id}{suffix}"
    dst = settings.audio_dir / f"lecture_{lecture.id}.wav"
    tmp.write_bytes(await file.read())

    try:
        await asyncio.to_thread(transcode_to_wav16k, str(tmp), str(dst))
    except TranscodeError as e:
        lecture.status = LectureStatus.error
        session.add(lecture)
        session.commit()
        raise HTTPException(status_code=400, detail=f"Could not decode audio: {e}")
    finally:
        tmp.unlink(missing_ok=True)

    dl = wav.data_len(str(dst))
    lecture.audio_path = str(dst)
    lecture.audio_format = "wav"
    lecture.audio_bytes = dl + wav.HEADER_SIZE
    lecture.duration_sec = wav.duration_sec(dl)
    lecture.disk_bytes = dst.stat().st_size
    session.add(lecture)
    session.commit()
    session.refresh(lecture)
    return lecture
