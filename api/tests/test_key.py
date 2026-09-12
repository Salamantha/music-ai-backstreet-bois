"""Key and mode detection."""

from __future__ import annotations

import pytest

from chordcat.domain.key import detect_key
from chordcat.domain.pitch import key_name

from conftest import analyse_offline

C, G, Am, F = (60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)
Em, Dm, Bb, Ab = (64, 67, 71), (62, 65, 69), (58, 62, 65), (56, 60, 63)


@pytest.mark.parametrize(
    "progression,expected",
    [
        ([C, G, Am, F], "C major"),
        ([Am, F, C, G], "A minor"),
        ([Em, C, G, (62, 66, 69)], "E minor"),
        ([G, F, C, G], "G mixolydian"),
    ],
)
def test_detects_common_keys(progression, expected):
    estimate = detect_key(analyse_offline(progression * 2))
    assert key_name(estimate.key.tonic_pc, estimate.key.mode) == expected


def test_relative_major_is_always_offered_as_an_alternative():
    """The relative key shares a pitch-class set, so it is never ruled out.

    The override path depends on this: whichever way detection falls, the user
    must be one tap from the other reading.
    """
    estimate = detect_key(analyse_offline([Am, F, C, G] * 2))
    names = {key_name(k.tonic_pc, k.mode) for k, _ in estimate.alternatives}
    assert "C major" in names


def test_confidence_is_usable_not_flat():
    """A softmax over 84 candidates at T=1 reports ~6% for a clear winner."""
    estimate = detect_key(analyse_offline([C, G, Am, F] * 2))
    assert estimate.confidence > 0.15


def test_empty_input_does_not_raise():
    estimate = detect_key([])
    assert estimate.confidence == 0.0


def test_dorian_beats_its_relative_minor_on_a_dorian_vamp():
    """D dorian and D minor differ only in the sixth degree."""
    estimate = detect_key(analyse_offline([Dm, G, Dm, G] * 2))
    candidates = {key_name(estimate.key.tonic_pc, estimate.key.mode)} | {
        key_name(k.tonic_pc, k.mode) for k, _ in estimate.alternatives
    }
    assert "D dorian" in candidates
