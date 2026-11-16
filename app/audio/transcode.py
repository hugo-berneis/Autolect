"""Transcode an arbitrary uploaded audio file (e.g. iPhone Voice Memo .m4a) to
the same 16 kHz mono 16-bit PCM WAV the live pipeline produces, so uploads flow
through the identical transcription/notes path.
"""
from __future__ import annotations

import subprocess

from . import wav


class TranscodeError(RuntimeError):
    pass


def transcode_to_wav16k(src: str, dst: str) -> None:
    """Run ffmpeg to produce a 16 kHz mono pcm_s16le WAV at `dst`."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", src,
                "-ar", str(wav.SAMPLE_RATE),
                "-ac", str(wav.CHANNELS),
                "-f", "wav", "-acodec", "pcm_s16le",
                dst,
            ],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as e:  # ffmpeg not installed
        raise TranscodeError("ffmpeg not found on PATH") from e
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", "replace")[-500:] if e.stderr else str(e)
        raise TranscodeError(f"ffmpeg failed: {msg}") from e
