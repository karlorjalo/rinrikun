import json
import time
from datetime import datetime
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "anilist_cache"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# The fields of one anime. The page query and the id query use the same fields.
MEDIA_FIELDS = """id title { romaji english native } format seasonYear startDate { year } status episodes genres
tags { name rank } studios(isMain: true) { nodes { name } }
description(asHtml: false) averageScore coverImage { medium }
relations { edges { relationType node { id type } } }
recommendations(sort: RATING_DESC, perPage: 25) { nodes { rating mediaRecommendation { id type } } }"""
QUERY = ("query ($page: Int) { Page(page: $page, perPage: 50) { pageInfo { lastPage } "
         "media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) { " + MEDIA_FIELDS + " } } }")
ID_QUERY = ("query ($ids: [Int]) { Page(perPage: 50) { "
            "media(id_in: $ids, type: ANIME, isAdult: false) { " + MEDIA_FIELDS + " } } }")
# A cached answer without these keys is from an older query
REQUIRED_KEYS = ("relations", "recommendations", "status", "startDate")
# Seconds between two requests. AniList permits 30 requests in one minute.
PAUSE = 2.1
# AniList gives a maximum of 5000 results (100 pages) for one sorted query
MAX_PAGES = 100
# The cache of a page is good for this number of days. The popularity order changes slowly.
PAGE_MAX_AGE_DAYS = 30
# The cache of an anime that is not finished is good for this number of days. Without this limit
# an announced anime stays "not released" in the cache, and the recommendations never show it.
MEDIA_MAX_AGE_DAYS = 7
UNFINISHED = {"NOT_YET_RELEASED", "RELEASING", "HIATUS"}
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
        # The interface shows the romaji title and the Japanese title. Its search also uses the English title.
        "title_english": t.get("english") or "",
        # A movie, an OVA or a special frequently has no season: use the year of its start date
        "year": m.get("seasonYear") or (m.get("startDate") or {}).get("year"),
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
        # FINISHED, RELEASING, NOT_YET_RELEASED, CANCELLED or HIATUS
        "status": m.get("status"),
        "episodes": m.get("episodes"),
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
    time.sleep(PAUSE)


def _age_days(path: Path) -> float:
    return (datetime.now().timestamp() - path.stat().st_mtime) / 86400.0


def _read_cache(cache: Path) -> dict | None:
    """Return the cached page. Return None if the file is corrupt, too old, or from an older query."""
    try:
        page_data = json.loads(cache.read_text(encoding="utf-8"))["data"]["Page"]
        media = page_data["media"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if media and any(key not in media[0] for key in REQUIRED_KEYS):
        return None
    if _age_days(cache) > PAGE_MAX_AGE_DAYS:
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


def related_ids(pool_rows: list[dict]) -> set[int]:
    """Return the AniList ids that the pool points to and does not have.

    These are the shows that users recommend and the other members of the franchises. The most
    popular shows alone do not include them.
    """
    have = {r["anilist_id"] for r in pool_rows}
    wanted: set[int] = set()
    for r in pool_rows:
        wanted.update(other for other, _ in r.get("recommendations") or [])
        wanted.update(r.get("relations") or [])
    return wanted - have


def _read_media(cache: Path) -> dict | None:
    """Return one cached anime. Return None if the file is corrupt or older than the current query."""
    try:
        media = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(media, dict) or any(key not in media for key in REQUIRED_KEYS):
        return None
    if media.get("status") in UNFINISHED and _age_days(cache) > MEDIA_MAX_AGE_DAYS:
        return None
    return media


def _fetch_ids(ids: list[int]) -> list[dict]:
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            data = _graphql_ids(ids)
            if not (data.get("data") or {}).get("Page"):
                raise RuntimeError(f"AniList returned no data for ids {ids[:3]}: {str(data)[:200]}")
            return data["data"]["Page"]["media"]
        except Exception as err:
            last_err = err
            if attempt < 4:
                time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"AniList unreachable for ids {ids[:3]}") from last_err


def fetch_by_ids(ids, force: bool = False) -> list[dict]:
    """Return the rows of the anime with these AniList ids. Each anime has its own cache file.

    AniList does not return adult anime or removed entries. The function remembers these ids,
    so that it does not ask for them again.
    """
    media_dir = CACHE_DIR / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    absent_file = CACHE_DIR / "media_absent.json"
    absent: set[int] = set()
    if absent_file.exists() and not force:
        try:
            absent = set(json.loads(absent_file.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            absent = set()
    found: dict[int, dict] = {}
    todo: list[int] = []
    for i in sorted(set(ids)):
        media = None if force else _read_media(media_dir / f"{i}.json")
        if media is not None:
            found[i] = media
        elif i not in absent:
            todo.append(i)
    for start in range(0, len(todo), 50):
        batch = todo[start:start + 50]
        got = {m["id"]: m for m in _fetch_ids(batch)}
        for i in batch:
            if i in got:
                (media_dir / f"{i}.json").write_text(json.dumps(got[i]), encoding="utf-8")
                found[i] = got[i]
            else:
                absent.add(i)
        absent_file.write_text(json.dumps(sorted(absent)), encoding="utf-8")
        time.sleep(PAUSE)
    return [row_from_media(found[i]) for i in sorted(found)]


def fetch_extras(pool_rows: list[dict], ids, force: bool = False, rounds: int = 3) -> list[dict]:
    """Return the rows of the anime with these ids, and of the anime that the catalog points to.

    The catalog points to an anime with a user recommendation or with a franchise relation.
    A new row can point to more anime, thus the function asks again, for `rounds` times at most.
    """
    wanted = set(ids)
    extra: list[dict] = []
    for _ in range(rounds):
        have = {r["anilist_id"] for r in pool_rows + extra}
        wanted |= related_ids(pool_rows + extra)
        new_rows = fetch_by_ids(wanted - have, force=force)
        if not new_rows:
            break
        extra += new_rows
    return extra


def _post(query: str, variables: dict, timeout: int) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://graphql.anilist.co", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def _graphql(page: int, timeout: int = 60) -> dict:
    return _post(QUERY, {"page": page}, timeout)


def _graphql_ids(ids: list[int], timeout: int = 60) -> dict:
    return _post(ID_QUERY, {"ids": ids}, timeout)
