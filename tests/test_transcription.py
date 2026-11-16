"""Live + offline transcription tests using the fake provider."""
from __future__ import annotations

import numpy as np

from app.models import Lecture, TranscriptSegment
from app.transcription.windowing import find_cut


def _pcm(seconds_tone: float, seconds_silence: float = 0.0) -> bytes:
    tone = np.full(int(seconds_tone * 16000), 3000, dtype="<i2")
    silence = np.zeros(int(seconds_silence * 16000), dtype="<i2")
    return np.concatenate([tone, silence]).tobytes()


def recv_until(ws, type_, limit=200):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m
    raise AssertionError(f"did not receive {type_}")


def test_find_cut_prefers_silence_and_bounds():
    rate = 16000
    # 11s tone + 1s silence -> cut should land in the silent tail (~11s).
    samples = np.frombuffer(_pcm(11, 1), dtype="<i2").astype(np.float32) / 32768.0
    cut = find_cut(samples)
    assert cut is not None
    assert 10.5 * rate <= cut <= 12.0 * rate

    # Below MIN and no flush -> wait.
    short = np.frombuffer(_pcm(3), dtype="<i2").astype(np.float32) / 32768.0
    assert find_cut(short) is None
    # Flush transcribes whatever is there.
    assert find_cut(short, flush=True) == len(short)


def test_live_window_emits_segment_midstream(client, session):
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "Live", "course": "CS", "language": "en"})
        lid = recv_until(ws, "ready")["lecture_id"]
        ws.send_bytes(_pcm(11, 1))  # 12s with a silent tail -> one window cut at silence
        seg = recv_until(ws, "segment")
        assert seg["text"].startswith("fake segment")
        assert seg["start"] == 0.0
        ws.send_json({"type": "stop"})
        recv_until(ws, "stopped")

    rows = (
        session.query(TranscriptSegment)
        .filter_by(lecture_id=lid)
        .order_by(TranscriptSegment.seq)
        .all()
    )
    assert len(rows) >= 1
    lec = session.get(Lecture, lid)
    assert lec.transcribed_sec > 10  # cursor advanced


def test_flush_on_stop_transcribes_tail(client, session):
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "ShortFlush"})
        lid = recv_until(ws, "ready")["lecture_id"]
        ws.send_bytes(_pcm(3))  # below window min -> only transcribed on stop flush
        ws.send_json({"type": "stop"})
        seg = recv_until(ws, "segment")
        assert seg["text"].startswith("fake segment")
        recv_until(ws, "stopped")

    text = client.get(f"/api/lectures/{lid}/transcript").text
    assert "fake segment" in text


def test_retranscribe_from_saved_audio(client, monkeypatch):
    from app.api import upload as upmod
    from app.audio import wav

    def fake_transcode(src, dst):
        wav.create(dst)
        wav.append(dst, _pcm(5))  # 5s < window min -> one tail window offline
        wav.finalize(dst)

    monkeypatch.setattr(upmod, "transcode_to_wav16k", fake_transcode)
    up = client.post(
        "/api/upload",
        data={"title": "ReTx"},
        files={"file": ("a.m4a", b"x", "audio/m4a")},
    ).json()

    res = client.post(f"/api/lectures/{up['id']}/retranscribe")
    assert res.status_code == 200
    assert res.json()["segments"] >= 1
    assert "fake segment" in client.get(f"/api/lectures/{up['id']}/transcript").text
