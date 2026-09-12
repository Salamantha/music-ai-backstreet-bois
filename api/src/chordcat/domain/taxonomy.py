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


#: Hooktheory labels songs with its own genre vocabulary. Map it onto ours so
#: the two sources contribute to the same vector rather than fragmenting it.
#: Anything unmapped is dropped by `clean_genres`, which is the intended
#: behaviour -- an unrecognised label must never reach the matching vector.
HOOKTHEORY_GENRE_MAP: Final[dict[str, tuple[str, ...]]] = {
    "rock": ("rock",),
    "alternative": ("alternative",),
    "indie": ("indie rock",),
    "pop": ("pop",),
    "punk": ("punk",),
    "metal": ("metal",),
    "blues": ("blues",),
    "jazz": ("jazz",),
    "folk": ("folk",),
    "country": ("country",),
    "world": ("world",),
    "latin": ("latin",),
    "reggae": ("reggae",),
    "electronic": ("electronic",),
    "dance": ("electronic",),
    "house": ("house",),
    "techno": ("techno",),
    "ambient": ("ambient",),
    "hip-hop/rap": ("hip hop", "rap"),
    "hip hop": ("hip hop",),
    "rap": ("rap",),
    "r & b": ("r&b",),
    "r&b": ("r&b",),
    "soul": ("soul",),
    "funk": ("funk",),
    "gospel": ("gospel",),
    "classical": ("classical",),
    "soundtrack": ("film score",),
    "video game": ("video game",),
    "anime": ("anime",),
    "disney": ("musical theatre",),
    "singer-songwriter": ("singer-songwriter",),
    "vocal": (),
    "new age": ("ambient",),
}


def map_hooktheory_genres(labels: object) -> tuple[str, ...]:
    """Translate Hooktheory genre labels into this project's closed taxonomy."""
    if not isinstance(labels, (list, tuple)):
        return ()
    out: list[str] = []
    for label in labels:
        if not isinstance(label, str):
            continue
        for mapped in HOOKTHEORY_GENRE_MAP.get(label.strip().casefold(), ()):
            if mapped in GENRES and mapped not in out:
                out.append(mapped)
    return tuple(out)


def selectable_genres() -> tuple[str, ...]:
    """Genres a result can actually carry, for an up-front chooser.

    Only the taxonomy entries something in the data can map onto. Offering the
    full vocabulary would list genres no song will ever be labelled with, so
    picking one would silently return nothing.
    """
    out: list[str] = []
    for mapped in HOOKTHEORY_GENRE_MAP.values():
        for genre in mapped:
            if genre in GENRES and genre not in out:
                out.append(genre)
    return tuple(sorted(out))
