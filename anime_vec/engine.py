import numpy as np

from anime_vec.embed import blob_to_vec


class Engine:
    def __init__(self, store):
        self.rows = store.load_rows()
        self.rows = [r for r in self.rows if store.get_embedding(r["id"])]
        self.ids = [r["id"] for r in self.rows]
        self.by_id = {r["id"]: r for r in self.rows}
        M = np.array([blob_to_vec(store.get_embedding(r["id"])) for r in self.rows], dtype=np.float32)
        self.M = M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)
        self.owned_idx = [i for i, r in enumerate(self.rows) if r["owned"]]

    def taste_center(self) -> np.ndarray:
        if not self.owned_idx:
            raise RuntimeError("no owned rows in index — run build.py first")
        v = self.M[self.owned_idx].mean(axis=0)
        return v / max(np.linalg.norm(v), 1e-9)

    def similar_to(self, row_id: str, k: int = 12) -> list[dict]:
        if k <= 0:
            return []
        i = self.ids.index(row_id)
        sims = self.M @ self.M[i]
        order = np.argsort(-sims)
        out = []
        for j in order:
            if j == i:
                continue
            out.append(self._result(j, float(sims[j]), seed=self.rows[i]))
            if len(out) >= k:
                break
        return out

    def recommend(self, k: int = 20, seed_id: str | None = None) -> list[dict]:
        if k <= 0:
            return []
        q = self.M[self.ids.index(seed_id)] if seed_id else self.taste_center()
        sims = self.M @ q
        order = np.argsort(-sims)
        out = []
        for j in order:
            r = self.rows[j]
            if seed_id is not None and self.ids[j] == seed_id:
                continue
            if r["owned"]:
                continue
            out.append(self._result(j, float(sims[j]), seed=None))
            if len(out) >= k:
                break
        return out

    def defining_shows(self, k: int = 15) -> list[dict]:
        c = self.taste_center()
        sims = self.M[self.owned_idx] @ c
        order = np.argsort(-sims)[:k]
        return [self._result(self.owned_idx[j], float(sims[j]), seed=None) for j in order]

    def owned_tag_summary(self, k: int = 20) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for i in self.owned_idx:
            for t in self.rows[i]["tags"]:
                counts[t] = counts.get(t, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:k]

    def owned_genre_summary(self, k: int = 10) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for i in self.owned_idx:
            for g in self.rows[i]["genres"]:
                counts[g] = counts.get(g, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])[:k]

    def owned_era_summary(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for i in self.owned_idx:
            y = self.rows[i]["year"]
            if y:
                era = f"{(int(y) // 10) * 10}s"
                counts[era] = counts.get(era, 0) + 1
        return sorted(counts.items(), key=lambda x: x[0], reverse=True)

    def _result(self, j: int, sim: float, seed) -> dict:
        r = self.rows[j]
        out = dict(r)
        out.pop("text_hash", None)
        out["similarity"] = round(sim * 100, 1)
        if seed is not None:
            out["shared_tags"] = sorted(set(seed["tags"]) & set(r["tags"]))
        else:
            out["shared_tags"] = []
        return out
