"""The unit of conversation: one person's playing, plus what they said about it.

Append-only and clock-free, like everything the analysis layer touches. Time is
client-supplied milliseconds, which is what the browser's Web MIDI API hands us.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.events import RawEvent


@dataclass(slots=True)
class Session:
    id: str
    events: list[RawEvent] = field(default_factory=list)
    device: str = "chordcat"
    #: Length of the capture. Segmentation needs it to close held notes.
    elapsed_ms: float = 0.0
    user_text: str | None = None
    intent_tags: list[str] = field(default_factory=list)
    #: Brief 4.1 -- the whole of memory. Without it the helper repeats itself
    #: on turn four and stops feeling like a guide.
    suggested_nodes: list[str] = field(default_factory=list)
    tried_nodes: list[str] = field(default_factory=list)
    override_count: int = 0
