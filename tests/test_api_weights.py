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

        # 3. Check unrated_only queue
        unrated_res = client.get("/api/review-queue?unrated_only=true")
        assert unrated_res.status_code == 200
        assert len(unrated_res.json()) == 1
        assert unrated_res.json()[0]["id"] == "al:2"

        # 4. Check profile tier summary
        prof_res = client.get("/api/profile")
        assert prof_res.status_code == 200
        assert set(prof_res.json()) == {"tier_summary", "owned_count", "manual_count", "total_count"}
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
