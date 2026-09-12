"""HTTP endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from ..deps import get_services
from ..domain.events import Hole, Key, RawEvent
from ..domain.pitch import MODES, key_name, pc_name
from ..services.pipeline import analyse
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ArtistOut,
    ChordOut,
    HarmonicOut,
    KeyOut,
    MatchOut,
    ProfileOut,
    SongOut,
)

log = logging.getLogger(__name__)
router = APIRouter()

_QUALITY_SYMBOL = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus2": "sus2",
    "sus4": "sus4", "dom7": "7", "maj7": "maj7", "min7": "m7", "m7b5": "m7b5",
    "dim7": "dim7", "minmaj7": "mMaj7", "7sus4": "7sus4", "maj6": "6",
    "min6": "m6", "add9": "add9", "madd9": "madd9",
}


@router.get("/health")
async def health() -> dict:
    s = get_services()
    return {
        "ok": True,
        "hooktheory": s.client is not None,
        "genre_labels": getattr(getattr(s.genres, "static", s.genres), "size", 0),
        "personas": len(s.pool.personas),
        "offline": s.settings.chordcat_offline,
    }


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    services = get_services()

    raw = [
        RawEvent(kind=e.k, t=e.t, pitch=e.p, velocity=e.v, controller=e.n)
        for e in req.events
    ]
    if not raw:
        raise HTTPException(400, "no MIDI events supplied")

    override: Key | None = None
    if req.key_tonic_pc is not None and req.key_mode:
        if req.key_mode not in MODES:
            raise HTTPException(400, f"unknown mode {req.key_mode!r}")
        override = Key(req.key_tonic_pc, req.key_mode)  # type: ignore[arg-type]

    result = await analyse(
        raw,
        client=services.client,
        genres=services.genres,
        key_override=override,
        session_end_ms=req.session_end_ms,
        budget=req.budget or services.settings.song_request_budget,
        artist_document_frequency=services.cache.artist_frequencies(),
        corpus_size=services.cache.corpus_size(),
    )

    romans: list[str] = []
    cp_by_index: dict[int, str] = {}
    for item in result.cp_sequence:
        if isinstance(item, Hole):
            if item.label:
                romans.append(f"[{item.label}]")
        else:
            romans.append(item.roman)
            cp_by_index[item.chord_index] = item.root_position_token

    chords = [
        ChordOut(
            index=i,
            start_ms=c.event.start_ms,
            end_ms=c.event.end_ms,
            root=pc_name(c.best.root_pc),
            quality=c.best.quality,
            inversion=c.best.inversion,
            symbol=pc_name(c.best.root_pc) + _QUALITY_SYMBOL.get(c.best.quality, ""),
            roman=romans[i] if i < len(romans) else None,
            cp=cp_by_index.get(i),
            pitches=list(c.event.pitches),
        )
        for i, c in enumerate(result.chords)
    ]

    key_out = None
    if result.key_estimate is not None:
        k = result.key_estimate
        key_out = KeyOut(
            tonic_pc=k.key.tonic_pc,
            mode=k.key.mode,
            name=key_name(k.key.tonic_pc, k.key.mode),
            confidence=k.confidence,
            source=k.source,
            modulation_suspected=k.modulation_suspected,
            alternatives=[
                {
                    "tonic_pc": a.tonic_pc,
                    "mode": a.mode,
                    "name": key_name(a.tonic_pc, a.mode),
                    "confidence": c,
                }
                for a, c in k.alternatives
            ],
        )

    profile_out = None
    matches: list[MatchOut] = []
    if result.chords:
        p = result.profile
        h = p.harmonic
        profile_out = ProfileOut(
            genres=p.genre_weights,
            artists=p.artist_weights,
            eras=p.era_weights,
            moods=p.mood_weights,
            harmonic=HarmonicOut(
                mode=result.key_estimate.key.mode if result.key_estimate else "major",
                seventh_density=h.seventh_density,
                borrowed_rate=h.borrowed_rate,
                mean_progression_rarity=h.mean_progression_rarity,
                key_spread=h.key_spread,
                chord_variety=h.chord_variety,
                mean_chord_duration_s=h.mean_chord_duration_s,
                cadence_profile=h.cadence_profile,
            ),
            taste_document=p.taste_document(),
        )
        matches = [
            MatchOut(
                id=m.persona.id,
                name=m.persona.name,
                instrument=m.persona.instrument,
                city=m.persona.city,
                bio=m.persona.bio,
                score=m.breakdown.total,
                percentile=m.percentile,
                components={
                    "genre": m.breakdown.genre,
                    "artist": m.breakdown.artist,
                    "harmonic": m.breakdown.harmonic,
                    "mood": m.breakdown.mood,
                    "era": m.breakdown.era,
                },
                shared_artists=list(m.breakdown.shared_artists),
                shared_genres=list(m.breakdown.shared_genres),
                shared_harmonic=list(m.breakdown.shared_harmonic),
                rationale=m.rationale,
                signature_progression=m.persona.signature_progression,
            )
            for m in services.pool.rank(p, limit=8)
        ]

    notes: list[str] = []
    if services.client is None:
        notes.append(
            "Hooktheory is not configured, so no song matches were attempted. "
            "Chords, key and harmonic features are still real."
        )
    elif not result.search.songs:
        notes.append(
            "No song in the Hooktheory database uses this exact progression. "
            "Matching fell back to harmonic features, which is expected for "
            "anything unusual -- it only matches exact contiguous progressions."
        )
    if result.segmentation_mode == "grid":
        notes.append(
            "The input looked arpeggiated or sequenced, so chords were pooled "
            "into fixed time windows instead of by note onset."
        )
    if result.stuck_notes:
        notes.append(f"{result.stuck_notes} note(s) never received a note-off.")
    if result.key_estimate and result.key_estimate.source == "matched":
        notes.append(
            f"The key was settled as {key_out.name if key_out else ''} because "
            "that reading is the one Hooktheory actually has songs for."
        )
    if result.key_estimate and result.key_estimate.modulation_suspected:
        notes.append("A key change was detected; windows do not span it.")

    return AnalyzeResponse(
        session_id=str(uuid.uuid4()),
        chords=chords,
        key=key_out,
        cp=result.cp_string,
        romans=romans,
        unmapped=list(result.unmapped),
        songs=[
            SongOut(
                artist=s.artist, song=s.song, section=s.section, url=s.url,
                score=s.score, matched_ngrams=list(s.matched_ngrams),
            )
            for s in result.search.songs[:25]
        ],
        artists=[
            ArtistOut(artist=a.artist, score=a.score, songs=list(a.songs))
            for a in result.search.artists[:15]
        ],
        profile=profile_out,
        matches=matches,
        requests_spent=result.search.requests_spent,
        queried=result.search.queried,
        segmentation_mode=result.segmentation_mode,
        stuck_notes=result.stuck_notes,
        notes=notes,
    )
