"""Dependency wiring. One place where the I/O adapters are constructed."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .adapters.cache import SqliteCache
from .adapters.genre_llm import (
    ClaudeGenreResolver,
    GenreResolver,
    LayeredGenreResolver,
    StaticGenreResolver,
)
from .adapters.hooktheory import HooktheoryClient, HttpHooktheoryClient
from .adapters.ratelimit import TokenBucket
from .config import Settings, get_settings
from .services.matching import PersonaPool

log = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent
GENRE_FILE = PACKAGE_ROOT / "data" / "artist_genres.json"
PERSONA_FILE = PACKAGE_ROOT / "seed" / "personas.json"


@dataclass(slots=True)
class Services:
    settings: Settings
    cache: SqliteCache
    client: HooktheoryClient | None
    genres: GenreResolver
    pool: PersonaPool
    #: Shared by every request: the Hooktheory quota is account-wide, so one
    #: bucket per process. With more than one worker this must become Redis.
    bucket: TokenBucket


@lru_cache
def get_services() -> Services:
    settings = get_settings()
    cache = SqliteCache(settings.chordcat_db_path)
    bucket = TokenBucket()

    client: HooktheoryClient | None = None
    if settings.has_hooktheory and not settings.chordcat_offline:
        client = HttpHooktheoryClient(
            username=settings.hooktheory_username,
            password=settings.hooktheory_password,
            bucket=bucket,
            cache=cache,
        )
    else:
        log.warning(
            "Hooktheory disabled (credentials missing or offline mode). "
            "Analysis will still return chords, key and harmonic features."
        )

    static = StaticGenreResolver(GENRE_FILE)
    genres: GenreResolver = static
    if settings.has_anthropic and not settings.chordcat_offline:
        genres = LayeredGenreResolver(
            static,
            ClaudeGenreResolver(
                api_key=settings.anthropic_api_key,
                model=settings.claude_model,
                prompt_version=settings.genre_prompt_version,
                cache=cache,
            ),
        )

    pool = PersonaPool.load(PERSONA_FILE)
    if not pool.personas:
        log.warning("no personas loaded from %s; run scripts/generate_pool.py", PERSONA_FILE)

    return Services(settings, cache, client, genres, pool, bucket)
