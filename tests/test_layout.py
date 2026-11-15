import numpy as np
import pytest

from anime_vec import layout
from anime_vec.engine import Engine
from anime_vec.store import Store


def test_fit_unit_square_keeps_one_scale():
    P = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
    Q = layout.fit_unit_square(P)
    assert np.allclose(Q[:, 0].min(), 0.0) and np.allclose(Q[:, 0].max(), 1.0)
    # The short axis keeps its ratio of 1:2 and is in the middle of the square
    assert np.allclose(Q[:, 1].min(), 0.25) and np.allclose(Q[:, 1].max(), 0.75)


def test_pca_layout_finds_the_largest_axis():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 5)) * np.array([0.1, 9.0, 0.1, 3.0, 0.1])
    P = layout.pca_layout(X)
    assert P.shape == (200, 2)
    assert abs(np.corrcoef(P[:, 0], X[:, 1])[0, 1]) > 0.99
    assert abs(np.corrcoef(P[:, 1], X[:, 3])[0, 1]) > 0.99


def test_tsne_layout_keeps_groups_together():
    pytest.importorskip("sklearn")
    rng = np.random.default_rng(0)
    centers = rng.normal(size=(3, 20)) * 5
    labels = np.repeat(np.arange(3), 60)
    X = centers[labels] + rng.normal(size=(180, 20)) * 0.3
    P = layout.tsne_layout(X)
    assert P.shape == (180, 2)
    d = ((P[:, None, :] - P[None, :, :]) ** 2).sum(axis=2)
    np.fill_diagonal(d, np.inf)
    assert (labels[d.argmin(axis=1)] == labels).mean() > 0.95


def _store_with_rows(tmp_path, n, dim=8):
    s = Store(tmp_path / "l.db")
    rng = np.random.default_rng(0)
    for i in range(n):
        s.upsert_rows([{"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": 1 if i < 3 else 0,
                        "tmdbid": None, "anilist_id": i, "poster": None}])
        s.save_embedding(f"al:{i}", rng.normal(size=dim).astype(np.float32).tobytes())
    return s


def test_engine_caches_the_slow_layout(tmp_path, monkeypatch):
    calls = []

    def fake_tsne(X):
        calls.append(len(X))
        return layout.pca_layout(X)

    monkeypatch.setattr(layout, "can_use_tsne", lambda n: True)
    monkeypatch.setattr(layout, "tsne_layout", fake_tsne)
    s = _store_with_rows(tmp_path, 12)
    first = Engine(s).coords_2d
    second = Engine(s).coords_2d
    assert calls == [12]
    assert np.allclose(first, second)

    # New embeddings make the cache stale
    s.save_embedding("al:0", np.ones(8, dtype=np.float32).tobytes())
    Engine(s)
    assert calls == [12, 12]


def test_engine_layout_is_in_the_unit_square(tmp_path):
    e = Engine(_store_with_rows(tmp_path, 12))
    assert e.coords_2d.shape == (12, 2)
    assert e.coords_2d.min() >= 0.0 and e.coords_2d.max() <= 1.0
    x, y = e.center_2d()
    assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
