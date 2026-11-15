"""2D layout of the embedding space for the vector map."""
import numpy as np

# Change this value when the layout method changes. The cached layouts then become stale.
VERSION = "tsne-v1"
# t-SNE needs more rows than its perplexity. Smaller indexes use PCA.
TSNE_MIN_ROWS = 100
TSNE_PERPLEXITY = 30


def can_use_tsne(n_rows: int) -> bool:
    if n_rows < TSNE_MIN_ROWS:
        return False
    try:
        import sklearn.manifold  # noqa: F401
    except ImportError:
        return False
    return True


def pca_layout(X: np.ndarray, dims: int = 2) -> np.ndarray:
    """Project the rows on their principal components. The result has `dims` columns."""
    X = np.asarray(X, dtype=np.float64)
    out = np.zeros((X.shape[0], dims))
    if X.ndim != 2 or X.shape[0] < 2 or X.shape[1] < 1:
        return out
    centered = X - X.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    proj = centered @ vt[:dims].T
    out[:, :proj.shape[1]] = proj
    return out


def tsne_layout(X: np.ndarray) -> np.ndarray:
    """Put rows that are neighbors in the embedding space near each other in 2D.

    PCA to 2 dimensions keeps less than 10% of the variance of a text embedding, thus the neighbors
    on a PCA map are almost random. t-SNE keeps the local neighbors.
    """
    from sklearn.manifold import TSNE

    reduced = pca_layout(X, dims=min(50, X.shape[1]))
    tsne = TSNE(n_components=2, perplexity=TSNE_PERPLEXITY, init="pca", random_state=0)
    return tsne.fit_transform(reduced)


def fit_unit_square(P: np.ndarray) -> np.ndarray:
    """Move the points into the square from 0 to 1, with the same scale on the two axes."""
    P = np.asarray(P, dtype=np.float64)
    if P.shape[0] == 0:
        return P.astype(np.float32)
    lo = P.min(axis=0)
    span = max(float((P.max(axis=0) - lo).max()), 1e-9)
    Q = (P - lo) / span
    # Put the shorter axis in the middle of the square
    Q += (1.0 - Q.max(axis=0)) / 2.0
    return Q.astype(np.float32)
