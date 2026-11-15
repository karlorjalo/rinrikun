import numpy as np

from anime_vec.embed import blob_to_vec
from anime_vec.store import TIER_WEIGHTS


class Engine:
    def __init__(self, store):
        self.store = store
        self.rows = store.load_rows()
        self.rows = [r for r in self.rows if store.get_embedding(r["id"])]
        self.ids = [r["id"] for r in self.rows]
        self.by_id = {r["id"]: r for r in self.rows}
        M = np.array([blob_to_vec(store.get_embedding(r["id"])) for r in self.rows], dtype=np.float32)
        self.M = M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)
        self.owned_idx = [i for i, r in enumerate(self.rows) if r["owned"]]
        self.weights = {r["id"]: r.get("weight", 1.0) for r in self.rows if r.get("tier") is not None}

    def taste_center(self) -> np.ndarray:
        if not self.owned_idx:
            raise RuntimeError("no owned rows in index — run build.py first")
        weights = np.array([self.weights.get(self.ids[i], 1.0) for i in self.owned_idx], dtype=np.float32)
        if np.all(weights <= 0):
            weights = np.ones(len(self.owned_idx), dtype=np.float32)
        v = (self.M[self.owned_idx] * weights[:, None]).sum(axis=0)
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

    def set_watched(self, show_id: str, watched: bool):
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        self.store.set_manual_watched(show_id, watched)
        r = self.by_id[show_id]
        r["manual_watched"] = 1 if watched else 0
        if r["source"] != "library":
            r["owned"] = 1 if watched else 0
        self.owned_idx = [i for i, row in enumerate(self.rows) if row["owned"]]

    def manual_shows(self) -> list[dict]:
        manual_ids = self.store.get_manual_watched_ids()
        c = self.taste_center() if self.owned_idx else None
        out = []
        for i, r in enumerate(self.rows):
            if r["id"] in manual_ids:
                sim = float(self.M[i] @ c) if c is not None else 0.0
                out.append(self._result(i, sim, seed=None))
        return out

    def set_show_tier(self, show_id: str, tier: str | None) -> dict:
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        r = self.by_id[show_id]
        if tier:
            tier_upper = tier.upper()
            w = TIER_WEIGHTS.get(tier_upper, 1.0)
            self.store.set_weight(show_id, tier_upper, w)
            r["tier"] = tier_upper
            r["weight"] = w
            self.weights[show_id] = w
        else:
            self.store.delete_weight(show_id)
            r["tier"] = None
            r["weight"] = 1.0
            self.weights.pop(show_id, None)
        return {"id": show_id, "tier": r["tier"], "weight": r["weight"]}

    def review_queue(self, unrated_only: bool = False) -> list[dict]:
        c = self.taste_center() if self.owned_idx else None
        owned_rows = [self.rows[i] for i in self.owned_idx]
        if unrated_only:
            owned_rows = [r for r in owned_rows if r.get("tier") is None]

        def sort_key(r):
            is_unrated = 0 if r.get("tier") is None else 1
            idx = self.ids.index(r["id"])
            sim = float(self.M[idx] @ c) if c is not None else 0.0
            return (is_unrated, -sim)

        sorted_rows = sorted(owned_rows, key=sort_key)
        out = []
        for r in sorted_rows:
            idx = self.ids.index(r["id"])
            sim = float(self.M[idx] @ c) if c is not None else 0.0
            out.append(self._result(idx, sim, seed=None))
        return out

    def rated_shows(self) -> list[dict]:
        c = self.taste_center() if self.owned_idx else None
        out = []
        for i, r in enumerate(self.rows):
            if r.get("tier") is not None:
                sim = float(self.M[i] @ c) if c is not None else 0.0
                out.append(self._result(i, sim, seed=None))
        tier_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        return sorted(out, key=lambda x: (tier_order.get(x.get("tier"), 99), -(x.get("similarity") or 0.0)))

    def tier_summary(self) -> dict[str, int]:
        counts = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0, "unrated": 0}
        for i in self.owned_idx:
            tier = self.rows[i].get("tier")
            if tier and tier in counts:
                counts[tier] += 1
            else:
                counts["unrated"] += 1
        return counts

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
