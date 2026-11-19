import json
import os
import time

import anime_vec.anilist_pull as anilist_pull
import anime_vec.frames as frames
from anime_vec.frames import pictures_from_media

EMPTY = {"frames": [], "trailer": None, "banner": None}
MEDIA = {
    "id": 7, "status": "FINISHED", "bannerImage": "https://s4.example/banner/7.jpg",
    "trailer": {"id": "abcDEF_1234", "site": "youtube", "thumbnail": "https://i.ytimg.com/vi/abcDEF_1234/hqdefault.jpg"},
    "streamingEpisodes": [
        {"title": "Episode 12 - The End", "thumbnail": "https://img.example/12.jpg"},
        {"title": "Teaser", "thumbnail": "https://img.example/teaser.jpg"},
        {"title": "Episode 2 - Second", "thumbnail": "https://img.example/2.jpg"},
        {"title": "Episode 1 - First", "thumbnail": "https://img.example/1.jpg"},
        {"title": "Episode 3 - Third", "thumbnail": "https://img.example/3.jpg"},
    ],
}


def test_pictures_have_the_first_episodes_then_the_trailer():
    p = pictures_from_media(MEDIA)
    assert [f["label"] for f in p["frames"]] == ["Episode 1", "Episode 2", "Episode 3", "Trailer", "Trailer", "Trailer"]
    assert p["frames"][0] == {"small": "https://img.example/1.jpg", "large": "https://img.example/1.jpg", "label": "Episode 1"}
    assert p["frames"][3] == {"small": "https://i.ytimg.com/vi/abcDEF_1234/mq1.jpg",
                              "large": "https://i.ytimg.com/vi/abcDEF_1234/maxres1.jpg", "label": "Trailer"}
    assert p["trailer"] == "https://www.youtube.com/watch?v=abcDEF_1234"
    assert p["banner"] == "https://s4.example/banner/7.jpg"


def test_pictures_of_an_anime_with_few_data():
    assert pictures_from_media({"id": 1}) == EMPTY
    assert pictures_from_media({"id": 1, "trailer": None, "streamingEpisodes": None, "bannerImage": None}) == EMPTY
    # An entry without a number comes after the episodes, and one picture gives one frame
    m = {"id": 1, "streamingEpisodes": [{"title": "Teaser", "thumbnail": "https://img.example/t.jpg"},
                                         {"title": "Episode 1", "thumbnail": "https://img.example/1.jpg"},
                                         {"title": "Episode 1 (dub)", "thumbnail": "https://img.example/1.jpg"},
                                         {"title": "Episode 2", "thumbnail": None}]}
    assert [(f["label"], f["small"]) for f in pictures_from_media(m)["frames"]] == [
        ("Episode 1", "https://img.example/1.jpg"), ("Teaser", "https://img.example/t.jpg")]
    daily = pictures_from_media({"id": 1, "trailer": {"id": "x8abc12", "site": "dailymotion",
                                                      "thumbnail": "https://s.example/t.jpg"}})
    assert daily["trailer"] == "https://www.dailymotion.com/video/x8abc12"
    assert daily["frames"] == [{"small": "https://s.example/t.jpg", "large": "https://s.example/t.jpg", "label": "Trailer"}]


def test_pictures_refuse_an_address_that_is_not_safe():
    # The interface puts each address in the page, thus only a plain https address is permitted
    m = {"id": 1, "bannerImage": "javascript:alert(1)",
         "trailer": {"id": "abc\"><script>", "site": "youtube"},
         "streamingEpisodes": [{"title": "Episode 1", "thumbnail": "http://img.example/1.jpg"},
                               {"title": "Episode 2", "thumbnail": "https://img.example/2.jpg\" onerror=\"x"}]}
    assert pictures_from_media(m) == EMPTY
    assert pictures_from_media({"id": 1, "trailer": {"id": "abcDEF_1234", "site": "other"}}) == EMPTY


def _setup(tmp_path, monkeypatch, answers):
    """Use tmp_path for the files, and give the answers of `answers` in place of AniList. Return the list of the requests."""
    monkeypatch.setattr(anilist_pull, "CACHE_DIR", tmp_path)
    calls = []

    def fake(ids):
        calls.append(list(ids))
        return [answers[i] for i in ids if i in answers]

    monkeypatch.setattr(frames, "_fetch", fake)
    return calls


def _make_old(path, days):
    then = time.time() - days * 86400
    os.utime(path, (then, then))


def test_get_pictures_asks_one_time_and_keeps_a_file(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch, {7: MEDIA})
    first = frames.get_pictures([7, 8, 7])
    assert calls == [[7, 8]]
    assert len(first[7]["frames"]) == 6 and first[8] == EMPTY
    # AniList did not return anime 8. The file keeps this result.
    assert json.loads((tmp_path / "frames" / "8.json").read_text(encoding="utf-8")) == {"id": 8, "absent": True}
    assert frames.get_pictures([8, 7]) == first and calls == [[7, 8]]
    assert frames.get_pictures([]) == {}


def test_get_pictures_asks_again_for_an_old_file(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch, {7: MEDIA, 9: dict(MEDIA, id=9, status="RELEASING")})
    frames.get_pictures([7, 8, 9])
    for i in (7, 8, 9):
        _make_old(tmp_path / "frames" / f"{i}.json", frames.SHORT_MAX_AGE_DAYS + 1)
    frames.get_pictures([7, 8, 9])
    # The file of a finished anime with pictures is good for a longer time
    assert calls == [[7, 8, 9], [8, 9]]
    _make_old(tmp_path / "frames" / "7.json", frames.MAX_AGE_DAYS + 1)
    frames.get_pictures([7])
    assert calls[-1] == [7]


def test_get_pictures_without_an_answer_of_anilist(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {7: MEDIA})
    frames.get_pictures([7])
    _make_old(tmp_path / "frames" / "7.json", frames.MAX_AGE_DAYS + 1)

    def fail(ids):
        raise OSError("no network")

    monkeypatch.setattr(frames, "_fetch", fail)
    # The old file gives the pictures of anime 7. Anime 8 has no file, thus it is not in the result.
    got = frames.get_pictures([7, 8])
    assert list(got) == [7] and len(got[7]["frames"]) == 6
    assert not (tmp_path / "frames" / "8.json").exists()


def test_get_pictures_in_batches(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch, {})
    monkeypatch.setattr(frames, "BATCH", 2)
    frames.get_pictures([5, 1, 2, 3, 4])
    assert calls == [[1, 2], [3, 4], [5]]


def test_a_corrupt_file_is_no_file(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch, {7: MEDIA})
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "7.json").write_text("{not json", encoding="utf-8")
    assert len(frames.get_pictures([7])[7]["frames"]) == 6 and calls == [[7]]
