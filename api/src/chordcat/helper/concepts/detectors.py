"""Named predicates over a FactSet. YAML names one; this decides if it is lit.

Kept separate from the node data so the concept map stays editable by someone
who does not write Python.

Each detector also declares which fact kinds it reads, because "unlit" has two
very different meanings. If ``voicing.inversions`` says 0 of 19, the absence is
measured. If no ``harmony.cadence`` fact exists at all, nothing was measured and
the absence is merely unobserved -- and telling someone "you have not tried
landing" on that basis asserts something the truth layer never established.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..facts import FactSet


@dataclass(frozen=True, slots=True)
class Detector:
    #: Fact kinds this predicate consults.
    reads: tuple[str, ...]
    predicate: Callable[[FactSet], bool]

    def __call__(self, facts: FactSet) -> bool:
        return self.predicate(facts)

    def measured(self, facts: FactSet) -> bool:
        """True when every fact this reads is actually present."""
        return all(facts.get(kind) is not None for kind in self.reads)


def _val(fs: FactSet, kind: str) -> dict:
    fact = fs.get(kind)
    return fact.value if fact is not None and isinstance(fact.value, dict) else {}


def _any_of(fs: FactSet, kind: str, *names: str) -> bool:
    value = _val(fs, kind)
    return any(value.get(n, 0) > 0 for n in names)


def _span(fs: FactSet) -> int:
    return _val(fs, "voicing.register_span").get("span_semitones", 0)


def _mean_chord_ms(fs: FactSet) -> float:
    return _val(fs, "harmony.rhythm").get("mean_chord_ms", 0)


DETECTORS: dict[str, Detector] = {
    # The root. Note this is *not* "plays three-note chords": the ChordCat
    # voices five-note extended harmony, so a triad-only predicate leaves the
    # root of the map unlit on real hardware and strands everything behind it.
    "has_chords": Detector(
        ("harmony.chord",), lambda fs: bool(fs.by_kind("harmony.chord"))
    ),
    "has_sevenths": Detector(
        ("harmony.extensions",),
        lambda fs: _val(fs, "harmony.extensions").get("sevenths", 0) > 0,
    ),
    "has_extended_voicings": Detector(
        ("voicing.notes_per_chord",),
        lambda fs: _val(fs, "voicing.notes_per_chord").get("max", 0) >= 5,
    ),
    "has_sus": Detector(
        ("harmony.quality_counts",),
        lambda fs: _any_of(fs, "harmony.quality_counts", "sus2", "sus4", "7sus4"),
    ),
    "has_inversions": Detector(
        ("voicing.inversions",),
        lambda fs: _val(fs, "voicing.inversions").get("inverted", 0) > 0,
    ),
    "is_close_voiced": Detector(
        ("voicing.register_span",), lambda fs: 0 < _span(fs) <= 12
    ),
    "is_open_voiced": Detector(("voicing.register_span",), lambda fs: _span(fs) >= 19),
    "spans_wide_register": Detector(
        ("voicing.register_span",), lambda fs: _span(fs) >= 24
    ),
    "has_authentic_cadence": Detector(
        ("harmony.cadence",), lambda fs: _any_of(fs, "harmony.cadence", "authentic")
    ),
    "has_plagal_cadence": Detector(
        ("harmony.cadence",), lambda fs: _any_of(fs, "harmony.cadence", "plagal")
    ),
    "has_backdoor_cadence": Detector(
        ("harmony.cadence",), lambda fs: _any_of(fs, "harmony.cadence", "backdoor")
    ),
    "moves_by_fourths": Detector(
        ("harmony.root_motion",),
        lambda fs: _any_of(fs, "harmony.root_motion", "fourth", "fifth"),
    ),
    "moves_by_step": Detector(
        ("harmony.root_motion",), lambda fs: _any_of(fs, "harmony.root_motion", "step")
    ),
    "moves_by_thirds": Detector(
        ("harmony.root_motion",),
        lambda fs: _any_of(fs, "harmony.root_motion", "minor third", "major third"),
    ),
    "moves_chromatically": Detector(
        ("harmony.root_motion",),
        lambda fs: _any_of(fs, "harmony.root_motion", "semitone"),
    ),
    "moves_by_tritone": Detector(
        ("harmony.root_motion",),
        lambda fs: _any_of(fs, "harmony.root_motion", "tritone"),
    ),
    "is_slow_harmony": Detector(
        ("harmony.rhythm",), lambda fs: _mean_chord_ms(fs) >= 3000
    ),
    "is_fast_harmony": Detector(
        ("harmony.rhythm",), lambda fs: 0 < _mean_chord_ms(fs) <= 800
    ),
    "is_looping": Detector(
        ("perf.repetition",),
        lambda fs: _val(fs, "perf.repetition").get("repeat_rate", 0) >= 0.6,
    ),
    "has_dynamic_range": Detector(
        ("perf.velocity_stats",),
        lambda fs: _val(fs, "perf.velocity_stats").get("spread", 0) >= 20,
    ),
    "is_minor_key": Detector(
        ("harmony.key_estimate",),
        lambda fs: (
            fs.get("harmony.key_estimate") is not None
            and "major" not in str(fs.get("harmony.key_estimate").value)
        ),
    ),
}
