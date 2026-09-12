"""Closed vocabularies for taste profiling.

These are deliberately *closed*. An open genre vocabulary would let free text --
possibly originating in a public, user-editable song database -- reach the
matching vectors, where it would silently fragment the genre space and make
cosine similarity meaningless. Anything outside these sets is dropped and logged.

Bump ``TAXONOMY_VERSION`` on any edit: it is part of the genre cache key, so a
change here invalidates cached labels cleanly and nothing else does.
"""

from __future__ import annotations

from typing import Final

TAXONOMY_VERSION: Final[str] = "v1"

GENRES: Final[frozenset[str]] = frozenset({
    "rock", "classic rock", "indie rock", "alternative", "punk", "metal",
    "grunge", "emo", "post-rock", "psychedelic",
    "pop", "synthpop", "indie pop", "dream pop", "k-pop", "j-pop", "teen pop",
    "hip hop", "rap", "r&b", "soul", "funk", "motown", "disco",
    "electronic", "house", "techno", "ambient", "edm", "trance", "drum and bass",
    "jazz", "blues", "bossa nova", "swing",
    "folk", "singer-songwriter", "americana", "country", "bluegrass",
    "classical", "film score", "video game", "musical theatre",
    "reggae", "ska", "latin", "afrobeat", "world",
    "gospel", "christian", "anime", "lo-fi",
})

MOODS: Final[frozenset[str]] = frozenset({
    "melancholic", "euphoric", "aggressive", "dreamy", "nostalgic", "anthemic",
    "tender", "brooding", "playful", "triumphant", "restless", "hypnotic",
    "wistful", "defiant", "warm", "cinematic", "sparse", "lush", "driving", "eerie",
})

ERAS: Final[tuple[str, ...]] = (
    "pre-1970", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s", "unknown",
)


def clean_genres(values: object) -> tuple[str, ...]:
    """Keep only recognised genres, deduplicated, order preserved."""
    return _clean(values, GENRES)


def clean_moods(values: object) -> tuple[str, ...]:
    return _clean(values, MOODS)


def clean_era(value: object) -> str:
    return value if isinstance(value, str) and value in ERAS else "unknown"


def _clean(values: object, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    seen: list[str] = []
    for v in values:
        if isinstance(v, str):
            key = v.strip().casefold()
            if key in allowed and key not in seen:
                seen.append(key)
    return tuple(seen)
