"""What the helper remembers between turns.

Deliberately small. Not a profile, not an identity claim, not taste modelling:
which nodes have been suggested, which have been tried, how often the user asked
to be shown rather than told, and the fact snapshot of the last take so the next
one can be compared against it.

Without this the helper repeats itself on turn four and cannot say what changed,
which is most of what makes an assistant feel like a guide rather than a tip
generator.

The helper owns its own tables and its own connection rather than extending
``adapters/cache.py``: that file belongs to the matching path, and these rows
have nothing to do with Hooktheory.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .facts import Fact, FactSet

_SCHEMA = """
CREATE TABLE IF NOT EXISTS helper_sessions (
    session_id TEXT PRIMARY KEY,
    override_count INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS helper_turns (
    session_id TEXT NOT NULL,
    n INTEGER NOT NULL,
    node_id TEXT,
    tried INTEGER NOT NULL DEFAULT 0,
    text TEXT NOT NULL,
    facts TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (session_id, n)
);
"""


def fact_to_dict(f: Fact) -> dict[str, Any]:
    return {
        "id": f.id, "kind": f.kind, "value": f.value, "confidence": f.confidence,
        "evidence": list(f.evidence), "n_observations": f.n_observations,
        "is_pattern": f.is_pattern,
    }


def fact_from_dict(d: dict[str, Any]) -> Fact:
    return Fact(
        id=d["id"], kind=d["kind"], value=d["value"],
        confidence=d.get("confidence", 1.0),
        evidence=tuple(d.get("evidence") or ()),
        n_observations=d.get("n_observations", 0),
        is_pattern=d.get("is_pattern", True),
    )


@dataclass(frozen=True, slots=True)
class Recall:
    """Everything the helper knows about this session so far."""

    suggested_nodes: tuple[str, ...] = ()
    tried_nodes: tuple[str, ...] = ()
    override_count: int = 0
    #: Facts from the previous take, for diffing. Empty on the first turn.
    previous: FactSet = field(default_factory=FactSet)
    #: Newest last: (node_id, text) for each turn already spoken.
    turns: tuple[tuple[str | None, str], ...] = ()

    @property
    def is_first_turn(self) -> bool:
        return not self.turns


class SessionStore(Protocol):
    def recall(self, session_id: str) -> Recall: ...
    def record(self, session_id: str, facts: FactSet, node_id: str | None, text: str) -> None: ...
    def mark_tried(self, session_id: str, node_id: str) -> None: ...
    def bump_override(self, session_id: str) -> None: ...


@dataclass(slots=True)
class SqliteSessionStore:
    path: Path
    _conn: sqlite3.Connection | None = None

    def __post_init__(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        assert self._conn is not None
        return self._conn

    def recall(self, session_id: str) -> Recall:
        rows = self.conn.execute(
            "SELECT node_id, tried, text, facts FROM helper_turns "
            "WHERE session_id = ? ORDER BY n",
            (session_id,),
        ).fetchall()
        if not rows:
            return Recall()

        suggested = tuple(r[0] for r in rows if r[0])
        tried = tuple(r[0] for r in rows if r[0] and r[1])
        previous = FactSet(tuple(fact_from_dict(d) for d in json.loads(rows[-1][3])))
        counted = self.conn.execute(
            "SELECT override_count FROM helper_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return Recall(
            suggested_nodes=suggested,
            tried_nodes=tried,
            override_count=counted[0] if counted else 0,
            previous=previous,
            turns=tuple((r[0], r[2]) for r in rows),
        )

    def record(self, session_id: str, facts: FactSet, node_id: str | None, text: str) -> None:
        now = time.time()
        with self.conn:
            self.conn.execute(
                "INSERT INTO helper_sessions (session_id, updated_at) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET updated_at = excluded.updated_at",
                (session_id, now),
            )
            n = self.conn.execute(
                "SELECT COALESCE(MAX(n), 0) + 1 FROM helper_turns WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO helper_turns (session_id, n, node_id, text, facts, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id, n, node_id, text,
                    json.dumps([fact_to_dict(f) for f in facts]), now,
                ),
            )

    def mark_tried(self, session_id: str, node_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE helper_turns SET tried = 1 WHERE session_id = ? AND node_id = ?",
                (session_id, node_id),
            )

    def bump_override(self, session_id: str) -> None:
        """Rising override rate is a bug signal on the explanations, not engagement."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO helper_sessions (session_id, override_count, updated_at) "
                "VALUES (?, 1, ?) ON CONFLICT(session_id) DO UPDATE SET "
                "override_count = override_count + 1, updated_at = excluded.updated_at",
                (session_id, time.time()),
            )
