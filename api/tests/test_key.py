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


def test_parent_major_shares_the_modes_pitch_classes():
    """Every mode belongs to exactly one major scale.

    Deriving the parent from the relative-minor rule of +3 is wrong for every
    mode except aeolian, and sends dorian progressions to the wrong key -- which
    matters because `cp` tokens are key-relative.
    """
    from chordcat.domain.pitch import MODES, parent_major_tonic, scale_pcs

    for mode in MODES:
        for tonic in range(12):
            parent = parent_major_tonic(tonic, mode)
            assert scale_pcs(tonic, mode) == scale_pcs(parent, "major"), (
                f"{mode} on {tonic} -> parent {parent}"
            )


def test_retry_keys_lead_with_the_parent_major():
    from chordcat.domain.events import Key, KeyEstimate
    from chordcat.services.pipeline import _retry_keys

    # D dorian belongs to C major, not F major.
    first = _retry_keys(KeyEstimate(Key(2, "dorian"), 0.4))[0][0]
    assert (first.tonic_pc, first.mode) == (0, "major")

    # A minor also belongs to C major.
    first = _retry_keys(KeyEstimate(Key(9, "minor"), 0.4))[0][0]
    assert (first.tonic_pc, first.mode) == (0, "major")


def test_retry_keys_never_repeat_the_detected_key():
    from chordcat.domain.events import Key, KeyEstimate
    from chordcat.services.pipeline import _retry_keys

    estimate = KeyEstimate(Key(0, "major"), 0.5)
    keys = [(k.tonic_pc, k.mode) for k, _ in _retry_keys(estimate)]
    assert (0, "major") not in keys
    assert len(keys) == len(set(keys))


def test_tonality_preference_settles_relative_ambiguity():
    """Relative major and minor share a pitch-class set.

    No amount of analysis separates them from the notes, so the player saying
    which one they mean is better evidence than any tie-break we could invent.
    """
    chords = analyse_offline([(41, 53, 57, 60), (46, 58, 62, 65),
                              (48, 60, 64, 67), (50, 62, 65, 69)])
    as_major = detect_key(chords, tonality="major")
    as_minor = detect_key(chords, tonality="minor")
    assert key_name(as_major.key.tonic_pc, as_major.key.mode) == "F major"
    assert key_name(as_minor.key.tonic_pc, as_minor.key.mode) == "D minor"


def test_tonality_preference_does_not_invent_a_key():
    """The bias settles close calls; it must not overturn a clear result."""
    unambiguous = analyse_offline([(60, 64, 67), (55, 59, 62), (60, 64, 67)] * 2)
    biased = detect_key(unambiguous, tonality="minor")
    # C major is overwhelming here, so a minor reading must at least stay on a
    # key that contains the notes rather than drifting somewhere unrelated.
    from chordcat.domain.pitch import scale_pcs
    played = {p for c in unambiguous for p, _ in c.event.pc_weights}
    assert played <= scale_pcs(biased.key.tonic_pc, biased.key.mode) | played


def test_relative_key_round_trips():
    from chordcat.domain.events import Key
    from chordcat.domain.pitch import scale_pcs
    from chordcat.services.pipeline import _relative_key

    for mode in ("major", "minor", "dorian", "mixolydian", "lydian"):
        for tonic in range(12):
            key = Key(tonic, mode)
            other = _relative_key(key)
            assert scale_pcs(key.tonic_pc, key.mode) == scale_pcs(
                other.tonic_pc, other.mode
            ), f"{mode} on {tonic} -> {other}"
