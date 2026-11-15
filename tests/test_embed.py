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


def test_hash_changes_with_model(monkeypatch):
    import anime_vec.embed as embed
    before = embed.text_hash(ROW)
    monkeypatch.setattr(embed, "MODEL", "other/model")
    assert embed.text_hash(ROW) != before


def test_empty_input_has_model_dimension():
    from anime_vec.embed import DIM, embed_texts
    assert embed_texts([]).shape == (0, DIM)


def test_gpu_providers_follow_onnxruntime(monkeypatch):
    import sys
    from types import SimpleNamespace
    import anime_vec.embed as embed

    loaded = []
    fake = SimpleNamespace(get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
                           preload_dlls=lambda: loaded.append(True))
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    assert embed.gpu_providers() == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert loaded == [True]

    fake.get_available_providers = lambda: ["CPUExecutionProvider"]
    assert embed.gpu_providers() is None
