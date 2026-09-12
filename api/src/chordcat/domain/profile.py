"""Build a musician's taste profile and compare two of them.

The important design property here is that :class:`HarmonicFeatures` is derived
entirely from our own analysis of what was played. It needs no Hooktheory match
and no LLM. Given that Hooktheory only matches exact contiguous progressions --
so a real fraction of takes return *no* song hits at all -- this is what keeps
the matching experience alive rather than showing the user an empty page.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .events import HarmonicFeatures, IdentifiedChord, Key
from .ngrams import Ngram, rarity
from .pitch import MODES, scale_pcs
from .taxonomy import ERAS

#: Component weights of the fused similarity score.
W_GENRE = 0.45
W_ARTIST = 0.20
W_HARMONIC = 0.15
W_MOOD = 0.10
W_ERA = 0.10

_SEVENTHS = frozenset({"dom7", "maj7", "min7", "m7b5", "dim7", "minmaj7", "7sus4"})


@dataclass(slots=True)
class TasteProfile:
    genre_weights: dict[str, float] = field(default_factory=dict)
    artist_weights: dict[str, float] = field(default_factory=dict)
    era_weights: dict[str, float] = field(default_factory=dict)
    mood_weights: dict[str, float] = field(default_factory=dict)
    harmonic: HarmonicFeatures = field(default_factory=HarmonicFeatures)
    #: Optional dense text embedding of the taste document, when available.
    embedding: tuple[float, ...] = ()

    def taste_document(self) -> str:
        """Short natural-language summary, used for text embedding."""
        parts = [
            "genres: " + ", ".join(_top(self.genre_weights, 6)),
            "artists: " + ", ".join(_top(self.artist_weights, 8)),
            "moods: " + ", ".join(_top(self.mood_weights, 5)),
            "eras: " + ", ".join(_top(self.era_weights, 3)),
        ]
        return " | ".join(p for p in parts if not p.endswith(": "))


def _top(weights: Mapping[str, float], n: int) -> list[str]:
    return [k for k, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:n]]


def _l2(weights: Mapping[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in weights.values()))
    return {k: v / norm for k, v in weights.items()} if norm else dict(weights)


def cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def jaccard_overlap(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Weighted Jaccard. An exactly shared artist is strong, specific evidence.

    Plain cosine would treat two musicians who share nobody but sit in adjacent
    genres as similar; sharing an actual artist is a different, sharper signal.
    """
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    inter = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    union = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return inter / union if union else 0.0


def harmonic_features(
    chords: Sequence[IdentifiedChord],
    key: Key,
    ngrams: Sequence[Ngram] = (),
    transition_prob: Mapping[tuple[str, ...], float] | None = None,
) -> HarmonicFeatures:
    """Summarise *how* someone plays, independently of what they match."""
    if not chords:
        return HarmonicFeatures()

    total_dur = sum(max(c.duration_ms, 1.0) for c in chords)
    in_key = scale_pcs(key.tonic_pc, key.mode)

    sevenths = sum(
        max(c.duration_ms, 1.0) for c in chords if c.best.quality in _SEVENTHS
    )
    borrowed = sum(
        max(c.duration_ms, 1.0) for c in chords if c.best.root_pc not in in_key
    )

    # Cadences, as a share of all chord-to-chord moves.
    moves = Counter[str]()
    tonic, dominant = key.tonic_pc, (key.tonic_pc + 7) % 12
    subdominant, subtonic = (key.tonic_pc + 5) % 12, (key.tonic_pc + 10) % 12
    submediant = (key.tonic_pc + 9) % 12
    for a, b in zip(chords, chords[1:]):
        ra, rb = a.best.root_pc, b.best.root_pc
        if rb == tonic and ra == dominant:
            moves["authentic"] += 1
        elif rb == tonic and ra == subdominant:
            moves["plagal"] += 1
        elif rb == tonic and ra == subtonic:
            moves["backdoor"] += 1
        elif ra == dominant and rb == submediant:
            moves["deceptive"] += 1
    transitions = max(len(chords) - 1, 1)

    rarities = [rarity(g, dict(transition_prob) if transition_prob else None) for g in ngrams]

    pcs_used = {c.best.root_pc for c in chords}

    return HarmonicFeatures(
        modal_usage={m: 1.0 if m == key.mode else 0.0 for m in MODES},
        seventh_density=sevenths / total_dur,
        borrowed_rate=borrowed / total_dur,
        mean_progression_rarity=(sum(rarities) / len(rarities)) if rarities else 1.0,
        cadence_profile={k: v / transitions for k, v in moves.items()},
        key_spread=len(pcs_used) / 12,
        chord_variety=len({(c.best.root_pc, c.best.quality) for c in chords})
        / max(len(chords), 1),
        mean_chord_duration_s=total_dur / len(chords) / 1000,
    )


def harmonic_vector(h: HarmonicFeatures) -> dict[str, float]:
    """Flatten harmonic features into a comparable vector."""
    vec: dict[str, float] = {
        "seventh_density": h.seventh_density,
        "borrowed_rate": h.borrowed_rate,
        # Rarity is roughly 0.5..2.0; rescale so it cannot dominate the others.
        "rarity": (h.mean_progression_rarity - 0.5) / 1.5,
        "key_spread": h.key_spread,
        "chord_variety": h.chord_variety,
        "pace": min(h.mean_chord_duration_s / 4.0, 1.0),
    }
    for mode, v in h.modal_usage.items():
        vec[f"mode:{mode}"] = v
    for cadence, v in h.cadence_profile.items():
        vec[f"cadence:{cadence}"] = v
    return vec


def build_profile(
    genre_counts: Mapping[str, float],
    artist_counts: Mapping[str, float],
    era_counts: Mapping[str, float],
    mood_counts: Mapping[str, float],
    harmonic: HarmonicFeatures,
) -> TasteProfile:
    return TasteProfile(
        genre_weights=_l2(genre_counts),
        artist_weights=_l2(artist_counts),
        era_weights=_l2({e: era_counts.get(e, 0.0) for e in ERAS if era_counts.get(e)}),
        mood_weights=_l2(mood_counts),
        harmonic=harmonic,
    )


@dataclass(frozen=True, slots=True)
class SimilarityBreakdown:
    total: float
    genre: float
    artist: float
    harmonic: float
    mood: float
    era: float
    shared_artists: tuple[str, ...] = ()
    shared_genres: tuple[str, ...] = ()
    shared_moods: tuple[str, ...] = ()
    #: Harmonic traits both profiles score highly on.
    shared_harmonic: tuple[str, ...] = ()


def similarity(
    a: TasteProfile, b: TasteProfile, embedding_weight: float = 0.0
) -> SimilarityBreakdown:
    """Fused similarity, with the component scores kept for explanation.

    ``embedding_weight`` blends a dense text-embedding cosine into the genre
    term when both profiles carry an embedding. It is zero when
    sentence-transformers is not installed, which is the common case.
    """
    genre = cosine(a.genre_weights, b.genre_weights)
    if embedding_weight > 0 and a.embedding and b.embedding:
        dense = _dense_cosine(a.embedding, b.embedding)
        genre = (1 - embedding_weight) * genre + embedding_weight * dense

    artist = jaccard_overlap(a.artist_weights, b.artist_weights)
    harmonic = cosine(harmonic_vector(a.harmonic), harmonic_vector(b.harmonic))
    mood = cosine(a.mood_weights, b.mood_weights)
    era = cosine(a.era_weights, b.era_weights)

    total = (
        W_GENRE * genre
        + W_ARTIST * artist
        + W_HARMONIC * harmonic
        + W_MOOD * mood
        + W_ERA * era
    )

    return SimilarityBreakdown(
        total=total,
        genre=genre,
        artist=artist,
        harmonic=harmonic,
        mood=mood,
        era=era,
        shared_artists=_shared(a.artist_weights, b.artist_weights),
        shared_genres=_shared(a.genre_weights, b.genre_weights),
        shared_moods=_shared(a.mood_weights, b.mood_weights),
        shared_harmonic=_shared_harmonic(a.harmonic, b.harmonic),
    )


def _shared(a: Mapping[str, float], b: Mapping[str, float], n: int = 5) -> tuple[str, ...]:
    common = {k: min(a[k], b[k]) for k in set(a) & set(b)}
    return tuple(k for k, _ in sorted(common.items(), key=lambda kv: -kv[1])[:n])


_HARMONIC_LABELS = {
    "seventh_density": "seventh chords",
    "borrowed_rate": "borrowed chords",
    "rarity": "unusual progressions",
    "chord_variety": "harmonic variety",
    "cadence:authentic": "V-I cadences",
    "cadence:plagal": "plagal (IV-I) cadences",
    "cadence:backdoor": "backdoor (bVII-I) cadences",
    "cadence:deceptive": "deceptive cadences",
}


def _shared_harmonic(a: HarmonicFeatures, b: HarmonicFeatures) -> tuple[str, ...]:
    va, vb = harmonic_vector(a), harmonic_vector(b)
    out = [
        (label, min(va.get(k, 0.0), vb.get(k, 0.0)))
        for k, label in _HARMONIC_LABELS.items()
        if min(va.get(k, 0.0), vb.get(k, 0.0)) > 0.15
    ]
    modes = [
        m for m in MODES
        if a.modal_usage.get(m, 0) > 0.5 and b.modal_usage.get(m, 0) > 0.5
        and m not in ("major",)
    ]
    out.extend((f"{m} tonality", 1.0) for m in modes)
    return tuple(label for label, _ in sorted(out, key=lambda kv: -kv[1])[:3])


def _dense_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
