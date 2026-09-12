"""
Local test bench. Stdlib HTTP only -- no Flask.

    run_ui.bat      ->  http://localhost:8765

Two pipelines share one UI and one similarity/clustering layer:

  A. CHORDS   roman numerals -> features.py  -> FeatureSpace  -.
                                                                >-- recommend.py
  B. AUDIO    song.mp3 -> audio.py -> embedders.py -> store.py -'   (cosine,
                                                                     KNN,
                                                                     KMeans,
                                                                     PCA)

recommend.py is reused verbatim for both: its functions take a matrix X and
do not care whether a column came from a Roman numeral or a neural network.
"""
from __future__ import annotations

import json
import tempfile
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd

from demo import ARCHETYPES, make_users
from features import FeatureSpace, UserInput, build_dataframe, normalize_roman
from providers import default_registry
from recommend import choose_k, explain, pca_report

import store as STOREMOD

PORT = 8765
HERE = Path(__file__).parent
MAX_UPLOAD = 60 * 1024 * 1024          # 60 MB


# ------------------------------------------------ A. chord model (as was) --

print("fitting chord-progression model...")
REGISTRY = default_registry(online=False)
USERS = make_users()
DF = build_dataframe(USERS, REGISTRY)
SPACE = FeatureSpace()
X = SPACE.fit_transform(DF, REGISTRY)
CLUSTERS = choose_k(X, range(2, 9), seed=7)
PCA_MODEL, _ = pca_report(X, n_components=10, seed=7)
Z = PCA_MODEL.transform(X)[:, :2]
ARCH_OF = {u.user_id: u.user_id.rsplit("_", 1)[0] for u in USERS}
print(f"  {X.shape[0]} users x {X.shape[1]} features, k={CLUSTERS.k}")

POPULATION = {
    "users": [{"id": uid, "archetype": ARCH_OF[uid],
               "cluster": int(CLUSTERS.labels[i]),
               "pc1": float(Z[i, 0]), "pc2": float(Z[i, 1]),
               "tempo": float(DF.loc[uid, "tempo_bpm"]),
               "genres": list(DF.loc[uid, "genres"])}
              for i, uid in enumerate(DF.index)],
    "archetypes": list(ARCHETYPES.keys()),
    "vocab_size": len(SPACE.vocab_),
    "n_features": int(X.shape[1]),
    "weights": SPACE.w,
    "all_genres": sorted({g for gs in DF["genres"] for g in gs}),
}


def match_payload(progression, tempo, genres, artists):
    roman = [t for t in (normalize_roman(t) for t in progression) if t]
    if len(roman) < 2:
        return {"error": "Pick at least 2 chords."}
    you = UserInput(user_id="__you__", progressions=[roman],
                    genres=genres or [], artists=artists or [],
                    tempo_pref=float(tempo) if tempo else None)
    ndf = build_dataframe([you], REGISTRY)
    xn = SPACE.transform(ndf)[0]
    sims = (X @ xn) / (np.linalg.norm(X, axis=1) * np.linalg.norm(xn) + 1e-12)
    order = np.argsort(-sims)[:5]
    both = pd.concat([DF, ndf])
    matches = [{"id": str(DF.index[j]), "archetype": ARCH_OF[str(DF.index[j])],
                "score": round(float(sims[j]), 3),
                "why": explain(both, SPACE, "__you__", str(DF.index[j]), REGISTRY)}
               for j in order]
    z = PCA_MODEL.transform(xn.reshape(1, -1))[0]
    row = ndf.iloc[0]
    shared = sorted(({"ngram": g.replace(">", " - "),
                      "bits": round(SPACE.surprisal_[g], 1)}
                     for g in row["ngrams"] if g in SPACE.surprisal_),
                    key=lambda s: -s["bits"])
    return {"roman": roman, "pc1": float(z[0]), "pc2": float(z[1]),
            "profile": {"extension_rate": round(float(row["extension_rate"]), 2),
                        "chromaticism": round(float(row["chromaticism"]), 2),
                        "minor_ratio": round(float(row["minor_ratio"]), 2),
                        "repertoire": round(float(row["repertoire"]), 2),
                        "harmonic_complexity": (
                            round(float(row["harmonic_complexity"]), 2)
                            if pd.notna(row["harmonic_complexity"]) else None),
                        "tempo_bpm": (round(float(row["tempo_bpm"]), 1)
                                      if pd.notna(row["tempo_bpm"]) else None)},
            "shared": shared[:6], "matches": matches}


# ---------------------------------------------------- B. audio embeddings --

STORE = STOREMOD.VectorStore()
_EMB_LOCK = threading.Lock()
_EMBEDDER = {"obj": None, "error": None, "probed": None}


_WARM = {"state": "idle", "note": ""}


def embedder():
    """Return an embedder that is READY NOW.

    The good model is hundreds of megabytes. Downloading it inside an upload
    request means the request hangs for as long as the download takes, with
    no way to report progress and a browser timeout at the end of it. So:
    whatever is ready right now serves the request, and the heavy model is
    fetched by `warm_up()` in the background. When it lands it becomes the
    default for subsequent uploads.

    Vectors keep the name of the model that made them, so nothing silently
    mixes two vector spaces mid-library -- see store.song_matrix.
    """
    with _EMB_LOCK:
        if _EMBEDDER["obj"] is None and _EMBEDDER["error"] is None:
            try:
                import embedders
                _EMBEDDER["obj"] = embedders.get_embedder("spectral")
            except Exception as e:
                _EMBEDDER["error"] = f"{type(e).__name__}: {e}"
        return _EMBEDDER["obj"]


def warm_up():
    """Try to bring the pretrained model online, off the request path."""
    import embedders
    _WARM["state"] = "loading"
    try:
        emb = embedders.ClapEmbedder()
        emb.selfcheck()            # degenerate model -> keep the DSP baseline
        with _EMB_LOCK:
            _EMBEDDER["obj"] = emb
        _TAGGER["obj"] = _TAGGER["error"] = None      # rebuild against CLAP
        _WARM.update(state="ready", note=emb.name)
        print(f"  [warm] {emb.name} ready ({emb.dim}d) — new uploads use it")
    except Exception as e:
        _WARM.update(state="unavailable", note=f"{type(e).__name__}: {e}"[:200])
        print(f"  [warm] CLAP unavailable: {_WARM['note'][:120]}")


def embed_status():
    out = {"loaded": None, "error": _EMBEDDER["error"], "store": STORE.stats(),
           "warm": dict(_WARM)}
    if _EMBEDDER["obj"] is not None:
        e = _EMBEDDER["obj"]
        out["loaded"] = {"name": e.name, "dim": e.dim,
                         "sample_rate": e.sample_rate, "window_s": e.window_s}
    if _EMBEDDER["probed"] is None:
        try:
            import embedders
            _EMBEDDER["probed"] = embedders.probe()
        except Exception as e:
            _EMBEDDER["probed"] = [{"class": "import", "ok": False,
                                    "note": f"{type(e).__name__}: {e}"[:200]}]
    out["available"] = _EMBEDDER["probed"]
    return out


_TAGGER = {"obj": None, "error": None}


def tagger():
    """Zero-shot genre tagger. Only exists if the embedder has a text side."""
    if _TAGGER["obj"] is None and _TAGGER["error"] is None:
        try:
            import genres as G
            _TAGGER["obj"] = G.GenreTagger(embedder())
        except Exception as e:
            _TAGGER["error"] = f"{type(e).__name__}: {e}"
    return _TAGGER["obj"]


def handle_upload(raw: bytes, filename: str, user_id: str,
                  manual_genres: list | None = None,
                  filter_genres: list | None = None) -> dict:
    import audio as A
    import embedders as E

    if not A.is_supported(filename):
        return {"error": f"Unsupported file type. Try {sorted(A.SUPPORTED)}."}

    emb = embedder()
    if emb is None:
        return {"error": "No audio embedder available. " + (_EMBEDDER["error"] or "")}

    suffix = Path(filename).suffix or ".mp3"
    tmp = Path(tempfile.gettempdir()) / f"cp_{abs(hash(filename))}{suffix}"
    tmp.write_bytes(raw)
    try:
        se = E.embed_song(str(tmp), embedder=emb)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    # zero-shot genre tagging straight off the embedding (CLAP only)
    auto, ranked, gsource = [], [], "manual" if manual_genres else "none"
    tg = tagger()
    if tg is not None:
        try:
            ranked = tg.score(se.vector)[:6]
            auto = tg.tag(se.vector)
            gsource = "both" if manual_genres else "clap-zero-shot"
        except Exception as e:
            _TAGGER["error"] = f"{type(e).__name__}: {e}"

    all_genres = list(dict.fromkeys(list(manual_genres or []) + auto))
    song_id = STORE.add_song(user_id=user_id, title=Path(filename).stem, emb=se,
                             genres=all_genres, genre_source=gsource)

    uvec = STORE.user_embedding(user_id, se.model, filter_genres)
    return {
        "song_id": song_id,
        "title": Path(filename).stem,
        "user_id": user_id,
        "model": se.model,
        "dim": se.dim,
        "n_windows": se.n_windows,
        "duration_s": round(se.duration_s, 1),
        "vector_head": [round(float(v), 4) for v in se.vector[:8]],
        "genres": all_genres,
        "genre_source": gsource,
        "genre_ranked": ranked,
        "genre_error": _TAGGER["error"],
        "filter": filter_genres or [],
        "nearest_songs": STORE.knn_songs(se.vector, k=5, model=se.model,
                                         exclude=(song_id,),
                                         genres=filter_genres),
        "similar_users": ([] if uvec is None else STORE.knn_users(
            uvec, k=5, model=se.model, exclude=(user_id,),
            genres=filter_genres)),
        "store": STORE.stats(),
    }


def embed_map(model: str | None = None, genres: list | None = None) -> dict:
    """PCA to 2D + KMeans, both run on the LEARNED EMBEDDINGS.

    With a genre filter, PCA is refit on the filtered subset -- the axes are
    then the directions that best separate *those* songs, which is usually
    far more informative than a global projection with everything else
    squashed into a corner.
    """
    model = model or (STORE.models_in_use() or [None])[0]
    ids, Xs = STORE.song_matrix(model, genres)
    out = {"model": model, "n_songs": len(ids), "songs": [], "users": [],
           "explained": None, "k": None, "silhouette": None,
           "filter": genres or []}
    if len(ids) == 0:
        return out

    meta = {s["song_id"]: s for s in STORE.songs}
    if len(ids) >= 3:
        p, table = pca_report(Xs, n_components=min(10, len(ids) - 1), seed=7)
        Zs = p.transform(Xs)[:, :2]
        out["explained"] = float(table["cumulative"].iloc[
            min(1, len(table) - 1)])
    else:
        Zs = np.zeros((len(ids), 2), dtype=np.float32)

    labels = np.zeros(len(ids), dtype=int)
    if len(ids) >= 4:
        res = choose_k(Xs, range(2, min(9, len(ids))), seed=7)
        labels, out["k"], out["silhouette"] = res.labels, res.k, round(res.silhouette, 3)

    out["songs"] = [{"song_id": sid, "title": meta[sid]["title"],
                     "user_id": meta[sid]["user_id"],
                     "genres": meta[sid].get("genres", []),
                     "cluster": int(labels[i]),
                     "pc1": float(Zs[i, 0]), "pc2": float(Zs[i, 1])}
                    for i, sid in enumerate(ids)]

    uids, Xu = STORE.user_matrix(model, genres)
    if len(uids) and len(ids) >= 3:
        Zu = p.transform(Xu)[:, :2]
        out["users"] = [{"user_id": u, "pc1": float(Zu[i, 0]),
                         "pc2": float(Zu[i, 1]),
                         "n_songs": len(STORE.songs_of(u))}
                        for i, u in enumerate(uids)]
    return out


def similar_to_song(song_id: str, k: int = 5, genres: list | None = None) -> dict:
    s = STORE.song(song_id)
    if not s or song_id not in STORE.song_vecs:
        return {"error": "unknown song_id"}
    q = STORE.song_vecs[song_id]
    return {"song": s, "filter": genres or [],
            "nearest_songs": STORE.knn_songs(q, k=k, model=s["model"],
                                             exclude=(song_id,), genres=genres),
            "similar_users": STORE.knn_users(q, k=k, model=s["model"],
                                             genres=genres)}


def retag_all() -> dict:
    """Re-run zero-shot tagging over everything already stored -- for when
    CLAP finishes downloading after you already uploaded under the fallback,
    or when you edit the taxonomy in genres.py."""
    tg = tagger()
    if tg is None:
        return {"error": _TAGGER["error"] or "no text-capable model loaded"}
    emb = embedder()
    n = 0
    for s in STORE.songs:
        if s["model"] != emb.name or s["song_id"] not in STORE.song_vecs:
            continue
        STORE.set_genres(s["song_id"], tg.tag(STORE.song_vecs[s["song_id"]]),
                         "clap-zero-shot")
        n += 1
    return {"retagged": n, "skipped": len(STORE.songs) - n,
            "genres": _genre_index()}


def _genre_index() -> dict:
    import genres as G
    return {"taxonomy": G.LABELS, "counts": G.counts(STORE.songs),
            "tagger_ready": tagger() is not None,
            "tagger_error": _TAGGER["error"]}


# ----------------------------------------------------------------- server --

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _file(self, name, ctype):
        p = HERE / name
        if not p.exists():
            return self._send(404, b"not found", "text/plain")
        self._send(200, p.read_bytes(), ctype)

    def _qs_genres(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        raw = q.get("genres", [""])[0]
        return [g for g in raw.split(",") if g] or None

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html", "/ui.html"):
            return self._file("ui.html", "text/html; charset=utf-8")
        if path == "/chordprint.js":
            return self._file("chordprint.js", "application/javascript; charset=utf-8")
        if path == "/api/population":
            return self._send(200, json.dumps(POPULATION))
        if path == "/api/embed_status":
            return self._send(200, json.dumps(embed_status()))
        if path == "/api/embed_map":
            return self._send(200, json.dumps(embed_map(None, self._qs_genres())))
        if path == "/api/genres":
            return self._send(200, json.dumps(_genre_index()))
        if path == "/api/songs":
            import genres as G
            want = self._qs_genres()
            rows = [s for s in STORE.songs if G.matches(s.get("genres"), want)]
            return self._send(200, json.dumps(
                {"songs": rows, "stats": STORE.stats(), "filter": want or []}))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n > MAX_UPLOAD:
            return self._send(413, json.dumps(
                {"error": f"File too large (max {MAX_UPLOAD // 1024 // 1024} MB)."}))
        body = self.rfile.read(n) if n else b""
        try:
            if path == "/api/match":
                req = json.loads(body or b"{}")
                return self._send(200, json.dumps(match_payload(
                    req.get("progression", []), req.get("tempo"),
                    req.get("genres", []), req.get("artists", []))))

            if path == "/api/upload":
                fn = self.headers.get("X-Filename", "upload.mp3")
                uid = self.headers.get("X-User", "you").strip() or "you"
                man = [g for g in self.headers.get("X-Genres", "").split(",") if g]
                flt = [g for g in self.headers.get("X-Filter", "").split(",") if g]
                return self._send(200, json.dumps(
                    handle_upload(body, fn, uid, man, flt or None)))

            if path == "/api/similar_songs":
                req = json.loads(body or b"{}")
                return self._send(200, json.dumps(similar_to_song(
                    req.get("song_id", ""), int(req.get("k", 5)),
                    req.get("genres") or None)))

            if path == "/api/set_genres":
                req = json.loads(body or b"{}")
                ok = STORE.set_genres(req.get("song_id", ""),
                                      req.get("genres", []), "manual")
                return self._send(200, json.dumps(
                    {"ok": ok, "genres": _genre_index()}))

            if path == "/api/retag":
                return self._send(200, json.dumps(retag_all()))

            if path == "/api/delete_song":
                req = json.loads(body or b"{}")
                ok = STORE.remove_song(req.get("song_id", ""))
                return self._send(200, json.dumps(
                    {"deleted": ok, "store": STORE.stats()}))
        except Exception as e:
            traceback.print_exc()
            return self._send(200, json.dumps(
                {"error": f"{type(e).__name__}: {e}"}))
        self._send(404, json.dumps({"error": "not found"}))


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"\n  open {url}   (ctrl-c to stop)")
    print("  [warm] fetching CLAP in the background; uploads work immediately\n")
    threading.Thread(target=warm_up, daemon=True).start()
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
