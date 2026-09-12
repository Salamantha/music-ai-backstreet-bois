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


# -- session memory over HTTP ---------------------------------------------

def fewer_chords(payload: dict, keep: int = 40) -> dict:
    """A materially different second take, by truncating the first."""
    out = dict(payload)
    out["events"] = payload["events"][:keep]
    out["elapsed_ms"] = payload["events"][keep - 1]["t"]
    return out


def test_a_session_id_comes_back_and_can_be_reused():
    first = client.post("/api/helper/turn", json=take_payload()).json()
    assert first["session_id"]
    assert first["turn_number"] == 1

    second = client.post(
        "/api/helper/turn", json=take_payload(session_id=first["session_id"])
    ).json()
    assert second["session_id"] == first["session_id"]
    assert second["turn_number"] == 2


def test_the_server_remembers_so_a_refresh_cannot_make_it_repeat_itself():
    """The client sends no suggested_nodes at all -- the server supplies them."""
    sid = "regression-refresh"
    first = client.post("/api/helper/turn", json=take_payload(session_id=sid)).json()
    second = client.post("/api/helper/turn", json=take_payload(session_id=sid)).json()
    assert second["node_id"] != first["node_id"]


def test_a_changed_take_reports_what_moved():
    sid = "regression-change"
    client.post("/api/helper/turn", json=take_payload(session_id=sid))
    second = client.post(
        "/api/helper/turn", json=fewer_chords(take_payload(session_id=sid))
    ).json()
    assert second["changes"], "a materially shorter take should register as changed"
    assert all(c["kind"].startswith("change.") for c in second["changes"])


def test_the_first_turn_of_a_session_reports_no_change():
    body = client.post("/api/helper/turn", json=take_payload(session_id="fresh-one")).json()
    assert body["changes"] == []


def test_song_context_is_accepted_without_any_hooktheory_call():
    body = client.post(
        "/api/helper/turn",
        json=take_payload(
            session_id="with-songs",
            songs=[{"artist": "Arctic Monkeys", "song": "505",
                    "matched_chords": ["i", "ii"]}],
        ),
    ).json()
    assert body["node_id"]


def test_asking_to_be_shown_is_counted_as_an_override():
    sid = "override-session"
    turn = client.post("/api/helper/turn", json=take_payload(session_id=sid)).json()
    body = client.post(
        "/api/helper/override",
        params={"session_id": sid, "node_id": turn["node_id"]},
    ).json()
    assert body["override_count"] == 1
    assert body["override_rate"] == 1.0


def test_a_node_the_user_asked_to_see_counts_as_tried():
    sid = "tried-session"
    first = client.post("/api/helper/turn", json=take_payload(session_id=sid)).json()
    client.post(
        "/api/helper/override",
        params={"session_id": sid, "node_id": first["node_id"]},
    )
    second = client.post("/api/helper/turn", json=take_payload(session_id=sid)).json()
    assert second["node_id"] != first["node_id"]
