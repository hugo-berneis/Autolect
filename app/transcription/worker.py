"""Live transcription worker.

A single background task drains a bounded, de-duplicated queue of lectures that
have new audio. For each, it reads the un-transcribed tail from the on-disk WAV,
cuts a rolling window at silence, runs the provider off the event loop, persists
segments, and streams them to the client. Memory stays flat for a 3-hour lecture
(only the current window is held) and each second of audio is transcribed once
via the per-lecture byte cursor.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Optional

import numpy as np

from ..audio import wav
from ..models import Lecture, TranscriptSegment
from .base import Segment, TranscriptionProvider
from .windowing import find_cut

logger = logging.getLogger("autolect.transcribe")

SendFn = Callable[[dict], Awaitable[None]]
MIN_BYTES = int(10.0 * wav.BYTES_PER_SEC)


class _LiveSession:
    def __init__(
        self,
        lecture_id: int,
        path: str,
        send: SendFn,
        language: Optional[str],
        initial_prompt: str,
        cursor_bytes: int,
        seq: int,
    ) -> None:
        self.lecture_id = lecture_id
        self.path = path
        self.send = send
        self.language = language
        self.initial_prompt = initial_prompt
        self.cursor_bytes = cursor_bytes
        self.seq = seq
        self.flushing = False
        self.flush_done = asyncio.Event()


class LiveTranscriber:
    def __init__(self, provider: TranscriptionProvider, session_factory) -> None:
        self.provider = provider
        self.session_factory = session_factory
        self._sessions: dict[int, _LiveSession] = {}
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._queued: set[int] = set()
        self._task: Optional[asyncio.Task] = None

    # --- lifecycle ---
    def set_provider(self, provider: TranscriptionProvider) -> None:
        self.provider = provider

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._sessions.clear()
        self._queued.clear()
        self._queue = asyncio.Queue()

    # --- per-connection session management ---
    def start_session(
        self,
        lecture_id: int,
        path: str,
        send: SendFn,
        language: Optional[str],
        initial_prompt: str,
        cursor_bytes: int,
        seq: int,
    ) -> None:
        self._sessions[lecture_id] = _LiveSession(
            lecture_id, path, send, language, initial_prompt, cursor_bytes, seq
        )

    def stop_session(self, lecture_id: int) -> None:
        self._sessions.pop(lecture_id, None)
        self._queued.discard(lecture_id)

    def notify(self, lecture_id: int) -> None:
        self._enqueue(lecture_id)

    async def flush(self, lecture_id: int) -> None:
        s = self._sessions.get(lecture_id)
        if s is None:
            return
        s.flushing = True
        s.flush_done.clear()
        self._enqueue(lecture_id)
        await s.flush_done.wait()

    def _enqueue(self, lecture_id: int) -> None:
        if lecture_id in self._sessions and lecture_id not in self._queued:
            self._queued.add(lecture_id)
            self._queue.put_nowait(lecture_id)

    # --- worker loop ---
    async def _run(self) -> None:
        while True:
            lecture_id = await self._queue.get()
            self._queued.discard(lecture_id)
            s = self._sessions.get(lecture_id)
            if s is None:
                continue
            try:
                await self._process_one(s)
            except Exception:  # pragma: no cover - defensive
                logger.exception("transcription window failed for %s", lecture_id)
                if s.flushing:
                    s.flushing = False
                    s.flush_done.set()

    async def _process_one(self, s: _LiveSession) -> None:
        data_len = wav.data_len(s.path)
        avail = data_len - s.cursor_bytes
        if avail <= 0:
            if s.flushing:
                s.flushing = False
                s.flush_done.set()
            return

        raw = await asyncio.to_thread(wav.read_pcm, s.path, s.cursor_bytes, data_len)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        cut = find_cut(samples, flush=s.flushing)
        if cut is None:
            return  # wait for more audio; a later notify re-enqueues

        window = samples[:cut]
        base_sec = s.cursor_bytes / wav.BYTES_PER_SEC
        t0 = time.perf_counter()
        segments: list[Segment] = await asyncio.to_thread(
            self.provider.transcribe,
            window,
            language=s.language,
            initial_prompt=s.initial_prompt,
        )
        proc = time.perf_counter() - t0
        cut_sec = cut / float(wav.SAMPLE_RATE)

        with self.session_factory() as db:
            for seg in segments:
                if not seg.text:
                    continue
                seq_val = s.seq
                row = TranscriptSegment(
                    lecture_id=s.lecture_id,
                    seq=seq_val,
                    start_sec=base_sec + seg.start,
                    end_sec=base_sec + seg.end,
                    text=seg.text,
                )
                db.add(row)
                s.seq += 1
                await self._safe_send(
                    s,
                    {
                        "type": "segment",
                        "seq": seq_val,
                        "start": base_sec + seg.start,
                        "end": base_sec + seg.end,
                        "text": seg.text,
                    },
                )
            lecture = db.get(Lecture, s.lecture_id)
            if lecture is not None:
                lecture.transcribed_sec = base_sec + cut_sec
                db.add(lecture)
            db.commit()

        s.cursor_bytes += cut * 2
        lag = wav.duration_sec(wav.data_len(s.path)) - s.cursor_bytes / wav.BYTES_PER_SEC
        await self._safe_send(
            s,
            {
                "type": "status",
                "transcribed_sec": s.cursor_bytes / wav.BYTES_PER_SEC,
                "lag_sec": max(0.0, lag),
                "rtf": (proc / cut_sec) if cut_sec > 0 else 0.0,
            },
        )

        remaining = wav.data_len(s.path) - s.cursor_bytes
        if s.flushing:
            if remaining > 0:
                self._enqueue(s.lecture_id)
            else:
                s.flushing = False
                s.flush_done.set()
        elif remaining >= MIN_BYTES:
            self._enqueue(s.lecture_id)

    async def _safe_send(self, s: _LiveSession, payload: dict) -> None:
        try:
            await s.send(payload)
        except Exception:  # client gone; keep persisting, stop emitting
            pass
