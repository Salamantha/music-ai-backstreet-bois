"""HTTP endpoints."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..adapters.hooktheory import AuthError, HooktheoryError
from ..deps import get_services
from ..domain.chords import identify_chord
from ..domain.cp import to_cp
from ..domain.events import ChordEvent, Hole, IdentifiedChord, Key, RawEvent
from ..domain.pitch import MODES, key_name, pc_name, roman_for
from ..helper.analysis import run_all
from ..helper.concepts.graph import choose
from ..helper.concepts.schema import APPROVED, load_nodes
from ..helper.converse import ClaudeVoice, LayeredVoice, TemplateVoice
from ..helper.prepare import prepare
from ..helper.session import Session
from ..services.pipeline import analyse
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ArtistOut,
    CandidateOut,
    ChordOut,
    HarmonicOut,
    HelperFactOut,
    HelperTurnRequest,
    HelperTurnResponse,
    IdentifyRequest,
    IdentifyResponse,
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


def _symbol(root_pc: int, quality: str) -> str:
    return pc_name(root_pc) + _QUALITY_SYMBOL.get(quality, "")


def _chord_event(pitches: list[int], duration_ms: float = 600.0) -> ChordEvent:
    """Build a ChordEvent from a set of simultaneously sounding pitches."""
    weights: dict[int, float] = {}
    for p in pitches:
        weights[p % 12] = weights.get(p % 12, 0.0) + 1.0
    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}
    bass = min(pitches)
    weights[bass % 12] = weights.get(bass % 12, 0.0) + 0.6
    return ChordEvent(
        start_ms=0.0,
        end_ms=duration_ms,
        pitches=tuple(sorted(pitches)),
        bass_pitch=bass,
        onset_pitches=tuple(sorted(pitches)),
        pc_weights=tuple(sorted(weights.items())),
        velocity_mean=100.0,
    )


@router.get("/genres")
async def genres() -> dict:
    """Genres that can be chosen before an analysis runs."""
    from ..domain.taxonomy import selectable_genres

    return {"genres": list(selectable_genres())}


@router.get("/hooktheory/nodes")
async def hooktheory_nodes(cp: str = "") -> dict:
    """Raw next-chord probabilities for a child path.

    Powers the voice/harmoniser features, which need one probability lookup
    per bar rather than a full /analyze pipeline run. Goes through the same
    HttpHooktheoryClient, shared rate limiter and SQLite cache as /analyze --
    never a second client with its own quota.
    """
    services = get_services()
    if services.client is None:
        raise HTTPException(503, "Hooktheory is not configured")
    try:
        rows = await services.client.nodes(cp or None)
    except AuthError as e:
        raise HTTPException(502, str(e)) from e
    except HooktheoryError as e:
        raise HTTPException(503, f"Hooktheory unavailable: {e}") from e
    return {"cp": cp, "nodes": rows}


@router.get("/hooktheory/songs")
async def hooktheory_songs(cp: str, page: int = 1) -> dict:
    """Raw song hits for a child path, for the voice feature's 'used in' callouts."""
    services = get_services()
    if services.client is None:
        raise HTTPException(503, "Hooktheory is not configured")
    try:
        rows = await services.client.songs(cp, page)
    except AuthError as e:
        raise HTTPException(502, str(e)) from e
    except HooktheoryError as e:
        raise HTTPException(503, f"Hooktheory unavailable: {e}") from e
    return {"cp": cp, "page": page, "songs": rows}


@router.post("/identify", response_model=IdentifyResponse)
async def identify(req: IdentifyRequest) -> IdentifyResponse:
    """Identify one chord as it is being held.

    Deliberately does no network I/O, so it can be called on every change to the
    set of held notes without touching the shared Hooktheory quota.
    """
    pitches = sorted(set(req.pitches))
    if req.bass_pitch is not None and req.bass_pitch not in pitches:
        pitches = sorted({*pitches, req.bass_pitch})

    key: Key | None = None
    if req.key_tonic_pc is not None and req.key_mode in MODES:
        key = Key(req.key_tonic_pc, req.key_mode)  # type: ignore[arg-type]

    event = _chord_event(pitches)
    candidates = identify_chord(event, key=key)
    if not candidates:
        raise HTTPException(400, "could not identify a chord from those pitches")

    best = candidates[0]
    roman = cp_token = None
    if key is not None:
        result = to_cp(IdentifiedChord(event=event, candidates=candidates), key)
        cp_token = result.root_position_token
        roman = roman_for((best.root_pc - key.tonic_pc) % 12, best.quality, key.mode)

    return IdentifyResponse(
        symbol=_symbol(best.root_pc, best.quality)
        + ("(" + ",".join(best.extensions) + ")" if best.extensions else ""),
        root=pc_name(best.root_pc),
        quality=best.quality,
        inversion=best.inversion,
        extensions=list(best.extensions),
        bass=pc_name(event.bass_pc),
        roman=roman,
        cp=cp_token,
        pitch_classes=[pc_name(p) for p in sorted(event.pcs)],
        candidates=[
            CandidateOut(
                root=pc_name(c.root_pc),
                quality=c.quality,
                symbol=_symbol(c.root_pc, c.quality),
                inversion=c.inversion,
                extensions=list(c.extensions),
                score=c.score,
            )
            for c in candidates
        ],
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    services = get_services()

    if req.chords:
        # Step entry: the client already separated the chords, so render them as
        # a note stream rather than asking segmentation to re-derive boundaries
        # it cannot know better than the player did.
        raw = []
        t = 0.0
        for step in req.chords:
            for i, pitch in enumerate(sorted(set(step.pitches))):
                raw.append(RawEvent("on", t + i * 2.0, pitch, 100))
            for i, pitch in enumerate(sorted(set(step.pitches))):
                raw.append(RawEvent("off", t + step.duration_ms - 20 + i, pitch))
            t += step.duration_ms
        if req.session_end_ms is None:
            req = req.model_copy(update={"session_end_ms": t})
    else:
        raw = [
            RawEvent(kind=e.k, t=e.t, pitch=e.p, velocity=e.v, controller=e.n)
            for e in req.events
        ]
    if not raw:
        raise HTTPException(400, "no MIDI events or chords supplied")

    override: Key | None = None
    if req.key_tonic_pc is not None and req.key_mode:
        if req.key_mode not in MODES:
            raise HTTPException(400, f"unknown mode {req.key_mode!r}")
        override = Key(req.key_tonic_pc, req.key_mode)  # type: ignore[arg-type]

    result = await analyse(
        raw,
        client=services.client,
        genres=services.genres,
        theorytab=services.theorytab,
        key_override=override,
        wanted_genres=req.genres,
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

    if req.genres and not result.search.songs:
        notes.append(
            "No matched song is in the selected genre"
            f"{'s' if len(req.genres) > 1 else ''}. Clearing the filter will "
            "show everything the progression matched."
        )

    if not result.chords:
        d = result.diagnostics
        notes.append(
            f"No chords were identified from {d.get('raw_events', 0)} MIDI events."
        )
        if d.get("max_simultaneous", 0) < d.get("min_notes_for_chord", 3):
            notes.append(
                f"At most {d.get('max_simultaneous', 0)} note(s) ever sounded at "
                "once, so nothing formed a chord. If the ChordCat is streaming a "
                "sequencer track, make sure a harmony channel is selected rather "
                "than a bass or lead line."
            )
        elif d.get("dropped_too_few_notes", 0):
            notes.append(
                f"{d['dropped_too_few_notes']} of {d.get('clusters_found', 0)} "
                "candidate segments had fewer than "
                f"{d.get('min_notes_for_chord', 3)} notes sounding together. This "
                "usually means several tracks are interleaved, or the notes are "
                "arriving one at a time."
            )
        elif not d.get("notes_paired"):
            notes.append(
                "No note-on/note-off pairs were found. The stream may be clock "
                "or control messages only."
            )

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
                video_url=s.video_url, genres=list(s.genres),
                song_chords=list(s.song_chords),
                matched_chords=list(s.matched_chords),
                song_key=s.song_key, coverage=s.coverage,
                sections=list(s.sections),
            )
            for s in result.search.songs[:40]
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
        diagnostics=result.diagnostics,
        available_genres=result.available_genres,
        applied_genres=list(req.genres),
        notes=notes,
    )


#: Recorded ChordCat capture, so the helper can be seen working with no
#: hardware in the room. It lives under tests/ and is therefore absent from a
#: packaged install -- the endpoint says so rather than failing obscurely.
DEMO_CAPTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "midi"
    / "chordcat-8track-sequencer.json"
)


@router.get("/helper/demo", response_model=HelperTurnRequest)
async def helper_demo() -> HelperTurnRequest:
    """The bundled capture, in the shape `/helper/turn` expects."""
    if not DEMO_CAPTURE.exists():
        raise HTTPException(404, "no demo capture in this install")
    take = json.loads(DEMO_CAPTURE.read_text())
    return HelperTurnRequest(
        events=take["events"],
        elapsed_ms=take["elapsed_ms"],
        harmony_channel=take.get("harmony_channel"),
    )


@router.post("/helper/turn", response_model=HelperTurnResponse)
async def helper_turn(req: HelperTurnRequest) -> HelperTurnResponse:
    """One conversational turn over a take.

    Deliberately does no Hooktheory I/O: this is the teaching path, not the
    matching path, and it must stay responsive and quota-free.
    """
    channel = req.harmony_channel
    raw = [
        RawEvent(kind=e.k, t=e.t, pitch=e.p, velocity=e.v, controller=e.n)
        for e in req.events
        if not channel or e.c == channel
    ]
    session = Session(
        id=uuid.uuid4().hex[:12],
        events=raw,
        elapsed_ms=req.elapsed_ms,
        user_text=req.user_text,
        intent_tags=req.intent_tags,
        suggested_nodes=req.suggested_nodes,
        tried_nodes=req.tried_nodes,
    )

    analysis = prepare(session)
    facts = run_all(analysis).supported()
    choice = choose(facts, session, load_nodes())

    fact_out = [
        HelperFactOut(
            id=f.id, kind=f.kind, value=f.value,
            n_observations=f.n_observations, confidence=f.confidence,
        )
        for f in facts
    ]
    chords = [str(f.value) for f in facts.by_kind("harmony.chord")]
    key_fact = facts.get("harmony.key_estimate")

    if choice is None:
        return HelperTurnResponse(
            node_id=None, plain_name=None,
            text="Play a little more -- there is not enough here to say anything true yet.",
            why=[], distance=0, measured=True, tied_with=[], draft=False,
            templated=True, facts=fact_out, chords=chords,
            key=str(key_fact.value) if key_fact else None,
        )

    settings = get_services().settings if hasattr(get_services(), "settings") else None
    use_model = settings.has_anthropic and not settings.chordcat_offline if settings else False
    voice = LayeredVoice(ClaudeVoice()) if use_model else TemplateVoice()
    response = voice.respond(facts, choice, session.user_text)

    return HelperTurnResponse(
        node_id=choice.node.id,
        plain_name=choice.node.plain_name,
        text=response.text,
        why=list(choice.why),
        distance=choice.distance,
        measured=choice.measured,
        tied_with=list(choice.tied_with),
        draft=choice.node.status != APPROVED,
        templated=response.used_fallback,
        facts=fact_out,
        chords=chords,
        key=str(key_fact.value) if key_fact else None,
    )
