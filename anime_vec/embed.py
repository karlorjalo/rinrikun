import hashlib

import numpy as np

# A multilingual model: the library rows are in Japanese and the AniList rows are in English.
MODEL = "google/embeddinggemma-300m"
DIM = 768
BATCH_SIZE = 32
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
    # The model name is part of the hash. Thus a change of model makes all cached embeddings stale.
    return hashlib.sha1(f"{MODEL}\n{build_text(r)}".encode("utf-8")).hexdigest()


def gpu_providers() -> list[str] | None:
    """Return the ONNX providers for the GPU, or None if only the CPU is available.

    The GPU needs the packages `fastembed-gpu` and `onnxruntime-gpu[cuda,cudnn]`.
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
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        providers = gpu_providers()
        _model = TextEmbedding(MODEL, providers=providers) if providers else TextEmbedding(MODEL)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    return np.array(list(_get_model().embed(texts, batch_size=BATCH_SIZE)), dtype=np.float32)


def vec_to_blob(v: np.ndarray) -> bytes:
    return np.ascontiguousarray(v, dtype=np.float32).tobytes()


def blob_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
