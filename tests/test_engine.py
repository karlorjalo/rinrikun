import numpy as np
import pytest
from anime_vec.engine import Engine


def make_engine(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "e.db")
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(6, 4)).astype(np.float32)
    rows = []
    for i, v in enumerate(vecs):
        v = v / np.linalg.norm(v)
        rows.append({"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
                     "year": 2020, "format": "tv", "genres": ["Drama"], "tags": ["School"],
                     "tag_ranks": [50], "studios": ["S"], "overview": "O", "score": 7.0,
                     "owned": 1 if i < 3 else 0, "tmdbid": None, "anilist_id": i, "poster": None})
        s.upsert_rows([rows[-1]])
        s.save_embedding(rows[-1]["id"], v.astype(np.float32).tobytes())
    return Engine(s), rows


def test_similar_excludes_self_and_ranks(tmp_path):
    e, rows = make_engine(tmp_path)
    res = e.similar_to("al:0", k=2)
    assert len(res) == 2 and all(r["id"] != "al:0" for r in res)
    assert res[0]["similarity"] >= res[1]["similarity"]

def test_center_is_owned_mean(tmp_path):
    e, rows = make_engine(tmp_path)
    c = e.taste_center()
    assert c.shape == (4,) and abs(np.linalg.norm(c) - 1) < 1e-5

def test_recommend_excludes_owned(tmp_path):
    e, rows = make_engine(tmp_path)
    res = e.recommend(k=3)
    assert len(res) == 3
    assert all(not r["owned"] for r in res)
    assert all(r["similarity"] <= 100.0 for r in res)

def test_recommend_excludes_seed(tmp_path):
    e, rows = make_engine(tmp_path)
    res = e.recommend(k=10, seed_id="al:4")
    assert res, "expected results"
    assert all(r["id"] != "al:4" for r in res)

def test_shared_tags(tmp_path):
    e, rows = make_engine(tmp_path)
    res = e.similar_to("al:0", k=1)
    assert "shared_tags" in res[0]

def test_empty_owned_center_raises(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "z.db")
    import numpy as np
    v = np.ones(4, dtype=np.float32) / 2
    s.upsert_rows([{"id": "al:0", "source": "anilist", "title": "T", "title_native": "",
                    "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                    "studios": [], "overview": "O", "score": 7.0, "owned": 0, "tmdbid": None,
                    "anilist_id": 0, "poster": None}])
    s.save_embedding("al:0", v.tobytes())
    e = Engine(s)
    with pytest.raises(RuntimeError):
        e.taste_center()

def test_k_zero_returns_empty(tmp_path):
    e, rows = make_engine(tmp_path)
    assert e.similar_to("al:0", k=0) == []
    assert e.recommend(k=0) == []

def test_defining_shows_owned_only(tmp_path):
    e, rows = make_engine(tmp_path)
    res = e.defining_shows(k=2)
    assert len(res) == 2
    assert all(r["owned"] for r in res)

def test_unknown_id_raises(tmp_path):
    e, rows = make_engine(tmp_path)
    with pytest.raises(ValueError):
        e.similar_to("al:999", k=1)
