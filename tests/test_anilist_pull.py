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
