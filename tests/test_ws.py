"""WebSocket audio-ingest tests: record lifecycle and lossless resume."""
from __future__ import annotations

from app.audio import wav
from app.models import Lecture


def recv_until(ws, type_):
    while True:
        m = ws.receive_json()
        if m["type"] == type_:
            return m


def test_record_stream_stop_persists(client, session):
    pcm = b"\x01\x00" * 8000  # 16000 bytes
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "WS Lecture", "course": "CS"})
        ready = recv_until(ws, "ready")
        lid = ready["lecture_id"]
        assert ready["received_bytes"] == 0

        ws.send_bytes(pcm)
        ws.send_json({"type": "stop"})
        stopped = recv_until(ws, "stopped")
        assert stopped["lecture_id"] == lid
        assert stopped["audio_bytes"] == 16000 + wav.HEADER_SIZE

    lec = session.get(Lecture, lid)
    assert lec is not None
    # stop runs the final notes pass -> lecture becomes ready
    assert lec.status.value == "ready"
    assert lec.audio_bytes == 16000 + wav.HEADER_SIZE
    assert abs(lec.duration_sec - 0.5) < 1e-6  # 16000 bytes / 32000 = 0.5s


def test_resume_is_lossless_and_dedup(client, session):
    chunk = b"\x02\x00" * 4000  # 8000 bytes -> triggers an ack at threshold

    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "Resume me"})
        lid = recv_until(ws, "ready")["lecture_id"]
        ws.send_bytes(chunk)
        ack = recv_until(ws, "ack")
        assert ack["received_bytes"] == 8000
        # Exit without stop == a dropped connection.

    with client.websocket_connect("/ws/record") as ws2:
        ws2.send_json({"type": "resume", "lecture_id": lid})
        ready = recv_until(ws2, "ready")
        # Server reports exactly what it persisted — the client would replay only
        # the unacknowledged tail (here: nothing new before the next chunk).
        assert ready["received_bytes"] == 8000
        ws2.send_bytes(chunk)
        ws2.send_json({"type": "stop"})
        stopped = recv_until(ws2, "stopped")
        assert stopped["audio_bytes"] == 16000 + wav.HEADER_SIZE

    lec = session.get(Lecture, lid)
    assert lec.audio_bytes == 16000 + wav.HEADER_SIZE  # no loss, no duplication


def test_resume_unknown_lecture_errors(client):
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "resume", "lecture_id": 99999})
        m = ws.receive_json()
        assert m["type"] == "error"


def test_stop_compresses_to_opus(client, session, monkeypatch):
    import shutil

    if shutil.which("ffmpeg") is None:
        import pytest

        pytest.skip("ffmpeg not installed")
    from app.config import settings

    monkeypatch.setattr(settings, "compress_audio", True)
    # ~1s of non-silent audio so Opus has something to encode.
    pcm = b"\x00\x40" * 16000
    with client.websocket_connect("/ws/record") as ws:
        ws.send_json({"type": "start", "title": "Opus"})
        lid = recv_until(ws, "ready")["lecture_id"]
        ws.send_bytes(pcm)
        ws.send_json({"type": "stop"})
        recv_until(ws, "stopped")

    lec = session.get(Lecture, lid)
    assert lec.audio_format == "opus"
    assert lec.audio_path.endswith(".opus")
    assert lec.audio_bytes < 32044  # much smaller than the raw WAV
