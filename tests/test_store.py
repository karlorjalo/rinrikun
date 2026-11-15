from anime_vec.store import Store

def make_row(i, **kw):
    r = {"id": f"al:{i}", "source": "anilist", "title": f"T{i}", "title_native": "",
         "year": 2020, "format": "tv", "genres": ["Drama"], "tags": ["School"],
         "tag_ranks": [50], "studios": ["S"], "overview": "O", "score": 7.0,
         "owned": 0, "tmdbid": None, "anilist_id": i, "poster": None}
    r.update(kw)
    return r

def test_upsert_and_load(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_rows([make_row(1, owned=1), make_row(2)])
    s.save_embedding("al:1", b"\x00" * 1536)
    rows = s.load_rows()
    assert len(rows) == 2
    assert rows[0]["id"] == "al:1"
    assert s.get_embedding("al:1") == b"\x00" * 1536
    assert s.get_hash("al:2") is None

def test_hash_upsert(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_rows([make_row(1)])
    s.save_hash("al:1", "abc")
    assert s.get_hash("al:1") == "abc"

def test_upsert_preserves_hash_and_embedding(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_rows([make_row(1, title="Old")])
    s.save_embedding("al:1", b"\x01" * 1536)
    s.save_hash("al:1", "h1")
    s.upsert_rows([make_row(1, title="New")])
    assert s.get_embedding("al:1") == b"\x01" * 1536
    assert s.get_hash("al:1") == "h1"
    rows = s.load_rows()
    assert rows[0]["title"] == "New"
