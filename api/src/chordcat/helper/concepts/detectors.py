"""Named predicates over a FactSet. YAML names one; this decides if it is lit.

Kept separate from the node data so the concept map stays editable by someone
who does not write Python.
"""

from __future__ import annotations

from collections.abc import Callable

from ..facts import FactSet

Detector = Callable[[FactSet], bool]


def _val(fs: FactSet, kind: str) -> dict:
    fact = fs.get(kind)
    return fact.value if fact is not None and isinstance(fact.value, dict) else {}


def _any_of(fs: FactSet, kind: str, *names: str) -> bool:
    value = _val(fs, kind)
    return any(value.get(n, 0) > 0 for n in names)


DETECTORS: dict[str, Detector] = {
    # The root. Note this is *not* "plays three-note chords": the ChordCat
    # voices five-note extended harmony, so a triad-only predicate leaves the
    # root of the map unlit on real hardware and strands everything behind it.
    "has_chords": lambda fs: bool(fs.by_kind("harmony.chord")),
    "has_sevenths": lambda fs: _val(fs, "harmony.extensions").get("sevenths", 0) > 0,
    "has_extended_voicings": lambda fs: _val(fs, "voicing.notes_per_chord").get("max", 0) >= 5,
    "has_sus": lambda fs: _any_of(fs, "harmony.quality_counts", "sus2", "sus4", "7sus4"),
    "has_inversions": lambda fs: _val(fs, "voicing.inversions").get("inverted", 0) > 0,
    "is_close_voiced": lambda fs: 0 < _val(fs, "voicing.register_span").get(
        "span_semitones", 0
    ) <= 12,
    "is_open_voiced": lambda fs: _val(fs, "voicing.register_span").get("span_semitones", 0) >= 19,
    "spans_wide_register": lambda fs: _val(fs, "voicing.register_span").get(
        "span_semitones", 0
    ) >= 24,
    "has_authentic_cadence": lambda fs: _any_of(fs, "harmony.cadence", "authentic"),
    "has_plagal_cadence": lambda fs: _any_of(fs, "harmony.cadence", "plagal"),
    "has_backdoor_cadence": lambda fs: _any_of(fs, "harmony.cadence", "backdoor"),
    "moves_by_fourths": lambda fs: _any_of(fs, "harmony.root_motion", "fourth", "fifth"),
    "moves_by_step": lambda fs: _any_of(fs, "harmony.root_motion", "step"),
    "moves_by_thirds": lambda fs: _any_of(
        fs, "harmony.root_motion", "minor third", "major third"
    ),
    "moves_chromatically": lambda fs: _any_of(fs, "harmony.root_motion", "semitone"),
    "moves_by_tritone": lambda fs: _any_of(fs, "harmony.root_motion", "tritone"),
    "is_slow_harmony": lambda fs: _val(fs, "harmony.rhythm").get("mean_chord_ms", 0) >= 3000,
    "is_fast_harmony": lambda fs: 0 < _val(fs, "harmony.rhythm").get("mean_chord_ms", 0) <= 800,
    "is_looping": lambda fs: _val(fs, "perf.repetition").get("repeat_rate", 0) >= 0.6,
    "has_dynamic_range": lambda fs: _val(fs, "perf.velocity_stats").get("spread", 0) >= 20,
    "is_minor_key": lambda fs: (
        fs.get("harmony.key_estimate") is not None
        and "major" not in str(fs.get("harmony.key_estimate").value)
    ),
}
