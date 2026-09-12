"""The truth layer's output format.

Every fact carries how much evidence it rests on. That is not bookkeeping: a
helper that calls two bars a habit is the fastest way to lose a musician, and
the easiest thing for a judge to puncture.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Below this, the helper says "not enough yet" rather than asserting a pattern.
MIN_OBSERVATIONS = 3


@dataclass(frozen=True, slots=True)
class Fact:
    id: str
    kind: str
    value: Any
    confidence: float = 1.0
    #: Indices into the identified-chord sequence that produced this fact.
    evidence: tuple[int, ...] = ()
    n_observations: int = 0

    @property
    def namespace(self) -> str:
        return self.kind.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class FactSet:
    facts: tuple[Fact, ...] = ()

    def by_kind(self, kind: str) -> tuple[Fact, ...]:
        return tuple(f for f in self.facts if f.kind == kind)

    def get(self, kind: str) -> Fact | None:
        found = self.by_kind(kind)
        return found[0] if found else None

    def by_id(self, fact_id: str) -> Fact | None:
        return next((f for f in self.facts if f.id == fact_id), None)

    def ids(self) -> frozenset[str]:
        return frozenset(f.id for f in self.facts)

    def supported(self, minimum: int = MIN_OBSERVATIONS) -> FactSet:
        return FactSet(tuple(f for f in self.facts if f.n_observations >= minimum))

    def __iter__(self):
        return iter(self.facts)
