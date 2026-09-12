"""TheoryTab search: the second song source.

Exists because the Trends API index is stale -- Arctic Monkeys' "505" is in
TheoryTab as D Dorian `i ii i ii` but absent from all 17 pages of the equivalent
Trends query. These tests run entirely against a captured page; nothing here
touches the network.
"""

from __future__ import annotations

import pytest

from chordcat.adapters.theorytab import (
    FakeTheoryTabClient,
    TheoryTabHit,
    parse_results,
    romans_to_chord_string,
)
from chordcat.domain.ranking import progression_coverage

from conftest import FIXTURES

PAGE = FIXTURES / "theorytab" / "arctic-monkeys-i-ii.html"


@pytest.fixture(scope="module")
def hits():
    return parse_results(PAGE.read_text(encoding="utf-8", errors="ignore"))


def test_parses_both_sections_of_505(hits):
    assert len(hits) == 2
    assert {h.section for h in hits} == {"Chorus", "Instrumental"}
    assert all(h.song == "505" for h in hits)
    assert all(h.artist == "Arctic Monkeys" for h in hits)


def test_parses_the_full_metadata(hits):
    chorus = next(h for h in hits if h.section == "Chorus")
    assert chorus.key_tonic == "D"
    assert chorus.scale == "Dorian"
    assert chorus.key_name == "D Dorian"
    assert chorus.tempo == 71
    assert chorus.chords == ("i", "ii") * 4
    assert chorus.url.endswith("/theorytab/view/arctic-monkeys/505#Chorus")


def test_genres_come_free_with_the_result(hits):
    """Hooktheory's own labels, which beat guessing at them."""
    assert hits[0].genres == ("Rock", "Alternative", "Indie")


def test_highlighted_chords_are_the_matched_prefix(hits):
    assert hits[0].matched == ("i", "ii")


def test_youtube_id_comes_from_the_result_thumbnail(hits):
    """The thumbnail is a YouTube still, so the recording is one hop away."""
    assert hits[0].youtube_id == "qU9mHegkTc4"
    assert hits[0].youtube_url == "https://www.youtube.com/watch?v=qU9mHegkTc4"


def test_missing_thumbnail_leaves_no_video_link():
    from chordcat.adapters.theorytab import TheoryTabHit

    assert TheoryTabHit(song="X", artist="Y", section="", url="u").youtube_url == ""


def test_malformed_markup_degrades_to_no_results():
    """A markup change must not raise into a user's analysis."""
    assert parse_results("<html><body><table><tr><td>junk") == []
    assert parse_results("") == []


def test_roman_normalisation_for_the_search_box():
    assert romans_to_chord_string(["i", "ii"]) == "i ii"
    assert romans_to_chord_string(["vii°", "♭VI"]) == "viio bVI"
    # Holes are rendered in brackets and must not enter a query.
    assert romans_to_chord_string(["I", "[Xsus]", "V"]) == "I V"


class TestProgressionCoverage:
    """Coverage is what ranks the obvious answer where it belongs.

    Both a song that loops your progression and one that contains it once match
    an exact search identically; only coverage separates them.
    """

    def test_a_song_that_is_the_loop_scores_one(self):
        assert progression_coverage(["i", "ii"] * 4, ["i", "ii"]) == 1.0

    def test_a_song_that_merely_contains_it_scores_low(self):
        song = ["I", "V", "vi", "IV", "i", "ii", "V", "I", "IV", "V"]
        assert 0.0 < progression_coverage(song, ["i", "ii"]) < 0.3

    def test_no_occurrence_scores_zero(self):
        assert progression_coverage(["I", "IV", "V"], ["i", "ii"]) == 0.0

    def test_is_case_insensitive_but_not_degree_insensitive(self):
        assert progression_coverage(["I", "II"], ["i", "ii"]) == 1.0
        assert progression_coverage(["i", "iii"], ["i", "ii"]) == 0.0

    def test_edge_cases(self):
        assert progression_coverage([], ["i"]) == 0.0
        assert progression_coverage(["i"], []) == 0.0
        assert progression_coverage(["i"], ["i", "ii"]) == 0.0


async def test_fake_client_pages_and_dedupes():
    hit = TheoryTabHit(song="X", artist="Y", section="Verse", url="u")
    fake = FakeTheoryTabClient(fixtures={"i ii": [hit]})
    assert await fake.search_all("i ii") == [hit]
    assert fake.calls[0] == "i ii"


def test_hit_carries_the_songs_own_progression(hits):
    """What matched is only meaningful against what the song actually plays."""
    chorus = next(h for h in hits if h.section == "Chorus")
    assert chorus.chords == ("i", "ii") * 4
    assert chorus.key_name == "D Dorian"
    # The whole song is the played pattern, looped.
    assert progression_coverage(chorus.chords, ["i", "ii"]) == 1.0


def test_coverage_separates_looping_from_incidental_use():
    """A song built on your two chords beats one that passes through them."""
    loop = ["i", "ii"] * 4
    incidental = ["i", "ii", "i", "i65", "VI9", "i65sus4", "VI9", "ii7"]
    assert progression_coverage(loop, ["i", "ii"]) > progression_coverage(
        incidental, ["i", "ii"]
    )
