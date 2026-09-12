"""Merge Hooktheory song hits from many n-gram queries into one ranked list."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .events import ArtistHit, SongHit
from .ngrams import Ngram, rarity

#: A window that opens the take is slightly better evidence of intent.
W_OPENS_TAKE = 1.15
#: One song matching in six sections should not outweigh six different songs.
MAX_SECTION_MULTIPLIER = 1.5
#: Prolific catalogue artists would otherwise win on volume alone.
ARTIST_VOLUME_EXPONENT = 0.5

_LEADING_THE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Fold an artist or song name for deduplication and cache keys."""
    folded = unicodedata.normalize("NFKD", name).casefold()
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _PUNCT.sub(" ", folded)
    folded = _LEADING_THE.sub("", folded.strip())
    return _WS.sub(" ", folded).strip()


@dataclass(frozen=True, slots=True)
class NgramResult:
    """What one Hooktheory ``trends/songs`` query returned."""

    ngram: Ngram
    songs: tuple[SongHit, ...]
    #: Total hits the query is known to have, across all pages. Falls back to the
    #: number actually fetched when paging stopped early.
    total_hits: int = 0


#: A song that is entirely the played progression is worth several times one
#: that merely contains it. Bounded so coverage informs the ranking without
#: overwhelming progression rarity and length.
MAX_COVERAGE_MULTIPLIER = 4.0


def _coverage_multiplier(coverage: float | None) -> float:
    if coverage is None:
        return 1.0
    return 1.0 + (MAX_COVERAGE_MULTIPLIER - 1.0) * max(0.0, min(1.0, coverage))


def _section_multiplier(n_sections: int) -> float:
    """Bounded bonus for a song matching in several sections."""
    return min(MAX_SECTION_MULTIPLIER, 1.0 + 0.25 * (n_sections - 1))


def progression_coverage(
    song_chords: Sequence[str], pattern: Sequence[str]
) -> float:
    """How much of a song's progression the played pattern accounts for.

    A song whose whole progression *is* the pattern, looped, is a far better
    match than a song that merely contains it once among twenty other chords.
    Both score identically on "contains the progression", which is why an
    exact-match search alone ranks the obvious answer far down the list.

    Returns the fraction of the song's chords covered by occurrences of the
    pattern, in 0..1.
    """
    if not song_chords or not pattern:
        return 0.0
    n = len(pattern)
    if n > len(song_chords):
        return 0.0
    target = [c.casefold() for c in pattern]
    chords = [c.casefold() for c in song_chords]
    covered = 0
    i = 0
    while i <= len(chords) - n:
        if chords[i : i + n] == target:
            covered += n
            i += n
        else:
            i += 1
    return min(1.0, covered / len(chords))


def score_songs(
    results: Sequence[NgramResult],
    transition_prob: Mapping[tuple[str, ...], float] | None = None,
    coverage: Mapping[tuple[str, str], float] | None = None,
) -> tuple[SongHit, ...]:
    """Rank songs by how strongly the take's windows point at them.

    The `1 / (1 + log(total_hits))` term carries most of the weight: a match on a
    progression thousands of songs share is nearly worthless, while a match on a
    rare one is close to an identification.
    """
    scores: dict[tuple[str, str], float] = defaultdict(float)
    sections: dict[tuple[str, str], set[str]] = defaultdict(set)
    display: dict[tuple[str, str], SongHit] = {}
    matched: dict[tuple[str, str], set[str]] = defaultdict(set)

    for result in results:
        g = result.ngram
        if not result.songs:
            continue
        total = max(result.total_hits, len(result.songs))
        specificity = 1.0 / (1.0 + math.log(max(total, 1)))
        weight = (
            (g.n**1.5)
            * (W_OPENS_TAKE if g.opens_take else 1.0)
            * rarity(g, dict(transition_prob) if transition_prob else None)
            * g.fidelity
            * specificity
        )
        seen_this_ngram: set[tuple[str, str]] = set()
        for hit in result.songs:
            key = (normalize_name(hit.artist), normalize_name(hit.song))
            if key not in sections:
                display[key] = hit
            sections[key].add(hit.section)
            matched[key].add(g.cp)
            # Score each song once per window. Additional *sections* of the same
            # song are extra evidence, but applied as a bounded multiplier at
            # the end -- accumulating per section instead lets one song with six
            # matching sections outscore six different songs.
            if key not in seen_this_ngram:
                seen_this_ngram.add(key)
                scores[key] += weight

    out = [
        SongHit(
            artist=display[k].artist,
            song=display[k].song,
            section=", ".join(sorted(sections[k])),
            url=display[k].url,
            score=v
            * _section_multiplier(len(sections[k]))
            * _coverage_multiplier(coverage.get(k) if coverage else None),
            matched_ngrams=tuple(sorted(matched[k])),
        )
        for k, v in scores.items()
    ]
    out.sort(key=lambda s: (-s.score, normalize_name(s.artist), normalize_name(s.song)))
    return tuple(out)


def rollup_artists(
    songs: Sequence[SongHit],
    artist_document_frequency: Mapping[str, int] | None = None,
    corpus_size: int = 0,
) -> tuple[ArtistHit, ...]:
    """Aggregate song scores per artist.

    Two dampers: a sublinear volume term so a large catalogue cannot win by
    breadth, and an inverse-document-frequency term built from everything the
    shared cache has ever seen -- so the cross-user cache doubles as a corpus
    that makes ranking better over time.
    """
    grouped: dict[str, list[SongHit]] = defaultdict(list)
    for s in songs:
        grouped[normalize_name(s.artist)].append(s)

    hits: list[ArtistHit] = []
    for key, group in grouped.items():
        raw = sum(s.score for s in group) / (len(group) ** ARTIST_VOLUME_EXPONENT)
        if artist_document_frequency and corpus_size > 0:
            df = artist_document_frequency.get(key, 1)
            raw *= math.log(1 + corpus_size / max(df, 1))
        hits.append(
            ArtistHit(
                artist=group[0].artist,
                score=raw,
                songs=tuple(sorted({s.song for s in group})),
            )
        )
    hits.sort(key=lambda a: (-a.score, normalize_name(a.artist)))
    return tuple(hits)


def top_artist_names(artists: Iterable[ArtistHit], n: int = 5) -> tuple[str, ...]:
    return tuple(a.artist for a in list(artists)[:n])
