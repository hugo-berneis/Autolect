"""faster-whisper transcription provider.

Live-tuned: int8, beam_size 1, VAD filter on (silence is never transcribed or
emitted). Model loads lazily on first use and falls back from the experimental
Metal (mps) backend to cpu if it fails to initialize.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from .base import Segment

logger = logging.getLogger("autolect.whisper")


class FasterWhisperProvider:
    def __init__(
        self,
        model: str = "small",
        device: str = "mps",
        compute_type: str = "int8",
        device_fallback: str = "cpu",
        beam_size: int = 1,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.device_fallback = device_fallback
        self.beam_size = beam_size
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel  # lazy: heavy import

        try:
            self._model = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
            logger.info(
                "Loaded Whisper %s on %s/%s",
                self.model_name, self.device, self.compute_type,
            )
        except Exception as e:  # pragma: no cover - hardware dependent
            logger.warning(
                "Whisper %s on %s failed (%s); falling back to %s/int8",
                self.model_name, self.device, e, self.device_fallback,
            )
            self._model = WhisperModel(
                self.model_name, device=self.device_fallback, compute_type="int8"
            )
        return self._model

    def transcribe(
        self,
        samples: np.ndarray,
        *,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> list[Segment]:
        model = self._ensure_model()
        segments, _info = model.transcribe(
            samples,
            beam_size=self.beam_size,
            language=language or None,
            initial_prompt=initial_prompt or None,
            vad_filter=True,
        )
        out: list[Segment] = []
        for s in segments:
            text = s.text.strip()
            if text:
                out.append(Segment(s.start, s.end, text))
        return out
