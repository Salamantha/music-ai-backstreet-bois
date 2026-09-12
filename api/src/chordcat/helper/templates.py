"""The turn, assembled from facts and node prose with no model involved.

This is the floor. If the model is unreachable, rate-limited, or keeps producing
sentences the validator rejects, the user still gets a true, useful turn -- it
just reads stiffly.
"""

from __future__ import annotations

from dataclasses import dataclass

from .concepts.graph import Choice
from .concepts.schema import UNFILLED_DEVICE
from .facts import FactSet


@dataclass(frozen=True, slots=True)
class Turn:
    notice: str
    suggestion: str
    what_it_means: str
    how_to: str

    def text(self) -> str:
        return "\n\n".join((self.notice, self.suggestion, self.what_it_means, self.how_to))


def render_turn(facts: FactSet, choice: Choice) -> Turn:
    return Turn(
        notice=_notice(facts),
        suggestion=f"One thing you have not tried: {choice.node.plain_name}.",
        what_it_means=" ".join(
            (choice.node.what_it_means, choice.node.what_it_does_to_the_sound)
        ),
        how_to=_how_to(choice),
    )


def _notice(facts: FactSet) -> str:
    """Observation first, and only from facts with enough behind them."""
    bits: list[str] = []
    key = facts.get("harmony.key_estimate")
    if key is not None:
        bits.append(f"You are sitting in {key.value}")

    chords = facts.by_kind("harmony.chord")
    if chords:
        shapes = list(dict.fromkeys(str(c.value) for c in chords))[:4]
        bits.append("moving through " + ", ".join(shapes))

    rhythm = facts.get("harmony.rhythm")
    if rhythm is not None:
        bits.append(f"with each chord lasting about {rhythm.value['mean_chord_s']} seconds")

    return (", ".join(bits) + ".") if bits else "Not enough played yet to see a pattern."


def _how_to(choice: Choice) -> str:
    if choice.node.on_device and choice.node.on_device != UNFILLED_DEVICE:
        return choice.node.on_device
    return "The steps for this on your device have not been written up yet."
