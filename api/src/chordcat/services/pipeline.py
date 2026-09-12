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
from ..domain.chords import identify_all, merge_identified
from ..domain.cp import CpConfig, progression_to_cp
from ..domain.events import (
    CpSequence,
    Hole,
    IdentifiedChord,
    Key,
    KeyEstimate,
    RawEvent,
    SongHit,
)
from ..domain.key import detect_key
from ..domain.ngrams import NgramConfig
from ..domain.profile import TasteProfile, build_profile, harmonic_features
from ..domain.ranking import normalize_name
from ..domain.segment import SegmentConfig, events_from_raw
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

    harmonic = harmonic_features(chords, estimate.key, outcome.ngrams, transitions)
    profile = await build_taste_profile(outcome.songs, harmonic, genres)

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
    )


async def build_taste_profile(
    songs: Sequence[SongHit],
    harmonic,
    genres: GenreResolver | None,
) -> TasteProfile:
    """Roll matched songs up into genre / artist / era / mood weights."""
    artist_weights = Counter[str]()
    for hit in songs:
        artist_weights[hit.artist] += hit.score

    genre_weights = Counter[str]()
    era_weights = Counter[str]()
    mood_weights = Counter[str]()

    if genres is not None and artist_weights:
        labels = await genres.resolve(list(artist_weights))
        for artist, weight in artist_weights.items():
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
    if outcome.songs or key_override is not None:
        return outcome, estimate, chords, sequence, transitions

    for alt_key, alt_confidence in _retry_keys(estimate)[:MAX_KEY_RETRIES]:
        log.info(
            "no matches under %s; retrying as %s",
            estimate.key, alt_key,
        )
        alt_chords = merge_identified(
            identify_all(tuple(c.event for c in first_pass), key=alt_key),
            segment_cfg.min_chord_dur_ms,
            segment_cfg.jaccard_same,
        )
        alt_sequence = progression_to_cp(alt_chords, alt_key, cp_cfg)
        alt_outcome, alt_transitions = await run(alt_sequence, budget)
        if alt_outcome.songs:
            # Hooktheory matching this reading and not the other is real
            # evidence about the key, usually better evidence than the
            # pitch-class analysis that lost. Reporting the losing candidate's
            # score here would show "0% confident" for a key we just confirmed.
            # Put the originally detected key at the head of the alternatives:
            # it was the best reading of the notes themselves, and if the user
            # disagrees with the correction it is the first thing they will
            # reach for. Without this it vanishes from the override list.
            alternatives = (
                (estimate.key, estimate.confidence),
                *(
                    (k, c)
                    for k, c in estimate.alternatives
                    if (k.tonic_pc, k.mode) != (alt_key.tonic_pc, alt_key.mode)
                ),
            )
            resolved = KeyEstimate(
                key=alt_key,
                confidence=max(alt_confidence, estimate.confidence),
                alternatives=alternatives,
                method_scores=(*estimate.method_scores, ("song_match", 1.0)),
                source="matched",
                modulation_suspected=estimate.modulation_suspected,
            )
            return alt_outcome, resolved, alt_chords, alt_sequence, alt_transitions

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

    The relative major and relative minor go first regardless of their detection
    score. They are the readings that share a pitch-class set with the detected
    key, so they are both the most likely to be right and the only ones that
    reliably change the `cp` tokens into something Hooktheory has catalogued.
    Scored alternatives such as a phrygian reading follow behind.
    """
    detected = estimate.key
    preferred: list[tuple[Key, float]] = []
    scored = {(k.tonic_pc, k.mode): c for k, c in estimate.alternatives}

    if detected.mode in ("minor", "dorian", "phrygian"):
        relative = Key((detected.tonic_pc + 3) % 12, "major")
    elif detected.mode in ("major", "lydian", "mixolydian"):
        relative = Key((detected.tonic_pc + 9) % 12, "minor")
    else:
        relative = Key((detected.tonic_pc + 3) % 12, "major")

    preferred.append((relative, scored.get((relative.tonic_pc, relative.mode), 0.0)))

    parallel = Key(
        detected.tonic_pc, "minor" if detected.mode != "minor" else "major"
    )
    preferred.append((parallel, scored.get((parallel.tonic_pc, parallel.mode), 0.0)))

    seen = {(k.tonic_pc, k.mode) for k, _ in preferred}
    for k, c in estimate.alternatives:
        if (k.tonic_pc, k.mode) not in seen:
            preferred.append((k, c))
    return preferred
