#!/usr/bin/env python3
"""Validate every generated `cp` token against the live Hooktheory API.

The `cp` syntax is community-documented rather than specified, so rather than
trusting the enumeration in `domain/cp.py`, this script asks the API which
tokens actually return songs and commits the answer as a fixture. Anything that
comes back empty is either genuinely unused in the database or not a legal
token; either way we should not spend live request budget on it at runtime.

    python scripts/probe_cp_tokens.py            # probe every table token
    python scripts/probe_cp_tokens.py 5/6 B6 57  # probe specific tokens

Respects the 10-request/10-second account-wide limit, so a full run takes a
couple of minutes.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "src"))

from chordcat.adapters.hooktheory import HttpHooktheoryClient  # noqa: E402
from chordcat.adapters.ratelimit import TokenBucket  # noqa: E402
from chordcat.config import get_settings  # noqa: E402
from chordcat.domain.cp import CP_TABLE  # noqa: E402

OUT = ROOT / "api/src/chordcat/data/cp_table.json"


async def main() -> int:
    settings = get_settings()
    if not settings.has_hooktheory:
        print("FAIL: HOOKTHEORY_USERNAME / HOOKTHEORY_PASSWORD not set in .env")
        return 2

    explicit = sys.argv[1:]
    entries = sorted({e.token for e in CP_TABLE.values()})
    tokens = explicit or entries

    client = HttpHooktheoryClient(
        username=settings.hooktheory_username,
        password=settings.hooktheory_password,
        bucket=TokenBucket(),
    )

    valid: dict[str, int] = {}
    empty: list[str] = []
    try:
        await client.authenticate()
        for i, token in enumerate(tokens, 1):
            rows = await client.songs(token)
            if rows:
                valid[token] = len(rows)
                sample = f"{rows[0].get('artist','')} - {rows[0].get('song','')}"
            else:
                empty.append(token)
                sample = ""
            flag = "ok  " if rows else "EMPTY"
            print(f"[{i:3d}/{len(tokens)}] {token:8s} {flag} {len(rows):3d}  {sample[:46]}")
    finally:
        await client.aclose()

    print(f"\n{len(valid)} tokens returned songs, {len(empty)} came back empty")
    if empty:
        print("empty:", " ".join(empty))

    if not explicit:
        payload = {
            "schema_version": 1,
            "note": "Tokens empirically confirmed against the live Hooktheory API.",
            "valid": sorted(valid),
            "empty": sorted(empty),
        }
        OUT.write_text(json.dumps(payload, indent=1) + "\n")
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
