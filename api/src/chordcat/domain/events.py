"""Core data shapes for the analysis pipeline.

Everything here is frozen and hashable so the pure core can be memoised and
golden-tested freely. Time is always client-supplied milliseconds -- this module
never reads a clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .pitch import Mode, pc

RawKind = Literal["on", "off", "cc"]


@dataclass(frozen=True, slots=True)
class RawEvent:
    """A single MIDI event as delivered by the browser's Web MIDI API.

    ``t`` is milliseconds since session start (``performance.now()`` based, so
    monotonic within a session but meaningless across sessions).
    """

    kind: RawKind
    t: float
    pitch: int | None = None
    velocity: int = 0
    controller: int | None = None


@dataclass(frozen=True, slots=True)
class Sounding:
    """A note that was held from ``on_ms`` until ``off_ms``."""

    pitch: int
    velocity: int
    on_ms: float
    off_ms: float
    stuck: bool = False
    pedal_only: bool = False

    @property
    def duration_ms(self) -> float:
        return self.off_ms - self.on_ms

    def overlap_ms(self, start: float, end: float) -> float:
        return max(0.0, min(self.off_ms, end) - max(self.on_ms, start))


@dataclass(frozen=True, slots=True)
class ChordEvent:
    """A window of time during which one harmony was sounding."""

    start_ms: float
    end_ms: float
    pitches: tuple[int, ...]
    bass_pitch: int
    onset_pitches: tuple[int, ...]
    pc_weights: tuple[tuple[int, float], ...]  # sorted (pc, weight); tuple so it stays hashable
    velocity_mean: float

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms

    @property
    def pcs(self) -> frozenset[int]:
        return frozenset(p for p, _ in self.pc_weights)

    @property
    def bass_pc(self) -> int:
        return pc(self.bass_pitch)

    def weights(self) -> dict[int, float]:
        return dict(self.pc_weights)


@dataclass(frozen=True, slots=True)
class ChordCandidate:
    """One possible reading of a :class:`ChordEvent`."""

    root_pc: int
    quality: str
    inversion: int
    bass_pc: int
    score: float
    extensions: tuple[str, ...] = ()
    slash_bass_pc: int | None = None

    @property
    def is_seventh(self) -> bool:
        return self.quality in {
            "dom7", "maj7", "min7", "m7b5", "dim7", "minmaj7", "7sus4",
        }


@dataclass(frozen=True, slots=True)
class IdentifiedChord:
    """A chord event resolved to its best reading, keeping runners-up."""

    event: ChordEvent
    candidates: tuple[ChordCandidate, ...]

    @property
    def best(self) -> ChordCandidate:
        return self.candidates[0]

    @property
    def duration_ms(self) -> float:
        return self.event.duration_ms


@dataclass(frozen=True, slots=True)
class Key:
    tonic_pc: int
    mode: Mode


@dataclass(frozen=True, slots=True)
class KeyEstimate:
    key: Key
    confidence: float
    alternatives: tuple[tuple[Key, float], ...] = ()
    method_scores: tuple[tuple[str, float], ...] = ()
    #: "matched" means the key was settled by which reading Hooktheory
    #: actually has songs for, not by pitch-class analysis alone.
    source: Literal["detected", "user", "matched"] = "detected"
    modulation_suspected: bool = False


@dataclass(frozen=True, slots=True)
class CpToken:
    """A chord successfully expressed in Hooktheory ``cp`` syntax."""

    token: str
    #: Token with any inversion suffix removed; what search actually queries.
    root_position_token: str
    chord_index: int
    fidelity: float
    roman: str


@dataclass(frozen=True, slots=True)
class Hole:
    """A chord that has no ``cp`` representation, or a key-region boundary.

    A hole is a hard barrier: no n-gram may span it. Skipping over one and
    joining its neighbours would fabricate a progression that was never played.
    """

    chord_index: int
    label: str
    reason: str


CpSequence = tuple[CpToken | Hole, ...]


@dataclass(frozen=True, slots=True)
class SongHit:
    artist: str
    song: str
    section: str
    url: str
    score: float = 0.0
    matched_ngrams: tuple[str, ...] = ()
    #: Link to the recording itself, when the source knows one.
    video_url: str = ""


@dataclass(frozen=True, slots=True)
class ArtistHit:
    artist: str
    score: float
    songs: tuple[str, ...] = ()


@dataclass(slots=True)
class HarmonicFeatures:
    """Derived purely from our own analysis -- never needs a Hooktheory match.

    This is what keeps matching alive when a take returns zero song hits, which
    is a common outcome given Hooktheory's exact-contiguous matching.
    """

    modal_usage: dict[str, float] = field(default_factory=dict)
    seventh_density: float = 0.0
    borrowed_rate: float = 0.0
    mean_progression_rarity: float = 0.0
    cadence_profile: dict[str, float] = field(default_factory=dict)
    key_spread: float = 0.0
    chord_variety: float = 0.0
    mean_chord_duration_s: float = 0.0
