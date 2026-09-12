"""
Feature engineering: user input + enriched metadata -> one numeric matrix.

THE MATH, IN ORDER
------------------
1. Roman numerals          key-invariance:   C-Am-F-G == G-Em-C-D
2. n-grams                 order matters:    IV->I is not I->IV
3. Surprisal weighting     w(g) = -log2 P(g). This is exactly TF-IDF's idf
                           term, except the probability comes from
                           Hooktheory instead of a corpus count.
4. Cyclic key encoding     key is a circle, not a number. C=0 and B=11 are
                           NOT 11 apart. We place keys on the circle of
                           FIFTHS (C-G-D-A...) because that is the distance
                           that matters harmonically, then take sin/cos.
5. Log tempo               tempo is perceived multiplicatively: 60->120 is
                           the same step as 120->240. And 140 ~ 70 (half
                           time), so we fold into one octave first.
6. Block normalisation     THE STEP EVERYONE SKIPS. If you have 60 genre
                           dummies and 4 numeric columns, raw cosine is 94%
                           genre. We L2-normalise each block separately,
                           then apply an explicit weight. Now the weights
                           mean what they say.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler

# --------------------------------------------------- 1. roman numerals ----

_QUALITY_ALIAS = {
    "maj7": "M7", "M7": "M7", "major7": "M7", "ma7": "M7",
    "min7": "7", "m7": "7", "-7": "7",
    "dim": "o", "o": "o", "dim7": "o7", "o7": "o7",
    "m7b5": "hdim7", "hdim7": "hdim7",
    "aug": "+", "+": "+",
    "sus": "sus4", "sus4": "sus4", "sus2": "sus2",
    "": "", "6": "6", "7": "7", "9": "9", "11": "11", "13": "13", "add9": "add9",
}
_ROMAN_RE = re.compile(r"^([b#]?)([ivIV]+)(.*)$")
_SECONDARY_RE = re.compile(r"^[b#]?[ivIV]+$")


def normalize_roman(token: str) -> Optional[str]:
    """'IImin7' -> 'ii7',  'I/3' -> 'I',  'V/V' -> 'V/V',  'Imaj7' -> 'IM7'.

    Case carries quality (ii minor, II major), the b/# prefix carries
    borrowing, the suffix carries extension. Inversions are dropped on
    purpose -- we want transposed AND revoiced progressions to collide.
    """
    if token is None:
        return None
    s = str(token).strip().replace(" ", "")
    if not s:
        return None
    secondary = ""
    if "/" in s:
        head, _, tail = s.partition("/")
        if _SECONDARY_RE.match(tail):     # V/V  -> keep, it is a real function
            secondary = "/" + tail
        s = head                           # I/3  -> drop, it is an inversion
    m = _ROMAN_RE.match(s)
    if not m:
        return None
    acc, num, suf = m.groups()
    is_minor = num == num.lower()
    qual = _QUALITY_ALIAS.get(suf, suf)
    if suf in ("min7", "m7", "-7"):
        is_minor, qual = True, "7"
    num = num.lower() if is_minor else num.upper()
    return f"{acc}{num}{qual}{secondary}"


def normalize_progression(seq: Sequence[str]) -> list[str]:
    out = [normalize_roman(t) for t in seq]
    return [t for t in out if t]


def is_extended(tok: str) -> bool:
    return bool(re.search(r"7|9|11|13|M7|hdim", tok))


def is_chromatic(tok: str) -> bool:
    return tok.startswith(("b", "#")) or "/" in tok


# ------------------------------------------------------------ 2. n-grams --

def ngrams(seq: Sequence[str], sizes: Sequence[int] = (2, 3)) -> dict[str, int]:
    out: dict[str, int] = {}
    for n in sizes:
        for i in range(len(seq) - n + 1):
            g = ">".join(seq[i:i + n])
            out[g] = out.get(g, 0) + 1
    return out


# ------------------------------------------------------------ 3. the user --

@dataclass
class UserInput:
    """WHAT YOU COLLECT DIRECTLY FROM THE USER. Nothing here needs an API."""
    user_id: str
    progressions: list[list[str]] = field(default_factory=list)  # from ChordCat
    genres: list[str] = field(default_factory=list)              # declared
    artists: list[str] = field(default_factory=list)             # declared
    songs: list[tuple[str, str]] = field(default_factory=list)   # (artist,title)
    tempo_pref: Optional[float] = None                           # or measured
    # measured while they play -- free, and not derivable from chords alone
    velocity_mean: Optional[float] = None
    voicing_density: Optional[float] = None


# -------------------------------------------------- 4. build a DataFrame --

_PITCH = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
          "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10,
          "Bb": 10, "B": 11}


def fold_tempo(bpm: float, lo: float = 70.0) -> float:
    """140 and 70 are the same groove at half time. Fold into [lo, 2*lo)."""
    if bpm is None or bpm <= 0:
        return float("nan")
    while bpm < lo:
        bpm *= 2
    while bpm >= 2 * lo:
        bpm /= 2
    return bpm


def build_dataframe(users: Iterable[UserInput], registry) -> pd.DataFrame:
    """One row per user. Raw, human-readable, still un-encoded -- this is the
    table you eyeball to check the enrichment actually worked."""
    rows = []
    for u in users:
        facts = registry.genre_facts(u.genres)
        for artist, title in u.songs:
            facts = facts.merge(registry.track_facts(artist, title))

        flat = [t for p in u.progressions for t in p]
        n = max(1, len(flat))
        grams: dict[str, int] = {}
        surprisal_total, counted = 0.0, 0
        for p in u.progressions:
            for g, c in ngrams(p).items():
                grams[g] = grams.get(g, 0) + c
            if len(p) >= 2:
                surprisal_total += registry.surprisal(p) / len(p)
                counted += 1

        rows.append({
            "user_id": u.user_id,
            "genres": sorted(set(u.genres) | set(facts.genres)),
            "tags": facts.tags,
            "artists": u.artists,
            "progressions": u.progressions,
            "ngrams": grams,
            "tempo_bpm": u.tempo_pref if u.tempo_pref is not None else facts.tempo_bpm,
            "key": facts.key,
            "mode": facts.mode,
            "energy": facts.energy,
            "valence": facts.valence,
            # derived from the numerals themselves -- always available
            "extension_rate": sum(is_extended(t) for t in flat) / n,
            "chromaticism": sum(is_chromatic(t) for t in flat) / n,
            "minor_ratio": sum(t[:1].islower() or t[1:2].islower() for t in flat) / n,
            "repertoire": len(set(flat)) / n,
            "harmonic_complexity": (surprisal_total / counted) if counted else np.nan,
            "velocity_mean": u.velocity_mean,
            "voicing_density": u.voicing_density,
            "enriched_by": ",".join(facts.sources),
        })
    return pd.DataFrame(rows).set_index("user_id")


# ------------------------------------------------- 5. encode to numbers ---

NUMERIC = ["tempo_log", "energy", "valence", "extension_rate", "chromaticism",
           "minor_ratio", "repertoire", "harmonic_complexity",
           "velocity_mean", "voicing_density"]

DEFAULT_WEIGHTS = {
    "progression": 0.40,   # what your hands do        <- the core signal
    "genre": 0.25,         # what you say you like
    "artist": 0.10,
    "numeric": 0.20,       # tempo / energy / complexity
    "key": 0.05,           # weakest: key is mostly an accident of the device
}


class FeatureSpace:
    """fit() on the population, transform() anyone -- including a brand new
    user, which is what you need at demo time."""

    def __init__(self, weights: Optional[dict] = None, ngram_min_users: int = 2):
        self.w = dict(DEFAULT_WEIGHTS, **(weights or {}))
        self.ngram_min_users = ngram_min_users
        self.mlb_genre = MultiLabelBinarizer()
        self.mlb_artist = MultiLabelBinarizer()
        self.scaler = StandardScaler()
        self.vocab_: list[str] = []
        self.surprisal_: dict[str, float] = {}
        self.blocks_: dict[str, slice] = {}
        self.columns_: list[str] = []

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _key_cycle(key: Optional[str]) -> tuple[float, float]:
        """Circle of FIFTHS, not chromatic. C and G are neighbours (one
        accidental apart); C and C# are as far apart as it gets."""
        if not key or key not in _PITCH:
            return (0.0, 0.0)                      # unknown -> origin, no vote
        fifths = (_PITCH[key] * 7) % 12
        ang = 2 * math.pi * fifths / 12
        return (math.cos(ang), math.sin(ang))

    @staticmethod
    def _l2(block: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(block, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return block / n

    # -- fit ----------------------------------------------------------------
    def fit(self, df: pd.DataFrame, registry=None) -> "FeatureSpace":
        self.mlb_genre.fit(df["genres"])
        self.mlb_artist.fit(df["artists"])

        # keep n-grams that at least N users have -- a progression only one
        # person played can never create a match, it only adds dimensions
        seen: dict[str, int] = {}
        for grams in df["ngrams"]:
            for g in grams:
                seen[g] = seen.get(g, 0) + 1
        self.vocab_ = sorted(g for g, c in seen.items() if c >= self.ngram_min_users)

        # weight each n-gram by how surprising it is
        self.surprisal_ = {}
        for g in self.vocab_:
            toks = g.split(">")
            s = registry.surprisal(toks) if registry is not None else None
            self.surprisal_[g] = s if s else math.log2(len(df) + 1)

        num = self._numeric_frame(df)
        self.scaler.fit(num)
        return self

    def _numeric_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        out["tempo_log"] = [math.log2(fold_tempo(b)) if pd.notna(b) else np.nan
                            for b in df["tempo_bpm"]]
        for c in NUMERIC:
            if c == "tempo_log":
                continue
            out[c] = pd.to_numeric(df[c], errors="coerce") if c in df else np.nan
        # median impute: a missing value should pull you to the middle of the
        # room, never to zero (zero is a *position*, and a confident one)
        return out.fillna(out.median(numeric_only=True)).fillna(0.0)

    # -- transform ----------------------------------------------------------
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        blocks, names, cols = [], [], []

        prog = np.zeros((len(df), len(self.vocab_)))
        idx = {g: i for i, g in enumerate(self.vocab_)}
        for r, grams in enumerate(df["ngrams"]):
            for g, c in grams.items():
                j = idx.get(g)
                if j is not None:
                    prog[r, j] = (1 + math.log(c)) * self.surprisal_[g]
        blocks.append(self._l2(prog) * self.w["progression"])
        names.append("progression")
        cols += [f"prog::{g}" for g in self.vocab_]

        gen = self.mlb_genre.transform(df["genres"]).astype(float)
        blocks.append(self._l2(gen) * self.w["genre"])
        names.append("genre")
        cols += [f"genre::{g}" for g in self.mlb_genre.classes_]

        art = self.mlb_artist.transform(df["artists"]).astype(float)
        blocks.append(self._l2(art) * self.w["artist"])
        names.append("artist")
        cols += [f"artist::{a}" for a in self.mlb_artist.classes_]

        num = self.scaler.transform(self._numeric_frame(df))
        blocks.append(self._l2(num) * self.w["numeric"])
        names.append("numeric")
        cols += [f"num::{c}" for c in (["tempo_log"] + [c for c in NUMERIC if c != "tempo_log"])]

        key = np.array([self._key_cycle(k) for k in df["key"]], dtype=float)
        minor = np.array([[1.0 if str(m).lower() == "minor" else 0.0]
                          for m in df["mode"]])
        kb = np.hstack([key, minor])
        blocks.append(self._l2(kb) * self.w["key"])
        names.append("key")
        cols += ["key::cos5th", "key::sin5th", "key::minor"]

        X = np.hstack(blocks)
        self.columns_ = cols
        start = 0
        self.blocks_ = {}
        for nm, b in zip(names, blocks):
            self.blocks_[nm] = slice(start, start + b.shape[1])
            start += b.shape[1]
        return X

    def fit_transform(self, df: pd.DataFrame, registry=None) -> np.ndarray:
        return self.fit(df, registry).transform(df)
