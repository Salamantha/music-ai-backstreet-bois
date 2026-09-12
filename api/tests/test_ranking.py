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


def test_songs_are_ranked_by_how_much_of_them_you_played():
    """The Match column has to explain the order, or it reads as arbitrary.

    A blended relevance score alone put a 36% match above a 100% one.
    """
    from chordcat.domain.events import SongHit

    g = Ngram(("i", "ii"), 1, 1.0)
    partial = SongHit("A", "Partial", "Verse", "u", song_chords=("i", "ii", "V", "IV"))
    whole = SongHit("B", "Whole", "Verse", "u", song_chords=("i", "ii"))
    songs = score_songs(
        [NgramResult(g, (partial, whole), total_hits=2)],
        coverage={("a", "partial"): 0.5, ("b", "whole"): 1.0},
    )
    assert [s.song for s in songs] == ["Whole", "Partial"]


def test_songs_without_chord_data_sort_after_measurable_ones():
    """Trends results carry no chords, so there is nothing to measure."""
    from chordcat.domain.events import SongHit

    g = Ngram(("i", "ii"), 1, 1.0)
    measured = SongHit("A", "Measured", "Verse", "u", song_chords=("i", "ii"))
    unmeasured = SongHit("B", "Unmeasured", "Verse", "u")
    songs = score_songs(
        [NgramResult(g, (measured, unmeasured), total_hits=2)],
        coverage={("a", "measured"): 1.0},
    )
    assert [s.song for s in songs] == ["Measured", "Unmeasured"]


def test_empty_results_are_safe():
    assert score_songs([]) == ()
    assert rollup_artists([]) == ()


class TestGenreFilter:
    def songs(self):
        from chordcat.domain.events import SongHit
        return [
            SongHit("Arctic Monkeys", "505", "Chorus", "u",
                    genres=("rock", "alternative", "indie rock")),
            SongHit("Avicii", "Levels", "Chorus", "u", genres=("edm", "house")),
            SongHit("Nobody", "Unlabelled", "Verse", "u", genres=()),
        ]

    def test_no_filter_keeps_everything(self):
        from chordcat.domain.ranking import filter_songs_by_genre
        assert len(filter_songs_by_genre(self.songs(), [])) == 3

    def test_keeps_songs_matching_any_selected_genre(self):
        from chordcat.domain.ranking import filter_songs_by_genre
        kept = filter_songs_by_genre(self.songs(), ["rock"])
        assert [s.song for s in kept] == ["505"]

    def test_unlabelled_songs_are_excluded_while_filtering(self):
        """Unknown is not a match. Keeping them would quietly reintroduce
        exactly the material the filter was meant to remove."""
        from chordcat.domain.ranking import filter_songs_by_genre
        kept = filter_songs_by_genre(self.songs(), ["rock", "edm"])
        assert "Unlabelled" not in {s.song for s in kept}
        assert len(kept) == 2

    def test_is_case_insensitive(self):
        from chordcat.domain.ranking import filter_songs_by_genre
        assert len(filter_songs_by_genre(self.songs(), ["ROCK"])) == 1

    def test_unknown_genre_matches_nothing(self):
        from chordcat.domain.ranking import filter_songs_by_genre
        assert filter_songs_by_genre(self.songs(), ["polka"]) == ()
