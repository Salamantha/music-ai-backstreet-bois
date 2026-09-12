from __future__ import annotations

from chordcat.helper.concepts.graph import Choice
from chordcat.helper.concepts.schema import load_nodes
from chordcat.helper.converse import LayeredVoice, TemplateVoice, build_prompt
from chordcat.helper.facts import Fact, FactSet

NODES = load_nodes()
CHOICE = Choice(node=NODES["seventh_chords"], why=("chords_in_a_key",), distance=1, score=9.0)
FACTS = FactSet((
    Fact("harmony.chord#0", "harmony.chord", "C", n_observations=1, is_pattern=False),
    Fact("harmony.key_estimate#0", "harmony.key_estimate", "C major", confidence=0.8,
         n_observations=8),
))


class Rejecting:
    """A voice that always invents a chord, to prove the fallback fires."""

    calls = 0

    def speak(self, prompt: str) -> str:
        Rejecting.calls += 1
        return "Try the Fmin7 you played there."


class Grounded:
    def speak(self, prompt: str) -> str:
        return "You are in C major. Try adding a fourth note."


def test_the_prompt_never_carries_raw_midi():
    prompt = build_prompt(FACTS, CHOICE, user_text="make it heavier")
    assert "note_on" not in prompt and "RawEvent" not in prompt
    assert "harmony.key_estimate" in prompt
    assert "adding a fourth note" in prompt
    assert "make it heavier" in prompt


def test_template_voice_needs_no_model():
    result = TemplateVoice().respond(FACTS, CHOICE)
    assert result.used_fallback is True
    assert result.text


def test_a_grounded_model_answer_is_used_as_is():
    result = LayeredVoice(Grounded()).respond(FACTS, CHOICE)
    assert result.used_fallback is False
    assert "C major" in result.text


def test_an_ungrounded_answer_is_retried_then_falls_back_to_the_template():
    Rejecting.calls = 0
    result = LayeredVoice(Rejecting(), max_retries=2).respond(FACTS, CHOICE)
    assert result.used_fallback is True
    assert Rejecting.calls == 3  # first attempt + 2 retries
    assert "Fmin7" not in result.text
    assert result.rejections


def test_rejection_rate_is_exposed():
    voice = LayeredVoice(Rejecting(), max_retries=1)
    voice.respond(FACTS, CHOICE)
    assert voice.rejection_rate == 1.0
