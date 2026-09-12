"""Taste profile construction and similarity."""

from __future__ import annotations

from chordcat.domain.events import HarmonicFeatures, Key
from chordcat.domain.profile import (
    build_profile, cosine, harmonic_features, jaccard_overlap, similarity,
)

from conftest import analyse_offline

C, G, Am, F = (60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)
Ab, Bb, G7 = (56, 60, 63), (58, 62, 65), (55, 59, 62, 65)


def profile(genres, artists, harmonic=None):
    return build_profile(
        genres, artists, {"2010s": 1.0}, {"melancholic": 1.0},
        harmonic or HarmonicFeatures(modal_usage={"major": 1.0}),
    )


def test_self_similarity_is_one():
    p = profile({"indie rock": 2.0}, {"Big Thief": 1.0})
    assert similarity(p, p).total == 1.0


def test_similarity_is_symmetric():
    a = profile({"indie rock": 2.0}, {"Big Thief": 1.0})
    b = profile({"folk": 1.0, "indie rock": 1.0}, {"Phoebe Bridgers": 1.0})
    assert similarity(a, b).total == similarity(b, a).total


def test_similar_profiles_beat_dissimilar_ones():
    me = profile({"indie rock": 3.0, "folk": 2.0}, {"Big Thief": 2.0})
    near = profile({"indie rock": 2.0, "folk": 3.0}, {"Big Thief": 1.0})
    far = profile({"edm": 4.0, "house": 2.0}, {"Avicii": 3.0})
    assert similarity(me, near).total > similarity(me, far).total


def test_missing_fields_do_not_raise():
    empty = build_profile({}, {}, {}, {}, HarmonicFeatures())
    populated = profile({"pop": 1.0}, {"Adele": 1.0})
    assert 0.0 <= similarity(empty, populated).total <= 1.0


def test_shared_artists_are_surfaced_for_the_explanation():
    a = profile({"folk": 1.0}, {"Big Thief": 2.0, "Radiohead": 1.0})
    b = profile({"folk": 1.0}, {"Big Thief": 1.0, "Mitski": 1.0})
    assert "Big Thief" in similarity(a, b).shared_artists


def test_cosine_and_jaccard_edge_cases():
    assert cosine({}, {"a": 1.0}) == 0.0
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0
    assert jaccard_overlap({}, {}) == 0.0
    assert jaccard_overlap({"a": 1.0}, {"a": 1.0}) == 1.0


def test_harmonic_features_need_no_song_match():
    """This is what keeps matching alive when Hooktheory returns nothing."""
    chords = analyse_offline([C, Ab, Bb, C])
    h = harmonic_features(chords, Key(0, "major"))
    assert h.borrowed_rate > 0.0
    assert h.chord_variety > 0.0
    assert h.mean_chord_duration_s > 0.0


def test_seventh_density_tracks_seventh_chords():
    plain = harmonic_features(analyse_offline([C, G, Am, F]), Key(0, "major"))
    sevenths = harmonic_features(analyse_offline([G7, G7]), Key(0, "major"))
    assert sevenths.seventh_density > plain.seventh_density


def test_authentic_cadence_is_detected():
    h = harmonic_features(analyse_offline([F, G, C]), Key(0, "major"))
    assert h.cadence_profile.get("authentic", 0) > 0
