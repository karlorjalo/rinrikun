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

    for mode in ["hybrid", "diverse"]:
        res = e.recommend(k=2, mode=mode)
        assert len(res) == 2
        assert all(not r["owned"] for r in res)
        assert all(r["similarity"] <= 100.0 for r in res)

    # The only liked show is the S-tier show, thus it is the matched favorite of each result
    res = e.recommend(k=2, mode="hybrid")
    assert all(r["matched_favorite"] == "T0" for r in res)


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
        assert pt["score"] == 7.0

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

def test_unknown_id_raises(tmp_path):
    e, rows = make_engine(tmp_path)
    with pytest.raises(ValueError):
        e.similar_to("al:999", k=1)


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
    assert e.set_show_tier("jf:1", "S") == {"id": "jf:1", "tier": "S", "weight": 2.0, "ids": ["jf:1", "al:100"]}
    assert e.by_id["jf:1"]["tier"] == "S"
    assert e.by_id["al:100"]["tier"] == "S"
    assert len(e.rated_shows()) == 1

    # 4. Rating al:100 updates jf:1. The answer names jf:1, which is the point on the map.
    assert e.set_show_tier("al:100", "A")["ids"] == ["al:100", "jf:1"]
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
    center = e.taste_center()
    assert e.eff_M[e.pos["al:21"]] @ center > e.eff_M[e.pos["al:20"]] @ center
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
    for kwargs in ({"mode": "hybrid"}, {"mode": "diverse"}, {"seed_id": "al:1"}):
        ids = [r["id"] for r in e.recommend(k=4, **kwargs)]
        assert len(ids) == 4, kwargs
        assert len(same & set(ids)) == 1, kwargs


def test_recommend_marks_and_hides_owned_franchises(tmp_path):
    e = _franchise_engine(tmp_path)
    # al:1 is the only owned show. Put it in the franchise of al:10, al:11 and al:12.
    e.franchise["al:1"] = e.franchise["al:10"]
    for kwargs in ({"mode": "hybrid"}, {"mode": "diverse"}, {"seed_id": "al:20"}):
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
    assert e.link_weight(a, b) > 0 and e.link_weight(a, b) == e.link_weight(b, a)
    assert e.link_weight(a, c) == 0


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
    for mode in ("hybrid", "diverse"):
        ids = [r["id"] for r in e.recommend(k=6, mode=mode)]
        assert "al:10" in ids and "al:11" not in ids and "al:12" not in ids, mode

    # After the user watches the first season, the other shows of the franchise are candidates again
    e.set_watched("al:10", True)
    ids = [r["id"] for r in e.recommend(k=6, mode="hybrid")]
    assert len({"al:11", "al:12"} & set(ids)) == 1


def test_library_row_with_two_seasons_by_id(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "seasons.db")
    base = {"genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O", "score": 7.0,
            "tmdbid": None, "poster": None}
    rows = [
        dict(base, id="jf:1", source="library", title="ライブラリ", title_native="ライブラリ", year=2020,
             format="series", owned=1, anilist_id=None),
        # The titles are different from the library title: only the link connects them
        dict(base, id="al:11", source="anilist", title="Show 2nd Season", title_native="", year=2021,
             format="tv", owned=1, anilist_id=11, library_id="jf:1"),
        dict(base, id="al:10", source="anilist", title="Show", title_native="", year=2019,
             format="tv", owned=1, anilist_id=10, library_id="jf:1"),
        dict(base, id="al:20", source="anilist", title="Other", title_native="", year=2020,
             format="tv", owned=0, anilist_id=20),
        dict(base, id="al:21", source="anilist", title="Other 2", title_native="", year=2020,
             format="tv", owned=0, anilist_id=21),
    ]
    vectors = {"jf:1": [1, 0, 0, 0], "al:10": [0, 1, 0, 0], "al:11": [0, 0.9, 0.1, 0],
               "al:20": [0, 0, 1, 0], "al:21": [0, 0, 0, 1]}
    for r in rows:
        s.upsert_rows([r])
        s.save_embedding(r["id"], np.array(vectors[r["id"]], dtype=np.float32).tobytes())
    e = Engine(s)
    assert e.duplicate_of == {"al:10": "jf:1", "al:11": "jf:1"}
    # The first counterpart is the first season
    assert e.counterparts["jf:1"] == ["al:10", "al:11"]
    assert [e.ids[i] for i in e.owned_idx] == ["jf:1"]
    assert np.allclose(e.eff_M[e.pos["jf:1"]], e.eff_M[e.pos["al:10"]])
    assert {r["id"] for r in e.recommend(k=10)} == {"al:20", "al:21"}
    # A tier on the library row goes to the two seasons
    e.set_show_tier("jf:1", "S")
    assert e.by_id["al:10"]["tier"] == "S" and e.by_id["al:11"]["tier"] == "S"


def test_unreleased_shows_are_not_recommended(tmp_path):
    e = _franchise_engine(tmp_path)
    ids = {r["id"] for r in e.recommend(k=10)}
    assert "al:20" in ids
    e.by_id["al:20"]["status"] = "NOT_YET_RELEASED"
    assert "al:20" not in {r["id"] for r in e.recommend(k=10)}
    assert "al:20" not in {r["id"] for r in e.recommend(k=10, seed_id="al:1")}
    e.by_id["al:20"]["status"] = "FINISHED"
    assert "al:20" in {r["id"] for r in e.recommend(k=10)}


def test_manually_watched_pool_row_is_one_show_with_its_library_row(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "manual_dup.db")
    base = {"genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O", "score": 7.0,
            "tmdbid": None, "poster": None, "year": 2015}
    rows = [
        dict(base, id="jf:1", source="library", title="ライブラリ", title_native="ライブラリ", format="series",
             owned=1, anilist_id=None),
        dict(base, id="al:10", source="anilist", title="Show", title_native="", format="tv", owned=1,
             anilist_id=10, library_id="jf:1"),
        dict(base, id="al:20", source="anilist", title="Other", title_native="", format="tv", owned=0, anilist_id=20),
        dict(base, id="al:30", source="anilist", title="Third", title_native="", format="tv", owned=0, anilist_id=30),
    ]
    for n, r in enumerate(rows):
        s.upsert_rows([r])
        s.save_embedding(r["id"], np.eye(4, dtype=np.float32)[n].tobytes())
    # Before the library had the show, the user marked the two pool rows as watched and gave a tier
    s.set_manual_watched("al:10", True)
    s.set_manual_watched("al:30", True)
    s.set_weight("al:10", "S")
    e = Engine(s)
    assert e.duplicate_of == {"al:10": "jf:1"}
    assert [e.ids[i] for i in e.owned_idx] == ["al:30", "jf:1"]
    # The tier of the pool row goes to the library row, and the show is in the lists one time
    assert e.by_id["jf:1"]["tier"] == "S"
    assert [r["id"] for r in e.rated_shows()] == ["jf:1"]
    assert [r["id"] for r in e.manual_shows()] == ["al:30"]
    assert [p["id"] for p in e.get_vector_map()["points"] if p["owned"]] == ["al:30", "jf:1"]


def _status_engine(tmp_path, specs):
    """Build an engine from (id, source, format, year, status, owned, relations, library_id) tuples."""
    from anime_vec.store import Store
    s = Store(tmp_path / "status_entry.db")
    for n, (rid, source, fmt, year, status, owned, relations, library_id) in enumerate(specs):
        s.upsert_rows([{"id": rid, "source": source, "title": rid, "title_native": "", "year": year,
                        "format": fmt, "genres": [], "tags": [], "tag_ranks": [], "studios": [],
                        "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]) if source == "anilist" else None,
                        "poster": None, "relations": relations, "status": status, "library_id": library_id}])
        vec = np.zeros(8, dtype=np.float32)
        vec[n % 8] = 1.0
        vec[(n + 3) % 8] = 0.1 * n
        s.save_embedding(rid, vec.tobytes())
    return Engine(s)


def test_unreleased_tv_sequel_is_not_the_entry_point(tmp_path):
    # The franchise of al:10 has a released movie and an announced TV series
    e = _status_engine(tmp_path, [
        ("al:1", "anilist", "tv", 2020, "FINISHED", 1, [], None),
        ("al:10", "anilist", "tv", None, "NOT_YET_RELEASED", 0, [11], None),
        ("al:11", "anilist", "movie", 2021, "FINISHED", 0, [10], None),
        ("al:20", "anilist", "tv", 2019, "FINISHED", 0, [], None),
    ])
    assert e.ids[e.entry_row[e.franchise["al:10"]]] == "al:11"
    ids = {r["id"] for r in e.recommend(k=10)}
    assert "al:11" in ids and "al:10" not in ids


def test_hidden_library_series_with_an_announced_sequel_is_found(tmp_path):
    from anime_vec.evaluation import rank_of_hidden
    # The library has the first season. AniList also has an announced second season.
    e = _status_engine(tmp_path, [
        ("jf:1", "library", "series", 2022, None, 1, [], None),
        ("al:10", "anilist", "tv", 2022, "FINISHED", 1, [11], "jf:1"),
        ("al:11", "anilist", "tv", None, "NOT_YET_RELEASED", 0, [10], None),
        ("al:2", "anilist", "tv", 2020, "FINISHED", 1, [], None),
        ("al:20", "anilist", "tv", 2019, "FINISHED", 0, [], None),
        ("al:21", "anilist", "tv", 2018, "FINISHED", 0, [], None),
    ])
    assert e.franchise["jf:1"] == e.franchise["al:11"]
    assert e.ids[e.entry_row[e.franchise["jf:1"]]] == "jf:1"
    rank, length = rank_of_hidden(e, "jf:1")
    assert rank < length


def _tier_engine(tmp_path, monkeypatch):
    """The user rated band shows S and mecha shows C. All shows have different, unrelated embeddings."""
    import anime_vec.engine as engine_module
    from anime_vec.store import Store
    monkeypatch.setattr(engine_module, "TIER_MODEL_MIN_RATED", 4)
    s = Store(tmp_path / "tier.db")
    specs = [(f"al:{n}", 1, ["Band"], "S") for n in range(1, 5)]
    specs += [(f"al:{n}", 1, ["Mecha"], "C") for n in range(5, 9)]
    specs += [("al:20", 0, ["Band"], None), ("al:21", 0, ["Mecha"], None), ("al:22", 0, ["Idol"], None),
              ("al:23", 0, ["Sports"], None)]
    rng = np.random.default_rng(3)
    for rid, owned, tags, tier in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": tags, "tag_ranks": [90], "studios": [],
                        "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None}])
        s.save_embedding(rid, rng.normal(size=16).astype(np.float32).tobytes())
        if tier:
            s.set_weight(rid, tier)
    return Engine(s)


def test_tier_model_learns_the_tags_of_the_high_and_the_low_tiers(tmp_path, monkeypatch):
    e = _tier_engine(tmp_path, monkeypatch)
    band, mecha, idol = e._predicted_tier([e.pos["al:20"], e.pos["al:21"], e.pos["al:22"]])
    assert band > idol > mecha
    # A show with tags that the user never rated gets the mean tier
    assert idol == pytest.approx(2.5, abs=0.01)


def test_tier_model_needs_enough_ratings(tmp_path):
    e = _engine_from(tmp_path, [("al:1", [1, 0, 0, 0], 1, ["Band"], [90]), ("al:10", [0, 1, 0, 0], 0, ["Band"], [90])])
    e.set_show_tier("al:1", "S")
    assert list(e._predicted_tier([e.pos["al:10"]])) == [0.0]


def test_tier_penalty_moves_a_low_prediction_down_and_gives_no_bonus(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    e = _tier_engine(tmp_path, monkeypatch)
    # Without the other terms that use the low tiers, only the tier penalty can change the order
    monkeypatch.setattr(engine_module, "DISLIKE_WEIGHT", 0.0)
    monkeypatch.setattr(engine_module, "TIER_PENALTY", 0.0)
    before = [r["id"] for r in e.recommend(k=4)]
    monkeypatch.setattr(engine_module, "TIER_PENALTY", 5.0)
    after = [r["id"] for r in e.recommend(k=4)]
    assert after[-1] == "al:21"
    # The other shows keep their order: the show with the high prediction does not move up
    assert [i for i in after if i != "al:21"] == [i for i in before if i != "al:21"]


def _dismiss_engine(tmp_path):
    # al:10 and al:11 are almost the same show. al:12 is a different show that the user can also like.
    return _engine_from(tmp_path, [
        ("al:1", [1, 0, 0, 0], 1, ["Band"], [90]),
        ("al:10", [0.9, 0.31, 0, 0], 0, ["Band", "Idol"], [90, 80]),
        ("al:11", [0.9, 0.3, 0, 0], 0, ["Band", "Idol"], [90, 80]),
        ("al:12", [0.6, 0, 0.8, 0], 0, ["Band", "Sports"], [90, 80]),
        ("al:13", [0, 0, 0, 1], 0, ["Mecha"], [90]),
    ])


def test_dismissed_show_is_not_recommended(tmp_path):
    e = _dismiss_engine(tmp_path)
    assert e.by_id["al:10"]["dismissed"] == 0
    e.set_dismissed("al:10", True)
    assert e.by_id["al:10"]["dismissed"] == 1
    for kwargs in ({"mode": "hybrid"}, {"mode": "diverse"}, {"seed_id": "al:11"}, {"mode": "hybrid", "new_only": True}):
        assert "al:10" not in {r["id"] for r in e.recommend(k=10, **kwargs)}, kwargs
    assert [r["id"] for r in e.dismissed_shows()] == ["al:10"]
    # The choice stays after a restart
    again = Engine(e.store)
    assert again.dismissed == {"al:10"}
    assert "al:10" not in {r["id"] for r in again.recommend(k=10)}
    # The user can put the show back
    e.set_dismissed("al:10", False)
    assert "al:10" in {r["id"] for r in e.recommend(k=10)}
    assert e.dismissed_shows() == []
    with pytest.raises(KeyError):
        e.set_dismissed("al:999", True)


def test_dismissed_show_counts_as_a_dislike(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    monkeypatch.setattr(engine_module, "DISLIKE_WEIGHT", 5.0)
    e = _dismiss_engine(tmp_path)
    before = [r["id"] for r in e.recommend(k=10)]
    assert before.index("al:11") < before.index("al:12")
    e.set_dismissed("al:10", True)
    after = [r["id"] for r in e.recommend(k=10)]
    # al:11 is almost the same show as the removed al:10, thus it is below al:12 now
    assert after.index("al:12") < after.index("al:11")


def test_dismissed_show_is_a_low_tier_example_for_the_tier_model(tmp_path, monkeypatch):
    e = _tier_engine(tmp_path, monkeypatch)
    idol = e.pos["al:22"]
    assert e._predicted_tier([idol])[0] == pytest.approx(2.5, abs=0.01)
    e.set_dismissed("al:22", True)
    assert e._predicted_tier([idol])[0] < 2.4
    # An owned show is not a dismissed example
    e.set_dismissed("al:1", True)
    assert e._dismissed_rows() == [idol]


def test_link_weight_is_smaller_for_shows_with_many_links(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "degree.db")
    # al:1 has one link of rating 10. al:2 has the same link to al:3 and nine more links.
    specs = [("al:1", [[3, 10]]), ("al:2", [[3, 10]] + [[n, 10] for n in range(10, 19)]), ("al:3", [])]
    specs += [(f"al:{n}", []) for n in range(10, 19)]
    for n, (rid, recommendations) in enumerate(specs):
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": [], "tag_ranks": [], "studios": [],
                        "overview": "O", "score": 7.0, "owned": 0, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None, "recommendations": recommendations}])
        vec = np.zeros(16, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(rid, vec.tobytes())
    e = Engine(s)
    f = {rid: int(e.row_fr[e.pos[rid]]) for rid, _ in specs}
    assert e.link_weight(f["al:1"], f["al:3"]) > e.link_weight(f["al:2"], f["al:3"]) > 0
    # degree of al:1 is 10, of al:3 is 20: weight = 10 / sqrt(10 * 20)
    assert e.link_weight(f["al:1"], f["al:3"]) == pytest.approx(10 / (200 ** 0.5), rel=1e-5)


def test_music_video_is_not_recommended(tmp_path):
    # The franchise of al:10 has a music video (the earliest entry) and a movie
    e = _status_engine(tmp_path, [
        ("al:1", "anilist", "tv", 2020, "FINISHED", 1, [], None),
        ("al:10", "anilist", "music", 2015, "FINISHED", 0, [11], None),
        ("al:11", "anilist", "movie", 2021, "FINISHED", 0, [10], None),
        ("al:20", "anilist", "music", 2019, "FINISHED", 0, [], None),
        ("al:21", "anilist", "tv", 2019, "FINISHED", 0, [], None),
    ])
    assert e.ids[e.entry_row[e.franchise["al:10"]]] == "al:11"
    for kwargs in ({"mode": "hybrid"}, {"mode": "diverse"}, {"seed_id": "al:1"}):
        ids = {r["id"] for r in e.recommend(k=10, **kwargs)}
        assert ids == {"al:11", "al:21"}, kwargs
    # A music video is still in the index: the map and the search have it
    assert "al:20" in {p["id"] for p in e.get_vector_map()["points"]}


def _kind_engine(tmp_path):
    """Build an engine with a library of TV series from about 2020, and candidates of other kinds.

    All candidates have the same vector, thus only the kind of a candidate can change its position.
    """
    from anime_vec.store import Store
    s = Store(tmp_path / "kinds.db")
    specs = [
        # id, owned, format, year, episodes, score
        (1, 1, "tv", 2020, 12, 7.6), (2, 1, "tv", 2021, 12, 7.4), (3, 1, "tv", 2022, 13, 7.8), (4, 1, "tv", 2020, 24, 7.5),
        (10, 0, "tv", 2021, 12, 7.6), (11, 0, "movie", 1985, 1, 5.5), (12, 0, "ova", 1995, 2, 6.2),
        (13, 0, "tv", 2021, 13, 7.4), (14, 0, "tv", None, None, None),
    ]
    for rid, owned, fmt, year, episodes, score in specs:
        s.upsert_rows([{"id": f"al:{rid}", "source": "anilist", "title": f"T{rid}", "title_native": "", "year": year,
                        "format": fmt, "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
                        "score": score, "owned": owned, "tmdbid": None, "anilist_id": rid, "poster": None,
                        "episodes": episodes}])
        vec = np.zeros(4, dtype=np.float32)
        vec[0 if owned else 1] = 1.0
        s.save_embedding(f"al:{rid}", vec.tobytes())
    return Engine(s)


def test_kind_score_is_high_for_the_kinds_of_the_library(tmp_path):
    e = _kind_engine(tmp_path)
    cands = [e.pos[f"al:{i}"] for i in (10, 11, 12, 13, 14)]
    usual_a, movie, ova, usual_b, unknown = e._kind_score(cands, e.owned_franchises())
    assert min(usual_a, usual_b) > unknown > max(movie, ova)
    # A property that is not known gives the mean value: al:14 is a TV series without other data
    assert np.isfinite(unknown)
    # No library: all rows get 0
    assert not e._kind_score(cands, set()).any()


def test_usual_kinds_formula_moves_the_usual_kinds_up(tmp_path):
    e = _kind_engine(tmp_path)
    usual = [r["id"] for r in e.recommend(k=5, kinds="usual")]
    assert set(usual[:2]) == {"al:10", "al:13"}
    assert set(usual[3:]) == {"al:11", "al:12"}
    # The two formulas give the same shows. "all" is the default.
    assert {r["id"] for r in e.recommend(k=5)} == set(usual)
    assert [r["id"] for r in e.recommend(k=5)] == [r["id"] for r in e.recommend(k=5, kinds="all")]
    # "More variety" also uses the formula
    assert e.recommend(k=1, mode="diverse", kinds="usual")[0]["id"] in ("al:10", "al:13")
    with pytest.raises(ValueError):
        e.recommend(k=5, kinds="other")


def test_seeded_list_ignores_the_kinds(tmp_path):
    e = _kind_engine(tmp_path)
    assert ([r["id"] for r in e.recommend(k=5, seed_id="al:1", kinds="usual")]
            == [r["id"] for r in e.recommend(k=5, seed_id="al:1")])


def test_hidden_franchise_test_uses_the_kinds(tmp_path):
    from anime_vec.evaluation import rank_of_hidden
    e = _kind_engine(tmp_path)
    # The hidden show al:1 is a TV series from 2020: the "usual kinds" formula puts it above the
    # movie and the OVA
    rank, length = rank_of_hidden(e, "al:1", kinds="usual")
    assert length == 6 and rank <= 3


def test_a_higher_crowd_score_gives_no_advantage(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "crowd.db")
    specs = [(1, 1, 7.0), (2, 1, 7.2), (3, 1, 6.6), (10, 0, 6.6), (11, 0, 8.9), (12, 0, 6.4), (13, 0, 5.0)]
    for rid, owned, score in specs:
        s.upsert_rows([{"id": f"al:{rid}", "source": "anilist", "title": f"T{rid}", "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
                        "score": score, "owned": owned, "tmdbid": None, "anilist_id": rid, "poster": None,
                        "episodes": 12}])
        vec = np.zeros(4, dtype=np.float32)
        vec[0 if owned else 1] = 1.0
        s.save_embedding(f"al:{rid}", vec.tobytes())
    e = Engine(s)
    fair, high, low, lowest = e._kind_score([e.pos[f"al:{i}"] for i in (10, 11, 12, 13)], e.owned_franchises())
    # 6.6 and 8.9 are in the same group. 6.4 and 5.0 are below the limit, and they are equal too.
    assert fair == high
    assert low == lowest
    assert fair > low


def test_show_without_a_tier_gives_links_with_a_smaller_weight(tmp_path):
    # al:1 gets tier S. al:2 is a show of the user without a tier, and AniList users connect it to al:11.
    e = _link_engine(tmp_path, extra=[("al:2", [0, 0, 1, 0], 1, [[11, 80]])])
    e.set_show_tier("al:1", "S")
    sources, weights = e._link_sources(*e._liked())
    assert {e.ids[i]: float(w) for i, w in zip(sources, weights)} == {"al:1": 2.0, "al:2": 0.75}
    by_id = {r["id"]: r for r in e.recommend(k=4)}
    assert by_id["al:11"]["linked_favorite"] == "al:2"
    assert by_id["al:10"]["linked_favorite"] == "al:1"
    # A C-tier show gives no links
    e.set_show_tier("al:2", "C")
    sources, _ = e._link_sources(*e._liked())
    assert [e.ids[i] for i in sources] == ["al:1"]
    assert "linked_favorite" not in {r["id"]: r for r in e.recommend(k=4)}["al:11"]


def test_library_row_gets_the_anilist_id_and_the_score_of_its_entry(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "entry.db")
    base = {"title_native": "", "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
            "owned": 1, "tmdbid": None, "poster": None}
    s.upsert_rows([dict(base, id="jf:1", source="library", title="Show", year=2021, format="series",
                        score=8.9, anilist_id=None),
                   dict(base, id="jf:2", source="library", title="No entry", year=2020, format="series",
                        score=6.0, anilist_id=None),
                   dict(base, id="al:101", source="anilist", title="Show 2", year=2023, format="tv",
                        score=7.6, anilist_id=101, library_id="jf:1"),
                   dict(base, id="al:100", source="anilist", title="Show", year=2021, format="tv",
                        score=7.1, anilist_id=100, library_id="jf:1")])
    for n, rid in enumerate(("jf:1", "jf:2", "al:101", "al:100")):
        vec = np.zeros(4, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(rid, vec.tobytes())
    e = Engine(s)
    # The entry is the first TV season: al:100
    out = e.public_row(e.pos["jf:1"])
    assert (out["anilist_id"], out["score"], out["library_score"]) == (100, 7.1, 8.9)
    assert {r["id"]: r["anilist_id"] for r in e.review_queue()} == {"jf:1": 100, "jf:2": None}
    # The row of the database does not change
    assert e.by_id["jf:1"]["anilist_id"] is None and e.by_id["jf:1"]["score"] == 8.9
    # A library row without an AniList entry and an AniList row do not change
    assert e.public_row(e.pos["jf:2"])["score"] == 6.0 and "library_score" not in e.public_row(e.pos["jf:2"])
    assert e.public_row(e.pos["al:100"])["score"] == 7.1 and "library_score" not in e.public_row(e.pos["al:100"])


def test_library_row_gets_a_poster_that_other_computers_can_load(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "poster.db")
    base = {"title_native": "", "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
            "owned": 1, "tmdbid": None, "year": 2021, "score": 7.0}
    local = "http://localhost:8096/Items/{}/Images/Primary"
    s.upsert_rows([dict(base, id="jf:1", source="library", title="Show", format="series", anilist_id=None, poster=local.format(1)),
                   dict(base, id="jf:2", source="library", title="No entry", format="series", anilist_id=None, poster=local.format(2)),
                   dict(base, id="jf:3", source="library", title="No poster", format="series", anilist_id=None, poster=None),
                   dict(base, id="al:100", source="anilist", title="Show", format="tv", anilist_id=100, library_id="jf:1",
                        poster="https://img.example/cover/small/100.jpg")])
    for n, rid in enumerate(("jf:1", "jf:2", "jf:3", "al:100")):
        vec = np.zeros(4, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(rid, vec.tobytes())
    e = Engine(s)
    # A library show with an AniList entry uses the poster of the entry
    assert e.poster_of(e.pos["jf:1"]) == "https://img.example/cover/small/100.jpg"
    # A library show without an entry gets an address of this server
    assert e.poster_of(e.pos["jf:2"]) == "/api/poster/jf:2"
    assert e.poster_of(e.pos["jf:3"]) is None
    assert e.poster_of(e.pos["al:100"]) == "https://img.example/cover/small/100.jpg"
    # The lists and the map use these posters. No address has "localhost".
    posters = {r["id"]: r["poster"] for r in e.review_queue()}
    assert posters == {"jf:1": "https://img.example/cover/small/100.jpg", "jf:2": "/api/poster/jf:2", "jf:3": None}
    assert {p["id"]: p["poster"] for p in e.get_vector_map()["points"]} == posters
    # The row of the database does not change
    assert e.by_id["jf:1"]["poster"] == local.format(1)
