"""Transcode an arbitrary uploaded audio file (e.g. iPhone Voice Memo .m4a) to
the same 16 kHz mono 16-bit PCM WAV the live pipeline produces, so uploads flow
through the identical transcription/notes path.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from . import wav


class TranscodeError(RuntimeError):
    pass


def _run(args: list[str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise TranscodeError("ffmpeg not found on PATH") from e
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", "replace")[-500:] if e.stderr else str(e)
        raise TranscodeError(f"ffmpeg failed: {msg}") from e


def compress_to_opus(wav_path: str, opus_path: str, bitrate: str = "24k") -> int:
    """Compress a WAV to Opus (~7-11 MB/hr at 24k). Returns the output size."""
    _run(
        ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", bitrate, opus_path]
    )
    return os.path.getsize(opus_path)


def decode_to_wav(path: str) -> tuple[str, bool]:
    """Return a 16 kHz mono WAV path for `path`. If `path` is already a WAV it is
    returned as-is (is_temp=False); otherwise it is transcoded to a temp WAV
    (is_temp=True — caller must delete it)."""
    if path.lower().endswith(".wav"):
        return path, False
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    transcode_to_wav16k(path, tmp)
    return tmp, True


def transcode_to_wav16k(src: str, dst: str) -> None:
    """Run ffmpeg to produce a 16 kHz mono pcm_s16le WAV at `dst`."""
    _run(
        [
            "ffmpeg", "-y", "-i", src,
            "-ar", str(wav.SAMPLE_RATE),
            "-ac", str(wav.CHANNELS),
            "-f", "wav", "-acodec", "pcm_s16le",
            dst,
        ]
    )
