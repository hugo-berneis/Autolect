"""Upload-endpoint tests (transcode faked for hermeticity; one real-ffmpeg run
guarded by availability)."""
from __future__ import annotations

import shutil

import pytest

from app.audio import wav


def test_upload_creates_lecture(client, monkeypatch):
    from app.api import upload as upmod

    def fake_transcode(src, dst):
        wav.create(dst)
        wav.append(dst, b"\x00\x00" * 16000)  # 32000 bytes = 1.0s
        wav.finalize(dst)

    monkeypatch.setattr(upmod, "transcode_to_wav16k", fake_transcode)

    res = client.post(
        "/api/upload",
        data={"title": "Memo", "course": "HIST"},
        files={"file": ("memo.m4a", b"not real audio", "audio/m4a")},
    )
    assert res.status_code == 201, res.text
    lec = res.json()
    assert lec["status"] == "processing"
    assert lec["course"] == "HIST"
    assert lec["audio_bytes"] == 32000 + wav.HEADER_SIZE
    assert abs(lec["duration_sec"] - 1.0) < 1e-6


def test_upload_transcode_failure_marks_error(client, monkeypatch):
    from app.api import upload as upmod
    from app.audio.transcode import TranscodeError

    def boom(src, dst):
        raise TranscodeError("bad input")

    monkeypatch.setattr(upmod, "transcode_to_wav16k", boom)
    res = client.post(
        "/api/upload",
        data={"title": "Broken"},
        files={"file": ("x.m4a", b"xx", "audio/m4a")},
    )
    assert res.status_code == 400
    # the lecture was created then marked error
    lectures = client.get("/api/lectures").json()
    assert any(l["title"] == "Broken" and l["status"] == "error" for l in lectures)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_upload_real_ffmpeg_wav(client):
    # A valid 0.5s 16kHz mono WAV as the uploaded file; ffmpeg transcodes it.
    pcm = b"\x00\x00" * 8000  # 16000 bytes = 0.5s
    data = wav.header(len(pcm)) + pcm
    res = client.post(
        "/api/upload",
        data={"title": "RealFFmpeg"},
        files={"file": ("in.wav", data, "audio/wav")},
    )
    assert res.status_code == 201, res.text
    lec = res.json()
    assert lec["status"] == "processing"
    assert lec["duration_sec"] > 0.4
