"""The room of real musicians: storing a profile and ranking against the rest."""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from chordcat.deps import PERSONA_FILE, get_services
from chordcat.services.matching import persona_from_dict, profile_to_dict


class FakeRoom:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows: list[dict] = list(rows or [])

    async def upsert_member(self, row: dict) -> dict:
        self.rows = [r for r in self.rows if r["client_id"] != row["client_id"]]
        self.rows.append(row)
        return row

    async def list_members(self) -> list[dict]:
        return [r for r in self.rows if r.get("profile") is not None]


def _seed_rows(n: int = 3) -> list[dict]:
    personas = json.loads(PERSONA_FILE.read_text())["personas"]
    rows = []
    for p in personas:
        if not p["profile"]["genre_weights"]:
            continue
        rows.append(
            {
                "client_id": f"seed:{p['id']}",
                "name": p["name"],
                "city": p["city"],
                "instrument": p["instrument"],
                "signature_progression": p["signature_progression"],
                "mode": p["mode"],
                "profile": p["profile"],
                "is_seed": True,
            }
        )
        if len(rows) == n:
            break
    return rows


def _join_payload(row: dict, client_id: str = "browser-1") -> dict:
    p = row["profile"]
    h = p["harmonic"]
    return {
        "client_id": client_id,
        "name": "Test Player",
        "city": "Berlin, Germany",
        "instrument": "keys",
        "signature_progression": row["signature_progression"],
        "mode": row["mode"],
        "profile": {
            "genres": p["genre_weights"],
            "artists": p["artist_weights"],
            "eras": p["era_weights"],
            "moods": p["mood_weights"],
            "harmonic": {
                "mode": row["mode"],
                "seventh_density": h["seventh_density"],
                "borrowed_rate": h["borrowed_rate"],
                "mean_progression_rarity": h["mean_progression_rarity"],
                "key_spread": h["key_spread"],
                "chord_variety": h["chord_variety"],
                "mean_chord_duration_s": h["mean_chord_duration_s"],
                "cadence_profile": h["cadence_profile"],
            },
        },
    }


@pytest.fixture(scope="module", autouse=True)
def offline_services():
    from chordcat.config import get_settings

    os.environ["CHORDCAT_OFFLINE"] = "1"
    get_settings.cache_clear()
    get_services.cache_clear()
    yield
    os.environ.pop("CHORDCAT_OFFLINE", None)
    get_settings.cache_clear()
    get_services.cache_clear()


@pytest.fixture
def client():
    from chordcat.main import app

    return TestClient(app)


def test_persona_from_room_row_round_trips():
    row = _seed_rows(1)[0]
    persona = persona_from_dict(row)
    assert persona.id == row["client_id"]
    assert persona.name == row["name"]
    assert persona.bio == ""
    assert profile_to_dict(persona.profile) == row["profile"]


def test_join_returns_503_without_a_room(client):
    get_services().room = None
    r = client.post("/api/room/join", json=_join_payload(_seed_rows(1)[0]))
    assert r.status_code == 503


def test_join_ranks_against_everyone_but_yourself(client):
    room = FakeRoom(_seed_rows(3))
    get_services().room = room
    payload = _join_payload(_seed_rows(1)[0])

    r = client.post("/api/room/join", json=payload)
    assert r.status_code == 200
    body = r.json()

    assert body["room_size"] == 4
    assert len(body["matches"]) == 3
    assert all(m["id"] != "browser-1" for m in body["matches"])
    # We sent the first seed's exact profile, so it must be the top match.
    assert body["matches"][0]["id"] == "seed:p01"
    assert body["matches"][0]["percentile"] > 0.9
    assert body["matches"][0]["rationale"]

    # Replaying upserts the same row rather than adding a second one.
    r = client.post("/api/room/join", json=payload)
    assert r.json()["room_size"] == 4
    assert sum(1 for row in room.rows if row["client_id"] == "browser-1") == 1


def test_health_reports_room(client):
    get_services().room = FakeRoom()
    assert client.get("/api/health").json()["room"] is True
    get_services().room = None
    assert client.get("/api/health").json()["room"] is False
