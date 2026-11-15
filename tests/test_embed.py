from anime_vec.embed import build_text, text_hash, vec_to_blob, blob_to_vec

ROW = {"title_native": "冴えない彼女の育てかた", "title": "Saenai Heroine no Sodatekata",
       "year": 2015, "genres": ["コメディ"], "tags": ["school"], "tag_ranks": [],
       "studios": ["A-1 Pictures"], "overview": "Tomoya is an otaku."}

def test_build_text_template():
    t = build_text(ROW)
    assert t.startswith("冴えない彼女の育てかた (Saenai Heroine no Sodatekata). 2015.")
    assert "Genres: コメディ." in t
    assert "Tags: school." in t
    assert "Studios: A-1 Pictures." in t
    assert "Tomoya is an otaku." in t

def test_missing_overview_omits_clause():
    r = dict(ROW, overview="")
    assert "Tomoya" not in build_text(r)

def test_hash_changes_with_content():
    assert text_hash(ROW) != text_hash(dict(ROW, year=2016))

def test_blob_roundtrip():
    import numpy as np
    v = np.arange(384, dtype=np.float32)
    assert (blob_to_vec(vec_to_blob(v)) == v).all()
