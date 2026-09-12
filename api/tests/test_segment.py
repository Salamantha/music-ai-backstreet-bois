"""Segmentation: note stream -> chord events."""

from __future__ import annotations

from chordcat.domain.events import RawEvent
from chordcat.domain.segment import (
    SegmentConfig,
    _cluster_onsets,
    events_from_raw,
    pair_notes,
)

from conftest import play


def test_block_chords_split_cleanly(axis):
    events, end = play(axis)
    result = events_from_raw(events, session_end_ms=end)
    assert result.mode == "onset"
    assert len(result.events) == 4
    assert [sorted(e.pcs) for e in result.events] == [
        [0, 4, 7], [2, 7, 11], [0, 4, 9], [0, 5, 9]
    ]


def test_onset_window_is_measured_from_the_cluster_head_not_chained():
    """Each cluster spans a fixed window from its own first onset.

    If the window were re-based on every absorbed note, a run of notes each
    inside the window of the previous one would chain indefinitely and swallow
    the whole take into a single meaningless cluster. Tested at the clustering
    level because the minimum-notes-per-chord filter would otherwise confound it.
    """
    cfg = SegmentConfig()
    spacing = cfg.onset_window_ms * 0.8  # each note inside the previous one's window
    notes, _ = pair_notes(
        [
            e
            for i, p in enumerate([60, 64, 67, 72])
            for e in (
                RawEvent("on", i * spacing, p, 100),
                RawEvent("off", i * spacing + 400, p),
            )
        ],
        session_end_ms=1000,
    )
    clusters = _cluster_onsets(notes, cfg)
    assert len(clusters) == 2, "chained absorption would give exactly one cluster"


def test_rolled_chord_is_one_harmony():
    """Notes spread by a strum or roll are one chord, not several."""
    events = []
    for i, p in enumerate([60, 64, 67, 72, 76]):
        events.append(RawEvent("on", i * 50.0, p, 100))
        events.append(RawEvent("off", i * 50.0 + 400, p))
    result = events_from_raw(events, session_end_ms=1000)
    assert len(result.events) == 1
    assert sorted(result.events[0].pcs) == [0, 4, 7]


def test_note_on_velocity_zero_is_note_off():
    events = [
        RawEvent("on", 0, 60, 100), RawEvent("on", 0, 64, 100), RawEvent("on", 0, 67, 100),
        RawEvent("on", 400, 60, 0), RawEvent("on", 400, 64, 0), RawEvent("on", 400, 67, 0),
    ]
    notes, stuck = pair_notes(events, session_end_ms=800)
    assert stuck == 0
    assert all(n.off_ms == 400 for n in notes)


def test_missing_note_off_is_flagged_not_dropped():
    events = [RawEvent("on", 0, 60, 100), RawEvent("on", 0, 64, 100)]
    notes, stuck = pair_notes(events, session_end_ms=900)
    assert stuck == 2
    assert all(n.off_ms == 900 and n.stuck for n in notes)


def test_rearticulation_inside_grace_is_one_note():
    cfg = SegmentConfig()
    events = [
        RawEvent("on", 0, 60, 100),
        RawEvent("off", 200, 60),
        RawEvent("on", 200 + cfg.release_grace_ms / 2, 60, 100),
        RawEvent("off", 600, 60),
    ]
    notes, _ = pair_notes(events, session_end_ms=600, cfg=cfg)
    assert len(notes) == 1
    assert notes[0].on_ms == 0 and notes[0].off_ms == 600


def test_out_of_order_events_are_sorted():
    events, end = play([(60, 64, 67), (55, 59, 62)])
    shuffled = list(reversed(events))
    assert events_from_raw(shuffled, session_end_ms=end).events == \
        events_from_raw(events, session_end_ms=end).events


def test_octave_doubled_bass_collapses_in_pitch_class_space():
    events, end = play([(36, 48, 60, 64, 67)])
    result = events_from_raw(events, session_end_ms=end)
    ev = result.events[0]
    assert sorted(ev.pcs) == [0, 4, 7]
    assert ev.bass_pitch == 36


def test_arpeggio_falls_back_to_grid():
    """A running arpeggiator should switch to fixed-window pooling."""
    events = []
    pattern = [60, 64, 67, 72] * 6
    for i, p in enumerate(pattern):
        events.append(RawEvent("on", i * 120.0, p, 100))
        events.append(RawEvent("off", i * 120.0 + 110, p))
    result = events_from_raw(events, session_end_ms=len(pattern) * 120)
    assert result.mode == "grid"
    assert result.grid_ms is not None
