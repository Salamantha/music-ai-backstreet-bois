"""
STAGE 3: the database.

    song embedding -> disk -> user embedding -> retrieval

Two files in ./store/ :
    catalog.json   metadata (who uploaded what, which model made the vector)
    vectors.npz    the float32 matrices

Deliberately not a vector database. At hackathon scale a numpy matrix and a
matrix-vector product ARE the index: 10k songs x 512 dims is 20 MB and a
brute-force cosine over all of it takes about a millisecond. Swap in FAISS or
pgvector when that stops being true; `knn_songs` is the only function that
would change.

LAYOUT (the structure from the spec):

    User A
      Song 1 -> [0.12, -0.43, 0.82, ...]
      Song 2 -> [0.17, -0.38, 0.76, ...]
      user_embedding = mean(song vectors)      <- kept alongside, not instead
    User B
      Song 3 -> [0.14, -0.40, 0.79, ...]
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

STORE_DIR = Path(__file__).parent / "store"


def _l2(x: np.ndarray, axis=-1) -> np.ndarray:
    n = np.linalg.norm(x, axis=axis, keepdims=True)
    return x / np.where(n == 0, 1.0, n)


class VectorStore:
    def __init__(self, path: Path = STORE_DIR):
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.dir / "catalog.json"
        self.vectors_path = self.dir / "vectors.npz"
        self.songs: list[dict] = []
        self.song_vecs: dict[str, np.ndarray] = {}
        self.window_vecs: dict[str, np.ndarray] = {}
        self.load()

    # ------------------------------------------------------------ io ----
    def load(self) -> None:
        if self.catalog_path.exists():
            self.songs = json.loads(self.catalog_path.read_text("utf-8"))
        if self.vectors_path.exists():
            with np.load(self.vectors_path, allow_pickle=False) as z:
                for k in z.files:
                    if k.startswith("w::"):
                        self.window_vecs[k[3:]] = z[k]
                    else:
                        self.song_vecs[k] = z[k]

    def save(self) -> None:
        self.catalog_path.write_text(json.dumps(self.songs, indent=1), "utf-8")
        payload = dict(self.song_vecs)
        payload.update({f"w::{k}": v for k, v in self.window_vecs.items()})
        np.savez_compressed(self.vectors_path, **payload)

    # --------------------------------------------------------- writing --
    def add_song(self, user_id: str, title: str, emb, source: str = "upload",
                 keep_windows: bool = True, genres: Optional[list] = None,
                 genre_source: str = "none") -> str:
        """`emb` is an embedders.SongEmbedding."""
        song_id = uuid.uuid4().hex[:12]
        self.songs.append({
            "song_id": song_id,
            "user_id": user_id,
            "title": title,
            "model": emb.model,
            "dim": int(emb.dim),
            "n_windows": int(emb.n_windows),
            "duration_s": round(float(emb.duration_s), 1),
            "source": source,
            "genres": list(genres or []),
            "genre_source": genre_source,      # "clap-zero-shot" | "manual" | "both"
            "added": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.song_vecs[song_id] = np.asarray(emb.vector, dtype=np.float32)
        if keep_windows:
            self.window_vecs[song_id] = np.asarray(emb.windows, dtype=np.float32)
        self.save()
        return song_id

    def remove_song(self, song_id: str) -> bool:
        before = len(self.songs)
        self.songs = [s for s in self.songs if s["song_id"] != song_id]
        self.song_vecs.pop(song_id, None)
        self.window_vecs.pop(song_id, None)
        if len(self.songs) != before:
            self.save()
            return True
        return False

    # --------------------------------------------------------- reading --
    def song(self, song_id: str) -> Optional[dict]:
        return next((s for s in self.songs if s["song_id"] == song_id), None)

    def songs_of(self, user_id: str) -> list[dict]:
        return [s for s in self.songs if s["user_id"] == user_id]

    def user_ids(self) -> list[str]:
        seen = []
        for s in self.songs:
            if s["user_id"] not in seen:
                seen.append(s["user_id"])
        return seen

    def models_in_use(self) -> list[str]:
        return sorted({s["model"] for s in self.songs})

    def set_genres(self, song_id: str, genres: list, source: str = "manual") -> bool:
        s = self.song(song_id)
        if not s:
            return False
        s["genres"] = list(dict.fromkeys(genres))      # de-dup, keep order
        s["genre_source"] = source
        self.save()
        return True

    def song_matrix(self, model: Optional[str] = None,
                    genres: Optional[list] = None):
        """-> (ids, X). Only vectors from ONE model are ever stacked together:
        two different models produce two different vector spaces and a cosine
        between them is meaningless, not merely inaccurate.

        `genres` filters BEFORE the similarity is computed, not after -- so
        "top 5 jazz songs" really is the best five jazz songs, not whatever
        jazz survived a global top-5."""
        import genres as G
        rows = [s for s in self.songs
                if (model is None or s["model"] == model)
                and s["song_id"] in self.song_vecs
                and G.matches(s.get("genres"), genres)]
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        ids = [s["song_id"] for s in rows]
        X = np.vstack([self.song_vecs[i] for i in ids]).astype(np.float32)
        return ids, X

    def user_genres(self, user_id: str) -> list[str]:
        c: dict[str, int] = {}
        for s in self.songs_of(user_id):
            for g in (s.get("genres") or []):
                c[g] = c.get(g, 0) + 1
        return sorted(c, key=lambda g: (-c[g], g))

    def user_embedding(self, user_id: str, model: Optional[str] = None,
                       genres: Optional[list] = None) -> Optional[np.ndarray]:
        """user_embedding = mean(song_1, song_2, ...)

        Each song is already a unit vector, so the mean is an unweighted vote
        per song -- a 7-minute track does not outvote a 2-minute one. The
        individual song vectors stay in the store; this is derived, never a
        replacement.
        """
        import genres as G
        vecs = [self.song_vecs[s["song_id"]] for s in self.songs_of(user_id)
                if (model is None or s["model"] == model)
                and s["song_id"] in self.song_vecs
                and G.matches(s.get("genres"), genres)]
        if not vecs:
            return None
        return _l2(np.mean(_l2(np.vstack(vecs), axis=1), axis=0), axis=0)

    def user_matrix(self, model: Optional[str] = None,
                    genres: Optional[list] = None):
        """With a genre filter this becomes a *conditional* taste vector:
        "who else likes the jazz side of what I like", computed from only
        each user's jazz songs rather than their whole library."""
        ids, rows = [], []
        for uid in self.user_ids():
            v = self.user_embedding(uid, model, genres)
            if v is not None:
                ids.append(uid)
                rows.append(v)
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        return ids, np.vstack(rows).astype(np.float32)

    # ------------------------------------------------------ retrieval ---
    @staticmethod
    def _cos(X: np.ndarray, q: np.ndarray) -> np.ndarray:
        if X.size == 0:
            return np.zeros((0,), dtype=np.float32)
        return (_l2(X, axis=1) @ _l2(q, axis=0)).astype(np.float32)

    def knn_songs(self, q: np.ndarray, k: int = 5, model: Optional[str] = None,
                  exclude: tuple[str, ...] = (),
                  genres: Optional[list] = None) -> list[dict]:
        ids, X = self.song_matrix(model, genres)
        if not ids:
            return []
        sims = self._cos(X, q)
        out = []
        for j in np.argsort(-sims):
            sid = ids[j]
            if sid in exclude:
                continue
            meta = dict(self.song(sid) or {})
            meta["similarity"] = round(float(sims[j]), 4)
            out.append(meta)
            if len(out) >= k:
                break
        for rank, row in enumerate(out, 1):
            row["rank"] = rank
        return out

    def knn_users(self, q: np.ndarray, k: int = 5, model: Optional[str] = None,
                  exclude: tuple[str, ...] = (),
                  genres: Optional[list] = None) -> list[dict]:
        import genres as G
        ids, X = self.user_matrix(model, genres)
        if not ids:
            return []
        sims = self._cos(X, q)
        out = []
        for j in np.argsort(-sims):
            uid = ids[j]
            if uid in exclude:
                continue
            mine = [s for s in self.songs_of(uid)
                    if G.matches(s.get("genres"), genres)]
            out.append({"user_id": uid,
                        "similarity": round(float(sims[j]), 4),
                        "n_songs": len(mine),
                        "genres": self.user_genres(uid)[:4],
                        "songs": [s["title"] for s in mine][:6]})
            if len(out) >= k:
                break
        for rank, row in enumerate(out, 1):
            row["rank"] = rank
        return out

    def stats(self) -> dict:
        return {"n_songs": len(self.songs), "n_users": len(self.user_ids()),
                "models": self.models_in_use(),
                "dims": sorted({s["dim"] for s in self.songs})}
