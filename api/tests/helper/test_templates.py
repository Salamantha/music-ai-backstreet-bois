from __future__ import annotations

from chordcat.helper.concepts.graph import Choice
from chordcat.helper.concepts.schema import load_nodes
from chordcat.helper.facts import Fact, FactSet
from chordcat.helper.templates import render_turn
from chordcat.helper.validator import validate

NODES = load_nodes()
CHOICE = Choice(node=NODES["seventh_chords"], why=("chords_in_a_key",), distance=1, score=9.0)

FACTS = FactSet((
    Fact("harmony.chord#0", "harmony.chord", "C", n_observations=1, is_pattern=False),
    Fact("harmony.key_estimate#0", "harmony.key_estimate", "C major", confidence=0.8,
         n_observations=8),
    Fact("harmony.rhythm#0", "harmony.rhythm",
         {"mean_chord_ms": 1200.0, "mean_chord_s": 1.2, "chords": 8}, n_observations=8),
))


def test_the_turn_has_all_four_moves():
    turn = render_turn(FACTS, CHOICE)
    assert turn.notice
    assert turn.suggestion
    assert turn.what_it_means
    assert turn.how_to


def test_the_templated_turn_passes_its_own_validator():
    turn = render_turn(FACTS, CHOICE)
    assert validate(turn.text(), FACTS, CHOICE.node).ok


def test_a_number_the_template_derives_is_still_grounded():
    """The fallback must pass the same validator it exists to satisfy."""
    turn = render_turn(FACTS, CHOICE)
    assert "1.2 seconds" in turn.notice


def test_an_unfilled_device_action_says_so_rather_than_inventing_one():
    turn = render_turn(FACTS, CHOICE)
    assert "TUTOR_TODO" not in turn.text()
