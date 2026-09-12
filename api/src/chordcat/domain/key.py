"""Detect the key and mode of a chord sequence.

Two independent methods, z-scored and blended:

* **Krumhansl-Schmuckler** correlation of a duration-weighted pitch-class
  histogram against tonal-hierarchy profiles.
* **Chord-set coverage**, which asks which key's diatonic chords best explain
  the chords actually identified, with bonuses for tonic framing and cadences.

The blend matters: KS is nearly blind to relative major/minor/dorian, because
those share an identical pitch-class set. The chord method's tonic and cadence
bonuses are the *only* signal that separates them, which is also why the user
override path is load-bearing rather than a nicety.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .events import IdentifiedChord, Key, KeyEstimate
from .pitch import MODE_CHARACTERISTIC_DEGREE, MODE_SCALES, MODES, Mode, scale_pcs

#: Krumhansl-Kessler tonal hierarchy profiles (major and minor are empirical).
KK_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
KK_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

#: How much the mode's characteristic degree is boosted in the derived profiles.
MODE_CHAR_BOOST = 1.25

#: Chord-coverage scoring weights.
W_DIATONIC = 1.0
W_ROOT_ONLY = 0.35
W_TONIC_FIRST = 0.15
W_TONIC_LAST = 0.15
W_CADENCE = 0.10
#: Share of total sounding time spent on the tonic chord. This is the single
#: strongest signal separating a mode from its own rotations (D dorian vs G
#: mixolydian vs C major all share one pitch-class set, so only *which chord
#: behaves as home* can tell them apart).
W_TONIC_PROMINENCE = 0.45

#: Blend of the two methods, and of the two histograms feeding method A.
W_KS = 0.55
W_CHORD = 0.45
ALPHA_NOTE_HIST = 0.6

_TRIAD_QUALITY = {
    (0, 4, 7): "maj", (0, 3, 7): "min", (0, 3, 6): "dim", (0, 4, 8): "aug",
}


def _derived_profile(mode: Mode) -> tuple[float, ...]:
    """Profile for a mode.

    Major and minor use the empirical Krumhansl-Kessler weights. The other five
    are *heuristic*: the major profile rotated onto the mode's own scale, with
    the characteristic degree boosted so e.g. dorian's natural 6 can outvote
    minor's b6. They are not empirically derived and should not be presented as
    though they were.
    """
    if mode == "major":
        return KK_MAJOR
    if mode == "minor":
        return KK_MINOR

    scale = MODE_SCALES[mode]
    major_scale = MODE_SCALES["major"]
    out = [1.5] * 12  # small floor for non-scale tones
    for degree, offset in enumerate(scale):
        out[offset] = KK_MAJOR[major_scale[degree]]
    char = scale[MODE_CHARACTERISTIC_DEGREE[mode]]
    out[char] *= MODE_CHAR_BOOST
    total = sum(out)
    return tuple(v * 12 / total * (sum(KK_MAJOR) / 12) for v in out)


PROFILES: dict[Mode, tuple[float, ...]] = {m: _derived_profile(m) for m in MODES}


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def _normalize(hist: Sequence[float]) -> list[float]:
    total = sum(hist)
    return [h / total for h in hist] if total else [0.0] * 12


def build_histogram(chords: Sequence[IdentifiedChord]) -> list[float]:
    """Blend a note histogram with a chord-root histogram.

    Root weighting is far more robust for harmonic material than raw note
    counts: it is immune to voicing, doubling and inversion, all of which a
    chord-voicing device varies freely.
    """
    note_hist = [0.0] * 12
    root_hist = [0.0] * 12
    for ch in chords:
        dur = max(ch.duration_ms, 1.0)
        for p, w in ch.event.pc_weights:
            note_hist[p] += dur * w
        root_hist[ch.best.root_pc] += dur

    n, r = _normalize(note_hist), _normalize(root_hist)
    return [ALPHA_NOTE_HIST * n[i] + (1 - ALPHA_NOTE_HIST) * r[i] for i in range(12)]


def _rotate(profile: Sequence[float], tonic_pc: int) -> list[float]:
    return [profile[(i - tonic_pc) % 12] for i in range(12)]


def _chord_coverage(
    chords: Sequence[IdentifiedChord], tonic_pc: int, mode: Mode
) -> float:
    if not chords:
        return 0.0
    scale = MODE_SCALES[mode]
    in_key = scale_pcs(tonic_pc, mode)
    diatonic: dict[int, str] = {}
    for degree_offset in scale:
        root = (tonic_pc + degree_offset) % 12
        third = (root + 3) % 12 in in_key and (root + 4) % 12 not in in_key
        fifth_dim = (root + 6) % 12 in in_key and (root + 7) % 12 not in in_key
        if fifth_dim and third:
            diatonic[root] = "dim"
        elif third:
            diatonic[root] = "min"
        else:
            diatonic[root] = "maj"

    total_dur = sum(max(c.duration_ms, 1.0) for c in chords)
    score = 0.0
    for ch in chords:
        dur = max(ch.duration_ms, 1.0)
        root, quality = ch.best.root_pc, ch.best.quality
        base = _TRIAD_QUALITY.get(
            tuple(sorted({0, *(i % 12 for i in _triad_intervals(quality))}))[:3], None
        ) or _simple_quality(quality)
        if root in diatonic and diatonic[root] == base:
            score += dur * W_DIATONIC
        elif root in diatonic:
            score += dur * W_ROOT_ONLY

    tonic_dur = sum(
        max(c.duration_ms, 1.0) for c in chords if c.best.root_pc == tonic_pc
    )
    score += total_dur * W_TONIC_PROMINENCE * (tonic_dur / total_dur)

    if chords[0].best.root_pc == tonic_pc:
        score += total_dur * W_TONIC_FIRST
    if chords[-1].best.root_pc == tonic_pc:
        score += total_dur * W_TONIC_LAST

    dominant = (tonic_pc + 7) % 12
    subtonic = (tonic_pc + 10) % 12
    for a, b in zip(chords, chords[1:]):
        if b.best.root_pc != tonic_pc:
            continue
        if a.best.root_pc == dominant:
            score += total_dur * W_CADENCE
        elif mode in ("mixolydian", "dorian", "minor") and a.best.root_pc == subtonic:
            score += total_dur * W_CADENCE
    return score


def _triad_intervals(quality: str) -> tuple[int, ...]:
    from .chords import TEMPLATES

    return TEMPLATES.get(quality, (0, 4, 7))[:3]


def _simple_quality(quality: str) -> str:
    if quality in {"min", "min7", "min6", "madd9", "minmaj7"}:
        return "min"
    if quality in {"dim", "dim7", "m7b5"}:
        return "dim"
    if quality == "aug":
        return "aug"
    return "maj"


def _zscore(values: Sequence[float]) -> list[float]:
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / n)
    return [(v - mean) / sd for v in values] if sd else [0.0] * n


@dataclass(frozen=True, slots=True)
class KeyConfig:
    #: Low, because the softmax runs over 84 candidates: at T=1.0 even a clear
    #: winner reports ~6% and the number means nothing to a user.
    softmax_temperature: float = 0.25
    modulation_window: int = 8
    modulation_min_runs: int = 2
    top_alternatives: int = 4


def detect_key(
    chords: Sequence[IdentifiedChord], cfg: KeyConfig = KeyConfig()
) -> KeyEstimate:
    """Estimate the key and mode, with ranked alternatives for UI override."""
    if not chords:
        return KeyEstimate(Key(0, "major"), 0.0)

    hist = build_histogram(chords)
    candidates: list[Key] = [Key(t, m) for m in MODES for t in range(12)]

    ks_raw = [_pearson(hist, _rotate(PROFILES[k.mode], k.tonic_pc)) for k in candidates]
    ch_raw = [_chord_coverage(chords, k.tonic_pc, k.mode) for k in candidates]

    ks_z, ch_z = _zscore(ks_raw), _zscore(ch_raw)
    combined = [W_KS * a + W_CHORD * b for a, b in zip(ks_z, ch_z)]

    exps = [math.exp(c / cfg.softmax_temperature) for c in combined]
    total = sum(exps) or 1.0
    probs = [e / total for e in exps]

    order = sorted(range(len(candidates)), key=lambda i: -combined[i])
    best_i = order[0]

    # Offer alternatives that span different tonal centres. Ranking purely by
    # score fills the list with five modes of one tonic -- G major, G minor, G
    # dorian, G lydian -- which is useless as an override affordance, because
    # the reading the user actually wants is usually a *different* tonic
    # (typically the relative major or minor).
    alternatives: list[tuple[Key, float]] = []
    seen_tonics = {candidates[best_i].tonic_pc}
    for i in order[1:]:
        if len(alternatives) >= cfg.top_alternatives:
            break
        if candidates[i].tonic_pc in seen_tonics:
            continue
        seen_tonics.add(candidates[i].tonic_pc)
        alternatives.append((candidates[i], probs[i]))
    # Backfill with same-tonic modes only if there is room left over.
    for i in order[1:]:
        if len(alternatives) >= cfg.top_alternatives:
            break
        pair = (candidates[i], probs[i])
        if pair not in alternatives:
            alternatives.append(pair)
    alternatives = tuple(alternatives)

    return KeyEstimate(
        key=candidates[best_i],
        confidence=probs[best_i],
        alternatives=alternatives,
        method_scores=(("ks", ks_raw[best_i]), ("chord", ch_raw[best_i])),
        source="detected",
        modulation_suspected=_suspect_modulation(chords, cfg),
    )


def _suspect_modulation(
    chords: Sequence[IdentifiedChord], cfg: KeyConfig
) -> bool:
    """Slide a window over the sequence and look for a sustained key change.

    A single divergent window is noise; two or more consecutive windows
    disagreeing with the global estimate is evidence of a real modulation, which
    matters because `cp` tokens are key-relative and must not span the boundary.
    """
    w = cfg.modulation_window
    if len(chords) < w * 2:
        return False

    windows = [chords[i : i + w] for i in range(0, len(chords) - w + 1, max(w // 2, 1))]
    keys = []
    for win in windows:
        hist = build_histogram(win)
        cands = [Key(t, m) for m in MODES for t in range(12)]
        scores = [_pearson(hist, _rotate(PROFILES[k.mode], k.tonic_pc)) for k in cands]
        keys.append(cands[max(range(len(cands)), key=lambda i: scores[i])].tonic_pc)

    runs, longest = 1, 1
    for a, b in zip(keys, keys[1:]):
        runs = runs + 1 if a != b else 1
        longest = max(longest, runs)
    return longest > cfg.modulation_min_runs
