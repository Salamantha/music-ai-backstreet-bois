# ChordCat Connect

Turn chords played on an [AlphaTheta ChordCat](https://alphatheta.com/en/product/production/chordcat/gray/)
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

Open the frontend in **Chrome, Edge, or Firefox 108+**. Safari does not implement the
Web MIDI API on any platform and has no roadmap to.

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
