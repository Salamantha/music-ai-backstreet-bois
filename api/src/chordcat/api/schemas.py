"""Request and response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NoteEventIn(BaseModel):
    """One Web MIDI event, as posted by the browser."""

    k: Literal["on", "off", "cc"]
    t: float = Field(description="ms since session start (performance.now based)")
    p: int | None = Field(default=None, ge=0, le=127, description="MIDI note number")
    v: int = Field(default=0, ge=0, le=127, description="velocity / controller value")
    n: int | None = Field(default=None, ge=0, le=127, description="controller number")
    c: int | None = Field(default=None, ge=1, le=16, description="MIDI channel, 1-16")


class AnalyzeRequest(BaseModel):
    events: list[NoteEventIn] = Field(default_factory=list, max_length=20000)
    session_end_ms: float | None = None
    key_tonic_pc: int | None = Field(default=None, ge=0, le=11)
    key_mode: str | None = None
    #: Let the client ask for a bigger search when the user explicitly retries.
    budget: int | None = Field(default=None, ge=1, le=24)


class ChordOut(BaseModel):
    index: int
    start_ms: float
    end_ms: float
    root: str
    quality: str
    inversion: int
    symbol: str
    roman: str | None = None
    cp: str | None = None
    pitches: list[int]


class KeyOut(BaseModel):
    tonic_pc: int
    mode: str
    name: str
    confidence: float
    source: str
    modulation_suspected: bool
    alternatives: list[dict]


class SongOut(BaseModel):
    artist: str
    song: str
    section: str
    url: str
    score: float
    matched_ngrams: list[str] = Field(default_factory=list)


class ArtistOut(BaseModel):
    artist: str
    score: float
    songs: list[str] = Field(default_factory=list)


class HarmonicOut(BaseModel):
    mode: str
    seventh_density: float
    borrowed_rate: float
    mean_progression_rarity: float
    key_spread: float
    chord_variety: float
    mean_chord_duration_s: float
    cadence_profile: dict[str, float]


class ProfileOut(BaseModel):
    genres: dict[str, float]
    artists: dict[str, float]
    eras: dict[str, float]
    moods: dict[str, float]
    harmonic: HarmonicOut
    taste_document: str


class MatchOut(BaseModel):
    id: str
    name: str
    instrument: str
    city: str
    bio: str
    score: float
    percentile: float
    components: dict[str, float]
    shared_artists: list[str]
    shared_genres: list[str]
    shared_harmonic: list[str]
    rationale: str
    signature_progression: str


class AnalyzeResponse(BaseModel):
    session_id: str
    chords: list[ChordOut]
    key: KeyOut | None
    cp: str
    romans: list[str]
    unmapped: list[dict]
    songs: list[SongOut]
    artists: list[ArtistOut]
    profile: ProfileOut | None
    matches: list[MatchOut]
    requests_spent: int
    queried: list[str]
    segmentation_mode: str
    stuck_notes: int
    diagnostics: dict = Field(default_factory=dict)
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable caveats about this analysis.",
    )
