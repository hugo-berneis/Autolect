"""WebSocket audio ingest.

Protocol (client -> server):
  - first message, JSON:
      {"type":"start", "title":..., "course":..., "language":..., ...}  -> new lecture
      {"type":"resume", "lecture_id": N}                                 -> continue one
  - then binary frames: raw 16 kHz mono 16-bit little-endian PCM
  - control, JSON: {"type":"stop"}  (pause is purely client-side: it just stops
    sending frames, so nothing special is needed server-side)

Server -> client, JSON:
  - {"type":"ready", "lecture_id": N, "received_bytes": B}  (B = PCM bytes persisted)
  - {"type":"ack", "received_bytes": B}                      (lets the client trim its resend buffer)
  - {"type":"stopped", "lecture_id": N, "duration_sec": D, "audio_bytes": A}
  - {"type":"error", "message": ...}

Resume is offset-based: the server reports how many PCM bytes it has persisted;
the client replays only the unacknowledged tail. The server only acks bytes it
has written to disk, so audio is never lost or duplicated across reconnects.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from ..audio import wav
from ..auth import get_current_user
from ..config import settings
from ..db import get_session
from ..models import Lecture, LectureStatus, utcnow

logger = logging.getLogger("autolect.ws")
router = APIRouter()

# Guard against two concurrent writers to the same lecture's WAV.
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

    first = await websocket.receive()
    if first["type"] == "websocket.disconnect":
        return
    try:
        intro = _json(first)
    except ValueError:
        await websocket.send_json({"type": "error", "message": "expected JSON start frame"})
        await websocket.close()
        return

    lecture = await _begin(websocket, session, user, intro)
    if lecture is None:
        return
    lecture_id = lecture.id
    settings.audio_dir.mkdir(parents=True, exist_ok=True)

    if not await _claim(lecture_id):
        await websocket.send_json(
            {"type": "error", "message": "lecture already being recorded"}
        )
        await websocket.close()
        return

    path = _audio_path(lecture_id)
    if intro.get("type") == "start":
        await asyncio.to_thread(wav.create, path)
    received = wav.data_len(path)
    await websocket.send_json(
        {"type": "ready", "lecture_id": lecture_id, "received_bytes": received}
    )

    since_ack = 0
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                # Keep the WAV; lecture stays `recording` so it can be resumed.
                break
            if msg.get("bytes") is not None:
                pcm = msg["bytes"]
                if pcm:
                    await asyncio.to_thread(wav.append, path, pcm)
                    received += len(pcm)
                    since_ack += len(pcm)
                    if since_ack >= ACK_INTERVAL_BYTES:
                        since_ack = 0
                        await websocket.send_json(
                            {"type": "ack", "received_bytes": received}
                        )
                continue
            # text control frame
            try:
                ctrl = _json(msg)
            except ValueError:
                continue
            if ctrl.get("type") == "stop":
                await _finish(session, lecture_id, path)
                final = wav.data_len(path)
                await websocket.send_json(
                    {
                        "type": "stopped",
                        "lecture_id": lecture_id,
                        "duration_sec": wav.duration_sec(final),
                        "audio_bytes": final + wav.HEADER_SIZE,
                    }
                )
                await websocket.close()
                break
            # pause/resume are client-side no-ops; ack current state.
            await websocket.send_json({"type": "ack", "received_bytes": received})
    except WebSocketDisconnect:
        pass
    finally:
        await _release(lecture_id)


async def _begin(
    websocket: WebSocket, session: Session, user: str, intro: dict
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
        return lecture
    if kind == "resume":
        lecture = session.get(Lecture, intro.get("lecture_id"))
        if lecture is None or lecture.user_id != user:
            await websocket.send_json({"type": "error", "message": "lecture not found"})
            await websocket.close()
            return None
        if lecture.status != LectureStatus.recording:
            await websocket.send_json(
                {"type": "error", "message": "lecture is not resumable"}
            )
            await websocket.close()
            return None
        return lecture
    await websocket.send_json({"type": "error", "message": "unknown start type"})
    await websocket.close()
    return None


async def _finish(session: Session, lecture_id: int, path: str) -> None:
    final = await asyncio.to_thread(wav.finalize, path)
    lecture = session.get(Lecture, lecture_id)
    if lecture is None:
        return
    lecture.audio_bytes = final + wav.HEADER_SIZE
    lecture.duration_sec = wav.duration_sec(final)
    lecture.disk_bytes = final + wav.HEADER_SIZE
    lecture.status = LectureStatus.processing  # awaiting transcription (phase c)
    lecture.updated_at = utcnow()
    session.add(lecture)
    session.commit()


def _json(message: dict) -> dict:
    import json

    text = message.get("text")
    if text is None:
        raise ValueError("not a text frame")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data
