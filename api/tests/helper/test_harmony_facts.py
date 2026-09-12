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


def test_a_real_take_produces_the_v0_harmony_kinds():
    kinds = {f.kind for f in facts_for_take()}
    assert "harmony.key_estimate" in kinds
    assert "harmony.chord" in kinds
    assert "harmony.quality_counts" in kinds
    assert "harmony.root_motion" in kinds
    assert "harmony.rhythm" in kinds


def test_every_fact_is_namespaced_and_uniquely_identified():
    fs = facts_for_take()
    assert all(f.namespace in {"harmony", "voicing", "perf"} for f in fs)
    ids = [f.id for f in fs]
    assert len(ids) == len(set(ids))


def test_key_estimate_carries_its_confidence_and_chord_count():
    key = facts_for_take().get("harmony.key_estimate")
    assert 0.0 <= key.confidence <= 1.0
    assert key.n_observations > 0


def test_each_chord_fact_points_back_at_the_chord_it_came_from():
    chords = facts_for_take().by_kind("harmony.chord")
    assert chords
    assert all(c.evidence for c in chords)
