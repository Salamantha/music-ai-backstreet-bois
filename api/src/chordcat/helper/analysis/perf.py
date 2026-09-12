"""How it was played: loudness, pace, and whether it repeats."""

from __future__ import annotations

from collections import Counter

from ..facts import Fact
from ..prepare import AnalysisInput
from . import register


@register
def velocity_stats(inp: AnalysisInput) -> list[Fact]:
    vels = [c.event.velocity_mean for c in inp.chords]
    if not vels:
        return []
    mean = sum(vels) / len(vels)
    return [
        Fact(
            id="perf.velocity_stats#0",
            kind="perf.velocity_stats",
            value={"mean": round(mean, 1), "spread": round(max(vels) - min(vels), 1)},
            n_observations=len(vels),
        )
    ]


@register
def density(inp: AnalysisInput) -> list[Fact]:
    minutes = (inp.session.elapsed_ms or 0.0) / 60_000
    if not inp.chords or minutes <= 0:
        return []
    return [
        Fact(
            id="perf.density#0",
            kind="perf.density",
            value={"chords_per_minute": round(len(inp.chords) / minutes, 1)},
            n_observations=len(inp.chords),
        )
    ]


@register
def repetition(inp: AnalysisInput) -> list[Fact]:
    """How much of the take is the same chord shape coming back around.

    Deliberately crude: a real loop detector is a different problem, and the
    helper only needs to know whether it is looking at a habit or at noise.
    """
    if len(inp.chords) < 4:
        return []
    shapes = Counter((c.best.root_pc, c.best.quality) for c in inp.chords)
    repeated = sum(n for n in shapes.values() if n > 1)
    return [
        Fact(
            id="perf.repetition#0",
            kind="perf.repetition",
            value={
                "repeat_rate": round(repeated / len(inp.chords), 2),
                "distinct_shapes": len(shapes),
            },
            n_observations=len(inp.chords),
        )
    ]
