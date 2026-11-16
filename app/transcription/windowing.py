"""Rolling-window boundary selection.

Cut each window at a low-energy (silence) point so words are not split, while
guaranteeing progress: never shorter than MIN, never longer than MAX. Returns a
sample index to cut at, or None if we should wait for more audio.
"""
from __future__ import annotations

import numpy as np

RATE = 16000
MIN_SEC = 10.0
MAX_SEC = 20.0
FRAME_SEC = 0.1
ABS_SILENCE = 0.02  # RMS on [-1, 1]


def find_cut(
    samples: np.ndarray,
    rate: int = RATE,
    min_sec: float = MIN_SEC,
    max_sec: float = MAX_SEC,
    flush: bool = False,
) -> int | None:
    n = len(samples)
    if flush:
        return n if n > 0 else None
    if n < int(min_sec * rate):
        return None

    frame = int(FRAME_SEC * rate)
    search_start = int(min_sec * rate)
    best_i: int | None = None
    best_rms = float("inf")
    i = search_start
    while i + frame <= n:
        rms = float(np.sqrt(np.mean(np.square(samples[i : i + frame]))))
        if rms < best_rms:
            best_rms, best_i = rms, i
        i += frame

    global_rms = float(np.sqrt(np.mean(np.square(samples)))) or 1e-9
    if best_i is not None and (best_rms < ABS_SILENCE or best_rms < 0.4 * global_rms):
        return best_i + frame  # cut just after the quiet frame

    if n >= int(max_sec * rate):
        return int(max_sec * rate)
    return None  # not long enough yet and no clear silence — wait
