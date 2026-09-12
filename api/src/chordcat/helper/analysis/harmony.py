"""Harmonic facts, read off the domain analysis rather than recomputed."""

from __future__ import annotations

from collections import Counter

from ...domain.pitch import pc_name
from ..facts import Fact
from ..prepare import AnalysisInput
from . import register

INTERVAL_NAMES = {
    0: "repeat", 1: "semitone", 2: "step", 3: "minor third", 4: "major third",
    5: "fourth", 6: "tritone", 7: "fifth", 8: "minor sixth", 9: "major sixth",
    10: "minor seventh", 11: "major seventh",
}

_SUFFIX = {
    "major": "", "minor": "m", "dim": "dim", "aug": "aug",
    "dom7": "7", "maj7": "maj7", "min7": "m7", "m7b5": "m7b5",
    "dim7": "dim7", "minmaj7": "mMaj7", "7sus4": "7sus4",
    "sus2": "sus2", "sus4": "sus4",
}


def _symbol(root_pc: int, quality: str) -> str:
    return f"{pc_name(root_pc)}{_SUFFIX.get(quality, quality)}"


@register
def key_estimate(inp: AnalysisInput) -> list[Fact]:
    if not inp.chords:
        return []
    k = inp.key
    return [
        Fact(
            id="harmony.key_estimate#0",
            kind="harmony.key_estimate",
            value=f"{pc_name(k.key.tonic_pc)} {k.key.mode}",
            confidence=k.confidence,
            n_observations=len(inp.chords),
        )
    ]


@register
def chords(inp: AnalysisInput) -> list[Fact]:
    return [
        Fact(
            id=f"harmony.chord#{i}",
            kind="harmony.chord",
            value=_symbol(c.best.root_pc, c.best.quality),
            confidence=min(c.best.score, 1.0),
            evidence=(i,),
            n_observations=1,
        )
        for i, c in enumerate(inp.chords)
    ]


@register
def quality_counts(inp: AnalysisInput) -> list[Fact]:
    if not inp.chords:
        return []
    counts = Counter(c.best.quality for c in inp.chords)
    return [
        Fact(
            id="harmony.quality_counts#0",
            kind="harmony.quality_counts",
            value=dict(counts),
            n_observations=len(inp.chords),
        )
    ]


@register
def extensions(inp: AnalysisInput) -> list[Fact]:
    sevenths = [i for i, c in enumerate(inp.chords) if c.best.is_seventh]
    if not sevenths:
        return []
    return [
        Fact(
            id="harmony.extensions#0",
            kind="harmony.extensions",
            value={"sevenths": len(sevenths), "of": len(inp.chords)},
            evidence=tuple(sevenths),
            n_observations=len(sevenths),
        )
    ]


@register
def root_motion(inp: AnalysisInput) -> list[Fact]:
    if len(inp.chords) < 2:
        return []
    moves = Counter(
        INTERVAL_NAMES[(b.best.root_pc - a.best.root_pc) % 12]
        for a, b in zip(inp.chords, inp.chords[1:])
    )
    return [
        Fact(
            id="harmony.root_motion#0",
            kind="harmony.root_motion",
            value=dict(moves),
            n_observations=len(inp.chords) - 1,
        )
    ]


@register
def cadences(inp: AnalysisInput) -> list[Fact]:
    """Named landings, relative to the detected key."""
    if len(inp.chords) < 2:
        return []
    tonic = inp.key.key.tonic_pc
    named = {
        (tonic + 7) % 12: "authentic",
        (tonic + 5) % 12: "plagal",
        (tonic + 10) % 12: "backdoor",
    }
    found: Counter[str] = Counter()
    where: list[int] = []
    for i, (a, b) in enumerate(zip(inp.chords, inp.chords[1:])):
        if b.best.root_pc == tonic and a.best.root_pc in named:
            found[named[a.best.root_pc]] += 1
            where.append(i)
    if not found:
        return []
    return [
        Fact(
            id="harmony.cadence#0",
            kind="harmony.cadence",
            value=dict(found),
            evidence=tuple(where),
            n_observations=sum(found.values()),
        )
    ]


@register
def rhythm(inp: AnalysisInput) -> list[Fact]:
    if not inp.chords:
        return []
    durations = [c.duration_ms for c in inp.chords]
    mean = sum(durations) / len(durations)
    return [
        Fact(
            id="harmony.rhythm#0",
            kind="harmony.rhythm",
            value={
                "mean_chord_ms": round(mean, 1),
                # Carried explicitly so the phrasing layer can say "seconds"
                # without deriving a number the validator has never seen.
                "mean_chord_s": round(mean / 1000, 1),
                "chords": len(durations),
            },
            n_observations=len(durations),
        )
    ]
