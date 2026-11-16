import json

import anime_vec.idmap as idmap_module
from anime_vec.idmap import IdMap

ENTRIES = [
    {"type": "TV", "anilist_id": 1, "mal_id": 101, "themoviedb_id": {"tv": 500}, "tvdb_id": 900,
     "imdb_id": ["tt1"], "season": {"tvdb": 1, "tmdb": 1}},
    {"type": "TV", "anilist_id": 2, "mal_id": 102, "themoviedb_id": {"tv": 500}, "tvdb_id": 900,
     "season": {"tvdb": 2, "tmdb": 2}},
    {"type": "SPECIAL", "anilist_id": 3, "tvdb_id": 900, "season": {"tvdb": 0}},
    {"type": "MOVIE", "anilist_id": 4, "themoviedb_id": {"movie": [700]}, "imdb_id": ["tt4"]},
    {"type": "TV", "mal_id": 105, "tvdb_id": 901},
]


def test_series_gives_only_the_seasons_of_the_library():
    m = IdMap(ENTRIES)
    ids = {"tmdb": "500", "tvdb": "900"}
    assert m.anilist_ids(ids, False, [1]) == {1}
    assert m.anilist_ids(ids, False, [1, 2]) == {1, 2}
    assert m.anilist_ids(ids, False, [0, 2]) == {2, 3}


def test_series_without_season_numbers_gives_all_seasons():
    m = IdMap(ENTRIES)
    assert m.anilist_ids({"tvdb": "900"}, False, []) == {1, 2, 3}


def test_movie_uses_the_movie_id_and_the_imdb_id():
    m = IdMap(ENTRIES)
    assert m.anilist_ids({"tmdb": "700"}, True) == {4}
    assert m.anilist_ids({"imdb": "tt4"}, True) == {4}
    # The TMDB id 500 is a series id, not a movie id
    assert m.anilist_ids({"tmdb": "500"}, True) == set()


def test_unknown_ids_give_nothing():
    m = IdMap(ENTRIES)
    assert m.anilist_ids({"tmdb": "1"}, False, [1]) == set()
    assert m.anilist_ids({}, False) == set()
    assert m.anilist_ids(None, True) == set()


def test_mal_ids():
    assert IdMap(ENTRIES).mal_of == {1: 101, 2: 102}


def test_load_entries_uses_the_cache(tmp_path, monkeypatch):
    cache = tmp_path / "idmap" / "list.json"
    monkeypatch.setattr(idmap_module, "CACHE", cache)
    calls = []

    class Response:
        def read(self):
            calls.append(1)
            return json.dumps(ENTRIES).encode()

    monkeypatch.setattr(idmap_module.urllib.request, "urlopen", lambda url, timeout=0: Response())
    assert len(idmap_module.load_entries()) == 5
    assert len(idmap_module.load_entries()) == 5
    assert calls == [1]
    assert len(idmap_module.load_entries(force=True)) == 5
    assert calls == [1, 1]


def test_load_entries_keeps_the_old_cache_when_the_download_fails(tmp_path, monkeypatch):
    cache = tmp_path / "list.json"
    cache.write_text(json.dumps(ENTRIES[:2]), encoding="utf-8")
    monkeypatch.setattr(idmap_module, "CACHE", cache)

    def fail(url, timeout=0):
        raise OSError("no network")

    monkeypatch.setattr(idmap_module.urllib.request, "urlopen", fail)
    assert len(idmap_module.load_entries(force=True)) == 2
