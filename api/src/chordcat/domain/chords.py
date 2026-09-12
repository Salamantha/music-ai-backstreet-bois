"""Identify the harmony in a :class:`ChordEvent`.

Template matching over 18 chord qualities x 12 roots. 9ths, 11ths and 13ths are
deliberately *not* separate templates: they reduce to the underlying seventh with
the colour tone recorded in ``extensions``. That keeps the search at 216
candidates and matches Hooktheory's vocabulary, which has no 9ths at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from .events import ChordCandidate, ChordEvent, IdentifiedChord, Key
from .pitch import scale_pcs

#: quality -> semitone intervals above the root.
TEMPLATES: Final[dict[str, tuple[int, ...]]] = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "dom7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "minmaj7": (0, 3, 7, 11),
    "7sus4": (0, 5, 7, 10),
    "maj6": (0, 4, 7, 9),
    "min6": (0, 3, 7, 9),
    "add9": (0, 2, 4, 7),
    "madd9": (0, 2, 3, 7),
}

#: Tones the chord cannot be identified without. The fifth is never essential --
#: rootless and fifthless voicings are entirely normal, especially from a
#: chord-voicing device that spreads notes across octaves.
ESSENTIAL: Final[dict[str, tuple[int, ...]]] = {
    q: tuple(i for i in ivs if i in (0, 2, 3, 4, 5, 10, 11) and i != 7)
    for q, ivs in TEMPLATES.items()
}

#: Weight of each interval as *evidence*. The fifth is the least informative tone
#: (shared by maj/min/sus/dom/maj7/...), so it is discounted.
TONE_WEIGHT: Final[dict[int, float]] = {
    0: 1.30,   # root
    3: 1.25, 4: 1.25,   # third
    2: 1.20, 5: 1.20,   # sus2 / sus4
    10: 1.10, 11: 1.10,  # seventh
    9: 1.00,   # sixth
    6: 1.05, 8: 1.05,   # b5 / #5
    7: 0.80,   # fifth
}

ESSENTIAL_WEIGHT: Final[dict[int, float]] = {
    0: 1.5, 3: 1.2, 4: 1.2, 2: 1.1, 5: 1.1, 10: 0.9, 11: 0.9, 6: 0.9, 9: 0.6,
}

#: Priors exist only to break the structural ties enumerated in the module docs;
#: they are never large enough to overturn real evidence.
PRIOR: Final[dict[str, float]] = {
    "maj": 0.30, "min": 0.28, "dom7": 0.20, "min7": 0.18, "maj7": 0.15,
    "sus4": 0.05, "maj6": 0.05, "sus2": 0.00, "dim": 0.00, "m7b5": 0.00,
    "7sus4": 0.00, "min6": 0.00, "dim7": -0.05, "aug": -0.10,
    "add9": -0.15, "madd9": -0.15, "minmaj7": -0.15,
}

#: Extra pitch classes at these intervals are colour tones, not errors.
_COLOUR_INTERVALS: Final[frozenset[int]] = frozenset({2, 5, 9})
_EXTENSION_NAME: Final[dict[int, str]] = {2: "9", 5: "11", 9: "13"}

#: Qualities whose interval set is rotationally symmetric, so every rotation
#: scores identically and the root must be chosen by an explicit rule.
_SYMMETRIC: Final[frozenset[str]] = frozenset({"dim7", "aug"})


@dataclass(frozen=True, slots=True)
class ChordConfig:
    miss_penalty: float = 1.0
    extra_penalty: float = 0.7
    colour_discount: float = 0.35
    tie_epsilon: float = 0.15
    top_n: int = 3


def _inversion_of(root_pc: int, quality: str, bass_pc: int) -> tuple[int, int | None]:
    """Return ``(inversion, slash_bass_pc)`` for a bass note under a chord."""
    intervals = TEMPLATES[quality]
    rel = (bass_pc - root_pc) % 12
    if rel in intervals:
        return intervals.index(rel), None
    return 0, bass_pc


def _score(
    root_pc: int,
    quality: str,
    weights: dict[int, float],
    cfg: ChordConfig,
) -> tuple[float, tuple[str, ...]]:
    intervals = TEMPLATES[quality]
    template_pcs = {(root_pc + i) % 12: i for i in intervals}
    observed = set(weights)

    score = 0.0
    for p, interval in template_pcs.items():
        if p in observed:
            score += weights[p] * TONE_WEIGHT.get(interval, 1.0)

    for interval in ESSENTIAL[quality]:
        if (root_pc + interval) % 12 not in observed:
            score -= cfg.miss_penalty * ESSENTIAL_WEIGHT.get(interval, 1.0)

    extensions: list[str] = []
    for p in observed - set(template_pcs):
        rel = (p - root_pc) % 12
        if rel in _COLOUR_INTERVALS:
            score -= cfg.extra_penalty * weights[p] * cfg.colour_discount
            extensions.append(_EXTENSION_NAME[rel])
        else:
            score -= cfg.extra_penalty * weights[p]

    return score + PRIOR[quality], tuple(sorted(extensions))


def _resolve_symmetric_root(
    quality: str, roots: Sequence[int], bass_pc: int, key: Key | None
) -> int:
    """Pick the root of a rotationally symmetric chord.

    Diminished sevenths have four equally valid roots and augmented triads three;
    every rotation scores identically, so without an explicit rule the answer
    would be an accident of iteration order. Prefer the root that acts as a
    leading tone into a scale degree of the current key; otherwise use the bass.
    """
    if key is not None:
        in_key = scale_pcs(key.tonic_pc, key.mode)
        leading = [r for r in roots if (r + 1) % 12 in in_key]
        if leading:
            return min(leading, key=lambda r: (r != bass_pc, r))
    return bass_pc if bass_pc in roots else min(roots)


def identify_chord(
    event: ChordEvent,
    cfg: ChordConfig = ChordConfig(),
    key: Key | None = None,
) -> tuple[ChordCandidate, ...]:
    """Return the top candidate readings of ``event``, best first.

    Pass ``key=None`` on the first pass (before key detection), then re-run with
    the detected key so the diatonic tie-break can resolve ambiguities such as
    Em vs G6. Both passes are pure and cheap.
    """
    weights = event.weights()
    if not weights:
        return ()

    diatonic = scale_pcs(key.tonic_pc, key.mode) if key is not None else frozenset()
    scored: list[ChordCandidate] = []

    for quality in TEMPLATES:
        for root_pc in range(12):
            value, extensions = _score(root_pc, quality, weights, cfg)
            inversion, slash = _inversion_of(root_pc, quality, event.bass_pc)
            scored.append(
                ChordCandidate(
                    root_pc=root_pc,
                    quality=quality,
                    inversion=inversion,
                    bass_pc=event.bass_pc,
                    score=value,
                    extensions=extensions,
                    slash_bass_pc=slash,
                )
            )

    scored = _collapse_symmetric(scored, event.bass_pc, key)

    best = max(c.score for c in scored)
    near = [c for c in scored if c.score >= best - cfg.tie_epsilon]
    # Candidates within `tie_epsilon` of the best are treated as genuinely tied on
    # evidence, and separated by musical preference rather than by score noise.
    # This is what makes {C,E,G,A} over a C bass read as C6 rather than Am7/C.
    near.sort(
        key=lambda c: (
            c.root_pc != c.bass_pc,               # prefer root position
            c.root_pc not in diatonic,            # prefer diatonic roots (pass 2)
            len(TEMPLATES[c.quality]),            # Occam: fewer template tones
            -c.score,
            c.root_pc,                            # deterministic floor
        )
    )
    rest = sorted(
        (c for c in scored if c.score < best - cfg.tie_epsilon),
        key=lambda c: (-c.score, c.root_pc),
    )
    return tuple((near + rest)[: cfg.top_n])


def _collapse_symmetric(
    scored: list[ChordCandidate], bass_pc: int, key: Key | None
) -> list[ChordCandidate]:
    """Keep one canonical rotation of each symmetric chord."""
    out: list[ChordCandidate] = []
    by_quality: dict[str, list[ChordCandidate]] = {}
    for c in scored:
        if c.quality in _SYMMETRIC:
            by_quality.setdefault(c.quality, []).append(c)
        else:
            out.append(c)

    for quality, group in by_quality.items():
        best = max(c.score for c in group)
        tied = [c for c in group if abs(c.score - best) < 1e-9]
        chosen_root = _resolve_symmetric_root(
            quality, [c.root_pc for c in tied], bass_pc, key
        )
        keep = next(c for c in tied if c.root_pc == chosen_root)
        out.append(keep)
        out.extend(c for c in group if abs(c.score - best) >= 1e-9)
    return out


def identify_all(
    events: Sequence[ChordEvent],
    cfg: ChordConfig = ChordConfig(),
    key: Key | None = None,
) -> tuple[IdentifiedChord, ...]:
    return tuple(
        IdentifiedChord(event=e, candidates=identify_chord(e, cfg, key))
        for e in events
        if identify_chord(e, cfg, key)
    )


def merge_identified(
    chords: Sequence[IdentifiedChord],
    min_chord_dur_ms: float = 120.0,
    jaccard_same: float = 0.75,
) -> tuple[IdentifiedChord, ...]:
    """Collapse adjacent events that are the same harmony re-voiced.

    A quality change is *never* merged away: C -> Cmaj7 sits at Jaccard 0.75 but
    is a genuine chord change. An inversion change only counts as a new chord if
    the new bass persists -- otherwise a walking bass under a held triad would
    fragment the whole take.
    """
    if not chords:
        return ()

    merged: list[IdentifiedChord] = [chords[0]]
    for cur in chords[1:]:
        prev = merged[-1]
        a, b = prev.best, cur.best
        same_identity = (a.root_pc, a.quality) == (b.root_pc, b.quality)
        pcs_a, pcs_b = prev.event.pcs, cur.event.pcs
        jac = len(pcs_a & pcs_b) / max(len(pcs_a | pcs_b), 1)

        should_merge = (
            (pcs_a == pcs_b)
            or (pcs_b <= pcs_a and same_identity)
            or (cur.duration_ms < min_chord_dur_ms and same_identity)
            or (jac >= jaccard_same and same_identity)
        )
        # A bass change that does not last is not a new chord.
        if (
            not should_merge
            and same_identity
            and a.inversion != b.inversion
            and cur.duration_ms < min_chord_dur_ms
        ):
            should_merge = True

        if should_merge:
            merged[-1] = _extend(prev, cur)
        else:
            merged.append(cur)

    return tuple(merged)


def _extend(prev: IdentifiedChord, cur: IdentifiedChord) -> IdentifiedChord:
    """Stretch ``prev`` to cover ``cur``, keeping the longer event's identity."""
    e, f = prev.event, cur.event
    keep = prev if prev.duration_ms >= cur.duration_ms else cur
    widened = ChordEvent(
        start_ms=e.start_ms,
        end_ms=f.end_ms,
        pitches=tuple(sorted(set(e.pitches) | set(f.pitches))),
        bass_pitch=min(e.bass_pitch, f.bass_pitch),
        onset_pitches=e.onset_pitches,
        pc_weights=e.pc_weights,
        velocity_mean=(e.velocity_mean + f.velocity_mean) / 2,
    )
    return IdentifiedChord(event=widened, candidates=keep.candidates)
