"""
End-to-end on 30 synthetic users. Runs offline.

    python demo.py

To go live, change ONE line:
    registry = default_registry(online=True)
and set CHORDPRINT_HT_USER / CHORDPRINT_HT_PASS. Nothing else changes --
that is the whole point of the provider seam.
"""
from __future__ import annotations

import random

import numpy as np
import pandas as pd

from features import UserInput, build_dataframe, FeatureSpace
from providers import default_registry
from recommend import (similarity_matrix, top_matches, knn_model, knn_query,
                       choose_k, describe_clusters, pca_report, recommend)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

SEED = 7
random.seed(SEED)
np.random.seed(SEED)

# --------------------------------------------------------------- archetypes
# Six taste archetypes, five users each = 30. Each user gets their
# archetype's progressions with noise, so clusters exist but are not trivial.
ARCHETYPES = {
    "neo-soul": dict(
        progs=[["ii7", "V7", "IM7", "vi7"], ["IM7", "vi7", "ii7", "V7"]],
        genres=["neo-soul", "jazz"], tempo=(78, 92),
        artists=["A. Rivers", "K. Osei", "Blue Lantern"]),
    "trap": dict(
        progs=[["i", "bVI", "bVII", "i"], ["i", "bVII", "bVI", "bVII"]],
        genres=["trap"], tempo=(132, 150),
        artists=["YK9", "Northside", "Prod. Halo"]),
    "punk": dict(
        progs=[["I", "IV", "V", "IV"], ["I", "V", "IV", "I"]],
        genres=["punk", "rock"], tempo=(158, 180),
        artists=["Deadline", "The Vents"]),
    "house": dict(
        progs=[["i", "bVII", "bVI", "bVII"], ["i", "iv", "bVI", "V"]],
        genres=["house"], tempo=(120, 128),
        artists=["Marin", "Club Atlas"]),
    "citypop": dict(
        progs=[["IM7", "iii7", "vi7", "ii7"], ["IM7", "V7", "vi7", "IV"]],
        genres=["city pop", "pop"], tempo=(100, 116),
        artists=["Nozomi", "Harbour Line"]),
    "ambient": dict(
        progs=[["I", "iii", "IV", "I"], ["I", "IV", "I", "IV"]],
        genres=["ambient"], tempo=(66, 80),
        artists=["Slow Field", "Nils K."]),
}

NOISE = ["V/V", "bIII", "IV", "vi", "ii", "V", "I", "bVII"]


def make_users(n_per: int = 5) -> list[UserInput]:
    users = []
    for arch, spec in ARCHETYPES.items():
        for i in range(n_per):
            uid = f"{arch}_{i+1}"
            progs = [list(random.choice(spec["progs"]))]
            if random.random() < 0.6:
                progs.append(list(random.choice(spec["progs"])))
            if random.random() < 0.35:                      # individual quirk
                p = list(random.choice(spec["progs"]))
                p.insert(random.randrange(len(p)), random.choice(NOISE))
                progs.append(p)
            users.append(UserInput(
                user_id=uid,
                progressions=progs,
                genres=list(spec["genres"]) + (
                    ["pop"] if random.random() < 0.3 else []),
                artists=random.sample(spec["artists"],
                                      k=min(2, len(spec["artists"]))),
                tempo_pref=random.uniform(*spec["tempo"]),
                velocity_mean=random.uniform(60, 115),
                voicing_density=random.uniform(2.8, 4.8),
            ))
    return users


def main() -> None:
    registry = default_registry(online=False)
    users = make_users()

    # 4. combine user input + enrichment into one DataFrame -----------------
    df = build_dataframe(users, registry)
    print("=" * 78)
    print("1-4. RAW TABLE  (user input + enriched metadata)")
    print("=" * 78)
    print(df[["genres", "tempo_bpm", "key", "mode", "energy",
              "extension_rate", "harmonic_complexity", "enriched_by"]].head(8))

    # 5-7. encode -----------------------------------------------------------
    space = FeatureSpace()
    X = space.fit_transform(df, registry)
    print("\n" + "=" * 78)
    print(f"5-7. FEATURE MATRIX  {X.shape[0]} users x {X.shape[1]} features")
    print("=" * 78)
    for name, sl in space.blocks_.items():
        print(f"   {name:<12} cols {sl.start:>3}..{sl.stop-1:<3} "
              f"({sl.stop-sl.start:>3})  weight {space.w[name]}")
    print(f"   surprisal range: "
          f"{min(space.surprisal_.values()):.1f} .. {max(space.surprisal_.values()):.1f} bits")

    # 8. cosine + KNN -------------------------------------------------------
    print("\n" + "=" * 78)
    print("8. MOST SIMILAR USERS")
    print("=" * 78)
    S = similarity_matrix(X, list(df.index))
    probe = "neo-soul_1"
    print(f"\ncosine, top 5 for {probe}:")
    print(top_matches(S, probe, 5).round(3).to_string())

    nn = knn_model(X, k=6)
    row = list(df.index).index(probe)
    print(f"\nsklearn KNN (metric='cosine'), same query:")
    print(knn_query(nn, X, list(df.index), row, 5).round(3).to_string())

    print(f"\nrecommendations with reasons for {probe}:")
    print(recommend(df, X, space, probe, k=3, registry=registry).to_string())

    # 9. clustering ---------------------------------------------------------
    print("\n" + "=" * 78)
    print("9. K-MEANS")
    print("=" * 78)
    res = choose_k(X, range(2, 9), seed=SEED)
    print("silhouette by k:", {k: round(v, 3) for k, v in res.scores.items()})
    print(f"chosen k = {res.k}  (silhouette {res.silhouette:.3f})\n")
    print(describe_clusters(df, res.labels).to_string())

    truth = [u.user_id.rsplit("_", 1)[0] for u in users]
    ct = pd.crosstab(pd.Series(truth, name="archetype"),
                     pd.Series(res.labels, name="cluster"))
    print("\narchetype vs cluster (did it recover the real groups?)")
    print(ct.to_string())

    # 10. PCA ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("10. PCA")
    print("=" * 78)
    p, table = pca_report(X, n_components=10, seed=SEED)
    print(table.head(6).to_string())
    keep = int(np.searchsorted(p.explained_variance_ratio_.cumsum(), 0.90) + 1)
    print(f"\n{keep} components hold 90% of the variance "
          f"(from {X.shape[1]} raw columns)")

    Z = p.transform(X)[:, :2]
    print("\ntaste map (PC1, PC2) - plot these two columns for the demo:")
    for arch in ARCHETYPES:
        m = np.array([t == arch for t in truth])
        print(f"   {arch:<10} centre ({Z[m,0].mean():+.3f}, {Z[m,1].mean():+.3f})")

    res2 = choose_k(p.transform(X)[:, :keep], range(2, 9), seed=SEED)
    print(f"\nk-means on {keep} PCA components: k={res2.k}, "
          f"silhouette {res2.silhouette:.3f} "
          f"(vs {res.silhouette:.3f} on the full space)")

    # 11. cold start --------------------------------------------------------
    print("\n" + "=" * 78)
    print("11. NEW USER, 4 CHORDS, NO HISTORY")
    print("=" * 78)
    newbie = UserInput(user_id="judge", progressions=[["ii7", "V7", "IM7"]],
                       genres=[], artists=[], tempo_pref=86.0)
    ndf = build_dataframe([newbie], registry)
    Xn = space.transform(ndf)                 # fitted space, no refit
    sims = (X @ Xn[0]) / (np.linalg.norm(X, axis=1) * np.linalg.norm(Xn[0]) + 1e-12)
    order = np.argsort(-sims)[:3]
    for j in order:
        who = df.index[j]
        print(f"   {who:<14} {sims[j]:.3f}")
    print("\n   ->", recommend(pd.concat([df, ndf]),
                               np.vstack([X, Xn]), space, "judge", k=1,
                               registry=registry)["why"].iloc[0])


if __name__ == "__main__":
    main()
