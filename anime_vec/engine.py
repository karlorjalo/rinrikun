import hashlib

import numpy as np

from anime_vec import layout
from anime_vec.embed import blob_to_vec
from anime_vec.store import TIER_WEIGHTS


# Centered cosine similarity at which the D-tier penalty starts. Random pairs are near 0.0.
D_SIM_START = 0.5


def display_similarity(sim: float) -> float:
    """Map a centered cosine (-1 to 1) to a percentage (0 to 100) for the UI."""
    return round((1.0 + sim) * 50.0, 1)


# Number of nearest liked shows that give the score of a candidate
LIKED_K = 5
# Weight of the D-tier penalty in the hybrid score, in standard deviations
D_PENALTY = 1.0
# Weight of the AniList user recommendations in the hybrid score, relative to the content score
LINK_WEIGHT = 0.5
# Weight of the similarity to the C-tier and D-tier shows, which decreases the hybrid score
DISLIKE_WEIGHT = 0.5
# Number of nearest disliked shows that give the dislike score of a candidate
DISLIKED_K = 3


def _zscore(x: np.ndarray) -> np.ndarray:
    sd = float(x.std())
    return (x - x.mean()) / sd if sd > 1e-9 else np.zeros_like(x)


def _knn_score(cand: np.ndarray, liked: np.ndarray, weights: np.ndarray, k: int = LIKED_K):
    """Score each candidate by the mean weighted similarity to its k nearest liked shows.

    Return the scores, the mean similarity without weights, and the index of the best liked show.
    """
    sims = cand @ liked.T
    weighted = sims * weights[None, :]
    k = min(k, liked.shape[0])
    top = np.argpartition(-weighted, k - 1, axis=1)[:, :k]
    score = np.take_along_axis(weighted, top, axis=1).mean(axis=1)
    shown = np.take_along_axis(sims, top, axis=1).mean(axis=1)
    return score, shown, weighted.argmax(axis=1)


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

        # Effective embedding matrix: bridge library rows to the vectors of their AniList counterparts
        self.pos = {rid: i for i, rid in enumerate(self.ids)}
        bridged = np.array(self.M, copy=True)
        for i, r in enumerate(self.rows):
            if r["source"] == "library" and r["id"] in self.counterparts:
                for cp_id in self.counterparts[r["id"]]:
                    if cp_id in self.by_id:
                        bridged[i] = self.M[self.pos[cp_id]]
                        break

        # Text embeddings share one large common direction, which hides the differences between shows.
        # Subtract the corpus mean and normalize again, so that cosine similarity measures only the differences.
        unique = [i for i, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]
        self.corpus_mean = bridged[unique].mean(axis=0) if unique else np.zeros(bridged.shape[1:], dtype=np.float32)
        centered = bridged - self.corpus_mean
        self.eff_M = centered / np.clip(np.linalg.norm(centered, axis=1, keepdims=True), 1e-9, None)
        self.tag_M = self._build_tag_matrix()
        self.franchise = self._build_franchises()
        self._build_links()

        self.coords_2d = self._build_layout(unique)
        self.regions = self._build_regions(unique)

    def _build_regions(self, unique: list[int]) -> list[dict]:
        """Divide the map into regions and name each region after its most typical tags.

        The directions on a t-SNE map have no meaning. The labels tell the user what a region contains.
        """
        if len(unique) < layout.REGION_MIN_ROWS or not self.tag_names:
            return []
        P = self.coords_2d[unique]
        T = self.tag_M[unique]
        labels, _ = layout.kmeans(P, layout.REGION_COUNT)
        corpus_mean = T.mean(axis=0)
        regions = []
        for c in range(int(labels.max()) + 1):
            members = np.where(labels == c)[0]
            if len(members) < layout.REGION_MIN_SIZE:
                continue
            # The tags that are much more frequent in this region than in the full index
            lift = T[members].mean(axis=0) - corpus_mean
            top = [j for j in np.argsort(-lift)[:2] if lift[j] > 0]
            if not top:
                continue
            x, y = P[members].mean(axis=0)
            regions.append({"x": round(float(x), 4), "y": round(float(y), 4),
                            "label": " · ".join(self.tag_names[j] for j in top), "count": int(len(members))})
        return regions

    def _build_layout(self, unique: list[int]) -> np.ndarray:
        """Return the 2D map position of each row, in the square from 0 to 1."""
        coords = np.full((len(self.rows), 2), 0.5, dtype=np.float32)
        if len(unique) >= 2:
            X = self.eff_M[unique]
            if layout.can_use_tsne(len(unique)):
                # t-SNE is slow, thus keep the result in the database until the embeddings change
                ids = [self.ids[i] for i in unique]
                signature = hashlib.sha1(
                    layout.VERSION.encode() + "\n".join(ids).encode() + np.ascontiguousarray(X).tobytes()
                ).hexdigest()
                cached = self.store.get_layout(signature)
                if cached is not None and all(i in cached for i in ids):
                    points = np.array([cached[i] for i in ids], dtype=np.float32)
                else:
                    points = layout.fit_unit_square(layout.tsne_layout(X))
                    self.store.save_layout(signature, dict(zip(ids, points.tolist())))
            else:
                points = layout.fit_unit_square(layout.pca_layout(X))
            coords[unique] = points
        # A duplicate pool row is at the position of its library row
        for dup_id, lib_id in self.duplicate_of.items():
            coords[self.pos[dup_id]] = coords[self.pos[lib_id]]
        return coords

    def taste_center(self) -> np.ndarray:
        if not self.owned_idx:
            raise RuntimeError("no owned rows in index — run build.py first")
        has_rated = any(self.ids[i] in self.weights for i in self.owned_idx)
        default_weight = 0.0 if has_rated else 1.0
        weights = np.array([self.weights.get(self.ids[i], default_weight) for i in self.owned_idx], dtype=np.float32)
        if np.all(weights <= 0):
            weights = np.ones(len(self.owned_idx), dtype=np.float32)
        v = (self.eff_M[self.owned_idx] * weights[:, None]).sum(axis=0)
        return v / max(np.linalg.norm(v), 1e-9)

    def similar_to(self, row_id: str, k: int = 24) -> list[dict]:
        if k <= 0:
            return []
        if row_id not in self.by_id:
            raise ValueError(f"unknown id {row_id}")
        i = self.pos[row_id]
        sims = self.eff_M @ self.eff_M[i]
        order = np.argsort(-sims)
        out = []
        exclude_ids = {row_id} | set(self.counterparts.get(row_id, []))
        for j in order:
            if self.ids[j] in exclude_ids:
                continue
            out.append(self._result(j, float(sims[j]), seed=self.rows[i]))
            if len(out) >= k:
                break
        return out

    def owned_franchises(self) -> set[str]:
        return {self.franchise[self.ids[i]] for i in self.owned_idx}

    def recommend(self, k: int = 20, seed_id: str | None = None, mode: str = "hybrid",
                  new_only: bool = False) -> list[dict]:
        """Return the recommendations. Each result says if the user owns a show of the same franchise.

        If new_only is true, the list has no shows from franchises that the user owns.
        """
        owned = self.owned_franchises()
        out = self._recommend(k, seed_id, mode, owned if new_only else set())
        for r in out:
            r["franchise_owned"] = self.franchise[r["id"]] in owned
        return out

    def _recommend(self, k: int, seed_id: str | None, mode: str, skip: set[str]) -> list[dict]:
        if k <= 0:
            return []

        if seed_id is not None:
            if seed_id not in self.by_id:
                raise KeyError(f"unknown seed id {seed_id}")
            q = self.eff_M[self.pos[seed_id]]
            sims = self.eff_M @ q
            exclude_ids = {seed_id} | set(self.counterparts.get(seed_id, []))
            allowed = [j for j in np.argsort(-sims)
                       if self.ids[j] not in exclude_ids and not self.rows[j]["owned"]
                       and self.franchise[self.ids[j]] not in skip]
            return [self._result(j, float(sims[j]), seed=None) for j in self._one_per_franchise(allowed, k)]

        cand_indices = [j for j, r in enumerate(self.rows)
                        if not r["owned"] and r["id"] not in self.duplicate_of and self.franchise[r["id"]] not in skip]
        if not cand_indices:
            return []

        cand_M = self.eff_M[cand_indices]
        mode = (mode or "hybrid").lower()

        if mode == "center":
            c_sims = cand_M @ self.taste_center()
            order = self._one_per_franchise(np.argsort(-c_sims), k, cand_indices)
            return [self._result(cand_indices[j], float(c_sims[j]), seed=None) for j in order]

        d_penalty = np.zeros(len(cand_indices), dtype=np.float32)
        d_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "D"]
        if d_indices:
            raw_d_sims = (cand_M @ self.eff_M[d_indices].T).max(axis=1)
            # Soft threshold: the penalty starts when the similarity to a D-tier show is more than D_SIM_START
            d_penalty = np.maximum(0.0, raw_d_sims - D_SIM_START) / (1.0 - D_SIM_START)

        if mode == "peak":
            s_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "S"]
            if not s_indices:
                s_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "A"]
            if not s_indices:
                s_indices = self.owned_idx
            s_all_sims = cand_M @ self.eff_M[s_indices].T
            s_best_idx = s_all_sims.argmax(axis=1)
            s_peak_sims = s_all_sims.max(axis=1)
            order = self._one_per_franchise(np.argsort(-(s_peak_sims - 0.15 * d_penalty)), k, cand_indices)
            return [self._result(cand_indices[j], float(s_peak_sims[j]), seed=None,
                                 matched_favorite=self._favorite_title(s_indices[s_best_idx[j]]))
                    for j in order]

        # "hybrid" and "diverse": one center cannot describe a taste that has many small groups.
        # Score each candidate by its nearest liked shows, in the text space and in the tag space.
        liked, liked_w = self._liked()
        text_score, text_sims, best = _knn_score(cand_M, self.eff_M[liked], liked_w)
        tag_score, _, _ = _knn_score(self.tag_M[cand_indices], self.tag_M[liked], liked_w)
        scores = _zscore(0.5 * _zscore(text_score) + 0.5 * _zscore(tag_score)) - D_PENALTY * d_penalty

        # Content tells the kind of a show. The AniList user recommendations tell which shows the
        # people who like one show also like. This second signal comes from other people.
        cand_fr = self.row_fr[cand_indices]
        link_score, link_source = self._link_scores(liked, liked_w)
        scores = scores + LINK_WEIGHT * _zscore(link_score[cand_fr])

        # Shows that are similar to the C-tier and D-tier shows of the user get a lower score
        disliked = [i for i in self.owned_idx if self.rows[i].get("tier") in ("C", "D")]
        if disliked:
            ones = np.ones(len(disliked), dtype=np.float32)
            bad_text, _, _ = _knn_score(cand_M, self.eff_M[disliked], ones, DISLIKED_K)
            bad_tag, _, _ = _knn_score(self.tag_M[cand_indices], self.tag_M[disliked], ones, DISLIKED_K)
            scores = scores - DISLIKE_WEIGHT * _zscore(0.5 * _zscore(bad_text) + 0.5 * _zscore(bad_tag))

        if mode == "diverse":
            # Maximal marginal relevance: balance the score against the similarity to the shows already selected
            span = float(scores.max() - scores.min())
            base = (scores - scores.min()) / span if span > 1e-9 else np.zeros_like(scores)
            lambda_param = 0.65
            selected: list[int] = []
            unselected = set(range(len(cand_indices)))
            cand_franchise = [self.franchise[self.ids[i]] for i in cand_indices]
            while unselected and len(selected) < k:
                if not selected:
                    pick = int(np.argmax(base))
                else:
                    unsel_list = list(unselected)
                    sims_to_sel = (cand_M[unsel_list] @ cand_M[selected].T).max(axis=1)
                    mmr = lambda_param * base[unsel_list] - (1.0 - lambda_param) * sims_to_sel
                    pick = unsel_list[int(np.argmax(mmr))]
                selected.append(pick)
                # Remove the other entries of the same franchise from the pool
                unselected -= {j for j in unselected if cand_franchise[j] == cand_franchise[pick]}
            order = selected
        else:
            order = self._one_per_franchise(np.argsort(-scores), k, cand_indices)

        out = []
        for j in order:
            r = self._result(cand_indices[j], float(text_sims[j]), seed=None,
                             matched_favorite=self._favorite_title(liked[best[j]]))
            source = link_source.get(int(cand_fr[j]))
            if source is not None:
                # The liked show that AniList users connect most strongly to this candidate
                r["linked_favorite"] = self._favorite_title(source)
            out.append(r)
        return out

    def _build_links(self):
        """Build the link matrix between franchises from the AniList user recommendations.

        A link between two shows gets less weight when the two shows have many links, so that
        very popular shows do not fill the list.
        """
        names = sorted(set(self.franchise.values()))
        fr_pos = {f: k for k, f in enumerate(names)}
        self.row_fr = np.array([fr_pos[self.franchise[i]] for i in self.ids], dtype=np.int64)
        by_anilist = {r["anilist_id"]: self.row_fr[i] for i, r in enumerate(self.rows)
                      if r.get("anilist_id") is not None}
        A = np.zeros((len(names), len(names)), dtype=np.float32)
        for i, r in enumerate(self.rows):
            a = self.row_fr[i]
            for other, rating in r.get("recommendations") or []:
                b = by_anilist.get(other)
                if b is not None and b != a and rating > 0:
                    A[a, b] += rating
        # A recommendation connects the two shows in the two directions
        A = np.maximum(A, A.T)
        degree = np.maximum(A.sum(axis=1), 1.0)
        self.link_M = A / np.sqrt(np.outer(degree, degree))

    def _link_scores(self, liked: list[int], liked_w: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
        """Return the link score of each franchise, and the liked show with the strongest link to it."""
        weight = np.zeros(self.link_M.shape[0], dtype=np.float32)
        best_row: dict[int, int] = {}
        for i, w in zip(liked, liked_w):
            f = int(self.row_fr[i])
            if w > weight[f]:
                weight[f] = w
                best_row[f] = i
        sources = np.nonzero(weight)[0]
        if len(sources) == 0:
            return np.zeros(self.link_M.shape[0], dtype=np.float32), {}
        links = self.link_M[sources] * weight[sources, None]
        strongest = links.argmax(axis=0)
        source = {int(g): best_row[int(sources[strongest[g]])]
                  for g in np.nonzero(links.max(axis=0) > 0)[0]}
        return links.sum(axis=0), source

    def _one_per_franchise(self, order, k: int, index_map: list[int] | None = None) -> list[int]:
        """Keep the first k entries of an ordered list, with a maximum of one entry for each franchise.

        If index_map is given, the entries of the list are positions in index_map.
        """
        seen = set()
        out = []
        for j in order:
            row_index = index_map[j] if index_map is not None else j
            f = self.franchise[self.ids[row_index]]
            if f in seen:
                continue
            seen.add(f)
            out.append(int(j))
            if len(out) >= k:
                break
        return out

    def _build_franchises(self) -> dict[str, str]:
        """Group the rows into franchises with the AniList relations (sequel, prequel, side story).

        Two rows are in the same franchise if a chain of relations connects them. The chain can go
        through anime that are not in the index.
        """
        parent: dict[int, int] = {}

        def find(a: int) -> int:
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for r in self.rows:
            if r.get("anilist_id") is not None:
                for other in r.get("relations") or []:
                    parent[find(r["anilist_id"])] = find(other)

        franchise: dict[str, str] = {}
        for r in self.rows:
            if r.get("anilist_id") is not None:
                franchise[r["id"]] = f"al:{find(r['anilist_id'])}"
        for i, r in enumerate(self.rows):
            if r["id"] not in franchise:
                # A library row uses the franchise of its AniList counterpart
                franchise[r["id"]] = franchise.get(self._tag_source(i)["id"], r["id"])
        return franchise

    def _favorite_title(self, i: int) -> str:
        r = self.rows[i]
        return r.get("title_native") or r.get("title")

    def _liked(self) -> tuple[list[int], np.ndarray]:
        """Return the indexes and the weights of the owned shows that describe what the user likes."""
        liked = [i for i in self.owned_idx if self.weights.get(self.ids[i], 0.0) >= 1.0]
        if liked:
            return liked, np.array([self.weights[self.ids[i]] for i in liked], dtype=np.float32)
        # No S, A or B ratings: use all owned shows except the disliked shows
        liked = [i for i in self.owned_idx if self.rows[i].get("tier") not in ("C", "D")] or list(self.owned_idx)
        return liked, np.ones(len(liked), dtype=np.float32)

    def _tag_source(self, i: int) -> dict:
        """Return the row that supplies the tags of row i. A library row uses its AniList counterpart."""
        r = self.rows[i]
        if r["source"] == "library":
            for cp_id in self.counterparts.get(r["id"], []):
                if cp_id in self.by_id:
                    return self.by_id[cp_id]
        return r

    def _build_tag_matrix(self) -> np.ndarray:
        """Build one TF-IDF vector for each row from its genres and its tags, weighted by tag rank."""
        vocab: dict[str, int] = {}
        feats: list[dict[int, float]] = []
        for i in range(len(self.rows)):
            r = self._tag_source(i)
            ranks = r.get("tag_ranks") or []
            f: dict[int, float] = {}
            for k, t in enumerate(r.get("tags") or []):
                rank = ranks[k] if k < len(ranks) and ranks[k] else 50
                f[vocab.setdefault("t:" + t, len(vocab))] = rank / 100.0
            for g in r.get("genres") or []:
                f[vocab.setdefault("g:" + g, len(vocab))] = 1.0
            feats.append(f)
        # Column names without the "t:" or "g:" prefix
        self.tag_names = [name[2:] for name, _ in sorted(vocab.items(), key=lambda kv: kv[1])]
        T = np.zeros((len(self.rows), max(len(vocab), 1)), dtype=np.float32)
        for i, f in enumerate(feats):
            for col, val in f.items():
                T[i, col] = val
        # A tag that many shows have gives less information than a rare tag
        df = (T > 0).sum(axis=0)
        T *= (np.log((len(self.rows) + 1) / (df + 1)) + 1.0).astype(np.float32)
        return T / np.clip(np.linalg.norm(T, axis=1, keepdims=True), 1e-9, None)

    def defining_shows(self, k: int = 15) -> list[dict]:
        c = self.taste_center()
        sims = self.eff_M[self.owned_idx] @ c
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
        self.owned_idx = [i for i, row in enumerate(self.rows) if row["owned"] and row["id"] not in self.duplicate_of]

    def manual_shows(self) -> list[dict]:
        manual_ids = self.store.get_manual_watched_ids()
        c = self.taste_center() if self.owned_idx else None
        out = []
        for i, r in enumerate(self.rows):
            if r["id"] in manual_ids:
                sim = float(self.eff_M[i] @ c) if c is not None else 0.0
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
            idx = self.pos[r["id"]]
            sim = float(self.eff_M[idx] @ c) if c is not None else 0.0
            return (is_unrated, -sim)

        sorted_rows = sorted(owned_rows, key=sort_key)
        out = []
        for r in sorted_rows:
            idx = self.pos[r["id"]]
            sim = float(self.eff_M[idx] @ c) if c is not None else 0.0
            out.append(self._result(idx, sim, seed=None))
        return out

    def rated_shows(self) -> list[dict]:
        c = self.taste_center() if self.owned_idx else None
        out = []
        for i in self.owned_idx:
            r = self.rows[i]
            if r.get("tier") is not None:
                sim = float(self.eff_M[i] @ c) if c is not None else 0.0
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
        out["similarity"] = display_similarity(sim)
        if seed is not None:
            out["shared_tags"] = sorted(set(seed["tags"]) & set(r["tags"]))
        else:
            out["shared_tags"] = []
        if matched_favorite:
            out["matched_favorite"] = matched_favorite
        return out

    def center_2d(self, k: int = 5) -> tuple[float, float] | None:
        """Return the map position of the taste center.

        The layout has no formula for a new vector. Thus the position is the mean position of the
        k shows that are nearest to the taste center.
        """
        if not self.owned_idx:
            return None
        unique = [i for i, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]
        sims = self.eff_M[unique] @ self.taste_center()
        nearest = [unique[j] for j in np.argsort(-sims)[:k]]
        x, y = self.coords_2d[nearest].mean(axis=0)
        return (float(x), float(y))

    def get_vector_map(self) -> dict:
        c_proj = self.center_2d()
        points = []
        for i, r in enumerate(self.rows):
            if r["id"] in self.duplicate_of:
                continue
            poster = r.get("poster")
            if (not poster or "localhost" in poster or "127.0.0.1" in poster) and r.get("source") == "library":
                for cp_id in self.counterparts.get(r["id"], []):
                    if cp_id in self.by_id and self.by_id[cp_id].get("poster"):
                        poster = self.by_id[cp_id]["poster"]
                        break
            points.append({
                "id": r["id"],
                "x": round(float(self.coords_2d[i, 0]), 4),
                "y": round(float(self.coords_2d[i, 1]), 4),
                "title": r.get("title", ""),
                "title_native": r.get("title_native", ""),
                "year": r.get("year"),
                "poster": poster,
                "genres": r.get("genres", [])[:2],
                "owned": r.get("owned", 0),
                "tier": r.get("tier"),
            })
        return {
            "center": {"x": round(c_proj[0], 4), "y": round(c_proj[1], 4)} if c_proj else None,
            "points": points,
            "regions": self.regions,
        }
