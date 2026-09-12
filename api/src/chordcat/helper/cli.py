"""`python -m chordcat.helper.cli analyse <capture.json>`.

This is the v0 finish line, ahead of anything demo-facing: facts to node to
validated sentence, printed from a real recording.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from .analysis import run_all
from .concepts.graph import Choice, choose
from .concepts.schema import APPROVED, UNFILLED_DEVICE, load_nodes
from .converse import Response, TemplateVoice, build_voice
from .facts import FactSet
from .prepare import prepare
from .sources import FixtureSource


@dataclass(frozen=True, slots=True)
class TurnResult:
    facts: FactSet
    choice: Choice | None
    response: Response


def analyse_capture(path: Path, *, channel: int | None = None, live: bool = False) -> TurnResult:
    session = FixtureSource(path, channel=channel).load()
    facts = run_all(prepare(session)).supported()
    choice = choose(facts, session, load_nodes())
    if choice is None:
        return TurnResult(facts, None, Response("Not enough played yet to say anything.", True))
    voice = build_voice() if live else TemplateVoice()
    return TurnResult(facts, choice, voice.respond(facts, choice, session.user_text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chordcat-helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("analyse", help="print one turn for a recorded capture")
    run.add_argument("capture", type=Path)
    run.add_argument("--channel", type=int, default=None)
    run.add_argument("--live", action="store_true", help="use the model, not the template")

    sub.add_parser("tutor-todo", help="list nodes whose prose still needs writing")

    args = parser.parse_args(argv)

    if args.cmd == "tutor-todo":
        for node in load_nodes().values():
            gaps = []
            if node.status != APPROVED:
                gaps.append("draft prose")
            if node.on_device == UNFILLED_DEVICE:
                gaps.append("on_device (needs the manual)")
            if gaps:
                print(f"{node.id:28} {', '.join(gaps)}")
        return 0

    result = analyse_capture(args.capture, channel=args.channel, live=args.live)
    print(f"\nFACTS ({len(result.facts.facts)} the helper may assert)")
    for fact in result.facts:
        print(f"  {fact.id:32} {fact.value!r}  n={fact.n_observations}")
    if result.choice is not None:
        print(
            f"\nWHY THIS: {result.choice.node.id} is {result.choice.distance} step(s) "
            f"from {', '.join(result.choice.why) or 'what you played'}"
        )
        if not result.choice.measured:
            print("  (no reading for this -- absence is unobserved, not measured)")
        if result.choice.tied_with:
            print(f"  tied with: {', '.join(result.choice.tied_with)}")
        if result.choice.node.status != APPROVED:
            print("  (draft prose -- not for a demo)")
    print("\nNOTICED\n")
    print(result.response.text)
    if result.response.used_fallback:
        print("\n[templated turn -- no model used]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
