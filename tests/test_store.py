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


def test_manual_watched_store(tmp_path):
    s = Store(tmp_path / "w.db")
    s.upsert_rows([make_row(1, owned=0)])
    assert s.get_manual_watched_ids() == set()
    s.set_manual_watched("al:1", watched=True)
    assert s.get_manual_watched_ids() == {"al:1"}
    rows = s.load_rows()
    assert rows[0]["owned"] == 1
    assert rows[0]["manual_watched"] == 1
    s.set_manual_watched("al:1", watched=False)
    assert s.get_manual_watched_ids() == set()
    rows2 = s.load_rows()
    assert rows2[0]["owned"] == 0
    assert rows2[0]["manual_watched"] == 0


def test_show_weights_store(tmp_path):
    s = Store(tmp_path / "weights.db")
    s.upsert_rows([make_row(1, owned=1)])
    assert s.get_weights() == {}
    s.set_weight("al:1", "S")
    w = s.get_weights()
    assert "al:1" in w
    assert w["al:1"]["tier"] == "S"
    assert w["al:1"]["weight"] == 2.0
    rows = s.load_rows()
    assert rows[0]["tier"] == "S"
    assert rows[0]["weight"] == 2.0
    s.delete_weight("al:1")
    assert s.get_weights() == {}
    rows2 = s.load_rows()
    assert rows2[0]["tier"] is None
    assert rows2[0]["weight"] == 1.0


def test_relations_roundtrip(tmp_path):
    s = Store(tmp_path / "r.db")
    s.upsert_rows([make_row(1, relations=[5, 9]), make_row(2)])
    rows = s.load_rows()
    assert rows[0]["relations"] == [5, 9]
    assert rows[1]["relations"] == []


def test_old_database_gets_relations_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE shows (id TEXT PRIMARY KEY, source TEXT, title TEXT, title_native TEXT, "
                "year INTEGER, format TEXT, genres TEXT, tags TEXT, tag_ranks TEXT, studios TEXT, "
                "overview TEXT, score REAL, owned INTEGER, tmdbid TEXT, anilist_id INTEGER, "
                "poster TEXT, text_hash TEXT, embedding BLOB)")
    con.execute("INSERT INTO shows (id, source, title, genres, tags, tag_ranks, studios, owned) "
                "VALUES ('al:1', 'anilist', 'Old', '[]', '[]', '[]', '[]', 0)")
    con.commit()
    con.close()
    s = Store(path)
    assert s.load_rows()[0]["relations"] == []
    s.upsert_rows([make_row(1, relations=[2], recommendations=[[3, 50]])])
    assert s.load_rows()[0]["relations"] == [2]
    assert s.load_rows()[0]["recommendations"] == [[3, 50]]


def test_recommendations_roundtrip(tmp_path):
    s = Store(tmp_path / "rec.db")
    s.upsert_rows([make_row(1, recommendations=[[5, 120], [9, 3]]), make_row(2)])
    rows = s.load_rows()
    assert rows[0]["recommendations"] == [[5, 120], [9, 3]]
    assert rows[1]["recommendations"] == []


def test_library_link_columns_roundtrip(tmp_path):
    s = Store(tmp_path / "link.db")
    s.upsert_rows([make_row(1, library_id="jf:9"),
                   make_row(2, provider_ids={"tmdb": "5"}, seasons=[1, 2], added_at="2024-05-01T10:00:00Z")])
    rows = s.load_rows()
    assert rows[0]["library_id"] == "jf:9" and rows[0]["provider_ids"] == {} and rows[0]["seasons"] == []
    assert rows[1]["library_id"] is None and rows[1]["provider_ids"] == {"tmdb": "5"}
    assert rows[1]["seasons"] == [1, 2] and rows[1]["added_at"] == "2024-05-01T10:00:00Z"
    # A later build without the link removes it
    s.upsert_rows([make_row(1)])
    assert s.load_rows()[0]["library_id"] is None


def test_status_and_episodes_roundtrip(tmp_path):
    s = Store(tmp_path / "status.db")
    s.upsert_rows([make_row(1, status="RELEASING", episodes=24), make_row(2)])
    rows = s.load_rows()
    assert rows[0]["status"] == "RELEASING" and rows[0]["episodes"] == 24
    assert rows[1]["status"] is None and rows[1]["episodes"] is None


def test_read_only_store_reads_an_old_database(tmp_path):
    import sqlite3
    path = tmp_path / "old_ro.db"
    con = sqlite3.connect(str(path))
    con.executescript("""
        CREATE TABLE shows (id TEXT PRIMARY KEY, source TEXT, title TEXT, title_native TEXT, year INTEGER,
          format TEXT, genres TEXT, tags TEXT, tag_ranks TEXT, studios TEXT, overview TEXT, score REAL,
          owned INTEGER, tmdbid TEXT, anilist_id INTEGER, poster TEXT, text_hash TEXT, embedding BLOB);
        CREATE TABLE watched_manual (id TEXT PRIMARY KEY, created_at TEXT);
        CREATE TABLE show_weights (id TEXT PRIMARY KEY, tier TEXT NOT NULL, weight REAL NOT NULL, updated_at TEXT);
        INSERT INTO shows (id, source, title, genres, tags, tag_ranks, studios, owned)
          VALUES ('al:1', 'anilist', 'Old', '["Drama"]', '[]', '[]', '[]', 0);
    """)
    con.commit()
    con.close()
    row = Store(path, read_only=True).load_rows()[0]
    assert row["title"] == "Old" and row["genres"] == ["Drama"]
    assert row["relations"] == [] and row["status"] is None and row["library_id"] is None
