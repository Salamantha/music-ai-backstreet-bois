"""The room of real musicians, stored in a Supabase `users` table.

Talks to PostgREST directly so the API needs no extra dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

MEMBER_COLUMNS = "client_id,name,city,instrument,signature_progression,mode,profile,is_seed"


class RoomStore(Protocol):
    async def upsert_member(self, row: dict) -> dict: ...

    async def list_members(self) -> list[dict]: ...

    async def count_members(self) -> int | None: ...


@dataclass(slots=True)
class SupabaseRoom:
    url: str
    key: str
    table: str = "users"
    _client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.url.rstrip("/") + "/rest/v1",
                timeout=httpx.Timeout(15.0),
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def upsert_member(self, row: dict) -> dict:
        http = await self._http()
        res = await http.post(
            f"/{self.table}",
            params={"on_conflict": "client_id"},
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
            json=row,
        )
        res.raise_for_status()
        body = res.json()
        return body[0] if isinstance(body, list) and body else {}

    async def count_members(self) -> int | None:
        """How many people have submitted a progression.

        Asks PostgREST for the count alone rather than counting rows we fetch:
        every row carries a whole taste profile, and selecting all of them just
        to take a length times out. Returns None when the count cannot be read,
        so a caller can say "unknown" rather than "none".
        """
        http = await self._http()
        res = await http.get(
            f"/{self.table}",
            params={"select": "client_id", "profile": "not.is.null"},
            headers={"Prefer": "count=exact", "Range": "0-0"},
        )
        res.raise_for_status()
        # PostgREST reports it as "0-0/57", or "*/0" when nothing matched.
        total = res.headers.get("content-range", "").rsplit("/", 1)[-1]
        return int(total) if total.isdigit() else None

    async def list_members(self) -> list[dict]:
        http = await self._http()
        res = await http.get(
            f"/{self.table}",
            params={"select": MEMBER_COLUMNS, "profile": "not.is.null"},
        )
        res.raise_for_status()
        return res.json()
