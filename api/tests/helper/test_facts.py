from __future__ import annotations

from chordcat.helper.facts import MIN_OBSERVATIONS, Fact, FactSet


def make(kind: str, value, n: int = 5) -> Fact:
    return Fact(id=f"{kind}#0", kind=kind, value=value, n_observations=n)


def test_namespace_is_the_part_before_the_dot():
    assert make("harmony.chord", "Cmaj7").namespace == "harmony"


def test_lookup_by_kind_and_by_id():
    fs = FactSet((make("harmony.chord", "Cmaj7"), make("perf.density", 2.1)))
    assert fs.get("harmony.chord").value == "Cmaj7"
    assert fs.by_id("perf.density#0").value == 2.1
    assert fs.get("voicing.inversions") is None


def test_thin_evidence_is_withheld_not_asserted():
    """Two bars is not a habit."""
    fs = FactSet((make("harmony.cadence", "authentic", n=1), make("harmony.chord", "C", n=9)))
    assert {f.kind for f in fs.supported().facts} == {"harmony.chord"}
    assert MIN_OBSERVATIONS > 1


def test_ids_are_unique_within_a_set():
    fs = FactSet((make("harmony.chord", "C"), make("harmony.chord", "F")))
    assert len(fs.ids()) == 1  # same id -- the builder must disambiguate
