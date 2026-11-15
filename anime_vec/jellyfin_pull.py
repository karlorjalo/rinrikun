import json
import urllib.request

import json as _json
import os as _os
from pathlib import Path as _Path

JELLYFIN = "http://localhost:8096"
USER_ID = "F56C05D6-C1CF-4B39-AE56-F7892FD5347C"


def _api_key() -> str:
    key = _os.environ.get("JELLYFIN_API_KEY")
    if key:
        return key
    f = _Path(__file__).resolve().parent.parent / "secrets.json"
    if f.exists():
        return _json.loads(f.read_text(encoding="utf-8"))["jellyfin_api_key"]
    raise RuntimeError("Set JELLYFIN_API_KEY env var or create secrets.json with {\"jellyfin_api_key\": ...}")


API_KEY = _api_key()

FIELDS = "Genres,Tags,Studios,CommunityRating,ProviderIds,ProductionYear,Overview"


def fetch_library() -> list[dict]:
    url = (
        f"{JELLYFIN}/Items?api_key={API_KEY}&UserId={USER_ID}&Recursive=true"
        f"&IncludeItemTypes=Series,Movie&Fields={FIELDS}&Limit=5000"
    )
    items = json.load(urllib.request.urlopen(url, timeout=120))["Items"]
    return [row_from_item(i) for i in items]


def poster_url(item_id: str) -> str:
    return f"{JELLYFIN}/Items/{item_id}/Images/Primary"


def row_from_item(i: dict) -> dict:
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
    }
