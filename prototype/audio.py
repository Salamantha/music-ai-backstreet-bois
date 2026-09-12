"""
STAGE 1 of the pipeline: audio file -> model-ready windows.

    song.mp3 -> decode -> mono -> resample -> overlapping windows

Nothing here knows what an embedding is. It hands `embedders.py` a list of
equal-length float arrays and nothing else. That is the whole job.

WHY WINDOWS AT ALL
    Every pretrained audio model has a fixed input length it was trained on
    (CLAP: 10 s at 48 kHz, MERT: ~5 s at 24 kHz). A 3-minute song does not
    fit. You cannot just truncate to the first 10 seconds either -- the intro
    of a song is often the least representative part of it. So we cut the
    whole song into windows, embed each one, and pool (see embedders.py).

WHY OVERLAP
    A hard cut every 10 s can land in the middle of a chord change or a
    transition, producing a window that represents nothing real. 50% overlap
    means every moment of the song appears in two windows, so a badly placed
    boundary never hides anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class AudioClip:
    y: np.ndarray            # mono float32, -1..1
    sr: int
    path: str
    duration_s: float

    @property
    def n_samples(self) -> int:
        return len(self.y)


def load_audio(path: str | Path, sr: int = 48000,
               max_seconds: Optional[float] = 300.0,
               offset: float = 0.0) -> AudioClip:
    """Decode MP3/WAV/FLAC/OGG/M4A to mono at `sr`.

    mono:      the models are mono. Averaging channels also kills any
               accidental stereo-phase weirdness in the upload.
    resample:  a model trained at 48 kHz has learned filters at 48 kHz
               spacing. Feeding 44.1 kHz audio shifts every frequency it
               keys on -- so resampling is mandatory, not cosmetic.
    max 5 min: caps memory and runtime on a long upload. Plenty of song.
    """
    import librosa                      # imported lazily: heavy

    y, sr_out = librosa.load(str(path), sr=sr, mono=True,
                             offset=offset, duration=max_seconds)
    y = np.asarray(y, dtype=np.float32)

    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0:
        y = y / peak                    # peak-normalise: loudness is a
                                        # mastering choice, not a musical one
    return AudioClip(y=y, sr=sr_out, path=str(path),
                     duration_s=float(len(y) / sr_out) if sr_out else 0.0)


def window_audio(clip: AudioClip, window_s: float = 10.0,
                 hop_s: Optional[float] = None,
                 min_fill: float = 0.4) -> np.ndarray:
    """-> array of shape (n_windows, window_samples).

    The final partial window is zero-padded, and dropped entirely if it is
    less than `min_fill` full -- a 1-second tail of mostly silence is not a
    representative sample of the song and would drag the mean down.
    """
    hop_s = hop_s if hop_s is not None else window_s / 2
    w = int(round(window_s * clip.sr))
    h = max(1, int(round(hop_s * clip.sr)))
    y = clip.y

    if len(y) == 0:
        return np.zeros((0, w), dtype=np.float32)
    if len(y) <= w:                                    # short clip: one window
        out = np.zeros((1, w), dtype=np.float32)
        out[0, :len(y)] = y
        return out

    starts = list(range(0, len(y) - w + 1, h))
    tail = starts[-1] + w if starts else 0
    if len(y) - tail >= min_fill * w:
        starts.append(len(y) - w)

    out = np.zeros((len(starts), w), dtype=np.float32)
    for i, s in enumerate(starts):
        out[i] = y[s:s + w]
    return out


def is_silent(win: np.ndarray, thresh: float = 1e-4) -> bool:
    """Drop dead air so it does not vote in the pooled average."""
    return float(np.sqrt(np.mean(win ** 2))) < thresh


SUPPORTED = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff"}


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED
