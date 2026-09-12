"""L4: the mouth. It phrases what the facts layer computed. It computes nothing.

The model receives the FactSet, the one chosen node with its teaching payload,
the device action, and what the user said -- and nothing else. It is never asked
to identify a chord, a key or an interval, because deterministic code does that
exactly and nearly free, while a model naming a chord the user never played
loses them permanently and they cannot catch the error themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from .concepts.graph import Choice
from .facts import FactSet
from .templates import render_turn
from .validator import Rejection, validate

log = logging.getLogger(__name__)

TURN_CONTRACT = """\
You are rephrasing one teaching note for someone messing about on a groovebox.
They cannot read music and have no training. Rules, all hard:

- Notice something true about what they played, then offer ONE thing to explore.
- Never use a musical term without its plain meaning in the same breath.
- Nothing they played is wrong. Options are unexplored territory, not corrections.
- Do not name any chord, key or number that is not listed in the facts below.
- Do not write music for them and do not describe notes to play.
- Four short paragraphs: what you noticed, the one option, what it means and what
  it does to the sound, how to do it on the device.
"""


class Voice(Protocol):
    def speak(self, prompt: str) -> str: ...


@dataclass(frozen=True, slots=True)
class Response:
    text: str
    used_fallback: bool
    rejections: tuple[Rejection, ...] = ()


def build_prompt(facts: FactSet, choice: Choice, user_text: str | None = None) -> str:
    lines = [TURN_CONTRACT, "", "FACTS (the only things you may assert):"]
    for fact in facts:
        lines.append(f"  {fact.id} = {fact.value!r}  (n={fact.n_observations})")
    node = choice.node
    lines += [
        "",
        "THE ONE THING TO SUGGEST:",
        f"  name: {node.plain_name}",
        f"  what it means: {node.what_it_means}",
        f"  what it does to the sound: {node.what_it_does_to_the_sound}",
        f"  when it helps: {node.when_it_helps}",
        f"  common mistake: {node.common_mistake}",
        f"  on the device: {node.on_device}",
        f"  why this one: it is one step from {', '.join(choice.why) or 'what they played'}",
    ]
    if user_text:
        lines += ["", f"WHAT THEY SAID: {user_text}"]
    return "\n".join(lines)


@dataclass(slots=True)
class TemplateVoice:
    """No model at all. The offline default."""

    def respond(self, facts: FactSet, choice: Choice, user_text: str | None = None) -> Response:
        return Response(render_turn(facts, choice).text(), used_fallback=True)


@dataclass(slots=True)
class LayeredVoice:
    """A model, with the template underneath it.

    ``rejection_rate`` is a health metric on the language layer, not on the
    model: a rising rate means the prompt or the node prose is failing.
    """

    voice: Voice
    max_retries: int = 2
    attempts: int = 0
    rejected: int = 0
    _last: tuple[Rejection, ...] = field(default=(), init=False)

    @property
    def rejection_rate(self) -> float:
        return (self.rejected / self.attempts) if self.attempts else 0.0

    def respond(self, facts: FactSet, choice: Choice, user_text: str | None = None) -> Response:
        prompt = build_prompt(facts, choice, user_text)
        for _ in range(self.max_retries + 1):
            self.attempts += 1
            try:
                text = self.voice.speak(prompt)
            except Exception:  # noqa: BLE001 -- a dead model must not kill the turn
                log.warning("voice failed; falling back to template", exc_info=True)
                break
            verdict = validate(text, facts, choice.node)
            if verdict.ok:
                return Response(text, used_fallback=False)
            self.rejected += 1
            self._last = verdict.rejections
            log.info("rejected generated turn: %s", [r.claim for r in verdict.rejections])
        return Response(
            render_turn(facts, choice).text(), used_fallback=True, rejections=self._last
        )


@dataclass(slots=True)
class OpenAICompatibleVoice:
    """Any provider that speaks /chat/completions.

    Groq, Together, OpenRouter and a local Ollama are all the same wire format,
    so one class covers every option and swapping provider is a config change.
    Uses httpx, which the project already depends on, rather than pulling in a
    vendor SDK for one POST.

    A small open model is safe in this position specifically because
    :mod:`chordcat.helper.validator` rejects any chord, key or number that is
    not in the FactSet. The worst a weak model can do here is get rejected and
    fall through to the template.
    """

    base_url: str = ""
    model: str = ""
    api_key: str = ""
    max_tokens: int = 600
    timeout_s: float = 30.0

    def speak(self, prompt: str) -> str:
        import httpx

        from ..config import get_settings

        settings = get_settings()
        base = (self.base_url or settings.llm_base_url).rstrip("/")
        model = self.model or settings.llm_model
        key = self.api_key or settings.llm_api_key
        if not base or not model:
            raise RuntimeError("no LLM endpoint configured")
        if settings.chordcat_offline:
            raise RuntimeError("offline mode forbids the network")

        headers = {"Content-Type": "application/json"}
        # Ollama needs no key; hosted providers do. Sending an empty bearer
        # token upsets some of them, so only set it when there is one.
        if key:
            headers["Authorization"] = f"Bearer {key}"

        response = httpx.post(
            f"{base}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "max_tokens": self.max_tokens or settings.llm_max_tokens,
                # Low, not zero: the phrasing should vary between turns, but
                # this is not the place for invention.
                "temperature": 0.4,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


@dataclass(slots=True)
class ClaudeVoice:
    """Live phrasing. Optional: used only when an API key is configured."""

    model: str = ""
    max_tokens: int = 600

    def speak(self, prompt: str) -> str:
        import anthropic

        from ..config import get_settings

        settings = get_settings()
        if not settings.has_anthropic or settings.chordcat_offline:
            raise RuntimeError("no Anthropic key configured, or offline mode is set")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model=self.model or settings.claude_model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


def build_voice() -> TemplateVoice | LayeredVoice:
    """Pick the best available voice, with the template as the floor.

    Order is deliberate: a configured open-source endpoint wins, because that
    is the helper's own setting; Anthropic is the fallback only because a key
    may already be present for genre labelling. If neither is configured the
    app still answers -- from a template, and it says so -- rather than going
    silent, which is the one outcome that makes it useless.
    """
    from ..config import get_settings

    settings = get_settings()
    if settings.chordcat_offline:
        return TemplateVoice()
    if settings.has_llm:
        return LayeredVoice(OpenAICompatibleVoice())
    if settings.has_anthropic:
        return LayeredVoice(ClaudeVoice())
    return TemplateVoice()
