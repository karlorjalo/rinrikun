import hashlib
from bisect import bisect_right

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
# The tier model predicts the tier that the user will give to a show, as a number
TIER_VALUES = {"S": 4.0, "A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0}
# Strength of the ridge regression of the tier model. A larger value gives a smoother model.
TIER_RIDGE = 3.0
# The tier model needs this number of rated shows
TIER_MODEL_MIN_RATED = 20
# A candidate gets the tier penalty if its predicted tier is more than this number of standard
# deviations below the mean of the candidates
TIER_MARGIN = 0.5
# Weight of the tier penalty in the hybrid score
TIER_PENALTY = 1.0
# A show that the user removed from the recommendations counts as a C-tier show in the tier model
DISMISSED_TIER = TIER_VALUES["C"]
# The "usual kinds" formula gives a higher score to the kinds of shows that the library has many of.
# The kind of a show is its year, its format and its number of episodes. The crowd score counts
# only as a lower limit.
# Weight of this part in the hybrid score, in standard deviations
KIND_WEIGHT = 1.0
# The limits between the groups of a year and of a number of episodes
KIND_YEARS = (1990, 2000, 2005, 2010, 2015, 2020)
KIND_EPISODES = (2, 7, 14, 27, 61)
# The crowd score has two groups: below this limit, and not below it. The crowd score does not
# predict the tier that the user gives (rank correlation 0.07 for 179 rated franchises), thus a
# higher crowd score must not give an advantage. But the library has few shows that the crowd
# rates very low, and the catalog has many. In the hidden franchise test this one limit gives
# the same result as six groups of the crowd score.
KIND_SCORES = (6.5,)
# The group of each format. A format that is not in this table is in group 6.
KIND_FORMATS = {"tv": 0, "series": 0, "movie": 1, "ova": 2, "ona": 3, "special": 4, "tv_short": 5}
# The number of groups of each property: year, format, number of episodes, crowd score
KIND_SIZES = (len(KIND_YEARS) + 1, 7, len(KIND_EPISODES) + 1, len(KIND_SCORES) + 1)
# The formulas of the recommendations
KINDS = ("all", "usual")


def _entry_key(r: dict) -> tuple:
    """Sort key that puts the entry point of a franchise first.

    The entry point is a show that can be a recommendation, then a TV series before the other
    formats, then the earliest year. An unreleased sequel or a music video must not be the entry
    point, because the recommendations do not show it. A library row has the format "series"
    for a TV series.
    """
    format_rank = {"tv": 0, "series": 0, "tv_short": 1, "ona": 1}
    return (not _watchable(r), format_rank.get(r.get("format"), 2), r.get("year") or 9999, r["id"])


def _watchable(r: dict) -> bool:
    """Return True if the row can be a recommendation.

    A show that is not released cannot be watched. A music video is an AniList entry, but it is
    not a show: it stays in the catalog and on the map, and it is not a recommendation.
    """
    return r.get("status") != "NOT_YET_RELEASED" and r.get("format") != "music"


def _number(value) -> float:
    """Return a value of the database as a number. Return 0 if it is empty or not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        # The shows that the user removed from the recommendations ("not interested")
        self.dismissed = {i for i in store.get_dismissed_ids() if i in self.by_id}
        for r in self.rows:
            r["dismissed"] = 1 if r["id"] in self.dismissed else 0
        M = np.array([blob_to_vec(store.get_embedding(r["id"])) for r in self.rows], dtype=np.float32)
        self.M = M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)

        # Identify pool rows that match library rows to avoid duplicating watched items
        lib_rows = [r for r in self.rows if r["source"] == "library"]
        self.duplicate_of: dict[str, str] = {}
        self.counterparts: dict[str, list[str]] = {}
        if any(r.get("library_id") for r in self.rows):
            # The build connected the pool rows to the library rows. One library row can have
            # more than one pool row: one for each season. A pool row that the user marked as
            # watched by hand is also the same show as its library row.
            for r in self.rows:
                lib_id = r.get("library_id")
                if r["source"] == "anilist" and lib_id in self.by_id:
                    self.duplicate_of[r["id"]] = lib_id
                    self.counterparts.setdefault(lib_id, []).append(r["id"])
                    self.counterparts.setdefault(r["id"], []).append(lib_id)
            # The first counterpart of a library row is its first TV season
            for lib in lib_rows:
                if lib["id"] in self.counterparts:
                    self.counterparts[lib["id"]].sort(key=lambda c: _entry_key(self.by_id[c]))
        elif lib_rows:
            # A database from before the id match: connect the rows by title
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
        self.entry_row = self._build_entry_rows()
        self.kind_codes = self._build_kind_codes()

        self.coords_2d, self.grid_2d, self.cell = self._build_layout(unique)
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

    def _build_layout(self, unique: list[int]) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
        """Return the map position of each row, the grid cell of each row, and the size of a cell.

        The positions are in the square from 0 to 1. The grid is for the close view of the map,
        where each show has its own cell.
        """
        coords = np.full((len(self.rows), 2), 0.5, dtype=np.float32)
        grid = np.full((len(self.rows), 2), 0.5, dtype=np.float32)
        cell = (1.0, layout.CELL_ASPECT)
        if len(unique) >= 2:
            X = self.eff_M[unique]
            ids = [self.ids[i] for i in unique]
            # The shows of the user select their cell first (by tier), then the catalog by score.
            # Thus the shows that the user knows are nearest to their map position.
            tier_rank = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
            order = sorted(range(len(unique)), key=lambda k: (
                0 if self.rows[unique[k]]["owned"] else 1,
                tier_rank.get(self.rows[unique[k]].get("tier"), 5),
                -(self._tag_source(unique[k]).get("score") or 0.0),
                k,
            ))
            if layout.can_use_tsne(len(unique)):
                # t-SNE is slow, thus keep the result in the database until the embeddings change
                signature = hashlib.sha1(
                    layout.VERSION.encode() + "\n".join(ids).encode() + np.ascontiguousarray(X).tobytes()
                ).hexdigest()
                cached = self.store.get_layout(signature)
                if cached is not None and all(i in cached["coords"] and i in cached["grid"] for i in ids):
                    points = np.array([cached["coords"][i] for i in ids], dtype=np.float32)
                    cells = np.array([cached["grid"][i] for i in ids], dtype=np.float32)
                    cell = cached["cell"]
                else:
                    points = layout.fit_unit_square(layout.tsne_layout(X))
                    cells, width, height = layout.grid_layout(points, order)
                    cell = (width, height)
                    self.store.save_layout(signature, dict(zip(ids, points.tolist())), dict(zip(ids, cells.tolist())), cell)
            else:
                points = layout.fit_unit_square(layout.pca_layout(X))
                cells, width, height = layout.grid_layout(points, order)
                cell = (width, height)
            coords[unique] = points
            grid[unique] = cells
        # A duplicate pool row is at the position of its library row
        for dup_id, lib_id in self.duplicate_of.items():
            coords[self.pos[dup_id]] = coords[self.pos[lib_id]]
            grid[self.pos[dup_id]] = grid[self.pos[lib_id]]
        return coords, grid, cell

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
                  new_only: bool = False, kinds: str = "all") -> list[dict]:
        """Return the recommendations. Each result says if the user owns a show of the same franchise.

        The mode is "hybrid" (the best scores) or "diverse" (the same scores, with more variety).
        If new_only is true, the list has no shows from franchises that the user owns.

        `kinds` selects the formula. "all" gives each kind of show the same chance. "usual" gives
        a higher score to the kinds of shows that the library has many of. A list with a seed
        is ordered by the similarity to the seed, and `kinds` has no effect on it.
        """
        if kinds not in KINDS:
            raise ValueError(f"unknown kinds {kinds}")
        owned = self.owned_franchises()
        out = self._recommend(k, seed_id, mode, owned if new_only else set(), kinds)
        for r in out:
            r["franchise_owned"] = self.franchise[r["id"]] in owned
        return out

    def _recommend(self, k: int, seed_id: str | None, mode: str, skip: set[str], kinds: str = "all") -> list[dict]:
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
                       and self.franchise[self.ids[j]] not in skip and _watchable(self.rows[j])
                       and self.ids[j] not in self.dismissed]
            return [self._result(j, float(sims[j]), seed=None) for j in self._one_per_franchise(allowed, k)]

        # A franchise that the user does not own has one candidate: its entry point. A franchise that
        # the user owns keeps all its other shows as candidates, because one of them is the next to watch.
        owned = self.owned_franchises()
        cand_indices = [j for j, r in enumerate(self.rows)
                        if not r["owned"] and r["id"] not in self.duplicate_of and self.franchise[r["id"]] not in skip
                        and _watchable(r) and r["id"] not in self.dismissed
                        and (self.franchise[r["id"]] in owned or self.entry_row[self.franchise[r["id"]]] == j)]
        if not cand_indices:
            return []

        cand_M = self.eff_M[cand_indices]
        mode = (mode or "hybrid").lower()

        d_penalty = np.zeros(len(cand_indices), dtype=np.float32)
        d_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "D"]
        if d_indices:
            raw_d_sims = (cand_M @ self.eff_M[d_indices].T).max(axis=1)
            # Soft threshold: the penalty starts when the similarity to a D-tier show is more than D_SIM_START
            d_penalty = np.maximum(0.0, raw_d_sims - D_SIM_START) / (1.0 - D_SIM_START)

        # One center cannot describe a taste that has many small groups.
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

        # Shows that are similar to the C-tier and D-tier shows of the user, or to the shows that
        # the user removed from the recommendations, get a lower score
        disliked = [i for i in self.owned_idx if self.rows[i].get("tier") in ("C", "D")] + self._dismissed_rows()
        if disliked:
            ones = np.ones(len(disliked), dtype=np.float32)
            bad_text, _, _ = _knn_score(cand_M, self.eff_M[disliked], ones, DISLIKED_K)
            bad_tag, _, _ = _knn_score(self.tag_M[cand_indices], self.tag_M[disliked], ones, DISLIKED_K)
            scores = scores - DISLIKE_WEIGHT * _zscore(0.5 * _zscore(bad_text) + 0.5 * _zscore(bad_tag))

        # A candidate that the tier model puts clearly below the other candidates gets a lower score.
        # A high prediction gives no bonus: in the hidden franchise test a bonus made the list worse,
        # and the penalty moved the S-tier and A-tier shows up.
        low = np.maximum(0.0, -_zscore(self._predicted_tier(cand_indices)) - TIER_MARGIN)
        scores = scores - TIER_PENALTY * low

        # The "usual kinds" formula: a candidate of a kind that the library has many of moves up.
        # In the hidden franchise test this part moves the S-tier and A-tier shows up in the full
        # list (the first 100 more than the first 20).
        if kinds == "usual":
            scores = scores + KIND_WEIGHT * _zscore(self._kind_score(cand_indices, owned))

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

    def _predicted_tier(self, indices: list[int]) -> np.ndarray:
        """Predict the tier that the user will give to each row, as a number (4 = S, 0 = D).

        The model is a ridge regression on the tags of the shows that the user rated: it learns
        which tags go with high tiers and which go with low tiers. The crowd score of a show does
        not predict the tier of this user, but the tiers of the user for shows with the same tags do.
        All predictions are 0 if the user has too few ratings.
        """
        rated = [i for i in self.owned_idx if self.rows[i].get("tier") in TIER_VALUES]
        # A removed recommendation is a show near the taste of the user that the user does not want.
        # The model has few low tiers, thus these shows are its most useful examples.
        dismissed = self._dismissed_rows()
        values = np.array([TIER_VALUES[self.rows[i]["tier"]] for i in rated] + [DISMISSED_TIER] * len(dismissed),
                          dtype=np.float64)
        if len(rated) < TIER_MODEL_MIN_RATED or values.std() < 1e-9:
            return np.zeros(len(indices), dtype=np.float32)
        R = self.tag_M[rated + dismissed].astype(np.float64)
        alpha = np.linalg.solve(R @ R.T + TIER_RIDGE * np.eye(len(values)), values - values.mean())
        predicted = self.tag_M[indices].astype(np.float64) @ (R.T @ alpha) + values.mean()
        return predicted.astype(np.float32)

    def _build_kind_codes(self) -> np.ndarray:
        """Return the group of each row for each property of its kind. -1 = the property is not known.

        The columns are the year, the format, the number of episodes and the crowd score.
        A library row uses the data of its AniList counterpart.
        """
        codes = np.full((len(self.rows), len(KIND_SIZES)), -1, dtype=np.int64)
        for i in range(len(self.rows)):
            r = self._tag_source(i)
            if r.get("anilist_id") is None:
                continue
            year, episodes, score = _number(r.get("year")), _number(r.get("episodes")), _number(r.get("score"))
            if year > 0:
                codes[i, 0] = bisect_right(KIND_YEARS, year)
            codes[i, 1] = KIND_FORMATS.get(r.get("format") or "", 6)
            if episodes > 0:
                codes[i, 2] = bisect_right(KIND_EPISODES, episodes)
            if score > 0:
                codes[i, 3] = bisect_right(KIND_SCORES, score)
        return codes

    def _kind_score(self, indices: list[int], owned: set[str]) -> np.ndarray:
        """Score each row by how usual its kind is in the library of the user.

        For each property (year, format, number of episodes, crowd score below the limit or not)
        the score compares two shares: the share of the library that is in the group of the row, and the share of the
        rows in `indices` that is in this group. The score is the sum of the logarithms of these
        ratios. A group that is more frequent in the library than in `indices` gives a positive
        value. A property that is not known gives the mean value of the rows that have it.

        `owned` are the franchises of the library. Each franchise counts one time, as its entry point.
        """
        total = np.zeros(len(indices), dtype=np.float64)
        library = [self.entry_row[f] for f in sorted(owned) if f in self.entry_row]
        if not library or not len(indices):
            return total.astype(np.float32)
        for col, size in enumerate(KIND_SIZES):
            cand = self.kind_codes[indices, col]
            lib = self.kind_codes[library, col]
            lib = lib[lib >= 0]
            known = cand >= 0
            if not known.any() or not len(lib):
                continue
            n_cand = np.bincount(cand[known], minlength=size)
            n_lib = np.bincount(lib, minlength=size)
            # Each group gets 0.5 more, so that an empty group does not give an infinite value
            ratio = (np.log((n_lib + 0.5) / (n_lib.sum() + 0.5 * size))
                     - np.log((n_cand + 0.5) / (n_cand.sum() + 0.5 * size)))
            value = np.where(known, ratio[np.clip(cand, 0, None)], 0.0)
            value[~known] = value[known].mean()
            total += value
        return total.astype(np.float32)

    def _build_entry_rows(self) -> dict[str, int]:
        """Return the entry point of each franchise: the earliest TV series, or the earliest show if none."""
        entry: dict[str, tuple] = {}
        for j, r in enumerate(self.rows):
            if r["id"] in self.duplicate_of:
                continue
            key = _entry_key(r)
            f = self.franchise[r["id"]]
            if f not in entry or key < entry[f][0]:
                entry[f] = (key, j)
        return {f: j for f, (_, j) in entry.items()}

    def _build_links(self):
        """Build the links between franchises from the AniList user recommendations.

        A link between two shows gets less weight when the two shows have many links, so that
        very popular shows do not fill the list.

        `self.links[f]` holds the franchises that have a link with franchise f, and the weights
        of these links. A full matrix of all franchise pairs is too large for a catalog of all
        anime: most pairs have no link.
        """
        names = sorted(set(self.franchise.values()))
        fr_pos = {f: k for k, f in enumerate(names)}
        self.row_fr = np.array([fr_pos[self.franchise[i]] for i in self.ids], dtype=np.int64)
        by_anilist = {r["anilist_id"]: int(self.row_fr[i]) for i, r in enumerate(self.rows)
                      if r.get("anilist_id") is not None}
        directed: dict[tuple[int, int], float] = {}
        for i, r in enumerate(self.rows):
            a = int(self.row_fr[i])
            for other, rating in r.get("recommendations") or []:
                b = by_anilist.get(other)
                if b is not None and b != a and rating > 0:
                    directed[(a, b)] = directed.get((a, b), 0.0) + rating
        # A recommendation connects the two shows in the two directions
        pairs: dict[tuple[int, int], float] = {}
        for (a, b), rating in directed.items():
            key = (a, b) if a < b else (b, a)
            pairs[key] = max(pairs.get(key, 0.0), rating)
        degree = np.zeros(len(names), dtype=np.float64)
        for (a, b), rating in pairs.items():
            degree[a] += rating
            degree[b] += rating
        degree = np.maximum(degree, 1.0)
        neighbors: list[list[tuple[int, float]]] = [[] for _ in names]
        for (a, b), rating in pairs.items():
            weight = rating / float(np.sqrt(degree[a] * degree[b]))
            neighbors[a].append((b, weight))
            neighbors[b].append((a, weight))
        self.links = [(np.array([j for j, _ in sorted(row)], dtype=np.int64),
                       np.array([w for _, w in sorted(row)], dtype=np.float32)) for row in neighbors]

    def link_weight(self, a: int, b: int) -> float:
        """Return the weight of the link between two franchises (by index), or 0 if they have no link."""
        others, weights = self.links[a]
        hit = np.nonzero(others == b)[0]
        return float(weights[hit[0]]) if len(hit) else 0.0

    def _link_scores(self, liked: list[int], liked_w: np.ndarray) -> tuple[np.ndarray, dict[int, int]]:
        """Return the link score of each franchise, and the liked show with the strongest link to it."""
        count = len(self.links)
        weight = np.zeros(count, dtype=np.float32)
        best_row: dict[int, int] = {}
        for i, w in zip(liked, liked_w):
            f = int(self.row_fr[i])
            if w > weight[f]:
                weight[f] = w
                best_row[f] = i
        score = np.zeros(count, dtype=np.float32)
        strongest = np.zeros(count, dtype=np.float32)
        strongest_source = np.full(count, -1, dtype=np.int64)
        for f in np.nonzero(weight)[0]:
            others, weights = self.links[f]
            value = weights * weight[f]
            score[others] += value
            better = value > strongest[others]
            strongest[others[better]] = value[better]
            strongest_source[others[better]] = f
        source = {int(g): best_row[int(strongest_source[g])] for g in np.nonzero(strongest > 0)[0]}
        return score, source

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

    def set_watched(self, show_id: str, watched: bool):
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        self.store.set_manual_watched(show_id, watched)
        r = self.by_id[show_id]
        r["manual_watched"] = 1 if watched else 0
        if r["source"] != "library":
            r["owned"] = 1 if watched else 0
        self.owned_idx = [i for i, row in enumerate(self.rows) if row["owned"] and row["id"] not in self.duplicate_of]

    def _dismissed_rows(self) -> list[int]:
        """Return the indexes of the shows that the user removed from the recommendations and does not own."""
        return [self.pos[i] for i in sorted(self.dismissed)
                if not self.by_id[i]["owned"] and i not in self.duplicate_of]

    def set_dismissed(self, show_id: str, dismissed: bool):
        """Remove a show from the recommendations, or put it back.

        A removed show is never a recommendation. It also counts as a dislike: shows that are
        similar to it get a lower score.
        """
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        self.store.set_dismissed(show_id, dismissed)
        self.by_id[show_id]["dismissed"] = 1 if dismissed else 0
        if dismissed:
            self.dismissed.add(show_id)
        else:
            self.dismissed.discard(show_id)

    def dismissed_shows(self) -> list[dict]:
        c = self.taste_center() if self.owned_idx else None
        out = []
        for show_id in sorted(self.dismissed):
            i = self.pos[show_id]
            sim = float(self.eff_M[i] @ c) if c is not None else 0.0
            out.append(self._result(i, sim, seed=None))
        return out

    def manual_shows(self) -> list[dict]:
        manual_ids = self.store.get_manual_watched_ids()
        c = self.taste_center() if self.owned_idx else None
        out = []
        for i, r in enumerate(self.rows):
            # A show that the library has now is not a manually added show
            if r["id"] in manual_ids and r["id"] not in self.duplicate_of:
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
        # "ids" are the rows that changed: the show and its counterparts. The map has only one of
        # these rows as a point, and the interface must know which points to change.
        changed = [sid for sid in target_ids if sid in self.by_id]
        return {"id": show_id, "tier": primary["tier"], "weight": primary["weight"], "ids": changed}

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
                # The cell of the show in the close view of the map
                "gx": round(float(self.grid_2d[i, 0]), 5),
                "gy": round(float(self.grid_2d[i, 1]), 5),
                "title": r.get("title", ""),
                "title_native": r.get("title_native", ""),
                "year": r.get("year"),
                "poster": poster,
                "genres": r.get("genres", [])[:2],
                "owned": r.get("owned", 0),
                "tier": r.get("tier"),
                # The map uses the score to select which posters it shows first
                "score": self._tag_source(i).get("score"),
            })
        return {
            "center": {"x": round(c_proj[0], 4), "y": round(c_proj[1], 4)} if c_proj else None,
            "points": points,
            "regions": self.regions,
            "cell": {"w": float(self.cell[0]), "h": float(self.cell[1])},
        }
