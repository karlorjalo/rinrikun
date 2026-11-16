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


def test_hash_changes_with_prompt(monkeypatch):
    import anime_vec.embed as embed
    before = embed.text_hash(ROW)
    monkeypatch.setattr(embed, "PROMPT", "task: clustering | query: ")
    assert embed.text_hash(ROW) != before


def test_embed_texts_batches_by_length_and_keeps_the_order(monkeypatch):
    import numpy as np
    from types import SimpleNamespace
    import anime_vec.embed as embed

    class FakeTokenizer:
        def encode(self, text):
            return SimpleNamespace(ids=list(range(1, len(text) + 1)))

    class FakeSession:
        def __init__(self):
            self.feeds = []

        def get_inputs(self):
            return [SimpleNamespace(name="input_ids", shape=["batch_size", "sequence_length"]),
                    SimpleNamespace(name="attention_mask", shape=["batch_size", "sequence_length"]),
                    SimpleNamespace(name="image_features", shape=["num_image_tokens", 512])]

        def run(self, output_names, feed):
            assert output_names == ["sentence_embedding"]
            self.feeds.append(feed)
            out = np.zeros((feed["input_ids"].shape[0], embed.DIM), dtype=np.float32)
            # The first value of each vector is the number of tokens that are not padding
            out[:, 0] = feed["attention_mask"].sum(axis=1)
            return [out]

    session = FakeSession()
    monkeypatch.setattr(embed, "_get_model", lambda: (FakeTokenizer(), session))
    monkeypatch.setattr(embed, "BATCH_SIZE", 2)
    texts = ["ccc", "a", "eeeee", "bb", "dddd"]
    vecs = embed.embed_texts(texts)

    assert vecs.shape == (5, embed.DIM)
    assert [int(v) for v in vecs[:, 0]] == [len(embed.PROMPT) + len(t) for t in texts]
    assert len(session.feeds) == 3
    # Each batch has the width of its longest text, and the padding has mask 0
    assert session.feeds[0]["input_ids"].shape == (2, len(embed.PROMPT) + 2)
    assert session.feeds[0]["attention_mask"][0].sum() == len(embed.PROMPT) + 1
    # Text-only use gives an empty array for the image input
    assert session.feeds[0]["image_features"].shape == (0, 512)
