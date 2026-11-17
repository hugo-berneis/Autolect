"""Offline re-transcription of a saved WAV (the /retranscribe endpoint).

Runs the same silence-windowing over the whole file and replaces the lecture's
transcript. Designed to run in a worker thread (provider is CPU/GPU heavy); it
opens its own DB session via the injected factory.
"""
from __future__ import annotations

import os

import numpy as np
from sqlmodel import delete

from ..audio import wav
from ..audio.transcode import decode_to_wav
from ..models import Lecture, TranscriptSegment
from .base import TranscriptionProvider
from .windowing import find_cut


def retranscribe(
    path: str,
    provider: TranscriptionProvider,
    session_factory,
    lecture_id: int,
) -> int:
    # Accept compressed audio (Opus) by decoding to a temp WAV first.
    wav_path, is_temp = decode_to_wav(path)
    try:
        return _retranscribe_wav(wav_path, provider, session_factory, lecture_id)
    finally:
        if is_temp:
            os.unlink(wav_path)


def _retranscribe_wav(
    path: str,
    provider: TranscriptionProvider,
    session_factory,
    lecture_id: int,
) -> int:
    data_len = wav.data_len(path)
    with session_factory() as db:
        db.exec(delete(TranscriptSegment).where(TranscriptSegment.lecture_id == lecture_id))
        db.commit()

        cursor = 0
        seq = 0
        language = None
        initial_prompt = None
        lecture = db.get(Lecture, lecture_id)
        if lecture is not None:
            language = lecture.language
            from .base import build_initial_prompt

            initial_prompt = build_initial_prompt(
                lecture.course, lecture.context_topic, lecture.context_vocab
            ) or None

        while cursor < data_len:
            raw = wav.read_pcm(path, cursor, data_len)
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            cut = find_cut(samples, flush=False)
            if cut is None:
                cut = len(samples)  # tail
            base_sec = cursor / wav.BYTES_PER_SEC
            segments = provider.transcribe(
                samples[:cut], language=language, initial_prompt=initial_prompt
            )
            for seg in segments:
                if not seg.text:
                    continue
                db.add(
                    TranscriptSegment(
                        lecture_id=lecture_id,
                        seq=seq,
                        start_sec=base_sec + seg.start,
                        end_sec=base_sec + seg.end,
                        text=seg.text,
                    )
                )
                seq += 1
            cursor += cut * 2
            if cut >= len(samples):
                break

        lecture = db.get(Lecture, lecture_id)
        if lecture is not None:
            lecture.transcribed_sec = cursor / wav.BYTES_PER_SEC
            db.add(lecture)
        db.commit()

        return seq  # number of segments written
