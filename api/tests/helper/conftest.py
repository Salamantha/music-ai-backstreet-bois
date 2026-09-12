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
def isolated_session_store(tmp_path, monkeypatch):
    from chordcat.helper.memory import SqliteSessionStore

    store = SqliteSessionStore(tmp_path / "helper-test.db")
    monkeypatch.setattr(routes, "get_session_store", lambda: store)
    yield store
