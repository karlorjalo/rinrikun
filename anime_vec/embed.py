import hashlib

import numpy as np

MODEL = "BAAI/bge-small-en-v1.5"
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
    return hashlib.sha1(build_text(r).encode("utf-8")).hexdigest()


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    return np.array(list(_get_model().embed(texts)), dtype=np.float32)


def vec_to_blob(v: np.ndarray) -> bytes:
    return np.ascontiguousarray(v, dtype=np.float32).tobytes()


def blob_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
