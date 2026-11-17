"""Notes engine: live delta updates + final pass.

Per-update cost is flat: each update sends only the headings outline plus the
transcript added since the last update (read from the DB via the `noted_sec`
cursor), and Claude returns only new/changed sections, which are patched in. A
content hash prevents paying twice for the same input (retries/regenerate), and
a per-lecture budget cap pauses live notes while transcription continues.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, col, select

from ..config import settings
from ..models import Lecture, LectureStatus, TranscriptSegment, TypedNote, utcnow
from .base import NotesProvider
from .document import DEFAULT_TEMPLATE, SYSTEM_PROMPT, NotesDocument, clean_transcript
from .pricing import estimate_cost

logger = logging.getLogger("autolect.notes")

SendFn = Callable[[dict], Awaitable[None]]


@dataclass
class _NoteSession:
    send: Optional[SendFn] = None
    last_hash: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class NotesEngine:
    def __init__(self, provider: NotesProvider, session_factory) -> None:
        self.provider = provider
        self.session_factory = session_factory
        self._sessions: dict[int, _NoteSession] = {}

    def set_provider(self, provider: NotesProvider) -> None:
        self.provider = provider

    def start_session(self, lecture_id: int, send: Optional[SendFn]) -> None:
        self._sessions[lecture_id] = _NoteSession(send=send)

    def stop_session(self, lecture_id: int) -> None:
        self._sessions.pop(lecture_id, None)

    def add_typed_note(self, lecture_id: int, at_sec: float, text: str) -> None:
        if not text.strip():
            return
        with self.session_factory() as db:
            db.add(TypedNote(lecture_id=lecture_id, at_sec=at_sec, text=text.strip()))
            db.commit()

    async def _send(self, lecture_id: int, payload: dict) -> None:
        sess = self._sessions.get(lecture_id)
        if sess and sess.send:
            try:
                await sess.send(payload)
            except Exception:
                pass

    def _template(self, db: Session, lecture: Lecture) -> str:
        if lecture.template_id:
            from ..models import Template

            tpl = db.get(Template, lecture.template_id)
            if tpl:
                return tpl.content
        return DEFAULT_TEMPLATE

    async def update_once(self, lecture_id: int, force: bool = False) -> bool:
        sess = self._sessions.get(lecture_id)
        lock = sess.lock if sess else asyncio.Lock()
        async with lock:
            return await self._update_locked(lecture_id, force)

    async def _update_locked(self, lecture_id: int, force: bool) -> bool:
        # --- read phase ---
        with self.session_factory() as db:
            lecture = db.get(Lecture, lecture_id)
            if lecture is None or lecture.notes_paused:
                return False
            segs = db.exec(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.lecture_id == lecture_id,
                    TranscriptSegment.start_sec >= lecture.noted_sec,
                )
                .order_by(col(TranscriptSegment.seq))
            ).all()
            if not segs:
                return False
            delta = clean_transcript(" ".join(s.text for s in segs))
            if not force and len(delta.split()) < settings.min_new_words_for_update:
                return False
            typed = db.exec(
                select(TypedNote).where(
                    TypedNote.lecture_id == lecture_id,
                    TypedNote.at_sec >= lecture.noted_sec,
                )
            ).all()
            typed_text = "\n".join(t.text for t in typed)
            template = self._template(db, lecture)
            doc = NotesDocument.from_markdown(lecture.notes_markdown)
            outline = doc.outline()
            new_cursor = max(s.end_sec for s in segs)

        digest = hashlib.sha256(
            (template + "\x00" + delta + "\x00" + typed_text).encode("utf-8")
        ).hexdigest()
        sess = self._sessions.get(lecture_id)
        if sess and sess.last_hash == digest:
            return False  # identical input (retry) — don't double-spend

        try:
            result = await asyncio.to_thread(
                self.provider.update_notes,
                system=SYSTEM_PROMPT,
                template=template,
                outline=outline,
                transcript_delta=delta,
                typed_notes=typed_text,
            )
        except Exception as e:  # keep last good notes; retry next interval
            logger.warning("live notes update failed lecture=%s: %s", lecture_id, e)
            await self._send(lecture_id, {"type": "notes_error", "message": str(e)})
            return False

        # --- write phase ---
        with self.session_factory() as db:
            lecture = db.get(Lecture, lecture_id)
            if lecture is None:
                return False
            doc = NotesDocument.from_markdown(lecture.notes_markdown)
            for patch in result.sections:
                doc.upsert(patch.heading, patch.body)
            lecture.notes_markdown = doc.to_markdown()
            lecture.noted_sec = new_cursor
            self._account(lecture, result.model, result.usage)
            paused = lecture.est_cost_usd >= settings.per_lecture_budget_usd
            if paused:
                lecture.notes_paused = True
            lecture.updated_at = utcnow()
            db.add(lecture)
            db.commit()
            md = lecture.notes_markdown
            cost = lecture.est_cost_usd

        if sess:
            sess.last_hash = digest
        logger.info(
            "live notes update lecture=%s in=%d out=%d cached=%d cost=$%.4f",
            lecture_id, result.usage.input_tokens, result.usage.output_tokens,
            result.usage.cache_read_input_tokens, cost,
        )
        await self._send(lecture_id, {"type": "notes", "markdown": md})
        await self._send(
            lecture_id, {"type": "notes_cost", "est_cost_usd": cost, "paused": paused}
        )
        if paused:
            await self._send(
                lecture_id,
                {"type": "notes_paused", "reason": "budget", "est_cost_usd": cost},
            )
        return True

    async def finalize(self, lecture_id: int) -> bool:
        sess = self._sessions.get(lecture_id)
        lock = sess.lock if sess else asyncio.Lock()
        async with lock:
            return await self._finalize_locked(lecture_id)

    async def _finalize_locked(self, lecture_id: int) -> bool:
        with self.session_factory() as db:
            lecture = db.get(Lecture, lecture_id)
            if lecture is None:
                return False
            segs = db.exec(
                select(TranscriptSegment)
                .where(TranscriptSegment.lecture_id == lecture_id)
                .order_by(col(TranscriptSegment.seq))
            ).all()
            transcript = clean_transcript(" ".join(s.text for s in segs))
            typed = db.exec(
                select(TypedNote).where(TypedNote.lecture_id == lecture_id)
            ).all()
            typed_text = "\n".join(t.text for t in typed)
            template = self._template(db, lecture)
            prior_hash = lecture.final_hash
            had_notes = bool(lecture.notes_markdown.strip())

        digest = hashlib.sha256(
            (template + "\x00" + transcript + "\x00" + typed_text).encode("utf-8")
        ).hexdigest()
        if digest == prior_hash and had_notes:
            # identical input already finalized — reuse, don't double-spend.
            with self.session_factory() as db:
                lecture = db.get(Lecture, lecture_id)
                if lecture:
                    lecture.status = LectureStatus.ready
                    db.add(lecture)
                    db.commit()
            await self._send(lecture_id, {"type": "notes_final", "reused": True})
            return False

        try:
            result = await asyncio.to_thread(
                self.provider.final_notes,
                system=SYSTEM_PROMPT,
                template=template,
                transcript=transcript,
                typed_notes=typed_text,
            )
        except Exception as e:  # keep last good (live) notes; leave as processing
            logger.warning("final notes failed lecture=%s: %s", lecture_id, e)
            with self.session_factory() as db:
                lecture = db.get(Lecture, lecture_id)
                if lecture:
                    lecture.status = LectureStatus.processing
                    db.add(lecture)
                    db.commit()
            await self._send(lecture_id, {"type": "notes_error", "message": str(e)})
            return False

        with self.session_factory() as db:
            lecture = db.get(Lecture, lecture_id)
            if lecture is None:
                return False
            if result.markdown.strip():
                lecture.notes_markdown = result.markdown
            lecture.final_hash = digest
            lecture.status = LectureStatus.ready
            self._account(lecture, result.model, result.usage)
            lecture.updated_at = utcnow()
            db.add(lecture)
            db.commit()
            md = lecture.notes_markdown
            cost = lecture.est_cost_usd

        logger.info(
            "final notes lecture=%s in=%d out=%d cost=$%.4f",
            lecture_id, result.usage.input_tokens, result.usage.output_tokens, cost,
        )
        await self._send(
            lecture_id, {"type": "notes_final", "markdown": md, "est_cost_usd": cost}
        )
        return True

    @staticmethod
    def _account(lecture: Lecture, model: str, usage) -> None:
        lecture.input_tokens += usage.input_tokens + usage.cache_creation_input_tokens
        lecture.output_tokens += usage.output_tokens
        lecture.cached_tokens += usage.cache_read_input_tokens
        lecture.est_cost_usd += estimate_cost(model, usage)
