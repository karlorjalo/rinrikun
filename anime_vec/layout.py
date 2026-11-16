"""2D layout of the embedding space for the vector map."""
import numpy as np

# Change this value when the layout method changes. The cached layouts then become stale.
VERSION = "tsne-v2"
# t-SNE needs more rows than its perplexity. Smaller indexes use PCA.
TSNE_MIN_ROWS = 100
TSNE_PERPLEXITY = 30
# The map gets region labels only when the index has this number of rows or more
REGION_MIN_ROWS = 200
REGION_COUNT = 14
# A region with less than this number of rows gets no label
REGION_MIN_SIZE = 15


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

    t-SNE gets the full vectors with the cosine distance. A PCA step to 50 dimensions before t-SNE
    is common because it is faster, but it removed a part of the structure: the map kept 33% of the
    10 nearest neighbors with that step and 40% without it.
    """
    from sklearn.manifold import TSNE

    tsne = TSNE(n_components=2, perplexity=TSNE_PERPLEXITY, metric="cosine", init="pca", random_state=0)
    return tsne.fit_transform(np.asarray(X, dtype=np.float64))


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


def kmeans(P: np.ndarray, k: int, iterations: int = 50, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Divide the points into k groups. Return the group of each point and the centers of the groups."""
    P = np.asarray(P, dtype=np.float64)
    k = max(1, min(k, len(P)))
    rng = np.random.default_rng(seed)
    # k-means++ start: each new center is probably far from the centers that exist
    centers = [P[rng.integers(len(P))]]
    for _ in range(1, k):
        d = np.min([((P - c) ** 2).sum(axis=1) for c in centers], axis=0)
        total = d.sum()
        pick = rng.choice(len(P), p=d / total) if total > 0 else rng.integers(len(P))
        centers.append(P[pick])
    centers = np.array(centers)
    labels = np.full(len(P), -1)
    for _ in range(iterations):
        dist = ((P[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dist.argmin(axis=1)
        if (new_labels == labels).all():
            break
        labels = new_labels
        for c in range(k):
            members = P[labels == c]
            if len(members):
                centers[c] = members.mean(axis=0)
    return labels, centers
