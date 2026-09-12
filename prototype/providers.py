"""
Enrichment layer.
==================================================================
The recommender NEVER imports a provider. It asks the Registry for facts and
gets back a plain dataclass. Swap Hooktheory for something else, add Last.fm,
delete MusicBrainz -- features.py and recommend.py do not change.

    Registry(providers=[Offline()])            # no network, for the demo
    Registry(providers=[Hooktheory(), MusicBrainz(), Offline()])

Merge rule: providers are asked in order; the first non-None value for a
scalar field wins, list fields (genres, tags) are unioned. So put your most
trusted source first and a fallback last.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional, Protocol

CACHE_DIR = Path(os.environ.get("CHORDPRINT_CACHE", ".cache"))


# ----------------------------------------------------------------- schema --

@dataclass
class TrackFacts:
    """Everything an external source can tell us about one song/artist."""
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    tempo_bpm: Optional[float] = None
    key: Optional[str] = None          # 'C', 'F#', ...
    mode: Optional[str] = None         # 'major' | 'minor'
    energy: Optional[float] = None     # 0..1
    valence: Optional[float] = None    # 0..1  (mood: sad -> happy)
    sources: list[str] = field(default_factory=list)

    def merge(self, other: "TrackFacts") -> "TrackFacts":
        out = TrackFacts(
            genres=sorted(set(self.genres) | set(other.genres)),
            tags=sorted(set(self.tags) | set(other.tags)),
            sources=self.sources + [s for s in other.sources if s not in self.sources],
        )
        for f in ("tempo_bpm", "key", "mode", "energy", "valence"):
            setattr(out, f, getattr(self, f) if getattr(self, f) is not None
                    else getattr(other, f))
        return out


class Provider(Protocol):
    name: str
    def track_facts(self, artist: str, title: str) -> Optional[TrackFacts]: ...
    def progression_logprob(self, roman: list[str]) -> Optional[float]: ...


class _Base:
    """Default no-ops so a provider only implements what it actually knows."""
    name = "base"
    def track_facts(self, artist: str, title: str) -> Optional[TrackFacts]:
        return None
    def progression_logprob(self, roman: list[str]) -> Optional[float]:
        return None


# ------------------------------------------------------------ disk cache --

def _cache(key: str, produce):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = urllib.parse.quote(key, safe="")[:180]
    p = CACHE_DIR / f"{safe}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    val = produce()
    if val is not None:
        p.write_text(json.dumps(val), encoding="utf-8")
    return val


# ------------------------------------------------------------ Hooktheory --

class Hooktheory(_Base):
    """
    https://api.hooktheory.com/v1/

    Two endpoints only:
      GET trends/nodes?cp=4,1   -> next-chord probabilities
      GET trends/songs?cp=4,1   -> songs using that progression (no genre!)

    So Hooktheory answers ONE question for us, and answers it well:
    how surprising is this chord progression?  We do not need to count a
    corpus -- the API hands us P(next | context) directly.

    Auth: bearer token from POST users/auth with your hooktheory.com login.
    Set CHORDPRINT_HT_USER / CHORDPRINT_HT_PASS in your environment, or pass
    a token you already have. Never hard-code credentials in the repo.

    Rate limit: 10 requests / 10 seconds. Every call is cached on disk.
    """
    name = "hooktheory"
    BASE = "https://api.hooktheory.com/v1/"

    def __init__(self, token: Optional[str] = None, min_interval: float = 1.05):
        self.token = token or os.environ.get("CHORDPRINT_HT_TOKEN")
        self.min_interval = min_interval          # 10 per 10s -> 1 per second
        self._last = 0.0
        self._id_cache: dict[str, str] = {}

    # -- auth ---------------------------------------------------------------
    def login(self) -> Optional[str]:
        user = os.environ.get("CHORDPRINT_HT_USER")
        pw = os.environ.get("CHORDPRINT_HT_PASS")
        if not (user and pw):
            return None
        body = json.dumps({"username": user, "password": pw}).encode()
        req = urllib.request.Request(
            self.BASE + "users/auth", data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            self.token = json.load(r).get("activkey")
        return self.token

    # -- transport ----------------------------------------------------------
    def _get(self, path: str):
        if not self.token and not self.login():
            return None
        def go():
            gap = self.min_interval - (time.time() - self._last)
            if gap > 0:
                time.sleep(gap)
            req = urllib.request.Request(
                self.BASE + path,
                headers={"Authorization": f"Bearer {self.token}",
                         "Accept": "application/json",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.load(r)
            except Exception:
                return None
            finally:
                self._last = time.time()
        return _cache("ht_" + path, go)

    def nodes(self, cp: str = "") -> list[dict]:
        path = "trends/nodes" + (f"?cp={urllib.parse.quote(cp)}" if cp else "")
        return self._get(path) or []

    def songs(self, cp: str, page: int = 1) -> list[dict]:
        return self._get(f"trends/songs?cp={urllib.parse.quote(cp)}&page={page}") or []

    # -- roman numeral -> hooktheory chord_ID -------------------------------
    def _resolve(self, cp_prefix: str, roman_html: str) -> Optional[tuple[str, float]]:
        """Find the chord_ID for `roman_html` among the children of cp_prefix.

        We discover IDs from the API's own chord_HTML field rather than
        hard-coding their metasyntax -- so this keeps working if they add
        chord types, and never guesses.
        """
        for n in self.nodes(cp_prefix):
            if str(n.get("chord_HTML", "")).strip() == roman_html:
                return str(n["child_path"]), float(n.get("probability") or 0.0)
        return None

    def progression_logprob(self, roman: list[str]) -> Optional[float]:
        """log2 P(c1) + log2 P(c2|c1) + ... ; None if any chord is unknown.

        Chain rule:  P(c1..cn) = P(c1) * prod_i P(ci | c1..c(i-1))
        We report log2 so the numbers add instead of vanishing to 1e-9,
        and so -logprob is directly 'bits of surprise'.
        """
        if not roman:
            return None
        cp, total = "", 0.0
        for token in roman:
            hit = self._resolve(cp, token)
            if hit is None:
                return None
            cp, p = hit
            if p <= 0:
                return None
            total += math.log2(p)
        return total

    def songs_using(self, roman: list[str], page: int = 1) -> list[dict]:
        cp = ""
        for token in roman:
            hit = self._resolve(cp, token)
            if hit is None:
                return []
            cp = hit[0]
        return self.songs(cp, page)


# ----------------------------------------------------------- MusicBrainz --

class MusicBrainz(_Base):
    """Open, no API key, CC0 data. Gives genres and folksonomy tags.
    Requires a descriptive User-Agent and ~1 request/second (their rule)."""
    name = "musicbrainz"
    BASE = "https://musicbrainz.org/ws/2/"

    def __init__(self, app: str = "chordprint/0.1 (hackathon project)"):
        self.app = app
        self._last = 0.0

    def track_facts(self, artist: str, title: str) -> Optional[TrackFacts]:
        q = f'recording:"{title}" AND artist:"{artist}"'
        url = (self.BASE + "recording?query=" + urllib.parse.quote(q)
               + "&fmt=json&limit=1&inc=tags+genres")
        def go():
            gap = 1.05 - (time.time() - self._last)
            if gap > 0:
                time.sleep(gap)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.app})
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.load(r)
            except Exception:
                return None
            finally:
                self._last = time.time()
        data = _cache("mb_" + q, go)
        if not data or not data.get("recordings"):
            return None
        rec = data["recordings"][0]
        return TrackFacts(
            genres=[g["name"] for g in rec.get("genres", [])],
            tags=[t["name"] for t in rec.get("tags", [])],
            sources=[self.name],
        )


# ---------------------------------------------------------------- Offline --

class Offline(_Base):
    """Zero-network fallback keyed by GENRE, not by real artist -- we don't
    assert facts about real musicians we haven't verified. Values are
    illustrative defaults so the pipeline runs on a dead conference wifi.

    Replace with a real downloadable dataset (see DATASETS.md) by loading a
    CSV into `self.table`; the interface stays identical."""
    name = "offline"

    TABLE = {
        # genre        bpm   key  mode     energy valence
        "pop":        (118, "C", "major", 0.72, 0.70),
        "rock":       (132, "E", "major", 0.82, 0.58),
        "punk":       (168, "A", "major", 0.94, 0.55),
        "neo-soul":   (84,  "D", "major", 0.42, 0.62),
        "jazz":       (128, "F", "major", 0.48, 0.55),
        "house":      (124, "A", "minor", 0.80, 0.60),
        "trap":       (140, "G", "minor", 0.66, 0.30),
        "flamenco":   (96,  "E", "minor", 0.70, 0.40),
        "city pop":   (108, "C", "major", 0.62, 0.74),
        "ambient":    (72,  "D", "minor", 0.20, 0.45),
    }

    def __init__(self, table: Optional[dict] = None):
        self.table = table or dict(self.TABLE)

    def facts_for_genre(self, genre: str) -> Optional[TrackFacts]:
        row = self.table.get(genre)
        if not row:
            return None
        bpm, key, mode, energy, valence = row
        return TrackFacts(genres=[genre], tempo_bpm=bpm, key=key, mode=mode,
                          energy=energy, valence=valence, sources=[self.name])

    def track_facts(self, artist: str, title: str) -> Optional[TrackFacts]:
        return None

    def progression_logprob(self, roman: list[str]) -> Optional[float]:
        """Crude stand-in for Hooktheory when offline: a hand-set unigram
        prior over scale degrees, chained independently. Good enough to keep
        rare progressions scoring as rare; replace with the real API."""
        if not roman:
            return None
        prior = {"I": .19, "IV": .17, "V": .16, "vi": .15, "ii": .05, "iii": .04,
                 "viio": .01, "bVII": .03, "bVI": .025, "bIII": .02, "i": .12,
                 "IM7": .03, "ii7": .03, "V7": .05, "vi7": .02, "iii7": .01}
        total = 0.0
        for t in roman:
            total += math.log2(prior.get(t, 0.004))
        return total


# ---------------------------------------------------------------- Registry --

class Registry:
    """The seam. Everything downstream depends on this, not on providers."""

    def __init__(self, providers: Iterable[Provider]):
        self.providers = list(providers)

    def track_facts(self, artist: str, title: str) -> TrackFacts:
        out = TrackFacts()
        for p in self.providers:
            got = p.track_facts(artist, title)
            if got:
                out = out.merge(got)
        return out

    def genre_facts(self, genres: Iterable[str]) -> TrackFacts:
        """Facts for a user who named genres but no specific songs."""
        out = TrackFacts()
        for g in genres:
            for p in self.providers:
                fn = getattr(p, "facts_for_genre", None)
                if fn:
                    got = fn(g)
                    if got:
                        out = out.merge(got)
                        break
        return out

    def progression_logprob(self, roman: list[str]) -> Optional[float]:
        for p in self.providers:
            got = p.progression_logprob(roman)
            if got is not None:
                return got
        return None

    def surprisal(self, roman: list[str]) -> float:
        """Bits of surprise. THIS is the number that makes matching work:
        sharing a surprising progression means far more than sharing I-V-vi-IV.
        Unknown progression -> treat as maximally surprising."""
        lp = self.progression_logprob(roman)
        return 24.0 if lp is None else -lp


def default_registry(online: bool = False) -> Registry:
    ps: list[Provider] = []
    if online:
        ps += [Hooktheory(), MusicBrainz()]
    ps.append(Offline())
    return Registry(ps)
