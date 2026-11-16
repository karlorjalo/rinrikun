import difflib
import re
import unicodedata


def normalize_title(t: str) -> str:
    if not t:
        return ""
    t = unicodedata.normalize("NFKC", t).lower()
    t = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff\u3400-\u4dbf\uff66-\uff9f]+", "", t)
    if t.startswith("the"):
        t = t[3:]
    return t


class OwnershipMatcher:
    THRESHOLD = 0.92

    def __init__(self, owned: list[tuple[str, str, str]]):
        # owned: list of (id, native_title, english_title)
        self.by_key: dict[str, str] = {}
        self.normed: list[tuple[str, str]] = []
        for row_id, native, english in owned:
            for t in (native, english):
                n = normalize_title(t)
                if not n:
                    continue
                self.by_key.setdefault(n, row_id)
                self.normed.append((n, row_id))

    def match(self, *titles: str) -> str | None:
        return self.best(*titles)[0]

    def best(self, *titles: str) -> tuple[str | None, float]:
        """Return the id of the nearest owned title and the ratio of the match (1.0 = the same title)."""
        best_id, best_ratio = None, 0.0
        for t in titles:
            n = normalize_title(t)
            if not n:
                continue
            hit = self.by_key.get(n)
            if hit:
                return hit, 1.0
            for other, row_id in self.normed:
                if 2 * min(len(n), len(other)) / (len(n) + len(other)) < self.THRESHOLD:
                    continue
                r = difflib.SequenceMatcher(None, n, other).ratio()
                if r > best_ratio:
                    best_id, best_ratio = row_id, r
        return (best_id, best_ratio) if best_ratio >= self.THRESHOLD else (None, 0.0)


def title_similarity(lib: dict, pool: dict) -> float:
    """Return how near the titles of a library row and of a pool row are, from 0 to 1."""
    best = 0.0
    for a in (lib.get("title"), lib.get("title_native")):
        for b in (pool.get("title"), pool.get("title_native")):
            na, nb = normalize_title(a), normalize_title(b)
            if na and nb:
                best = max(best, difflib.SequenceMatcher(None, na, nb).ratio())
    return best


def link_library(lib_rows: list[dict], pool_rows: list[dict], idmap=None) -> dict:
    """Connect each pool row that the library has to its library row.

    A connected pool row gets owned = 1 and the id of the library row in `library_id`.

    The id map is the first method. It connects each season that the library has. If the id map
    gives one AniList entry to two library rows, the library row with the nearest title gets it.

    The title match is the second method. It is only for the library rows that the id map did not
    connect: a title does not tell the season, so it must not add seasons to a row that has ids.
    """
    by_anilist = {r["anilist_id"]: r for r in pool_rows}
    for r in pool_rows:
        r["library_id"] = None
    claims: dict[int, list[dict]] = {}
    missing: set[int] = set()
    if idmap is not None:
        for lib in lib_rows:
            for i in idmap.anilist_ids(lib.get("provider_ids"), lib.get("format") == "movie", lib.get("seasons")):
                if i in by_anilist:
                    claims.setdefault(i, []).append(lib)
                else:
                    missing.add(i)
    by_id = 0
    for i, libs in claims.items():
        pool = by_anilist[i]
        winner = libs[0] if len(libs) == 1 else max(libs, key=lambda lib: title_similarity(lib, pool))
        pool["owned"] = 1
        pool["library_id"] = winner["id"]
        by_id += 1
    linked_libs = {r["library_id"] for r in pool_rows if r["library_id"]}
    matcher = OwnershipMatcher([(r["id"], r["title_native"], r["title"])
                                for r in lib_rows if r["id"] not in linked_libs])
    found: dict[str, list[tuple[float, dict]]] = {}
    for r in pool_rows:
        if not r["library_id"]:
            hit, ratio = matcher.best(r["title"], r["title_native"])
            if hit:
                found.setdefault(hit, []).append((ratio, r))
    by_title = 0
    for lib_id, hits in found.items():
        # A title that is almost the same is frequently a different entry ("Title 3" for "Title").
        # Thus a near match counts only if no pool row has the same title, and then only the nearest.
        same = [r for ratio, r in hits if ratio >= 1.0]
        for r in same or [max(hits, key=lambda h: h[0])[1]]:
            r["owned"] = 1
            r["library_id"] = lib_id
            by_title += 1
    linked_libs = {r["library_id"] for r in pool_rows if r["library_id"]}
    return {"by_id": by_id, "by_title": by_title, "missing_ids": missing,
            "unlinked_library_rows": [r["id"] for r in lib_rows if r["id"] not in linked_libs]}
