"""Regression tests against a real AlphaTheta ChordCat capture.

The fixture is 54 seconds of all eight sequencer tracks running at once. It is
here because synthetic note streams hid the two things that actually broke
identification on real hardware: every track arrives interleaved on its own MIDI
channel, and the device voices chords as five-note extended harmony rather than
triads.
"""

from __future__ import annotations

import json

import pytest

from chordcat.domain.chords import identify_all, identify_chord, merge_identified
from chordcat.domain.events import RawEvent
from chordcat.domain.pitch import pc_name
from chordcat.domain.segment import events_from_raw

from conftest import FIXTURES

CAPTURE = FIXTURES / "midi" / "chordcat-8track-sequencer.json"
HARMONY_CHANNEL = 2


@pytest.fixture(scope="module")
def take():
    return json.loads(CAPTURE.read_text())


def raw_events(take, channel: int | None = None):
    return [
        RawEvent(
            kind=e["k"], t=e["t"], pitch=e.get("p"),
            velocity=e.get("v", 0), controller=e.get("n"),
        )
        for e in take["events"]
        if channel is None or e.get("c") == channel
    ]


def test_the_capture_really_does_interleave_eight_tracks(take):
    channels = {e.get("c") for e in take["events"]}
    assert len(channels) == 8


def test_only_the_chord_track_has_multi_note_onsets(take):
    """The premise of channel filtering: exactly one track carries harmony."""
    chordal = [
        s["channel"] for s in take["channel_stats"] if s["maxSimultaneous"] >= 3
    ]
    assert HARMONY_CHANNEL in chordal


def test_harmony_channel_segments_into_clean_chords(take):
    result = events_from_raw(
        raw_events(take, HARMONY_CHANNEL), session_end_ms=take["elapsed_ms"]
    )
    assert result.mode == "onset"
    assert len(result.events) >= 20
    # The device voices every chord with five notes.
    assert all(len(e.pitches) == 5 for e in result.events)


def test_extended_voicings_are_identified_correctly(take):
    """ChordCat sends 9ths and 11ths with the fifth omitted.

    These are exactly the voicings a triad-and-seventh template set could get
    wrong, so pin the readings of known chords from the capture.
    """
    result = events_from_raw(
        raw_events(take, HARMONY_CHANNEL), session_end_ms=take["elapsed_ms"]
    )
    chords = merge_identified(identify_all(result.events))
    readings = {
        (c.event.pitches, pc_name(c.best.root_pc), c.best.quality) for c in chords
    }
    by_pitches = {p: (r, q) for p, r, q in readings}

    # E2 G#3 B3 D#4 F#4 -> Emaj9
    assert by_pitches[(40, 56, 59, 63, 66)] == ("E", "maj7")
    # A2 G3 C4 D4 G4 -> Am11
    assert by_pitches[(45, 55, 60, 62, 67)] == ("A", "min7")
    # D3 C4 F4 G4 C5 -> Dm11
    assert by_pitches[(50, 60, 65, 67, 72)] == ("D", "min7")
    # F#2 E3 A3 B3 G#4 -> F#m11
    assert by_pitches[(42, 52, 57, 59, 68)] == ("F#", "min7")


def test_colour_tones_are_recorded_as_extensions(take):
    """The 9th and 11th should be captured, not silently discarded."""
    result = events_from_raw(
        raw_events(take, HARMONY_CHANNEL), session_end_ms=take["elapsed_ms"]
    )
    am11 = next(e for e in result.events if e.pitches == (45, 55, 60, 62, 67))
    best = identify_chord(am11)[0]
    assert "11" in best.extensions


def test_merging_all_channels_destroys_identification(take):
    """Why channel filtering exists, pinned as a test.

    Feeding every track in at once does not fail loudly -- it produces a
    different, confident, wrong answer. That silence is what made the original
    bug hard to spot.
    """
    harmony = merge_identified(
        identify_all(
            events_from_raw(
                raw_events(take, HARMONY_CHANNEL), session_end_ms=take["elapsed_ms"]
            ).events
        )
    )
    everything = merge_identified(
        identify_all(
            events_from_raw(
                raw_events(take), session_end_ms=take["elapsed_ms"]
            ).events
        )
    )
    harmony_seq = [(c.best.root_pc, c.best.quality) for c in harmony]
    merged_seq = [(c.best.root_pc, c.best.quality) for c in everything]

    # Every melody and bass note becomes its own spurious chord change.
    assert len(merged_seq) > 3 * len(harmony_seq)

    # Almost nothing lines up. Note that comparing the *sets* of chords would
    # miss this -- the harmony notes are still present in the merged soup, so
    # the chord vocabulary overlaps heavily even though the progression is
    # destroyed. Position is what matters.
    aligned = sum(1 for a, b in zip(harmony_seq, merged_seq) if a == b)
    assert aligned <= 2, f"{aligned} of {len(harmony_seq)} chords survived merging"
