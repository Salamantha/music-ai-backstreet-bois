"""Fact producers, held in a list so new ones cost nothing above this layer.

The melody seam is exactly this: melody arrives later as its own module with
`melody.*` fact kinds, appends itself here, and traversal, ranking, validation
and conversation are untouched.
"""

from __future__ import annotations

from collections.abc import Callable

from ..facts import Fact, FactSet
from ..prepare import AnalysisInput

Analyser = Callable[[AnalysisInput], list[Fact]]

ANALYSERS: list[Analyser] = []


def register(fn: Analyser) -> Analyser:
    ANALYSERS.append(fn)
    return fn


def run_all(inp: AnalysisInput) -> FactSet:
    facts: list[Fact] = []
    for analyser in ANALYSERS:
        facts.extend(analyser(inp))
    return FactSet(tuple(facts))


from . import harmony, perf, voicing  # noqa: E402,F401  (registration by import)
