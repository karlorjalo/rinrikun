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

        # Identify pool rows that match library rows to avoid duplicating watched items
        lib_rows = [r for r in self.rows if r["source"] == "library"]
        self.duplicate_of: dict[str, str] = {}
        self.counterparts: dict[str, list[str]] = {}
        if lib_rows:
            from anime_vec.match import OwnershipMatcher
            matcher = OwnershipMatcher([(r["id"], r["title_native"], r["title"]) for r in lib_rows])
            for r in self.rows:
                if r["source"] == "anilist" and r.get("owned") and not r.get("manual_watched"):
                    hit = matcher.match(r["title"], r["title_native"])
                    if hit:
                        self.duplicate_of[r["id"]] = hit
                        self.counterparts.setdefault(hit, []).append(r["id"])
                        self.counterparts.setdefault(r["id"], []).append(hit)

        # Synchronize weights across counterparts on load
        for sid, tier_info in store.get_weights().items():
            tier = tier_info.get("tier")
            w = tier_info.get("weight", 1.0)
            if tier:
                for c_id in self.counterparts.get(sid, []):
                    if c_id in self.by_id and not self.by_id[c_id].get("tier"):
                        self.by_id[c_id]["tier"] = tier
                        self.by_id[c_id]["weight"] = w

        self.owned_idx = [i for i, r in enumerate(self.rows) if r["owned"] and r["id"] not in self.duplicate_of]
        self.weights = {r["id"]: r.get("weight", 1.0) for r in self.rows if r.get("tier") is not None}

        # Compute 2D projection for vector space visualization
        if len(self.rows) >= 2 and self.M.ndim == 2 and self.M.shape[1] >= 2:
            self.mean_M = self.M.mean(axis=0)
            X = self.M - self.mean_M
            cov = X.T @ X
            _, v = np.linalg.eigh(cov)
            self.pca_basis = v[:, -2:]
            raw_coords = X @ self.pca_basis
            self.c_min = raw_coords.min(axis=0)
            self.c_max = raw_coords.max(axis=0)
            self.c_span = np.maximum(self.c_max - self.c_min, 1e-6)
            self.coords_2d = ((raw_coords - self.c_min) / self.c_span).astype(np.float32)
        else:
            dim = self.M.shape[1] if self.M.ndim == 2 else 0
            self.mean_M = np.zeros(dim, dtype=np.float32)
            self.pca_basis = np.zeros((dim, 2), dtype=np.float32)
            self.c_min = np.zeros(2, dtype=np.float32)
            self.c_span = np.ones(2, dtype=np.float32)
            self.coords_2d = np.zeros((len(self.rows), 2), dtype=np.float32)

    def taste_center(self) -> np.ndarray:
        if not self.owned_idx:
            raise RuntimeError("no owned rows in index — run build.py first")
        has_rated = any(self.ids[i] in self.weights for i in self.owned_idx)
        default_weight = 0.0 if has_rated else 1.0
        weights = np.array([self.weights.get(self.ids[i], default_weight) for i in self.owned_idx], dtype=np.float32)
        if np.all(weights <= 0):
            weights = np.ones(len(self.owned_idx), dtype=np.float32)
        v = (self.M[self.owned_idx] * weights[:, None]).sum(axis=0)
        return v / max(np.linalg.norm(v), 1e-9)

    def similar_to(self, row_id: str, k: int = 24) -> list[dict]:
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

    def recommend(self, k: int = 20, seed_id: str | None = None, mode: str = "hybrid") -> list[dict]:
        if k <= 0:
            return []

        if seed_id is not None:
            if seed_id not in self.by_id:
                raise KeyError(f"unknown seed id {seed_id}")
            q = self.M[self.ids.index(seed_id)]
            sims = self.M @ q
            order = np.argsort(-sims)
            out = []
            for j in order:
                r = self.rows[j]
                if self.ids[j] == seed_id or r["owned"]:
                    continue
                out.append(self._result(j, float(sims[j]), seed=None))
                if len(out) >= k:
                    break
            return out

        cand_indices = [j for j, r in enumerate(self.rows) if not r["owned"]]
        if not cand_indices:
            return []

        cand_M = self.M[cand_indices]
        c = self.taste_center()
        c_sims = cand_M @ c

        s_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "S"]
        if not s_indices:
            s_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "A"]
        if not s_indices:
            s_indices = self.owned_idx

        d_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "D"]

        S_M = self.M[s_indices]
        s_all_sims = cand_M @ S_M.T
        s_best_idx = s_all_sims.argmax(axis=1)
        s_peak_sims = s_all_sims.max(axis=1)

        d_penalty = np.zeros(len(cand_indices), dtype=np.float32)
        if d_indices:
            D_M = self.M[d_indices]
            d_penalty = np.maximum(0.0, (cand_M @ D_M.T).max(axis=1))

        mode = (mode or "hybrid").lower()
        if mode == "center":
            order = np.argsort(-c_sims)[:k]
            out = []
            for rank in order:
                orig_idx = cand_indices[rank]
                out.append(self._result(orig_idx, float(c_sims[rank]), seed=None))
            return out

        elif mode == "peak":
            scores = s_peak_sims - 0.25 * d_penalty
            order = np.argsort(-scores)[:k]
            out = []
            for rank in order:
                orig_idx = cand_indices[rank]
                fav = self.rows[s_indices[s_best_idx[rank]]]
                fav_title = fav.get("title_native") or fav.get("title")
                out.append(self._result(orig_idx, float(s_peak_sims[rank]), seed=None, matched_favorite=fav_title))
            return out

        elif mode == "diverse":
            base_scores = 0.5 * c_sims + 0.5 * s_peak_sims - 0.2 * d_penalty
            selected = []
            unselected = set(range(len(cand_indices)))
            lambda_param = 0.65
            limit = min(k, len(cand_indices))

            for _ in range(limit):
                if not selected:
                    best = int(np.argmax(base_scores))
                else:
                    unsel_list = list(unselected)
                    sel_M = cand_M[selected]
                    sims_to_sel = (cand_M[unsel_list] @ sel_M.T).max(axis=1)
                    mmr = lambda_param * base_scores[unsel_list] - (1.0 - lambda_param) * sims_to_sel
                    best = unsel_list[int(np.argmax(mmr))]
                selected.append(best)
                unselected.remove(best)

            out = []
            for sel_idx in selected:
                orig_idx = cand_indices[sel_idx]
                sim_val = float(0.5 * c_sims[sel_idx] + 0.5 * s_peak_sims[sel_idx])
                fav = self.rows[s_indices[s_best_idx[sel_idx]]]
                fav_title = fav.get("title_native") or fav.get("title")
                out.append(self._result(orig_idx, sim_val, seed=None, matched_favorite=fav_title))
            return out

        else: # "hybrid"
            scores = 0.5 * c_sims + 0.5 * s_peak_sims - 0.2 * d_penalty
            order = np.argsort(-scores)[:k]
            out = []
            for rank in order:
                orig_idx = cand_indices[rank]
                sim_val = float(0.5 * c_sims[rank] + 0.5 * s_peak_sims[rank])
                fav = self.rows[s_indices[s_best_idx[rank]]]
                fav_title = fav.get("title_native") or fav.get("title")
                out.append(self._result(orig_idx, sim_val, seed=None, matched_favorite=fav_title))
            return out

    def defining_shows(self, k: int = 15) -> list[dict]:
        c = self.taste_center()
        sims = self.M[self.owned_idx] @ c
        has_rated = any(self.rows[i].get("tier") is not None for i in self.owned_idx)
        if not has_rated:
            order = np.argsort(-sims)[:k]
            return [self._result(self.owned_idx[j], float(sims[j]), seed=None) for j in order]

        scored = []
        fallback = []
        for j, i in enumerate(self.owned_idx):
            r = self.rows[i]
            tier = r.get("tier")
            sim = float(sims[j])
            if tier in ("S", "A", "B"):
                w = self.weights.get(self.ids[i], 1.0)
                scored.append((w * sim, j, sim))
            elif tier not in ("C", "D"):
                fallback.append((sim, j, sim))

        scored.sort(key=lambda x: -x[0])
        fallback.sort(key=lambda x: -x[0])
        combined = scored + fallback
        return [self._result(self.owned_idx[j], sim, seed=None) for _, j, sim in combined[:k]]

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
        target_ids = [show_id] + self.counterparts.get(show_id, [])
        tier_upper = tier.upper() if tier else None
        w = TIER_WEIGHTS.get(tier_upper, 1.0) if tier_upper else 1.0

        for sid in target_ids:
            if sid not in self.by_id:
                continue
            r = self.by_id[sid]
            if tier_upper:
                self.store.set_weight(sid, tier_upper, w)
                r["tier"] = tier_upper
                r["weight"] = w
                self.weights[sid] = w
            else:
                self.store.delete_weight(sid)
                r["tier"] = None
                r["weight"] = 1.0
                self.weights.pop(sid, None)

        primary = self.by_id[show_id]
        return {"id": show_id, "tier": primary["tier"], "weight": primary["weight"]}

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
        for i in self.owned_idx:
            r = self.rows[i]
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

    def _result(self, j: int, sim: float, seed=None, matched_favorite: str | None = None) -> dict:
        r = self.rows[j]
        out = dict(r)
        out.pop("text_hash", None)
        out["similarity"] = round(sim * 100, 1)
        if seed is not None:
            out["shared_tags"] = sorted(set(seed["tags"]) & set(r["tags"]))
        else:
            out["shared_tags"] = []
        if matched_favorite:
            out["matched_favorite"] = matched_favorite
        return out

    def project_2d(self, vec: np.ndarray) -> tuple[float, float]:
        if len(self.rows) < 2 or self.M.ndim != 2 or self.M.shape[1] < 2:
            return (0.5, 0.5)
        raw = (vec - self.mean_M) @ self.pca_basis
        proj = (raw - self.c_min) / self.c_span
        return (float(np.clip(proj[0], 0.0, 1.0)), float(np.clip(proj[1], 0.0, 1.0)))

    def get_vector_map(self) -> dict:
        c = self.taste_center() if self.owned_idx else None
        c_proj = self.project_2d(c) if c is not None else None
        points = []
        for i, r in enumerate(self.rows):
            points.append({
                "id": r["id"],
                "x": round(float(self.coords_2d[i, 0]), 3),
                "y": round(float(self.coords_2d[i, 1]), 3),
                "title": r.get("title", ""),
                "title_native": r.get("title_native", ""),
                "year": r.get("year"),
                "genres": r.get("genres", [])[:2],
                "owned": r.get("owned", 0),
                "tier": r.get("tier"),
            })
        return {
            "center": {"x": round(c_proj[0], 3), "y": round(c_proj[1], 3)} if c_proj else None,
            "points": points,
        }
