from pathlib import Path

import librosa
import numpy as np
import pretty_midi

MODEL_NAME = "m-a-p/MERT-v1-95M"
MERT_SR = 24000

_MIDI_EXTENSIONS = {".mid", ".midi"}

_model = None
_processor = None


def _fix_weight_norm_checkpoint(model) -> None:
    """MERT's checkpoint was saved with the classic weight_norm parameterization
    (`weight_g`/`weight_v`), but the installed torch/transformers versions build the
    positional conv embedding with the newer `parametrizations.weight.{original0,original1}`
    layout. from_pretrained silently drops the mismatched keys and leaves that layer randomly
    initialized, so remap them by hand.
    """
    import torch
    from huggingface_hub import hf_hub_download

    checkpoint_path = hf_hub_download(MODEL_NAME, "pytorch_model.bin")
    raw_state = torch.load(checkpoint_path, map_location="cpu")
    params = dict(model.named_parameters())

    # load_state_dict() silently no-ops on parametrized submodule keys like these, so
    # copy directly into the parameter tensors instead.
    with torch.no_grad():
        for key, tensor in raw_state.items():
            for old_suffix, new_suffix in (
                (".weight_g", ".parametrizations.weight.original0"),
                (".weight_v", ".parametrizations.weight.original1"),
            ):
                if key.endswith(old_suffix):
                    new_key = key[: -len(old_suffix)] + new_suffix
                    if new_key in params:
                        params[new_key].copy_(tensor)


def _get_model():
    global _model, _processor
    if _model is None:
        from transformers import AutoConfig, AutoModel, Wav2Vec2FeatureExtractor

        _processor = Wav2Vec2FeatureExtractor.from_pretrained(MODEL_NAME, trust_remote_code=True)
        config = AutoConfig.from_pretrained(MODEL_NAME, trust_remote_code=True)
        config.output_hidden_states = True
        _model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True, config=config)
        _fix_weight_norm_checkpoint(_model)
        _model.eval()
    return _model, _processor


def _load_waveform(path: str, sr: int = MERT_SR) -> np.ndarray:
    if Path(path).suffix.lower() in _MIDI_EXTENSIONS:
        pm = pretty_midi.PrettyMIDI(path)
        return pm.synthesize(fs=sr).astype(np.float32)
    y, _ = librosa.load(path, sr=sr)
    return y.astype(np.float32)


def embed(path: str) -> np.ndarray:
    import torch

    model, processor = _get_model()
    waveform = _load_waveform(path)
    inputs = processor(waveform, sampling_rate=MERT_SR, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)

    # (num_layers, time, hidden_dim) -> average over layers, then over time -> one fixed vector
    all_layers = torch.stack(outputs.hidden_states, dim=0).squeeze(1)
    return all_layers.mean(dim=0).mean(dim=0).numpy()


def mert_similarity(path_a: str, path_b: str) -> float:
    a = embed(path_a)
    b = embed(path_b)
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.clip((cosine + 1.0) / 2.0, 0.0, 1.0))
