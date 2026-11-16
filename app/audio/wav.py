"""Minimal incremental WAV writer for 16 kHz mono 16-bit PCM.

Design for crash-safety: PCM is appended to the data chunk as it arrives. The
RIFF/data sizes in the 44-byte header are patched on finalize, but the audio is
never lost if the process dies mid-recording — `data_len()` derives the real
length from the file size, so a recording can always be resumed or repaired.
"""
from __future__ import annotations

import os
import struct

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes (16-bit)
HEADER_SIZE = 44
BYTES_PER_SEC = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH


def header(data_len: int) -> bytes:
    byte_rate = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
    block_align = CHANNELS * SAMPLE_WIDTH
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + data_len),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", 16),
            struct.pack("<H", 1),  # PCM
            struct.pack("<H", CHANNELS),
            struct.pack("<I", SAMPLE_RATE),
            struct.pack("<I", byte_rate),
            struct.pack("<H", block_align),
            struct.pack("<H", SAMPLE_WIDTH * 8),
            b"data",
            struct.pack("<I", data_len),
        ]
    )


def create(path: str) -> None:
    """Create a new WAV with an empty data chunk."""
    with open(path, "wb") as f:
        f.write(header(0))


def append(path: str, pcm: bytes) -> None:
    with open(path, "ab") as f:
        f.write(pcm)


def data_len(path: str) -> int:
    """PCM byte count derived from file size (authoritative even if the header
    was never patched, e.g. after a crash)."""
    if not os.path.exists(path):
        return 0
    return max(0, os.path.getsize(path) - HEADER_SIZE)


def finalize(path: str) -> int:
    """Patch the header to match the actual data length. Returns data length."""
    dl = data_len(path)
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(header(dl))
    return dl


def duration_sec(data_len_bytes: int) -> float:
    return data_len_bytes / BYTES_PER_SEC
