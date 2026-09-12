"""What changed since the last take.

Not an analyser: analysers read one take, this compares two fact sets. It runs
after ``run_all`` and its output is ordinary facts, which matters -- it means
the validator governs these claims exactly like any other, so the model can
only say what the diff actually found. "You've slowed right down" is a
measurement here, never an impression.
"""

from __future__ import annotations

from ..facts import Fact, FactSet

#: Below this, a difference is noise rather than a change worth remarking on.
#: Chord durations wobble take to take; a fifth is a deliberate shift.
REL_TOLERANCE = 0.20


def _dict(facts: FactSet, kind: str) -> dict:
    fact = facts.get(kind)
    return fact.value if fact is not None and isinstance(fact.value, dict) else {}


def _num(facts: FactSet, kind: str, key: str) -> float | None:
    value = _dict(facts, kind).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _moved(before: float, after: float) -> bool:
    if before == 0:
        return after != 0
    return abs(after - before) / abs(before) >= REL_TOLERANCE


def diff_facts(previous: FactSet, current: FactSet) -> list[Fact]:
    """Facts about the difference between two takes. Empty on the first turn."""
    if not previous.facts:
        return []

    out: list[Fact] = []

    was, now = previous.get("harmony.key_estimate"), current.get("harmony.key_estimate")
    if was is not None and now is not None and was.value != now.value:
        out.append(
            Fact(
                id="change.key#0", kind="change.key",
                value={"from": was.value, "to": now.value},
                confidence=min(was.confidence, now.confidence),
                n_observations=now.n_observations,
            )
        )

    for kind, key, name in (
        ("harmony.rhythm", "mean_chord_s", "change.harmonic_rhythm"),
        ("voicing.register_span", "span_semitones", "change.register_span"),
        ("perf.repetition", "repeat_rate", "change.repetition"),
        ("perf.velocity_stats", "spread", "change.dynamic_spread"),
    ):
        before, after = _num(previous, kind, key), _num(current, kind, key)
        if before is None or after is None or not _moved(before, after):
            continue
        out.append(
            Fact(
                id=f"{name}#0", kind=name,
                value={"from": before, "to": after,
                       "direction": "up" if after > before else "down"},
                n_observations=current.get(kind).n_observations,
            )
        )

    before_q = _dict(previous, "harmony.quality_counts")
    after_q = _dict(current, "harmony.quality_counts")
    fresh = sorted(set(after_q) - set(before_q))
    dropped = sorted(set(before_q) - set(after_q))
    if fresh or dropped:
        out.append(
            Fact(
                id="change.chord_types#0", kind="change.chord_types",
                value={"new": fresh, "gone": dropped},
                n_observations=sum(after_q.values()) if after_q else 0,
            )
        )

    before_n = _num(previous, "harmony.rhythm", "chords")
    after_n = _num(current, "harmony.rhythm", "chords")
    if before_n is not None and after_n is not None and _moved(before_n, after_n):
        out.append(
            Fact(
                id="change.chord_count#0", kind="change.chord_count",
                value={"from": int(before_n), "to": int(after_n)},
                n_observations=int(after_n),
            )
        )

    return out
