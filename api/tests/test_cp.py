"""Hooktheory `cp` token conversion."""

from __future__ import annotations

import pytest

from chordcat.domain.cp import (
    CP_TABLE,
    DEAD_TOKENS,
    CpConfig,
    progression_to_cp,
    segments_without_holes,
    to_cp,
)
from chordcat.domain.events import Hole, Key

from conftest import analyse_offline

C, G, Am, F = (60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)
E, G7, Ab, Bb = (64, 68, 71), (55, 59, 62, 65), (56, 60, 63), (58, 62, 65)


def cps(progression, key):
    seq = progression_to_cp(analyse_offline(progression), key)
    return [t.root_position_token for t in seq if not isinstance(t, Hole)]


def test_no_dead_token_is_reachable():
    """The table is built by enumeration, so this must hold by construction."""
    assert {e.token for e in CP_TABLE.values()} & DEAD_TOKENS == set()


def test_every_token_round_trips_to_its_meaning():
    for (offset, quality, seventh), entry in CP_TABLE.items():
        assert entry.offset % 12 == offset
        assert entry.quality == quality
        assert entry.seventh == seventh


def test_axis_progression_in_c_major():
    assert cps([C, G, Am, F], Key(0, "major")) == ["1", "5", "6", "4"]


def test_minor_progression_uses_b_prefix():
    assert cps([Am, F, C, G], Key(9, "minor")) == ["B1", "B6", "B3", "B7"]


def test_secondary_dominant_prefers_v_of_vi_over_iv_of_vii():
    """E major in C is V/vi. Both spellings resolve to the same chord, and
    tie-breaking them alphabetically would pick the wrong one."""
    assert cps([C, E, Am], Key(0, "major")) == ["1", "5/6", "6"]


def test_borrowed_chords():
    assert cps([C, Ab, Bb, C], Key(0, "major")) == ["1", "B6", "B7", "1"]


def test_sus_chords_resolve_to_a_triad_not_a_dominant_seventh():
    """7sus4 is in both the sus and seventh families; the sus reading wins.

    Otherwise Csus4/G7sus4 resolves to a spurious V7.
    """
    seq = progression_to_cp(analyse_offline([(60, 65, 67), C]), Key(0, "major"))
    tokens = [t.root_position_token for t in seq if not isinstance(t, Hole)]
    assert tokens == ["1", "1"]


def test_seventh_chords():
    assert cps([C, G7], Key(0, "major")) == ["1", "57"]


def test_inversions_are_stripped_by_default():
    """Exact contiguous matching plus inversion suffixes kills recall."""
    seq = progression_to_cp(analyse_offline([(64, 67, 72)]), Key(0, "major"))
    token = next(t for t in seq if not isinstance(t, Hole))
    assert token.token == "1"


def test_inversions_are_kept_when_asked_for():
    seq = progression_to_cp(
        analyse_offline([(64, 67, 72)]), Key(0, "major"),
        CpConfig(strip_inversions=False),
    )
    token = next(t for t in seq if not isinstance(t, Hole))
    assert token.token == "16"


def test_holes_are_hard_barriers():
    """No window may span a chord we could not express."""
    from chordcat.domain.events import CpToken

    seq = (
        CpToken("1", "1", 0, 1.0, "I"),
        CpToken("5", "5", 1, 1.0, "V"),
        Hole(2, "X", "unmappable"),
        CpToken("6", "6", 3, 1.0, "vi"),
    )
    runs = segments_without_holes(seq)
    assert [[t.token for t in run] for run in runs] == [["1", "5"], ["6"]]
