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
