# PROGRESS

## 2026-09-12 — the helper actually speaks now

**Why it felt dumb.** The LLM had never run. No `.env`, so `has_anthropic` was False and
every turn fell through to `TemplateVoice`. The whole hardware test was a system with zero
AI in it, reading engineer-written placeholder prose.

**Done** (branch rebased onto `origin/vishnu`, 238 tests, new code ruff-clean)
- **Rebase.** Inherited the three-step flow, indigo theme, cats and Atkinson Hyperlegible.
  The helper page needed no colour of its own — it was already on shared tokens.
- **A voice.** `OpenAICompatibleVoice` over httpx (already a dependency). Groq, Together,
  OpenRouter and local Ollama are one wire format, so provider is config not code.
  `build_voice()` prefers the open endpoint, then Anthropic, then the template.
- **Memory.** Own sqlite tables, keyed by `session_id`. Survives a refresh, so it stops
  repeating itself.
- **`change.*` facts.** `diff_facts()` compares this take to the last one. Measured, not
  guessed, so the validator governs them like any other fact. 20% relative tolerance —
  a fifth is a change, smaller is take-to-take noise.
- **Song context.** `HelperTurnRequest.songs` — passed in, never fetched, so a turn still
  spends no Hooktheory quota.
- **Conversation UI.** Turn list, text box, MIDI port picker, "Just show me" → counted
  override.

**Run it**
```
cd api && PYTHONPATH=src .venv/bin/uvicorn chordcat.main:app --reload --reload-dir src
cd web && npm run dev
```
`PYTHONPATH=src` matters: this venv's editable-install `.pth` goes stale repeatedly and
uvicorn then cannot import chordcat. pytest is now immune (`pythonpath = ["src","tests"]`).

**Still blocked on you / the team**
- **No LLM key.** Set `LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY` in `.env` (see
  `.env.example`). Ollama is installed and running on this machine with no models pulled —
  `ollama pull qwen2.5:7b` would work with no key at all.
- **No Hooktheory credentials**, so there are no song matches to pass as context.
- **21 nodes still `status: draft`.** A real model phrasing placeholder text reads better
  but still is not right. Tutor is the blocker.
- **Malcolm's sing→harmonise modules** (`pitch.js`, `harmonize.js`) are the Phase 5 plan.
  `main` deleted all nine of his files — confirm with him before reviving.

**Open, deliberately untuned:** five frontier nodes still tie; tie-break is alphabetical.
Needs the tutor's 10 rows, not a guess fitted to one.

---

## 2026-09-12 — one-button hardware test

**How to run it** (two terminals, then open http://localhost:3000/helper)
```
cd api && .venv/bin/uvicorn chordcat.main:app --reload
cd web && npm run dev
```
Chrome/Edge/Firefox only — Safari has no Web MIDI. One button: *Listen to me play* ->
play -> *Stop and ask*. "use a recorded take" runs the bundled capture with no hardware.
"Save this take as a test fixture" downloads a capture in the fixture format — that is how
the two missing takes (repetitive, adventurous) get made.

**Added**
- `POST /api/helper/turn` — take in, turn out. No Hooktheory I/O, so no shared quota.
- `GET /api/helper/demo` — the bundled capture, so the helper demos without hardware.
- `web/app/helper/page.tsx` — its own route. Vishnu's page is untouched; the only shared
  files edited are `lib/api.ts` (appended) and `globals.css` (appended).
- Intent tags wired end to end; `suggested_nodes` carried client-side so it does not repeat.
- Provenance panel: the why-path, the score tie, and every fact with its n.

**Note:** the venv's editable install went stale mid-session and `import chordcat` started
failing even though the .pth was correct. `rm -rf api/.venv && python3 -m venv .venv &&
.venv/bin/pip install -e '.[dev]'` fixed it. Worth knowing if it recurs.

---

## 2026-09-12 — v0 built and green

**Done** — all 13 plan tasks. `api/src/chordcat/helper/`, 54 new tests (199 total, ruff clean).
`python -m chordcat.helper.cli analyse <capture.json>` prints a validated turn from the
real ChordCat take. `tutor-todo` lists the 21 nodes awaiting prose.

**Three defects the real capture exposed** (all fixed, see commits)
1. Map root keyed on triad qualities — the take is 19 sevenths and zero triads, so the
   root never lit and everything behind it was stranded.
2. The evidence threshold was discarding individual chord facts (n=1 each). Facts now
   split into patterns (thresholded) and direct observations (self-supporting).
3. Draft prose for performance nodes was written in the "you are doing this" voice, which
   contradicts "one thing you have not tried". Rule now in the YAML header.

**Refinement done:** detectors declare which fact kinds they read, so the ranker can tell a
*measured* absence (`voicing.inversions` = 0 of 19) from an *unmeasured* one (no
`harmony.cadence` fact at all). Suggesting the latter asserts an absence the truth layer
never established. `authentic_cadence` correctly stopped winning.

**Open — deliberately not tuned.** Five frontier nodes now tie at 12.0 and the tie-break is
alphabetical, so the take picks `dynamic_range` where the tutor says `inversions`. Fitting
the ranker to n=1 would be overfitting. Instead `Choice.tied_with` is surfaced and
`eval_helper.py` splits disagreements into *ranking problem* (right answer was in the tie)
vs *map problem* (never on the frontier). Resolve with the tutor's 10 rows.

**Blocked on people, not code:** tutor prose for 21 nodes; `on_device` strings from the
ChordCat manual; 2 more captures (one repetitive, one adventurous) — needs hardware.

---

## 2026-09-12 — branch `omar` forked, v0 plan written

**Done**
- Forked `omar` from `origin/vishnu` @ `9e2f917` (he pushed 3 more commits mid-fetch;
  the main checkout is still on the older `4038446`). Not pushed yet.
- Wrote `docs/superpowers/plans/2026-09-12-ai-helper-v0.md` — 13 TDD tasks covering
  brief §11's whole v0, finishing at a CLI that prints one validated turn from the
  real ChordCat capture.

**Decisions taken, three of them against the brief** (detail in the plan's Decisions section)
1. Fixtures already exist and are JSON, not `.mid`:
   `api/tests/fixtures/midi/chordcat-8track-sequencer.json` is a real 54s capture,
   8 channels interleaved, harmony on channel 2. No `mido`/`rtmidi` in the repo —
   MIDI is read in the browser. Brief §11 step 1 is done.
2. L2 adapts `chordcat.domain` instead of recomputing theory. It adds only
   `n_observations` + `evidence`, which his types lack.
3. `music21` dropped — would duplicate a tested core.
4. Helper lives at `api/src/chordcat/helper/`.
5. Tutor prose is NOT written by us (brief §4 forbids it). Nodes carry
   `status: draft` and `on_device: TUTOR_TODO`; `cli.py tutor-todo` prints the worklist.

**Next**
- Execute the plan task by task. Task 1 is the package skeleton + `FixtureSource`.
- Chase the tutor for node prose and the ChordCat manual for `on_device` — that is
  the long-lead item, not the code.

---

## 2026-09-12 — branch base set to vishnu

**Done**
- Rebased worktree branch `claude/team-integration-setup-3e105e` off `main` (empty, README-only)
  onto `origin/vishnu` @ `9e2f917`. Branch had no commits of its own, so this was a clean
  `git reset --hard`. Nothing lost.
- Read `~/Downloads/AI_HELPER_BRIEF.md` (Omar's component: the conversational AI helper).
- Surveyed the inherited codebase for integration seams.

**State**
- Base: `origin/vishnu` — FastAPI `api/` (hexagonal: `domain/` pure theory, `adapters/` I/O,
  `services/` orchestration) + Next.js `web/` reading the ChordCat over Web MIDI.
- `origin/zoha` @ `7a64860` forked off `076e48a` (an ancestor of vishnu's tip) and adds an
  audio-embedding matching prototype. Will need a merge eventually; not our problem yet.

**Open decisions before any helper code lands** — see chat readout for detail
1. MIDI source: brief §9.1/§14 assume `mido`/`python-rtmidi` + `.mid` fixtures. Reality is
   browser Web MIDI -> `RawEvent` JSON over HTTP. No mido/rtmidi anywhere in the repo.
   Fixtures probably want to be recorded `RawEvent` streams, not `.mid`.
2. Facts layer (brief §8): most v0 fact kinds are already computed deterministically in
   `api/src/chordcat/domain/` (key.py, chords.py, segment.py, events.py). Brief §1 says
   consume the mobile dev's analysis rather than rebuild it — so L2 should be an adapter
   mapping his types to `Fact{id,kind,value,confidence,evidence,n_observations}`.
3. `music21` (brief §14) would duplicate the hand-written, unit-tested theory core. Probably drop.
4. Where the helper package lives: `api/src/chordcat/helper/` vs a sibling package.

**Next**
- Settle 1-4 with the team, then brief §11 v0 build order starting from fixtures.
