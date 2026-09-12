"""Nothing reaches the user that the truth layer cannot account for.

Extracts every chord, key and numeric claim from generated text and asserts each
one against the FactSet or the chosen node's own prose. A miss is a rejection,
not a warning -- the caller regenerates, then falls back to a template.

Deliberately strict in one direction only. It can reject a sentence that was
actually fine, and that is the cheap error. Letting through a chord the user
never played is the expensive one, because this user cannot catch it themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .concepts.schema import ConceptNode
from .facts import FactSet

QUALITIES = "maj7|min7|m7b5|dim7|mMaj7|7sus4|sus2|sus4|maj|min|dim|aug|m7|m|7"
CHORD = re.compile(rf"\b([A-G][#b]?)({QUALITIES})?\b")
MODE_WORDS = ("major", "minor", "dorian", "phrygian", "lydian", "mixolydian", "locrian")
KEY = re.compile(rf"\b([A-G][#b]?)\s+({'|'.join(MODE_WORDS)})\b", re.I)
NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
#: Our own fact ids -- `perf.velocity_stats#0` and friends. The prompt lists
#: them so claims can be traced, and a model will happily quote one straight at
#: the user. That is machine jargon in a tool whose whole promise is plain
#: language, so it is rejected rather than merely discouraged.
FACT_ID = re.compile(r"\b[a-z]+\.[a-z_]+(?:#\d+)?\b")


@dataclass(frozen=True, slots=True)
class Rejection:
    claim: str
    reason: str


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    rejections: tuple[Rejection, ...] = ()


def _strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for k, v in value.items():
            out.append(str(k))
            out.extend(_strings(v))
        return out
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return [str(value)]


def _node_text(node: ConceptNode) -> str:
    return " ".join(
        (node.plain_name, node.what_it_means, node.what_it_does_to_the_sound,
         node.when_it_helps, node.common_mistake, node.on_device)
    )


def validate(text: str, facts: FactSet, node: ConceptNode) -> Verdict:
    blob = " ".join(s for f in facts for s in _strings(f.value))
    node_text = _node_text(node)

    chords = {m.group(0) for m in CHORD.finditer(blob)}
    keys = {m.group(0).lower() for m in KEY.finditer(blob)}
    numbers = set(NUMBER.findall(blob)) | set(NUMBER.findall(node_text))
    # Rounded forms of a measured value read naturally and mean the same thing.
    for n in list(numbers):
        if "." in n:
            numbers.add(str(int(float(n))))
            numbers.add(str(round(float(n))))

    bad: list[Rejection] = []

    keyed_spans = [m.span() for m in KEY.finditer(text)]
    for match in KEY.finditer(text):
        if match.group(0).lower() not in keys:
            bad.append(Rejection(match.group(0), "key not in the analysis"))

    for match in CHORD.finditer(text):
        if any(s <= match.start() < e for s, e in keyed_spans):
            continue  # already judged as part of a key name
        if match.group(0) not in chords and match.group(0) not in node_text:
            bad.append(Rejection(match.group(0), "chord not in the FactSet"))

    for leaked in FACT_ID.findall(text):
        bad.append(Rejection(leaked, "internal fact id leaked into the answer"))

    for number in NUMBER.findall(text):
        if number not in numbers:
            bad.append(Rejection(number, "number not backed by a fact"))

    return Verdict(ok=not bad, rejections=tuple(bad))
