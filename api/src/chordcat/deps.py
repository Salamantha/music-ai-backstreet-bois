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
from .adapters.supabase import RoomStore, SupabaseRoom
from .adapters.theorytab import HttpTheoryTabClient, TheoryTabClient
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
    #: Second song source: the TheoryTab search page. Optional and independent
    #: of the Trends API, so either can be unavailable without the other.
    theorytab: TheoryTabClient | None
    #: Shared by every request: the Hooktheory quota is account-wide, so one
    #: bucket per process. With more than one worker this must become Redis.
    bucket: TokenBucket
    #: Real musicians who have joined. None means fall back to the seed pool.
    room: RoomStore | None = None


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

    theorytab: TheoryTabClient | None = None
    if settings.theorytab_enabled and not settings.chordcat_offline:
        theorytab = HttpTheoryTabClient(cache=cache)

    room: RoomStore | None = None
    if settings.has_supabase and not settings.chordcat_offline:
        room = SupabaseRoom(url=settings.supabase_url, key=settings.supabase_key)
    else:
        log.warning("Supabase not configured; matches come from the seed pool only.")

    return Services(settings, cache, client, genres, pool, theorytab, bucket, room)
