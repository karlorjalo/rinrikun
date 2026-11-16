import json
from types import SimpleNamespace

import pytest

import anime_vec.anilist_pull as anilist_pull
from anime_vec.anilist_pull import row_from_media

GOOD_PAGE = {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": []}}}

MEDIA = {
    "id": 1531749,
    "title": {"romaji": "Gekijouban BanG Dream!", "english": None, "native": "劇場編集版"},
    "format": "MOVIE",
    "seasonYear": 2025,
    "genres": ["Drama"],
    "tags": [{"name": "School", "rank": 80}, {"name": "Music", "rank": 70}],
    "studios": {"nodes": [{"name": "SanZigen"}]},
    "description": "A compilation film.",
    "averageScore": 72,
    "coverImage": {"medium": "https://s4.anilist.co/x.jpg"},
}

def test_row_from_media():
    r = row_from_media(MEDIA)
    assert r["id"] == "al:1531749"
    assert r["title"] == "Gekijouban BanG Dream!"
    assert r["tags"] == ["School", "Music"]
    assert r["tag_ranks"] == [80, 70]
    assert r["studios"] == ["SanZigen"]
    assert r["owned"] == 0
    assert r["poster"].startswith("https://s4.anilist.co/")


def test_row_from_media_english_fallback():
    m = dict(MEDIA, title={"romaji": None, "english": "English Title", "native": None})
    assert row_from_media(m)["title"] == "English Title"


def test_row_from_media_score_scaling():
    assert row_from_media(dict(MEDIA, averageScore=72))["score"] == 7.2
    assert row_from_media(dict(MEDIA, averageScore=None))["score"] is None


def _fake_time(monkeypatch):
    monkeypatch.setattr(anilist_pull, "time", SimpleNamespace(sleep=lambda _s: None))


def test_corrupt_cache_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    monkeypatch.setattr(anilist_pull, "_graphql", lambda page, timeout=60: GOOD_PAGE)
    (tmp_path / "page_1.json").write_text('{"data": null}', encoding="utf-8")

    assert anilist_pull.fetch_pool() == []
    assert json.loads((tmp_path / "page_1.json").read_text(encoding="utf-8")) == GOOD_PAGE


def test_errors_response_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    errors_body = {"errors": [{"message": "Too Many Requests"}], "data": None}
    monkeypatch.setattr(anilist_pull, "_graphql", lambda page, timeout=60: errors_body)

    with pytest.raises(RuntimeError, match="unreachable") as exc_info:
        anilist_pull.fetch_pool(max_pages=1)
    assert "no data for page 1" in str(exc_info.value.__cause__)
    assert not (tmp_path / "page_1.json").exists()


def test_row_from_media_keeps_franchise_relations():
    m = dict(MEDIA, relations={"edges": [
        {"relationType": "SEQUEL", "node": {"id": 7, "type": "ANIME"}},
        {"relationType": "PREQUEL", "node": {"id": 3, "type": "ANIME"}},
        {"relationType": "ADAPTATION", "node": {"id": 99, "type": "MANGA"}},
        {"relationType": "CHARACTER", "node": {"id": 50, "type": "ANIME"}},
    ]})
    assert row_from_media(m)["relations"] == [3, 7]
    assert row_from_media(MEDIA)["relations"] == []


def test_cache_without_relations_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    old_page = {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": [MEDIA]}}}
    new_media = dict(MEDIA, relations={"edges": [{"relationType": "SEQUEL", "node": {"id": 7, "type": "ANIME"}}]})
    new_page = {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": [new_media]}}}
    (tmp_path / "page_1.json").write_text(json.dumps(old_page), encoding="utf-8")
    monkeypatch.setattr(anilist_pull, "_graphql", lambda page, timeout=60: new_page)

    rows = anilist_pull.fetch_pool()
    assert rows[0]["relations"] == [7]
    assert json.loads((tmp_path / "page_1.json").read_text(encoding="utf-8")) == new_page


def test_row_from_media_keeps_user_recommendations():
    m = dict(MEDIA, recommendations={"nodes": [
        {"rating": 120, "mediaRecommendation": {"id": 5, "type": "ANIME"}},
        {"rating": 40, "mediaRecommendation": {"id": 6, "type": "MANGA"}},
        {"rating": -3, "mediaRecommendation": {"id": 7, "type": "ANIME"}},
        {"rating": 9, "mediaRecommendation": None},
    ]})
    assert row_from_media(m)["recommendations"] == [[5, 120]]
    assert row_from_media(MEDIA)["recommendations"] == []


def test_cache_without_recommendations_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    old_media = dict(MEDIA, relations={"edges": []})
    new_media = dict(old_media, recommendations={"nodes": [{"rating": 8, "mediaRecommendation": {"id": 5, "type": "ANIME"}}]})
    page = lambda media: {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": [media]}}}
    (tmp_path / "page_1.json").write_text(json.dumps(page(old_media)), encoding="utf-8")
    monkeypatch.setattr(anilist_pull, "_graphql", lambda page_no, timeout=60: page(new_media))

    assert anilist_pull.fetch_pool()[0]["recommendations"] == [[5, 8]]


def test_row_from_media_keeps_status_and_episodes():
    r = row_from_media(dict(MEDIA, status="FINISHED", episodes=12))
    assert r["status"] == "FINISHED" and r["episodes"] == 12
    assert row_from_media(MEDIA)["status"] is None


def test_cache_from_an_older_query_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    old_media = dict(MEDIA, relations={"edges": []}, recommendations={"nodes": []})
    new_media = dict(old_media, status="FINISHED", episodes=12)
    page = lambda media: {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": [media]}}}
    (tmp_path / "page_1.json").write_text(json.dumps(page(old_media)), encoding="utf-8")
    monkeypatch.setattr(anilist_pull, "_graphql", lambda page_no, timeout=60: page(new_media))

    assert anilist_pull.fetch_pool()[0]["status"] == "FINISHED"


def _media(i, **kw):
    return dict(MEDIA, id=i, relations={"edges": []}, recommendations={"nodes": []}, status="FINISHED",
                startDate={"year": 2025}, **kw)


def test_related_ids():
    rows = [
        {"anilist_id": 1, "recommendations": [[2, 50], [7, 3]], "relations": [8]},
        {"anilist_id": 2, "recommendations": [[1, 50]], "relations": []},
    ]
    assert anilist_pull.related_ids(rows) == {7, 8}


def test_fetch_by_ids_caches_each_anime(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    calls = []

    def fake(ids, timeout=60):
        calls.append(list(ids))
        # AniList does not return id 3
        return {"data": {"Page": {"media": [_media(i) for i in ids if i != 3]}}}

    monkeypatch.setattr(anilist_pull, "_graphql_ids", fake)
    rows = anilist_pull.fetch_by_ids({1, 2, 3})
    assert [r["id"] for r in rows] == ["al:1", "al:2"]
    assert calls == [[1, 2, 3]]

    # The second call uses the cache, and does not ask for the absent id again
    rows = anilist_pull.fetch_by_ids({1, 2, 3, 4})
    assert [r["id"] for r in rows] == ["al:1", "al:2", "al:4"]
    assert calls == [[1, 2, 3], [4]]

    # A forced call asks for all ids again
    anilist_pull.fetch_by_ids({1, 3}, force=True)
    assert calls[-1] == [1, 3]


def test_fetch_by_ids_refetches_a_cache_file_from_an_older_query(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "1.json").write_text(json.dumps(dict(MEDIA, id=1)), encoding="utf-8")
    monkeypatch.setattr(anilist_pull, "_graphql_ids",
                        lambda ids, timeout=60: {"data": {"Page": {"media": [_media(i, episodes=12) for i in ids]}}})
    assert anilist_pull.fetch_by_ids([1])[0]["episodes"] == 12


def test_fetch_by_ids_in_batches_of_50(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    sizes = []

    def fake(ids, timeout=60):
        sizes.append(len(ids))
        return {"data": {"Page": {"media": [_media(i) for i in ids]}}}

    monkeypatch.setattr(anilist_pull, "_graphql_ids", fake)
    assert len(anilist_pull.fetch_by_ids(range(1, 121))) == 120
    assert sizes == [50, 50, 20]


def _make_old(path, days):
    import os
    import time as real_time
    stamp = real_time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def test_old_page_cache_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    page = lambda media: {"data": {"Page": {"pageInfo": {"lastPage": 1}, "media": [media]}}}
    cache = tmp_path / "page_1.json"
    cache.write_text(json.dumps(page(_media(1, episodes=1))), encoding="utf-8")
    calls = []

    def fake(page_no, timeout=60):
        calls.append(page_no)
        return page(_media(1, episodes=2))

    monkeypatch.setattr(anilist_pull, "_graphql", fake)
    assert anilist_pull.fetch_pool()[0]["episodes"] == 1
    assert calls == []
    _make_old(cache, anilist_pull.PAGE_MAX_AGE_DAYS + 1)
    assert anilist_pull.fetch_pool()[0]["episodes"] == 2
    assert calls == [1]


def test_old_cache_of_an_unfinished_anime_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    (tmp_path / "media").mkdir()
    old = anilist_pull.MEDIA_MAX_AGE_DAYS + 1
    for i, status in ((1, "NOT_YET_RELEASED"), (2, "FINISHED"), (3, "RELEASING")):
        f = tmp_path / "media" / f"{i}.json"
        f.write_text(json.dumps(dict(_media(i), status=status)), encoding="utf-8")
        _make_old(f, old if i != 3 else 1)
    calls = []

    def fake(ids, timeout=60):
        calls.append(list(ids))
        return {"data": {"Page": {"media": [dict(_media(i), status="FINISHED") for i in ids]}}}

    monkeypatch.setattr(anilist_pull, "_graphql_ids", fake)
    rows = anilist_pull.fetch_by_ids([1, 2, 3])
    # Only the old cache of the anime that was not released is asked again
    assert calls == [[1]]
    assert [r["status"] for r in rows] == ["FINISHED", "FINISHED", "RELEASING"]


def test_fetch_extras_follows_the_new_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    # 5 points to 6, 6 points to 7, 7 points to 8, 8 points to 9
    relation = lambda other: {"edges": [{"relationType": "SEQUEL", "node": {"id": other, "type": "ANIME"}}]}
    calls = []

    def fake(ids, timeout=60):
        calls.append(sorted(ids))
        return {"data": {"Page": {"media": [dict(_media(i), relations=relation(i + 1)) for i in ids]}}}

    monkeypatch.setattr(anilist_pull, "_graphql_ids", fake)
    pool = [{"anilist_id": 1, "recommendations": [[5, 10]], "relations": []}]
    rows = anilist_pull.fetch_extras(pool, {20}, rounds=3)
    # Round 1: the given id and the id that the pool points to. Rounds 2 and 3: one step more each.
    assert calls == [[5, 20], [6, 21], [7, 22]]
    assert [r["id"] for r in rows] == ["al:5", "al:20", "al:6", "al:21", "al:7", "al:22"]
    # A second call uses the cache: it gives the rows and makes no request
    assert [r["id"] for r in anilist_pull.fetch_extras(pool, set(), rounds=1)] == ["al:5"]
    assert len(calls) == 3


def test_row_from_media_uses_the_start_year_when_there_is_no_season():
    assert row_from_media(dict(MEDIA, seasonYear=None, startDate={"year": 1998}))["year"] == 1998
    assert row_from_media(dict(MEDIA, seasonYear=2025, startDate={"year": 2024}))["year"] == 2025
    assert row_from_media(dict(MEDIA, seasonYear=None, startDate={"year": None}))["year"] is None
    assert row_from_media(dict(MEDIA, seasonYear=None))["year"] is None


def test_cache_without_the_start_date_refetches(tmp_path, monkeypatch):
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    _fake_time(monkeypatch)
    (tmp_path / "media").mkdir()
    old = dict(_media(1), seasonYear=None)
    del old["startDate"]
    (tmp_path / "media" / "1.json").write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(anilist_pull, "_graphql_ids", lambda ids, timeout=60: {"data": {"Page": {"media": [
        dict(_media(i), seasonYear=None, startDate={"year": 1998}) for i in ids]}}})
    assert anilist_pull.fetch_by_ids([1])[0]["year"] == 1998


def test_row_from_media_keeps_the_english_title():
    m = dict(MEDIA, title={"romaji": "Saenai Heroine no Sodatekata", "native": "冴えない彼女の育てかた",
                           "english": "Saekano: How to Raise a Boring Girlfriend"})
    r = row_from_media(m)
    assert r["title"] == "Saenai Heroine no Sodatekata"
    assert r["title_english"] == "Saekano: How to Raise a Boring Girlfriend"
    assert row_from_media(MEDIA)["title_english"] == ""
