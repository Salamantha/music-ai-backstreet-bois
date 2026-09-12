from __future__ import annotations

from pathlib import Path

from chordcat.helper.prepare import prepare
from chordcat.helper.session import Session
from chordcat.helper.sources import FixtureSource

CHORDCAT_TAKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "midi" / "chordcat-8track-sequencer.json"
)


def test_prepare_yields_chords_and_a_key_from_a_real_take():
    got = prepare(FixtureSource(CHORDCAT_TAKE).load())
    assert len(got.chords) > 4
    assert 0 <= got.key.key.tonic_pc < 12
    assert got.key.confidence > 0.0
    assert got.segment.mode in {"onset", "grid"}


def test_prepare_on_silence_is_empty_not_an_exception():
    got = prepare(Session(id="empty"))
    assert got.chords == ()
    assert got.segment.events == ()
