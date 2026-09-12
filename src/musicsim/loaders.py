from pathlib import Path

import librosa
import numpy as np
import pretty_midi

AUDIO_SR = 22050
CHROMA_FPS = 43.0  # ~ AUDIO_SR / hop_length(512), shared time grid for audio and MIDI chroma

_MIDI_EXTENSIONS = {".mid", ".midi"}


def load_audio_chroma(path: str, fps: float = CHROMA_FPS, sr: int = AUDIO_SR) -> np.ndarray:
    y, sr = librosa.load(path, sr=sr)
    hop_length = max(1, int(round(sr / fps)))
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    # silent frames can come back as all-zero columns, which chroma_cqt's internal
    # normalization turns into NaN (0/0) instead of leaving as zero
    return np.nan_to_num(chroma)


def load_midi_chroma(path: str, fps: float = CHROMA_FPS) -> np.ndarray:
    pm = pretty_midi.PrettyMIDI(path)
    return np.nan_to_num(pm.get_chroma(fs=fps))


def load_chroma(path: str, fps: float = CHROMA_FPS) -> np.ndarray:
    if Path(path).suffix.lower() in _MIDI_EXTENSIONS:
        return load_midi_chroma(path, fps=fps)
    return load_audio_chroma(path, fps=fps)
