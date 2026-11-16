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
