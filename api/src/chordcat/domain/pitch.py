"""Pitch-class primitives and scale definitions shared across the theory core.

Pure module: no I/O, no state. Pitch classes are ints in 0..11 with 0 = C.
"""

from __future__ import annotations

from typing import Final, Literal

Mode = Literal[
    "major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "locrian"
]

MODES: Final[tuple[Mode, ...]] = (
    "major",
    "minor",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "locrian",
)

#: Semitone offsets from the tonic for each mode's seven scale degrees.
MODE_SCALES: Final[dict[Mode, tuple[int, ...]]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}

#: Scale degree (0-indexed) whose alteration characterises each mode against the
#: major scale. Used to bias the rotated Krumhansl profiles in key detection.
MODE_CHARACTERISTIC_DEGREE: Final[dict[Mode, int]] = {
    "major": 6,      # leading tone
    "minor": 5,      # b6
    "dorian": 5,     # natural 6
    "phrygian": 1,   # b2
    "lydian": 3,     # #4
    "mixolydian": 6,  # b7
    "locrian": 4,    # b5
}

SHARP_NAMES: Final[tuple[str, ...]] = (
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
)
FLAT_NAMES: Final[tuple[str, ...]] = (
    "C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B",
)

#: Modes whose tonal centre is minor-ish; used only to pick flat spellings.
_FLAT_MODES: Final[frozenset[str]] = frozenset(
    {"minor", "dorian", "phrygian", "locrian"}
)


def pc(midi_pitch: int) -> int:
    """Pitch class of a MIDI note number."""
    return midi_pitch % 12


def pc_name(pitch_class: int, *, prefer_flats: bool = False) -> str:
    """Human-readable name for a pitch class."""
    names = FLAT_NAMES if prefer_flats else SHARP_NAMES
    return names[pitch_class % 12]


def key_name(tonic_pc: int, mode: str) -> str:
    """Display name for a key, e.g. ``"C major"`` or ``"Eb dorian"``."""
    return f"{pc_name(tonic_pc, prefer_flats=mode in _FLAT_MODES)} {mode}"


def scale_pcs(tonic_pc: int, mode: Mode) -> frozenset[int]:
    """The seven pitch classes of ``mode`` rooted on ``tonic_pc``."""
    return frozenset((tonic_pc + step) % 12 for step in MODE_SCALES[mode])


def degree_offset(mode: Mode, degree: int) -> int:
    """Semitone offset above the tonic of a 1-indexed scale ``degree``."""
    if not 1 <= degree <= 7:
        raise ValueError(f"degree must be 1..7, got {degree}")
    return MODE_SCALES[mode][degree - 1]


#: Roman numerals by 0-indexed degree, upper- and lower-case forms.
_UPPER: Final[tuple[str, ...]] = ("I", "II", "III", "IV", "V", "VI", "VII")


def roman_for(offset: int, quality: str, mode: Mode) -> str:
    """Roman-numeral label for a chord ``offset`` semitones above the tonic.

    The numeral's *degree* is chosen by how the offset relates to the mode's own
    scale: an offset that is in the scale takes that degree's numeral plainly; an
    offset that is not takes the nearest lower degree's numeral with an accidental.
    Case and suffix come from ``quality``.
    """
    scale = MODE_SCALES[mode]
    offset %= 12
    if offset in scale:
        degree_index = scale.index(offset)
        accidental = ""
    else:
        # Nearest scale degree below, spelled with a flat (the common case for
        # borrowed chords: bIII, bVI, bVII) or a sharp when that reads better.
        below = max((s for s in scale if s < offset), default=None)
        above = min((s for s in scale if s > offset), default=None)
        if below is not None and offset - below == 1 and above is not None:
            degree_index, accidental = scale.index(above), "b"
        elif below is not None:
            degree_index, accidental = scale.index(below), "#"
        else:
            degree_index, accidental = scale.index(above), "b"  # type: ignore[arg-type]

    numeral = _UPPER[degree_index]
    minorish = quality in {"min", "dim", "min7", "m7b5", "dim7", "min6", "madd9", "minmaj7"}
    if minorish:
        numeral = numeral.lower()

    suffix = {
        "dim": "°", "m7b5": "ø", "dim7": "°7", "aug": "+",
        "dom7": "7", "maj7": "maj7", "min7": "7", "minmaj7": "maj7",
        "maj6": "6", "min6": "6", "sus2": "sus2", "sus4": "sus4",
        "7sus4": "7sus4", "add9": "add9", "madd9": "add9",
    }.get(quality, "")
    return f"{accidental}{numeral}{suffix}"
