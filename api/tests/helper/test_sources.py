from __future__ import annotations

from pathlib import Path

from chordcat.helper.sources import FixtureSource

CHORDCAT_TAKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "midi" / "chordcat-8track-sequencer.json"
)


def test_fixture_source_narrows_to_the_harmony_channel():
    session = FixtureSource(CHORDCAT_TAKE).load()
    assert session.device == "Chordcat"  # the capture spells it as the device does
    assert len(session.events) == 230  # 115 note-ons + 115 note-offs on channel 2
    assert session.elapsed_ms > 53_000


def test_fixture_source_can_be_pointed_at_another_channel():
    session = FixtureSource(CHORDCAT_TAKE, channel=1).load()
    assert len(session.events) == 331  # 165 on + 166 off


def test_whole_capture_when_channel_is_explicitly_none():
    session = FixtureSource(CHORDCAT_TAKE, channel=0).load()
    assert len(session.events) == 1596
