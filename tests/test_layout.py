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


def test_kmeans_finds_separate_groups():
    rng = np.random.default_rng(0)
    P = np.concatenate([rng.normal(size=(40, 2)) * 0.1, rng.normal(size=(40, 2)) * 0.1 + [5, 5]])
    labels, centers = layout.kmeans(P, 2)
    assert centers.shape == (2, 2)
    assert len(set(labels[:40])) == 1 and len(set(labels[40:])) == 1
    assert labels[0] != labels[40]


def test_regions_are_named_after_their_typical_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(layout, "REGION_MIN_ROWS", 10)
    monkeypatch.setattr(layout, "REGION_COUNT", 2)
    monkeypatch.setattr(layout, "REGION_MIN_SIZE", 3)
    s = Store(tmp_path / "regions.db")
    rng = np.random.default_rng(0)
    for i in range(20):
        band = i < 10
        vec = (np.array([1, 0, 0, 0] if band else [0, 1, 0, 0]) + rng.normal(size=4) * 0.02).astype(np.float32)
        s.upsert_rows([{"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": ["Band" if band else "Mecha", "School"],
                        "tag_ranks": [90, 40], "studios": [], "overview": "O", "score": 7.0, "owned": 0,
                        "tmdbid": None, "anilist_id": i, "poster": None}])
        s.save_embedding(f"al:{i}", vec.tobytes())
    e = Engine(s)
    regions = e.get_vector_map()["regions"]
    assert sorted(r["label"].split(" · ")[0] for r in regions) == ["Band", "Mecha"]
    assert all(0.0 <= r["x"] <= 1.0 and 0.0 <= r["y"] <= 1.0 and r["count"] == 10 for r in regions)
    # An area of 10 rows is too small for smaller areas
    assert all(r["level"] == 0 and np.isfinite(r["gx"]) and np.isfinite(r["gy"]) for r in regions)


def test_large_areas_are_divided_into_smaller_areas(tmp_path, monkeypatch):
    monkeypatch.setattr(layout, "REGION_MIN_ROWS", 10)
    monkeypatch.setattr(layout, "REGION_COUNT", 2)
    monkeypatch.setattr(layout, "REGION_MIN_SIZE", 3)
    monkeypatch.setattr(layout, "REGION_PART_SIZES", (10, 100))
    monkeypatch.setattr(layout, "REGION_MIN_PART", 3)
    s = Store(tmp_path / "areas.db")
    rng = np.random.default_rng(0)
    # Two large groups (music, robots). Each has two smaller groups.
    groups = [(["Band", "Music"], "Idol", [1, 0, 0.4]), (["Band", "Music"], "Rock", [1, 0, -0.4]),
              (["Mecha", "Sci-Fi"], "Space", [0, 1, 0.4]), (["Mecha", "Sci-Fi"], "War", [0, 1, -0.4])]
    n = 0
    for large, small, center in groups:
        for _ in range(10):
            vec = (np.array(center + [0]) + rng.normal(size=4) * 0.02).astype(np.float32)
            s.upsert_rows([{"id": f"al:{n}", "source": "anilist", "title": f"T{n}", "title_native": "",
                            "year": 2020, "format": "tv", "genres": [], "tags": large + [small, "School"],
                            "tag_ranks": [90, 90, 80, 40], "studios": [], "overview": "O", "score": 7.0, "owned": 0,
                            "tmdbid": None, "anilist_id": n, "poster": None}])
            s.save_embedding(f"al:{n}", vec.tobytes())
            n += 1
    regions = Engine(s).get_vector_map()["regions"]
    large = [r for r in regions if r["level"] == 0]
    small = [r for r in regions if r["level"] == 1]
    assert sorted(set(r["label"].split(" · ")) & {"Band", "Mecha"} == set() for r in large) == [False, False]
    assert all(r["count"] == 20 for r in large)
    # A smaller area has the tag that is special in its larger area, and not the tags of the larger area
    assert sorted(r["label"] for r in small) == ["Idol", "Rock", "Space", "War"]
    assert all(r["count"] == 10 for r in small)
    # The large areas are first in the list
    assert [r["level"] for r in regions] == [0, 0, 1, 1, 1, 1]


def test_small_index_has_no_regions(tmp_path):
    e = Engine(_store_with_rows(tmp_path, 12))
    assert e.get_vector_map()["regions"] == []


def test_grid_layout_gives_each_point_its_own_cell():
    rng = np.random.default_rng(0)
    # 300 points in three dense groups: many points are at almost the same position
    P = np.concatenate([rng.normal(loc=c, scale=0.01, size=(100, 2)) for c in ((0.2, 0.2), (0.8, 0.3), (0.5, 0.8))])
    G, dx, dy = layout.grid_layout(P)
    assert dy == pytest.approx(dx * layout.CELL_ASPECT)
    assert dx * dy * len(P) == pytest.approx(layout.GRID_FILL)
    cells = {(round(float(x) / dx), round(float(y) / dy)) for x, y in G}
    assert len(cells) == len(P)
    # Each point stays near its group: the movement is some cells, not the width of the map
    move = np.sqrt(((G - P) ** 2).sum(axis=1))
    assert move.max() < 12 * dy
    # The groups stay separate
    assert G[:100, 0].max() < G[100:200, 0].min()


def test_grid_layout_keeps_separate_points_in_their_nearest_cell():
    P = np.array([[0.1, 0.1], [0.5, 0.5], [0.9, 0.2], [0.3, 0.8]])
    G, dx, dy = layout.grid_layout(P)
    assert (np.abs(G[:, 0] - P[:, 0]) <= dx / 2 + 1e-6).all()
    assert (np.abs(G[:, 1] - P[:, 1]) <= dy / 2 + 1e-6).all()


def test_grid_layout_order_gives_the_first_point_the_nearest_cell():
    P = np.array([[0.5, 0.5]] * 5 + [[0.0, 0.0], [1.0, 1.0]])
    G, dx, dy = layout.grid_layout(P, order=[3, 0, 1, 2, 4, 5, 6], passes=0)
    move = np.sqrt(((G - P) ** 2).sum(axis=1))
    assert move[3] == move[:5].min()
    assert len({(round(float(x) / dx), round(float(y) / dy)) for x, y in G}) == 7


def test_grid_layout_of_no_points():
    G, dx, dy = layout.grid_layout(np.zeros((0, 2)))
    assert G.shape == (0, 2)


def test_engine_gives_the_grid_in_the_map_data(tmp_path, monkeypatch):
    calls = []

    def fake_tsne(X):
        calls.append(len(X))
        return layout.pca_layout(X)

    monkeypatch.setattr(layout, "can_use_tsne", lambda n: True)
    monkeypatch.setattr(layout, "tsne_layout", fake_tsne)
    s = _store_with_rows(tmp_path, 12)
    e = Engine(s)
    vm = e.get_vector_map()
    assert vm["cell"]["h"] == pytest.approx(vm["cell"]["w"] * layout.CELL_ASPECT)
    cells = {(round(p["gx"] / vm["cell"]["w"]), round(p["gy"] / vm["cell"]["h"])) for p in vm["points"]}
    assert len(cells) == 12
    # The second engine reads the map and the grid from the database
    again = Engine(s)
    assert calls == [12]
    assert np.allclose(again.grid_2d, e.grid_2d) and again.cell == pytest.approx(e.cell)


def test_owned_shows_select_their_grid_cell_first(tmp_path, monkeypatch):
    seen = {}
    real = layout.grid_layout

    def spy(P, order=None, passes=6):
        seen["order"] = list(order)
        return real(P, order, passes)

    monkeypatch.setattr(layout, "grid_layout", spy)
    s = _store_with_rows(tmp_path, 12)
    s.set_weight("al:2", "S")
    s.set_weight("al:0", "B")
    e = Engine(s)
    first = [e.ids[i] for i in seen["order"][:3]]
    # The owned shows are al:0, al:1 and al:2: the S tier, then the B tier, then the show without a tier
    assert first == ["al:2", "al:0", "al:1"]
    assert sorted(seen["order"]) == list(range(12))
