"""Choose which sub-progressions to ask Hooktheory about.

Hooktheory matches only *exact contiguous* progressions, so a whole take almost
never matches anything -- the useful queries are short windows. With a budget of
roughly a dozen requests per take (the account-wide limit is 10 requests per 10
seconds), which windows we pick and in what order is the difference between a
good match list and an empty one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .events import CpSequence, CpToken
from .cp import segments_without_holes

#: Longer windows are far more identifying, so they are worth more per hit.
LENGTH_WEIGHT: dict[int, float] = {5: 1.6, 4: 1.4, 3: 1.0, 2: 0.5, 1: 0.15}

RARITY_FLOOR = 0.5
RARITY_CEIL = 2.0
#: A rotation of a loop is slightly weaker evidence than the order as played:
#: where a musician *starts* a loop says something real about their sense of tonic.
ROTATION_DISCOUNT = 0.9


@dataclass(frozen=True, slots=True)
class Ngram:
    tokens: tuple[str, ...]
    multiplicity: int
    fidelity: float
    #: True when this ordering was produced by rotating a detected loop rather
    #: than played in this order.
    rotated: bool = False
    #: True when the window starts at the very first chord of the take.
    opens_take: bool = False

    @property
    def n(self) -> int:
        return len(self.tokens)

    @property
    def cp(self) -> str:
        return ",".join(self.tokens)


@dataclass(frozen=True, slots=True)
class NgramConfig:
    lengths: tuple[int, ...] = (4, 3, 2)
    max_loop_period: int = 4
    #: n=5 is attempted only for the single most-repeated run.
    try_five: bool = True


def detect_loop_period(tokens: Sequence[str], cfg: NgramConfig = NgramConfig()) -> int | None:
    """Smallest period repeating over at least two full cycles.

    One mismatch is tolerated for periods of four or more, because a player
    almost always varies something on the last repeat.
    """
    n = len(tokens)
    for p in range(1, n // 2 + 1):
        cycles = n // p
        if cycles < 2:
            continue
        mismatches = sum(
            1 for i in range(p, cycles * p) if tokens[i] != tokens[i % p]
        )
        allowed = 1 if p >= 4 else 0
        if mismatches <= allowed:
            return p
    return None


def _windows(tokens: Sequence[str], n: int) -> list[tuple[int, tuple[str, ...]]]:
    return [(i, tuple(tokens[i : i + n])) for i in range(len(tokens) - n + 1)]


def generate_ngrams(
    seq: CpSequence,
    cfg: NgramConfig = NgramConfig(),
) -> tuple[Ngram, ...]:
    """Generate candidate query windows, deduplicated with multiplicity.

    Windows never span a hole: a hole marks a chord we could not express or a key
    change, and joining across one would fabricate a progression that was never
    played.
    """
    runs = segments_without_holes(seq)
    if not runs:
        return ()

    # (tokens, rotated) -> [multiplicity, fidelity_sum, opens_take]
    acc: dict[tuple[tuple[str, ...], bool], list[float]] = {}

    def add(window: Sequence[CpToken], rotated: bool, opens: bool) -> None:
        key = (tuple(t.root_position_token for t in window), rotated)
        fidelity = min(t.fidelity for t in window)
        slot = acc.setdefault(key, [0.0, 0.0, 0.0])
        slot[0] += 1
        slot[1] += fidelity
        slot[2] = max(slot[2], 1.0 if opens else 0.0)

    longest_run = max(runs, key=len)

    for run in runs:
        tokens = [t.root_position_token for t in run]
        period = detect_loop_period(tokens, cfg)

        lengths = [n for n in cfg.lengths if n <= len(run)]
        if cfg.try_five and run is longest_run and len(run) >= 5:
            lengths = [5, *lengths]
        if not lengths:
            # The run is shorter than the smallest configured window -- a single
            # chord, or a two-chord fragment between holes. Query it whole
            # rather than returning nothing. A one-chord query is weak evidence
            # (`LENGTH_WEIGHT` scores it accordingly) but it is real: it finds
            # every song that uses that chord, which is the honest answer to
            # "what does this chord belong to".
            lengths = [len(run)]

        for n in lengths:
            if n > len(run):
                continue
            for start, _ in _windows(tokens, n):
                add(run[start : start + n], False, start == 0 and run is runs[0])

        if period is not None and period <= cfg.max_loop_period:
            # A loop is catalogued by Hooktheory from wherever the *song's*
            # section begins, so a IV-I-V-vi loop is very likely indexed as
            # I-V-vi-IV. Query the other rotations too.
            cycle = run[:period]
            for shift in range(1, period):
                rotated = cycle[shift:] + cycle[:shift]
                add(rotated, True, False)
            # Circular windows so the wrap-around transition is not lost.
            if len(run) > period:
                doubled = run + run[:period]
                for n in cfg.lengths:
                    if n > period:
                        continue
                    for start in range(len(run), len(run) + period - n + 1):
                        add(doubled[start : start + n], True, False)

    out = [
        Ngram(
            tokens=tokens,
            multiplicity=int(slot[0]),
            fidelity=slot[1] / slot[0],
            rotated=rotated,
            opens_take=bool(slot[2]),
        )
        for (tokens, rotated), slot in acc.items()
    ]
    return tuple(out)


def rarity(
    ngram: Ngram, transition_prob: dict[tuple[str, ...], float] | None
) -> float:
    """How surprising this progression is, from the global chord-transition tree.

    Matching I-V-vi-IV means almost nothing; matching bVI-bVII-i-V means a great
    deal. Without a warmed tree this returns 1.0 and every progression looks
    equally ordinary, which is why warming matters before launch.
    """
    if not transition_prob:
        return 1.0
    logp = 0.0
    for i in range(1, len(ngram.tokens)):
        prefix = ngram.tokens[:i]
        p = transition_prob.get((*prefix, ngram.tokens[i]))
        if p and p > 0:
            logp += math.log(p)
    if logp == 0.0:
        return 1.0
    return max(RARITY_FLOOR, min(RARITY_CEIL, -logp / max(len(ngram.tokens) - 1, 1)))


def priority(
    ngram: Ngram, transition_prob: dict[tuple[str, ...], float] | None = None
) -> float:
    """Query order. Rarest long windows first -- the most identifying evidence."""
    base = LENGTH_WEIGHT.get(ngram.n, 0.1)
    mult = math.log1p(ngram.multiplicity)
    score = base * mult * rarity(ngram, transition_prob) * ngram.fidelity
    return score * (ROTATION_DISCOUNT if ngram.rotated else 1.0)


def prioritize(
    ngrams: Sequence[Ngram],
    transition_prob: dict[tuple[str, ...], float] | None = None,
) -> tuple[Ngram, ...]:
    return tuple(
        sorted(ngrams, key=lambda g: (-priority(g, transition_prob), g.cp))
    )
