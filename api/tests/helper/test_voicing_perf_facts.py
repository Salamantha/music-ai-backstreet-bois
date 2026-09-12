from __future__ import annotations

from pathlib import Path

from chordcat.helper.analysis import run_all
from chordcat.helper.prepare import prepare
from chordcat.helper.sources import FixtureSource

CHORDCAT_TAKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "midi" / "chordcat-8track-sequencer.json"
)


def facts_for_take():
    return run_all(prepare(FixtureSource(CHORDCAT_TAKE).load()))


def test_register_span_is_measured_in_semitones():
    span = facts_for_take().get("voicing.register_span")
    assert span is not None
    assert 0 < span.value["span_semitones"] < 88


def test_inversion_usage_is_counted():
    inv = facts_for_take().get("voicing.inversions")
    assert inv is not None
    assert inv.value["root_position"] + inv.value["inverted"] == inv.n_observations


def test_velocity_stats_and_density_are_present():
    fs = facts_for_take()
    assert fs.get("perf.velocity_stats").value["mean"] > 0
    assert fs.get("perf.density").value["chords_per_minute"] > 0


def test_repetition_notices_a_repeated_shape():
    rep = facts_for_take().get("perf.repetition")
    assert rep is None or 0.0 <= rep.value["repeat_rate"] <= 1.0
