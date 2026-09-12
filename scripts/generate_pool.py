#!/usr/bin/env python3
"""Build the synthetic musician pool, committed as `seed/personas.json`.

Each persona is defined by a *signature progression* in Hooktheory `cp` form.
The generator runs that progression through the real Trends API and builds the
persona's taste profile from the songs that actually come back, so the pool is
grounded in real data rather than invented artist lists.

This runs once; the output is committed. At runtime the app loads the file and
does a 40-row cosine -- no API calls, no vector database.

It also computes the pairwise similarity distribution across the pool and stores
it, so matches can be reported as a *percentile* rather than a raw cosine. A raw
0.8 means nothing to a user if everyone scores 0.8 against everyone.

    python scripts/generate_pool.py
"""

from __future__ import annotations

import asyncio
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "src"))

from chordcat.adapters.cache import SqliteCache  # noqa: E402
from chordcat.adapters.genre_llm import StaticGenreResolver  # noqa: E402
from chordcat.adapters.hooktheory import HttpHooktheoryClient, rows_to_hits  # noqa: E402
from chordcat.adapters.ratelimit import TokenBucket  # noqa: E402
from chordcat.config import get_settings  # noqa: E402
from chordcat.domain.events import HarmonicFeatures  # noqa: E402
from chordcat.domain.ngrams import Ngram  # noqa: E402
from chordcat.domain.profile import similarity  # noqa: E402
from chordcat.domain.ranking import NgramResult, rollup_artists, score_songs  # noqa: E402
from chordcat.services.pipeline import build_taste_profile  # noqa: E402

OUT = ROOT / "api/src/chordcat/seed/personas.json"

# name, instrument, city, signature cp, mode, bio
PERSONAS = [
    ("Mara Ellison", "guitar", "Portland, OR", "1,5,6,4", "major", "Writes in her kitchen at 2am. Believes the four chords still have something left."),
    ("Dev Raghunathan", "keys", "Brooklyn, NY", "4,5,3,6", "major", "Grew up on Final Fantasy soundtracks and never really left."),
    ("Yuki Tanabe", "synth", "Osaka, JP", "4,5,3,6", "major", "Makes city pop for people stuck on trains."),
    ("Colm Feeney", "piano", "Dublin, IE", "B1,B6,B3,B7", "minor", "Minor keys, long reverb, one take."),
    ("Priya Nandakumar", "guitar", "Austin, TX", "6,4,1,5", "major", "Loud amps, soft lyrics."),
    ("Tobias Lindqvist", "keys", "Stockholm, SE", "1,5,6,4", "major", "Swedish pop factory training, indie budget."),
    ("Renata Dias", "guitar", "Lisbon, PT", "2,5,1", "major", "Bossa nova by way of a jazz degree she didn't finish."),
    ("Aisha Bello", "bass", "Lagos, NG", "1,4,1,5", "major", "Afrobeat rhythm section, gospel harmony."),
    ("Jonah Pike", "guitar", "Sheffield, UK", "6,4,1,5", "major", "Britpop revivalist, unrepentant."),
    ("Silje Haugen", "synth", "Oslo, NO", "B1,B7,B6,B7", "minor", "Cold synths, warmer than they sound."),
    ("Marcus Adeyemi", "keys", "Atlanta, GA", "1,6,2,5", "major", "Neo-soul changes over trap drums."),
    ("Elena Vasquez", "guitar", "Mexico City, MX", "B1,B6,B7,B5", "minor", "Flamenco fingers, shoegaze pedals."),
    ("Rory McAllister", "piano", "Glasgow, UK", "1,4,5,4", "major", "Folk songs that turn into anthems by the third chorus."),
    ("Nina Kowalski", "keys", "Warsaw, PL", "6,2,5,1", "major", "Studied Chopin, plays in a basement."),
    ("Theo Marchand", "guitar", "Montreal, QC", "4,1,5,6", "major", "Bilingual lyrics, monolingual guitar tone."),
    ("Hana Park", "synth", "Seoul, KR", "1,5,6,4", "major", "K-pop demo writer trying to escape the demo."),
    ("Isaac Brenner", "piano", "Tel Aviv, IL", "B1,B4,B5,B1", "minor", "Klezmer scales in a jazz trio."),
    ("Cleo Anand", "guitar", "London, UK", "1,3,6,4", "major", "That one borrowed chord is the whole song."),
    ("Viktor Novak", "keys", "Prague, CZ", "B6,B7,B1", "minor", "Film score ambitions, bedroom equipment."),
    ("Sadie Kwon", "guitar", "Vancouver, BC", "4,5,6,1", "major", "Dream pop, drowned vocals."),
    ("Emeka Okafor", "bass", "Houston, TX", "1,B7,4,1", "mixolydian", "Church bass player gone secular."),
    ("Luca Ferrari", "piano", "Milan, IT", "2,5,1,6", "major", "Standards, then something stranger."),
    ("Astrid Bergman", "synth", "Copenhagen, DK", "B1,B3,B7,B4", "minor", "Ambient washes, techno pulse."),
    ("Jamal Rivers", "keys", "Detroit, MI", "1,6,4,5", "major", "Motown inheritance, house music future."),
    ("Freya Sørensen", "guitar", "Bergen, NO", "B1,B7,B3,B6", "minor", "Black metal training, folk songwriting."),
    ("Nadia Haddad", "keys", "Beirut, LB", "Y1,Y2,Y1,Y7", "phrygian", "Maqam scales meeting western harmony badly, on purpose."),
    ("Oscar Delgado", "guitar", "Buenos Aires, AR", "B1,B5,B6,B7", "minor", "Tango grandfather, post-rock band."),
    ("Wren Halliday", "piano", "Melbourne, AU", "1,4,6,5", "major", "Writes for other people, sings anyway."),
    ("Kai Nakamura", "synth", "Tokyo, JP", "4,5,3,6", "major", "Vocaloid producer with a day job."),
    ("Sofia Marchetti", "guitar", "Rome, IT", "6,4,1,5", "major", "Italo-disco chords, indie rock volume."),
    ("Bram de Vries", "keys", "Amsterdam, NL", "1,5,4,5", "major", "Festival main stage, 2am set."),
    ("Zoe Okonkwo", "guitar", "Manchester, UK", "B1,B6,B7,B5", "minor", "Grime-adjacent guitarist. Yes, really."),
    ("Anders Holm", "piano", "Helsinki, FI", "1,2,4,5", "major", "Sad in a major key, which is harder."),
    ("Talia Mizrahi", "synth", "Berlin, DE", "B1,B4,B1,B5", "minor", "Four-to-the-floor with a music theory problem."),
    ("Finn Gallagher", "guitar", "Cork, IE", "1,4,5,1", "major", "Trad sessions, then a Fender."),
    ("Mei Ling Chua", "keys", "Singapore, SG", "1,6,2,5", "major", "Jazz standards for a generation that streams them."),
    ("Rafael Santos", "bass", "São Paulo, BR", "2,5,1,4", "major", "Bossa, samba, and a lot of seventh chords."),
    ("Ingrid Halvorsen", "guitar", "Reykjavik, IS", "4,1,5,6", "major", "Plays slowly on purpose."),
    ("Omar Farouk", "keys", "Cairo, EG", "Y1,Y7,Y6,Y7", "phrygian", "Modal loops that refuse to resolve."),
    ("Bea Lindgren", "guitar", "Gothenburg, SE", "1,5,6,3", "major", "Pop punk chords, folk tempo."),
]


async def main() -> int:
    settings = get_settings()
    if not settings.has_hooktheory:
        print("FAIL: HOOKTHEORY_* not set in .env")
        return 2

    cache = SqliteCache(ROOT / "api/var/chordcat.db")
    client = HttpHooktheoryClient(
        settings.hooktheory_username, settings.hooktheory_password,
        TokenBucket(), cache=cache,
    )
    genres = StaticGenreResolver(ROOT / "api/src/chordcat/data/artist_genres.json")

    records = []
    try:
        await client.authenticate()
        for i, (name, instrument, city, cp, mode, bio) in enumerate(PERSONAS, 1):
            tokens = tuple(cp.split(","))
            rows = await client.songs(cp)
            hits = rows_to_hits(rows)
            ngram = Ngram(tokens, multiplicity=2, fidelity=1.0, opens_take=True)
            songs = score_songs([NgramResult(ngram, hits, total_hits=len(hits))])
            artists = rollup_artists(songs)

            harmonic = HarmonicFeatures(
                modal_usage={mode: 1.0},
                seventh_density=0.35 if "7" in cp else 0.05,
                borrowed_rate=0.4 if any(t.startswith(("B", "Y", "M", "L")) for t in tokens) else 0.05,
                mean_progression_rarity=1.6 if len(hits) < 20 else 0.8,
                cadence_profile={"authentic": 0.3} if tokens[-1] in ("1", "B1") else {"plagal": 0.2},
                key_spread=len(set(tokens)) / 12,
                chord_variety=len(set(tokens)) / len(tokens),
                mean_chord_duration_s=2.0,
            )
            profile = await build_taste_profile(songs, harmonic, genres)

            records.append({
                "id": f"p{i:02d}",
                "name": name,
                "instrument": instrument,
                "city": city,
                "bio": bio,
                "signature_progression": cp,
                "mode": mode,
                "profile": {
                    "genre_weights": profile.genre_weights,
                    "artist_weights": profile.artist_weights,
                    "era_weights": profile.era_weights,
                    "mood_weights": profile.mood_weights,
                    "harmonic": {
                        "modal_usage": harmonic.modal_usage,
                        "seventh_density": harmonic.seventh_density,
                        "borrowed_rate": harmonic.borrowed_rate,
                        "mean_progression_rarity": harmonic.mean_progression_rarity,
                        "cadence_profile": harmonic.cadence_profile,
                        "key_spread": harmonic.key_spread,
                        "chord_variety": harmonic.chord_variety,
                        "mean_chord_duration_s": harmonic.mean_chord_duration_s,
                    },
                },
                "top_artists": [a.artist for a in artists[:6]],
                "song_matches": len(hits),
            })
            print(f"[{i:2d}/{len(PERSONAS)}] {name:22.22s} {cp:14s} {len(hits):3d} songs"
                  f"  {', '.join(a.artist for a in artists[:3])[:44]}")
    finally:
        await client.aclose()

    # Calibration: without the pairwise distribution a raw cosine is
    # uninterpretable, because everyone scores highly against everyone.
    from chordcat.domain.profile import TasteProfile
    profiles = {}
    for r in records:
        h = r["profile"]["harmonic"]
        profiles[r["id"]] = TasteProfile(
            genre_weights=r["profile"]["genre_weights"],
            artist_weights=r["profile"]["artist_weights"],
            era_weights=r["profile"]["era_weights"],
            mood_weights=r["profile"]["mood_weights"],
            harmonic=HarmonicFeatures(**h),
        )
    pairwise = sorted(
        similarity(profiles[a], profiles[b]).total
        for a, b in itertools.combinations(profiles, 2)
    )

    payload = {
        "schema_version": 1,
        "personas": records,
        "calibration": {
            "pairwise_similarities": [round(v, 5) for v in pairwise],
            "n_pairs": len(pairwise),
            "median": round(pairwise[len(pairwise) // 2], 4),
            "p90": round(pairwise[int(len(pairwise) * 0.9)], 4),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"\nwrote {len(records)} personas -> {OUT}")
    print(f"pairwise similarity: median={payload['calibration']['median']} "
          f"p90={payload['calibration']['p90']} over {len(pairwise)} pairs")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
