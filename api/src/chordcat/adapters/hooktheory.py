"""Hooktheory Trends API client.

Endpoints (https://api.hooktheory.com/v1/):

* ``POST users/auth``            -- username/password -> ``activkey`` bearer token
* ``GET  trends/nodes?cp=``      -- next-chord probabilities
* ``GET  trends/songs?cp=&page=`` -- songs containing a progression, 20 per page

Everything the API returns is user-contributed content from a public database.
It is data, never instruction, and is passed through as such.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import httpx

from .cache import SqliteCache
from .ratelimit import TokenBucket

log = logging.getLogger(__name__)

BASE_URL = "https://api.hooktheory.com/v1/"
PAGE_SIZE = 20
MAX_RETRIES = 3


class HooktheoryError(RuntimeError):
    pass


class AuthError(HooktheoryError):
    pass


class OfflineError(HooktheoryError):
    """Raised when a live call is attempted but the process is in offline mode."""


class HooktheoryClient(Protocol):
    async def nodes(self, cp: str | None = None) -> list[dict[str, Any]]: ...
    async def songs(self, cp: str, page: int = 1) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class HttpHooktheoryClient:
    """Live client. Rate limiting and caching are mandatory, not optional.

    The 10-request/10-second quota is account-wide, so the bucket passed in must
    be shared by every caller in the process.
    """

    username: str
    password: str
    bucket: TokenBucket
    cache: SqliteCache | None = None
    base_url: str = BASE_URL
    _token: str | None = None
    _client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(20.0),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def authenticate(self) -> str:
        """Exchange username/password for the long-lived ``activkey``."""
        if self._token:
            return self._token
        if not self.username or not self.password:
            raise AuthError(
                "HOOKTHEORY_USERNAME / HOOKTHEORY_PASSWORD are not set. "
                "The Trends API requires a hooktheory.com account."
            )
        client = await self._http()
        await self.bucket.acquire()
        resp = await client.post(
            "users/auth", json={"username": self.username, "password": self.password}
        )
        self.bucket.observe(resp.headers)
        if resp.status_code == 401:
            raise AuthError("Hooktheory rejected those credentials.")
        resp.raise_for_status()
        token = resp.json().get("activkey")
        if not token:
            raise AuthError("Hooktheory auth succeeded but returned no activkey.")
        self._token = token
        return token

    async def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        token = await self.authenticate()
        client = await self._http()
        for attempt in range(MAX_RETRIES):
            await self.bucket.acquire()
            resp = await client.get(
                path, params=params, headers={"Authorization": f"Bearer {token}"}
            )
            self.bucket.observe(resp.headers)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = self.bucket.penalize(
                    float(retry_after) if retry_after else None, attempt
                )
                log.warning("Hooktheory 429 on %s; backing off %.1fs", path, delay)
                await asyncio.sleep(delay)
                continue
            if resp.status_code == 401:
                # activkey can be invalidated server-side; re-auth once.
                self._token = None
                token = await self.authenticate()
                continue
            if resp.status_code >= 500:
                # Some `cp` values make the Hooktheory backend 500 rather than
                # return an empty list (a bare seventh such as `57` does it
                # reliably). One malformed window must not fail a whole take, so
                # retry once and then degrade to "no results".
                if attempt + 1 < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                log.warning(
                    "Hooktheory %s for %s %s; treating as no results",
                    resp.status_code, path, params,
                )
                return []
            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError:
                # The API occasionally answers 200 with a non-JSON body (an
                # empty body, or an HTML error page). Treat it as no results
                # rather than letting it break a whole analysis.
                log.warning(
                    "Hooktheory returned non-JSON 200 for %s %s: %r",
                    path, params, resp.text[:200],
                )
                return []
            return payload if isinstance(payload, list) else []
        raise HooktheoryError(f"Hooktheory rate limit not clearing for {path}")

    async def nodes(self, cp: str | None = None) -> list[dict[str, Any]]:
        if self.cache is not None:
            cached = self.cache.get_nodes(cp)
            if cached is not None:
                return cached
        rows = await self._get("trends/nodes", {"cp": cp} if cp else {})
        if self.cache is not None:
            self.cache.put_nodes(cp, rows)
        return rows

    async def songs(self, cp: str, page: int = 1) -> list[dict[str, Any]]:
        if self.cache is not None:
            cached = self.cache.get_songs(cp, page)
            if cached is not None:
                return cached
            known_pages = self.cache.get_total_pages(cp)
            if known_pages is not None and page > known_pages:
                return []  # never re-probe past a known end
        rows = await self._get("trends/songs", {"cp": cp, "page": page})
        if self.cache is not None:
            self.cache.put_songs(cp, page, rows)
            if len(rows) < PAGE_SIZE:
                total = (page - 1) * PAGE_SIZE + len(rows)
                self.cache.set_total_pages(cp, page, total)
        return rows


@dataclass(slots=True)
class FakeHooktheoryClient:
    """Fixture-backed client used by tests and offline development.

    In strict mode a fixture miss raises rather than returning empty, so a test
    that would have reached the network fails loudly instead of silently going
    live and burning the shared quota.
    """

    fixture_dir: Path
    strict: bool = True
    calls: list[tuple[str, str, int]] | None = None

    def _load(self, kind: str, name: str) -> list[dict[str, Any]] | None:
        import json

        path = self.fixture_dir / kind / f"{_safe(name)}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    async def nodes(self, cp: str | None = None) -> list[dict[str, Any]]:
        if self.calls is not None:
            self.calls.append(("nodes", cp or "", 0))
        data = self._load("nodes", cp or "_root")
        if data is None:
            if self.strict:
                raise OfflineError(f"no nodes fixture for cp={cp!r}")
            return []
        return data

    async def songs(self, cp: str, page: int = 1) -> list[dict[str, Any]]:
        if self.calls is not None:
            self.calls.append(("songs", cp, page))
        data = self._load("songs", f"{cp}_p{page}")
        if data is None:
            if self.strict:
                raise OfflineError(f"no songs fixture for cp={cp!r} page={page}")
            return []
        return data


def _safe(name: str) -> str:
    """Filesystem-safe fixture name for a cp path."""
    return name.replace("/", "~").replace(",", "-")


def rows_to_hits(rows: Sequence[dict[str, Any]]):
    from ..domain.events import SongHit

    return tuple(
        SongHit(
            artist=str(r.get("artist", "")).strip(),
            song=str(r.get("song", "")).strip(),
            section=str(r.get("section", "")).strip(),
            url=str(r.get("url", "")).strip(),
        )
        for r in rows
        if r.get("artist") and r.get("song")
    )
