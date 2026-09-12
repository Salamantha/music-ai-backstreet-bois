"""Persistent cache for Hooktheory responses.

Two things make this more than an optimisation. First, negative caching: empty
results are the *common* case for anything but a cliche progression, and
re-asking burns the shared quota for nothing. Second, the accumulated song rows
double as an artist-frequency corpus, so ranking quality improves on its own as
the cache fills.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

NODES_TTL_S = 90 * 24 * 3600
SONGS_TTL_S = 30 * 24 * 3600
#: Empty results are cached for less time than hits: the database does grow.
EMPTY_TTL_S = 7 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ht_nodes (
    cp TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ht_songs (
    cp TEXT NOT NULL, page INTEGER NOT NULL,
    payload TEXT NOT NULL, fetched_at REAL NOT NULL,
    PRIMARY KEY (cp, page)
);
CREATE TABLE IF NOT EXISTS ht_song_pages (
    cp TEXT PRIMARY KEY, total_pages INTEGER NOT NULL, total_hits INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS artist_frequency (
    artist TEXT PRIMARY KEY, n INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS corpus_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS genre_cache (
    cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at REAL NOT NULL
);
"""


class HooktheoryCache(Protocol):
    def get_nodes(self, cp: str | None) -> list[dict[str, Any]] | None: ...
    def put_nodes(self, cp: str | None, rows: Sequence[dict[str, Any]]) -> None: ...
    def get_songs(self, cp: str, page: int) -> list[dict[str, Any]] | None: ...
    def put_songs(self, cp: str, page: int, rows: Sequence[dict[str, Any]]) -> None: ...
    def get_total_pages(self, cp: str) -> int | None: ...
    def set_total_pages(self, cp: str, pages: int, hits: int) -> None: ...
    def get_total_hits(self, cp: str) -> int | None: ...


class SqliteCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- nodes -------------------------------------------------------------
    def get_nodes(self, cp: str | None) -> list[dict[str, Any]] | None:
        row = self._conn.execute(
            "SELECT payload, fetched_at FROM ht_nodes WHERE cp = ?", (cp or "",)
        ).fetchone()
        return _unwrap(row, NODES_TTL_S)

    def put_nodes(self, cp: str | None, rows: Sequence[dict[str, Any]]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO ht_nodes VALUES (?, ?, ?)",
            (cp or "", json.dumps(list(rows)), time.time()),
        )
        self._conn.commit()

    # -- songs -------------------------------------------------------------
    def get_songs(self, cp: str, page: int) -> list[dict[str, Any]] | None:
        row = self._conn.execute(
            "SELECT payload, fetched_at FROM ht_songs WHERE cp = ? AND page = ?",
            (cp, page),
        ).fetchone()
        return _unwrap(row, SONGS_TTL_S)

    def put_songs(self, cp: str, page: int, rows: Sequence[dict[str, Any]]) -> None:
        rows = list(rows)
        self._conn.execute(
            "INSERT OR REPLACE INTO ht_songs VALUES (?, ?, ?, ?)",
            (cp, page, json.dumps(rows), time.time()),
        )
        for r in rows:
            artist = r.get("artist", "")
            if artist:
                self._conn.execute(
                    "INSERT INTO artist_frequency(artist, n) VALUES (?, 1) "
                    "ON CONFLICT(artist) DO UPDATE SET n = n + 1",
                    (artist,),
                )
        self._conn.commit()

    def get_total_pages(self, cp: str) -> int | None:
        row = self._conn.execute(
            "SELECT total_pages FROM ht_song_pages WHERE cp = ?", (cp,)
        ).fetchone()
        return row[0] if row else None

    def get_total_hits(self, cp: str) -> int | None:
        row = self._conn.execute(
            "SELECT total_hits FROM ht_song_pages WHERE cp = ?", (cp,)
        ).fetchone()
        return row[0] if row else None

    def set_total_pages(self, cp: str, pages: int, hits: int) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO ht_song_pages VALUES (?, ?, ?)", (cp, pages, hits)
        )
        self._conn.commit()

    # -- corpus ------------------------------------------------------------
    def artist_frequencies(self) -> dict[str, int]:
        return {
            a: n for a, n in self._conn.execute("SELECT artist, n FROM artist_frequency")
        }

    def corpus_size(self) -> int:
        row = self._conn.execute("SELECT SUM(n) FROM artist_frequency").fetchone()
        return int(row[0] or 0)

    # -- genre labels ------------------------------------------------------
    def get_genre(self, cache_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload, fetched_at FROM genre_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put_genre(self, cache_key: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO genre_cache VALUES (?, ?, ?)",
            (cache_key, json.dumps(payload), time.time()),
        )
        self._conn.commit()


def _unwrap(row: tuple[str, float] | None, ttl: float) -> list[dict[str, Any]] | None:
    if row is None:
        return None
    payload, fetched_at = row
    data = json.loads(payload)
    effective = EMPTY_TTL_S if not data else ttl
    if time.time() - fetched_at > effective:
        return None
    return data
