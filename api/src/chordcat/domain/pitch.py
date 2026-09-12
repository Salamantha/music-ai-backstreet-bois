"""Pitch-class primitives and scale definitions shared across the theory core.

Pure module: no I/O, no state. Pitch classes are ints in 0..11 with 0 = C.
"""

from __future__ import annotations

import re
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

#: Semitones from the parent major scale's tonic up to each mode's tonic.
#: D dorian belongs to the C major scale because dorian sits on the 2nd degree,
#: so its parent tonic is D minus 2. Deriving this from the order of `MODES`
#: would be wrong -- that tuple is not in scale-degree order.
PARENT_MAJOR_OFFSET: Final[dict[Mode, int]] = {
    "major": 0,
    "dorian": 2,
    "phrygian": 4,
    "lydian": 5,
    "mixolydian": 7,
    "minor": 9,
    "locrian": 11,
}


def parent_major_tonic(tonic_pc: int, mode: Mode) -> int:
    """Tonic of the major scale containing exactly this mode's pitch classes."""
    return (tonic_pc - PARENT_MAJOR_OFFSET[mode]) % 12


#: Natural pitch class of each letter name.
_LETTERS: Final[str] = "CDEFGAB"
_NATURAL_PC: Final[tuple[int, ...]] = (0, 2, 4, 5, 7, 9, 11)
_ACCIDENTALS: Final[dict[int, str]] = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}


def spell_in_key(pitch_class: int, tonic_pc: int, mode: str) -> str:
    """Name a pitch class as it would be written in a given key.

    A scale uses each letter name once, so the seventh degree of F# major is
    E#, not F -- the two sound alike but only one can be written without using
    the letter F twice. A fixed twelve-name table cannot express that, which is
    why the spelling is derived from the scale rather than looked up.

    Pitches outside the key fall back to the key's own accidental preference.
    """
    pitch_class %= 12
    scale = MODE_SCALES.get(mode, MODE_SCALES["major"])
    flats = prefers_flats(tonic_pc, mode)

    tonic_name = pc_name(tonic_pc, prefer_flats=flats)
    tonic_letter = _LETTERS.index(tonic_name[0])

    for degree, step in enumerate(scale):
        if (tonic_pc + step) % 12 != pitch_class:
            continue
        letter_index = (tonic_letter + degree) % 7
        letter = _LETTERS[letter_index]
        offset = (pitch_class - _NATURAL_PC[letter_index]) % 12
        if offset > 6:
            offset -= 12
        if offset in _ACCIDENTALS:
            return f"{letter}{_ACCIDENTALS[offset]}"
        break

    return pc_name(pitch_class, prefer_flats=flats)


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

Tonality = Literal["any", "major", "minor"]

#: Which modes read as major and which as minor. A mode is minor-ish when its
#: third is minor, which is what a player means by "I'm in a minor key" -- the
#: distinction that matters here, not the precise mode.
MINOR_MODES: Final[frozenset[str]] = frozenset(
    {"minor", "dorian", "phrygian", "locrian"}
)
MAJOR_MODES: Final[frozenset[str]] = frozenset(
    {"major", "lydian", "mixolydian"}
)


def matches_tonality(mode: str, tonality: str) -> bool:
    """Whether a mode satisfies a stated major/minor preference."""
    if tonality == "major":
        return mode in MAJOR_MODES
    if tonality == "minor":
        return mode in MINOR_MODES
    return True


#: Modes whose tonal centre is minor-ish; used only to pick flat spellings.
_FLAT_MODES: Final[frozenset[str]] = frozenset(
    {"minor", "dorian", "phrygian", "locrian"}
)

#: Natural pitch class of each letter name.
_LETTERS: Final[str] = "CDEFGAB"
_NATURAL_PC: Final[tuple[int, ...]] = (0, 2, 4, 5, 7, 9, 11)
_ACCIDENTALS: Final[dict[int, str]] = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}


def spell_in_key(pitch_class: int, tonic_pc: int, mode: str) -> str:
    """Name a pitch class as it would be written in a given key.

    A scale uses each letter name once, so the seventh degree of F# major is
    E#, not F -- the two sound alike but only one can be written without using
    the letter F twice. A fixed twelve-name table cannot express that, which is
    why the spelling is derived from the scale rather than looked up.

    Pitches outside the key fall back to the key's own accidental preference.
    """
    pitch_class %= 12
    scale = MODE_SCALES.get(mode, MODE_SCALES["major"])
    flats = prefers_flats(tonic_pc, mode)

    tonic_name = pc_name(tonic_pc, prefer_flats=flats)
    tonic_letter = _LETTERS.index(tonic_name[0])

    for degree, step in enumerate(scale):
        if (tonic_pc + step) % 12 != pitch_class:
            continue
        letter_index = (tonic_letter + degree) % 7
        letter = _LETTERS[letter_index]
        offset = (pitch_class - _NATURAL_PC[letter_index]) % 12
        if offset > 6:
            offset -= 12
        if offset in _ACCIDENTALS:
            return f"{letter}{_ACCIDENTALS[offset]}"
        break

    return pc_name(pitch_class, prefer_flats=flats)


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

Tonality = Literal["any", "major", "minor"]

#: Which modes read as major and which as minor. A mode is minor-ish when its
#: third is minor, which is what a player means by "I'm in a minor key" -- the
#: distinction that matters here, not the precise mode.
MINOR_MODES: Final[frozenset[str]] = frozenset(
    {"minor", "dorian", "phrygian", "locrian"}
)
MAJOR_MODES: Final[frozenset[str]] = frozenset(
    {"major", "lydian", "mixolydian"}
)


def matches_tonality(mode: str, tonality: str) -> bool:
    """Whether a mode satisfies a stated major/minor preference."""
    if tonality == "major":
        return mode in MAJOR_MODES
    if tonality == "minor":
        return mode in MINOR_MODES
    return True


#: Modes whose tonal centre is minor-ish; used only to pick flat spellings.
_FLAT_MODES: Final[frozenset[str]] = frozenset(
    {"minor", "dorian", "phrygian", "locrian"}
)

#: Major keys written with flats in their signature: F, Bb, Eb, Ab, Db.
#: Pitch class 6 is left to sharps, since F# major is the commoner spelling
#: than Gb major.
_FLAT_KEY_TONICS: Final[frozenset[int]] = frozenset({5, 10, 3, 8, 1})


def prefers_flats(tonic_pc: int, mode: str) -> bool:
    """Whether a key is written with flats.

    Decided by the parent major scale, because that is what carries the key
    signature: D dorian belongs to C major and uses neither, while D minor
    belongs to F major and therefore writes a B flat -- not an A sharp.
    """
    parent = (tonic_pc - PARENT_MAJOR_OFFSET.get(mode, 0)) % 12
    return parent in _FLAT_KEY_TONICS


def pc(midi_pitch: int) -> int:
    """Pitch class of a MIDI note number."""
    return midi_pitch % 12


def pc_name(pitch_class: int, *, prefer_flats: bool = False) -> str:
    """Human-readable name for a pitch class."""
    names = FLAT_NAMES if prefer_flats else SHARP_NAMES
    return names[pitch_class % 12]


def key_name(tonic_pc: int, mode: str) -> str:
    """Display name for a key, e.g. ``"C major"`` or ``"Bb major"``."""
    return f"{pc_name(tonic_pc, prefer_flats=prefers_flats(tonic_pc, mode))} {mode}"


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


#: Everything after the numeral that a triadic comparison should ignore:
#: sevenths, sixths, suspensions, added tones and inversion figures.
_ROMAN_HEAD: Final = re.compile(r"^([b#\u266d\u266f]*)([ivxIVX]+)(o|0|\u00b0|\u00f8|\+)?")


def strip_modifiers(roman: str) -> str:
    """Reduce a roman numeral to the triad it is built on.

    Queries are sent to Hooktheory as plain triads so that `V vi ii iii` matches
    a song analysed as `V vi ii7 iii7`. Anything that then compares the played
    progression against the song's own chords has to normalise the same way --
    comparing `ii` against `ii7` as raw strings finds nothing, and a real match
    silently scores zero.
    """
    token = roman.strip().replace("\u266d", "b").replace("\u266f", "#")
    match = _ROMAN_HEAD.match(token)
    if not match:
        return token
    accidental, numeral, quality = match.groups()
    return f"{accidental}{numeral}{quality or ''}"


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
