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


class IdMap:
    def __init__(self, entries: list[dict]):
        # Each index gives a list of (anilist id, season number or None)
        self.tmdb_tv: dict[str, list] = {}
        self.tmdb_movie: dict[str, list] = {}
        self.tvdb: dict[str, list] = {}
        self.imdb: dict[str, list] = {}
        self.mal_of: dict[int, int] = {}
        for e in entries:
            anilist_id = e.get("anilist_id")
            if anilist_id is None:
                continue
            if e.get("mal_id") is not None:
                self.mal_of[anilist_id] = e["mal_id"]
            season = e.get("season") or {}
            tmdb = e.get("themoviedb_id")
            if isinstance(tmdb, dict):
                for key in _as_list(tmdb.get("tv")):
                    self.tmdb_tv.setdefault(str(key), []).append((anilist_id, season.get("tmdb")))
                for key in _as_list(tmdb.get("movie")):
                    self.tmdb_movie.setdefault(str(key), []).append((anilist_id, None))
            elif tmdb is not None:
                index = self.tmdb_movie if (e.get("type") or "").upper() == "MOVIE" else self.tmdb_tv
                for key in _as_list(tmdb):
                    index.setdefault(str(key), []).append((anilist_id, season.get("tmdb")))
            for key in _as_list(e.get("tvdb_id")):
                self.tvdb.setdefault(str(key), []).append((anilist_id, season.get("tvdb")))
            for key in _as_list(e.get("imdb_id")):
                self.imdb.setdefault(str(key), []).append((anilist_id, None))

    def anilist_ids(self, provider_ids: dict, is_movie: bool, seasons: list[int] | None = None) -> set[int]:
        """Return the AniList ids of a library item.

        For a series, an AniList entry is in the result only if its season is in `seasons`
        (the seasons that the library has). If `seasons` is empty, all seasons are in the result.
        """
        ids = provider_ids or {}
        if is_movie:
            found = self.tmdb_movie.get(str(ids.get("tmdb")), []) + self.imdb.get(str(ids.get("imdb")), [])
            return {anilist_id for anilist_id, _ in found}
        found = self.tmdb_tv.get(str(ids.get("tmdb")), []) + self.tvdb.get(str(ids.get("tvdb")), [])
        if not seasons:
            return {anilist_id for anilist_id, _ in found}
        return {anilist_id for anilist_id, season in found if season in seasons}
