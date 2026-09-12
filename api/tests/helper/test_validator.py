from __future__ import annotations

from chordcat.helper.concepts.schema import load_nodes
from chordcat.helper.facts import Fact, FactSet
from chordcat.helper.validator import validate

NODE = load_nodes()["seventh_chords"]

FACTS = FactSet((
    Fact("harmony.chord#0", "harmony.chord", "Cmaj7", n_observations=1, is_pattern=False),
    Fact("harmony.chord#1", "harmony.chord", "Am", n_observations=1, is_pattern=False),
    Fact("harmony.key_estimate#0", "harmony.key_estimate", "C major", confidence=0.8,
         n_observations=8),
    Fact("harmony.rhythm#0", "harmony.rhythm",
         {"mean_chord_ms": 1200.0, "mean_chord_s": 1.2, "chords": 8}, n_observations=8),
))


def test_text_grounded_in_the_facts_passes():
    assert validate("You played Cmaj7 and Am, in C major.", FACTS, NODE).ok


def test_a_chord_that_was_never_played_is_rejected():
    verdict = validate("That Fmin7 you played is doing the work.", FACTS, NODE)
    assert not verdict.ok
    assert "Fmin7" in {r.claim for r in verdict.rejections}


def test_a_number_with_no_fact_behind_it_is_rejected():
    verdict = validate("All 14 of your chords are sevenths.", FACTS, NODE)
    assert not verdict.ok
    assert "14" in {r.claim for r in verdict.rejections}


def test_numbers_that_do_appear_in_the_facts_pass():
    assert validate("Across 8 chords, that is the shape.", FACTS, NODE).ok


def test_node_prose_is_always_allowed_through():
    assert validate(NODE.what_it_does_to_the_sound, FACTS, NODE).ok


def test_a_key_the_analysis_did_not_detect_is_rejected():
    verdict = validate("You are in F minor here.", FACTS, NODE)
    assert not verdict.ok


def test_an_internal_fact_id_is_not_allowed_through():
    """A real model did exactly this: cited `perf.velocity_stats#0` at the user."""
    verdict = validate(
        "You play evenly, per the perf.velocity_stats#0 fact.", FACTS, NODE
    )
    assert not verdict.ok
    assert "perf.velocity_stats#0" in {r.claim for r in verdict.rejections}


def test_ordinary_prose_with_a_full_stop_is_not_mistaken_for_a_fact_id():
    assert validate("It leans somewhere. Then it settles.", FACTS, NODE).ok
