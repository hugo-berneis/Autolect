"""WebSocket audio ingest + live transcription.

Protocol (client -> server):
  - first message, JSON:
      {"type":"start", "title":..., "course":..., "language":..., ...}  -> new lecture
      {"type":"resume", "lecture_id": N}                                 -> continue one
  - then binary frames: raw 16 kHz mono 16-bit little-endian PCM
  - control, JSON: {"type":"stop"}

Server -> client, JSON:
  - {"type":"ready", "lecture_id": N, "received_bytes": B}
  - {"type":"ack", "received_bytes": B}
  - {"type":"segment", "seq": i, "start": s, "end": e, "text": t}   (live transcript)
  - {"type":"status", "transcribed_sec": x, "lag_sec": l, "rtf": r}
  - {"type":"stopped", "lecture_id": N, "duration_sec": D, "audio_bytes": A}
  - {"type":"error", "message": ...}

Resume is offset-based and the transcription cursor (lecture.transcribed_sec)
persists, so transcription continues from where it left off without re-doing
already-transcribed audio.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from ..audio import wav
from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..models import Course, Lecture, LectureStatus, TranscriptSegment, utcnow
from ..transcription.base import build_initial_prompt

logger = logging.getLogger("autolect.ws")
router = APIRouter()

_active: set[int] = set()
_active_lock = asyncio.Lock()
ACK_INTERVAL_BYTES = 8000  # ~0.25s of audio


def _audio_path(lecture_id: int) -> str:
    return str(settings.audio_dir / f"lecture_{lecture_id}.wav")


async def _claim(lecture_id: int) -> bool:
    async with _active_lock:
        if lecture_id in _active:
            return False
        _active.add(lecture_id)
        return True


async def _release(lecture_id: int) -> None:
    async with _active_lock:
        _active.discard(lecture_id)


@router.websocket("/ws/record")
async def record(
    websocket: WebSocket,
    session: Session = Depends(get_session),
    user: str = Depends(get_current_user),
) -> None:
    await websocket.accept()
    transcriber = websocket.app.state.transcriber
    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    first = await websocket.receive()
    if first["type"] == "websocket.disconnect":
        return
    try:
        intro = _json(first)
    except ValueError:
        await send({"type": "error", "message": "expected JSON start frame"})
        await websocket.close()
        return

    lecture = await _begin(websocket, send, session, user, intro)
    if lecture is None:
        return
    lecture_id = lecture.id
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    if not await _claim(lecture_id):
        await send({"type": "error", "message": "lecture already being recorded"})
        await websocket.close()
        return

    path = _audio_path(lecture_id)
    if intro.get("type") == "start":
        await asyncio.to_thread(wav.create, path)
    received = wav.data_len(path)

    # Start the transcription session (continues from the persisted cursor).
    prompt, cursor_bytes, seq = _prompt_and_cursor(session, lecture)
    transcriber.start_session(
        lecture_id, path, send, lecture.language, prompt, cursor_bytes, seq
    )

    await send({"type": "ready", "lecture_id": lecture_id, "received_bytes": received})

    since_ack = 0
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break  # keep WAV + cursor; resumable
            if msg.get("bytes") is not None:
                pcm = msg["bytes"]
                if pcm:
                    await asyncio.to_thread(wav.append, path, pcm)
                    received += len(pcm)
                    since_ack += len(pcm)
                    transcriber.notify(lecture_id)
                    if since_ack >= ACK_INTERVAL_BYTES:
                        since_ack = 0
                        await send({"type": "ack", "received_bytes": received})
                continue
            try:
                ctrl = _json(msg)
            except ValueError:
                continue
            if ctrl.get("type") == "stop":
                await transcriber.flush(lecture_id)
                transcriber.stop_session(lecture_id)
                await _finish(session, lecture_id, path)
                final = wav.data_len(path)
                await send(
                    {
                        "type": "stopped",
                        "lecture_id": lecture_id,
                        "duration_sec": wav.duration_sec(final),
                        "audio_bytes": final + wav.HEADER_SIZE,
                    }
                )
                await websocket.close()
                break
            await send({"type": "ack", "received_bytes": received})
    except WebSocketDisconnect:
        pass
    finally:
        transcriber.stop_session(lecture_id)
        await _release(lecture_id)


async def _begin(
    websocket: WebSocket, send, session: Session, user: str, intro: dict
) -> Lecture | None:
    kind = intro.get("type")
    if kind == "start":
        lecture = Lecture(
            user_id=user,
            title=intro.get("title") or "Untitled lecture",
            course=intro.get("course"),
            language=intro.get("language") or "en",
            context_topic=intro.get("context_topic"),
            context_vocab=intro.get("context_vocab") or "",
            template_id=intro.get("template_id"),
            status=LectureStatus.recording,
        )
        session.add(lecture)
        session.commit()
        session.refresh(lecture)
        lecture.audio_path = _audio_path(lecture.id)
        lecture.audio_format = "wav"
        session.add(lecture)
        session.commit()
        session.refresh(lecture)
        _remember_vocab(session, lecture)
        return lecture
    if kind == "resume":
        lecture = session.get(Lecture, intro.get("lecture_id"))
        if lecture is None or lecture.user_id != user:
            await send({"type": "error", "message": "lecture not found"})
            await websocket.close()
            return None
        if lecture.status != LectureStatus.recording:
            await send({"type": "error", "message": "lecture is not resumable"})
            await websocket.close()
            return None
        return lecture
    await send({"type": "error", "message": "unknown start type"})
    await websocket.close()
    return None


def _remember_vocab(session: Session, lecture: Lecture) -> None:
    """Persist per-course vocabulary so it isn't retyped next time."""
    if not lecture.course or not lecture.context_vocab.strip():
        return
    course = session.exec(
        select(Course).where(
            Course.user_id == lecture.user_id, Course.name == lecture.course
        )
    ).first()
    if course is None:
        course = Course(
            user_id=lecture.user_id, name=lecture.course, vocabulary=lecture.context_vocab
        )
    else:
        course.vocabulary = lecture.context_vocab
    session.add(course)
    session.commit()


def _prompt_and_cursor(session: Session, lecture: Lecture) -> tuple[str, int, int]:
    vocab = lecture.context_vocab
    if not vocab.strip() and lecture.course:
        course = session.exec(
            select(Course).where(
                Course.user_id == lecture.user_id, Course.name == lecture.course
            )
        ).first()
        if course:
            vocab = course.vocabulary
    prompt = build_initial_prompt(lecture.course, lecture.context_topic, vocab or "")
    cursor_bytes = int(lecture.transcribed_sec * wav.BYTES_PER_SEC)
    cursor_bytes -= cursor_bytes % 2  # align to int16
    seq = len(
        session.exec(
            select(TranscriptSegment.id).where(
                TranscriptSegment.lecture_id == lecture.id
            )
        ).all()
    )
    return prompt, cursor_bytes, seq


async def _finish(session: Session, lecture_id: int, path: str) -> None:
    final = await asyncio.to_thread(wav.finalize, path)
    lecture = session.get(Lecture, lecture_id)
    if lecture is None:
        return
    lecture.audio_bytes = final + wav.HEADER_SIZE
    lecture.duration_sec = wav.duration_sec(final)
    lecture.disk_bytes = final + wav.HEADER_SIZE
    lecture.status = LectureStatus.processing  # transcript done; notes in phase d
    lecture.updated_at = utcnow()
    session.add(lecture)
    session.commit()


def _json(message: dict) -> dict:
    text = message.get("text")
    if text is None:
        raise ValueError("not a text frame")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data
