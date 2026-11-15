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


def test_recommend_modes(tmp_path):
    e, rows = make_engine(tmp_path)
    # Rate al:0 as S, al:1 as D
    e.set_show_tier("al:0", "S")
    e.set_show_tier("al:1", "D")

    for mode in ["hybrid", "peak", "diverse", "center"]:
        res = e.recommend(k=2, mode=mode)
        assert len(res) == 2
        assert all(not r["owned"] for r in res)
        assert all(r["similarity"] <= 100.0 for r in res)

    # In peak mode, matched_favorite should be the S-tier show title
    peak_res = e.recommend(k=2, mode="peak")
    assert all("matched_favorite" in r for r in peak_res)
    assert peak_res[0]["matched_favorite"] == "T0"


def test_vector_map(tmp_path):
    e, rows = make_engine(tmp_path)
    vm = e.get_vector_map()
    assert "points" in vm
    assert len(vm["points"]) == len(rows)
    assert "center" in vm
    for pt in vm["points"]:
        assert 0.0 <= pt["x"] <= 1.0
        assert 0.0 <= pt["y"] <= 1.0
        assert "title" in pt
        assert "owned" in pt

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


def test_defining_shows_weighted_preference(tmp_path):
    e, rows = make_engine(tmp_path)
    # Owned shows: al:0, al:1, al:2
    # Rate al:0 as S (2.0), al:1 as C (0.3), leave al:2 unrated
    e.set_show_tier("al:0", "S")
    e.set_show_tier("al:1", "C")
    res = e.defining_shows(k=2)
    # al:0 (S tier) must be #1
    assert res[0]["id"] == "al:0"
    assert res[0]["tier"] == "S"
    # al:1 (C tier) must be excluded; al:2 (unrated fallback) takes the second slot
    assert res[1]["id"] == "al:2"
    assert all(r["id"] != "al:1" for r in res)

    # Now rate al:2 as A (1.5)
    e.set_show_tier("al:2", "A")
    res2 = e.defining_shows(k=2)
    assert [r["id"] for r in res2] == ["al:0", "al:2"]
    assert res2[0]["tier"] == "S"
    assert res2[1]["tier"] == "A"

def test_unknown_id_raises(tmp_path):
    e, rows = make_engine(tmp_path)
    with pytest.raises(ValueError):
        e.similar_to("al:999", k=1)


def test_genre_and_era_summaries(tmp_path):
    e, rows = make_engine(tmp_path)
    genres = e.owned_genre_summary(k=5)
    assert genres == [("Drama", 3)]
    eras = e.owned_era_summary()
    assert eras == [("2020s", 3)]


def test_engine_manual_watched(tmp_path):
    e, rows = make_engine(tmp_path)
    # al:3 is originally unowned
    assert not e.by_id["al:3"]["owned"]
    assert len(e.manual_shows()) == 0
    e.set_watched("al:3", watched=True)
    assert e.by_id["al:3"]["owned"] == 1
    assert e.by_id["al:3"]["manual_watched"] == 1
    manuals = e.manual_shows()
    assert len(manuals) == 1
    assert manuals[0]["id"] == "al:3"
    # Unmark
    e.set_watched("al:3", watched=False)
    assert e.by_id["al:3"]["owned"] == 0
    assert len(e.manual_shows()) == 0


def test_weighted_taste_center_and_tiers(tmp_path):
    e, rows = make_engine(tmp_path)
    # Owned rows are al:0, al:1, al:2
    initial_center = e.taste_center()
    e.set_show_tier("al:0", "S") # weight 2.0
    e.set_show_tier("al:1", "D") # weight 0.0
    new_center = e.taste_center()
    # al:0 should have higher similarity to new_center than to initial_center
    v0 = e.M[0]
    assert (v0 @ new_center) > (v0 @ initial_center)
    # summary
    ts = e.tier_summary()
    assert ts["S"] == 1
    assert ts["D"] == 1
    assert ts["unrated"] == 1
    # review queue
    rq = e.review_queue(unrated_only=True)
    assert len(rq) == 1
    assert rq[0]["id"] == "al:2"
    # rated shows
    rated = e.rated_shows()
    assert len(rated) == 2
    assert rated[0]["id"] == "al:0" and rated[0]["tier"] == "S"
    assert rated[1]["id"] == "al:1" and rated[1]["tier"] == "D"
    # reset tier
    e.set_show_tier("al:0", None)
    assert e.by_id["al:0"]["tier"] is None


def test_deduplicate_library_and_pool_counterparts(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "dedup.db")
    v = np.ones(4, dtype=np.float32) / 2
    # Jellyfin row
    s.upsert_rows([{
        "id": "jf:1", "source": "library", "title": "Bokutachi no Remake", "title_native": "ぼくたちのリメイク",
        "year": 2021, "format": "series", "genres": [], "tags": [], "tag_ranks": [], "studios": [],
        "overview": "O", "score": 7.5, "owned": 1, "tmdbid": "1", "anilist_id": None, "poster": None,
    }])
    # AniList row matching the same show, flagged owned=1 by build.py
    s.upsert_rows([{
        "id": "al:100", "source": "anilist", "title": "Bokutachi no Remake", "title_native": "ぼくたちのリメイク",
        "year": 2021, "format": "tv", "genres": [], "tags": [], "tag_ranks": [], "studios": [],
        "overview": "O", "score": 7.5, "owned": 1, "tmdbid": None, "anilist_id": 100, "poster": None,
    }])
    s.save_embedding("jf:1", v.tobytes())
    s.save_embedding("al:100", v.tobytes())

    e = Engine(s)
    # 1. owned_idx should only contain the primary library row (len 1, not 2)
    assert len(e.owned_idx) == 1
    assert e.ids[e.owned_idx[0]] == "jf:1"

    # 2. review queue should only contain 1 item
    rq = e.review_queue(unrated_only=False)
    assert len(rq) == 1
    assert rq[0]["id"] == "jf:1"

    # 3. Rating jf:1 sets tier on both jf:1 and al:100
    e.set_show_tier("jf:1", "S")
    assert e.by_id["jf:1"]["tier"] == "S"
    assert e.by_id["al:100"]["tier"] == "S"
    assert len(e.rated_shows()) == 1

    # 4. Rating al:100 updates jf:1
    e.set_show_tier("al:100", "A")
    assert e.by_id["jf:1"]["tier"] == "A"
    assert e.by_id["al:100"]["tier"] == "A"
