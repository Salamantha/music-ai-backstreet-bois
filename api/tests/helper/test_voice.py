"""The phrasing layer, exercised without reaching any provider."""

from __future__ import annotations

import httpx
import pytest

from chordcat.config import Settings
from chordcat.helper.concepts.graph import Choice
from chordcat.helper.concepts.schema import load_nodes
from chordcat.helper.converse import (
    LayeredVoice,
    OpenAICompatibleVoice,
    TemplateVoice,
    build_voice,
)
from chordcat.helper.facts import Fact, FactSet

NODES = load_nodes()
CHOICE = Choice(node=NODES["inversions"], why=("chords_in_a_key",), distance=1, score=12.0)
FACTS = FactSet((
    Fact("harmony.chord#0", "harmony.chord", "Am7", n_observations=1, is_pattern=False),
    Fact("harmony.key_estimate#0", "harmony.key_estimate", "A major", confidence=0.3,
         n_observations=19),
))


def fake_provider(monkeypatch, reply: str, captured: dict):
    """Stand in for any OpenAI-compatible endpoint."""

    def post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json or {}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": reply}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)


def test_it_posts_the_openai_chat_shape(monkeypatch):
    captured: dict = {}
    fake_provider(monkeypatch, "You are in A major. Try a different bottom note.", captured)
    voice = OpenAICompatibleVoice(
        base_url="https://example.test/v1/", model="qwen2.5:7b", api_key="secret"
    )

    assert "A major" in voice.speak("prompt text")
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "qwen2.5:7b"
    assert captured["json"]["messages"][0]["content"] == "prompt text"


def test_no_auth_header_when_there_is_no_key(monkeypatch):
    """Ollama rejects an empty bearer token."""
    captured: dict = {}
    fake_provider(monkeypatch, "fine", captured)
    # api_key explicitly blank: a real key in .env would otherwise supply one.
    OpenAICompatibleVoice(
        base_url="http://localhost:11434/v1", model="qwen2.5:7b", api_key=""
    ).speak("p")
    assert "Authorization" not in captured["headers"]


def test_an_unconfigured_endpoint_refuses_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(
        "chordcat.config.get_settings", lambda: Settings(llm_base_url="", llm_model="")
    )
    with pytest.raises(RuntimeError, match="no LLM endpoint"):
        OpenAICompatibleVoice().speak("p")


def test_a_model_that_invents_a_chord_still_cannot_reach_the_user(monkeypatch):
    """The whole reason a small open model is safe in this position."""
    captured: dict = {}
    fake_provider(monkeypatch, "Lean on that Fmin7 you played.", captured)
    voice = LayeredVoice(
        OpenAICompatibleVoice(base_url="https://example.test/v1", model="m"), max_retries=1
    )
    result = voice.respond(FACTS, CHOICE)
    assert result.used_fallback is True
    assert "Fmin7" not in result.text
    assert voice.rejection_rate == 1.0


def test_a_dead_provider_falls_back_instead_of_erroring(monkeypatch):
    def explode(*a, **kw):
        raise httpx.ConnectError("nothing listening")

    monkeypatch.setattr(httpx, "post", explode)
    result = LayeredVoice(
        OpenAICompatibleVoice(base_url="https://example.test/v1", model="m")
    ).respond(FACTS, CHOICE)
    assert result.used_fallback is True
    assert result.text


def test_build_voice_prefers_the_open_endpoint_then_falls_to_template(monkeypatch):
    monkeypatch.setattr(
        "chordcat.config.get_settings",
        lambda: Settings(llm_base_url="https://example.test/v1", llm_model="m"),
    )
    assert isinstance(build_voice(), LayeredVoice)

    # Explicitly blank, not a bare Settings(): a developer's real .env would
    # otherwise decide the outcome of this test.
    monkeypatch.setattr(
        "chordcat.config.get_settings",
        lambda: Settings(llm_base_url="", llm_model="", anthropic_api_key=""),
    )
    assert isinstance(build_voice(), TemplateVoice)


def test_offline_mode_never_reaches_for_a_model(monkeypatch):
    monkeypatch.setattr(
        "chordcat.config.get_settings",
        lambda: Settings(
            llm_base_url="https://example.test/v1", llm_model="m", chordcat_offline=True
        ),
    )
    assert isinstance(build_voice(), TemplateVoice)
