import json
import time
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "anilist_cache"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
QUERY = """query ($page: Int) { Page(page: $page, perPage: 50) { pageInfo { lastPage } 
media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) {
id title { romaji english native } format seasonYear genres
tags { name rank } studios(isMain: true) { nodes { name } }
description(asHtml: false) averageScore coverImage { medium }
relations { edges { relationType node { id type } } }
recommendations(sort: RATING_DESC, perPage: 25) { nodes { rating mediaRecommendation { id type } } } } } }"""
MAX_PAGES = 80  # ~4000 anime
# Relation types that connect two entries of the same franchise
FRANCHISE_RELATIONS = {"SEQUEL", "PREQUEL", "PARENT", "SIDE_STORY", "SUMMARY", "ALTERNATIVE"}


def franchise_relations(m: dict) -> list[int]:
    """Return the AniList ids of the anime that are in the same franchise as this media."""
    edges = (m.get("relations") or {}).get("edges") or []
    return sorted({e["node"]["id"] for e in edges
                   if e.get("relationType") in FRANCHISE_RELATIONS
                   and (e.get("node") or {}).get("type") == "ANIME"})


def user_recommendations(m: dict) -> list[list[int]]:
    """Return [anilist id, rating] pairs: the anime that AniList users recommend to people who like this media.

    The rating is the number of users who agree with the recommendation, minus those who do not.
    """
    nodes = (m.get("recommendations") or {}).get("nodes") or []
    out = []
    for node in nodes:
        other = node.get("mediaRecommendation") or {}
        rating = node.get("rating") or 0
        if other.get("type") == "ANIME" and other.get("id") is not None and rating > 0:
            out.append([other["id"], rating])
    return out


def row_from_media(m: dict) -> dict:
    t = m.get("title") or {}
    return {
        "id": f"al:{m['id']}",
        "source": "anilist",
        "title": t.get("romaji") or t.get("english") or t.get("native") or "",
        "title_native": t.get("native") or "",
        "year": m.get("seasonYear"),
        "format": (m.get("format") or "").lower() or None,
        "genres": m.get("genres") or [],
        "tags": [tg["name"] for tg in (m.get("tags") or [])],
        "tag_ranks": [tg.get("rank") or 0 for tg in (m.get("tags") or [])],
        "studios": [s["name"] for s in ((m.get("studios") or {}).get("nodes") or [])],
        "overview": (m.get("description") or "").replace("<br>", "\n"),
        "score": (m.get("averageScore") or 0) / 10.0 or None,
        "owned": 0,
        "tmdbid": None,
        "anilist_id": m["id"],
        "poster": (m.get("coverImage") or {}).get("medium"),
        "relations": franchise_relations(m),
        "recommendations": user_recommendations(m),
    }


def _fetch_page(page: int) -> dict:
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            data = _graphql(page)
            if not (data.get("data") or {}).get("Page"):
                raise RuntimeError(
                    f"AniList returned no data for page {page}: {str(data)[:200]}")
            return data
        except Exception as err:
            last_err = err
            if attempt < 4:
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"AniList unreachable at page {page}") from last_err


def _fetch_and_cache(page: int, cache: Path) -> None:
    cache.write_text(json.dumps(_fetch_page(page)), encoding="utf-8")
    time.sleep(1.2)


def _read_cache(cache: Path) -> dict | None:
    """Return the cached page. Return None if the file is corrupt or older than the current query."""
    try:
        page_data = json.loads(cache.read_text(encoding="utf-8"))["data"]["Page"]
        media = page_data["media"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if media and ("relations" not in media[0] or "recommendations" not in media[0]):
        return None
    return page_data


def fetch_pool(max_pages: int = MAX_PAGES, force: bool = False) -> list[dict]:
    CACHE_DIR.mkdir(exist_ok=True)
    rows: list[dict] = []
    page = 1
    while page <= max_pages:
        cache = CACHE_DIR / f"page_{page}.json"
        page_data = None if force or not cache.exists() else _read_cache(cache)
        if page_data is None:
            cache.unlink(missing_ok=True)
            _fetch_and_cache(page, cache)
            page_data = json.loads(cache.read_text(encoding="utf-8"))["data"]["Page"]
        rows.extend(row_from_media(m) for m in page_data["media"])
        if page >= page_data["pageInfo"]["lastPage"]:
            break
        page += 1
    return rows


def _graphql(page: int, timeout: int = 60) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"page": page}}).encode()
    req = urllib.request.Request("https://graphql.anilist.co", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=timeout))
