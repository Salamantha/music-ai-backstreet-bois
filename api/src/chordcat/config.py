"""Runtime settings, read from the environment and `.env`.

Secrets live only in `.env`, which is gitignored. Nothing here is ever logged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hooktheory_username: str = ""
    hooktheory_password: str = ""
    anthropic_api_key: str = ""

    chordcat_db_path: Path = Field(default=REPO_ROOT / "var" / "chordcat.db")
    chordcat_log_level: str = "INFO"
    #: Forbid every live network call. Set for tests and offline development.
    chordcat_offline: bool = False

    claude_model: str = "claude-opus-5"
    #: Bump to invalidate every cached genre label after a prompt change.
    genre_prompt_version: str = "v1"
    genre_taxonomy_version: str = "v1"

    #: Requests spent on the primary query. One GET of the full progression is
    #: enough to identify a distinctive progression, and keeps the account-wide
    #: 10-per-10s limit supporting ~10 concurrent users rather than ~4.
    song_request_budget: int = 1
    #: Ceiling when the primary query returns too little to be useful.
    song_fallback_budget: int = 8

    #: Search the TheoryTab page as a second song source. It is not an API --
    #: it parses the public search page -- so it is a separate switch from the
    #: sanctioned Trends API and can be turned off independently.
    theorytab_enabled: bool = True

    @property
    def has_hooktheory(self) -> bool:
        return bool(self.hooktheory_username and self.hooktheory_password)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
