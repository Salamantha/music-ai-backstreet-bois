"""Keep helper tests off the real database.

The session store is a process-level singleton pointed at the configured db
path, so without this the suite would write turns into the developer's own
chordcat.db -- and, worse, a second run would find the sessions the first run
left behind and assert against different state.
"""

from __future__ import annotations

import pytest

from chordcat.api import routes


@pytest.fixture(autouse=True)
def never_call_a_real_model(monkeypatch):
    """No test may reach a live provider.

    Once a real key is in .env, build_voice() picks it up and every endpoint
    test becomes a paid network round trip -- the suite went from 2s to 120s
    the moment one was added. Tests that want to exercise the model layer
    build a voice explicitly with a stubbed transport instead.
    """
    from chordcat.config import Settings

    monkeypatch.setattr(
        "chordcat.config.get_settings",
        lambda: Settings(llm_base_url="", llm_model="", llm_api_key="",
                         anthropic_api_key=""),
    )


@pytest.fixture(autouse=True)
def isolated_session_store(tmp_path, monkeypatch):
    from chordcat.helper.memory import SqliteSessionStore

    store = SqliteSessionStore(tmp_path / "helper-test.db")
    monkeypatch.setattr(routes, "get_session_store", lambda: store)
    yield store
