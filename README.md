# music-ai-backstreet-bois

**ChordCat Connect** — turn chords played on an [AlphaTheta ChordCat](https://alphatheta.com/en/product/production/chordcat/gray/)
into a musical identity, and use that identity to connect like-minded musicians in real life.

    Web MIDI (browser)  ->  FastAPI  ->  chord segmentation + identification
                                     ->  key/mode detection
                                     ->  Roman numerals -> Hooktheory `cp` tokens
                                     ->  windowed Hooktheory TheoryTab search
                                     ->  Claude genre/taste profiling
                                     ->  fused-vector matching against a musician pool

## Layout

| Path | What |
|---|---|
| `api/src/chordcat/domain/` | Pure music-theory core. No clock, no network, no RNG. 100% unit tested. |
| `api/src/chordcat/adapters/` | I/O behind `typing.Protocol`: Hooktheory HTTP, rate limiter, cache, Claude. |
| `api/src/chordcat/services/` | Orchestration. The only place that awaits. |
| `scripts/` | One-off probes and generators (see below). |
| `web/` | Next.js frontend; reads the ChordCat over the Web MIDI API. |

## Setup

```bash
cp .env.example .env     # fill in HOOKTHEORY_* and ANTHROPIC_API_KEY
cd api && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
```

`sentence-transformers` is optional (`pip install -e '.[dev,embeddings]'`); without it the
matcher degrades to music-native features only and logs a warning.

## Run

```bash
cd api && uvicorn chordcat.main:app --reload     # http://localhost:8000
cd web && npm run dev                            # http://localhost:3000
```

Two pages: `/` matches you to musicians, `/helper` explains what to try next.

Open the frontend in **Chrome, Edge, or Firefox 108+**. Safari does not implement the
Web MIDI API on any platform and has no roadmap to.

## Song sources

Two, because one is not enough.

| Source | What it is | Why |
|---|---|---|
| **Trends API** | `api.hooktheory.com/v1` — the sanctioned API, `cp` tokens | Chord-transition probabilities, and song matches |
| **TheoryTab search** | the public advanced-search page, roman numerals | The Trends song index is a stale snapshot |

The second source exists because of a concrete gap. Arctic Monkeys' "505" is in
TheoryTab as D Dorian `i ii i ii`; the correct Trends token for that progression
is `2,3` (verified — other D-dorian i–ii songs are there); and an exhaustive
scan of `2,3`, all 17 pages and 338 songs, does not contain it. The Trends index
advertises "75,000+" songs while TheoryTab search reports 79,896, returns
`http://` URLs, and its docs leak a `local.www.` dev host. It is old.

**TheoryTab search is not an API.** It parses the server-rendered search page —
there is no JSON endpoint behind it. So:

- every field is optional and a parse failure degrades to "no results", never an
  exception into someone's analysis
- requests are serialised, spaced over a second apart, and aggressively cached
- `robots.txt` allows the path (`User-agent: *` / `Allow: /`) and signals
  `use=reference`, which is what this is
- it can be disabled on its own with `THEORYTAB_ENABLED=0`

It also queries in **roman numerals rather than `cp` tokens**, which suits a
chord-voicing device: with `ignoreModifiers` on, `i ii` matches a song whose
chords are really i11 and ii9 — exactly what the ChordCat sends. And Hooktheory's
own genre labels come free with each result, which beats guessing at them.

## Scripts (run in this order on a fresh install)

```bash
python scripts/probe_hooktheory.py    # credential smoke test
python scripts/probe_cp_tokens.py     # builds api/src/chordcat/data/cp_table.json
python scripts/warm_nodes_tree.py     # BFS the global chord-transition tree into the cache
python scripts/generate_pool.py       # regenerate the synthetic musician pool (rarely needed)
```

The Hooktheory API allows **10 requests / 10 seconds against the whole account**, so
`warm_nodes_tree.py` takes hours. It only has to run once, ever: the tree is global and
static, and warming it makes progression-rarity scoring and dead-path pruning free.
