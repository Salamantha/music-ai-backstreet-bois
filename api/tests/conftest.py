"""Shared fixtures. Nothing here touches the network."""

from __future__ import annotations

from pathlib import Path

import pytest

from chordcat.domain.chords import identify_all, merge_identified
from chordcat.domain.events import ChordEvent, RawEvent
from chordcat.domain.segment import events_from_raw

FIXTURES = Path(__file__).parent / "fixtures"


def chord_event(pitches: list[int], start: float = 0.0, end: float = 500.0) -> ChordEvent:
    """Build a ChordEvent directly, bypassing segmentation."""
    weights: dict[int, float] = {}
    for p in pitches:
        weights[p % 12] = weights.get(p % 12, 0.0) + 1.0
    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}
    bass = min(pitches)
    weights[bass % 12] = weights.get(bass % 12, 0.0) + 0.6
    return ChordEvent(
        start_ms=start,
        end_ms=end,
        pitches=tuple(sorted(pitches)),
        bass_pitch=bass,
        onset_pitches=tuple(sorted(pitches)),
        pc_weights=tuple(sorted(weights.items())),
        velocity_mean=100.0,
    )


def play(chords: list[tuple[int, ...]], dur: float = 500.0, spread: float = 8.0):
    """Render block chords as a MIDI event stream."""
    events: list[RawEvent] = []
    t = 0.0
    for chord in chords:
        for i, p in enumerate(chord):
            events.append(RawEvent("on", t + i * spread, p, 100))
        for i, p in enumerate(chord):
            events.append(RawEvent("off", t + dur - 15 + i * 3, p))
        t += dur
    return events, t


def analyse_offline(chords: list[tuple[int, ...]], **kw):
    """Segment + identify a progression with no network involved."""
    events, end = play(chords, **kw)
    segmented = events_from_raw(events, session_end_ms=end)
    return merge_identified(identify_all(segmented.events))


@pytest.fixture
def axis():
    return [(60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)]
