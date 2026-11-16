"""Low-level incremental WAV writer tests."""
from __future__ import annotations

import os
import struct
import wave

from app.audio import wav


def test_incremental_write_and_finalize(tmp_path):
    p = str(tmp_path / "a.wav")
    wav.create(p)
    assert wav.data_len(p) == 0

    wav.append(p, b"\x01\x00" * 100)  # 200 bytes
    wav.append(p, b"\x02\x00" * 100)  # 200 bytes
    assert wav.data_len(p) == 400  # derived from file size, header not yet patched

    assert wav.finalize(p) == 400
    assert os.path.getsize(p) == wav.HEADER_SIZE + 400

    with open(p, "rb") as f:
        head = f.read(44)
    assert head[0:4] == b"RIFF" and head[8:12] == b"WAVE" and head[36:40] == b"data"
    assert struct.unpack("<I", head[40:44])[0] == 400  # data chunk size
    assert struct.unpack("<I", head[4:8])[0] == 36 + 400  # RIFF size

    # Readable by the stdlib wave module with the expected format.
    w = wave.open(p)
    assert w.getframerate() == 16000
    assert w.getnchannels() == 1
    assert w.getsampwidth() == 2
    assert w.getnframes() == 200  # 400 bytes / 2 bytes-per-frame
    w.close()


def test_duration_and_missing_file(tmp_path):
    assert wav.duration_sec(32000) == 1.0  # 16000 * 2 bytes = 1s
    assert wav.data_len(str(tmp_path / "nope.wav")) == 0
