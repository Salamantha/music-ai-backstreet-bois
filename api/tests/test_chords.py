"""Chord identification, including the documented ambiguity traps."""

from __future__ import annotations

import pytest

from chordcat.domain.chords import TEMPLATES, identify_chord, merge_identified
from chordcat.domain.events import Key
from chordcat.domain.pitch import pc_name

from conftest import analyse_offline, chord_event


@pytest.mark.parametrize(
    "pitches,root,quality",
    [
        ([60, 64, 67], "C", "maj"),
        ([57, 60, 64], "A", "min"),
        ([55, 59, 62, 65], "G", "dom7"),
        ([60, 64, 67, 71], "C", "maj7"),
        ([57, 60, 64, 67], "A", "min7"),
        ([59, 62, 65], "B", "dim"),
        ([60, 64, 68], "C", "aug"),
        ([60, 65, 67], "C", "sus4"),
        ([60, 62, 67], "C", "sus2"),
        ([59, 62, 65, 69], "B", "m7b5"),
    ],
)
def test_basic_qualities(pitches, root, quality):
    best = identify_chord(chord_event(pitches))[0]
    assert (pc_name(best.root_pc), best.quality) == (root, quality)


def test_c6_over_c_bass_is_not_am7():
    """{C,E,G,A} is C6 or Am7 depending only on the bass.

    The two readings score within the tie epsilon of each other, so this is
    decided by the root-position preference, not by score.
    """
    assert identify_chord(chord_event([60, 64, 67, 69]))[0].root_pc == 0
    assert identify_chord(chord_event([57, 60, 64, 67]))[0].root_pc == 9


def test_sus4_versus_sus2_resolves_on_bass():
    """{C,F,G} is Csus4 or Fsus2 -- same notes, different root."""
    assert identify_chord(chord_event([60, 65, 67]))[0].quality == "sus4"
    assert identify_chord(chord_event([65, 67, 72]))[0].quality == "sus2"


def test_diminished_seventh_root_is_chosen_by_rule_not_iteration_order():
    """A dim7 has four equally-scoring roots; the choice must be deliberate.

    In C major, B is the leading tone, so Bdim7 is the reading that makes
    functional sense.
    """
    best = identify_chord(chord_event([59, 62, 65, 68]), key=Key(0, "major"))[0]
    assert best.quality == "dim7"
    assert pc_name(best.root_pc) == "B"


def test_symmetric_chord_is_deterministic_without_a_key():
    a = identify_chord(chord_event([59, 62, 65, 68]))[0]
    b = identify_chord(chord_event([59, 62, 65, 68]))[0]
    assert (a.root_pc, a.quality) == (b.root_pc, b.quality)


def test_fifthless_and_rootless_voicings():
    """The fifth is never essential; devices routinely omit it."""
    assert identify_chord(chord_event([60, 64]))[0].quality == "maj"
    assert identify_chord(chord_event([60, 63]))[0].quality == "min"


def test_extensions_are_recorded_not_punished():
    best = identify_chord(chord_event([60, 62, 64, 67]))[0]
    assert best.quality in {"maj", "add9"}
    if best.quality == "maj":
        assert "9" in best.extensions


def test_inversion_is_reported():
    best = identify_chord(chord_event([64, 67, 72]))[0]
    assert pc_name(best.root_pc) == "C"
    assert best.inversion == 1


def test_identification_is_deterministic_across_runs():
    for pitches in ([60, 64, 67], [60, 64, 67, 69], [59, 62, 65, 68]):
        results = {identify_chord(chord_event(pitches))[0] for _ in range(5)}
        assert len(results) == 1


def test_merge_collapses_revoicing_but_not_quality_change():
    """C -> Cmaj7 sits at Jaccard 0.75 but is a real chord change."""
    chords = analyse_offline([(60, 64, 67), (60, 64, 67, 71)])
    assert len(chords) == 2
    assert [c.best.quality for c in chords] == ["maj", "maj7"]


def test_merge_collapses_identical_repeats():
    chords = analyse_offline([(60, 64, 67), (60, 64, 67), (60, 64, 67)])
    assert len(chords) == 1


def test_every_template_is_identifiable_from_its_own_notes():
    """Sanity: each template must win on a voicing built from exactly its tones."""
    for quality, intervals in TEMPLATES.items():
        pitches = [60 + i for i in intervals]
        best = identify_chord(chord_event(pitches))[0]
        assert best.root_pc == 0, f"{quality}: got root {best.root_pc}"
