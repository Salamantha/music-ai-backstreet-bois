from __future__ import annotations

from pathlib import Path

from chordcat.helper.cli import analyse_capture, main

CHORDCAT_TAKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "midi" / "chordcat-8track-sequencer.json"
)


def test_a_real_capture_produces_a_full_turn_offline():
    result = analyse_capture(CHORDCAT_TAKE)
    assert result.choice is not None
    assert result.response.text
    assert result.facts.facts


def test_the_turn_never_contains_an_unfilled_marker():
    text = analyse_capture(CHORDCAT_TAKE).response.text
    assert "TUTOR_TODO" not in text
    assert "TBD" not in text


def test_the_turn_for_a_real_take_is_grounded_in_its_own_facts():
    from chordcat.helper.validator import validate

    result = analyse_capture(CHORDCAT_TAKE)
    assert validate(result.response.text, result.facts, result.choice.node).ok


def test_cli_prints_the_turn(capsys):
    assert main(["analyse", str(CHORDCAT_TAKE)]) == 0
    out = capsys.readouterr().out
    assert "NOTICED" in out
    assert "WHY THIS" in out


def test_tutor_todo_lists_what_still_needs_writing(capsys):
    assert main(["tutor-todo"]) == 0
    out = capsys.readouterr().out
    assert "draft" in out
    assert "on_device" in out
