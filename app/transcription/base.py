"""Transcription provider interface and lecture-context prompt building."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import numpy as np


@dataclass
class Segment:
    start: float  # seconds, relative to the transcribed window
    end: float
    text: str


@runtime_checkable
class TranscriptionProvider(Protocol):
    def transcribe(
        self,
        samples: "np.ndarray",
        *,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> list[Segment]:
        """Transcribe mono 16 kHz float32 samples in [-1, 1]."""
        ...


def build_initial_prompt(
    course: Optional[str], topic: Optional[str], vocabulary: str
) -> str:
    """Bias Whisper toward the lecture's domain (course, topic, key vocab)."""
    parts: list[str] = []
    if course:
        parts.append(f"Course: {course}.")
    if topic:
        parts.append(f"Topic: {topic}.")
    if vocabulary.strip():
        parts.append(f"Key terms: {vocabulary.strip()}.")
    return " ".join(parts)
