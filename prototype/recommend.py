"""
Matching: cosine similarity, KNN, K-Means, PCA.

WHY COSINE AND NOT EUCLIDEAN
    cos(a,b) = (a.b) / (|a||b|)
    It ignores magnitude. A user who listed 30 genres and a user who listed 3
    should still be "the same taste" if the 3 are inside the 30. Euclidean
    would call the long vector far from everything, purely for being long.

WHY K-MEANS STILL WORKS ON L2-NORMALISED VECTORS
    K-Means minimises squared Euclidean distance. For unit vectors:
        |a-b|^2 = |a|^2 + |b|^2 - 2 a.b = 2 - 2 cos(a,b)
    So on the unit sphere, Euclidean distance is a monotone function of
    cosine distance and K-Means is doing exactly what you want. This is
    "spherical k-means". Normalise first, or the clustering means something
    different from your similarity metric.

WHEN PCA
    see pca_report() below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize


# ------------------------------------------------------------- similarity --

def similarity_matrix(X: np.ndarray, index: Sequence[str]) -> pd.DataFrame:
    S = cosine_similarity(X)
    np.fill_diagonal(S, 0.0)              # nobody's best match is themselves
    return pd.DataFrame(S, index=index, columns=index)


def top_matches(S: pd.DataFrame, user_id: str, k: int = 5) -> pd.Series:
    return S.loc[user_id].sort_values(ascending=False).head(k)


def knn_model(X: np.ndarray, k: int = 6) -> NearestNeighbors:
    """sklearn's KNN with metric='cosine'. Same answer as the matrix above,
    but O(k) memory instead of O(n^2) -- use this once you have real users."""
    nn = NearestNeighbors(n_neighbors=min(k, len(X)), metric="cosine")
    nn.fit(X)
    return nn


def knn_query(nn: NearestNeighbors, X: np.ndarray, index: Sequence[str],
              row: int, k: int = 5) -> pd.Series:
    dist, idx = nn.kneighbors(X[row:row + 1], n_neighbors=min(k + 1, len(X)))
    out = {index[j]: 1 - d for d, j in zip(dist[0], idx[0]) if j != row}
    return pd.Series(out).sort_values(ascending=False).head(k)


# ------------------------------------------------------------- clustering --

@dataclass
class ClusterResult:
    labels: np.ndarray
    k: int
    silhouette: float
    model: KMeans
    scores: dict[int, float]


def choose_k(X: np.ndarray, k_range=range(2, 9), seed: int = 42) -> ClusterResult:
    """Silhouette picks k. s(i) = (b-a)/max(a,b) where a = mean distance to
    your own cluster and b = mean distance to the nearest other cluster.
    +1 = crisply grouped, 0 = on a boundary, -1 = in the wrong cluster."""
    Xn = normalize(X)                      # spherical k-means, see module doc
    best, scores = None, {}
    for k in k_range:
        if k >= len(Xn):
            break
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Xn)
        if len(set(km.labels_)) < 2:
            continue
        s = silhouette_score(Xn, km.labels_, metric="cosine")
        scores[k] = float(s)
        if best is None or s > best.silhouette:
            best = ClusterResult(km.labels_, k, float(s), km, scores)
    if best is None:
        km = KMeans(n_clusters=2, n_init=10, random_state=seed).fit(Xn)
        best = ClusterResult(km.labels_, 2, float("nan"), km, scores)
    best.scores = scores
    return best


def describe_clusters(df: pd.DataFrame, labels: np.ndarray, top: int = 3) -> pd.DataFrame:
    """Name each cluster by the genres that are OVER-represented in it, not
    the most frequent -- 'pop' is everywhere and names nothing."""
    base: dict[str, int] = {}
    for gs in df["genres"]:
        for g in gs:
            base[g] = base.get(g, 0) + 1
    n = len(df)
    rows = []
    for c in sorted(set(labels)):
        members = df[labels == c]
        cnt: dict[str, int] = {}
        for gs in members["genres"]:
            for g in gs:
                cnt[g] = cnt.get(g, 0) + 1
        lift = {g: (v / len(members)) / (base[g] / n) for g, v in cnt.items()}
        top_g = sorted(lift, key=lambda g: (-lift[g], g))[:top]
        rows.append({
            "cluster": c,
            "size": len(members),
            "signature_genres": ", ".join(top_g),
            "mean_tempo": round(float(pd.to_numeric(members["tempo_bpm"],
                                errors="coerce").mean(skipna=True) or 0), 1),
            "mean_complexity": round(float(pd.to_numeric(
                members["harmonic_complexity"], errors="coerce").mean(skipna=True) or 0), 2),
            "members": ", ".join(list(members.index)[:6]),
        })
    return pd.DataFrame(rows).set_index("cluster")


# -------------------------------------------------------------------- PCA --

def pca_report(X: np.ndarray, n_components: int = 10, seed: int = 42):
    """IS PCA WORTH IT HERE?

    Use it when:
      * you have hundreds of sparse one-hot genre/artist columns and only
        tens of users -- distances get meaningless in high dimensions
        (everything is roughly equidistant: the curse of dimensionality),
        and K-Means suffers badly from this.
      * you want a 2-D picture for the demo. PC1/PC2 IS your taste map.
      * n-gram columns are correlated (ii7>V7 and V7>IM7 co-occur), and PCA
        merges correlated columns into one axis instead of double-counting.

    Do NOT use it when:
      * you need to explain a match. PC3 has no name; 'you both play bVII-IV-I'
        does. Match on the raw space, visualise with PCA.
      * you have fewer users than features and you keep too many components --
        with 30 users, n_components <= 30 no matter how many columns you have.

    PCA centers the data, which destroys sparsity. For a big real deployment
    use TruncatedSVD (= LSA) on the sparse matrix instead; same idea, no
    centering.
    """
    n_components = int(min(n_components, X.shape[0] - 1, X.shape[1]))
    p = PCA(n_components=n_components, random_state=seed).fit(X)
    ev = p.explained_variance_ratio_
    return p, pd.DataFrame({
        "component": [f"PC{i+1}" for i in range(len(ev))],
        "explained": ev.round(4),
        "cumulative": ev.cumsum().round(4),
    }).set_index("component")


# ------------------------------------------------------------ explanation --

def explain(df: pd.DataFrame, space, a: str, b: str, registry=None,
            top: int = 3) -> str:
    """The sentence. A cosine of 0.83 does not make anyone message a stranger."""
    ga, gb = df.loc[a, "ngrams"], df.loc[b, "ngrams"]
    shared = set(ga) & set(gb)
    if shared:
        ranked = sorted(shared, key=lambda g: -space.surprisal_.get(g, 0.0))
        best = ranked[0]
        bits = space.surprisal_.get(best, 0.0)
        line = f"You both play {best.replace('>', ' - ')}"
        if bits:
            line += f" ({bits:.1f} bits of surprise - most people never go there)"
    else:
        line = "No shared progressions yet"

    common_g = set(df.loc[a, "genres"]) & set(df.loc[b, "genres"])
    if common_g:
        line += f"; shared ground in {', '.join(sorted(common_g)[:2])}"

    ta, tb = df.loc[a, "tempo_bpm"], df.loc[b, "tempo_bpm"]
    if pd.notna(ta) and pd.notna(tb) and abs(float(ta) - float(tb)) > 30:
        line += f"; you sit at {float(ta):.0f} bpm and they sit at {float(tb):.0f}"
    return line + "."


def recommend(df: pd.DataFrame, X: np.ndarray, space, user_id: str,
              k: int = 3, registry=None) -> pd.DataFrame:
    S = similarity_matrix(X, list(df.index))
    top = top_matches(S, user_id, k)
    return pd.DataFrame({
        "match": top.index,
        "similarity": top.values.round(3),
        "why": [explain(df, space, user_id, m, registry) for m in top.index],
    }).set_index("match")
