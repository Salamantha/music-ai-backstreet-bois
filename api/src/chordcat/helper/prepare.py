"""Adapter onto the existing analysis core.

Chord-progression analysis belongs to the mobile dev's component, and
`chordcat.domain` already identifies chords, detects key and segments takes,
under test. So this module does no music theory of its own. It runs that
pipeline in its own order and hands the result to our facts layer.

Ordering is copied deliberately from ``services/pipeline.py``: identify once with
no key context (otherwise key detection is circular), detect the key from that,
then re-identify with the key known so diatonic ambiguities resolve.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.chords import identify_all, merge_identified
from ..domain.events import IdentifiedChord, Key, KeyEstimate
from ..domain.key import detect_key
from ..domain.segment import SegmentConfig, SegmentResult, events_from_raw
from .session import Session


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """Everything an analyser is allowed to look at."""

    session: Session
    segment: SegmentResult
    chords: tuple[IdentifiedChord, ...]
    key: KeyEstimate


def prepare(session: Session, cfg: SegmentConfig = SegmentConfig()) -> AnalysisInput:
    segmented = events_from_raw(session.events, cfg, session_end_ms=session.elapsed_ms or None)
    if not segmented.events:
        return AnalysisInput(session, segmented, (), KeyEstimate(Key(0, "major"), 0.0))

    first_pass = merge_identified(
        identify_all(segmented.events), cfg.min_chord_dur_ms, cfg.jaccard_same
    )
    estimate = detect_key(first_pass)
    chords = merge_identified(
        identify_all(tuple(c.event for c in first_pass), key=estimate.key),
        cfg.min_chord_dur_ms,
        cfg.jaccard_same,
    )
    return AnalysisInput(session, segmented, chords, estimate)
