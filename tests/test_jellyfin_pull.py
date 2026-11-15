from anime_vec.jellyfin_pull import row_from_item

ITEM = {
    "Id": "d6e39268717edda9368827f7ccb45a8a",
    "Name": "冴えない彼女の育てかた",
    "SeriesName": None,
    "ProductionYear": 2015,
    "Type": "Series",
    "Genres": ["アニメーション", "コメディ"],
    "Tags": ["school", "comedy"],
    "Studios": [{"Name": "A-1 Pictures"}],
    "Overview": "Tomoya is an otaku...",
    "CommunityRating": 8.1,
    "ProviderIds": {"Tmdb": "86561"},
}

def test_row_from_item():
    r = row_from_item(ITEM)
    assert r["id"] == "jf:d6e39268717edda9368827f7ccb45a8a"
    assert r["title"] == "冴えない彼女の育てかた"
    assert r["year"] == 2015
    assert r["genres"] == ["アニメーション", "コメディ"]
    assert r["studios"] == ["A-1 Pictures"]
    assert r["score"] == 8.1
    assert r["tmdbid"] == "86561"
    assert r["owned"] == 1
