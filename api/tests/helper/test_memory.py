"""Session memory, and the change facts it makes possible."""

from __future__ import annotations

import pytest

from chordcat.helper.analysis.change import diff_facts
from chordcat.helper.facts import Fact, FactSet
from chordcat.helper.memory import SqliteSessionStore


@pytest.fixture
def store(tmp_path):
    return SqliteSessionStore(tmp_path / "memory.db")


def facts(key="A major", mean_s=2.8, span=37, qualities=None, chords=19) -> FactSet:
    return FactSet((
        Fact("harmony.key_estimate#0", "harmony.key_estimate", key, n_observations=chords),
        Fact("harmony.rhythm#0", "harmony.rhythm",
             {"mean_chord_ms": mean_s * 1000, "mean_chord_s": mean_s, "chords": chords},
             n_observations=chords),
        Fact("voicing.register_span#0", "voicing.register_span",
             {"span_semitones": span, "lowest": 37, "highest": 37 + span},
             n_observations=chords),
        Fact("harmony.quality_counts#0", "harmony.quality_counts",
             qualities or {"min7": 12, "maj7": 3}, n_observations=chords),
    ))


def test_recall_is_empty_before_anything_is_recorded(store):
    recall = store.recall("s1")
    assert recall.suggested_nodes == ()
    assert recall.previous.facts == ()
    assert recall.is_first_turn


def test_it_remembers_what_it_already_suggested(store):
    store.record("s1", facts(), "inversions", "first turn")
    store.record("s1", facts(), "slow_harmony", "second turn")

    recall = store.recall("s1")
    assert recall.suggested_nodes == ("inversions", "slow_harmony")
    assert [t[0] for t in recall.turns] == ["inversions", "slow_harmony"]
    assert not recall.is_first_turn


def test_memory_survives_a_new_process(tmp_path):
    """A browser refresh must not make the helper start repeating itself."""
    path = tmp_path / "memory.db"
    SqliteSessionStore(path).record("s1", facts(), "inversions", "said it once")

    reopened = SqliteSessionStore(path).recall("s1")
    assert reopened.suggested_nodes == ("inversions",)
    assert reopened.previous.get("harmony.key_estimate").value == "A major"


def test_sessions_do_not_leak_into_each_other(store):
    store.record("s1", facts(), "inversions", "for s1")
    store.record("s2", facts(), "slow_harmony", "for s2")
    assert store.recall("s1").suggested_nodes == ("inversions",)
    assert store.recall("s2").suggested_nodes == ("slow_harmony",)


def test_overrides_are_counted(store):
    store.bump_override("s1")
    store.bump_override("s1")
    store.record("s1", facts(), "inversions", "t")
    assert store.recall("s1").override_count == 2


def test_tried_is_a_subset_of_suggested(store):
    store.record("s1", facts(), "inversions", "t")
    store.record("s1", facts(), "slow_harmony", "t")
    store.mark_tried("s1", "inversions")
    recall = store.recall("s1")
    assert recall.tried_nodes == ("inversions",)
    assert set(recall.tried_nodes) <= set(recall.suggested_nodes)


# -- change facts ---------------------------------------------------------

def test_the_first_take_has_nothing_to_compare_against():
    assert diff_facts(FactSet(), facts()) == []


def test_an_unchanged_take_reports_no_change():
    assert diff_facts(facts(), facts()) == []


def test_a_key_change_is_noticed():
    changed = diff_facts(facts(key="A major"), facts(key="C minor"))
    assert [f.kind for f in changed] == ["change.key"]
    assert changed[0].value == {"from": "A major", "to": "C minor"}


def test_slowing_down_is_measured_with_a_direction():
    changed = {f.kind: f.value for f in diff_facts(facts(mean_s=2.8), facts(mean_s=6.0))}
    assert changed["change.harmonic_rhythm"]["direction"] == "up"
    assert changed["change.harmonic_rhythm"]["from"] == 2.8


def test_a_wobble_is_not_a_change():
    """Chord durations vary take to take; only a real shift counts."""
    assert diff_facts(facts(mean_s=2.8), facts(mean_s=3.0)) == []


def test_new_chord_types_are_named():
    changed = diff_facts(
        facts(qualities={"min7": 12}), facts(qualities={"min7": 10, "7sus4": 4})
    )
    by_kind = {f.kind: f.value for f in changed}
    assert by_kind["change.chord_types"]["new"] == ["7sus4"]
    assert by_kind["change.chord_types"]["gone"] == []


def test_change_facts_are_namespaced_so_the_validator_governs_them():
    changed = diff_facts(facts(key="A major"), facts(key="C minor"))
    assert all(f.namespace == "change" for f in changed)
