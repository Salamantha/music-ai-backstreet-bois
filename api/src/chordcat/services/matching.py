"""Rank the musician pool against a freshly analysed take."""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from ..domain.events import HarmonicFeatures
from ..domain.profile import SimilarityBreakdown, TasteProfile, similarity


@dataclass(frozen=True, slots=True)
class Persona:
    id: str
    name: str
    instrument: str
    city: str
    bio: str
    signature_progression: str
    mode: str
    profile: TasteProfile
    top_artists: tuple[str, ...] = ()
    song_matches: int = 0


@dataclass(frozen=True, slots=True)
class Match:
    persona: Persona
    breakdown: SimilarityBreakdown
    percentile: float
    rationale: str


@dataclass(slots=True)
class PersonaPool:
    personas: tuple[Persona, ...] = ()
    #: Sorted pairwise similarities across the pool, used to turn a raw cosine
    #: into a percentile. A raw 0.8 is meaningless on its own; "closer than 94%
    #: of pairs in the pool" is not.
    calibration: tuple[float, ...] = ()

    @classmethod
    def load(cls, path: Path) -> PersonaPool:
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text())
        personas = []
        for raw in payload.get("personas", []):
            p = raw["profile"]
            personas.append(
                Persona(
                    id=raw["id"],
                    name=raw["name"],
                    instrument=raw["instrument"],
                    city=raw["city"],
                    bio=raw["bio"],
                    signature_progression=raw["signature_progression"],
                    mode=raw.get("mode", "major"),
                    profile=TasteProfile(
                        genre_weights=p["genre_weights"],
                        artist_weights=p["artist_weights"],
                        era_weights=p["era_weights"],
                        mood_weights=p["mood_weights"],
                        harmonic=HarmonicFeatures(**p["harmonic"]),
                    ),
                    top_artists=tuple(raw.get("top_artists", [])),
                    song_matches=raw.get("song_matches", 0),
                )
            )
        calibration = tuple(payload.get("calibration", {}).get("pairwise_similarities", []))
        return cls(tuple(personas), calibration)

    def percentile(self, score: float) -> float:
        if not self.calibration:
            return 0.0
        return bisect.bisect_left(self.calibration, score) / len(self.calibration)

    def rank(self, profile: TasteProfile, limit: int = 8) -> list[Match]:
        scored = [
            (p, similarity(profile, p.profile)) for p in self.personas
        ]
        scored.sort(key=lambda pair: (-pair[1].total, pair[0].name))
        return [
            Match(
                persona=p,
                breakdown=b,
                percentile=self.percentile(b.total),
                rationale=explain(b, p),
            )
            for p, b in scored[:limit]
        ]


def explain(b: SimilarityBreakdown, persona: Persona) -> str:
    """Compose the "why you two should jam" line from what actually overlaps.

    Assembled from the similarity components rather than generated, so it is
    always accurate, always free, and never invents a shared influence.
    """
    clauses: list[str] = []

    if b.shared_artists:
        names = _join(b.shared_artists[:3])
        clauses.append(f"you both turn up in {names}")
    if b.shared_genres:
        clauses.append(f"you overlap on {_join(b.shared_genres[:2])}")
    if b.shared_harmonic:
        clauses.append(f"you share a taste for {_join(b.shared_harmonic[:2])}")
    if b.shared_moods and len(clauses) < 3:
        clauses.append(f"both lean {_join(b.shared_moods[:2])}")

    if not clauses:
        return (
            f"{persona.name} writes around {persona.signature_progression}, which sits "
            f"a long way from yours -- that might be the interesting part."
        )

    lead = clauses[0][0].upper() + clauses[0][1:]
    rest = clauses[1:]
    body = lead if not rest else lead + ", and " + " and ".join(rest)
    return f"{body}. {persona.name} builds most things off {persona.signature_progression}."


def _join(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"
