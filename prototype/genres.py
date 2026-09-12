"""
Genre tagging and filtering.

THE POINT
=========
CLAP was chosen because audio and text land in the SAME vector space. That
buys us zero-shot genre classification: we never train a genre classifier and
we never need a labelled dataset. We simply write down what each genre sounds
like in English, embed those sentences with the *text* half of CLAP, and ask
which sentence sits closest to the song's audio vector.

    cos( embed_audio(song.mp3), embed_text("a neo-soul song") )

That is the entire classifier. Adding a genre later costs one line of text --
no retraining, no new data. This is the payoff for the model choice in
embedders.py, and it is why genre filtering here is an AI feature rather than
a dropdown over metadata somebody typed.

PROMPT ENSEMBLING
=================
A single sentence is a noisy probe: "a rock song" also half-describes pop and
punk. So each genre gets several differently-worded prompts, we embed all of
them and average the result. Averaging cancels the wording-specific noise and
keeps what the prompts share -- the genre itself. (Same trick CLIP uses for
zero-shot image classification.) The averaged vector is re-normalised so all
genres remain comparable under cosine.

CALIBRATION
===========
Raw cosines between audio and text are all bunched in a narrow band and are
NOT probabilities. We softmax them with a temperature so the output is a
readable distribution, and we keep the raw cosine too so nothing is hidden.
A genre is only attached if it clears `min_score` -- an ambient field
recording should come back untagged rather than confidently "jazz".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

CACHE = Path(__file__).parent / "store" / "genre_text.npz"

# Taxonomy. Edit freely -- adding a genre needs no retraining, just prompts.
GENRE_PROMPTS: dict[str, list[str]] = {
    "neo-soul": ["a neo-soul song",
                 "smooth neo soul with lush seventh and ninth chords",
                 "warm soulful r&b with jazzy harmony and a laid back groove"],
    "jazz": ["a jazz song",
             "acoustic jazz with walking bass, brushed drums and piano",
             "improvised jazz with extended chords and swing feel"],
    "city pop": ["a city pop song",
                 "1980s japanese city pop with bright synths and funky bass",
                 "glossy retro pop with major seventh chords"],
    "pop": ["a pop song",
            "catchy mainstream pop with vocals and a clear chorus",
            "polished radio pop production"],
    "rock": ["a rock song",
             "guitar driven rock band with drums and bass",
             "classic rock with electric guitars"],
    "punk": ["a punk song",
             "fast aggressive punk rock with distorted power chords",
             "raw garage punk, loud and short"],
    "metal": ["a metal song",
              "heavy metal with double kick drums and heavily distorted guitars",
              "aggressive metal with screaming vocals"],
    "hip hop": ["a hip hop song",
                "rap over a boom bap drum beat",
                "hip hop instrumental with sampled soul loops"],
    "trap": ["a trap song",
             "trap beat with 808 bass, rolling hi hats and dark minor melody",
             "modern trap instrumental"],
    "house": ["a house track",
              "four on the floor house music with a steady kick and piano chords",
              "deep house with warm pads and a groovy bassline"],
    "techno": ["a techno track",
               "repetitive industrial techno with a driving machine beat",
               "dark minimal techno"],
    "drum and bass": ["a drum and bass track",
                      "fast breakbeat drum and bass with heavy sub bass",
                      "liquid dnb with rolling amen breaks"],
    "ambient": ["an ambient piece",
                "slow atmospheric ambient drone with no beat",
                "calm spacious soundscape, textural and floating"],
    "classical": ["a classical piece",
                  "orchestral classical music with strings and woodwinds",
                  "solo piano classical performance"],
    "folk": ["a folk song",
             "acoustic folk with fingerpicked guitar and gentle vocals",
             "singer songwriter acoustic ballad"],
    "country": ["a country song",
                "country music with steel guitar and twangy vocals",
                "americana with acoustic guitar and fiddle"],
    "reggae": ["a reggae song",
               "reggae with offbeat guitar skank and deep bass",
               "dub reggae with heavy echo"],
    "flamenco": ["a flamenco piece",
                 "spanish flamenco guitar with phrygian harmony and handclaps",
                 "passionate nylon string guitar with rapid strumming"],
    "funk": ["a funk song",
             "funk with slap bass, tight drums and rhythm guitar",
             "groovy funk horn section"],
    "lo-fi": ["a lo-fi hip hop track",
              "chill lofi beats with vinyl crackle and mellow keys",
              "relaxed study beats with soft drums"],
}

LABELS = list(GENRE_PROMPTS.keys())


def _l2(x: np.ndarray, axis=-1) -> np.ndarray:
    n = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


class GenreTagger:
    """Holds the text side of the space. Built once per (model, taxonomy)."""

    def __init__(self, embedder):
        if not hasattr(embedder, "embed_text"):
            raise RuntimeError(
                f"{embedder.name} has no text encoder -- zero-shot genre "
                "tagging needs a joint text-audio model such as CLAP.")
        self.embedder = embedder
        self.labels = LABELS
        self.T = self._build()

    def _signature(self) -> str:
        return f"{self.embedder.name}|{len(LABELS)}|{hash(tuple(LABELS)) & 0xffffff}"

    def _build(self) -> np.ndarray:
        sig = self._signature()
        if CACHE.exists():
            try:
                with np.load(CACHE, allow_pickle=False) as z:
                    if str(z["sig"]) == sig:
                        return z["T"]
            except Exception:
                pass

        rows = []
        for g in self.labels:
            prompts = GENRE_PROMPTS[g]
            E = self.embedder.embed_text(prompts)       # (n_prompts, dim)
            rows.append(_l2(np.mean(_l2(E, axis=1), axis=0), axis=0))
        T = np.vstack(rows).astype(np.float32)

        CACHE.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(CACHE, T=T, sig=np.array(sig))
        return T

    def score(self, audio_vec: np.ndarray, temperature: float = 0.02
              ) -> list[dict]:
        """-> every genre, ranked, with raw cosine AND calibrated probability."""
        q = _l2(np.asarray(audio_vec, dtype=np.float32), axis=0)
        cos = (self.T @ q).astype(float)
        z = (cos - cos.max()) / max(temperature, 1e-6)
        p = np.exp(z)
        p = p / p.sum()
        out = [{"genre": g, "cosine": round(float(c), 4), "p": round(float(pi), 4)}
               for g, c, pi in zip(self.labels, cos, p)]
        out.sort(key=lambda r: -r["p"])
        return out

    def tag(self, audio_vec: np.ndarray, top_k: int = 3,
            min_p: float = 0.08) -> list[str]:
        """The labels we are willing to attach. Deliberately conservative:
        something that matches nothing well comes back untagged rather than
        confidently wrong."""
        ranked = self.score(audio_vec)
        return [r["genre"] for r in ranked[:top_k] if r["p"] >= min_p]


# ------------------------------------------------------------- filtering --

def matches(song_genres, wanted) -> bool:
    """OR semantics: a song passes if it carries ANY selected genre.

    AND would be wrong here -- genres are overlapping descriptions, not
    exclusive categories, and requiring a song to be both 'jazz' and
    'neo-soul' would hide exactly the hybrids a discovery tool exists to find.
    """
    if not wanted:
        return True
    return bool(set(song_genres or []) & set(wanted))


def counts(songs) -> list[dict]:
    """Genre histogram over the library, for the filter bar."""
    c: dict[str, int] = {}
    for s in songs:
        for g in (s.get("genres") or []):
            c[g] = c.get(g, 0) + 1
    return sorted(({"genre": g, "n": n} for g, n in c.items()),
                  key=lambda r: (-r["n"], r["genre"]))
