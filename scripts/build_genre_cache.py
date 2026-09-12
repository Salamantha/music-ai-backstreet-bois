#!/usr/bin/env python3
"""Build the committed artist -> genre/era/mood label file.

The table below is curated rather than generated at runtime, for three reasons:
the app then needs no API key to work, results are deterministic so the test
suite can assert on them, and Hooktheory's artist set is small and heavily
repeated so a fixed table covers the overwhelming majority of lookups.

Artists absent from this table resolve to `unknown: true`, which contributes
nothing to the genre vector but still counts as a shared artist. That is the
honest failure mode -- lower coverage beats confident wrongness, especially for
colliding names (Bush, Air, Low, America).

    python scripts/build_genre_cache.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "api/src/chordcat/data/artist_genres.json"

# artist: (genres, era, moods, subgenres)
TABLE: dict[str, tuple[list[str], str, list[str], list[str]]] = {
    # --- classic rock / 60s-70s canon -----------------------------------
    "The Beatles": (["rock", "pop", "psychedelic"], "pre-1970", ["playful", "nostalgic", "warm"], ["merseybeat"]),
    "The Rolling Stones": (["rock", "classic rock", "blues"], "pre-1970", ["defiant", "driving"], []),
    "Led Zeppelin": (["classic rock", "rock", "blues"], "1970s", ["aggressive", "driving"], ["hard rock"]),
    "Pink Floyd": (["psychedelic", "classic rock", "post-rock"], "1970s", ["brooding", "cinematic", "hypnotic"], ["prog rock"]),
    "Queen": (["classic rock", "rock", "pop"], "1970s", ["anthemic", "triumphant", "playful"], ["glam rock"]),
    "David Bowie": (["rock", "pop", "psychedelic"], "1970s", ["defiant", "dreamy"], ["glam rock"]),
    "Fleetwood Mac": (["classic rock", "pop", "folk"], "1970s", ["wistful", "warm"], ["soft rock"]),
    "The Beach Boys": (["pop", "rock"], "pre-1970", ["nostalgic", "wistful", "warm"], ["surf"]),
    "Bob Dylan": (["folk", "singer-songwriter", "americana"], "pre-1970", ["defiant", "wistful"], []),
    "Simon & Garfunkel": (["folk", "singer-songwriter"], "pre-1970", ["melancholic", "tender"], []),
    "The Who": (["classic rock", "rock"], "pre-1970", ["defiant", "anthemic"], []),
    "Eagles": (["classic rock", "country", "americana"], "1970s", ["nostalgic", "warm"], ["soft rock"]),
    "Elton John": (["pop", "classic rock"], "1970s", ["anthemic", "tender"], []),
    "Stevie Wonder": (["soul", "funk", "r&b"], "1970s", ["warm", "euphoric", "playful"], ["motown"]),
    "Marvin Gaye": (["soul", "motown", "r&b"], "1970s", ["tender", "warm"], []),
    "Aretha Franklin": (["soul", "gospel", "r&b"], "pre-1970", ["triumphant", "warm"], []),
    "The Jackson 5": (["motown", "soul", "pop"], "1970s", ["euphoric", "playful"], []),
    "ABBA": (["pop", "disco"], "1970s", ["euphoric", "nostalgic"], []),
    "Bee Gees": (["disco", "pop", "soul"], "1970s", ["euphoric", "driving"], []),

    # --- 80s -------------------------------------------------------------
    "Michael Jackson": (["pop", "r&b", "funk"], "1980s", ["euphoric", "driving", "anthemic"], []),
    "Prince": (["funk", "pop", "r&b"], "1980s", ["playful", "defiant", "euphoric"], []),
    "Madonna": (["pop", "synthpop", "disco"], "1980s", ["defiant", "euphoric"], []),
    "U2": (["rock", "alternative"], "1980s", ["anthemic", "cinematic"], []),
    "Journey": (["classic rock", "rock"], "1980s", ["anthemic", "triumphant"], ["arena rock"]),
    "Bon Jovi": (["rock", "classic rock"], "1980s", ["anthemic", "defiant"], ["arena rock"]),
    "Toto": (["rock", "pop"], "1980s", ["warm", "nostalgic"], ["yacht rock"]),
    "a-ha": (["synthpop", "pop"], "1980s", ["wistful", "driving"], []),
    "Tears for Fears": (["synthpop", "pop", "alternative"], "1980s", ["brooding", "anthemic"], []),
    "Depeche Mode": (["synthpop", "electronic", "alternative"], "1980s", ["brooding", "hypnotic"], []),
    "The Cure": (["alternative", "rock", "dream pop"], "1980s", ["melancholic", "dreamy", "brooding"], ["post-punk"]),
    "The Police": (["rock", "reggae", "alternative"], "1980s", ["restless", "driving"], ["new wave"]),
    "Whitney Houston": (["pop", "r&b", "soul"], "1980s", ["triumphant", "tender"], []),
    "Cyndi Lauper": (["pop", "synthpop"], "1980s", ["playful", "tender"], []),
    "Phil Collins": (["pop", "rock"], "1980s", ["brooding", "anthemic"], []),

    # --- 90s -------------------------------------------------------------
    "Nirvana": (["grunge", "alternative", "rock"], "1990s", ["aggressive", "defiant", "brooding"], []),
    "Radiohead": (["alternative", "indie rock", "post-rock"], "1990s", ["brooding", "eerie", "melancholic"], ["art rock"]),
    "Pearl Jam": (["grunge", "rock", "alternative"], "1990s", ["brooding", "driving"], []),
    "Soundgarden": (["grunge", "metal", "alternative"], "1990s", ["aggressive", "brooding"], []),
    "Red Hot Chili Peppers": (["funk", "alternative", "rock"], "1990s", ["driving", "playful"], ["funk rock"]),
    "Oasis": (["rock", "alternative", "indie rock"], "1990s", ["anthemic", "nostalgic", "defiant"], ["britpop"]),
    "Blur": (["alternative", "indie rock", "pop"], "1990s", ["playful", "wistful"], ["britpop"]),
    "Green Day": (["punk", "rock", "alternative"], "1990s", ["defiant", "driving"], ["pop punk"]),
    "The Smashing Pumpkins": (["alternative", "rock", "grunge"], "1990s", ["brooding", "lush"], []),
    "Alanis Morissette": (["alternative", "rock", "singer-songwriter"], "1990s", ["defiant", "restless"], []),
    "Sheryl Crow": (["rock", "americana", "pop"], "1990s", ["warm", "nostalgic"], []),
    "Backstreet Boys": (["pop", "teen pop", "r&b"], "1990s", ["tender", "anthemic"], []),
    "Spice Girls": (["pop", "teen pop"], "1990s", ["playful", "euphoric"], []),
    "TLC": (["r&b", "hip hop", "pop"], "1990s", ["playful", "warm"], []),
    "Mariah Carey": (["pop", "r&b", "soul"], "1990s", ["tender", "euphoric"], []),
    "Celine Dion": (["pop"], "1990s", ["tender", "triumphant", "cinematic"], ["adult contemporary"]),
    "Britney Spears": (["pop", "teen pop", "synthpop"], "2000s", ["playful", "driving"], []),
    "Weezer": (["alternative", "rock", "indie rock"], "1990s", ["playful", "nostalgic"], ["power pop"]),
    "Third Eye Blind": (["alternative", "rock"], "1990s", ["restless", "nostalgic"], []),

    # --- 2000s -----------------------------------------------------------
    "Coldplay": (["alternative", "rock", "pop"], "2000s", ["anthemic", "wistful", "lush"], []),
    "Linkin Park": (["rock", "alternative", "metal"], "2000s", ["aggressive", "brooding", "anthemic"], ["nu metal"]),
    "The Killers": (["indie rock", "alternative", "synthpop"], "2000s", ["anthemic", "driving"], []),
    "Arcade Fire": (["indie rock", "alternative"], "2000s", ["anthemic", "cinematic", "restless"], []),
    "The Strokes": (["indie rock", "alternative", "rock"], "2000s", ["driving", "defiant"], ["garage rock"]),
    "Death Cab for Cutie": (["indie rock", "indie pop", "alternative"], "2000s", ["melancholic", "tender", "wistful"], []),
    "Modest Mouse": (["indie rock", "alternative"], "2000s", ["restless", "eerie"], []),
    "The White Stripes": (["rock", "blues", "punk"], "2000s", ["aggressive", "driving"], ["garage rock"]),
    "My Chemical Romance": (["emo", "punk", "rock"], "2000s", ["anthemic", "defiant", "cinematic"], []),
    "Fall Out Boy": (["emo", "punk", "pop"], "2000s", ["driving", "defiant"], ["pop punk"]),
    "Paramore": (["punk", "rock", "emo"], "2000s", ["defiant", "driving", "anthemic"], ["pop punk"]),
    "Panic! at the Disco": (["emo", "pop", "punk"], "2000s", ["playful", "anthemic"], []),
    "Maroon 5": (["pop", "funk", "r&b"], "2000s", ["playful", "warm"], []),
    "John Mayer": (["singer-songwriter", "blues", "pop"], "2000s", ["warm", "wistful", "tender"], []),
    "Norah Jones": (["jazz", "singer-songwriter", "folk"], "2000s", ["warm", "sparse", "tender"], []),
    "Amy Winehouse": (["soul", "jazz", "r&b"], "2000s", ["melancholic", "defiant", "warm"], ["neo soul"]),
    "Kanye West": (["hip hop", "rap", "soul"], "2000s", ["defiant", "triumphant", "brooding"], []),
    "Outkast": (["hip hop", "funk", "rap"], "2000s", ["playful", "euphoric"], []),
    "Eminem": (["rap", "hip hop"], "2000s", ["aggressive", "defiant", "restless"], []),
    "Gorillaz": (["alternative", "hip hop", "electronic"], "2000s", ["hypnotic", "eerie", "playful"], []),
    "Daft Punk": (["electronic", "house", "disco"], "2000s", ["euphoric", "hypnotic", "driving"], ["french house"]),

    # --- 2010s -----------------------------------------------------------
    "Adele": (["pop", "soul", "r&b"], "2010s", ["melancholic", "tender", "triumphant"], []),
    "Taylor Swift": (["pop", "country", "indie pop"], "2010s", ["wistful", "nostalgic", "tender"], []),
    "Ed Sheeran": (["pop", "folk", "singer-songwriter"], "2010s", ["tender", "warm"], []),
    "Bruno Mars": (["pop", "funk", "r&b"], "2010s", ["euphoric", "playful", "warm"], []),
    "Lorde": (["indie pop", "pop", "electronic"], "2010s", ["brooding", "sparse", "defiant"], ["art pop"]),
    "Lana Del Rey": (["dream pop", "indie pop", "pop"], "2010s", ["melancholic", "nostalgic", "cinematic"], ["baroque pop"]),
    "Billie Eilish": (["pop", "electronic", "indie pop"], "2010s", ["eerie", "sparse", "brooding"], ["dark pop"]),
    "The Weeknd": (["r&b", "pop", "synthpop"], "2010s", ["brooding", "hypnotic", "nostalgic"], []),
    "Frank Ocean": (["r&b", "soul", "hip hop"], "2010s", ["tender", "wistful", "sparse"], []),
    "Tame Impala": (["psychedelic", "indie rock", "electronic"], "2010s", ["hypnotic", "dreamy", "lush"], []),
    "Vampire Weekend": (["indie rock", "indie pop", "afrobeat"], "2010s", ["playful", "warm"], []),
    "Bon Iver": (["folk", "indie pop", "electronic"], "2010s", ["melancholic", "sparse", "wistful"], []),
    "Fleet Foxes": (["folk", "indie pop"], "2010s", ["lush", "nostalgic", "warm"], ["baroque pop"]),
    "The National": (["indie rock", "alternative"], "2010s", ["brooding", "melancholic", "restless"], []),
    "Arctic Monkeys": (["indie rock", "alternative", "rock"], "2010s", ["driving", "defiant", "brooding"], []),
    "Florence + the Machine": (["indie pop", "alternative", "rock"], "2010s", ["anthemic", "cinematic", "lush"], []),
    "Sufjan Stevens": (["folk", "indie pop", "singer-songwriter"], "2000s", ["tender", "sparse", "melancholic"], []),
    "Beyoncé": (["r&b", "pop", "soul"], "2010s", ["triumphant", "defiant", "driving"], []),
    "Rihanna": (["pop", "r&b", "edm"], "2010s", ["defiant", "driving"], []),
    "Sia": (["pop", "electronic"], "2010s", ["anthemic", "melancholic"], []),
    "Imagine Dragons": (["rock", "pop", "alternative"], "2010s", ["anthemic", "driving"], []),
    "Twenty One Pilots": (["alternative", "hip hop", "pop"], "2010s", ["restless", "defiant", "anthemic"], []),
    "Hozier": (["folk", "blues", "soul"], "2010s", ["brooding", "warm", "tender"], []),
    "Sam Smith": (["pop", "soul", "r&b"], "2010s", ["melancholic", "tender"], []),
    "Halsey": (["pop", "indie pop", "electronic"], "2010s", ["defiant", "brooding"], []),
    "Post Malone": (["hip hop", "pop", "rap"], "2010s", ["melancholic", "hypnotic"], []),
    "Kendrick Lamar": (["hip hop", "rap", "jazz"], "2010s", ["defiant", "restless", "brooding"], []),
    "Childish Gambino": (["hip hop", "r&b", "funk"], "2010s", ["playful", "defiant"], []),
    "Daniel Caesar": (["r&b", "soul", "gospel"], "2010s", ["tender", "warm", "sparse"], []),
    "Mac DeMarco": (["indie rock", "lo-fi", "dream pop"], "2010s", ["dreamy", "playful", "warm"], []),
    "Beach House": (["dream pop", "indie pop", "ambient"], "2010s", ["dreamy", "hypnotic", "lush"], []),
    "Big Thief": (["folk", "indie rock", "singer-songwriter"], "2010s", ["tender", "sparse", "wistful"], []),
    "Phoebe Bridgers": (["indie rock", "folk", "singer-songwriter"], "2010s", ["melancholic", "sparse", "eerie"], []),
    "Sufjan": (["folk", "indie pop"], "2010s", ["tender", "sparse"], []),
    "Khalid": (["r&b", "pop"], "2010s", ["warm", "wistful"], []),
    "SZA": (["r&b", "soul", "hip hop"], "2010s", ["tender", "restless"], []),

    # --- 2020s -----------------------------------------------------------
    "Olivia Rodrigo": (["pop", "punk", "indie pop"], "2020s", ["defiant", "melancholic", "restless"], ["pop punk"]),
    "Harry Styles": (["pop", "rock", "indie pop"], "2020s", ["warm", "nostalgic", "playful"], []),
    "Dua Lipa": (["pop", "disco", "electronic"], "2020s", ["euphoric", "driving"], ["nu-disco"]),
    "Doja Cat": (["pop", "hip hop", "r&b"], "2020s", ["playful", "driving"], []),
    "Clairo": (["indie pop", "lo-fi", "dream pop"], "2020s", ["dreamy", "tender", "sparse"], ["bedroom pop"]),
    "Wallows": (["indie rock", "indie pop", "alternative"], "2020s", ["restless", "nostalgic"], []),
    "boygenius": (["indie rock", "folk", "alternative"], "2020s", ["melancholic", "tender", "defiant"], []),
    "Mitski": (["indie rock", "indie pop", "alternative"], "2010s", ["melancholic", "defiant", "sparse"], []),
    "Laufey": (["jazz", "bossa nova", "pop"], "2020s", ["tender", "warm", "wistful"], []),
    "Chappell Roan": (["pop", "synthpop", "indie pop"], "2020s", ["euphoric", "playful", "defiant"], []),

    # --- video game / anime / film (heavily represented on Hooktheory) ----
    "Koji Kondo": (["video game", "classical"], "1980s", ["playful", "triumphant", "nostalgic"], ["chiptune"]),
    "Nobuo Uematsu": (["video game", "classical", "film score"], "1990s", ["cinematic", "triumphant", "melancholic"], []),
    "Toby Fox": (["video game", "electronic", "lo-fi"], "2010s", ["playful", "eerie", "tender"], ["chiptune"]),
    "Yoko Shimomura": (["video game", "classical", "film score"], "2000s", ["cinematic", "wistful"], []),
    "Joe Hisaishi": (["film score", "classical"], "1990s", ["tender", "cinematic", "nostalgic"], []),
    "Hans Zimmer": (["film score", "classical", "electronic"], "2000s", ["cinematic", "triumphant", "brooding"], []),
    "John Williams": (["film score", "classical"], "1980s", ["triumphant", "cinematic", "anthemic"], []),
    "Studio Ghibli": (["film score", "classical", "anime"], "1990s", ["tender", "nostalgic", "lush"], []),
    "RADWIMPS": (["j-pop", "rock", "anime"], "2010s", ["anthemic", "restless", "tender"], []),
    "Yoasobi": (["j-pop", "anime", "electronic"], "2020s", ["driving", "euphoric"], []),
    "Kenshi Yonezu": (["j-pop", "anime", "pop"], "2010s", ["restless", "cinematic"], []),
    "BTS": (["k-pop", "pop", "hip hop"], "2010s", ["anthemic", "euphoric", "driving"], []),
    "BLACKPINK": (["k-pop", "pop", "edm"], "2010s", ["defiant", "driving"], []),
    "TWICE": (["k-pop", "pop", "synthpop"], "2010s", ["playful", "euphoric"], []),
    "NewJeans": (["k-pop", "pop", "r&b"], "2020s", ["dreamy", "playful"], []),

    # --- jazz / standards / classical ------------------------------------
    "Bill Evans": (["jazz"], "pre-1970", ["tender", "sparse", "wistful"], ["modal jazz"]),
    "Miles Davis": (["jazz"], "pre-1970", ["sparse", "brooding", "hypnotic"], ["modal jazz"]),
    "John Coltrane": (["jazz"], "pre-1970", ["restless", "triumphant"], []),
    "Antonio Carlos Jobim": (["bossa nova", "jazz", "latin"], "pre-1970", ["warm", "wistful", "tender"], []),
    "Frank Sinatra": (["swing", "jazz", "pop"], "pre-1970", ["warm", "nostalgic"], ["traditional pop"]),
    "Nat King Cole": (["jazz", "swing", "soul"], "pre-1970", ["warm", "tender"], []),
    "Duke Ellington": (["jazz", "swing"], "pre-1970", ["playful", "lush"], []),
    "Johann Sebastian Bach": (["classical"], "pre-1970", ["triumphant", "hypnotic", "lush"], ["baroque"]),
    "Frédéric Chopin": (["classical"], "pre-1970", ["melancholic", "tender", "lush"], ["romantic"]),
    "Claude Debussy": (["classical"], "pre-1970", ["dreamy", "lush", "eerie"], ["impressionist"]),
    "Erik Satie": (["classical", "ambient"], "pre-1970", ["sparse", "melancholic", "dreamy"], []),
    "Ludwig van Beethoven": (["classical"], "pre-1970", ["triumphant", "brooding", "anthemic"], []),

    # --- country / folk / americana --------------------------------------
    "Johnny Cash": (["country", "americana", "folk"], "pre-1970", ["brooding", "defiant"], []),
    "Dolly Parton": (["country", "folk", "pop"], "1970s", ["warm", "tender"], []),
    "Chris Stapleton": (["country", "blues", "americana"], "2010s", ["brooding", "warm"], []),
    "Kacey Musgraves": (["country", "pop", "americana"], "2010s", ["dreamy", "warm", "wistful"], []),
    "Zach Bryan": (["country", "americana", "folk"], "2020s", ["wistful", "sparse"], []),
    "Mumford & Sons": (["folk", "indie rock", "americana"], "2010s", ["anthemic", "driving"], []),
    "The Lumineers": (["folk", "indie pop", "americana"], "2010s", ["nostalgic", "warm"], []),
    "Joni Mitchell": (["folk", "singer-songwriter", "jazz"], "1970s", ["wistful", "tender", "sparse"], []),
    "Neil Young": (["folk", "classic rock", "americana"], "1970s", ["melancholic", "defiant"], []),
    "Leonard Cohen": (["folk", "singer-songwriter"], "1970s", ["brooding", "sparse", "tender"], []),

    # --- electronic ------------------------------------------------------
    "Avicii": (["edm", "house", "electronic"], "2010s", ["euphoric", "anthemic"], ["progressive house"]),
    "Calvin Harris": (["edm", "house", "pop"], "2010s", ["euphoric", "driving"], []),
    "Deadmau5": (["house", "techno", "electronic"], "2010s", ["hypnotic", "driving"], ["progressive house"]),
    "Aphex Twin": (["electronic", "ambient", "techno"], "1990s", ["eerie", "hypnotic"], ["idm"]),
    "Boards of Canada": (["ambient", "electronic", "lo-fi"], "1990s", ["nostalgic", "eerie", "hypnotic"], ["idm"]),
    "Burial": (["electronic", "ambient", "drum and bass"], "2000s", ["eerie", "melancholic", "hypnotic"], ["dubstep"]),
    "ODESZA": (["electronic", "edm", "ambient"], "2010s", ["euphoric", "lush", "cinematic"], []),
    "Flume": (["electronic", "edm"], "2010s", ["hypnotic", "lush"], ["future bass"]),

    # --- reggae / latin / world ------------------------------------------
    "Bob Marley": (["reggae"], "1970s", ["warm", "triumphant", "hypnotic"], []),
    "Buena Vista Social Club": (["latin", "world", "jazz"], "1990s", ["warm", "nostalgic"], ["son cubano"]),
    "Bad Bunny": (["latin", "hip hop", "pop"], "2020s", ["driving", "playful"], ["reggaeton"]),
    "Fela Kuti": (["afrobeat", "funk", "world"], "1970s", ["hypnotic", "defiant", "driving"], []),
}


def main() -> None:
    artists = [
        {
            "artist": name,
            "genres": genres,
            "subgenres": subgenres,
            "era": era,
            "moods": moods,
            "confidence": 0.9,
            "unknown": False,
        }
        for name, (genres, era, moods, subgenres) in sorted(TABLE.items())
    ]
    payload = {
        "schema_version": 1,
        "taxonomy_version": "v1",
        "source": "curated",
        "artists": artists,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(artists)} artists -> {OUT}")


if __name__ == "__main__":
    main()
