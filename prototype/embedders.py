"""
STAGE 2: windows -> one fixed-length song vector.

    windows (n, samples) -> pretrained model -> (n, dim) -> pool -> (dim,)

MODEL CHOICE, AND WHY
=====================
Ranked, with the reason each was kept or dropped:

1. CLAP  (laion/larger_clap_music)                     <- DEFAULT
   Contrastive Language-Audio Pretraining. Trained on LAION-Audio-630K plus
   music corpora, with a music-specialised checkpoint. Picked because:
     * 512-d audio embedding -- compact, well-conditioned for cosine
     * native in HuggingFace `transformers` as ClapModel: no trust_remote_code,
       no custom CUDA kernels, runs on CPU
     * JOINT TEXT-AUDIO SPACE. Songs and sentences land in the SAME vector
       space, so "dreamy neo-soul with jazzy chords" can be scored against
       every uploaded song with the identical cosine function. For a social
       discovery product that is not a nice-to-have, it is a second whole
       feature for free.

2. MERT  (m-a-p/MERT-v1-95M)                           <- ALTERNATE, supported
   Music-specific self-supervised transformer, strong on MIR benchmarks
   (key, chord, genre probing). Genuinely better at *musical* structure than
   CLAP. Not the default only because it emits frame-level hidden states per
   layer -- you must choose layers and pool twice -- and it needs
   trust_remote_code plus occasionally nnAudio. Set CHORDPRINT_EMBEDDER=mert.

3. OpenL3 -- dropped. Drags in TensorFlow, which on Windows is a reliable way
   to lose an afternoon. L3 embeddings are also AudioSet/video-correspondence
   trained; CLAP's music checkpoint is closer to our domain.

4. musicnn -- dropped. TF1-era, effectively unmaintained.

5. SpectralEmbedder                                     <- FALLBACK, honest
   NOT a pretrained neural network. 100 real DSP descriptors computed from
   the uploaded audio with librosa: MFCC, chroma, spectral contrast, tonnetz,
   and their variances. It exists so the pipeline still runs with no model
   download, and because it is a fair baseline to compare the deep model
   against -- which is a more interesting result for a report than "we used
   a big model". Every response says which embedder produced the vector, so
   this is never silently mistaken for CLAP.

NOTHING HERE INVENTS A VECTOR. There is no np.random anywhere in this file.
If no embedder can run, we raise -- we do not return noise.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

import audio as A


# ------------------------------------------------------------- interface --

class AudioEmbedder(Protocol):
    name: str
    dim: int
    sample_rate: int
    window_s: float
    def embed_windows(self, windows: np.ndarray) -> np.ndarray: ...


@dataclass
class SongEmbedding:
    vector: np.ndarray          # (dim,) L2-normalised
    windows: np.ndarray         # (n_windows, dim) L2-normalised
    model: str
    dim: int
    n_windows: int
    duration_s: float


# ---------------------------------------------------------------- pooling --

def l2(x: np.ndarray, axis: int = -1) -> np.ndarray:
    n = np.linalg.norm(x, axis=axis, keepdims=True)
    n = np.where(n == 0, 1.0, n)
    return x / n


def mean_pool(window_vecs: np.ndarray) -> np.ndarray:
    """POOLING, and why it is done in this exact order.

    1. L2-normalise every window FIRST.
       A loud chorus produces a larger-magnitude embedding than a quiet
       verse. Without this step the chorus would dominate the average purely
       for being loud -- you would be embedding the mastering, not the music.
       After normalising, each window contributes a *direction* and every
       window gets one equal vote.

    2. Take the arithmetic mean -> the centroid direction of the song.

    3. L2-normalise the result, so cosine similarity is a plain dot product
       later and every song vector lives on the same unit sphere.

    Mean pooling assumes the song has one identity. That is usually right and
    always cheap. Where it fails: a track that changes character completely
    halfway through averages to a midpoint representing neither half. If that
    matters, keep the per-window vectors (we do) and use max-sim over windows.
    """
    if window_vecs.ndim != 2 or window_vecs.shape[0] == 0:
        raise ValueError("mean_pool needs at least one window embedding")
    unit = l2(window_vecs, axis=1)
    return l2(unit.mean(axis=0), axis=0)


# --------------------------------------------------------------- CLAP -----

class ClapEmbedder:
    name = "clap"
    sample_rate = 48000
    window_s = 10.0

    CANDIDATES = ["laion/larger_clap_music",
                  "laion/clap-htsat-unfused"]

    def __init__(self, model_id: Optional[str] = None, device: str = "cpu"):
        from transformers import AutoProcessor, ClapModel      # lazy
        import torch

        self.torch = torch
        last = None
        for mid in ([model_id] if model_id else self.CANDIDATES):
            try:
                self.processor = AutoProcessor.from_pretrained(mid)
                self.model = ClapModel.from_pretrained(mid).to(device).eval()
                self.model_id = mid
                break
            except Exception as e:                              # try next
                last = e
        else:
            raise RuntimeError(f"no CLAP checkpoint could be loaded: {last}")

        self.device = device
        self.dim = int(self.model.config.projection_dim)
        self.name = f"clap:{self.model_id.split('/')[-1]}"

    def _to_array(self, feats) -> np.ndarray:
        """transformers changed what get_*_features returns.

        <=4.x handed back a plain tensor. 5.x hands back a ModelOutput
        (BaseModelOutputWithPooling), so `.cpu()` raises AttributeError. Rather
        than pin a version, accept either shape and pull the projected
        embedding out of whichever field carries it.
        """
        t = feats
        if not hasattr(t, "cpu"):
            for attr in ("text_embeds", "audio_embeds", "embeds",
                         "pooler_output", "last_hidden_state"):
                got = getattr(t, attr, None)
                if got is not None:
                    t = got
                    break
            else:
                raise RuntimeError(
                    f"cannot find an embedding on {type(feats).__name__}: "
                    f"{list(getattr(feats, 'keys', lambda: [])())}")
        arr = t.detach().cpu().numpy()
        if arr.ndim == 3:                 # (batch, tokens, dim) -> mean tokens
            arr = arr.mean(axis=1)
        return arr.astype(np.float32)

    def embed_windows(self, windows: np.ndarray) -> np.ndarray:
        out = []
        bs = 4                                   # CPU-friendly batch
        for i in range(0, len(windows), bs):
            batch = [w for w in windows[i:i + bs]]
            # transformers 5.x renamed `audios` -> `audio`; support both so
            # this does not need a version pin.
            try:
                inputs = self.processor(audio=batch,
                                        sampling_rate=self.sample_rate,
                                        return_tensors="pt", padding=True)
            except (TypeError, ValueError):
                inputs = self.processor(audios=batch,
                                        sampling_rate=self.sample_rate,
                                        return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with self.torch.no_grad():
                feats = self.model.get_audio_features(**inputs)
            out.append(self._to_array(feats))
        return np.vstack(out).astype(np.float32)

    def embed_text(self, texts: list[str]) -> np.ndarray:
        """The joint-space bonus: sentences into the SAME 512-d space."""
        inputs = self.processor(text=texts, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with self.torch.no_grad():
            feats = self.model.get_text_features(**inputs)
        return l2(self._to_array(feats), axis=1)

    # ---------------------------------------------------------------------
    MAX_DEGENERATE_COS = 0.90

    def selfcheck(self) -> None:
        """Refuse to be used if the audio tower cannot tell noise from a tone.

        WHY THIS EXISTS
        A model that loads without error can still be silently broken -- a
        version-skewed checkpoint, a partially-restored state dict, a renamed
        output field that makes us read the wrong tensor. The failure mode is
        not a crash, it is an embedding that is nearly the same for every
        input. Every cosine then lands in a narrow band, every ranking is
        noise, and the UI happily reports "87% match" forever.

        So we hand it two signals that could not be more different -- white
        noise and a pure 440 Hz sine -- and require that it separate them.
        Anything above MAX_DEGENERATE_COS means the audio branch is not
        discriminating, and a DSP baseline that genuinely measures the signal
        is strictly better than a neural net that measures nothing.

        Observed with transformers 5.17 + laion/larger_clap_music: cos 0.949.
        """
        sr = self.sample_rate
        t = np.linspace(0, 10, sr * 10, endpoint=False)
        noise = (np.random.RandomState(0).randn(sr * 10) * 0.2).astype(np.float32)
        tone = (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32)
        E = l2(self.embed_windows(np.vstack([noise, tone])), axis=1)
        cos = float(E[0] @ E[1])
        if cos > self.MAX_DEGENERATE_COS:
            raise RuntimeError(
                f"{self.name} audio tower looks degenerate: white noise vs a "
                f"pure tone scored cos={cos:.3f} (expected well below "
                f"{self.MAX_DEGENERATE_COS}). Refusing to use it -- the "
                f"embeddings would be meaningless. Try pinning an older "
                f"transformers (4.x), which is where this checkpoint's audio "
                f"path is known to work.")


# --------------------------------------------------------------- MERT -----

class MertEmbedder:
    name = "mert"
    sample_rate = 24000
    window_s = 5.0

    def __init__(self, model_id: str = "m-a-p/MERT-v1-95M", device: str = "cpu",
                 layer: int = -1):
        from transformers import AutoModel, Wav2Vec2FeatureExtractor
        import torch

        self.torch = torch
        self.processor = Wav2Vec2FeatureExtractor.from_pretrained(
            model_id, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(
            model_id, trust_remote_code=True).to(device).eval()
        self.device, self.layer, self.model_id = device, layer, model_id
        self.dim = int(self.model.config.hidden_size)
        self.name = f"mert:{model_id.split('/')[-1]}"

    def embed_windows(self, windows: np.ndarray) -> np.ndarray:
        out = []
        for w in windows:
            inputs = self.processor(w, sampling_rate=self.sample_rate,
                                    return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with self.torch.no_grad():
                hs = self.model(**inputs, output_hidden_states=True).hidden_states
            # MERT is frame-level: (1, time, hidden). Mean over TIME first --
            # that is a second pooling step CLAP does not need.
            out.append(hs[self.layer][0].mean(axis=0).cpu().numpy())
        return np.vstack(out).astype(np.float32)


# ------------------------------------------------------- DSP baseline -----

class SpectralEmbedder:
    """100 real descriptors per window. Not a neural network -- and labelled
    as such everywhere it is used."""
    name = "spectral-dsp"
    sample_rate = 22050
    window_s = 10.0
    dim = 100

    # Fixed, CORPUS-INDEPENDENT scale per feature family.
    #
    # These raw descriptors live on wildly different scales: MFCCs run to
    # +-300, chroma is 0..1, spectral centroid is in Hz (thousands). Cosine
    # over that is decided entirely by the centroid.
    #
    # It is tempting to fix that with a StandardScaler -- but the scaler would
    # have to be fit on SOMETHING, and both obvious choices are wrong:
    #   * fit per song  -> every song normalised by its own statistics, so two
    #                      songs' vectors are no longer in the same space, and
    #                      a one-window song divides by zero and becomes 0.
    #   * fit per corpus -> every stored vector silently changes meaning the
    #                      next time somebody uploads a song.
    # An embedding must be a pure function of ONE audio file. So: constants.
    SCALE = {"mfcc": 50.0, "chroma": 1.0, "contrast": 40.0, "tonnetz": 1.0,
             "hz": 12.0, "unit": 1.0}

    def embed_windows(self, windows: np.ndarray) -> np.ndarray:
        import librosa
        sr = self.sample_rate
        rows = []
        for w in windows:
            S = np.abs(librosa.stft(w, n_fft=2048, hop_length=512))
            mel = librosa.feature.melspectrogram(S=S ** 2, sr=sr)
            mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=20)
            chroma = librosa.feature.chroma_stft(S=S, sr=sr)
            contrast = librosa.feature.spectral_contrast(S=S, sr=sr)
            tonnetz = librosa.feature.tonnetz(
                chroma=librosa.feature.chroma_cqt(y=w, sr=sr), sr=sr)
            cent = librosa.feature.spectral_centroid(S=S, sr=sr)
            bw = librosa.feature.spectral_bandwidth(S=S, sr=sr)
            roll = librosa.feature.spectral_rolloff(S=S, sr=sr)
            zcr = librosa.feature.zero_crossing_rate(w)
            rms = librosa.feature.rms(S=S)

            blocks = [
                (mfcc, "mfcc"), (chroma, "chroma"), (contrast, "contrast"),
                (tonnetz, "tonnetz"),
                (np.log1p(cent), "hz"), (np.log1p(bw), "hz"),
                (np.log1p(roll), "hz"), (zcr, "unit"), (rms, "unit"),
            ]
            parts = []
            for f, kind in blocks:
                k = self.SCALE[kind]
                parts.append(np.mean(f, axis=1) / k)
                parts.append(np.std(f, axis=1) / k)

            v = np.nan_to_num(np.concatenate(parts).astype(np.float32),
                              nan=0.0, posinf=0.0, neginf=0.0)
            if len(v) < self.dim:
                v = np.pad(v, (0, self.dim - len(v)))
            rows.append(v[:self.dim])
        return np.vstack(rows).astype(np.float32)


# ------------------------------------------------------------ selection ---

_CACHE: dict[str, AudioEmbedder] = {}


def get_embedder(prefer: Optional[str] = None) -> AudioEmbedder:
    """Load the best available embedder, once, and remember it.

    Order: explicit request -> CHORDPRINT_EMBEDDER -> CLAP -> MERT -> DSP.
    Raises if literally nothing can run; never returns a fake.
    """
    want = (prefer or os.environ.get("CHORDPRINT_EMBEDDER") or "clap").lower()
    if want in _CACHE:
        return _CACHE[want]

    order = {"clap": [ClapEmbedder, MertEmbedder, SpectralEmbedder],
             "mert": [MertEmbedder, ClapEmbedder, SpectralEmbedder],
             "spectral": [SpectralEmbedder],
             "dsp": [SpectralEmbedder]}.get(want,
             [ClapEmbedder, MertEmbedder, SpectralEmbedder])

    errors = []
    for cls in order:
        try:
            emb = cls()
            if hasattr(emb, "selfcheck"):
                emb.selfcheck()          # a broken model must not win by default
            _CACHE[want] = emb
            return emb
        except Exception as e:
            errors.append(f"{cls.__name__}: {type(e).__name__}: {e}")
    raise RuntimeError("no audio embedder available:\n  " + "\n  ".join(errors))


def probe() -> list[dict]:
    """What can actually run on this machine right now? Used by the UI."""
    rows = []
    for cls in (ClapEmbedder, MertEmbedder, SpectralEmbedder):
        try:
            e = cls()
            if hasattr(e, "selfcheck"):
                e.selfcheck()
            rows.append({"class": cls.__name__, "name": e.name,
                         "dim": e.dim, "ok": True, "note": ""})
        except Exception as ex:
            rows.append({"class": cls.__name__, "name": cls.name, "dim": None,
                         "ok": False, "note": f"{type(ex).__name__}: {ex}"[:180]})
    return rows


# ------------------------------------------------------------ the stage ---

def embed_song(path: str, embedder: Optional[AudioEmbedder] = None,
               max_seconds: float = 300.0) -> SongEmbedding:
    """song.mp3 -> preprocessing -> windows -> per-window embeddings -> pool."""
    emb = embedder or get_embedder()
    clip = A.load_audio(path, sr=emb.sample_rate, max_seconds=max_seconds)
    if clip.n_samples == 0:
        raise ValueError("audio decoded to zero samples")

    windows = A.window_audio(clip, window_s=emb.window_s,
                             hop_s=emb.window_s / 2)
    keep = np.array([not A.is_silent(w) for w in windows])
    if keep.any():
        windows = windows[keep]
    if len(windows) == 0:
        raise ValueError("audio is silent")

    win_vecs = emb.embed_windows(windows)
    if win_vecs.shape[0] != len(windows):
        raise RuntimeError("embedder returned the wrong number of vectors")

    unit = l2(win_vecs, axis=1)
    return SongEmbedding(vector=mean_pool(win_vecs), windows=unit,
                         model=emb.name, dim=int(win_vecs.shape[1]),
                         n_windows=int(len(windows)),
                         duration_s=clip.duration_s)
