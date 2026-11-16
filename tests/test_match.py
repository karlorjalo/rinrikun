from anime_vec.match import normalize_title, OwnershipMatcher

def test_nfkc_fullwidth():
    assert normalize_title("ｋｉｓｓ×ｓｉｓ") == normalize_title("kiss×sis")

def test_punct_case_space_removed():
    assert normalize_title("Saenai Heroine no Sodatekata!") == normalize_title("saenai heroine no sodatekata")

def test_leading_article():
    assert normalize_title("The Melancholy of Haruhi Suzumiya") == normalize_title("melancholy of haruhi suzumiya")

def test_exact_match():
    m = OwnershipMatcher([("jf:1", "冴えない彼女の育てかた", "Saenai Heroine no Sodatekata")])
    assert m.match("冴えない彼女の育てかた") == "jf:1"

def test_fuzzy_match():
    m = OwnershipMatcher([("jf:1", "ようこそ北宇治高校吹奏楽部へ", "Sound! Euphonium the Movie")])
    assert m.match("Gekijouban Hibike! Euphonium: Kitauji Koukou Suitougakubu e Youkoso") is None
    assert m.match("Sound! Euphonium the Movie: Welcome to the Kitauji High School Concert Band") is None

def test_no_match_returns_none():
    m = OwnershipMatcher([("jf:1", "涼宮ハルヒの憂鬱", "The Melancholy of Haruhi Suzumiya")])
    assert m.match("K-On!") is None

def test_length_mismatch_no_match():
    # Ratio is bounded by 2*min(len)/(len+other_len); a 3-char query vs a
    # 40-char owned title can never reach THRESHOLD, so result must be None.
    long_owned = "Hibike Euphonium Kitauji Koukou Brass Ensemble Monogatari"
    m = OwnershipMatcher([("jf:1", "長いタイトルのテスト用アニメ作品名", long_owned)])
    assert m.match("abc") is None


def _lib(i, fmt="series", seasons=(), **ids):
    return {"id": f"jf:{i}", "title": f"ライブラリ{i}", "title_native": f"ライブラリ{i}", "format": fmt,
            "provider_ids": ids, "seasons": list(seasons)}


def _pool(anilist_id, title="Pool", native=""):
    return {"id": f"al:{anilist_id}", "anilist_id": anilist_id, "title": title, "title_native": native, "owned": 0}


def test_link_library_connects_each_season_by_id():
    from anime_vec.idmap import IdMap
    from anime_vec.match import link_library
    idmap = IdMap([
        {"anilist_id": 1, "themoviedb_id": {"tv": 500}, "season": {"tmdb": 1}},
        {"anilist_id": 2, "themoviedb_id": {"tv": 500}, "season": {"tmdb": 2}},
        {"anilist_id": 3, "themoviedb_id": {"tv": 500}, "season": {"tmdb": 3}},
        {"anilist_id": 9, "themoviedb_id": {"tv": 500}, "season": {"tmdb": 2}},
    ])
    lib = [_lib(1, seasons=[1, 2], tmdb="500")]
    pool = [_pool(1), _pool(2), _pool(3)]
    stats = link_library(lib, pool, idmap)
    assert [(r["owned"], r["library_id"]) for r in pool] == [(1, "jf:1"), (1, "jf:1"), (0, None)]
    assert stats["by_id"] == 2 and stats["by_title"] == 0
    # AniList entry 9 is a season of the library show, but the pool does not have it
    assert stats["missing_ids"] == {9}
    assert stats["unlinked_library_rows"] == []


def test_link_library_uses_the_title_when_the_id_map_has_no_entry():
    from anime_vec.idmap import IdMap
    from anime_vec.match import link_library
    lib = [_lib(1, tmdb="1"), _lib(2, tmdb="2")]
    lib[0]["title_native"] = "ぼくたちのリメイク"
    pool = [_pool(5, "Bokutachi no Remake", "ぼくたちのリメイク"), _pool(6, "Other")]
    stats = link_library(lib, pool, IdMap([]))
    assert pool[0]["library_id"] == "jf:1" and pool[0]["owned"] == 1
    assert pool[1]["library_id"] is None and pool[1]["owned"] == 0
    assert stats["by_title"] == 1 and stats["unlinked_library_rows"] == ["jf:2"]


def test_link_library_removes_an_old_link():
    from anime_vec.match import link_library
    pool = [dict(_pool(5), library_id="jf:gone")]
    link_library([_lib(1)], pool, None)
    assert pool[0]["library_id"] is None


def test_link_library_gives_a_shared_entry_to_the_nearest_title():
    from anime_vec.idmap import IdMap
    from anime_vec.match import link_library
    # The id map has the two movies of the library on one AniList entry
    idmap = IdMap([{"type": "MOVIE", "anilist_id": 1, "themoviedb_id": {"movie": [10, 11]}}])
    lib = [
        dict(_lib(1, fmt="movie", tmdb="11"), title="大室家 dear friends", title_native="大室家 dear friends"),
        dict(_lib(2, fmt="movie", tmdb="10"), title="大室家 dear sisters", title_native="大室家 dear sisters"),
    ]
    pool = [_pool(1, "Oomuro-ke: dear sisters", "大室家 dear sisters"),
            _pool(2, "Oomuro-ke: dear friends", "大室家 dear friends")]
    stats = link_library(lib, pool, idmap)
    assert pool[0]["library_id"] == "jf:2"
    # The other movie has no id link, thus the title match connects it to its own entry
    assert pool[1]["library_id"] == "jf:1"
    assert stats["by_id"] == 1 and stats["by_title"] == 1 and stats["unlinked_library_rows"] == []


def test_link_library_does_not_add_seasons_by_title_to_a_row_with_ids():
    from anime_vec.idmap import IdMap
    from anime_vec.match import link_library
    idmap = IdMap([
        {"type": "TV", "anilist_id": 1, "tvdb_id": 900, "season": {"tvdb": 1}},
        {"type": "TV", "anilist_id": 2, "tvdb_id": 900, "season": {"tvdb": 2}},
    ])
    # The library has only season 1. The two AniList entries have the same title after normalization.
    lib = [dict(_lib(1, seasons=[1], tvdb="900"), title="けいおん!", title_native="けいおん!")]
    pool = [_pool(1, "K-ON!", "けいおん!"), _pool(2, "K-ON!!", "けいおん!!")]
    link_library(lib, pool, idmap)
    assert pool[0]["library_id"] == "jf:1" and pool[0]["owned"] == 1
    assert pool[1]["library_id"] is None and pool[1]["owned"] == 0


def test_link_library_does_not_give_a_movie_to_the_series_row():
    from anime_vec.idmap import IdMap
    from anime_vec.match import link_library
    # The id map lists the movie as season 0 of the series, and the library has a Specials folder
    idmap = IdMap([
        {"type": "TV", "anilist_id": 1, "tvdb_id": 900, "season": {"tvdb": 1}},
        {"type": "MOVIE", "anilist_id": 2, "tvdb_id": 900, "themoviedb_id": {"movie": [70]}, "season": {"tvdb": 0}},
    ])
    lib = [_lib(1, seasons=[0, 1], tvdb="900"), _lib(2, fmt="movie", tmdb="70")]
    pool = [_pool(1), _pool(2)]
    link_library(lib, pool, idmap)
    assert pool[0]["library_id"] == "jf:1"
    assert pool[1]["library_id"] == "jf:2"


def test_title_match_keeps_the_same_title_and_drops_the_near_titles():
    from anime_vec.match import link_library
    lib = [dict(_lib(1, fmt="movie"), title="センコロール", title_native="センコロール")]
    pool = [_pool(1, "Cencoroll", "センコロール"), _pool(2, "Cencoroll 3", "センコロール3")]
    stats = link_library(lib, pool, None)
    assert pool[0]["library_id"] == "jf:1"
    assert pool[1]["library_id"] is None and pool[1]["owned"] == 0
    assert stats["by_title"] == 1


def test_title_match_uses_only_the_nearest_title_when_none_is_the_same():
    from anime_vec.match import link_library
    title = "ガールズアンドパンツァー 最終章 第3話 特別版"
    lib = [dict(_lib(1), title=title, title_native=title)]
    pool = [_pool(3, "GuP 3", "ガールズアンドパンツァー 最終章 第3話 特別編"),
            _pool(4, "GuP 4", "ガールズアンドパンツァー 最終章 第4話 特別編")]
    link_library(lib, pool, None)
    assert pool[0]["library_id"] == "jf:1"
    assert pool[1]["library_id"] is None


def test_matcher_best_gives_the_ratio():
    m = OwnershipMatcher([("jf:1", "ぼくたちのリメイク", "Bokutachi no Remake")])
    assert m.best("Bokutachi no Remake") == ("jf:1", 1.0)
    hit, ratio = m.best("Bokutachi no Remakee")
    assert hit == "jf:1" and 0.92 <= ratio < 1.0
    assert m.best("Other") == (None, 0.0)
