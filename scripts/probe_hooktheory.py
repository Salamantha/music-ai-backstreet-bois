#!/usr/bin/env python3
"""Credential smoke test for the Hooktheory Trends API.

Reads HOOKTHEORY_USERNAME / HOOKTHEORY_PASSWORD from `.env` -- never from the
command line, so the password does not land in shell history or a process list.

    python scripts/probe_hooktheory.py [cp]

Prints the auth result, one `trends/songs` page, one `trends/nodes` page, and the
rate-limit headers. The activkey is shown only as a masked fingerprint.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "src"))

from chordcat.adapters.hooktheory import AuthError, HttpHooktheoryClient  # noqa: E402
from chordcat.adapters.ratelimit import TokenBucket  # noqa: E402
from chordcat.config import get_settings  # noqa: E402


def mask(token: str) -> str:
    return f"{token[:4]}...{token[-4:]} ({len(token)} chars)" if token else "<none>"


async def main() -> int:
    cp = sys.argv[1] if len(sys.argv) > 1 else "4,1"
    settings = get_settings()

    if not settings.has_hooktheory:
        print("FAIL: HOOKTHEORY_USERNAME / HOOKTHEORY_PASSWORD are not set.")
        print(f"      Add them to {Path.cwd() / '.env'} (copy .env.example).")
        return 2

    print(f"user        : {settings.hooktheory_username}")
    client = HttpHooktheoryClient(
        username=settings.hooktheory_username,
        password=settings.hooktheory_password,
        bucket=TokenBucket(),
    )
    try:
        token = await client.authenticate()
        print(f"auth        : OK, activkey {mask(token)}")

        songs = await client.songs(cp)
        print(f"\ntrends/songs?cp={cp} -> {len(songs)} rows")
        for row in songs[:5]:
            print(
                f"   {row.get('artist','?'):28.28s} {row.get('song','?'):30.30s}"
                f" [{row.get('section','?')}]"
            )

        nodes = await client.nodes(cp)
        print(f"\ntrends/nodes?cp={cp} -> {len(nodes)} rows")
        for row in nodes[:5]:
            print(
                f"   {row.get('chord_HTML','?'):10.10s} p={float(row.get('probability',0)):.3f}"
                f"  child_path={row.get('child_path','?')}"
            )

        http = await client._http()
        resp = await http.get(
            "trends/songs",
            params={"cp": cp},
            headers={"Authorization": f"Bearer {token}"},
        )
        print("\nrate-limit headers:")
        for k, v in resp.headers.items():
            if k.lower().startswith("x-rate-limit"):
                print(f"   {k}: {v}")
        return 0
    except AuthError as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
