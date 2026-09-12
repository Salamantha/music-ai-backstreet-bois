"""Orchestrate a full analysis: raw MIDI in, taste profile and matches out.

This is the only module that awaits. Everything it calls in `domain/` is a pure
function, which is what makes the whole pipeline reproducible from a recorded
note stream.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence

from ..adapters.genre_llm import GenreResolver
from ..adapters.hooktheory import HooktheoryClient
from ..adapters.theorytab import (
    TheoryTabClient,
    romans_to_chord_string,
    strip_modifiers,
)
from ..domain.chords import identify_all, merge_identified
from ..domain.cp import CpConfig, progression_to_cp
from ..domain.events import (
    CpSequence,
    SongHit as _SongHit,
    Hole,
    IdentifiedChord,
    Key,
    KeyEstimate,
    RawEvent,
    SongHit,
)
from ..domain.key import detect_key
from ..domain.pitch import parent_major_tonic
from ..domain.ngrams import NgramConfig
from ..domain.profile import TasteProfile, build_profile, harmonic_features
from ..domain.ranking import NgramResult, normalize_name, progression_coverage
from ..domain.taxonomy import map_hooktheory_genres
from ..domain.segment import SegmentConfig, events_from_raw
from ..domain.ranking import rollup_artists, score_songs
from .search import SearchOutcome, build_transition_table, search_progression

log = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalysisResult:
    chords: tuple[IdentifiedChord, ...] = ()
    key_estimate: KeyEstimate | None = None
    cp_sequence: CpSequence = ()
    search: SearchOutcome = field(default_factory=SearchOutcome)
    profile: TasteProfile = field(default_factory=TasteProfile)
    segmentation_mode: str = "onset"
    stuck_notes: int = 0
    unmapped: tuple[dict, ...] = ()
    diagnostics: dict = field(default_factory=dict)
    #: Genres Hooktheory itself assigns, keyed by normalised artist name. Better
    #: evidence than an LLM guess, and free with the TheoryTab result.
    source_genres: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def cp_string(self) -> str:
        return ",".join(
            t.root_position_token for t in self.cp_sequence if not isinstance(t, Hole)
        )


async def analyse(
    raw_events: Sequence[RawEvent],
    *,
    client: HooktheoryClient | None,
    genres: GenreResolver | None,
    theorytab: TheoryTabClient | None = None,
    key_override: Key | None = None,
    session_end_ms: float | None = None,
    budget: int = 12,
    segment_cfg: SegmentConfig = SegmentConfig(),
    cp_cfg: CpConfig = CpConfig(),
    ngram_cfg: NgramConfig = NgramConfig(),
    artist_document_frequency: dict[str, int] | None = None,
    corpus_size: int = 0,
    progress: object = None,
) -> AnalysisResult:
    """Run the full pipeline. Every external dependency is optional.

    With no Hooktheory client the result still carries chords, key, Roman
    numerals and harmonic features -- which is exactly the degraded mode a take
    with no song matches lands in anyway.
    """
    segmented = events_from_raw(raw_events, segment_cfg, session_end_ms=session_end_ms)
    diagnostics = {
        "raw_events": len(raw_events),
        "notes_paired": segmented.notes_paired,
        "clusters_found": segmented.clusters_found,
        "dropped_too_few_notes": segmented.dropped_too_few_notes,
        "max_simultaneous": segmented.max_simultaneous,
        "segments": len(segmented.events),
        "min_notes_for_chord": segment_cfg.min_notes_for_chord,
    }
    if not segmented.events:
        return AnalysisResult(
            segmentation_mode=segmented.mode, diagnostics=diagnostics
        )

    # Pass 1: identify without key context, so key detection is not circular.
    first_pass = merge_identified(
        identify_all(segmented.events), segment_cfg.min_chord_dur_ms,
        segment_cfg.jaccard_same,
    )
    estimate = detect_key(first_pass)
    if key_override is not None:
        estimate = KeyEstimate(
            key=key_override,
            confidence=1.0,
            alternatives=estimate.alternatives,
            method_scores=estimate.method_scores,
            source="user",
            modulation_suspected=estimate.modulation_suspected,
        )

    # Pass 2: re-identify with the key known, resolving diatonic ambiguities.
    chords = merge_identified(
        identify_all(tuple(c.event for c in first_pass), key=estimate.key),
        segment_cfg.min_chord_dur_ms,
        segment_cfg.jaccard_same,
    )
    sequence = progression_to_cp(chords, estimate.key, cp_cfg)
    # Keep the reading of the notes as first detected. The Trends search may
    # respell the progression into the parent major to find matches, but
    # TheoryTab indexes songs under their *own* modal analysis -- 505 is filed
    # as D dorian `i ii`, which the respelled `ii iii` would never find.
    detected_romans = [t.roman for t in sequence if not isinstance(t, Hole)]
    unmapped = tuple(
        {"index": h.chord_index, "label": h.label, "reason": h.reason}
        for h in sequence
        if isinstance(h, Hole) and h.label
    )

    outcome = SearchOutcome()
    transitions: dict[tuple[str, ...], float] = {}
    if client is not None:
        outcome, estimate, chords, sequence, transitions = await _search_with_key_retry(
            client=client,
            first_pass=first_pass,
            estimate=estimate,
            chords=chords,
            sequence=sequence,
            key_override=key_override,
            budget=budget,
            segment_cfg=segment_cfg,
            cp_cfg=cp_cfg,
            ngram_cfg=ngram_cfg,
            artist_document_frequency=artist_document_frequency,
            corpus_size=corpus_size,
            progress=progress,
        )
        unmapped = tuple(
            {"index": h.chord_index, "label": h.label, "reason": h.reason}
            for h in sequence
            if isinstance(h, Hole) and h.label
        )

    # Second source. The Trends index is a stale snapshot -- Arctic Monkeys'
    # "505" is in TheoryTab as D Dorian `i ii` but absent from every page of the
    # equivalent Trends query -- so search TheoryTab by roman numeral as well
    # and merge. `ignore_modifiers` is what makes this work for a chord-voicing
    # device: it matches `i ii` against a song whose chords are really i11/ii9.
    source_genres: dict[str, tuple[str, ...]] = {}
    if theorytab is not None:
        final_romans = [t.roman for t in sequence if not isinstance(t, Hole)]
        spellings: list[list[str]] = []
        for candidate in (detected_romans, final_romans):
            if candidate and candidate not in spellings:
                spellings.append(candidate)

        # Collect every spelling's hits before scoring. Merging and rescoring
        # once per spelling would discard the coverage measured on the previous
        # pass, which is what makes the obvious answer rank where it should.
        collected: list[tuple[object, list[str]]] = []
        seen_hits: set[tuple[str, str, str]] = set()
        queried_strings: list[str] = []
        for romans in spellings:
            chord_string = romans_to_chord_string(romans)
            if not chord_string:
                continue
            # Coverage has to compare like with like. The query is reduced to
            # plain triads so it matches Hooktheory's triadic analyses, so the
            # pattern used for coverage must be reduced the same way -- leaving
            # `ii7 iii7` here scores zero coverage against a song written `ii
            # iii`, and the match silently loses its ranking boost.
            pattern = chord_string.split()
            try:
                hits = await theorytab.search_all(chord_string, ignore_modifiers=True)
            except Exception as exc:  # noqa: BLE001 - a second source must not break the first
                log.warning("TheoryTab search failed (%s); continuing", exc)
                continue
            queried_strings.append(chord_string)
            for hit in hits:
                key = (hit.artist, hit.song, hit.section)
                if key in seen_hits:
                    continue
                seen_hits.add(key)
                collected.append((hit, pattern))

        if collected:
            outcome = _merge_theorytab(
                outcome, collected, transitions,
                artist_document_frequency, corpus_size, queried_strings,
            )
            for hit, _ in collected:
                mapped = map_hooktheory_genres(list(hit.genres))
                if mapped:
                    source_genres[normalize_name(hit.artist)] = mapped

    harmonic = harmonic_features(chords, estimate.key, outcome.ngrams, transitions)
    profile = await build_taste_profile(
        outcome.songs, harmonic, genres, source_genres=source_genres
    )

    return AnalysisResult(
        chords=chords,
        key_estimate=estimate,
        cp_sequence=sequence,
        search=outcome,
        profile=profile,
        segmentation_mode=segmented.mode,
        stuck_notes=segmented.stuck_notes,
        unmapped=unmapped,
        diagnostics={**diagnostics, "chords_identified": len(chords)},
        source_genres=source_genres,
    )


def _merge_theorytab(
    outcome: SearchOutcome,
    collected: Sequence[tuple[object, Sequence[str]]],
    transitions,
    artist_document_frequency,
    corpus_size: int,
    queried_strings: Sequence[str],
) -> SearchOutcome:
    """Fold TheoryTab results into the Trends results and rescore together."""
    from ..domain.ngrams import Ngram

    by_pattern: dict[tuple[str, ...], list] = {}
    coverage: dict[tuple[str, str], float] = {}

    for hit, romans in collected:
        pattern = tuple(romans)
        by_pattern.setdefault(pattern, []).append(
            _SongHit(
                artist=hit.artist,
                song=hit.song,
                section=hit.section or "",
                url=hit.url,
                video_url=hit.youtube_url,
            )
        )
        key = (normalize_name(hit.artist), normalize_name(hit.song))
        # Keep the best coverage across spellings and sections of a song.
        coverage[key] = max(
            coverage.get(key, 0.0), progression_coverage(hit.chords, romans)
        )

    results = list(outcome.results)
    for pattern, songs in by_pattern.items():
        results.append(
            NgramResult(
                Ngram(tokens=pattern, multiplicity=1, fidelity=1.0, opens_take=True),
                tuple(songs),
                total_hits=len(songs),
            )
        )

    scored = score_songs(tuple(results), transitions, coverage=coverage)
    return SearchOutcome(
        songs=scored,
        artists=rollup_artists(scored, artist_document_frequency, corpus_size),
        results=tuple(results),
        ngrams=outcome.ngrams,
        requests_spent=outcome.requests_spent,
        queried=[*outcome.queried, *(f"theorytab:{q}" for q in queried_strings)],
        stopped_early=outcome.stopped_early,
    )


async def build_taste_profile(
    songs: Sequence[SongHit],
    harmonic,
    genres: GenreResolver | None,
    source_genres: dict[str, tuple[str, ...]] | None = None,
) -> TasteProfile:
    """Roll matched songs up into genre / artist / era / mood weights."""
    artist_weights = Counter[str]()
    for hit in songs:
        artist_weights[hit.artist] += hit.score

    genre_weights = Counter[str]()
    era_weights = Counter[str]()
    mood_weights = Counter[str]()

    source_genres = source_genres or {}
    if artist_weights:
        labels = await genres.resolve(list(artist_weights)) if genres else {}
        for artist, weight in artist_weights.items():
            # Hooktheory's own label wins: it is authoritative for that song,
            # where our label file is a curated guess about the artist.
            known = source_genres.get(normalize_name(artist))
            if known:
                for g in known:
                    genre_weights[g] += weight
                continue
            profile = labels.get(normalize_name(artist))
            if profile is None or profile.unknown:
                # An unrecognised artist contributes nothing to genre -- lower
                # coverage beats confident wrongness -- but still counts as a
                # shared artist, which is high-precision evidence on its own.
                continue
            for g in profile.genres:
                genre_weights[g] += weight
            for m in profile.moods:
                mood_weights[m] += weight
            if profile.era != "unknown":
                era_weights[profile.era] += weight

    return build_profile(
        genre_counts=dict(genre_weights),
        artist_counts=dict(artist_weights),
        era_counts=dict(era_weights),
        mood_counts=dict(mood_weights),
        harmonic=harmonic,
    )


#: How many alternative keys to try before spending budget on narrower windows.
MAX_KEY_RETRIES = 2
#: Below this many songs the primary spelling has not told us much, so it is
#: worth also querying how the same chords read in the relative key.
MERGE_ALTERNATIVE_BELOW = 10


async def _search_with_key_retry(
    *,
    client: HooktheoryClient,
    first_pass: Sequence[IdentifiedChord],
    estimate: KeyEstimate,
    chords: tuple[IdentifiedChord, ...],
    sequence: CpSequence,
    key_override: Key | None,
    budget: int,
    segment_cfg: SegmentConfig,
    cp_cfg: CpConfig,
    ngram_cfg: NgramConfig,
    artist_document_frequency: dict[str, int] | None,
    corpus_size: int,
    progress: object,
):
    """Search, retrying under alternative keys before widening the window set.

    Relative major, minor and dorian readings of the same notes are genuinely
    ambiguous -- they share a pitch-class set, so no amount of analysis settles
    it from the notes alone. But `cp` is key-relative, so picking the wrong one
    produces a progression that matches *nothing*: the royal road played in C
    major is `4,5,3,6` with hundreds of matches, and read as A minor it becomes
    `B6,B7,B5,B1` with none.

    Hooktheory itself is the tie-breaker. Trying the top alternative costs one
    request; escalating to narrower windows under a wrong key costs eight and
    cannot succeed. So alternatives come first.
    """
    from ..domain.ngrams import generate_ngrams

    async def run(seq: CpSequence, request_budget: int):
        candidate = generate_ngrams(seq, ngram_cfg)
        if not candidate:
            return SearchOutcome(), {}
        table = await build_transition_table(client, [g.tokens for g in candidate])
        result = await search_progression(
            client,
            seq,
            budget=request_budget,
            fallback_budget=request_budget,  # no window escalation on this pass
            ngram_cfg=ngram_cfg,
            transition_prob=table,
            artist_document_frequency=artist_document_frequency,
            corpus_size=corpus_size,
            progress=progress,
        )
        return result, table

    outcome, transitions = await run(sequence, budget)
    if key_override is not None or len(outcome.songs) >= MERGE_ALTERNATIVE_BELOW:
        return outcome, estimate, chords, sequence, transitions

    # The same chords can be written several ways depending on which note is
    # called home, and Hooktheory's song index is very unevenly populated across
    # those spellings: a dorian i-ii returns a handful of songs while the
    # identical chords written as ii-iii in the relative major return hundreds.
    # A player asking "what songs use my chords" wants both, so query the
    # respellings and merge them rather than treating them as rival hypotheses.
    #
    # Keep the originally detected key at the head of the override list: it was
    # the best reading of the notes themselves, and it is the first thing a
    # player who disagrees with a correction will reach for.
    alternatives = ((estimate.key, estimate.confidence), *estimate.alternatives)
    best = outcome
    best_key, best_chords, best_sequence = estimate, chords, sequence
    merged_results = list(outcome.results)
    spent = outcome.requests_spent
    queried = list(outcome.queried)

    for alt_key, alt_confidence in _retry_keys(estimate)[:MAX_KEY_RETRIES]:
        alt_chords = merge_identified(
            identify_all(tuple(c.event for c in first_pass), key=alt_key),
            segment_cfg.min_chord_dur_ms,
            segment_cfg.jaccard_same,
        )
        alt_sequence = progression_to_cp(alt_chords, alt_key, cp_cfg)
        alt_outcome, alt_transitions = await run(alt_sequence, budget)
        spent += alt_outcome.requests_spent
        queried.extend(alt_outcome.queried)
        if not alt_outcome.songs:
            continue

        log.info(
            "respelling as %s yielded %d songs; merging",
            alt_key, len(alt_outcome.songs),
        )
        merged_results.extend(alt_outcome.results)
        # Report whichever reading the database actually knows best. Hooktheory
        # having songs for one spelling and not another is real evidence about
        # the key -- usually better evidence than pitch-class analysis alone.
        if len(alt_outcome.songs) > len(best.songs):
            best = alt_outcome
            best_chords, best_sequence = alt_chords, alt_sequence
            transitions = alt_transitions
            best_key = KeyEstimate(
                key=alt_key,
                confidence=max(alt_confidence, estimate.confidence),
                alternatives=alternatives,
                method_scores=(*estimate.method_scores, ("song_match", 1.0)),
                source="matched",
                modulation_suspected=estimate.modulation_suspected,
            )

    if merged_results:
        songs = score_songs(merged_results, transitions)
        if songs:
            return (
                SearchOutcome(
                    songs=songs,
                    artists=rollup_artists(
                        songs, artist_document_frequency, corpus_size
                    ),
                    results=tuple(merged_results),
                    ngrams=best.ngrams,
                    requests_spent=spent,
                    queried=queried,
                    stopped_early=best.stopped_early,
                ),
                best_key, best_chords, best_sequence, transitions,
            )

    # Every key reading came up empty; now it is worth widening the windows.
    candidate = generate_ngrams(sequence, ngram_cfg)
    if candidate:
        table = await build_transition_table(client, [g.tokens for g in candidate])
        outcome = await search_progression(
            client,
            sequence,
            budget=budget,
            ngram_cfg=ngram_cfg,
            transition_prob=table,
            artist_document_frequency=artist_document_frequency,
            corpus_size=corpus_size,
            progress=progress,
        )
        transitions = table
    return outcome, estimate, chords, sequence, transitions


def _retry_keys(estimate: KeyEstimate) -> list[tuple[Key, float]]:
    """Order the alternative keys worth re-querying.

    The parent major scale goes first: it shares a pitch-class set with the
    detected key, so it is both the most likely alternative reading and the one
    whose `cp` tokens are most likely to be well populated in Hooktheory's song
    index, which is heavily skewed toward major-scale spellings.

    Each mode sits on a different degree of that parent scale, so the parent's
    tonic is the mode's tonic minus that degree's offset -- D dorian belongs to
    C major (D minus 2), not F major. Assuming the relative-minor rule of +3
    for every mode sends dorian and mixolydian progressions to the wrong key.
    """
    detected = estimate.key
    scored = {(k.tonic_pc, k.mode): c for k, c in estimate.alternatives}
    preferred: list[tuple[Key, float]] = []

    def add(key: Key) -> None:
        if (key.tonic_pc, key.mode) == (detected.tonic_pc, detected.mode):
            return
        if any((key.tonic_pc, key.mode) == (k.tonic_pc, k.mode) for k, _ in preferred):
            return
        preferred.append((key, scored.get((key.tonic_pc, key.mode), 0.0)))

    parent_major = Key(parent_major_tonic(detected.tonic_pc, detected.mode), "major")
    add(parent_major)

    # The relative minor of that parent scale, which is where Hooktheory files a
    # great deal of minor-key material.
    add(Key((parent_major.tonic_pc + 9) % 12, "minor"))
    # The parallel major/minor, for a genuine mode mixture.
    add(Key(detected.tonic_pc, "minor" if detected.mode != "minor" else "major"))

    for k, c in estimate.alternatives:
        add(k)
        preferred[-1] = (k, c) if preferred and preferred[-1][0] is k else preferred[-1]
    return preferred
