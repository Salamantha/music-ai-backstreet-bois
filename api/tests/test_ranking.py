"""Scoring and artist rollup."""

from __future__ import annotations

from chordcat.domain.events import SongHit
from chordcat.domain.ngrams import Ngram
from chordcat.domain.ranking import (
    NgramResult, normalize_name, rollup_artists, score_songs,
)


def hit(artist, song, section="Chorus"):
    return SongHit(artist, song, section, "http://example.test")


def test_normalize_name():
    assert normalize_name("The Beatles") == "beatles"
    assert normalize_name("Beyoncé") == "beyonce"
    assert normalize_name("AC/DC") == "ac dc"
    assert normalize_name("  Weezer ") == "weezer"


def test_rare_progression_outweighs_a_cliche():
    """Matching I-V-vi-IV means little; matching a rare loop means a lot."""
    common = Ngram(("1", "5", "6", "4"), 3, 1.0)
    rare = Ngram(("b6", "b7", "b1", "5"), 1, 1.0)
    songs = score_songs([
        NgramResult(common, (hit("Cliche Band", "Four Chords"),), total_hits=1500),
        NgramResult(rare, (hit("Rare Band", "Odd Loop"),), total_hits=5),
    ])
    by_artist = {s.artist: s.score for s in songs}
    assert by_artist["Rare Band"] > by_artist["Cliche Band"]


def test_multiple_sections_help_but_are_capped():
    """One song matching in six sections must not swamp six different songs."""
    g = Ngram(("1", "5", "6", "4"), 1, 1.0)
    many = score_songs([
        NgramResult(g, tuple(
            hit("A", "Song", s)
            for s in ("Verse", "Chorus", "Bridge", "Intro", "Outro", "Solo")
        ), total_hits=20),
    ])
    one = score_songs([NgramResult(g, (hit("A", "Song"),), total_hits=20)])
    ratio = many[0].score / one[0].score
    assert 1.0 < ratio <= 6.0


def test_artist_volume_is_damped():
    """A large catalogue should not win on breadth alone."""
    g = Ngram(("1", "5", "6", "4"), 1, 1.0)
    songs = score_songs([
        NgramResult(g, (
            *(hit("Prolific", f"Song {i}") for i in range(8)),
            hit("Focused", "Only Song"),
        ), total_hits=20),
    ])
    artists = {a.artist: a.score for a in rollup_artists(songs)}
    assert artists["Prolific"] < 8 * artists["Focused"]


def test_empty_results_are_safe():
    assert score_songs([]) == ()
    assert rollup_artists([]) == ()
