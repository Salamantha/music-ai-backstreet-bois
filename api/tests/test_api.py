"""HTTP surface: live chord identification and step-entry analysis."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES


@pytest.fixture(scope="module", autouse=True)
def offline_services():
    """Force the app offline for the whole module.

    Without this the TestClient builds a live Hooktheory client from the
    developer's own `.env` and the suite quietly starts spending the shared
    account quota -- and failing on a closed event loop between requests.
    """
    import os

    from chordcat.config import get_settings
    from chordcat.deps import get_services

    os.environ["CHORDCAT_OFFLINE"] = "1"
    get_settings.cache_clear()
    get_services.cache_clear()
    yield
    os.environ.pop("CHORDCAT_OFFLINE", None)
    get_settings.cache_clear()
    get_services.cache_clear()


@pytest.fixture(scope="module")
def client(offline_services):
    from chordcat.main import app

    return TestClient(app)

# Real five-note voicings taken from the ChordCat capture.
CHORDCAT_VOICINGS = {
    (42, 52, 57, 59, 68): ("F#", "min7"),
    (40, 56, 59, 63, 66): ("E", "maj7"),
    (45, 55, 60, 62, 67): ("A", "min7"),
    (50, 60, 65, 67, 72): ("D", "min7"),
    (48, 58, 63, 65, 70): ("C", "min7"),
}


@pytest.mark.parametrize("pitches,expected", CHORDCAT_VOICINGS.items())
def test_identify_real_chordcat_voicings(client, pitches, expected):
    r = client.post("/api/identify", json={"pitches": list(pitches)})
    assert r.status_code == 200
    body = r.json()
    assert (body["root"], body["quality"]) == expected


def test_identify_reports_extensions_and_alternatives(client):
    r = client.post("/api/identify", json={"pitches": [45, 55, 60, 62, 67]})
    body = r.json()
    assert "11" in body["extensions"]
    assert body["symbol"].startswith("Am7")
    assert len(body["candidates"]) >= 2
    assert body["bass"] == "A"


def test_identify_with_a_key_adds_roman_and_cp(client):
    r = client.post(
        "/api/identify",
        json={"pitches": [60, 64, 67], "key_tonic_pc": 0, "key_mode": "major"},
    )
    body = r.json()
    assert body["roman"] == "I"
    assert body["cp"] == "1"


def test_identify_without_a_key_omits_roman(client):
    body = client.post("/api/identify", json={"pitches": [60, 64, 67]}).json()
    assert body["roman"] is None
    assert body["cp"] is None


def test_identify_rejects_an_empty_chord(client):
    assert client.post("/api/identify", json={"pitches": []}).status_code == 422


def test_identify_makes_no_network_calls(client, monkeypatch):
    """Live identification runs on every held-note change, so it must be local."""
    import httpx

    def boom(*_a, **_k):  # pragma: no cover - only runs on failure
        raise AssertionError("identify must not perform network I/O")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom)
    monkeypatch.setattr(httpx.AsyncClient, "post", boom)
    assert client.post("/api/identify", json={"pitches": [60, 64, 67]}).status_code == 200


def test_analyze_accepts_chord_steps(client):
    """Step entry skips segmentation: the player already separated the chords."""
    r = client.post(
        "/api/analyze",
        json={
            "chords": [
                {"pitches": [48, 60, 64, 67]},
                {"pitches": [43, 55, 59, 62]},
                {"pitches": [45, 57, 60, 64]},
                {"pitches": [41, 53, 57, 60]},
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert [c["symbol"] for c in body["chords"]] == ["C", "G", "Am", "F"]
    assert body["romans"] == ["I", "V", "vi", "IV"]
    assert body["cp"] == "1,5,6,4"


def test_analyze_chord_steps_honour_a_key_override(client):
    payload = {
        "chords": [
            {"pitches": [48, 60, 64, 67]},
            {"pitches": [43, 55, 59, 62]},
            {"pitches": [45, 57, 60, 64]},
            {"pitches": [41, 53, 57, 60]},
        ],
        "key_tonic_pc": 9,
        "key_mode": "minor",
    }
    body = client.post("/api/analyze", json=payload).json()
    assert body["key"]["name"] == "A minor"
    assert body["key"]["source"] == "user"
    assert body["cp"] == "b3,b7,b1,b6"


def test_analyze_requires_some_input(client):
    assert client.post("/api/analyze", json={}).status_code == 400


def test_step_entry_reproduces_the_real_capture_chords(client):
    """Regrouping the real capture into steps yields the same chord readings.

    This is the path Chord Cruiser takes: the player separates the chords, so
    the server never has to guess where one ends and the next begins.
    """
    take = json.loads(
        (FIXTURES / "midi" / "chordcat-8track-sequencer.json").read_text()
    )
    groups: list[list[int]] = []
    last_t: float | None = None
    for e in take["events"]:
        if e.get("c") != 2 or e["k"] != "on":
            continue
        if last_t is not None and e["t"] - last_t <= 15:
            groups[-1].append(e["p"])
        else:
            groups.append([e["p"]])
            last_t = e["t"]

    assert len(groups) == 23
    assert all(len(g) == 5 for g in groups), "the device voices every chord with five notes"

    body = client.post(
        "/api/analyze",
        json={"chords": [{"pitches": sorted(g)} for g in groups]},
    ).json()
    assert len(body["chords"]) >= 19
    symbols = {c["symbol"] for c in body["chords"]}
    assert {"F#m7", "Emaj7", "Am7", "Dm7"} <= symbols


def test_analyze_accepts_a_single_chord(client):
    """A player exploring one voicing should still get an answer."""
    r = client.post("/api/analyze", json={"chords": [{"pitches": [48, 60, 64, 67]}]})
    assert r.status_code == 200
    body = r.json()
    assert [c["symbol"] for c in body["chords"]] == ["C"]
    assert body["cp"] == "1"
    assert body["key"] is not None


def test_analyze_single_extended_chordcat_voicing(client):
    """The five-note voicings the device actually sends, one at a time."""
    body = client.post(
        "/api/analyze", json={"chords": [{"pitches": [45, 55, 60, 62, 67]}]}
    ).json()
    assert [c["symbol"] for c in body["chords"]] == ["Am7"]
