"""Notes: document model, delta engine, dedup, budget cap, final pass, and the
3-hour flat-cost/flat-memory proof — all with the fake provider."""
from __future__ import annotations

import tracemalloc

import numpy as np
from sqlmodel import Session

from app.models import Lecture, LectureStatus, TranscriptSegment, TypedNote
from app.notes.document import NotesDocument, clean_transcript
from app.notes.engine import NotesEngine
from app.notes.fake import FakeNotesProvider


# --- helpers ---
def _make_engine(engine):
    return NotesEngine(FakeNotesProvider(), lambda: Session(engine))


def _add_lecture(engine, **kw) -> int:
    with Session(engine) as s:
        lec = Lecture(title="T", status=LectureStatus.processing, **kw)
        s.add(lec)
        s.commit()
        s.refresh(lec)
        return lec.id


def _add_segment(engine, lid, seq, start, end, text):
    with Session(engine) as s:
        s.add(
            TranscriptSegment(
                lecture_id=lid, seq=seq, start_sec=start, end_sec=end, text=text
            )
        )
        s.commit()


def _words(n: int) -> str:
    return " ".join(["lecture"] * n)


def _pcm(seconds: float) -> bytes:
    return np.full(int(seconds * 16000), 1500, dtype="<i2").tobytes()


# --- document ---
def test_document_parse_upsert_render():
    doc = NotesDocument.from_markdown("## A\nbody a\n\n## B\nbody b")
    assert doc.outline() == ["## A", "## B"]
    doc.upsert("## A", "new a")  # replace existing
    doc.upsert("## C", "c body")  # append new
    assert doc.outline() == ["## A", "## B", "## C"]
    md = doc.to_markdown()
    assert "new a" in md and "body a" not in md
    assert "## C" in md and "c body" in md


def test_clean_transcript_strips_filler():
    out = clean_transcript("Um, the,  uh, result   is\n\n\n\n42")
    assert "uh" not in out.lower()
    assert "  " not in out
    assert "42" in out


# --- engine ---
async def test_live_update_accounts_tokens(engine):
    lid = _add_lecture(engine)
    _add_segment(engine, lid, 0, 0, 30, _words(40))
    ne = _make_engine(engine)

    assert await ne.update_once(lid, force=True) is True
    with Session(engine) as s:
        lec = s.get(Lecture, lid)
        assert lec.notes_markdown.strip()
        assert lec.noted_sec == 30
        assert lec.input_tokens == 200 and lec.output_tokens == 60
        assert lec.est_cost_usd > 0


async def test_skip_below_min_words(engine):
    lid = _add_lecture(engine)
    _add_segment(engine, lid, 0, 0, 2, "just three words")  # < MIN (25)
    ne = _make_engine(engine)
    assert await ne.update_once(lid, force=False) is False
    assert ne.provider.update_calls == 0


async def test_no_new_segments_is_noop(engine):
    lid = _add_lecture(engine)
    _add_segment(engine, lid, 0, 0, 30, _words(40))
    ne = _make_engine(engine)
    assert await ne.update_once(lid, force=True) is True
    assert await ne.update_once(lid, force=True) is False  # cursor consumed all
    assert ne.provider.update_calls == 1


async def test_budget_cap_pauses_live_notes(engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "per_lecture_budget_usd", 0.001)  # < one update's cost
    lid = _add_lecture(engine)
    _add_segment(engine, lid, 0, 0, 30, _words(40))
    ne = _make_engine(engine)

    assert await ne.update_once(lid, force=True) is True
    with Session(engine) as s:
        assert s.get(Lecture, lid).notes_paused is True

    _add_segment(engine, lid, 1, 30, 60, _words(40))
    assert await ne.update_once(lid, force=True) is False  # paused -> skipped
    assert ne.provider.update_calls == 1


async def test_final_pass_sets_ready_and_dedups(engine):
    lid = _add_lecture(engine)
    _add_segment(engine, lid, 0, 0, 30, _words(40))
    ne = _make_engine(engine)

    assert await ne.finalize(lid) is True
    with Session(engine) as s:
        lec = s.get(Lecture, lid)
        assert lec.status == LectureStatus.ready
        assert "## Summary" in lec.notes_markdown
    assert ne.provider.final_calls == 1

    assert await ne.finalize(lid) is False  # identical input -> reused
    assert ne.provider.final_calls == 1


async def test_three_hour_flat_cost_and_memory(engine):
    """Per-update payload, Claude call count, and memory do not grow with length."""
    lid = _add_lecture(engine)
    ne = _make_engine(engine)
    cycles = 180  # ~3h at one update/minute

    tracemalloc.start()
    for i in range(cycles):
        _add_segment(engine, lid, i, i * 30, i * 30 + 28, _words(30))
        await ne.update_once(lid, force=True)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # One Claude call per update — linear, not quadratic.
    assert ne.provider.update_calls == cycles
    # Per-update transcript payload is bounded and does not trend upward.
    assert max(ne.provider.delta_chars) < 2000
    assert ne.provider.delta_chars[-1] <= ne.provider.delta_chars[0] * 3
    # Total input tokens scale linearly (flat per-update cost).
    with Session(engine) as s:
        assert s.get(Lecture, lid).input_tokens == cycles * 200
    # Memory stays modest regardless of lecture length.
    assert peak < 80 * 1024 * 1024

    await ne.finalize(lid)
    assert ne.provider.final_calls == 1


# --- websocket + endpoints (via app) ---
def _recv_until(ws, type_, limit=300):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m
    raise AssertionError(f"no {type_}")


def test_ws_produces_final_notes_on_stop(client, session):
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "Notes WS"})
        lid = _recv_until(ws, "ready")["lecture_id"]
        ws.send_bytes(_pcm(3))
        ws.send_json({"type": "note", "text": "exam: this is important"})
        ws.send_json({"type": "stop"})
        _recv_until(ws, "stopped")

    lec = session.get(Lecture, lid)
    assert lec.status == LectureStatus.ready
    assert "## Summary" in lec.notes_markdown
    typed = session.query(TypedNote).filter_by(lecture_id=lid).all()
    assert any("important" in t.text for t in typed)


def test_regenerate_endpoint(client, session):
    r = client.post("/api/lectures", json={"title": "Regen"})
    lid = r.json()["id"]
    session.add(
        TranscriptSegment(lecture_id=lid, seq=0, start_sec=0, end_sec=5, text=_words(30))
    )
    session.commit()

    first = client.post(f"/api/lectures/{lid}/regenerate")
    assert first.status_code == 200 and first.json()["regenerated"] is True
    assert session.get(Lecture, lid).status == LectureStatus.ready

    second = client.post(f"/api/lectures/{lid}/regenerate")
    assert second.json()["regenerated"] is False  # identical input reused
