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
        personas = tuple(persona_from_dict(raw) for raw in payload.get("personas", []))
        calibration = tuple(payload.get("calibration", {}).get("pairwise_similarities", []))
        return cls(personas, calibration)

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


#: Mode prefixes a cp token can carry. The letter is a key-flavour marker, not
#: part of the number, so it is stripped for display and reported once.
_CP_PREFIXES = ("b", "B", "D", "Y", "L", "M", "C")


def spell_progression(cp: str) -> str:
    """A cp string as something a beginner can read aloud.

    ``1,5,6,4`` becomes "1-5-6-4"; ``B1,B6,B3,B7`` becomes "minor 1-6-3-7".
    The raw tokens are Hooktheory's internal spelling and mean nothing to
    someone who has not read its docs.
    """
    degrees: list[str] = []
    minorish = False
    for token in cp.split(","):
        token = token.strip()
        if not token:
            continue
        if token[0] in _CP_PREFIXES:
            minorish = True
            token = token[1:]
        degrees.append(token)
    if not degrees:
        return ""
    shape = "\u2013".join(degrees)
    return f"minor {shape}" if minorish else shape


def persona_from_dict(raw: dict) -> Persona:
    """Build a Persona from either a seed-file entry or a room-table row.

    Both carry the same `profile` shape; rows identify themselves by
    `client_id` and usually have no bio.
    """
    p = raw["profile"]
    return Persona(
        id=raw.get("id") or raw["client_id"],
        name=raw["name"],
        instrument=raw.get("instrument") or "",
        city=raw.get("city") or "",
        bio=raw.get("bio") or "",
        signature_progression=raw.get("signature_progression") or "",
        mode=raw.get("mode") or "major",
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


def profile_to_dict(profile: TasteProfile) -> dict:
    """The persona-shaped JSON stored in the room table."""
    h = profile.harmonic
    return {
        "genre_weights": dict(profile.genre_weights),
        "artist_weights": dict(profile.artist_weights),
        "era_weights": dict(profile.era_weights),
        "mood_weights": dict(profile.mood_weights),
        "harmonic": {
            "modal_usage": dict(h.modal_usage),
            "seventh_density": h.seventh_density,
            "borrowed_rate": h.borrowed_rate,
            "mean_progression_rarity": h.mean_progression_rarity,
            "cadence_profile": dict(h.cadence_profile),
            "key_spread": h.key_spread,
            "chord_variety": h.chord_variety,
            "mean_chord_duration_s": h.mean_chord_duration_s,
        },
    }


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
            f"{persona.name} writes around a {spell_progression(persona.signature_progression)} "
            f"progression, a long way from yours -- that might be the interesting part."
        )

    lead = clauses[0][0].upper() + clauses[0][1:]
    rest = clauses[1:]
    body = lead if not rest else lead + ", and " + " and ".join(rest)
    return (
        f"{body}. {persona.name} builds most things off a "
        f"{spell_progression(persona.signature_progression)} progression."
    )


def _join(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"
