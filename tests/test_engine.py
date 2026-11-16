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
        assert "poster" in pt
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
    v0 = e.eff_M[0]
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

    # 5. Vector map excludes counterpart duplicate
    vm = e.get_vector_map()
    assert len(vm["points"]) == 1
    assert vm["points"][0]["id"] == "jf:1"

    # 6. eff_M bridges jf:1 to al:100's vector
    assert np.allclose(e.eff_M[e.ids.index("jf:1")], e.eff_M[e.ids.index("al:100")])


def test_bridge_uses_counterpart_vector(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "bridge.db")
    base = {"year": 2021, "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
            "score": 7.5, "tmdbid": None, "poster": None}
    s.upsert_rows([
        dict(base, id="jf:1", source="library", title="Bokutachi no Remake", title_native="ぼくたちのリメイク",
             format="series", owned=1, anilist_id=None),
        dict(base, id="al:100", source="anilist", title="Bokutachi no Remake", title_native="ぼくたちのリメイク",
             format="tv", owned=1, anilist_id=100),
        dict(base, id="al:200", source="anilist", title="Other", title_native="", format="tv", owned=0,
             anilist_id=200),
    ])
    s.save_embedding("jf:1", np.array([1, 0, 0, 0], dtype=np.float32).tobytes())
    s.save_embedding("al:100", np.array([0, 1, 0, 0], dtype=np.float32).tobytes())
    s.save_embedding("al:200", np.array([0, 0, 1, 0], dtype=np.float32).tobytes())
    e = Engine(s)
    assert np.allclose(e.eff_M[e.pos["jf:1"]], e.eff_M[e.pos["al:100"]])
    assert not np.allclose(e.eff_M[e.pos["jf:1"]], e.eff_M[e.pos["al:200"]])


def test_vectors_are_mean_centered(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "c.db")
    rng = np.random.default_rng(1)
    # All vectors share one large common direction, as text embeddings do
    common = np.array([5.0, 0, 0, 0])
    for i in range(8):
        v = (common + rng.normal(size=4)).astype(np.float32)
        s.upsert_rows([{"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": 0, "tmdbid": None,
                        "anilist_id": i, "poster": None}])
        s.save_embedding(f"al:{i}", v.tobytes())
    e = Engine(s)
    raw = e.M @ e.M.T
    centered = e.eff_M @ e.eff_M.T
    off = ~np.eye(8, dtype=bool)
    assert raw[off].mean() > 0.8
    assert abs(centered[off].mean()) < 0.3
    assert np.allclose(np.linalg.norm(e.eff_M, axis=1), 1.0, atol=1e-5)


def test_similarity_is_a_percentage(tmp_path):
    e, rows = make_engine(tmp_path)
    for r in e.similar_to("al:0", k=5):
        assert 0.0 <= r["similarity"] <= 100.0


def _engine_from(tmp_path, specs):
    """Build an engine from (id, vector, owned, tags, tag_ranks) tuples."""
    from anime_vec.store import Store
    s = Store(tmp_path / "x.db")
    for rid, vec, owned, tags, ranks in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": tags, "tag_ranks": ranks,
                        "studios": [], "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None}])
        s.save_embedding(rid, np.array(vec, dtype=np.float32).tobytes())
    return Engine(s)


def test_hybrid_prefers_a_liked_group_to_the_gap_between_groups(tmp_path):
    # Two groups of liked shows on different axes. The center is in the gap between them.
    specs = []
    for n in range(5):
        specs.append((f"al:{n}", [1, 0.01 * n, 0, 0, 0, 0], 1, [], []))
        specs.append((f"al:{5 + n}", [0, 0, 1, 0.01 * n, 0, 0], 1, [], []))
    specs += [
        ("al:20", [1, 0.025, 0, 0, 0, 0], 0, [], []),     # inside the first group
        ("al:21", [0.5, 0, 0.5, 0, 0, 0], 0, [], []),     # in the gap
        ("al:22", [0, 0, 0, 0, 1, 0], 0, [], []),
        ("al:23", [0, 0, 0, 0, 0, 1], 0, [], []),
        ("al:24", [0, 0, 0, 1, 0, 1], 0, [], []),
    ]
    e = _engine_from(tmp_path, specs)
    assert e.recommend(k=1, mode="center")[0]["id"] == "al:21"
    top = e.recommend(k=1, mode="hybrid")[0]
    assert top["id"] == "al:20"
    assert top["matched_favorite"] in {f"al:{n}" for n in range(5)}


def test_hybrid_uses_tags_and_tag_ranks(tmp_path):
    # al:10 and al:11 have the same embedding. Only al:10 shares the important tag of the liked show.
    specs = [
        ("al:1", [1, 0, 0, 0], 1, ["Band", "School"], [90, 20]),
        ("al:10", [0, 1, 0, 0], 0, ["Band", "Mecha"], [90, 20]),
        ("al:11", [0, 1, 0, 0], 0, ["Mecha", "School"], [90, 20]),
        ("al:12", [0, 0, 1, 0], 0, ["Space"], [80]),
        ("al:13", [0, 0, 0, 1], 0, ["Idol"], [80]),
    ]
    e = _engine_from(tmp_path, specs)
    ids = [r["id"] for r in e.recommend(k=4, mode="hybrid")]
    assert ids[0] == "al:10"
    assert ids.index("al:10") < ids.index("al:11")


def test_liked_shows_ignore_low_tiers(tmp_path):
    e, rows = make_engine(tmp_path)
    e.set_show_tier("al:0", "S")
    e.set_show_tier("al:1", "C")
    liked, w = e._liked()
    assert [e.ids[i] for i in liked] == ["al:0"]
    assert list(w) == [2.0]


def _franchise_engine(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "f.db")
    # al:10, al:11 and al:12 are one franchise. al:12 connects through al:99, which is not in the index.
    specs = [
        ("al:1", [1, 0, 0, 0], 1, []),
        ("al:10", [1, 0.02, 0, 0], 0, [11]),
        ("al:11", [1, 0.04, 0, 0], 0, [10, 99]),
        ("al:12", [1, 0.06, 0, 0], 0, [99]),
        ("al:20", [0.8, 0.6, 0, 0], 0, []),
        ("al:21", [0, 0, 1, 0], 0, []),
        ("al:22", [0, 0, 0, 1], 0, []),
    ]
    for rid, vec, owned, relations in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None, "relations": relations}])
        s.save_embedding(rid, np.array(vec, dtype=np.float32).tobytes())
    return Engine(s)


def test_franchise_groups_follow_relation_chains(tmp_path):
    e = _franchise_engine(tmp_path)
    assert e.franchise["al:10"] == e.franchise["al:11"] == e.franchise["al:12"]
    assert e.franchise["al:20"] != e.franchise["al:10"]
    assert e.franchise["al:21"] != e.franchise["al:22"]


def test_recommend_gives_one_result_for_each_franchise(tmp_path):
    e = _franchise_engine(tmp_path)
    same = {"al:10", "al:11", "al:12"}
    for kwargs in ({"mode": "hybrid"}, {"mode": "peak"}, {"mode": "diverse"}, {"mode": "center"},
                   {"seed_id": "al:1"}):
        ids = [r["id"] for r in e.recommend(k=4, **kwargs)]
        assert len(ids) == 4, kwargs
        assert len(same & set(ids)) == 1, kwargs


def test_recommend_marks_and_hides_owned_franchises(tmp_path):
    e = _franchise_engine(tmp_path)
    # al:1 is the only owned show. Put it in the franchise of al:10, al:11 and al:12.
    e.franchise["al:1"] = e.franchise["al:10"]
    for kwargs in ({"mode": "hybrid"}, {"mode": "peak"}, {"mode": "diverse"}, {"mode": "center"},
                   {"seed_id": "al:20"}):
        marked = {r["id"]: r["franchise_owned"] for r in e.recommend(k=10, **kwargs)}
        assert any(marked[i] for i in marked if i in ("al:10", "al:11", "al:12")), kwargs
        assert not marked.get("al:21", False), kwargs

        ids = [r["id"] for r in e.recommend(k=10, new_only=True, **kwargs)]
        assert ids, kwargs
        assert not {"al:10", "al:11", "al:12"} & set(ids), kwargs
        assert all(not r["franchise_owned"] for r in e.recommend(k=10, new_only=True, **kwargs)), kwargs


def _link_engine(tmp_path, extra=()):
    """al:1 is liked. al:10 and al:11 have the same embedding. AniList users link al:1 to al:10."""
    from anime_vec.store import Store
    s = Store(tmp_path / "links.db")
    specs = [
        ("al:1", [1, 0, 0, 0], 1, [[10, 80]]),
        ("al:10", [0, 1, 0, 0], 0, []),
        ("al:11", [0, 1, 0, 0], 0, []),
        ("al:12", [0, 0, 1, 0], 0, []),
        ("al:13", [0, 0, 0, 1], 0, [[12, 5]]),
    ] + list(extra)
    for rid, vec, owned, recommendations in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None,
                        "recommendations": recommendations}])
        s.save_embedding(rid, np.array(vec, dtype=np.float32).tobytes())
    return Engine(s)


def test_link_matrix_connects_franchises_in_two_directions(tmp_path):
    e = _link_engine(tmp_path)
    a, b, c = (e.row_fr[e.pos[i]] for i in ("al:1", "al:10", "al:11"))
    assert e.link_M[a, b] > 0 and e.link_M[a, b] == e.link_M[b, a]
    assert e.link_M[a, c] == 0


def test_hybrid_uses_the_user_recommendations(tmp_path):
    e = _link_engine(tmp_path)
    res = e.recommend(k=4, mode="hybrid")
    ids = [r["id"] for r in res]
    # al:10 and al:11 have the same content. Only the link is different.
    assert ids.index("al:10") < ids.index("al:11")
    by_id = {r["id"]: r for r in res}
    assert by_id["al:10"]["linked_favorite"] == "al:1"
    assert "linked_favorite" not in by_id["al:11"]


def test_hybrid_moves_shows_like_the_disliked_shows_down(tmp_path):
    # al:2 is owned and gets tier C. al:12 has the same embedding as al:2.
    e = _link_engine(tmp_path, extra=[("al:2", [0, 0, 1, 0], 1, [])])
    e.set_show_tier("al:1", "S")
    before = [r["id"] for r in e.recommend(k=4, mode="hybrid")]
    e.set_show_tier("al:2", "C")
    after = [r["id"] for r in e.recommend(k=4, mode="hybrid")]
    assert after.index("al:12") > before.index("al:12") or after[-1] == "al:12"
    assert after[-1] == "al:12"


def test_new_franchise_appears_as_its_first_tv_season(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "entry.db")
    # al:10 (TV, 2019), al:11 (movie, 2018) and al:12 (TV, 2021) are one franchise.
    # The movie and the later season are nearer to the liked show than the first season.
    specs = [
        ("al:1", [1, 0, 0, 0], 1, "tv", 2020, []),
        ("al:10", [0.6, 0.8, 0, 0], 0, "tv", 2019, [11, 12]),
        ("al:11", [1, 0.05, 0, 0], 0, "movie", 2018, [10]),
        ("al:12", [1, 0.1, 0, 0], 0, "tv", 2021, [10]),
        ("al:20", [0, 0, 1, 0], 0, "tv", 2020, []),
        ("al:21", [0, 0, 0, 1], 0, "tv", 2020, []),
    ]
    for rid, vec, owned, fmt, year, relations in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": year, "format": fmt, "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None, "relations": relations}])
        s.save_embedding(rid, np.array(vec, dtype=np.float32).tobytes())
    e = Engine(s)
    for mode in ("hybrid", "peak", "diverse", "center"):
        ids = [r["id"] for r in e.recommend(k=6, mode=mode)]
        assert "al:10" in ids and "al:11" not in ids and "al:12" not in ids, mode

    # After the user watches the first season, the other shows of the franchise are candidates again
    e.set_watched("al:10", True)
    ids = [r["id"] for r in e.recommend(k=6, mode="hybrid")]
    assert len({"al:11", "al:12"} & set(ids)) == 1
