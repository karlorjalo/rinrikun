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
    # A list without a seed has no similarity to a seed
    assert all("similarity" not in r for r in res)


def test_recommend_modes(tmp_path):
    e, rows = make_engine(tmp_path)
    # Rate al:0 as S, al:1 as D
    e.set_show_tier("al:0", "S")
    e.set_show_tier("al:1", "D")

    for mode in ["hybrid", "diverse"]:
        res = e.recommend(k=2, mode=mode)
        assert len(res) == 2
        assert all(not r["owned"] for r in res)
        assert all("similarity" not in r for r in res)

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


def test_list_score_has_no_part_for_the_similarity_to_the_low_tiers(tmp_path):
    # al:2 is owned and gets tier C. al:12 has the same embedding as al:2. The shows have no tags,
    # thus the taste model cannot learn from the tier.
    e = _link_engine(tmp_path, extra=[("al:2", [0, 0, 1, 0], 1, [])])
    e.set_show_tier("al:1", "S")
    cand = [e.pos[i] for i in ("al:10", "al:11", "al:12", "al:13")]
    owned = e.owned_franchises()
    before = e._hybrid(cand, "all", owned)["scores"]
    e.set_show_tier("al:2", "C")
    after = e._hybrid(cand, "all", owned)
    # A show that is like a C-tier show does not move down for this reason
    assert np.allclose(before, after["scores"])
    assert [key for key, _ in after["stages"]] == ["content", "links"]


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
    # Only the tier penalty is different between the two lists
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


def test_dismissed_show_is_an_example_for_the_taste_model(tmp_path):
    e = _dismiss_engine(tmp_path)
    same_tags, one_tag = _taste_of(e, "al:11"), _taste_of(e, "al:12")
    e.set_dismissed("al:10", True)
    # al:11 has the two tags of the removed al:10, and al:12 has one of them
    assert same_tags - _taste_of(e, "al:11") > one_tag - _taste_of(e, "al:12")
    assert _taste_of(e, "al:11") < same_tags


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


def _match_engine(tmp_path):
    """al:1 and al:2 are liked shows with different content. Each has one candidate with the same content."""
    e = _link_engine(tmp_path, extra=[("al:2", [0, 0, 1, 0], 1, []), ("al:3", [0, 0, 0, 1], 1, [])])
    e.set_show_tier("al:1", "S")
    e.set_show_tier("al:2", "A")
    return e


def test_match_is_the_content_score_without_a_tier_model(tmp_path):
    e = _match_engine(tmp_path)
    match = e.match_percent()
    recs = e.recommend(k=10)
    cand = [e.pos[r["id"]] for r in recs]
    values = [float(match[j]) for j in cand]
    # Three rated shows are too few for the tier model. Then the match has the order of the content score.
    content = e._content(cand)["scores"]
    assert [values[k] for k in np.argsort(-content, kind="stable")] == sorted(values, reverse=True)
    assert all(0.0 <= v < 100.0 for v in values)
    # with_match gives the same values, with one decimal
    assert [r["match"] for r in e.with_match(recs)] == [round(v, 1) for v in values]


def test_match_does_not_use_the_crowd_links(tmp_path):
    e = _link_engine(tmp_path)
    ids = [r["id"] for r in e.recommend(k=4)]
    match = e.match_percent()
    # al:10 and al:11 have the same content. The crowd link of al:10 changes the list, not the match.
    assert ids.index("al:10") < ids.index("al:11")
    assert match[e.pos["al:10"]] == match[e.pos["al:11"]]


def test_match_of_a_show_of_the_user_ignores_the_show_itself(tmp_path):
    e = _match_engine(tmp_path)
    match = e.match_percent()
    # al:12 has the content of the liked show al:2, thus its content score is the best possible.
    # al:2 itself gets the score that it has without al:2: its content is far from al:1.
    cand = [e.pos[i] for i in ("al:10", "al:11", "al:12", "al:13")]
    content = e._content(cand, [e.pos["al:2"]])
    assert content["extra_scores"][0] < content["scores"][2]
    assert match[e.pos["al:2"]] <= match[e.pos["al:12"]]
    # All rows have a match: candidates, shows of the user, and shows without a tier
    assert not np.isnan(match).any()


def test_match_changes_when_a_tier_changes(tmp_path):
    e = _match_engine(tmp_path)
    before = e.match_percent().copy()
    assert e.match_percent() is e.match_percent()
    e.set_show_tier("al:2", "D")
    after = e.match_percent()
    # al:12 is like al:2, which is now a disliked show
    assert after[e.pos["al:12"]] < before[e.pos["al:12"]]


def test_match_of_an_anilist_row_of_a_library_show(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "match_lib.db")
    base = {"title_native": "", "genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O",
            "tmdbid": None, "poster": None, "year": 2021, "score": 7.0}
    s.upsert_rows([dict(base, id="jf:1", source="library", title="Show", format="series", anilist_id=None, owned=1),
                   dict(base, id="al:100", source="anilist", title="Show", format="tv", anilist_id=100, owned=1, library_id="jf:1"),
                   dict(base, id="al:200", source="anilist", title="Other", format="tv", anilist_id=200, owned=0),
                   dict(base, id="al:300", source="anilist", title="Third", format="tv", anilist_id=300, owned=0)])
    for n, rid in enumerate(("jf:1", "al:100", "al:200", "al:300")):
        vec = np.zeros(4, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(rid, vec.tobytes())
    e = Engine(s)
    match = e.match_percent()
    assert match[e.pos["al:100"]] == match[e.pos["jf:1"]]
    queue = e.review_queue()
    assert [r["id"] for r in queue] == ["jf:1"] and queue[0]["match"] is not None and "similarity" not in queue[0]


def test_review_queue_has_the_shows_without_a_tier_first_by_match(tmp_path):
    e = _match_engine(tmp_path)
    queue = e.review_queue()
    assert [r["id"] for r in queue] == ["al:3", "al:1", "al:2"] or [r["id"] for r in queue] == ["al:3", "al:2", "al:1"]
    # Three rated shows are too few for the tier model: no show has a tier guess
    assert all(r["tier_guess"] is None for r in queue)
    rated = [r for r in queue if r["tier"]]
    assert [r["match"] for r in rated] == sorted((r["match"] for r in rated), reverse=True)
    assert [r["id"] for r in e.review_queue(unrated_only=True)] == ["al:3"]
    # The rated shows: by tier, then by match
    assert [r["tier"] for r in e.rated_shows()] == ["S", "A"]


def test_tier_prediction_without_the_row_itself(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    monkeypatch.setattr(engine_module, "TIER_MODEL_MIN_RATED", 3)
    from anime_vec.store import Store
    s = Store(tmp_path / "loo.db")
    tags = [["A"], ["A"], ["A"], ["B"], ["B"], ["A", "B"]]
    for n, t in enumerate(tags):
        s.upsert_rows([{"id": f"al:{n}", "source": "anilist", "title": f"T{n}", "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": t, "tag_ranks": [80] * len(t), "studios": [],
                        "overview": "O", "score": 7.0, "owned": 1, "tmdbid": None, "anilist_id": n, "poster": None}])
        vec = np.zeros(8, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(f"al:{n}", vec.tobytes())
    e = Engine(s)
    for n, tier in enumerate(["S", "S", "D", "C", "C", "B"]):
        e.set_show_tier(f"al:{n}", tier)
    rows = [e.pos[f"al:{n}"] for n in range(6)]
    with_row = e._predicted_tier(rows)
    without_row = e._predicted_tier(rows, leave_out="row")
    # al:2 has tier D among shows with tag A that have tier S. The model that knows al:2 predicts a
    # lower tier for it than the model that does not know it.
    assert without_row[2] > with_row[2]
    # The check with a model that really does not have the row
    e.set_show_tier("al:2", None)
    assert e._predicted_tier([rows[2]])[0] == pytest.approx(without_row[2], abs=1e-3)


def _guess_engine(tmp_path, monkeypatch):
    """Shows with tag A have tier S, shows with tag B have tier C. Four shows have no tier."""
    import anime_vec.engine as engine_module
    monkeypatch.setattr(engine_module, "TIER_MODEL_MIN_RATED", 4)
    from anime_vec.store import Store
    s = Store(tmp_path / "guess.db")
    # id, tag, owned
    specs = [(1, "A", 1), (2, "A", 1), (3, "A", 1), (4, "B", 1), (5, "B", 1), (6, "B", 1),
             (7, "A", 1), (8, "B", 1), (20, "A", 0), (21, "B", 0)]
    for n, (rid, tag, owned) in enumerate(specs):
        s.upsert_rows([{"id": f"al:{rid}", "source": "anilist", "title": f"T{rid}", "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": [tag], "tag_ranks": [80], "studios": [],
                        "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None, "anilist_id": rid, "poster": None}])
        vec = np.zeros(12, dtype=np.float32)
        vec[n] = 1.0
        s.save_embedding(f"al:{rid}", vec.tobytes())
    e = Engine(s)
    for rid, tier in ((1, "S"), (2, "S"), (3, "S"), (4, "C"), (5, "C"), (6, "C")):
        e.set_show_tier(f"al:{rid}", tier)
    return e


def test_tier_guess_of_the_shows_without_a_tier(tmp_path, monkeypatch):
    e = _guess_engine(tmp_path, monkeypatch)
    guess = e.tier_guess()
    # A show with the tag of the S-tier shows gets a higher guess than a show with the tag of the C-tier shows
    assert guess[e.pos["al:7"]] > guess[e.pos["al:8"]]
    assert guess[e.pos["al:20"]] > guess[e.pos["al:21"]]
    by_id = {r["id"]: r for r in e.with_match([e.public_row(e.pos[f"al:{i}"]) for i in (1, 7, 8, 20, 21)])}
    assert by_id["al:7"]["tier_guess"] in ("S", "A") and by_id["al:8"]["tier_guess"] in ("B", "C")
    assert by_id["al:20"]["tier_guess"] in ("S", "A") and by_id["al:21"]["tier_guess"] in ("B", "C")
    # A rated show has its tier, thus it has no guess
    assert by_id["al:1"]["tier_guess"] is None
    # The engine keeps the result until a tier changes
    assert e.tier_guess() is guess
    e.set_show_tier("al:7", "S")
    assert e.tier_guess() is not guess


def test_shows_without_a_tier_are_in_the_order_of_the_guess_and_the_match(tmp_path, monkeypatch):
    e = _guess_engine(tmp_path, monkeypatch)
    rows = [e.pos["al:8"], e.pos["al:7"]]
    # The two shows have about the same match, thus the tier guess decides
    assert [e.ids[i] for i in e.watch_next_order(rows)] == ["al:7", "al:8"]
    queue = e.review_queue()
    assert [r["id"] for r in queue[:2]] == ["al:7", "al:8"]
    assert all(r["tier"] for r in queue[2:])
    assert [r["id"] for r in e.review_queue(unrated_only=True)] == ["al:7", "al:8"]
    assert e.watch_next_order([]) == [] and e.watch_next_order([rows[0]]) == [rows[0]]


def test_threads_compute_the_match_one_time(tmp_path):
    import threading
    import time
    e = _match_engine(tmp_path)
    e.match_percent()
    calls = []
    original = e._content

    def slow_content(*args, **kwargs):
        calls.append(1)
        time.sleep(0.2)
        return original(*args, **kwargs)

    e._content = slow_content
    # A change of a tier makes the match stale. Four requests then ask for it at the same time.
    e.set_show_tier("al:2", "B")
    results = []
    threads = [threading.Thread(target=lambda: results.append(e.match_percent())) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert all(r is results[0] for r in results)


def test_map_match_has_the_order_of_the_map_points(tmp_path):
    e = _match_engine(tmp_path)
    points = e.get_vector_map()["points"]
    match = e.match_percent()
    values = e.map_match()
    assert len(values) == len(points)
    assert values == [round(float(match[e.pos[p["id"]]]), 1) for p in points]


def test_map_match_is_none_without_shows_of_the_user(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "no_shows.db")
    for i, vec in ((1, [1, 0, 0, 0]), (2, [0, 1, 0, 0]), (3, [0, 0, 1, 0])):
        s.upsert_rows([{"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": 0, "tmdbid": None,
                        "anilist_id": i, "poster": None}])
        s.save_embedding(f"al:{i}", np.array(vec, dtype=np.float32).tobytes())
    assert Engine(s).map_match() == [None, None, None]


def test_other_titles_of_a_library_show_come_from_its_anilist_entries(tmp_path):
    from anime_vec.store import Store
    s = Store(tmp_path / "titles.db")
    base = {"genres": [], "tags": [], "tag_ranks": [], "studios": [], "overview": "O", "score": 7.0,
            "tmdbid": None, "poster": None, "year": 2015}
    rows = [
        dict(base, id="jf:1", source="library", title="冴えない彼女の育てかた", title_native="冴えない彼女の育てかた",
             format="series", owned=1, anilist_id=None),
        dict(base, id="al:10", source="anilist", title="Saenai Heroine no Sodatekata", title_native="冴えない彼女の育てかた",
             title_english="Saekano: How to Raise a Boring Girlfriend", format="tv", owned=1, anilist_id=10,
             library_id="jf:1"),
        dict(base, id="al:11", source="anilist", title="Saenai Heroine no Sodatekata Flat", title_native="冴えない彼女の育てかた♭",
             title_english="Saekano: How to Raise a Boring Girlfriend .flat", format="tv", year=2017, owned=1,
             anilist_id=11, library_id="jf:1"),
        dict(base, id="al:20", source="anilist", title="Romaji", title_native="日本語", title_english="Romaji",
             format="tv", owned=0, anilist_id=20),
        dict(base, id="al:30", source="anilist", title="No English", title_native="", format="tv", owned=0, anilist_id=30),
    ]
    for n, r in enumerate(rows):
        s.upsert_rows([r])
        s.save_embedding(r["id"], np.eye(5, dtype=np.float32)[n].tobytes())
    e = Engine(s)
    # The library row has the titles of its two entries. It does not have its own title a second time.
    assert e.other_titles(e.pos["jf:1"]) == [
        "Saenai Heroine no Sodatekata", "Saekano: How to Raise a Boring Girlfriend",
        "Saenai Heroine no Sodatekata Flat", "Saekano: How to Raise a Boring Girlfriend .flat", "冴えない彼女の育てかた♭"]
    # An AniList row has its English title, if that is not the same as its romaji title
    assert e.other_titles(e.pos["al:10"]) == ["Saekano: How to Raise a Boring Girlfriend"]
    assert e.other_titles(e.pos["al:20"]) == []
    assert e.other_titles(e.pos["al:30"]) == []
    # The map has the titles only for the points that have other titles
    points = {p["id"]: p for p in e.get_vector_map()["points"]}
    assert points["jf:1"]["aka"][0] == "Saenai Heroine no Sodatekata"
    assert "aka" not in points["al:20"]


def _taste_engine(tmp_path):
    """The three liked shows have the tag Band. The catalog has the tag School more frequently."""
    return _engine_from(tmp_path, [
        ("al:1", [1, 0, 0, 0, 0, 0, 0, 0], 1, ["Band", "School"], [90, 60]),
        ("al:2", [0, 1, 0, 0, 0, 0, 0, 0], 1, ["Band", "School"], [80, 60]),
        ("al:3", [0, 0, 1, 0, 0, 0, 0, 0], 1, ["Band", "Comedy"], [85, 60]),
        ("al:4", [0, 0, 0, 1, 0, 0, 0, 0], 1, ["Mecha"], [90]),
        ("al:10", [0, 0, 0, 0, 1, 0, 0, 0], 0, ["Band"], [90]),
        ("al:11", [0, 0, 0, 0, 0, 1, 0, 0], 0, ["School"], [90]),
        ("al:12", [0, 0, 0, 0, 0, 0, 1, 0], 0, ["School", "Space"], [70, 70]),
        ("al:13", [0, 0, 0, 0, 0, 0, 0, 1], 0, ["Mecha"], [90]),
        ("al:14", [0, 0, 0, 0, 1, 1, 0, 0], 0, ["School", "Idol"], [70, 70]),
        ("al:15", [0, 0, 0, 0, 0, 1, 1, 0], 0, ["Space"], [90]),
    ])


def _taste_of(e, show_id, leave_out=False):
    return float(e._taste_scores([e.pos[show_id]], leave_out=leave_out)[0])


def test_taste_model_prefers_what_the_liked_shows_have(tmp_path):
    e = _taste_engine(tmp_path)
    for tier, show_id in (("S", "al:1"), ("A", "al:2"), ("B", "al:3")):
        e.set_show_tier(show_id, tier)
    # Band is the tag of all liked shows. School is a tag of two liked shows and of three other shows.
    assert _taste_of(e, "al:10") > _taste_of(e, "al:11") > _taste_of(e, "al:15")
    # A row that is not a show of the user has the same score with leave_out
    assert _taste_of(e, "al:10", leave_out=True) == pytest.approx(_taste_of(e, "al:10"))


def test_taste_model_learns_from_the_low_tiers_and_the_removed_shows(tmp_path):
    e = _taste_engine(tmp_path)
    for show_id in ("al:1", "al:2", "al:3"):
        e.set_show_tier(show_id, "A")
    before = _taste_of(e, "al:13")
    e.set_show_tier("al:4", "C")
    # al:13 has the tag of the C-tier show al:4
    low_tier = _taste_of(e, "al:13")
    assert low_tier < before
    space = _taste_of(e, "al:12")
    e.set_dismissed("al:15", True)
    # al:12 has the tag Space of the removed show al:15
    assert _taste_of(e, "al:12") < space


def test_taste_model_has_no_scores_without_shows_of_the_user(tmp_path):
    specs = [(f"al:{n}", [1, 0.1 * n, 0, 0], 0, ["Band"], [80]) for n in range(1, 5)]
    e = _engine_from(tmp_path, specs)
    assert not e._taste_scores(list(range(len(e.rows)))).any()


def test_taste_score_of_a_show_of_the_user_ignores_its_franchise(tmp_path):
    from anime_vec.evaluation import hidden
    e = _taste_engine(tmp_path)
    for tier, show_id in (("S", "al:1"), ("A", "al:2"), ("B", "al:3"), ("C", "al:4")):
        e.set_show_tier(show_id, tier)
    for show_id in ("al:1", "al:4"):
        without = _taste_of(e, show_id, leave_out=True)
        # The model learned from the show, thus the score with the show is nearer to its value
        assert (without < _taste_of(e, show_id)) == (show_id == "al:1")
        with hidden(e, [show_id]):
            assert _taste_of(e, show_id) == pytest.approx(without, abs=1e-5)


def test_hybrid_uses_the_taste_model(tmp_path, monkeypatch):
    e = _taste_engine(tmp_path)
    for show_id in ("al:1", "al:2", "al:3"):
        e.set_show_tier(show_id, "A")
    before = [r["id"] for r in e.recommend(k=10)]
    last = before[-1]

    def one_show(self, indices, leave_out=False):
        return np.array([1.0 if self.ids[i] == last else 0.0 for i in indices], dtype=np.float32)

    monkeypatch.setattr(Engine, "_taste_scores", one_show)
    after = [r["id"] for r in e.recommend(k=10)]
    assert after.index(last) < before.index(last)


def test_formula_without_the_crowd_links(tmp_path, monkeypatch):
    e = _link_engine(tmp_path)
    cand = [e.pos[i] for i in ("al:10", "al:11", "al:12", "al:13")]
    owned = e.owned_franchises()
    with_links = e._hybrid(cand, "all", owned)["scores"]
    without = e._hybrid(cand, "all", owned, links=False)["scores"]
    # al:10 and al:11 have the same content. Only the crowd link of al:10 is different.
    assert with_links[0] > with_links[1]
    assert without[0] == without[1]
    ids = [r["id"] for r in e.recommend(k=4)]
    assert ids.index("al:10") < ids.index("al:11")
    assert all("linked_favorite" not in r for r in e.recommend(k=4, links=False))
    # The formula without the links is the formula with a link weight of 0
    monkeypatch.setattr("anime_vec.engine.LINK_WEIGHT", 0.0)
    assert np.allclose(e._hybrid(cand, "all", owned)["scores"], without)


def test_lists_of_the_user_have_the_match(tmp_path):
    e = _match_engine(tmp_path)
    match = e.match_percent()
    assert [r["match"] for r in e.rated_shows()] == [round(float(match[e.pos[r["id"]]]), 1) for r in e.rated_shows()]
    assert [r["match"] for r in e.review_queue()] == [round(float(match[e.pos[r["id"]]]), 1) for r in e.review_queue()]
    assert e.map_match() == [round(float(v), 1) for v in match]


def test_match_uses_the_predicted_tier(tmp_path, monkeypatch):
    e = _steps_engine(tmp_path)
    cand = [e.pos[f"al:{100 + n}"] for n in range(30)]
    before = e.match_percent()[cand].copy()
    last = cand[int(np.argmin(before))]

    def one_show(self, indices, leave_out=None):
        return np.array([4.0 if i == last else 2.0 for i in indices], dtype=np.float32)

    # The candidate with the lowest match gets the highest predicted tier of all candidates
    monkeypatch.setattr(Engine, "_predicted_tier", one_show)
    e._match_cache.clear()
    assert e.match_percent()[last] > before.min()


def test_match_gives_the_predicted_tier_a_small_weight(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    e = _steps_engine(tmp_path)
    cand = [e.pos[f"al:{100 + n}"] for n in range(30)]
    content = e._content(cand)["scores"]
    tiers = np.array([float(n % 5) for n in range(30)], dtype=np.float32)
    by_row = dict(zip(cand, tiers))

    def fixed(self, indices, leave_out=None):
        return np.array([by_row.get(i, 2.0) for i in indices], dtype=np.float32)

    monkeypatch.setattr(Engine, "_predicted_tier", fixed)
    z = (tiers - tiers.mean()) / tiers.std()
    assert 0.0 < engine_module.MATCH_TIER_WEIGHT < 1.0
    for weight in (engine_module.MATCH_TIER_WEIGHT, 0.0, 1.0):
        monkeypatch.setattr(engine_module, "MATCH_TIER_WEIGHT", weight)
        e._match_cache.clear()
        match = e.match_percent()[cand]
        # The match has the order of: content score + weight * predicted tier
        assert list(np.argsort(-match, kind="stable")) == list(np.argsort(-(content + weight * z), kind="stable"))


def test_match_of_a_show_with_an_answer_does_not_know_the_answer(tmp_path, monkeypatch):
    e = _discover_engine(tmp_path)
    calls = []
    original = Engine._content

    def spy(self, cand_indices, extra=None):
        calls.append((list(cand_indices), list(extra or [])))
        return original(self, cand_indices, extra)

    monkeypatch.setattr(Engine, "_content", spy)
    e.match_percent()
    yes, no, sequel = e.pos["al:107"], e.pos["al:105"], e.pos["al:110"]
    assert {yes, no, sequel} <= set(calls[-1][0])
    e.set_interest("al:107", True)
    e.set_interest("al:105", False)
    # al:110 is now a show of a franchise that the user has
    e.franchise["al:110"] = e.franchise["al:1"]
    e.set_interest("al:110", True, source="page")
    match = e.match_percent()
    cand, extra = calls[-1]
    # A show of a new franchise with an answer is an extra row: its score comes from a taste model
    # that does not know the answer. A show of a franchise of the user stays a candidate.
    assert yes not in cand and no not in cand and {yes, no} <= set(extra)
    assert sequel in cand
    assert not np.isnan(match[[yes, no, sequel]]).any()
    assert _taste_of(e, "al:107", leave_out=True) < _taste_of(e, "al:107")


def _season_engine(tmp_path, monkeypatch):
    """al:1 and al:2 are two seasons of one franchise with the tag A, and the two have tier S."""
    import anime_vec.engine as engine_module
    monkeypatch.setattr(engine_module, "TIER_MODEL_MIN_RATED", 3)
    from anime_vec.store import Store
    s = Store(tmp_path / "seasons.db")
    specs = [(1, ["A"], 1, []), (2, ["A"], 1, [1]), (3, ["A"], 1, []), (4, ["B"], 1, []), (5, ["B"], 1, []), (6, ["A", "B"], 1, [])]
    specs += [(20 + n, ["A"] if n % 2 else ["B"], 0, []) for n in range(12)]
    for n, (rid, tags, owned, relations) in enumerate(specs):
        s.upsert_rows([{"id": f"al:{rid}", "source": "anilist", "title": f"T{rid}", "title_native": "", "year": 2020,
                        "format": "tv", "genres": [], "tags": tags, "tag_ranks": [80] * len(tags), "studios": [],
                        "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None, "anilist_id": rid, "poster": None,
                        "relations": relations}])
        vec = np.zeros(20, dtype=np.float32)
        vec[n] = 1.0
        vec[(n * 7) % 20] += 0.3
        s.save_embedding(f"al:{rid}", vec.tobytes())
    e = Engine(s)
    for rid, tier in ((1, "S"), (2, "S"), (3, "B"), (4, "C"), (5, "C"), (6, "B")):
        e.set_show_tier(f"al:{rid}", tier)
    assert e.franchise["al:1"] == e.franchise["al:2"] != e.franchise["al:3"]
    return e


def test_tier_prediction_without_the_franchise(tmp_path, monkeypatch):
    e = _season_engine(tmp_path, monkeypatch)
    row = e.pos["al:1"]
    with_all = e._predicted_tier([row])[0]
    without_row = e._predicted_tier([row], leave_out="row")[0]
    without_franchise = e._predicted_tier([row], leave_out="franchise")[0]
    # Without al:1 the model still knows the S tier of the other season. Without the franchise it does not.
    assert with_all > without_franchise and without_row > without_franchise
    # A row of a franchise that the model did not learn from has the usual prediction
    new = e.pos["al:21"]
    assert e._predicted_tier([new], leave_out="franchise")[0] == pytest.approx(e._predicted_tier([new])[0])
    with pytest.raises(ValueError):
        e._predicted_tier([row], leave_out="season")
    # The check with a model that really does not have the two seasons
    e.set_show_tier("al:1", None)
    e.set_show_tier("al:2", None)
    assert e._predicted_tier([row])[0] == pytest.approx(without_franchise, abs=1e-3)


def test_match_of_a_show_of_the_user_ignores_its_franchise(tmp_path, monkeypatch):
    e = _season_engine(tmp_path, monkeypatch)
    calls = []
    original = Engine._predicted_tier

    def spy(self, indices, leave_out=None):
        calls.append((list(indices), leave_out))
        return original(self, indices, leave_out)

    monkeypatch.setattr(Engine, "_predicted_tier", spy)
    e._match_cache.clear()
    match = e.match_percent()
    # The candidates get the usual prediction. The shows of the user get the prediction of a model
    # that does not know their franchise: the S tier of the other season must not count for al:1.
    assert [leave_out for _, leave_out in calls] == [None, "franchise"]
    assert e.pos["al:20"] in calls[0][0] and e.pos["al:1"] in calls[1][0]
    assert not np.isnan(match).any()


def _steps_engine(tmp_path):
    """Three liked shows, one show with a low tier, and 30 candidates. AniList users link al:1 to al:100."""
    from anime_vec.store import Store
    s = Store(tmp_path / "steps.db")
    specs = [("al:1", [1, 0, 0, 0], 1, ["Band"], [[100, 50]]), ("al:2", [0.9, 0.1, 0, 0], 1, ["Band"], []),
             ("al:3", [0.8, 0.2, 0, 0], 1, ["Band", "School"], []), ("al:4", [0, 0, 1, 0], 1, ["Mecha"], [])]
    for n in range(30):
        specs.append((f"al:{100 + n}", [np.cos(n / 10), np.sin(n / 10), 0.02 * n, 0.1], 0,
                      ["Band"] if n % 3 == 0 else ["Mecha"] if n % 3 == 1 else ["School"], []))
    for rid, vec, owned, tags, recommendations in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": 2000 + int(rid.split(":")[1]) % 20, "format": "tv", "genres": [], "tags": tags,
                        "tag_ranks": [80] * len(tags), "studios": [], "overview": "O", "score": 7.0, "owned": owned,
                        "tmdbid": None, "anilist_id": int(rid.split(":")[1]), "poster": None,
                        "recommendations": recommendations}])
        s.save_embedding(rid, np.array(vec, dtype=np.float32).tobytes())
    e = Engine(s)
    for tier, show_id in (("S", "al:1"), ("A", "al:2"), ("B", "al:3"), ("C", "al:4")):
        e.set_show_tier(show_id, tier)
    return e


def test_steps_go_from_the_catalog_to_the_list(tmp_path):
    e = _steps_engine(tmp_path)
    out = e.recommendation_steps(k=3, kinds="usual")
    steps = out["steps"]
    assert [s["key"] for s in steps] == ["catalog", "new", "content", "links", "kind", "list"]
    counts = [s["count"] for s in steps]
    assert counts[0] == 34 and counts[1] == 30 and counts[-1] == 3
    assert counts == sorted(counts, reverse=True) and len(set(counts)) > 4
    assert steps[0]["points"] is None
    assert all(len(s["points"]) == s["count"] for s in steps[1:])
    # The points are positions in the points of the map, and the last step is the list
    points = e.get_vector_map()["points"]
    listed = [points[p]["id"] for p in steps[-1]["points"]]
    assert listed == [r["id"] for r in e.recommend(k=3, kinds="usual", new_only=True)]
    assert all(not points[p]["owned"] for s in steps[1:] for p in s["points"])
    assert out["info"] == {"shows": 4, "franchises": 4, "removed": 0, "liked": 3, "rated": 4, "sources": 3}


def test_steps_have_only_the_parts_of_the_formula(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    e = _steps_engine(tmp_path)
    keys = lambda **kw: [s["key"] for s in e.recommendation_steps(k=3, **kw)["steps"]]
    # Four rated shows are too few for the tier model, thus the tier penalty changes no score
    assert keys(kinds="all") == ["catalog", "new", "content", "links", "list"]
    assert keys(kinds="usual", links=False) == ["catalog", "new", "content", "kind", "list"]
    assert keys(kinds="all", links=False) == ["catalog", "new", "content", "list"]
    # With a tier model, the candidates with the tag of the C-tier show get the tier penalty
    monkeypatch.setattr(engine_module, "TIER_MODEL_MIN_RATED", 3)
    assert keys(kinds="all", links=False) == ["catalog", "new", "content", "tier", "list"]
    assert keys(kinds="usual") == ["catalog", "new", "content", "links", "tier", "kind", "list"]
    with pytest.raises(ValueError):
        e.recommendation_steps(kinds="other")


def test_steps_without_shows_of_the_user(tmp_path):
    specs = [(f"al:{n}", [1, 0.1 * n, 0, 0], 0, ["Band"], [80]) for n in range(1, 5)]
    e = _engine_from(tmp_path, specs)
    out = e.recommendation_steps(k=3)
    assert [(s["key"], s["count"]) for s in out["steps"]] == [("catalog", 4), ("new", 4)]


def _discover_engine(tmp_path):
    """Three liked shows with the tag Band, and 40 shows that the user does not have, with four tags."""
    specs = [("al:1", [1, 0, 0, 0], 1, ["Band"], [90]), ("al:2", [0.9, 0.1, 0, 0], 1, ["Band"], [90]),
             ("al:3", [0.8, 0.2, 0, 0], 1, ["Band", "School"], [90, 60])]
    for n in range(40):
        specs.append((f"al:{100 + n}", [np.cos(n / 12), np.sin(n / 12), 0.02 * n, 0.1], 0,
                      [("Band", "Mecha", "School", "Space")[n % 4]], [80]))
    e = _engine_from(tmp_path, specs)
    for show_id in ("al:1", "al:2", "al:3"):
        e.set_show_tier(show_id, "A")
    return e


def test_answers_of_the_deck_are_weak_examples_for_the_taste_model(tmp_path):
    e = _discover_engine(tmp_path)
    space, mecha = "al:103", "al:101"
    before = _taste_of(e, space)
    # al:107 has the tag Space
    e.set_interest("al:107", True)
    assert _taste_of(e, space) > before
    # al:105 has the tag Mecha
    base = _taste_of(e, mecha)
    e.set_interest("al:105", False)
    weak = base - _taste_of(e, mecha)
    assert weak > 0
    assert e.by_id["al:107"]["interest"] == 1 and e.by_id["al:105"]["interest"] == 0
    # A removed show is a stronger example than the answer "not interested"
    e.set_interest("al:105", None)
    assert _taste_of(e, mecha) == pytest.approx(base, abs=1e-6)
    e.set_dismissed("al:105", True)
    assert base - _taste_of(e, mecha) > weak
    # The tier model does not learn from an answer
    assert e.pos["al:107"] not in e._dismissed_rows()
    # A new engine has the answers
    assert Engine(e.store).interest == {"al:107": 1}


def test_not_interested_show_is_a_removed_show(tmp_path):
    e = _discover_engine(tmp_path)
    key = e._state_key()
    e.set_interest("al:104", False)
    e.set_interest("al:108", True)
    assert e._state_key() != key
    ids = [r["id"] for r in e.recommend(k=100)]
    assert "al:104" not in ids and "al:108" in ids
    assert e.by_id["al:104"]["dismissed"] == 1 and e.by_id["al:108"]["dismissed"] == 0
    assert [r["id"] for r in e.dismissed_shows()] == ["al:104"]
    assert [r["id"] for r in e.interest_shows()] == ["al:108"] and e.interest_shows()[0]["match"] is not None
    assert e.interest_counts() == {"interested": 1, "not_interested": 1}
    assert not np.isnan(e.match_percent()[e.pos["al:104"]])
    # To put the show back deletes the answer
    e.set_dismissed("al:104", False)
    assert "al:104" not in e.interest and e.by_id["al:104"]["dismissed"] == 0
    assert "al:104" in [r["id"] for r in e.recommend(k=100)]
    # To remove a show replaces the answer "interested", and "interested" puts a removed show back
    e.set_dismissed("al:108", True)
    assert "al:108" not in e.interest and e.by_id["al:108"]["interest"] is None
    e.set_interest("al:108", True)
    assert e.dismissed == set() and e.by_id["al:108"]["dismissed"] == 0
    with pytest.raises(ValueError):
        e.set_interest("al:1", True)
    with pytest.raises(KeyError):
        e.set_interest("al:999", True)


def test_discover_draws_shows_without_an_answer_from_the_groups(tmp_path, monkeypatch):
    import anime_vec.engine as engine_module
    # The parts of the groups are 1 together, and the group with the lowest match gets the fewest cards
    parts = [part for _, part in engine_module.DISCOVER_GROUPS]
    assert sum(parts) == pytest.approx(1.0) and parts[-1] == min(parts)
    e = _discover_engine(tmp_path)
    cards = e.discover(count=12, seed=3)
    ids = [c["id"] for c in cards]
    assert len(set(ids)) == 12 and all(not c["owned"] and c["match"] is not None for c in cards)
    assert ids == [c["id"] for c in e.discover(count=12, seed=3)]
    assert ids != [c["id"] for c in e.discover(count=12, seed=4)]
    # A show with an answer and a removed show are not cards
    for n, show_id in enumerate(ids[:10]):
        e.set_interest(show_id, n % 2 == 0)
    e.set_dismissed(ids[10], True)
    later = [c["id"] for c in e.discover(count=40, seed=3)]
    assert len(later) == 40 - 11 and not set(later) & set(ids[:11])
    # All cards come from the first group while it has shows
    monkeypatch.setattr(engine_module, "DISCOVER_GROUPS", ((50.0, 1.0), (0.0, 0.0)))
    high = [j for j in range(len(e.rows)) if e.rows[j]["id"] in later and e.match_percent()[j] >= 50.0]
    drawn = e.discover(count=len(high), seed=1)
    assert len(high) > 3 and all(c["match"] >= 50.0 for c in drawn)
    assert len(e.discover(count=40, seed=1)) == len(later)


def test_interest_results_have_the_answers_of_the_deck_by_match(tmp_path):
    e = _discover_engine(tmp_path)
    assert e.interest_results() == {"answers": 0, "interested": 0, "not_interested": 0, "model": None,
                                    "groups": [{"low": low, "high": high, "answers": 0, "interested": 0}
                                               for low, high in ((99.0, 100.0), (95.0, 99.0), (80.0, 95.0), (0.0, 80.0))]}
    band = [f"al:{100 + n}" for n in range(0, 40, 4)]
    mecha = [f"al:{100 + n}" for n in range(1, 40, 4)]
    for show_id in band[:4]:
        e.set_interest(show_id, True)
    for show_id in mecha[:4]:
        e.set_interest(show_id, False)
    # An answer from a page is not in the groups
    e.set_interest(band[5], True, source="page")
    res = e.interest_results()
    assert (res["answers"], res["interested"], res["not_interested"]) == (9, 5, 4)
    assert sum(g["answers"] for g in res["groups"]) == 8 and sum(g["interested"] for g in res["groups"]) == 4
    # Each answer of the deck is in the group of the match of its show
    match = e.match_percent()
    deck = [(float(match[e.pos[i]]), 1) for i in band[:4]] + [(float(match[e.pos[i]]), 0) for i in mecha[:4]]
    for g in res["groups"]:
        inside = [value for m, value in deck if g["low"] <= m and (m < g["high"] or g["high"] == 100.0)]
        assert (g["answers"], g["interested"]) == (len(inside), sum(inside))
    # The interested shows have the tag of the liked shows, thus the model orders all pairs correctly
    assert res["model"] == {"pairs": 20, "auc": 1.0}
