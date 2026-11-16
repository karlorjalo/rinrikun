import json
import re
import urllib.request

import json as _json
import os as _os
from pathlib import Path as _Path

JELLYFIN = "http://localhost:8096"


def _secrets() -> dict:
    f = _Path(__file__).resolve().parent.parent / "secrets.json"
    d = _json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    d.setdefault("jellyfin_api_key", _os.environ.get("JELLYFIN_API_KEY"))
    d.setdefault("jellyfin_user_id", _os.environ.get("JELLYFIN_USER_ID"))
    missing = [k for k in ("jellyfin_api_key", "jellyfin_user_id") if not d[k]]
    if missing:
        raise RuntimeError(f"missing secrets: {missing} — set env vars or secrets.json")
    return d


API_KEY = _secrets()["jellyfin_api_key"]
USER_ID = _secrets()["jellyfin_user_id"]

FIELDS = "Genres,Tags,Studios,CommunityRating,ProviderIds,ProductionYear,Overview,DateCreated"


def _items(item_types: str, fields: str) -> list[dict]:
    url = (
        f"{JELLYFIN}/Items?api_key={API_KEY}&UserId={USER_ID}&Recursive=true"
        f"&IncludeItemTypes={item_types}&Fields={fields}&Limit=5000"
    )
    return json.load(urllib.request.urlopen(url, timeout=120))["Items"]


def seasons_by_series(season_items: list[dict]) -> dict[str, list[int]]:
    """Return the season numbers that the library has for each series id."""
    out: dict[str, set[int]] = {}
    for s in season_items:
        # A virtual season has no files. A season without a number cannot be matched.
        if s.get("IndexNumber") is None or s.get("LocationType") == "Virtual":
            continue
        out.setdefault(s["SeriesId"], set()).add(s["IndexNumber"])
    return {k: sorted(v) for k, v in out.items()}


def merge_same_items(items: list[dict]) -> list[dict]:
    """Return one item for each show.

    Jellyfin makes two items when a movie folder has two files, or when one series is in two
    folders. The two items have the same type and the same TMDB id. The item that the library
    got first stays. Its "MergedIds" are the ids of the other items of the same show.
    """
    first: dict[tuple, dict] = {}
    out = []
    for item in sorted(items, key=lambda i: i.get("DateCreated") or ""):
        tmdb = (item.get("ProviderIds") or {}).get("Tmdb")
        key = (item.get("Type"), tmdb)
        if tmdb and key in first:
            first[key].setdefault("MergedIds", []).append(item["Id"])
            continue
        item = dict(item)
        if tmdb:
            first[key] = item
        out.append(item)
    return out


def fetch_library() -> list[dict]:
    seasons = seasons_by_series(_items("Season", "ProviderIds"))
    rows = []
    for item in merge_same_items(_items("Series,Movie", FIELDS)):
        own = set(seasons.get(item["Id"], []))
        for other in item.get("MergedIds") or []:
            own |= set(seasons.get(other, []))
        rows.append(row_from_item(item, sorted(own)))
    return rows


def poster_url(item_id: str) -> str:
    return f"{JELLYFIN}/Items/{item_id}/Images/Primary"


def clean_name(name: str) -> str:
    """Remove the folder suffix from a title, for example "Title (2015) [tmdbid-86561]".

    Jellyfin uses the folder name as the title of an item that has no metadata.
    """
    cleaned = re.sub(r"\s*\[(tmdbid|tvdbid|imdbid)-[^\]]+\]", "", name or "")
    cleaned = re.sub(r"\s*\((19|20)\d{2}\)\s*$", "", cleaned).strip()
    return cleaned or (name or "")


def row_from_item(i: dict, seasons: list[int] | None = None) -> dict:
    return {
        "id": f"jf:{i['Id']}",
        "source": "library",
        "title": clean_name(i.get("Name")),
        "title_native": clean_name(i.get("Name")),
        "year": i.get("ProductionYear"),
        "format": i.get("Type", "").lower() or None,
        "genres": i.get("Genres") or [],
        "tags": i.get("Tags") or [],
        "tag_ranks": [],
        "studios": [s["Name"] for s in (i.get("Studios") or [])],
        "overview": i.get("Overview") or "",
        "score": i.get("CommunityRating"),
        "owned": 1,
        "tmdbid": (i.get("ProviderIds") or {}).get("Tmdb"),
        "anilist_id": None,
        "poster": poster_url(i["Id"]),
        # The ids of the item at TMDB, TVDB and IMDb, with lower-case keys
        "provider_ids": {k.lower(): v for k, v in (i.get("ProviderIds") or {}).items()},
        "seasons": list(seasons or []),
        "added_at": i.get("DateCreated"),
        # The library rows of the other Jellyfin items of the same show. The build uses their tiers.
        "merged_ids": [f"jf:{other}" for other in i.get("MergedIds") or []],
    }
