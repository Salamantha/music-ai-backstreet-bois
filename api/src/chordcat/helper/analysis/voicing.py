"""How the notes are laid out, as opposed to which notes they are."""

from __future__ import annotations

from collections import Counter

from ..facts import Fact
from ..prepare import AnalysisInput
from . import register


@register
def register_span(inp: AnalysisInput) -> list[Fact]:
    pitches = [p for c in inp.chords for p in c.event.pitches]
    if not pitches:
        return []
    return [
        Fact(
            id="voicing.register_span#0",
            kind="voicing.register_span",
            value={
                "span_semitones": max(pitches) - min(pitches),
                "lowest": min(pitches),
                "highest": max(pitches),
            },
            n_observations=len(inp.chords),
        )
    ]


@register
def inversions(inp: AnalysisInput) -> list[Fact]:
    if not inp.chords:
        return []
    counts = Counter(
        "root_position" if c.best.inversion == 0 else "inverted" for c in inp.chords
    )
    where = tuple(i for i, c in enumerate(inp.chords) if c.best.inversion != 0)
    return [
        Fact(
            id="voicing.inversions#0",
            kind="voicing.inversions",
            value={
                "root_position": counts["root_position"],
                "inverted": counts["inverted"],
            },
            evidence=where,
            n_observations=len(inp.chords),
        )
    ]


@register
def notes_per_chord(inp: AnalysisInput) -> list[Fact]:
    if not inp.chords:
        return []
    sizes = [len(c.event.pcs) for c in inp.chords]
    return [
        Fact(
            id="voicing.notes_per_chord#0",
            kind="voicing.notes_per_chord",
            value={"mean": round(sum(sizes) / len(sizes), 2), "max": max(sizes)},
            n_observations=len(sizes),
        )
    ]
