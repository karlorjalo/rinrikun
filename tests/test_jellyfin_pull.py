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
    "ProviderIds": {"Tmdb": "86561", "Tvdb": "289882"},
    "DateCreated": "2024-05-01T10:00:00.0000000Z",
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


def test_row_keeps_provider_ids_seasons_and_date():
    r = row_from_item(ITEM, [1, 2])
    assert r["provider_ids"] == {"tmdb": "86561", "tvdb": "289882"}
    assert r["seasons"] == [1, 2]
    assert r["added_at"] == "2024-05-01T10:00:00.0000000Z"
    assert row_from_item(ITEM)["seasons"] == []


def test_seasons_by_series_ignores_virtual_and_unnumbered_seasons():
    from anime_vec.jellyfin_pull import seasons_by_series
    items = [
        {"SeriesId": "a", "IndexNumber": 2, "LocationType": "FileSystem"},
        {"SeriesId": "a", "IndexNumber": 1, "LocationType": "FileSystem"},
        {"SeriesId": "a", "IndexNumber": 3, "LocationType": "Virtual"},
        {"SeriesId": "b", "IndexNumber": None, "LocationType": "FileSystem"},
    ]
    assert seasons_by_series(items) == {"a": [1, 2]}


def test_folder_style_name_is_cleaned():
    from anime_vec.jellyfin_pull import clean_name
    assert clean_name("冴えない彼女の育てかた (2015) [tmdbid-86561]") == "冴えない彼女の育てかた"
    assert clean_name("Title [tvdbid-123]") == "Title"
    assert clean_name("冴えない彼女の育てかた") == "冴えない彼女の育てかた"
    # A year in the middle of a title is part of the title
    assert clean_name("Blade Runner 2049") == "Blade Runner 2049"
    assert clean_name("(2015)") == "(2015)"
    assert row_from_item(dict(ITEM, Name="冴えない彼女の育てかた (2015) [tmdbid-86561]"))["title"] == "冴えない彼女の育てかた"
