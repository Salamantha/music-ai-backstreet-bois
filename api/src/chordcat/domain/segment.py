"""Turn a raw Web MIDI note stream into chord events.

Pure module. The only notion of time is the client-supplied ``t`` on each event.

The hard problems here are (a) deciding which simultaneously-sounding notes form
one chord when the player's fingers do not land together, and (b) deciding when
a chord has actually *changed* versus merely been re-voiced. Constants are
gathered in :class:`SegmentConfig` so they can be swept in tests.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal, Sequence

from .events import ChordEvent, RawEvent, Sounding
from .pitch import pc

SegmentationMode = Literal["onset", "grid"]

SUSTAIN_CC = 64
#: A batch whose timestamps regress further than this behind the previous batch's
#: maximum is rejected as a clock glitch rather than silently reordering history.
CLOCK_SLOP_MS = 250.0


@dataclass(frozen=True, slots=True)
class SegmentConfig:
    onset_window_ms: float = 60.0
    min_chord_dur_ms: float = 120.0
    min_notes_for_chord: int = 3
    release_grace_ms: float = 40.0
    legato_overlap_ms: float = 80.0
    passing_note_ms: float = 90.0
    pedal_weight: float = 0.5
    jaccard_same: float = 0.75
    onset_role_mult: float = 1.3
    bass_bonus: float = 0.6
    #: Fraction of onset clusters that must be single notes before we conclude the
    #: arpeggiator or sequencer is running and switch to grid pooling.
    arp_single_note_ratio: float = 0.70
    arp_min_clusters: int = 8
    grid_beats_per_window: int = 4
    grid_max_pcs: int = 5


@dataclass(frozen=True, slots=True)
class SegmentResult:
    events: tuple[ChordEvent, ...]
    mode: SegmentationMode
    #: Estimated inter-onset interval in ms when grid pooling kicked in.
    grid_ms: float | None = None
    stuck_notes: int = 0
    #: Why candidate segments were discarded. Producing zero chords from a large
    #: note stream is the confusing failure, so it has to explain itself.
    notes_paired: int = 0
    clusters_found: int = 0
    dropped_too_few_notes: int = 0
    max_simultaneous: int = 0


def pair_notes(
    raw: Sequence[RawEvent],
    *,
    session_end_ms: float | None = None,
    cfg: SegmentConfig = SegmentConfig(),
) -> tuple[list[Sounding], int]:
    """Pair note-on/note-off events into :class:`Sounding` spans.

    Handles the three things a real device does that a naive pairing gets wrong:
    a repeated note-on without an intervening note-off, a note-off that never
    arrives, and a note-off immediately followed by a note-on of the same pitch
    (re-articulation, or a MIDI retrigger -- one note, not two).
    """
    ordered = sorted(raw, key=lambda e: (e.t, 0 if e.kind == "off" else 1))
    end = session_end_ms if session_end_ms is not None else (
        max((e.t for e in ordered), default=0.0)
    )

    open_notes: dict[int, list[RawEvent]] = {}
    closed: list[Sounding] = []
    # Pitch -> index into `closed` of the most recently closed sounding, so a
    # quick off->on can be merged back into it.
    last_closed: dict[int, int] = {}
    pedal_down = False
    pedal_spans: list[tuple[float, float]] = []
    pedal_start = 0.0
    stuck = 0

    for ev in ordered:
        if ev.kind == "cc":
            if ev.controller == SUSTAIN_CC:
                down = ev.velocity >= 64
                if down and not pedal_down:
                    pedal_start, pedal_down = ev.t, True
                elif not down and pedal_down:
                    pedal_spans.append((pedal_start, ev.t))
                    pedal_down = False
            continue

        if ev.pitch is None:
            continue

        if ev.kind == "on" and ev.velocity == 0:
            # Running-status note-off: on with velocity 0.
            ev = RawEvent("off", ev.t, ev.pitch)

        if ev.kind == "on":
            idx = last_closed.get(ev.pitch)
            if idx is not None and ev.t - closed[idx].off_ms <= cfg.release_grace_ms:
                # Re-articulation: reopen the note we just closed.
                reopened = closed.pop(idx)
                last_closed.pop(ev.pitch, None)
                _reindex(last_closed, idx)
                open_notes.setdefault(ev.pitch, []).append(
                    RawEvent("on", reopened.on_ms, ev.pitch, reopened.velocity)
                )
            else:
                open_notes.setdefault(ev.pitch, []).append(ev)
        else:
            stack = open_notes.get(ev.pitch)
            if not stack:
                continue
            start = stack.pop(0)
            closed.append(Sounding(ev.pitch, start.velocity, start.t, ev.t))
            last_closed[ev.pitch] = len(closed) - 1

    for pitch, stack in open_notes.items():
        for start in stack:
            closed.append(Sounding(pitch, start.velocity, start.t, end, stuck=True))
            stuck += 1

    if pedal_down:
        pedal_spans.append((pedal_start, end))

    closed = [_apply_pedal(s, pedal_spans, cfg) for s in closed]
    closed.sort(key=lambda s: (s.on_ms, s.pitch))
    return closed, stuck


def _reindex(last_closed: dict[int, int], removed: int) -> None:
    for k, v in list(last_closed.items()):
        if v > removed:
            last_closed[k] = v - 1


def _apply_pedal(
    s: Sounding, spans: list[tuple[float, float]], cfg: SegmentConfig
) -> Sounding:
    """Extend a note held only by the sustain pedal, and flag it as pedal-only."""
    for lo, hi in spans:
        if lo <= s.off_ms <= hi and hi > s.off_ms:
            return Sounding(s.pitch, s.velocity, s.on_ms, hi, s.stuck, pedal_only=True)
    return s


def _cluster_onsets(
    notes: Sequence[Sounding], cfg: SegmentConfig
) -> list[tuple[float, list[Sounding]]]:
    """Group note onsets into chords.

    The window is measured from the *first* onset of each cluster and never
    chained -- chaining lets a slow arpeggio absorb the entire take, one note at
    a time, into a single meaningless cluster.
    """
    clusters: list[tuple[float, list[Sounding]]] = []
    i = 0
    ordered = sorted(notes, key=lambda s: s.on_ms)
    while i < len(ordered):
        t0 = ordered[i].on_ms
        members = [n for n in ordered[i:] if n.on_ms <= t0 + cfg.onset_window_ms]
        i += len(members)
        clusters.append((statistics.median([m.on_ms for m in members]), members))
    return clusters


def _build_event(
    start: float,
    end: float,
    onset_members: Sequence[Sounding],
    all_notes: Sequence[Sounding],
    cfg: SegmentConfig,
) -> ChordEvent | None:
    span = max(end - start, 1e-6)
    onset_pitches = {n.pitch for n in onset_members}

    members: list[Sounding] = []
    for n in all_notes:
        audible = (
            n.on_ms <= start + cfg.onset_window_ms
            and n.off_ms > start + min(cfg.legato_overlap_ms, span * 0.5)
        )
        if not audible:
            continue
        if n.pitch not in onset_pitches and n.overlap_ms(start, end) < cfg.passing_note_ms:
            continue  # passing tone from the previous chord
        members.append(n)

    if not members:
        return None

    weights: dict[int, float] = {}
    for n in members:
        mult = cfg.onset_role_mult if n.pitch in onset_pitches else 1.0
        if n.pedal_only:
            mult *= cfg.pedal_weight
        weights[pc(n.pitch)] = weights.get(pc(n.pitch), 0.0) + (
            n.overlap_ms(start, end) / span
        ) * mult

    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}
    bass_pitch = min(n.pitch for n in members)
    weights[pc(bass_pitch)] = weights.get(pc(bass_pitch), 0.0) + cfg.bass_bonus

    return ChordEvent(
        start_ms=start,
        end_ms=end,
        pitches=tuple(sorted(n.pitch for n in members)),
        bass_pitch=bass_pitch,
        onset_pitches=tuple(sorted(onset_pitches)),
        pc_weights=tuple(sorted(weights.items())),
        velocity_mean=statistics.fmean([n.velocity for n in members]) if members else 0.0,
    )


def _looks_arpeggiated(
    clusters: Sequence[tuple[float, list[Sounding]]], cfg: SegmentConfig
) -> tuple[bool, float | None]:
    """Detect a running arpeggiator or sequencer.

    Two signals must agree: most onset clusters hold a single note, *and* the
    inter-onset intervals have a sharp mode (a machine, not a human).
    """
    if len(clusters) < cfg.arp_min_clusters:
        return False, None
    singles = sum(1 for _, m in clusters if len(m) == 1)
    if singles / len(clusters) < cfg.arp_single_note_ratio:
        return False, None

    iois = [b[0] - a[0] for a, b in zip(clusters, clusters[1:]) if b[0] > a[0]]
    if len(iois) < 4:
        return False, None
    median = statistics.median(iois)
    if median <= 0:
        return False, None
    # Sharp mode: most intervals sit within 20% of the median.
    tight = sum(1 for x in iois if abs(x - median) <= 0.2 * median)
    if tight / len(iois) < 0.6:
        return False, None
    return True, median


def _grid_segments(
    notes: Sequence[Sounding], ioi_ms: float, cfg: SegmentConfig
) -> list[ChordEvent]:
    """Pool pitch classes into fixed windows when onset clustering is hopeless."""
    if not notes:
        return []
    start = min(n.on_ms for n in notes)
    end = max(n.off_ms for n in notes)
    window = ioi_ms * cfg.grid_beats_per_window

    events: list[ChordEvent] = []
    t = start
    while t < end:
        hi = min(t + window, end)
        members = [n for n in notes if n.overlap_ms(t, hi) > 0]
        if len(members) >= cfg.min_notes_for_chord:
            ev = _build_event(t, hi, members, members, cfg)
            if ev is not None:
                events.append(ev)
        t = hi
    return events


def segment_notes(
    notes: Sequence[Sounding],
    cfg: SegmentConfig = SegmentConfig(),
    *,
    session_end_ms: float | None = None,
) -> SegmentResult:
    """Segment paired notes into chord events.

    Merging of adjacent events is deliberately *not* done here: it needs chord
    identities, which live one layer up. See :func:`merge_identified`.
    """
    if not notes:
        return SegmentResult((), "onset")

    clusters = _cluster_onsets(notes, cfg)
    arp, ioi = _looks_arpeggiated(clusters, cfg)
    if arp and ioi is not None:
        return SegmentResult(
            tuple(_grid_segments(notes, ioi, cfg)), "grid", grid_ms=ioi,
            notes_paired=len(notes), clusters_found=len(clusters),
            max_simultaneous=_max_simultaneous(notes),
        )

    end = session_end_ms if session_end_ms is not None else max(n.off_ms for n in notes)
    boundaries = [t for t, _ in clusters] + [end]

    events: list[ChordEvent] = []
    too_few = 0
    for i, (t, members) in enumerate(clusters):
        seg_end = boundaries[i + 1]
        if seg_end <= t:
            continue
        ev = _build_event(t, seg_end, members, notes, cfg)
        if ev is None:
            continue
        if len(ev.pitches) < cfg.min_notes_for_chord or len(ev.pcs) < min(
            cfg.min_notes_for_chord, len(ev.pitches)
        ):
            too_few += 1
            continue
        events.append(ev)

    return SegmentResult(
        tuple(events), "onset",
        notes_paired=len(notes), clusters_found=len(clusters),
        dropped_too_few_notes=too_few, max_simultaneous=_max_simultaneous(notes),
    )


def _max_simultaneous(notes: Sequence[Sounding]) -> int:
    """Largest number of notes sounding at once across the take."""
    points: list[tuple[float, int]] = []
    for n in notes:
        points.append((n.on_ms, 1))
        points.append((n.off_ms, -1))
    points.sort()
    current = best = 0
    for _, delta in points:
        current += delta
        best = max(best, current)
    return best


def events_from_raw(
    raw: Sequence[RawEvent],
    cfg: SegmentConfig = SegmentConfig(),
    *,
    session_end_ms: float | None = None,
) -> SegmentResult:
    """Convenience: pair then segment."""
    notes, stuck = pair_notes(raw, session_end_ms=session_end_ms, cfg=cfg)
    result = segment_notes(notes, cfg, session_end_ms=session_end_ms)
    return SegmentResult(
        result.events, result.mode, result.grid_ms, stuck,
        result.notes_paired, result.clusters_found,
        result.dropped_too_few_notes, result.max_simultaneous,
    )
