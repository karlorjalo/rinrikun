"""2D layout of the embedding space for the vector map."""
import numpy as np

# Change this value when the layout method changes. The cached layouts then become stale.
VERSION = "tsne-v3-grid"
# t-SNE needs more rows than its perplexity. Smaller indexes use PCA.
TSNE_MIN_ROWS = 100
TSNE_PERPLEXITY = 30
# The map gets region labels only when the index has this number of rows or more
REGION_MIN_ROWS = 200
REGION_COUNT = 14
# A region with less than this number of rows gets no label
REGION_MIN_SIZE = 15
# The grid of the close view: each show has its own cell, so that its poster never covers
# another poster. A cell is higher than wide, as a poster is.
CELL_ASPECT = 1.4
# The part of the map area that the cells of all shows fill. A smaller value keeps more room
# between the groups of the map, but then the largest zoom must be larger.
GRID_FILL = 0.5


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


def _cell_offsets(radius: int, dx: float, dy: float) -> list[tuple[int, int]]:
    """Return the cells around a cell, nearest first."""
    offsets = [(ox, oy) for ox in range(-radius, radius + 1) for oy in range(-radius, radius + 1)]
    offsets.sort(key=lambda o: (o[0] * dx) ** 2 + (o[1] * dy) ** 2)
    return offsets


def grid_layout(P: np.ndarray, order=None, passes: int = 6) -> tuple[np.ndarray, float, float]:
    """Give each point its own cell of a grid, near its position on the map.

    Return the centers of the cells, and the width and the height of a cell.

    The map puts similar shows near each other, and in a dense group the points are on top of
    each other. A poster for each point is then not possible. On the grid each show has its own
    place, so the close view of the map can show all posters. The interface uses the map
    positions for the far view and moves to the grid positions when the user zooms in.

    `order` gives the points that select their cell first. A point that selects late in a dense
    group gets a cell that is farther from its position.
    """
    P = np.asarray(P, dtype=np.float64)
    n = len(P)
    if n == 0:
        return P.astype(np.float32), 1.0, CELL_ASPECT
    dx = float(np.sqrt(GRID_FILL / (CELL_ASPECT * n)))
    dy = dx * CELL_ASPECT
    U = np.column_stack([P[:, 0] / dx, P[:, 1] / dy])  # the positions, in cells
    taken: dict[tuple[int, int], int] = {}
    where = np.zeros((n, 2), dtype=np.int64)
    radius = 16
    offsets = _cell_offsets(radius, dx, dy)
    for i in (range(n) if order is None else order):
        cx, cy = int(round(U[i, 0])), int(round(U[i, 1]))
        while True:
            key = next(((cx + ox, cy + oy) for ox, oy in offsets if (cx + ox, cy + oy) not in taken), None)
            if key is not None:
                break
            # All cells in the search area are taken: search a larger area
            radius *= 2
            offsets = _cell_offsets(radius, dx, dy)
        taken[key] = i
        where[i] = key

    def cost(i: int, c: tuple[int, int]) -> float:
        return ((U[i, 0] - c[0]) * dx) ** 2 + ((U[i, 1] - c[1]) * dy) ** 2

    # A point changes its cell with a point in an adjacent cell, or moves to an adjacent free
    # cell, if that makes the sum of the movements smaller
    adjacent = [(ox, oy) for ox in (-1, 0, 1) for oy in (-1, 0, 1) if (ox, oy) != (0, 0)]
    for _ in range(passes):
        changed = False
        for i in range(n):
            a = (int(where[i, 0]), int(where[i, 1]))
            for ox, oy in adjacent:
                b = (a[0] + ox, a[1] + oy)
                j = taken.get(b)
                if j is None:
                    if cost(i, b) < cost(i, a) - 1e-12:
                        del taken[a]
                        taken[b] = i
                        where[i] = b
                        a = b
                        changed = True
                elif cost(i, b) + cost(j, a) < cost(i, a) + cost(j, b) - 1e-12:
                    taken[a], taken[b] = j, i
                    where[i] = b
                    where[j] = a
                    a = b
                    changed = True
        if not changed:
            break
    G = np.column_stack([where[:, 0] * dx, where[:, 1] * dy])
    return G.astype(np.float32), dx, dy
