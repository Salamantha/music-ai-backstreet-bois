from .align import SimilarityResult, dtw_similarity
from .loaders import CHROMA_FPS, load_chroma


def compare(path_a: str, path_b: str, fps: float = CHROMA_FPS) -> SimilarityResult:
    chroma_a = load_chroma(path_a, fps=fps)
    chroma_b = load_chroma(path_b, fps=fps)
    return dtw_similarity(chroma_a, chroma_b)
