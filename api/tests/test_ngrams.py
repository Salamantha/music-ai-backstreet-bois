"""Window selection for Hooktheory queries."""

from __future__ import annotations

from chordcat.domain.events import CpToken, Hole
from chordcat.domain.ngrams import (
    Ngram, detect_loop_period, generate_ngrams, prioritize, priority, rarity,
)


def toks(*names):
    return tuple(CpToken(n, n, i, 1.0, n) for i, n in enumerate(names))


def test_detects_loop_period():
    assert detect_loop_period(["4", "1", "5", "6"] * 3) == 4
    assert detect_loop_period(["1", "5"] * 4) == 2
    assert detect_loop_period(["1", "4", "5", "2", "6"]) is None


def test_loop_tolerates_one_variation_on_longer_periods():
    assert detect_loop_period(["4", "1", "5", "6", "4", "1", "5", "2"]) == 4


def test_rotations_of_a_loop_are_generated():
    """Hooktheory indexes a loop from wherever the song's section starts, so a
    IV-I-V-vi loop is very likely catalogued as I-V-vi-IV."""
    grams = {g.cp for g in generate_ngrams(toks(*(["4", "1", "5", "6"] * 3)))}
    for rotation in ("4,1,5,6", "1,5,6,4", "5,6,4,1", "6,4,1,5"):
        assert rotation in grams


def test_windows_never_span_a_hole():
    seq = (*toks("1", "5"), Hole(2, "X", "unmappable"), *toks("6", "4"))
    grams = {g.cp for g in generate_ngrams(seq)}
    assert "1,5" in grams and "6,4" in grams
    assert not any("5,6" in cp for cp in grams)


def test_multiplicity_is_counted():
    """A window played four times is much stronger evidence than one played once.

    Rotated and as-played variants are tracked separately, so take the maximum
    across entries sharing a cp string.
    """
    grams = generate_ngrams(toks(*(["1", "5"] * 4)))
    assert max(g.multiplicity for g in grams if g.cp == "1,5") >= 3


def test_longer_windows_outrank_shorter_ones_all_else_equal():
    four = Ngram(("1", "5", "6", "4"), 1, 1.0)
    two = Ngram(("1", "5"), 1, 1.0)
    assert priority(four) > priority(two)


def test_rotations_are_discounted_against_the_order_as_played():
    played = Ngram(("1", "5", "6", "4"), 2, 1.0, rotated=False)
    rotated = Ngram(("1", "5", "6", "4"), 2, 1.0, rotated=True)
    assert priority(played) > priority(rotated)


def test_rarity_is_neutral_without_a_warm_transition_tree():
    assert rarity(Ngram(("1", "5"), 1, 1.0), None) == 1.0


def test_rare_progressions_outrank_common_ones():
    common = Ngram(("1", "5", "6", "4"), 1, 1.0)
    rare = Ngram(("B6", "B7", "B1", "5"), 1, 1.0)
    table = {
        ("1", "5"): 0.40, ("1", "5", "6"): 0.35, ("1", "5", "6", "4"): 0.40,
        ("B6", "B7"): 0.01, ("B6", "B7", "B1"): 0.02, ("B6", "B7", "B1", "5"): 0.01,
    }
    assert priority(rare, table) > priority(common, table)


def test_prioritize_is_deterministic():
    seq = toks(*(["4", "1", "5", "6"] * 3))
    assert [g.cp for g in prioritize(generate_ngrams(seq))] == \
           [g.cp for g in prioritize(generate_ngrams(seq))]
