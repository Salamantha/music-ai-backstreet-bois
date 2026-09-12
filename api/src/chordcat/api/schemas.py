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


class IdentifyRequest(BaseModel):
    """A single sounding chord, for live step-entry capture."""

    pitches: list[int] = Field(min_length=1, max_length=16)
    bass_pitch: int | None = Field(default=None, ge=0, le=127)
    key_tonic_pc: int | None = Field(default=None, ge=0, le=11)
    key_mode: str | None = None


class CandidateOut(BaseModel):
    root: str
    quality: str
    symbol: str
    inversion: int
    extensions: list[str]
    score: float


class IdentifyResponse(BaseModel):
    symbol: str
    root: str
    quality: str
    inversion: int
    extensions: list[str]
    bass: str
    roman: str | None = None
    cp: str | None = None
    pitch_classes: list[str]
    candidates: list[CandidateOut]


class ChordStepIn(BaseModel):
    """One chord captured as a discrete step."""

    pitches: list[int] = Field(min_length=1, max_length=16)
    duration_ms: float = Field(default=600.0, gt=0)


class AnalyzeRequest(BaseModel):
    events: list[NoteEventIn] = Field(default_factory=list, max_length=20000)
    #: Alternative to `events`: chords already separated by the client, which is
    #: how Chord Cruiser step entry works. Avoids segmentation entirely.
    chords: list[ChordStepIn] = Field(default_factory=list, max_length=512)
    session_end_ms: float | None = None
    key_tonic_pc: int | None = Field(default=None, ge=0, le=11)
    key_mode: str | None = None
    #: Let the client ask for a bigger search when the user explicitly retries.
    budget: int | None = Field(default=None, ge=1, le=24)
    #: Keep only songs in these genres. Empty means no filtering.
    genres: list[str] = Field(default_factory=list, max_length=40)


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
    #: The recording on YouTube, when the source provided one.
    video_url: str = ""
    genres: list[str] = Field(default_factory=list)
    #: The song's own progression, and the part of it you played.
    song_chords: list[str] = Field(default_factory=list)
    matched_chords: list[str] = Field(default_factory=list)
    song_key: str = ""
    coverage: float = 0.0
    #: All sections of the song that matched; `section` is the one shown.
    sections: list[str] = Field(default_factory=list)


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
    #: Genres present in the unfiltered matches, with how many songs each has.
    #: Lets the client offer a filter over what is actually there.
    available_genres: dict[str, int] = Field(default_factory=dict)
    applied_genres: list[str] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=list,
        description="Human-readable caveats about this analysis.",
    )


class HelperTurnRequest(BaseModel):
    """A take, plus whatever the player said about it."""

    events: list[NoteEventIn] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    #: Which MIDI channel carries the harmony. The ChordCat interleaves all
    #: eight sequencer tracks, so without this the analysis sees eight tracks
    #: at once. The browser works it out; 0 or null keeps every channel.
    harmony_channel: int | None = Field(default=None, ge=0, le=16)
    user_text: str | None = None
    intent_tags: list[str] = Field(default_factory=list)
    #: Carried by the client so the helper does not repeat itself across turns.
    suggested_nodes: list[str] = Field(default_factory=list)
    tried_nodes: list[str] = Field(default_factory=list)


class HelperFactOut(BaseModel):
    id: str
    kind: str
    value: object
    n_observations: int
    confidence: float


class HelperTurnResponse(BaseModel):
    #: Empty when nothing was played, or when nothing sits on the frontier.
    node_id: str | None
    plain_name: str | None
    text: str
    #: Lit nodes the suggestion hangs off: "why are you telling me this?"
    why: list[str]
    distance: int
    #: False when no fact backs this node's detector -- the absence is
    #: unobserved rather than measured.
    measured: bool
    #: Frontier nodes that scored identically. Surfaced, not hidden.
    tied_with: list[str]
    #: True while the node's prose is still engineer-written placeholder text.
    draft: bool
    #: True when the turn came from the template rather than the model.
    templated: bool
    facts: list[HelperFactOut]
    chords: list[str]
    key: str | None
