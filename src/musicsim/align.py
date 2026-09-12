from dataclasses import dataclass

import librosa
import numpy as np


@dataclass
class SimilarityResult:
    score: float  # 0 (dissimilar) .. 1 (identical), based on average DTW alignment cost
    cost: float  # average cosine distance along the optimal alignment path
    alignment_path: np.ndarray  # (N, 2) frame index pairs, chronological order
    chroma_a: np.ndarray
    chroma_b: np.ndarray


def _l2_normalize(chroma: np.ndarray) -> np.ndarray:
    # nudge silent (all-zero) frames off exactly zero so they normalize to a well-defined
    # unit vector instead of leaving a zero vector that blows up cosine distance into NaN
    chroma = chroma + 1e-8
    norm = np.linalg.norm(chroma, axis=0, keepdims=True)
    return chroma / norm


def dtw_similarity(chroma_a: np.ndarray, chroma_b: np.ndarray) -> SimilarityResult:
    a = _l2_normalize(chroma_a)
    b = _l2_normalize(chroma_b)
    cost_matrix, warping_path = librosa.sequence.dtw(X=a, Y=b, metric="cosine")

    avg_cost = float(cost_matrix[-1, -1] / len(warping_path))
    # cosine distance on L2-normalized vectors ranges [0, 2]; map to a 0..1 similarity score
    score = float(np.clip(1.0 - avg_cost / 2.0, 0.0, 1.0))

    return SimilarityResult(
        score=score,
        cost=avg_cost,
        alignment_path=warping_path[::-1],
        chroma_a=chroma_a,
        chroma_b=chroma_b,
    )
