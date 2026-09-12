"""
hooktheory_proxy.py — thin caching proxy for the Hooktheory Trends API.

Why this exists:
  - Hooktheory auth is username/password -> bearer token. That cannot live in a
    browser bundle.
  - The API is rate limited. The cache turns a demo that hammers it into one
    that hits it a handful of times.
  - Browser CORS would block direct calls anyway.

Run:
    pip install fastapi uvicorn httpx
    export HOOKTHEORY_USER=you HOOKTHEORY_PASS=secret
    uvicorn hooktheory_proxy:app --reload --port 8000

Before the demo:
    curl "http://localhost:8000/api/prewarm?progressions=1,5,6,4;6,4,1,5;1,4,5"
    curl "http://localhost:8000/api/cache"   # confirm it filled

The disk cache means that once you have pre-warmed, the demo works with the
wifi unplugged. Do that. Conference wifi is where demos go to die.
"""

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

API_ROOT = "https://api.hooktheory.com/v1"
CACHE_FILE = Path(os.getenv("HOOKTHEORY_CACHE", "hooktheory_cache.json"))
CACHE_TTL = int(os.getenv("HOOKTHEORY_CACHE_TTL", 60 * 60 * 24 * 30))

app = FastAPI(title="Chordcat Voice · Hooktheory proxy")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon setting; tighten before anything public
    allow_methods=["GET"],
    allow_headers=["*"],
)

_token: str | None = None
_cache: dict[str, dict[str, Any]] = {}


def _load_cache() -> None:
    global _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            _cache = {}


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps(_cache))
    except OSError:
        pass


_load_cache()


async def _auth() -> str:
    """Exchange credentials for an activkey. Cached for the process lifetime."""
    global _token
    if _token:
        return _token

    user = os.getenv("HOOKTHEORY_USER")
    password = os.getenv("HOOKTHEORY_PASS")
    if not user or not password:
        raise HTTPException(500, "Set HOOKTHEORY_USER and HOOKTHEORY_PASS")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{API_ROOT}/users/auth",
            json={"username": user, "password": password},
            headers={"Content-Type": "application/json"},
        )
    if r.status_code != 200:
        raise HTTPException(502, f"Hooktheory auth failed: {r.status_code}")

    _token = r.json().get("activkey")
    if not _token:
        raise HTTPException(502, "Hooktheory returned no activkey")
    return _token


async def _fetch(endpoint: str, cp: str) -> Any:
    key = f"{endpoint}:{cp}"
    hit = _cache.get(key)
    if hit and time.time() - hit["at"] < CACHE_TTL:
        return hit["data"]

    token = await _auth()
    params = {"cp": cp} if cp else {}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{API_ROOT}/trends/{endpoint}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )

    if r.status_code == 401:
        # token expired mid-session; retry once with a fresh one
        globals()["_token"] = None
        token = await _auth()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{API_ROOT}/trends/{endpoint}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )

    if r.status_code == 429:
        # Serve stale rather than failing the demo.
        if hit:
            return hit["data"]
        raise HTTPException(429, "Hooktheory rate limit and nothing cached")

    if r.status_code != 200:
        if hit:
            return hit["data"]
        raise HTTPException(502, f"Hooktheory {endpoint} returned {r.status_code}")

    data = r.json()
    _cache[key] = {"at": time.time(), "data": data}
    _save_cache()
    return data


@app.get("/api/nodes")
async def nodes(cp: str = Query("", description="e.g. 1,5,6")):
    """Next-chord probabilities given a child path."""
    return await _fetch("nodes", cp)


@app.get("/api/songs")
async def songs(cp: str = Query(..., description="e.g. 1,5,6,4")):
    """Songs whose progression contains this child path."""
    return await _fetch("songs", cp)


@app.get("/api/prewarm")
async def prewarm(
    progressions: str = Query(
        "1,5,6,4;6,4,1,5;1,4,5;2,5,1;1,6,4,5",
        description="semicolon-separated progressions",
    )
):
    """
    Fill the cache with every prefix of every progression you plan to demo.
    Run this before you go on stage.
    """
    paths: set[str] = {""}
    for prog in progressions.split(";"):
        degrees = [d.strip() for d in prog.split(",") if d.strip()]
        for i in range(1, len(degrees) + 1):
            paths.add(",".join(degrees[:i]))

    ok, failed = 0, 0
    for cp in sorted(paths):
        for endpoint in ("nodes", "songs"):
            if endpoint == "songs" and not cp:
                continue
            try:
                await _fetch(endpoint, cp)
                ok += 1
            except HTTPException:
                failed += 1

    return {"paths": len(paths), "cached": ok, "failed": failed}


@app.get("/api/cache")
async def cache_status():
    return {"entries": len(_cache), "file": str(CACHE_FILE.resolve())}


@app.get("/health")
async def health():
    return {"ok": True, "authenticated": _token is not None}
