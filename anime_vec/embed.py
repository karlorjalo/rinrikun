import hashlib

import numpy as np

# EmbeddingGemma 2 is multilingual: the library rows are in Japanese and the AniList rows are in English.
# fastembed does not support this model, thus this module runs the ONNX file with onnxruntime.
MODEL = "onnx-community/embeddinggemma-2-ONNX"
MODEL_FILE = "onnx/model.onnx"
# The model card gives this prefix for texts that are compared with each other
PROMPT = "task: sentence similarity | query: "
DIM = 768
BATCH_SIZE = 32
MAX_TOKENS = 2048
_model = None


def build_text(r: dict) -> str:
    parts = [f"{r.get('title_native') or r.get('title', '')} ({r.get('title')})"]
    if r.get("year"):
        parts.append(f". {r['year']}")
    if r.get("genres"):
        parts.append(". Genres: " + ", ".join(r["genres"][:6]))
    if r.get("tags"):
        parts.append(". Tags: " + ", ".join(r["tags"][:24]))
    if r.get("studios"):
        parts.append(". Studios: " + ", ".join(r["studios"][:3]))
    if r.get("overview"):
        parts.append(". " + r["overview"][:1200])
    return "".join(parts)


def text_hash(r: dict) -> str:
    # The model and the prompt are part of the hash. Thus a change of one of them makes all
    # cached embeddings stale.
    return hashlib.sha1(f"{MODEL}\n{PROMPT}\n{build_text(r)}".encode("utf-8")).hexdigest()


def gpu_providers() -> list[str] | None:
    """Return the ONNX providers for the GPU, or None if only the CPU is available.

    The GPU needs the package `onnxruntime-gpu[cuda,cudnn]` in the place of `onnxruntime`.
    """
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return None
    # Load the CUDA and cuDNN libraries that pip installed
    if hasattr(ort, "preload_dlls"):
        ort.preload_dlls()
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]


def _get_model():
    """Return the tokenizer and the ONNX session. The first call downloads the model (about 1.1 GB)."""
    global _model
    if _model is None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        model_path = hf_hub_download(MODEL, MODEL_FILE)
        # The weights are in a second file that must be adjacent to the model file
        hf_hub_download(MODEL, MODEL_FILE + "_data")
        tokenizer = Tokenizer.from_file(hf_hub_download(MODEL, "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        session = ort.InferenceSession(model_path, providers=gpu_providers() or ["CPUExecutionProvider"])
        _model = (tokenizer, session)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    tokenizer, session = _get_model()
    encoded = [tokenizer.encode(PROMPT + t).ids for t in texts]
    lengths = np.array([len(ids) for ids in encoded])
    # The model also accepts image, video and audio features. Text-only use gives empty arrays.
    extra = {i.name: np.zeros([d if isinstance(d, int) else 0 for d in i.shape], dtype=np.float32)
             for i in session.get_inputs() if i.name not in ("input_ids", "attention_mask")}
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    # Texts of similar length go in the same batch, so that the padding is small
    order = np.argsort(lengths, kind="stable")
    for start in range(0, len(texts), BATCH_SIZE):
        idx = order[start:start + BATCH_SIZE]
        width = int(lengths[idx].max())
        ids = np.zeros((len(idx), width), dtype=np.int64)
        mask = np.zeros((len(idx), width), dtype=np.int64)
        for row, i in enumerate(idx):
            ids[row, :lengths[i]] = encoded[i]
            mask[row, :lengths[i]] = 1
        feed = {"input_ids": ids, "attention_mask": mask, **extra}
        out[idx] = session.run(["sentence_embedding"], feed)[0]
    return out


def vec_to_blob(v: np.ndarray) -> bytes:
    return np.ascontiguousarray(v, dtype=np.float32).tobytes()


def blob_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
