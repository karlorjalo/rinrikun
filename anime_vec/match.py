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
        best_id, best_ratio = None, 0.0
        for t in titles:
            n = normalize_title(t)
            if not n:
                continue
            hit = self.by_key.get(n)
            if hit:
                return hit
            for other, row_id in self.normed:
                if 2 * min(len(n), len(other)) / (len(n) + len(other)) < self.THRESHOLD:
                    continue
                r = difflib.SequenceMatcher(None, n, other).ratio()
                if r > best_ratio:
                    best_id, best_ratio = row_id, r
        return best_id if best_ratio >= self.THRESHOLD else None


def link_library(lib_rows: list[dict], pool_rows: list[dict], idmap=None) -> dict:
    """Connect each pool row that the library has to its library row.

    A connected pool row gets owned = 1 and the id of the library row in `library_id`.
    The id map connects each season that the library has. The title match is the second method:
    it finds the shows that the id map does not have.
    """
    by_anilist = {r["anilist_id"]: r for r in pool_rows}
    for r in pool_rows:
        r["library_id"] = None
    by_id = 0
    missing: set[int] = set()
    if idmap is not None:
        for lib in lib_rows:
            ids = idmap.anilist_ids(lib.get("provider_ids"), lib.get("format") == "movie", lib.get("seasons"))
            missing |= {i for i in ids if i not in by_anilist}
            for i in ids:
                if i in by_anilist:
                    by_anilist[i]["owned"] = 1
                    by_anilist[i]["library_id"] = lib["id"]
                    by_id += 1
    matcher = OwnershipMatcher([(r["id"], r["title_native"], r["title"]) for r in lib_rows])
    by_title = 0
    for r in pool_rows:
        if not r["library_id"]:
            hit = matcher.match(r["title"], r["title_native"])
            if hit:
                r["owned"] = 1
                r["library_id"] = hit
                by_title += 1
    linked_libs = {r["library_id"] for r in pool_rows if r["library_id"]}
    return {"by_id": by_id, "by_title": by_title, "missing_ids": missing,
            "unlinked_library_rows": [r["id"] for r in lib_rows if r["id"] not in linked_libs]}
