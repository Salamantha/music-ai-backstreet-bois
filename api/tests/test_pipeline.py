"""End-to-end pipeline with every external dependency faked. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chordcat.adapters.genre_llm import StaticGenreResolver
from chordcat.adapters.hooktheory import FakeHooktheoryClient, OfflineError
from chordcat.domain.events import Hole, Key
from chordcat.services.matching import PersonaPool
from chordcat.services.pipeline import analyse

from conftest import FIXTURES, play

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "chordcat"

C, G, Am, F = (60, 64, 67), (55, 59, 62), (57, 60, 64), (53, 57, 60)
Fmaj, Gmaj, Em, Amin = (65, 69, 72), (67, 71, 74), (64, 67, 71), (57, 60, 64)


@pytest.fixture
def genres():
    return StaticGenreResolver(PACKAGE / "data" / "artist_genres.json")


@pytest.fixture
def fake_client():
    return FakeHooktheoryClient(FIXTURES / "hooktheory", strict=False)


async def test_analysis_without_hooktheory_still_produces_everything_local(genres):
    """No client at all: chords, key, Roman numerals and harmonic features remain."""
    events, end = play([C, G, Am, F])
    result = await analyse(events, client=None, genres=genres, session_end_ms=end)

    assert [c.best.quality for c in result.chords] == ["maj", "maj", "min", "maj"]
    assert result.key_estimate is not None
    assert result.cp_string == "1,5,6,4"
    assert result.profile.harmonic.chord_variety > 0
    assert result.search.requests_spent == 0


async def test_key_override_changes_the_cp_tokens(genres):
    events, end = play([C, G, Am, F])
    as_major = await analyse(events, client=None, genres=genres, session_end_ms=end)
    as_minor = await analyse(
        events, client=None, genres=genres, session_end_ms=end,
        key_override=Key(9, "minor"),
    )
    assert as_major.cp_string == "1,5,6,4"
    assert as_minor.cp_string == "b3,b7,b1,b6"
    assert as_minor.key_estimate.source == "user"


async def test_strict_fake_client_raises_rather_than_going_live():
    """A missing fixture must fail loudly, not silently reach the network."""
    strict = FakeHooktheoryClient(FIXTURES / "hooktheory", strict=True)
    with pytest.raises(OfflineError):
        await strict.songs("9,9,9,9")


async def test_search_uses_recorded_fixtures(genres, fake_client):
    events, end = play([Fmaj, Gmaj, Em, Amin] * 2)
    result = await analyse(
        events, client=fake_client, genres=genres, session_end_ms=end,
        key_override=Key(0, "major"), budget=1,
    )
    assert result.cp_string.startswith("4,5,3,6")
    assert result.search.songs, "the 4,5,3,6 fixture should produce matches"
    assert any("Avicii" in s.artist for s in result.search.songs)
    assert result.profile.genre_weights, "genres should come from the label file"


async def test_empty_input_is_handled(genres):
    result = await analyse([], client=None, genres=genres)
    assert result.chords == ()
    assert result.cp_string == ""


async def test_golden_end_to_end_shape(genres, fake_client):
    """Snapshot of the whole analysis, as a regression net for refactors."""
    events, end = play([Fmaj, Gmaj, Em, Amin] * 2)
    result = await analyse(
        events, client=fake_client, genres=genres, session_end_ms=end,
        key_override=Key(0, "major"), budget=1,
    )
    romans = [t.roman for t in result.cp_sequence if not isinstance(t, Hole)]
    assert romans == ["IV", "V", "iii", "vi"] * 2

    pool = PersonaPool.load(PACKAGE / "seed" / "personas.json")
    matches = pool.rank(result.profile, limit=3)
    assert len(matches) == 3
    assert all(0.0 <= m.percentile <= 1.0 for m in matches)
    assert all(m.rationale for m in matches)
