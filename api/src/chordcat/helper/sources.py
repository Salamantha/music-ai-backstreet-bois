"""Where playing comes from.

v0 reads recorded captures only. That is deliberate: it means no hardware in the
room and no teammate's branch is ever a blocker. The live path is a second
implementation of this Protocol, not a change to anything above it.

Captures are JSON note streams as produced by the browser (`web/lib/webmidi.ts`),
not Standard MIDI Files -- MIDI never reaches Python as a file in this system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..domain.events import RawEvent
from .session import Session


class MidiSource(Protocol):
    def load(self) -> Session: ...


@dataclass(frozen=True, slots=True)
class FixtureSource:
    """One recorded take.

    A ChordCat capture interleaves all eight sequencer tracks, each on its own
    MIDI channel, so a take has to be narrowed to the one track carrying harmony
    before any of it means anything. The capture names that channel itself;
    pass ``channel`` to override, or ``0`` to keep every track.
    """

    path: Path
    channel: int | None = None

    def load(self) -> Session:
        take = json.loads(self.path.read_text())
        wanted = self.channel if self.channel is not None else take.get("harmony_channel")
        events = [
            RawEvent(
                kind=e["k"],
                t=e["t"],
                pitch=e.get("p"),
                velocity=e.get("v", 0),
                controller=e.get("n"),
            )
            for e in take["events"]
            if not wanted or e.get("c") == wanted
        ]
        return Session(
            id=self.path.stem,
            events=events,
            device=take.get("device", "chordcat"),
            elapsed_ms=float(take.get("elapsed_ms", 0.0)),
        )
