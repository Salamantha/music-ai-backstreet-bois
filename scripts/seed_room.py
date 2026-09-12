#!/usr/bin/env python3
"""Put a handful of seed personas into the Supabase room so it is never empty.

Idempotent: rows are upserted on `client_id = "seed:<persona id>"`.

    python scripts/seed_room.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "src"))

from chordcat.adapters.supabase import SupabaseRoom  # noqa: E402
from chordcat.config import get_settings  # noqa: E402
from chordcat.deps import PERSONA_FILE  # noqa: E402

# Distinct progressions, instruments and cities, all with non-empty profiles.
SEED_IDS = ("p02", "p07", "p08", "p16", "p18", "p21", "p24")


async def main() -> None:
    settings = get_settings()
    if not settings.has_supabase:
        sys.exit("SUPABASE_URL and SUPABASE_KEY must be set in .env")

    personas = {p["id"]: p for p in json.loads(PERSONA_FILE.read_text())["personas"]}
    room = SupabaseRoom(url=settings.supabase_url, key=settings.supabase_key)
    try:
        for pid in SEED_IDS:
            p = personas[pid]
            await room.upsert_member(
                {
                    "client_id": f"seed:{pid}",
                    "name": p["name"],
                    "city": p["city"],
                    "instrument": p["instrument"],
                    "signature_progression": p["signature_progression"],
                    "mode": p.get("mode", "major"),
                    "profile": p["profile"],
                    "is_seed": True,
                }
            )
            print(f"seeded {p['name']} ({pid})")
    finally:
        await room.aclose()


if __name__ == "__main__":
    asyncio.run(main())
