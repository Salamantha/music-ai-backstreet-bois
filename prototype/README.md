# Chordprint — user-to-user music taste matching

Two ways in, one similarity engine:

- **Type chord progressions** → `pandas` / `numpy` / `scikit-learn`, no
  neural network, nothing to download.
- **Upload a whole song** → a *pretrained* audio embedding model (CLAP)
  turns it into one vector. Nothing is trained from scratch. See **Part II**.

## Running it

**Double-click `run_ui.bat`** for the interactive test bench
(http://localhost:8765), or **`run_demo.bat`** for the printed walkthrough.
A self-contained `.venv/` with numpy, pandas and scikit-learn already lives in
this folder — nothing to install.

### The test bench

`server.py` is stdlib-only (no Flask) and serves `ui.html`. Click Roman
numerals to build a progression, set a tempo, hit **Find my people**. You get
your five closest matches with the reason, your harmonic profile, the
progressions you share ranked by how rare they are, and a PCA taste map with
you plotted on it.

**The browser does no matching.** `chordprint.js` is used only to turn MIDI
notes into Roman numerals; every score, cluster and PCA coordinate comes from
`features.py` / `recommend.py` — the same code `demo.py` runs. One algorithm,
not two.

**Connect MIDI / ChordCat** works in Chrome or Edge: plug the device in, click
the button, play a chord and it lands in the progression strip.

From a terminal, from inside this folder:

```powershell
.\.venv\Scripts\python.exe demo.py
```

### If you type `python` or `pip` and get "The file cannot be accessed by the system"

That is **not** a broken install. Windows ships placeholder `python.exe` and
`pip.exe` stubs that open the Microsoft Store instead of running anything, and
they sit earlier on your PATH than any real Python. Two rules avoid it:

- always call the interpreter by path — `.\.venv\Scripts\python.exe`
- `cd` into this folder first, or `requirements.txt` and `demo.py` aren't there
  to be found

To install anything new, use the venv's own pip:

```powershell
.\.venv\Scripts\python.exe -m pip install <package>
```

### Rebuilding the venv from scratch

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> `.venv/` is ~250 MB and this folder is inside OneDrive, so it will sync to
> the cloud. It's in `.gitignore`, but if OneDrive gets slow, right-click the
> folder → "Always keep on this device" off, or move the project off Desktop.

```
A. CHORDS   roman numerals ──> features.py ─┐
B. AUDIO    song.mp3 ──> audio.py                            │
                     ──> embedders.py ──> store.py ──────────┴──> recommend.py
                                                                  cosine · KNN
                                                                  K-Means · PCA
providers.py   external metadata. swappable. nothing imports it directly.
features.py    user input + metadata -> one numeric matrix
audio.py       decode, mono, resample, overlapping windows
embedders.py   pretrained model -> per-window vectors -> pooled song vector
store.py       vector database (catalog.json + vectors.npz), user embeddings
recommend.py   cosine / KNN / K-Means / PCA — shared by BOTH pipelines
server.py      stdlib HTTP API
ui.html        two tabs: chord bench + audio upload
demo.py        30 synthetic users, chord pipeline end to end
```

`recommend.py` takes a matrix `X` and does not care whether a column came
from a Roman numeral or a neural network. That is why adding audio needed no
changes to it at all.

---

## The finding that shaped the design

**The Hooktheory Trends API is not a song corpus. It is a Markov model.**

Two endpoints only:

| Endpoint | Returns |
|---|---|
| `GET trends/nodes?cp=4,1` | probability of each possible *next* chord |
| `GET trends/songs?cp=4,1` | artist / song / section / url — **no genre, no BPM, no key** |

- Auth: bearer token from `POST users/auth` with your hooktheory.com login
- **Rate limit: 10 requests / 10 seconds**
- They state plainly that no full TheoryTab dump is available

This is good news. We wanted a rarity weight for progressions, and normally
you get that by counting a corpus. Hooktheory hands you the probabilities
directly, so there is no corpus to download, join, or clean:

```
P(I → V → vi) = P(I) · P(V|I) · P(vi|I,V)
surprisal     = −log₂ P        ← "bits of surprise"
```

One request per chord, cached on disk forever. A 4-chord progression costs 4
requests once and zero thereafter.

Everything Hooktheory *doesn't* have — genre, BPM, key, mood — comes from
other providers. That split is why the provider layer exists.

---

## 1. What you collect directly from the user

No API needed. This is `features.UserInput`:

| Field | Source | Why it matters |
|---|---|---|
| `progressions` | ChordCat / MIDI | the core signal — what their hands actually do |
| `genres`, `artists` | onboarding | solves cold start before they play a note |
| `songs` | onboarding | the join key for enrichment |
| `tempo_pref` | measured or asked | strong, cheap separator |
| `velocity_mean`, `voicing_density` | free from the same MIDI stream | **not derivable from chords** — this is your answer to "it's only chord progressions" |

Four more are derived from the numerals with no API at all:
`extension_rate`, `chromaticism`, `minor_ratio`, `repertoire`.

## 2. What you enrich externally

`genre` · `subgenre` · `tempo` · `key` · `mode` · `mood/energy/valence` ·
`artist tags` · `harmonic complexity`

Everything except harmonic complexity, which we compute ourselves from
Hooktheory surprisal.

## 3. Sources — downloads preferred over scraping

**Use these (bulk downloads, no scraping):**

| Source | Gives you | Notes |
|---|---|---|
| **AcousticBrainz dumps** | BPM, key, scale, mood/genre classifier outputs | best single source for audio features. Submissions closed 2022, **dumps still downloadable** |
| **MTG-Jamendo** | 55k CC tracks, 87 genre tags + mood/theme tags | research dataset, clean labels |
| **FMA** | 106k tracks, 161 hierarchical genres, precomputed features | good genre hierarchy |
| **MusicBrainz** | genres, folksonomy tags, stable IDs | CC0, no key needed, ~1 req/s, requires User-Agent |
| **"Chord progressions of 5000 songs"** | progressions in bulk | linked from Hooktheory's own docs — download instead of hammering the API |

**APIs, for live lookup:**

| API | Gives you | Notes |
|---|---|---|
| **Hooktheory Trends** | next-chord probabilities, songs using a progression | 10 req/10s, account required |
| **Last.fm** | folksonomy tags (mood + genre) | free key |
| **Deezer** | basic metadata, BPM on the track object | no auth for search — *verify the BPM field before depending on it* |

**Avoid:** Spotify audio-features / audio-analysis — restricted for new
applications since Nov 2024. Do not architect around it.

## 4. Combining into a DataFrame

`features.build_dataframe(users, registry)` → one row per user, still
human-readable so you can eyeball whether enrichment worked. Merge rule:
providers are asked in order, first non-`None` scalar wins, list fields
(genres, tags) are unioned.

## 5–7. Encoding

| Field | Encoding | Reason |
|---|---|---|
| progressions | n-gram counts × surprisal | order matters; `IV→I` ≠ `I→IV` |
| genres, artists | `MultiLabelBinarizer` (multi-hot) | a user has many, not one |
| tempo | **fold to one octave, then log₂** | 140 ≈ 70 at half time; tempo is perceived multiplicatively |
| key | **circle of fifths → sin/cos** | key is circular; C–G are neighbours, C–C♯ are not |
| mode | binary minor flag | |
| energy, valence | z-score | |
| harmonic complexity | mean surprisal per chord | |

**Missing values are median-imputed, never zero-filled.** After z-scoring,
zero is the *mean* — a confident claim about someone you know nothing about.

### The step almost everyone skips

49 progression columns, 9 genre columns, 10 numeric columns. Raw cosine over
that is ~60% progression *by accident of column count*. So each block is
L2-normalised **separately**, then multiplied by an explicit weight:

```python
DEFAULT_WEIGHTS = {"progression": .40, "genre": .25, "artist": .10,
                   "numeric": .20, "key": .05}
```

Now the weights mean what they say, and tuning them is a one-line experiment.

## 8. Similarity

`cos(a,b) = a·b / (‖a‖‖b‖)` — ignores magnitude, so a user who listed 30
genres and one who listed 3 can still be close. Euclidean would push the long
vector away from everyone purely for being long.

`similarity_matrix()` is O(n²) and fine for a demo; `knn_model()` uses
`NearestNeighbors(metric="cosine")` for when you have real users. **Both
return identical results** — verified in `demo.py`.

## 9. K-Means

K-Means minimises squared Euclidean distance. For unit vectors:

```
‖a−b‖² = ‖a‖² + ‖b‖² − 2a·b = 2 − 2·cos(a,b)
```

So on the unit sphere, Euclidean distance is a monotone function of cosine
distance and K-Means optimises exactly the metric you match on. This is
**spherical K-Means** — `choose_k()` normalises first. Skip that and your
clustering means something different from your similarity.

`k` is chosen by silhouette: `s(i) = (b−a)/max(a,b)`, where `a` is mean
distance to your own cluster and `b` to the nearest other one.

Clusters are named by **lift**, not frequency — `pop` is everywhere and names
nothing; the over-represented genre is the one that identifies a group.

## 10. Is PCA worth it?

**Yes, for three specific reasons:**
1. 85 mostly-sparse columns over 30 users — in high dimensions everything is
   roughly equidistant (curse of dimensionality) and K-Means degrades badly.
2. PC1/PC2 **is** your taste map. That's the demo visual, for free.
3. n-gram columns are correlated (`ii7>V7` and `V7>IM7` co-occur). PCA merges
   correlated columns into one axis instead of double-counting them.

Measured here: 9 components hold 90% of the variance, and K-Means on those 9
scores **0.824** silhouette vs **0.696** on all 85.

**No, when you need to explain a match.** PC3 has no name. "You both play
♭VII–IV–I" does. So: **match in the raw space, visualise with PCA.**

Two practical limits: `n_components ≤ min(n_samples, n_features)` — with 30
users you cannot keep 50 components no matter how many columns you have. And
PCA centers the data, destroying sparsity: at real scale use `TruncatedSVD`
instead, same idea without centering.

## 11–12. The synthetic example

30 users, 6 archetypes × 5. Actual measured output:

```
archetype vs cluster
cluster    0  1  2  3  4  5  6
ambient    0  0  5  0  0  0  0
citypop    0  5  0  0  0  0  0
house      0  0  0  2  0  0  3
neo-soul   5  0  0  0  0  0  0
punk       0  0  0  0  2  3  0
trap       0  0  0  5  0  0  0
```

Four of six archetypes recovered exactly. Two things went "wrong", and both
are worth understanding rather than fixing:

- **`house_2` landed with trap.** Both archetypes genuinely contain
  `i–♭VII–♭VI–♭VII`. The algorithm is right and the genre labels are wrong —
  which is the whole argument for matching on harmony instead of genre.
- **Punk split across two clusters, and silhouette chose k=7 for 6 groups.**
  Silhouette rewards tight clusters and will over-segment. If you want
  exactly-k, use the elbow method or cap the range.

Cold start works: a new user who plays four chords and declares nothing
matches `neo-soul_2` at 0.547.

## 13. Swapping providers later

`Registry` is the only seam. `features.py` and `recommend.py` import nothing
from `providers.py` except through it.

```python
registry = default_registry(online=False)                 # demo
registry = Registry([Hooktheory(), MusicBrainz(), Offline()])   # live
registry = Registry([LocalParquet("acousticbrainz.parquet"), Offline()])
```

Add a provider by implementing one or both methods — `track_facts()` and
`progression_logprob()`. Nothing downstream changes.

## 14. Why no deep learning

30 users. An embedding model would have more parameters than you have data
points, and it could not tell you *why* two people match — which is the
product. Revisit only with 10k+ users and real interaction feedback; then a
two-tower retrieval model earns its place.

---

## Credentials

Never in the repo:

```bash
export CHORDPRINT_HT_USER="your_hooktheory_username"
export CHORDPRINT_HT_PASS="your_password"
```

Every API response is cached to `.cache/` — add it to `.gitignore`. With a
10-requests-per-10-seconds limit, the cache is not an optimisation, it is the
difference between a working demo and a throttled one.

---

# Part II — Audio embeddings

Upload a full song instead of typing chords. Same similarity layer, same
clustering, same PCA — a different way of producing the vector.

```
song.mp3
  ↓  audio.py          decode → mono → resample → 10 s windows, 50% overlap
  ↓  embedders.py      pretrained model → one vector per window
  ↓  mean pooling      → ONE fixed-length song vector
  ↓  store.py          vectors.npz + catalog.json
  ↓  mean over songs   → user embedding
  ↓  recommend.py      cosine / KNN / K-Means / PCA
```

## Which pretrained model, and why

**CLAP (`laion/larger_clap_music`) is the default.** Reasons, in order:

- **512-d, music-specialised checkpoint.** Compact and well-conditioned for
  cosine similarity.
- **Native in `transformers` as `ClapModel`.** No `trust_remote_code`, no
  custom CUDA kernels, runs on CPU.
- **Joint text–audio space.** Songs and *sentences* land in the same vector
  space, so `"dreamy neo-soul with jazzy chords"` can be scored against every
  uploaded song with the identical cosine function. For a discovery product
  that is a second whole feature for free — `ClapEmbedder.embed_text()`.

| Model | Verdict |
|---|---|
| **CLAP** | **Default.** Music checkpoint, 512-d, CPU-friendly, joint text-audio space |
| **MERT** (`m-a-p/MERT-v1-95M`) | **Supported alternate.** Genuinely better at *musical* structure (key/chord/genre probing). Not default because it emits frame-level states per layer — you must pick layers and pool twice — and needs `trust_remote_code`. `set CHORDPRINT_EMBEDDER=mert` |
| OpenL3 | Dropped. Drags in TensorFlow; AudioSet/video-correspondence trained, further from our domain |
| musicnn | Dropped. TF1-era, unmaintained |
| **SpectralEmbedder** | **Fallback, clearly labelled.** 100 real DSP descriptors (MFCC, chroma, spectral contrast, tonnetz + variances) computed with librosa. **Not** a pretrained network — the UI always shows which embedder produced a vector, so it is never mistaken for CLAP. It is also a fair baseline to compare the deep model against, which is a better result for a report than "we used a big model" |

**No vector is ever faked.** There is no `np.random` anywhere in
`embedders.py`. If no embedder can load, the code raises — it does not return
noise.

## The AI concepts, explained

**Embedding.** A learned function from something complicated (3 minutes of
audio) to a fixed-length list of numbers, where *distance means similarity*.
The model was trained so that things humans call alike end up close together.
Nothing about "512 dimensions" is meaningful individually — no single axis is
"jazziness". Only relative positions carry meaning.

**Vector space.** All song vectors live in the same 512-d space, so they can
be compared. Two vectors from *different models* cannot — they are different
spaces, and a cosine between them is meaningless rather than merely
inaccurate. `store.song_matrix(model=...)` enforces this.

**Cosine similarity.** `cos(a,b) = a·b / (‖a‖‖b‖)` — the angle between two
vectors, ignoring length. Length tracks recording loudness and duration;
direction tracks musical character. We L2-normalise everything on the way in,
so cosine reduces to a plain dot product.

**Pooling.** A song makes many window vectors; we need one. Mean pooling in
this exact order:
1. **L2-normalise each window first.** A loud chorus produces a
   bigger-magnitude embedding than a quiet verse; without this you embed the
   *mastering*, not the music. After normalising, every window gets one equal
   vote.
2. **Mean** → the centroid direction of the song.
3. **L2-normalise the result** so all songs sit on the same unit sphere.

Mean pooling assumes a song has one identity. Where it fails: a track that
changes character halfway averages to a midpoint representing neither half.
We keep per-window vectors in the store so max-over-windows is available.

**K-nearest neighbours.** No training — store every vector, and to answer
"who is like me" sort everyone by similarity and take the top K. At this
scale brute force *is* the index: 10k × 512 floats is 20 MB and one
matrix-vector product.

**Clustering (K-Means).** KNN answers "who is near *me*"; K-Means answers
"what groups exist *at all*". `k` is chosen by silhouette score. It runs on
the **learned embeddings**, not the hand-written features.

**Dimensionality reduction (PCA).** 512 dims cannot be drawn. PCA finds the
directions of greatest variance and projects onto the top 2 — the taste map.
Also genuinely useful before K-Means: in high dimensions everything is
roughly equidistant, which degrades clustering. Caveat: **match in the full
space, visualise in 2-D.** PC1 has no name. Use UMAP instead if you want
local neighbourhoods preserved better than global distances.

## Verified end to end

Five generated test signals with deliberately distinct spectra, through the
real pipeline (`testaudio/`, regenerate any time):

```
song-song cosine          nearest to jazz_a
        jazz_a jazz_b punk_a punk_b dark_a      jazz_b  0.997
jazz_a   1.000  0.997  0.879  0.876  0.887      dark_a  0.887
punk_a   0.879  0.903  1.000  0.999  0.802      punk_a  0.879
dark_a   0.887  0.888  0.802  0.804  1.000

K-Means on the embeddings:  k=3, silhouette 0.787
   cluster 0: jazz_a, jazz_b     (ada)
   cluster 1: punk_a, punk_b     (ben)
   cluster 2: dark_a             (cleo)
PCA: PC1+PC2 hold 99.5% of variance
User vectors land at the centroid of their own songs, as they should.
```

## Enabling CLAP

The DSP fallback works with no download. For the real pretrained model:

```powershell
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install transformers
```

The checkpoint (~600 MB–2 GB) downloads on your **first upload**, not at
boot, so the UI stays responsive. The Embedding model panel shows exactly
which backends are ready and which are not.

## Known limits

- **Cosine floor.** DSP vectors are largely non-negative, so unrelated songs
  still score ~0.8. Rankings are correct but the *spread* is compressed —
  CLAP separates much better. Compare ranks, not absolute numbers.
- **Songs shorter than one window** produce a single window. Fine, but the
  pooled vector is then just that window.
- Uploads are capped at 60 MB and the first 5 minutes of audio.
