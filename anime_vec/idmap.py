"""Map the provider ids of a Jellyfin item (TMDB, TVDB, IMDb) to AniList ids.

Jellyfin gives one item for a series. AniList has one entry for each season. A title match finds
one of these entries at most, and it fails when the two titles are different. The public id map
of the Fribb/anime-lists project connects the ids, with the season number of each AniList entry.
"""
import json
import time
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
CACHE = Path(__file__).resolve().parent.parent / "idmap_cache" / "anime-list-full.json"
MAX_AGE_DAYS = 7


def load_entries(force: bool = False) -> list[dict]:
    """Return the entries of the id map. The file stays in a cache for MAX_AGE_DAYS."""
    fresh = CACHE.exists() and time.time() - CACHE.stat().st_mtime < MAX_AGE_DAYS * 86400
    if force or not fresh:
        try:
            data = urllib.request.urlopen(URL, timeout=120).read()
            json.loads(data)
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_bytes(data)
        except Exception:
            # An old cache is better than no id map
            if not CACHE.exists():
                raise
    return json.loads(CACHE.read_text(encoding="utf-8"))


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _season_number(season: dict, kind: str) -> int:
    """Return the season number of an entry of the id map. Season 0 is a special, an OVA or a movie.

    The id map can have one number from TVDB and one from TMDB. TMDB frequently has season 1 for
    all seasons of a series, and the season folders of a library use the TVDB numbers. Thus the
    TVDB number is the first choice. An entry without a number is season 1 if it is a TV series.
    """
    for source in ("tvdb", "tmdb"):
        if season.get(source) is not None:
            return season[source]
    return 1 if kind == "TV" else 0


class IdMap:
    def __init__(self, entries: list[dict]):
        # Each index gives a list of (anilist id, season number)
        self.tmdb_tv: dict[str, list] = {}
        self.tmdb_movie: dict[str, list] = {}
        self.tvdb: dict[str, list] = {}
        self.imdb: dict[str, list] = {}
        self.mal_of: dict[int, int] = {}
        # All AniList ids of the id map: the anime that the other anime databases know
        self.all_ids: set[int] = set()
        for e in entries:
            anilist_id = e.get("anilist_id")
            if anilist_id is None:
                continue
            self.all_ids.add(anilist_id)
            if e.get("mal_id") is not None:
                self.mal_of[anilist_id] = e["mal_id"]
            kind = (e.get("type") or "").upper()
            item = (anilist_id, _season_number(e.get("season") or {}, kind))
            tmdb = e.get("themoviedb_id")
            if isinstance(tmdb, dict):
                for key in _as_list(tmdb.get("tv")):
                    self.tmdb_tv.setdefault(str(key), []).append(item)
                for key in _as_list(tmdb.get("movie")):
                    self.tmdb_movie.setdefault(str(key), []).append(item)
            elif tmdb is not None:
                index = self.tmdb_movie if kind == "MOVIE" else self.tmdb_tv
                for key in _as_list(tmdb):
                    index.setdefault(str(key), []).append(item)
            for key in _as_list(e.get("tvdb_id")):
                self.tvdb.setdefault(str(key), []).append(item)
            for key in _as_list(e.get("imdb_id")):
                self.imdb.setdefault(str(key), []).append(item)

    def anilist_ids(self, provider_ids: dict, is_movie: bool, seasons: list[int] | None = None) -> set[int]:
        """Return the AniList ids of a library item.

        For a series, `seasons` are the seasons that the library has. An AniList entry is in the
        result if its season is not later than the last of these seasons: a library that has only
        season 3 also gives seasons 1 and 2, because the user watched them before season 3.
        If `seasons` is empty, all seasons are in the result.

        A series never gives the specials, OVAs and movies that the id map lists as season 0.
        A Specials folder in the library does not say which of them it holds, and a movie has its
        own library item.
        """
        ids = provider_ids or {}
        if is_movie:
            found = self.tmdb_movie.get(str(ids.get("tmdb")), []) + self.imdb.get(str(ids.get("imdb")), [])
            return {anilist_id for anilist_id, _ in found}

        regular = {s for s in (seasons or []) if s != 0}
        if seasons and not regular:
            # The library has only a Specials folder
            return set()
        last = max(regular) if regular else None
        found = self.tmdb_tv.get(str(ids.get("tmdb")), []) + self.tvdb.get(str(ids.get("tvdb")), [])
        return {anilist_id for anilist_id, season in found
                if season != 0 and (last is None or season <= last)}
