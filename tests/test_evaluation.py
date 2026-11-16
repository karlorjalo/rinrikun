import numpy as np
import pytest

from anime_vec.engine import Engine
from anime_vec.evaluation import hidden, hidden_franchise_test, rank_of_hidden, rated_shows, recent_test, summarize
from anime_vec.store import Store


def _engine(tmp_path):
    """Two groups of shows. In each group the user owns two shows, and two other shows are candidates."""
    s = Store(tmp_path / "eval.db")
    specs = []
    for g, axis in enumerate(([1, 0, 0, 0], [0, 0, 1, 0])):
        for n in range(4):
            vec = np.array(axis, dtype=np.float32)
            vec[g * 2 + 1] = 0.02 * n
            specs.append((f"al:{g * 10 + n}", vec, 1 if n < 2 else 0))
    specs.append(("al:90", np.array([0, 1, 0, 1], dtype=np.float32), 0))
    for rid, vec, owned in specs:
        s.upsert_rows([{"id": rid, "source": "anilist", "title": rid, "title_native": "",
                        "year": 2020, "format": "tv", "genres": [], "tags": [], "tag_ranks": [],
                        "studios": [], "overview": "O", "score": 7.0, "owned": owned, "tmdbid": None,
                        "anilist_id": int(rid.split(":")[1]), "poster": None}])
        s.save_embedding(rid, vec.tobytes())
    e = Engine(s)
    for rid in ("al:0", "al:1", "al:10", "al:11"):
        e.set_show_tier(rid, "S")
    return e


def test_hidden_restores_the_engine(tmp_path):
    e = _engine(tmp_path)
    before = (list(e.owned_idx), dict(e.weights), e.by_id["al:0"]["tier"])
    with hidden(e, ["al:0"]):
        assert e.by_id["al:0"]["owned"] == 0 and e.by_id["al:0"]["tier"] is None
        assert e.pos["al:0"] not in e.owned_idx and "al:0" not in e.weights
    assert (list(e.owned_idx), dict(e.weights), e.by_id["al:0"]["tier"]) == before


def test_hidden_restores_the_engine_after_an_error(tmp_path):
    e = _engine(tmp_path)
    with pytest.raises(RuntimeError):
        with hidden(e, ["al:0"]):
            raise RuntimeError("stop")
    assert e.by_id["al:0"]["owned"] == 1 and e.by_id["al:0"]["tier"] == "S"


def test_a_hidden_show_near_the_liked_shows_gets_a_high_rank(tmp_path):
    e = _engine(tmp_path)
    rank, length = rank_of_hidden(e, "al:0")
    # al:1 is still liked and is almost the same as al:0. Thus al:0 is in the first part of the list,
    # with the two unowned shows of its group, and before the shows of the other group.
    assert rank <= 3 and length >= 5


def test_rated_shows_gives_one_show_for_each_franchise(tmp_path):
    e = _engine(tmp_path)
    e.franchise["al:1"] = e.franchise["al:0"]
    assert rated_shows(e, ("S",)) == ["al:0", "al:10", "al:11"]
    assert rated_shows(e, ("C",)) == []


def test_summarize():
    s = summarize([(0, 100), (30, 100), (99, 100), (100, 100)])
    assert s["n"] == 4 and s["hit20"] == 0.25 and s["hit40"] == 0.5 and s["hit100"] == 0.75
    assert s["percentile"] == pytest.approx((1.0 + 0.7 + 0.01 + 0.0) / 4)
    assert summarize([])["n"] == 0


def test_hidden_franchise_test_runs(tmp_path):
    e = _engine(tmp_path)
    s = hidden_franchise_test(e, ("S",))
    assert s["n"] == 4 and 0.0 <= s["hit40"] <= 1.0


def test_read_only_store_does_not_change_the_database(tmp_path):
    e = _engine(tmp_path)
    path = tmp_path / "eval.db"
    before = path.read_bytes()
    ro = Engine(Store(path, read_only=True))
    assert len(ro.rows) == len(e.rows)
    with pytest.raises(Exception):
        ro.set_show_tier("al:0", "A")
    assert path.read_bytes() == before


def test_recent_test_hides_only_the_newest_franchises(tmp_path):
    e = _engine(tmp_path)
    for rid, date in (("al:0", "2021-01-01"), ("al:1", "2022-01-01"), ("al:10", "2023-01-01"), ("al:11", "2024-01-01")):
        e.by_id[rid]["added_at"] = date
    before = list(e.owned_idx)
    s = recent_test(e, count=2, tiers=("S",))
    assert s["n"] == 2
    assert list(e.owned_idx) == before
    # A show without a date is not in the test
    e.by_id["al:11"]["added_at"] = None
    assert recent_test(e, count=10, tiers=("S",))["n"] == 3
