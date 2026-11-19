import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from anime_vec.store import Store
from anime_vec.engine import Engine

def make_row(i, **kw):
    r = {
        "id": f"al:{i}", "source": "anilist", "title": f"Title {i}", "title_native": f"タイトル {i}",
        "year": 2021, "format": "tv", "genres": ["Action"], "tags": ["Super Power"],
        "tag_ranks": [80], "studios": ["Bones"], "overview": "Hero academy", "score": 8.0,
        "owned": 1, "tmdbid": None, "anilist_id": i, "poster": None,
    }
    r.update(kw)
    return r

def test_api_weights_endpoints(tmp_path):
    import serve
    db_path = tmp_path / "api_test.db"
    store = Store(db_path)
    store.upsert_rows([make_row(1, owned=1), make_row(2, owned=1), make_row(3, owned=0)])
    store.save_embedding("al:1", b"\x00" * 1536)
    store.save_embedding("al:2", b"\x00" * 1536)
    store.save_embedding("al:3", b"\x00" * 1536)
    engine = Engine(store)

    orig_store = serve.store
    orig_engine = serve.engine
    serve.store = store
    serve.engine = engine
    try:
        client = TestClient(serve.app)

        # 1. Initial review queue has 2 owned shows
        res = client.get("/api/review-queue")
        assert res.status_code == 200
        assert len(res.json()) == 2

        # 2. Rate al:1 as S tier
        post_res = client.post("/api/weights", json={"id": "al:1", "tier": "S"})
        assert post_res.status_code == 200
        assert post_res.json() == {"id": "al:1", "tier": "S", "weight": 2.0, "ids": ["al:1"]}

        # Check /api/ratings endpoint
        ratings_res = client.get("/api/ratings")
        assert ratings_res.status_code == 200
        assert len(ratings_res.json()) == 1
        assert ratings_res.json()[0]["id"] == "al:1"
        assert ratings_res.json()[0]["tier"] == "S"
        # Each list has the match of a show. Only a list with a seed has a similarity.
        assert 0.0 <= ratings_res.json()[0]["match"] <= 100.0 and "similarity" not in ratings_res.json()[0]
        # The match of a show does not use the formula of a list: a parameter for it has no effect
        assert client.get("/api/ratings?kinds=other").json() == ratings_res.json()
        assert "match" in client.get("/api/show/al:3").json()
        assert all("match" in r and "similarity" in r for r in client.get("/api/similar?id=al:1").json())
        assert all("match" in r and "similarity" not in r for r in client.get("/api/recommend").json())
        assert all("match" in r and "tier_guess" in r for r in client.get("/api/review-queue").json())

        # 3. Check unrated_only queue
        unrated_res = client.get("/api/review-queue?unrated_only=true")
        assert unrated_res.status_code == 200
        assert len(unrated_res.json()) == 1
        assert unrated_res.json()[0]["id"] == "al:2"

        # 4. Check profile tier summary
        prof_res = client.get("/api/profile")
        assert prof_res.status_code == 200
        assert set(prof_res.json()) == {"tier_summary", "owned_count", "library_count", "manual_count", "total_count"}
        # The two owned shows are AniList rows: the user marked them by hand
        assert prof_res.json()["owned_count"] == 2 and prof_res.json()["library_count"] == 0
        summary = prof_res.json()["tier_summary"]
        assert summary["S"] == 1
        assert summary["unrated"] == 1

        # 5. Delete weight via DELETE
        del_res = client.delete("/api/weights?id=al:1")
        assert del_res.status_code == 200
        assert del_res.json() == {"id": "al:1", "tier": None, "weight": 1.0, "ids": ["al:1"]}

        # 6. Both unrated now
        unrated_res2 = client.get("/api/review-queue?unrated_only=true")
        assert len(unrated_res2.json()) == 2

        # 7. Check recommend modes
        rec_hybrid = client.get("/api/recommend?mode=hybrid")
        assert rec_hybrid.status_code == 200
        assert len(rec_hybrid.json()) == 1
        assert rec_hybrid.json()[0]["id"] == "al:3"

        rec_invalid = client.get("/api/recommend?mode=invalid")
        assert rec_invalid.status_code == 422

        # The data of one show
        show_res = client.get("/api/show/al:1")
        assert show_res.status_code == 200
        assert show_res.json()["anilist_id"] == 1 and "text_hash" not in show_res.json()
        assert client.get("/api/show/al:99").status_code == 404

        # 8. Check vector-map endpoint
        vm_res = client.get("/api/vector-map")
        assert vm_res.status_code == 200
        assert "points" in vm_res.json()
        assert len(vm_res.json()["points"]) == 3

        # 9. The match of the map points: one value for each point
        mm_res = client.get("/api/vector-map/match")
        assert mm_res.status_code == 200
        assert len(mm_res.json()) == 3

        # 10. The list of the shows has the other titles of each show, for the search
        assert all(x["aka"] == [] for x in client.get("/api/shows").json())
    finally:
        serve.store = orig_store
        serve.engine = orig_engine


def test_api_recommend_new_only(tmp_path):
    import serve
    store = Store(tmp_path / "api_new_only.db")
    store.upsert_rows([make_row(1, owned=1), make_row(2, owned=0, relations=[1]), make_row(3, owned=0)])
    for i in (1, 2, 3):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        all_recs = client.get("/api/recommend?k=10").json()
        assert {r["id"]: r["franchise_owned"] for r in all_recs} == {"al:2": True, "al:3": False}
        new_recs = client.get("/api/recommend?k=10&new_only=true").json()
        assert [r["id"] for r in new_recs] == ["al:3"]
        assert client.get("/api/recommend?mode=diverse").status_code == 200
        # The two formulas
        assert [r["id"] for r in client.get("/api/recommend?k=10&kinds=usual").json()] != []
        assert client.get("/api/recommend?kinds=all").status_code == 200
        assert client.get("/api/recommend?kinds=other").status_code == 422
        # The formula without the crowd links
        no_links = client.get("/api/recommend?k=10&kinds=usual&links=false")
        assert no_links.status_code == 200 and all("linked_favorite" not in r for r in no_links.json())
        # The steps from the catalog to the list, for the animation of the map
        steps = client.get("/api/recommend/steps?k=1&kinds=usual&links=false").json()
        assert [s["key"] for s in steps["steps"]][:2] == ["catalog", "new"] and steps["steps"][-1]["key"] == "list"
        assert steps["steps"][0]["count"] == 3 and steps["links"] is False
        assert client.get("/api/recommend/steps?kinds=other").status_code == 422
        # The Center and Peak formulas do not exist now
        assert client.get("/api/recommend?mode=center").status_code == 422
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_dismissed(tmp_path):
    import serve
    store = Store(tmp_path / "api_dismissed.db")
    store.upsert_rows([make_row(1, owned=1), make_row(2, owned=0), make_row(3, owned=0)])
    for i in (1, 2, 3):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        assert client.get("/api/dismissed").json() == []
        res = client.post("/api/dismissed", json={"id": "al:2"})
        assert res.status_code == 200 and res.json() == {"id": "al:2", "dismissed": True}
        assert [r["id"] for r in client.get("/api/dismissed").json()] == ["al:2"]
        assert [r["id"] for r in client.get("/api/recommend?k=10").json()] == ["al:3"]
        assert client.get("/api/show/al:2").json()["dismissed"] == 1
        res = client.post("/api/dismissed", json={"id": "al:2", "dismissed": False})
        assert res.json() == {"id": "al:2", "dismissed": False}
        assert {r["id"] for r in client.get("/api/recommend?k=10").json()} == {"al:2", "al:3"}
        assert client.post("/api/dismissed", json={"id": "al:999"}).status_code == 404
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_compresses_large_responses(tmp_path):
    import serve
    store = Store(tmp_path / "api_gzip.db")
    store.upsert_rows([make_row(i, owned=0, overview="A long text. " * 40) for i in range(1, 40)])
    for i in range(1, 40):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        res = client.get("/api/vector-map", headers={"Accept-Encoding": "gzip"})
        assert res.status_code == 200 and res.headers.get("content-encoding") == "gzip"
        assert len(res.json()["points"]) == 39
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_passes_the_poster_of_a_library_show_on(tmp_path, monkeypatch):
    import email.message
    import serve
    store = Store(tmp_path / "api_poster.db")
    store.upsert_rows([make_row(1, owned=0),
                       dict(make_row(2), id="jf:2", source="library", anilist_id=None, format="series",
                            poster="http://localhost:8096/Items/2/Images/Primary")])
    for rid in ("al:1", "jf:2"):
        store.save_embedding(rid, b"\x00" * 1536)

    class FakeResponse:
        def __init__(self):
            self.headers = email.message.Message()
            self.headers["Content-Type"] = "image/jpeg"

        def read(self):
            return b"picture"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    asked = []

    def fake_urlopen(url, timeout=15):
        asked.append(url)
        if "fail" in url:
            raise OSError("no connection")
        return FakeResponse()

    monkeypatch.setattr(serve.urllib.request, "urlopen", fake_urlopen)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        # The list of titles gives the address of this server for the library show
        by_id = {r["id"]: r["poster"] for r in client.get("/api/shows").json()}
        assert by_id == {"al:1": None, "jf:2": "/api/poster/jf:2"}
        res = client.get("/api/poster/jf:2")
        assert res.status_code == 200 and res.content == b"picture"
        assert res.headers["content-type"] == "image/jpeg" and "max-age" in res.headers["cache-control"]
        assert asked == ["http://localhost:8096/Items/2/Images/Primary?maxWidth=400&quality=90"]
        # An AniList show and an unknown show have no poster at this address
        assert client.get("/api/poster/al:1").status_code == 404
        assert client.get("/api/poster/jf:9").status_code == 404
        # Jellyfin does not answer
        serve.engine.by_id["jf:2"]["poster"] = "http://localhost:8096/fail"
        assert client.get("/api/poster/jf:2").status_code == 502
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_logs_the_recommendations_and_their_results(tmp_path):
    import serve
    store = Store(tmp_path / "api_log.db")
    # al:2 is a sequel of the owned show al:1. al:3, al:4 and al:5 are new franchises.
    store.upsert_rows([make_row(1, owned=1), make_row(2, owned=0, relations=[1]),
                       make_row(3, owned=0), make_row(4, owned=0), make_row(5, owned=0)])
    for i in range(1, 6):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        assert client.get("/api/rec-log").json()["shown"] == 0
        # A list with a seed is not in the log
        client.get("/api/recommend?k=10&seed=al:1")
        assert store.get_rec_log() == {}
        # The list has the sequel al:2, but only the new franchises go into the log
        assert len(client.get("/api/recommend?k=10").json()) == 4
        assert set(store.get_rec_log()) == {"al:3", "al:4", "al:5"}
        # The user adds al:3 with tier A, adds al:4 without a tier, and removes al:5
        client.post("/api/watched", json={"id": "al:3", "watched": True})
        client.post("/api/weights", json={"id": "al:3", "tier": "A"})
        client.post("/api/watched", json={"id": "al:4", "watched": True})
        client.post("/api/dismissed", json={"id": "al:5", "dismissed": True})
        res = client.get("/api/rec-log").json()
        assert (res["shown"], res["added"], res["unrated"], res["removed"]) == (3, 2, 1, 1)
        assert res["tiers"] == {"S": 0, "A": 1, "B": 0, "C": 0, "D": 0}
        assert {x["id"]: x["tier"] for x in res["shows"]} == {"al:3": "A", "al:4": None}
        assert res["since"] is not None
        # All these shows came from a list with the crowd links
        assert res["formulas"] == {"links": {"shown": 3, "added": 2, "removed": 1},
                                   "no links": {"shown": 0, "added": 0, "removed": 0}}
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_log_keeps_the_formula_of_the_first_list(tmp_path):
    import serve
    store = Store(tmp_path / "api_log_formula.db")
    store.upsert_rows([make_row(1, owned=1), make_row(3, owned=0), make_row(4, owned=0)])
    for i in (1, 3, 4):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        # The first list has no crowd links, and it has only the first show
        assert len(client.get("/api/recommend?k=1&kinds=usual&links=false").json()) == 1
        first = next(iter(store.get_rec_log()))
        client.get("/api/recommend?k=10&kinds=usual")
        log = store.get_rec_log()
        other = next(i for i in log if i != first)
        assert log[first]["kinds"] == "usual, no links" and log[other]["kinds"] == "usual"
        client.post("/api/watched", json={"id": first, "watched": True})
        client.post("/api/dismissed", json={"id": other, "dismissed": True})
        res = client.get("/api/rec-log").json()
        assert res["formulas"] == {"links": {"shown": 1, "added": 0, "removed": 1},
                                   "no links": {"shown": 1, "added": 1, "removed": 0}}
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_discover_and_interest(tmp_path):
    import serve
    store = Store(tmp_path / "api_discover.db")
    store.upsert_rows([make_row(1, owned=1)] + [make_row(i, owned=0) for i in range(2, 9)])
    for i in range(1, 9):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    try:
        client = TestClient(serve.app)
        deck = client.get("/api/discover?count=3").json()
        assert len(deck["cards"]) == 3 and deck["counts"] == {"interested": 0, "not_interested": 0}
        assert all(not c["owned"] and "match" in c and c["interest"] is None for c in deck["cards"])
        first, second = deck["cards"][0]["id"], deck["cards"][1]["id"]
        res = client.post("/api/interest", json={"id": first, "value": True, "source": "deck"}).json()
        assert res == {"id": first, "interest": 1, "dismissed": 0, "counts": {"interested": 1, "not_interested": 0}}
        res = client.post("/api/interest", json={"id": second, "value": False, "source": "deck"}).json()
        assert res["interest"] == 0 and res["dismissed"] == 1 and res["counts"] == {"interested": 1, "not_interested": 1}
        # The watch list, the removed shows and the results
        assert [r["id"] for r in client.get("/api/interest").json()] == [first]
        assert [r["id"] for r in client.get("/api/dismissed").json()] == [second]
        results = client.get("/api/interest/results").json()
        assert results["answers"] == 2 and sum(g["answers"] for g in results["groups"]) == 2
        assert store.get_interest()[first]["source"] == "deck"
        # The two shows are not cards now
        later = {c["id"] for c in client.get("/api/discover?count=50").json()["cards"]}
        assert len(later) == 5 and not later & {first, second}
        # No answer, an answer from a page, and the errors
        assert client.post("/api/interest", json={"id": first, "value": None}).json()["interest"] is None
        assert client.post("/api/interest", json={"id": first, "value": True}).json()["interest"] == 1
        assert store.get_interest()[first]["source"] == "page"
        assert client.post("/api/dismissed", json={"id": second, "dismissed": False}).status_code == 200
        assert client.get("/api/dismissed").json() == [] and second not in store.get_interest()
        assert client.post("/api/interest", json={"id": "al:1", "value": True}).status_code == 400
        assert client.post("/api/interest", json={"id": "al:99", "value": True}).status_code == 404
        assert client.get("/api/discover?count=0").status_code == 422
    finally:
        serve.store, serve.engine = orig_store, orig_engine


def test_api_frames(tmp_path, monkeypatch):
    import serve
    store = Store(tmp_path / "api_frames.db")
    store.upsert_rows([make_row(1, owned=1), make_row(2, owned=0), make_row(3, owned=0)])
    for i in (1, 2, 3):
        store.save_embedding(f"al:{i}", b"\x00" * 1536)
    orig_store, orig_engine = serve.store, serve.engine
    serve.store, serve.engine = store, Engine(store)
    asked = []
    pictures = {"frames": [{"small": "https://x.example/s.jpg", "large": "https://x.example/l.jpg", "label": "Episode 1"}],
                "trailer": None, "banner": None}

    def fake(ids):
        asked.append(sorted(ids))
        return {2: pictures}

    monkeypatch.setattr(serve.frames, "get_pictures", fake)
    try:
        client = TestClient(serve.app)
        res = client.get("/api/frames?ids=al:1,al:2,al:99")
        # AniList gave no answer for al:1, and al:99 is not a show
        assert res.status_code == 200 and res.json() == {"al:2": pictures}
        assert asked == [[1, 2]]
        # No show of the catalog: the server does not ask AniList
        assert client.get("/api/frames?ids=al:99").json() == {} and len(asked) == 1
        assert client.get("/api/frames").status_code == 422
        monkeypatch.setattr(serve, "FRAMES_MAX", 2)
        assert client.get("/api/frames?ids=al:1,al:2,al:3").status_code == 400
    finally:
        serve.store, serve.engine = orig_store, orig_engine
