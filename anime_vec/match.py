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
