"""Convert identified chords into Hooktheory ``cp`` tokens.

The central decision here is that the token table is **built by enumeration**,
not by hand-written branches for borrowed and applied chords. Enumerating every
``(prefix, degree)`` pair, resolving each to a concrete ``(offset, quality)``,
then dropping the tokens known to be dead makes it *structurally impossible* to
emit a token the API will reject -- which is the right shape for a syntax that
is community-documented rather than specified.

Token grammar::

    <mode-prefix><degree><inversion-suffix>[ / <applied-target> ]

    mode prefix     ""=major  B=minor  D=dorian  Y=phrygian
                    L=lydian  M=mixolydian  C=locrian
    inversion       triad:   ""   6    64
                    seventh: 7    65   43   42
    applied         5/x (V/x)  57/x (V7/x)  4/x (IV/x)  7/x (vii/x)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable, Sequence

from .events import CpSequence, CpToken, Hole, IdentifiedChord, Key
from .pitch import MODE_SCALES, Mode, roman_for

#: Hooktheory's own `child_path` values come back lowercase for the minor
#: prefix -- `b1`, `b4`, `b6` -- and it renders as a flat sign in their chord
#: HTML (`b6` displays as bVI). Matching their casing keeps our tokens readable
#: as the flats they are, rather than looking like B-something chords.
MODE_PREFIX: Final[dict[Mode, str]] = {
    "major": "", "minor": "b", "dorian": "D", "phrygian": "Y",
    "lydian": "L", "mixolydian": "M", "locrian": "C",
}
PREFIX_MODE: Final[dict[str, Mode]] = {v: k for k, v in MODE_PREFIX.items()}

#: Tokens the API is documented to return nothing for, because Hooktheory
#: deduplicates them into an equivalent spelling.
DEAD_TOKENS: Final[frozenset[str]] = frozenset(
    {"D1", "L2", "4/6", "D7", "M7", "4/4", "5/1", "4/1", "5/4", "7/1"}
)

#: Collision priority: when several tokens denote the same (offset, quality),
#: keep the first prefix listed here.
_PREFIX_PRIORITY: Final[tuple[str, ...]] = ("", "b", "M", "D", "L", "Y", "C")

#: Priority among applied-chord numerators. Secondary dominants first.
_APPLIED_PRIORITY: Final[tuple[str, ...]] = ("5", "57", "7", "4")

TRIAD_INVERSION_SUFFIX: Final[tuple[str, ...]] = ("", "6", "64")
SEVENTH_INVERSION_SUFFIX: Final[tuple[str, ...]] = ("7", "65", "43", "42")

#: How a chord quality is reduced for table lookup. Hooktheory's vocabulary is
#: triads and sevenths only.
_TRIAD_FAMILY: Final[dict[str, str]] = {
    "maj": "maj", "min": "min", "dim": "dim", "aug": "aug",
    "sus2": "sus", "sus4": "sus", "maj6": "maj", "min6": "min",
    "add9": "maj", "madd9": "min",
    "dom7": "maj", "maj7": "maj", "min7": "min",
    "m7b5": "dim", "dim7": "dim", "minmaj7": "min", "7sus4": "sus",
}
_SEVENTH_FAMILY: Final[dict[str, str]] = {
    "dom7": "dom7", "maj7": "maj7", "min7": "min7",
    "m7b5": "m7b5", "dim7": "dim7", "minmaj7": "minmaj7", "7sus4": "dom7",
}


def _quality_from_intervals(third: int, fifth: int) -> str:
    if third == 4 and fifth == 7:
        return "maj"
    if third == 3 and fifth == 7:
        return "min"
    if third == 3 and fifth == 6:
        return "dim"
    if third == 4 and fifth == 8:
        return "aug"
    return "maj"


def _seventh_quality(third: int, fifth: int, seventh: int) -> str:
    triad = _quality_from_intervals(third, fifth)
    if triad == "maj":
        return "maj7" if seventh == 11 else "dom7"
    if triad == "min":
        return "minmaj7" if seventh == 11 else "min7"
    if triad == "dim":
        return "dim7" if seventh == 9 else "m7b5"
    return "dom7"


def _diatonic_chord(mode: Mode, degree: int) -> tuple[int, str, str]:
    """``(offset, triad_quality, seventh_quality)`` of a degree within a mode."""
    scale = MODE_SCALES[mode]
    i = degree - 1
    root = scale[i]
    third = (scale[(i + 2) % 7] - root) % 12
    fifth = (scale[(i + 4) % 7] - root) % 12
    seventh = (scale[(i + 6) % 7] - root) % 12
    return root, _quality_from_intervals(third, fifth), _seventh_quality(
        third, fifth, seventh
    )


@dataclass(frozen=True, slots=True)
class CpEntry:
    token: str
    offset: int
    quality: str
    seventh: bool
    prefix: str


def _build_table() -> dict[tuple[int, str, bool], CpEntry]:
    """Enumerate every legal root-position token, keyed by what it *means*."""
    table: dict[tuple[int, str, bool], CpEntry] = {}

    def offer(entry: CpEntry) -> None:
        if entry.token in DEAD_TOKENS:
            return
        key = (entry.offset % 12, entry.quality, entry.seventh)
        existing = table.get(key)
        if existing is None or _rank(entry) < _rank(existing):
            table[key] = entry

    def _rank(e: CpEntry) -> tuple[int, int, int, str]:
        applied = 1 if "/" in e.token else 0
        try:
            prefix_rank = _PREFIX_PRIORITY.index(e.prefix)
        except ValueError:
            prefix_rank = len(_PREFIX_PRIORITY)
        # Among applied chords, a secondary dominant is overwhelmingly the more
        # likely reading: E major in C is V/vi, not IV/vii. Without this, the
        # numerators tie and sort alphabetically, which picks the wrong one.
        numerator = e.token.split("/")[0] if applied else ""
        applied_rank = _APPLIED_PRIORITY.index(numerator) if applied else 0
        return (applied, prefix_rank, applied_rank, e.token)

    for mode, prefix in MODE_PREFIX.items():
        for degree in range(1, 8):
            offset, triad_q, seventh_q = _diatonic_chord(mode, degree)
            offer(CpEntry(f"{prefix}{degree}", offset, triad_q, False, prefix))
            offer(CpEntry(f"{prefix}{degree}7", offset, seventh_q, True, prefix))

    # Applied chords, expressed against major-scale targets.
    major = MODE_SCALES["major"]
    for target in range(1, 8):
        t_off = major[target - 1]
        offer(CpEntry(f"5/{target}", (t_off + 7) % 12, "maj", False, "applied"))
        offer(CpEntry(f"57/{target}", (t_off + 7) % 12, "dom7", True, "applied"))
        offer(CpEntry(f"4/{target}", (t_off + 5) % 12, "maj", False, "applied"))
        offer(CpEntry(f"7/{target}", (t_off + 11) % 12, "dim", False, "applied"))

    return table


CP_TABLE: Final[dict[tuple[int, str, bool], CpEntry]] = _build_table()


def _inversion_suffix(token: str, seventh: bool, inversion: int) -> str:
    """Attach an inversion to an already-built root-position token."""
    if "/" in token:
        numerator, _, target = token.partition("/")
        return f"{_inversion_suffix(numerator, seventh, inversion)}/{target}"
    if seventh:
        base = token[:-1] if token.endswith("7") else token
        return base + SEVENTH_INVERSION_SUFFIX[min(inversion, 3)]
    return token + TRIAD_INVERSION_SUFFIX[min(inversion, 2)]


#: Progressive simplifications applied when a chord has no exact token, each
#: with the fidelity multiplier that discounts any match it eventually earns.
SIMPLIFY_CHAIN: Final[tuple[tuple[str, float], ...]] = (
    ("exact", 1.00),
    ("drop_extensions", 0.85),
    ("drop_seventh", 0.70),
    ("sus_to_triad", 0.50),
)


@dataclass(frozen=True, slots=True)
class CpConfig:
    strip_inversions: bool = True
    #: Prefer a slightly lower-scoring chord reading when it is the only one that
    #: Hooktheory can actually express. Lives here, not in identification, so the
    #: theory core stays honest and independently testable.
    representability_epsilon: float = 0.20


@dataclass(frozen=True, slots=True)
class CpResult:
    token: str | None
    root_position_token: str | None
    fidelity: float
    reason: str


def to_cp(
    chord: IdentifiedChord,
    key: Key,
    cfg: CpConfig = CpConfig(),
) -> CpResult:
    """Express one chord as a ``cp`` token, simplifying as far as needed."""
    for candidate in _preferred_order(chord, key, cfg):
        offset = (candidate.root_pc - key.tonic_pc) % 12
        quality = candidate.quality

        for step, fidelity in SIMPLIFY_CHAIN:
            resolved = _resolve(offset, quality, step, key)
            if resolved is None:
                continue
            entry, seventh = resolved
            token = entry.token
            if not cfg.strip_inversions and candidate.inversion:
                token = _inversion_suffix(token, seventh, candidate.inversion)
            return CpResult(token, entry.token, fidelity, step)

    label = _label(chord, key)
    return CpResult(None, None, 0.0, f"no cp representation for {label}")


def _preferred_order(
    chord: IdentifiedChord, key: Key, cfg: CpConfig
) -> Iterable:
    """Best candidate first, but promote a representable near-tie over a dead one."""
    cands = list(chord.candidates)
    if len(cands) < 2:
        return cands
    best = cands[0]
    for other in cands[1:]:
        if best.score - other.score > cfg.representability_epsilon:
            break
        best_ok = _resolve((best.root_pc - key.tonic_pc) % 12, best.quality, "exact", key)
        other_ok = _resolve(
            (other.root_pc - key.tonic_pc) % 12, other.quality, "exact", key
        )
        if best_ok is None and other_ok is not None:
            return [other, *(c for c in cands if c is not other)]
    return cands


def _resolve(
    offset: int, quality: str, step: str, key: Key
) -> tuple[CpEntry, bool] | None:
    if step == "exact":
        # The sus check must come first: 7sus4 is in both families, and a 7sus4
        # is emphatically not a dominant seventh. Letting the seventh branch win
        # would resolve Csus4/G7sus4 to a spurious V7.
        if _TRIAD_FAMILY.get(quality) == "sus":
            return None  # sus chords are inexpressible; sus_to_triad handles them
        seventh = quality in _SEVENTH_FAMILY
        lookup_quality = _SEVENTH_FAMILY[quality] if seventh else _TRIAD_FAMILY.get(quality)
        if lookup_quality is None:
            return None
        entry = CP_TABLE.get((offset, lookup_quality, seventh))
        return (entry, seventh) if entry else None

    if step == "drop_extensions":
        if quality not in {"add9", "madd9", "maj6", "min6"}:
            return None
        family = _TRIAD_FAMILY[quality]
        entry = CP_TABLE.get((offset, family, False))
        return (entry, False) if entry else None

    if step == "drop_seventh":
        if quality not in _SEVENTH_FAMILY:
            return None
        family = _TRIAD_FAMILY[quality]
        entry = CP_TABLE.get((offset, family, False))
        return (entry, False) if entry else None

    if step == "sus_to_triad":
        if _TRIAD_FAMILY.get(quality) != "sus":
            return None
        # Resolve the suspension toward whichever triad is diatonic here.
        for family in ("maj", "min"):
            entry = CP_TABLE.get((offset, family, False))
            if entry and entry.prefix == MODE_PREFIX[key.mode]:
                return entry, False
        for family in ("maj", "min"):
            entry = CP_TABLE.get((offset, family, False))
            if entry:
                return entry, False
        return None

    return None


def _label(chord: IdentifiedChord, key: Key) -> str:
    c = chord.best
    return roman_for((c.root_pc - key.tonic_pc) % 12, c.quality, key.mode)


def progression_to_cp(
    chords: Sequence[IdentifiedChord],
    key: Key,
    cfg: CpConfig = CpConfig(),
    *,
    key_regions: Sequence[int] = (),
) -> CpSequence:
    """Convert a whole progression, inserting holes where conversion fails.

    A hole is a hard barrier that no n-gram may span. Skipping an unconvertible
    chord and joining its neighbours would fabricate a progression that was never
    played, and Hooktheory only matches exact contiguous sequences anyway. Key
    region boundaries are barriers for the same reason: ``cp`` is key-relative,
    so a window spanning two keys is meaningless.
    """
    out: list[CpToken | Hole] = []
    for i, chord in enumerate(chords):
        if i in key_regions and i > 0:
            out.append(Hole(i, "", "key change"))
        result = to_cp(chord, key, cfg)
        if result.token is None or result.root_position_token is None:
            out.append(Hole(i, _label(chord, key), result.reason))
        else:
            out.append(
                CpToken(
                    token=result.token,
                    root_position_token=result.root_position_token,
                    chord_index=i,
                    fidelity=result.fidelity,
                    roman=_label(chord, key),
                )
            )
    return tuple(out)


def segments_without_holes(seq: CpSequence) -> list[list[CpToken]]:
    """Split a converted progression at every hole."""
    runs: list[list[CpToken]] = [[]]
    for item in seq:
        if isinstance(item, Hole):
            if runs[-1]:
                runs.append([])
        else:
            runs[-1].append(item)
    return [r for r in runs if r]
