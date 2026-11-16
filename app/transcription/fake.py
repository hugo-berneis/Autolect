"""Deterministic provider for tests — no model, no downloads, no network."""
from __future__ import annotations

from typing import Optional

import numpy as np

from .base import Segment


class FakeTranscriptionProvider:
    """Returns one segment per window describing its duration, so tests can
    assert the windowing/streaming loop without a real model."""

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(
        self,
        samples: np.ndarray,
        *,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> list[Segment]:
        self.calls += 1
        dur = len(samples) / 16000.0
        if dur <= 0:
            return []
        return [Segment(0.0, dur, f"fake segment {self.calls} ({dur:.1f}s)")]
