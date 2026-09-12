"""Spend a limited Hooktheory request budget as well as possible.

The account-wide limit is 10 requests per 10 seconds, shared by every user of
this server. So the job is not "query everything" but "query the dozen windows
most likely to identify this musician", stop as soon as the answer stops
changing, and never re-ask something the cache already knows.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..adapters.hooktheory import HooktheoryClient, rows_to_hits
from ..domain.events import ArtistHit, CpSequence, SongHit
from ..domain.ngrams import Ngram, NgramConfig, generate_ngrams, prioritize
from ..domain.ranking import NgramResult, rollup_artists, score_songs, top_artist_names

log = logging.getLogger(__name__)

PAGE_SIZE = 20
#: How many pages to fetch per window. Longer windows are rarer and more
#: identifying, so they justify more paging.
PAGES_BY_LENGTH = {2: 1, 3: 3, 4: 5, 5: 5}
#: Stop early once the top artists stop moving.
STABLE_ROUNDS_TO_STOP = 3
_TAG = re.compile(r"<[^>]+>")


def strip_html(raw: str) -> str:
    """`chord_HTML` comes back with markup, e.g. ``V<sup>6</sup>``."""
    return _TAG.sub("", raw).strip()


#: Below this many distinct songs, the primary query has not told us much and
#: it is worth spending more of the budget on narrower windows.
ESCALATE_BELOW_SONGS = 5


@dataclass(slots=True)
class SearchOutcome:
    songs: tuple[SongHit, ...] = ()
    artists: tuple[ArtistHit, ...] = ()
    results: tuple[NgramResult, ...] = ()
    ngrams: tuple[Ngram, ...] = ()
    requests_spent: int = 0
    queried: list[str] = field(default_factory=list)
    stopped_early: bool = False


async def build_transition_table(
    client: HooktheoryClient, sequences: Sequence[tuple[str, ...]]
) -> dict[tuple[str, ...], float]:
    """Look up transition probabilities from the (cached) global nodes tree.

    After `scripts/warm_nodes_tree.py` has run once these are all cache hits and
    cost nothing, which is the whole point: rarity scoring should not compete
    with song search for the live request budget.
    """
    table: dict[tuple[str, ...], float] = {}
    prefixes = {seq[:i] for seq in sequences for i in range(1, len(seq))}
    for prefix in sorted(prefixes, key=len):
        try:
            rows = await client.nodes(",".join(prefix) if prefix else None)
        except Exception as exc:  # noqa: BLE001 - rarity is an optimisation
            log.debug("nodes lookup failed for %s: %s", prefix, exc)
            continue
        for row in rows:
            child = str(row.get("child_path", ""))
            if not child:
                continue
            table[tuple(child.split(","))] = float(row.get("probability", 0.0))
    return table


async def search_progression(
    client: HooktheoryClient,
    sequence: CpSequence,
    *,
    budget: int = 1,
    fallback_budget: int = 8,
    ngram_cfg: NgramConfig = NgramConfig(),
    transition_prob: Mapping[tuple[str, ...], float] | None = None,
    artist_document_frequency: Mapping[str, int] | None = None,
    corpus_size: int = 0,
    progress: object = None,
) -> SearchOutcome:
    """Query the most informative windows until the budget or the answer runs out."""
    ngrams = generate_ngrams(sequence, ngram_cfg)
    if not ngrams:
        return SearchOutcome()

    ordered = prioritize(ngrams, dict(transition_prob) if transition_prob else None)

    results: list[NgramResult] = []
    queried: list[str] = []
    spent = 0
    stable = 0
    previous_top: tuple[str, ...] = ()
    stopped_early = False

    # The first query is the whole point: for a distinctive progression one GET
    # identifies the musician outright. Extra windows are an escalation path for
    # when that query returns little or nothing -- which happens as soon as a
    # take is longer than about four chords, because Hooktheory only matches
    # exact contiguous sequences.
    effective_budget = budget

    for ngram in ordered:
        if spent >= effective_budget:
            if (
                effective_budget < fallback_budget
                and len(score_songs(results, transition_prob)) < ESCALATE_BELOW_SONGS
            ):
                effective_budget = fallback_budget
                log.info(
                    "primary query yielded too little; escalating budget to %d",
                    fallback_budget,
                )
            else:
                break

        max_pages = PAGES_BY_LENGTH.get(ngram.n, 1)
        rows: list[dict] = []
        for page in range(1, max_pages + 1):
            if spent >= effective_budget:
                break
            page_rows = await client.songs(ngram.cp, page)
            spent += 1
            rows.extend(page_rows)
            if len(page_rows) < PAGE_SIZE:
                break  # short page means the end; never probe past it

        queried.append(ngram.cp)
        results.append(
            NgramResult(
                ngram=ngram, songs=rows_to_hits(rows), total_hits=max(len(rows), 0)
            )
        )
        if progress is not None and callable(progress):
            progress(ngram.cp, len(rows), spent, budget)

        songs = score_songs(results, transition_prob)
        artists = rollup_artists(songs, artist_document_frequency, corpus_size)
        top = top_artist_names(artists, 5)
        stable = stable + 1 if top and top == previous_top else 0
        previous_top = top
        if stable >= STABLE_ROUNDS_TO_STOP:
            stopped_early = True
            break

    songs = score_songs(results, transition_prob)
    artists = rollup_artists(songs, artist_document_frequency, corpus_size)
    return SearchOutcome(
        songs=songs,
        artists=artists,
        results=tuple(results),
        ngrams=tuple(ordered),
        requests_spent=spent,
        queried=queried,
        stopped_early=stopped_early,
    )
