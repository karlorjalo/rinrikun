import json
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


def fetch_library() -> list[dict]:
    seasons = seasons_by_series(_items("Season", "ProviderIds"))
    return [row_from_item(i, seasons.get(i["Id"], [])) for i in _items("Series,Movie", FIELDS)]


def poster_url(item_id: str) -> str:
    return f"{JELLYFIN}/Items/{item_id}/Images/Primary"


def row_from_item(i: dict, seasons: list[int] | None = None) -> dict:
    return {
        "id": f"jf:{i['Id']}",
        "source": "library",
        "title": i.get("Name") or "",
        "title_native": i.get("Name") or "",
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
    }
