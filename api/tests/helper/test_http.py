from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from chordcat.main import app

CHORDCAT_TAKE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "midi" / "chordcat-8track-sequencer.json"
)
client = TestClient(app)


def take_payload(**over):
    take = json.loads(CHORDCAT_TAKE.read_text())
    return {
        "events": take["events"],
        "elapsed_ms": take["elapsed_ms"],
        "harmony_channel": take["harmony_channel"],
        **over,
    }


def test_posting_a_real_take_returns_a_grounded_turn():
    body = client.post("/api/helper/turn", json=take_payload()).json()
    assert body["node_id"]
    assert body["text"]
    assert body["why"]
    assert body["key"] == "A major"
    assert len(body["chords"]) == 19
    assert body["draft"] is True  # no node is tutor-approved yet


def test_the_endpoint_filters_to_the_harmony_channel():
    everything = client.post(
        "/api/helper/turn", json=take_payload(harmony_channel=0)
    ).json()
    harmony = client.post("/api/helper/turn", json=take_payload()).json()
    assert len(everything["chords"]) != len(harmony["chords"])


def test_an_intent_tag_changes_the_suggestion():
    body = client.post(
        "/api/helper/turn", json=take_payload(intent_tags=["smoother"])
    ).json()
    assert body["node_id"] == "inversions"


def test_already_suggested_nodes_are_not_repeated():
    first = client.post("/api/helper/turn", json=take_payload()).json()
    second = client.post(
        "/api/helper/turn", json=take_payload(suggested_nodes=[first["node_id"]])
    ).json()
    assert second["node_id"] != first["node_id"]


def test_silence_asks_for_more_playing_rather_than_erroring():
    body = client.post("/api/helper/turn", json={"events": [], "elapsed_ms": 0}).json()
    assert body["node_id"] is None
    assert "Play a little more" in body["text"]
