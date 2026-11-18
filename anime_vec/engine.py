import hashlib
import random
import threading
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
# Weight of a show of the user that has no tier, as a source of links. The user selects the shows
# of the library, thus such a show is a mild like before it has a tier. A B-tier show has the
# weight 1.0. In the hidden franchise test this weight moved the S-tier and A-tier shows up.
# The same shows as examples for the content score did not help.
UNRATED_LINK_WEIGHT = 0.75
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
# The tier guess of a show without a tier: the letter for a predicted value, from the highest limit down.
# The guess is weak. In a test on 221 rated shows, with each franchise hidden from the model, the
# rank correlation between the prediction and the tier was 0.20: of the shows in the highest
# quarter of the predictions 64% were S or A, and of the shows in the lowest quarter 36%.
# Newer models (TabPFN v2, TabICLv2, boosted trees) were not better than this ridge regression.
TIER_GUESS_LIMITS = (("S", 3.5), ("A", 2.5), ("B", 1.5), ("C", 0.5))
# The taste model is a ridge regression on the tags of all shows of the catalog. It learns what
# makes the liked shows of the user different from the catalog. The content score is the mean of
# this model and of the score from the nearest liked shows. In the hidden franchise test (74 S-tier
# and A-tier franchises, formula "usual kinds") the model moved the median place of a hidden
# franchise from 55 to 33. Without the crowd links, the part of the hidden franchises in the first
# 20 went from 15% to 26%.
# Strength of the ridge regression, relative to the mean variance of one tag in the catalog
TASTE_RIDGE = 1.0
# The value that the model learns for a C-tier or D-tier show, and for a show that the user removed
# from the recommendations. A liked show has its tier weight (S 2.0, A 1.5, B 1.0). Each other
# show of the catalog has the value 0.
TASTE_DISLIKED = -1.0
# An answer of the Discover deck is a weaker signal than a tier: the user saw only the poster,
# the text and the tags of the show. An answer has one half of the value of the nearest tier:
# "interested" is one half of a B-tier show, "not interested" is one half of a C-tier show.
# The answers are not examples for the tier model: a show that the user did not watch has no tier.
TASTE_INTERESTED = 0.5
TASTE_NOT_INTERESTED = -0.5
# The weight of the predicted tier in the match. The content score has the weight 1. The tier
# model orders the rated shows of the user a little, but it does not predict the interest of the
# user in a new show: see Engine.match_percent for the test.
MATCH_TIER_WEIGHT = 0.25
# The Discover deck draws its shows at random in groups of the match: (lowest match of the group,
# part of the cards that come from the group). In one group each show has the same chance, thus
# the answers of a group are a fair sample of the group. Most cards come from the groups between
# 80 and 99. There the first 110 answers of the user were mixed (27% and 58% "interested"), thus
# an answer tells the taste model the most. Below 80 the answer was "not interested" for 23 of
# 24 shows, thus this group gets only a few cards: they show if the match stays correct there.
DISCOVER_GROUPS = ((99.0, 0.25), (95.0, 0.35), (80.0, 0.35), (0.0, 0.05))
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


def _ranks(x: np.ndarray) -> np.ndarray:
    """Return the rank of each value (0 = lowest). Equal values get the mean of their ranks."""
    order = np.argsort(x, kind="stable")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(len(x), dtype=np.float64)
    _, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
    return np.bincount(inverse, weights=ranks)[inverse] / counts[inverse]


def _scale_like(reference: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Return the z-scores of x on the scale of `reference`: with the mean and the standard deviation of `reference`."""
    sd = float(reference.std())
    if sd <= 1e-9:
        return np.zeros(len(x), dtype=np.float32)
    return ((x - reference.mean()) / sd).astype(np.float32)


def _knn_score_without(cand: np.ndarray, liked: np.ndarray, weights: np.ndarray, skip: np.ndarray, k: int = LIKED_K):
    """As the score of _knn_score, but each candidate ignores the liked shows for which `skip` is true."""
    weighted = np.where(skip, -np.inf, (cand @ liked.T) * weights[None, :])
    k = min(k, liked.shape[0])
    top = np.take_along_axis(weighted, np.argpartition(-weighted, k - 1, axis=1)[:, :k], axis=1)
    valid = np.isfinite(top)
    return (np.where(valid, top, 0.0).sum(axis=1) / np.maximum(valid.sum(axis=1), 1)).astype(np.float32)


class Engine:
    def __init__(self, store):
        self.store = store
        self.rows = store.load_rows()
        self.rows = [r for r in self.rows if store.get_embedding(r["id"])]
        self.ids = [r["id"] for r in self.rows]
        self.by_id = {r["id"]: r for r in self.rows}
        # The shows that the user removed from the recommendations ("not interested")
        self.dismissed = {i for i in store.get_dismissed_ids() if i in self.by_id}
        # The answers of the Discover deck: 1 = interested, 0 = not interested. See set_interest.
        self.interest = {i: v["value"] for i, v in store.get_interest().items() if i in self.by_id}
        # The match of each card that the Discover deck gave, until the user answers it
        self._deck_match: dict[str, float] = {}
        for r in self.rows:
            # For the interface, a show with the answer "not interested" is a removed show
            r["dismissed"] = 1 if self._refused(r["id"]) else 0
            r["interest"] = self.interest.get(r["id"])
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
        self._build_taste_model()
        self.franchise = self._build_franchises()
        self._build_links()
        self.entry_row = self._build_entry_rows()
        self.kind_codes = self._build_kind_codes()
        # The match of each row, and the tier guess. See match_percent and tier_guess.
        self._match_cache: dict = {}
        # The server answers requests in more than one thread. After a change of a tier, some
        # requests need the match at the same time. One thread computes it and the other threads
        # wait for the result. Without the lock each thread computed it, which took 2 to 3 seconds.
        # A change of the data of the user also holds the lock.
        self.lock = threading.RLock()

        self.coords_2d, self.grid_2d, self.cell = self._build_layout(unique)
        self.regions = self._build_regions(unique)

    def _build_regions(self, unique: list[int]) -> list[dict]:
        """Divide the map into areas on three levels and name each area after its most typical tags.

        The directions on a t-SNE map have no meaning. The labels tell the user what an area contains.

        Level 0 has the large areas. Each large area is divided into smaller areas (level 1), and
        each of these is divided again (level 2). The interface shows the smaller areas when the
        user zooms in. A large area gets the tags that are more frequent in it than in the full
        index. A smaller area gets the tags that are more frequent in it than in its larger area,
        without the tags of its larger areas: its label tells what is special about it.

        Each area has its position on the map (x, y) and in the grid of the close view (gx, gy).
        The list has the large areas first, and on each level the areas with the most rows first.
        """
        if len(unique) < layout.REGION_MIN_ROWS or not self.tag_names:
            return []
        P = self.coords_2d[unique]
        G = self.grid_2d[unique]
        T = self.tag_M[unique]
        has_tag = T > 0
        corpus_mean = T.mean(axis=0)
        regions: list[dict] = []

        def typical_tags(members, base, exclude=(), support=0.0, count=2) -> list[str]:
            """Return the tags that are more frequent in the rows `members` than in `base`."""
            lift = T[members].mean(axis=0) - base
            share = has_tag[members].mean(axis=0)
            out = []
            for j in np.argsort(-lift):
                if lift[j] <= 0 or len(out) >= count:
                    break
                if share[j] >= support and self.tag_names[j] not in exclude:
                    out.append(self.tag_names[j])
            return out

        def add(members, level: int, tags: list[str]):
            x, y = P[members].mean(axis=0)
            gx, gy = G[members].mean(axis=0)
            regions.append({"x": round(float(x), 4), "y": round(float(y), 4),
                            "gx": round(float(gx), 4), "gy": round(float(gy), 4),
                            "label": " · ".join(tags), "count": int(len(members)), "level": level})

        def divide(members, level: int, exclude: set):
            parts = int(round(len(members) / layout.REGION_PART_SIZES[level - 1]))
            if parts < 2:
                return
            labels, _ = layout.kmeans(P[members], parts)
            base = T[members].mean(axis=0)
            support = layout.REGION_PART_SUPPORT[level - 1]
            for c in range(parts):
                part = members[labels == c]
                if len(part) < layout.REGION_MIN_PART:
                    continue
                tags = typical_tags(part, base, exclude, support) or typical_tags(part, corpus_mean, exclude, support)
                if tags:
                    add(part, level, tags)
                if level < len(layout.REGION_PART_SIZES):
                    divide(part, level + 1, exclude | set(tags))

        labels, _ = layout.kmeans(P, layout.REGION_COUNT)
        areas = sorted((np.where(labels == c)[0] for c in range(int(labels.max()) + 1)), key=len, reverse=True)
        used: set = set()
        for members in areas:
            if len(members) < layout.REGION_MIN_SIZE:
                continue
            tags = typical_tags(members, corpus_mean, count=6)
            if not tags:
                continue
            # Two large areas must not have the same label: the second area gets its next typical tag
            label = tags[:2]
            for other in tags[2:]:
                if " · ".join(label) not in used:
                    break
                label = [tags[0], other]
            used.add(" · ".join(label))
            add(members, 0, label)
            divide(members, 1, set(label))
        regions.sort(key=lambda r: (r["level"], -r["count"]))
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
                  new_only: bool = False, kinds: str = "all", links: bool = True) -> list[dict]:
        """Return the recommendations. Each result says if the user owns a show of the same franchise.

        The mode is "hybrid" (the best scores) or "diverse" (the same scores, with more variety).
        If new_only is true, the list has no shows from franchises that the user owns.

        `kinds` selects the formula. "all" gives each kind of show the same chance. "usual" gives
        a higher score to the kinds of shows that the library has many of. A list with a seed
        is ordered by the similarity to the seed, and `kinds` has no effect on it.

        If `links` is false, the formula does not use the crowd links: the recommendations of
        AniList users. The list then comes only from the ratings of the user and from the facts
        of the shows. `links` also has no effect on a list with a seed.
        """
        if kinds not in KINDS:
            raise ValueError(f"unknown kinds {kinds}")
        owned = self.owned_franchises()
        out = self._recommend(k, seed_id, mode, owned if new_only else set(), kinds, links)
        for r in out:
            r["franchise_owned"] = self.franchise[r["id"]] in owned
        return out

    def _recommend(self, k: int, seed_id: str | None, mode: str, skip: set[str], kinds: str = "all",
                   links: bool = True) -> list[dict]:
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
                       and not self._refused(self.ids[j])]
            return [self._result(j, float(sims[j]), seed=None) for j in self._one_per_franchise(allowed, k)]

        # A franchise that the user does not own has one candidate: its entry point. A franchise that
        # the user owns keeps all its other shows as candidates, because one of them is the next to watch.
        owned = self.owned_franchises()
        cand_indices = [j for j, r in enumerate(self.rows)
                        if not r["owned"] and r["id"] not in self.duplicate_of and self.franchise[r["id"]] not in skip
                        and _watchable(r) and not self._refused(r["id"])
                        and (self.franchise[r["id"]] in owned or self.entry_row[self.franchise[r["id"]]] == j)]
        if not cand_indices:
            return []

        mode = (mode or "hybrid").lower()
        hybrid = self._hybrid(cand_indices, kinds, owned, links=links)
        scores, best, liked = hybrid["scores"], hybrid["best"], hybrid["liked"]
        link_source, cand_fr = hybrid["link_source"], hybrid["cand_fr"]
        cand_M = self.eff_M[cand_indices]

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
            r = self._result(cand_indices[j], matched_favorite=self._favorite_title(liked[best[j]]))
            source = link_source.get(int(cand_fr[j]))
            if source is not None:
                # The liked show that AniList users connect most strongly to this candidate
                r["linked_favorite"] = self._favorite_title(source)
            out.append(r)
        return out

    def _content(self, cand_indices: list[int], extra: list[int] | None = None) -> dict:
        """Compute the content score of each candidate: how near the candidate is to the taste of the user.

        The score is the mean of two values: the similarity to the nearest liked shows (text and
        tags), and the taste model. A candidate that is very similar to a D-tier show gets a penalty.

        `extra` are rows that are not candidates, for example the shows of the user. Each of them
        gets a score on the scale of the candidates: each part of its score uses the mean and the
        standard deviation that the part has for the candidates. An extra row ignores the shows of
        its own franchise in each part. Thus a show of the user gets about the score that it
        would have if the user did not have its franchise.

        Return the scores, the scores of the extra rows, the nearest liked show of each candidate,
        and the liked shows with their weights.
        """
        cand_M = self.eff_M[cand_indices]
        cand_T = self.tag_M[cand_indices]
        extra = list(extra) if extra is not None else []
        extra_fr = self.row_fr[extra]

        def same_franchise(rows: list[int]) -> np.ndarray:
            """Return for each extra row which of `rows` are in its franchise."""
            return extra_fr[:, None] == self.row_fr[rows][None, :]

        d_penalty = np.zeros(len(cand_indices), dtype=np.float32)
        extra_d = np.zeros(len(extra), dtype=np.float32)
        d_indices = [i for i in self.owned_idx if self.rows[i].get("tier") == "D"]
        if d_indices:
            raw_d_sims = (cand_M @ self.eff_M[d_indices].T).max(axis=1)
            # Soft threshold: the penalty starts when the similarity to a D-tier show is more than D_SIM_START
            d_penalty = np.maximum(0.0, raw_d_sims - D_SIM_START) / (1.0 - D_SIM_START)
            if extra:
                sims = np.where(same_franchise(d_indices), -np.inf, self.eff_M[extra] @ self.eff_M[d_indices].T)
                extra_d = (np.maximum(0.0, sims.max(axis=1) - D_SIM_START) / (1.0 - D_SIM_START)).astype(np.float32)

        # One center cannot describe a taste that has many small groups.
        # Score each candidate by its nearest liked shows, in the text space and in the tag space.
        liked, liked_w = self._liked()
        text_score, _, best = _knn_score(cand_M, self.eff_M[liked], liked_w)
        tag_score, _, _ = _knn_score(cand_T, self.tag_M[liked], liked_w)
        nearest = 0.5 * _zscore(text_score) + 0.5 * _zscore(tag_score)
        # The nearest liked shows find a candidate that is like some shows of the user. The taste
        # model finds a candidate that has what the liked shows have and the catalog does not
        # have. The content score is the mean of the two. In the hidden franchise test the mean
        # was better than each of the two alone.
        taste = self._taste_scores(cand_indices)
        content = 0.5 * _zscore(nearest) + 0.5 * _zscore(taste)
        scores = _zscore(content) - D_PENALTY * d_penalty
        extra_scores = np.zeros(len(extra), dtype=np.float32)
        if extra:
            skip = same_franchise(liked)
            extra_text = _knn_score_without(self.eff_M[extra], self.eff_M[liked], liked_w, skip)
            extra_tag = _knn_score_without(self.tag_M[extra], self.tag_M[liked], liked_w, skip)
            extra_nearest = 0.5 * _scale_like(text_score, extra_text) + 0.5 * _scale_like(tag_score, extra_tag)
            extra_taste = self._taste_scores(extra, leave_out=True)
            extra_content = 0.5 * _scale_like(nearest, extra_nearest) + 0.5 * _scale_like(taste, extra_taste)
            extra_scores = _scale_like(content, extra_content) - D_PENALTY * extra_d
        return {"scores": scores, "extra_scores": extra_scores, "best": best, "liked": liked, "liked_w": liked_w}

    def _hybrid(self, cand_indices: list[int], kinds: str, owned: set[str], links: bool = True) -> dict:
        """Compute the hybrid score of each candidate. This score gives the order of a list of recommendations.

        If `links` is false, the score has no part from the crowd links.

        `stages` in the result has the score of the candidates after each part of the formula:
        "content", "links", "tier" and "kind". A part that the formula does not use, or that
        changes no score, has no stage.

        The score has no part for the similarity to the C-tier and D-tier shows of the user.
        Until November 2026 it had one, and a test with 113 answers of the Discover deck showed
        that it worked against the user: a show near these shows was more frequently a show that
        the user wanted. The user selected these shows too, thus they are in the area of the
        taste of the user. Without this part the formula predicted the answers better, and the
        result of the hidden franchise test was equal or better. The taste model and the tier
        model still learn from the low tiers.

        Return the scores and the data for the results.
        """
        cand_fr = self.row_fr[cand_indices]
        content = self._content(cand_indices)
        scores, best, liked, liked_w = content["scores"], content["best"], content["liked"], content["liked_w"]
        stages = [("content", scores.copy())]

        # Content tells the kind of a show. The AniList user recommendations tell which shows the
        # people who like one show also like. This second signal comes from other people, and it
        # starts at the liked shows of the user. The user can turn it off.
        link_source: dict[int, int] = {}
        if links:
            link_score, link_source = self._link_scores(*self._link_sources(liked, liked_w))
            cand_links = link_score[cand_fr]
            scores = scores + LINK_WEIGHT * _zscore(cand_links)
            stages.append(("links", scores.copy()))

        # A candidate that the tier model puts clearly below the other candidates gets a lower score.
        # A high prediction gives no bonus: in the hidden franchise test a bonus made the list worse,
        # and the penalty moved the S-tier and A-tier shows up.
        predicted = self._predicted_tier(cand_indices)
        low = np.maximum(0.0, -_zscore(predicted) - TIER_MARGIN)
        scores = scores - TIER_PENALTY * low
        if low.any():
            stages.append(("tier", scores.copy()))

        # The "usual kinds" formula: a candidate of a kind that the library has many of moves up.
        # In the hidden franchise test this part moves the S-tier and A-tier shows up in the full
        # list (the first 100 more than the first 20).
        if kinds == "usual":
            tables = self._kind_tables(cand_indices, owned)
            kind = self._kind_values(cand_indices, tables)
            scores = scores + KIND_WEIGHT * _zscore(kind)
            stages.append(("kind", scores.copy()))

        return {"scores": scores, "best": best, "liked": liked,
                "link_source": link_source, "cand_fr": cand_fr, "stages": stages}

    def recommendation_steps(self, k: int = 40, kinds: str = "all", links: bool = True, new_only: bool = True) -> dict:
        """Return the steps from the catalog to the list of recommendations, for the animation of the map.

        Each step has a key, the number of shows that stay, and the map points of these shows:
        positions in the points of get_vector_map, the best show first.
          catalog   All shows. This step has no points.
          new       The candidates: the shows that the list can have.
          content, links, tier, kind
                    One step for each part of the formula. The shows that stay are the best
                    shows by the sum of the parts up to this step.
          list      The first k shows by the full formula.
        The numbers of shows go down in equal ratios from the candidates to the list. A show can
        come back in a later step, because a later part can move it up.

        `info` has the numbers of the data of the user that the texts of the steps use.
        """
        if kinds not in KINDS:
            raise ValueError(f"unknown kinds {kinds}")
        owned = self.owned_franchises()
        skip = owned if new_only else set()
        # The candidates of _recommend
        cand = [j for j, r in enumerate(self.rows)
                if not r["owned"] and r["id"] not in self.duplicate_of and self.franchise[r["id"]] not in skip
                and _watchable(r) and not self._refused(r["id"])
                and (self.franchise[r["id"]] in owned or self.entry_row[self.franchise[r["id"]]] == j)]
        point_of = {j: n for n, j in enumerate(j for j, r in enumerate(self.rows) if r["id"] not in self.duplicate_of)}
        liked, liked_w = self._liked()
        rated = [i for i in self.owned_idx if self.rows[i].get("tier") in TIER_VALUES]
        info = {"shows": len(self.owned_idx), "franchises": len(owned), "removed": len(self._refused_ids()),
                "liked": len(liked) if self.owned_idx else 0, "rated": len(rated),
                "sources": len({int(self.row_fr[i]) for i in self._link_sources(liked, liked_w)[0]}) if self.owned_idx else 0}
        steps = [{"key": "catalog", "count": len(point_of), "points": None},
                 {"key": "new", "count": len(cand), "points": [point_of[j] for j in cand]}]
        if cand and self.owned_idx:
            stages = self._hybrid(cand, kinds, owned, links=links)["stages"]
            ratio = min(1.0, k / len(cand)) ** (1.0 / (len(stages) + 1))
            for n, (key, scores) in enumerate(stages):
                size = max(k, int(round(len(cand) * ratio ** (n + 1))))
                keep = self._one_per_franchise(np.argsort(-scores, kind="stable"), size, cand)
                steps.append({"key": key, "count": len(keep), "points": [point_of[cand[j]] for j in keep]})
            keep = self._one_per_franchise(np.argsort(-stages[-1][1], kind="stable"), k, cand)
            steps.append({"key": "list", "count": len(keep), "points": [point_of[cand[j]] for j in keep]})
        return {"kinds": kinds, "links": links, "k": k, "info": info, "steps": steps}

    def _state_key(self) -> tuple:
        """Return a value that changes when the shows, the tiers, the removed shows or the answers of the user change."""
        return (tuple(self.owned_idx), tuple(sorted(self.weights.items())), tuple(sorted(self.dismissed)),
                tuple(sorted(self.interest.items())))

    def match_percent(self) -> np.ndarray:
        """Return the match of each row in percent. The value is NaN for a row without a match.

        The match tells how near a show is to the user. Its score has two parts: the content
        score (the nearest liked shows and the taste model, see _content), and the tier that the
        tier model predicts for the show, with the weight MATCH_TIER_WEIGHT. The match is the
        part of the new franchises of the catalog that have a lower score than the show. 99
        means: the show is nearer to the user than 99% of the franchises that the user does not
        have.

        The match does not use the crowd links, and it does not use the kinds of the formulas.
        Thus a show has one match for all formulas, and a list of recommendations is not always
        in the order of the match.

        The tier part has a small weight, because it does not predict the interest of the user
        in a new show. In a test with 113 answers of the Discover deck, the match with this
        weight put an interested show above a not-interested show in 83% of the pairs. With the
        same weight for the two parts the result was 74%. The tier part stays because it orders
        the rated shows of the user a little: with each rated franchise hidden in turn, the rank
        correlation of the match with the tier was 0.11 (0.08 without the tier part). The median
        match was 98.8 for the S tier, 96.3 for the A tier, 97.3 for the B tier and 98.6 for the
        C tier. Thus the match tells if a show is for the user, and it is a weak prediction of
        the tier of one show.

        A show of the user gets the score that it would have if the user did not have its
        franchise: each part ignores the shows of this franchise. Thus the match of a show of
        the user tells how well the other shows of the user predict this show. In the same way,
        a show with an answer of the Discover deck gets the score that it would have without the
        answer.
        """
        with self.lock:
            return self._match_percent()

    def _match_percent(self) -> np.ndarray:
        """Compute or get the result of match_percent. The caller holds the lock."""
        key = self._state_key()
        cached = self._match_cache.get("match")
        if cached is not None and cached[0] == key:
            return cached[1]
        out = np.full(len(self.rows), np.nan, dtype=np.float32)
        owned = self.owned_franchises()
        unique = [j for j, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]
        # The candidates of a list that also has the franchises of the user (see _recommend).
        # A show of a new franchise that has an answer of the Discover deck is not a candidate
        # here: as an extra row it gets the score of a taste model that does not know its answer.
        cand = [j for j in unique
                if not self.rows[j]["owned"] and _watchable(self.rows[j]) and not self._refused(self.ids[j])
                and (self.franchise[self.ids[j]] in owned
                     or (self.entry_row[self.franchise[self.ids[j]]] == j and self.ids[j] not in self.interest))]
        if cand and self.owned_idx:
            cand_set = set(cand)
            extra = [j for j in unique if j not in cand_set]
            content = self._content(cand, extra)
            predicted = self._predicted_tier(cand)
            scores = content["scores"] + MATCH_TIER_WEIGHT * _zscore(predicted)
            # The reference: the franchises that the user does not have
            new = np.array([self.franchise[self.ids[j]] not in owned for j in cand])
            reference = np.sort(scores[new] if new.any() else scores)
            out[cand] = 100.0 * np.searchsorted(reference, scores, side="left") / len(reference)
            if extra:
                extra_predicted = self._predicted_tier(extra, leave_out="franchise")
                extra_scores = content["extra_scores"] + MATCH_TIER_WEIGHT * _scale_like(predicted, extra_predicted)
                out[extra] = 100.0 * np.searchsorted(reference, extra_scores, side="left") / len(reference)
            # An AniList row of a library show has the match of the library show
            for dup_id, lib_id in self.duplicate_of.items():
                out[self.pos[dup_id]] = out[self.pos[lib_id]]
        self._match_cache["match"] = (key, out)
        return out

    def tier_guess(self) -> np.ndarray:
        """Return the tier that the tier model predicts for each row, as a number (4 = S, 0 = D).

        The value is NaN if the user has too few ratings for the model. A row that the model
        learned from gets the prediction of a model without this row.
        """
        with self.lock:
            return self._tier_guess()

    def _tier_guess(self) -> np.ndarray:
        """Compute or get the result of tier_guess. The caller holds the lock."""
        key = self._state_key()
        cached = self._match_cache.get("tier guess")
        if cached is not None and cached[0] == key:
            return cached[1]
        out = np.full(len(self.rows), np.nan, dtype=np.float32)
        rated = [self.rows[i]["tier"] for i in self.owned_idx if self.rows[i].get("tier") in TIER_VALUES]
        if len(rated) >= TIER_MODEL_MIN_RATED and len(set(rated)) > 1:
            unique = [j for j, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]
            out[unique] = self._predicted_tier(unique, leave_out="row")
            for dup_id, lib_id in self.duplicate_of.items():
                out[self.pos[dup_id]] = out[self.pos[lib_id]]
        self._match_cache["tier guess"] = (key, out)
        return out

    def watch_next_order(self, rows: list[int]) -> list[int]:
        """Order shows without a tier: the shows that the user will probably rate highest are first.

        The order uses two signals with the same weight: the match, and the tier guess. The
        match ignores the other shows of the franchise of a show. The tier guess uses them: the
        tier of one season is a good guess for the next season. In a test on the 222 rated
        shows (the match and the guess of a show did not know its rating), the first quarter of
        this order had 29% S-tier shows, and the last quarter 7%. Of all rated shows 17% are
        S-tier shows.
        """
        rows = list(rows)
        if len(rows) < 2:
            return rows
        score = _zscore(_ranks(np.nan_to_num(self.match_percent()[rows], nan=0.0)))
        guess = self.tier_guess()[rows]
        if not np.isnan(guess).any():
            score = score + _zscore(guess.astype(np.float64))
        return [rows[k] for k in np.argsort(-score, kind="stable")]

    def with_match(self, results: list[dict]) -> list[dict]:
        """Add the match (see match_percent) to each result. The value is None for a show without a match.

        A show without a tier also gets `tier_guess`: the letter of the tier that the tier model
        predicts for it, or None.
        """
        match = self.match_percent()
        guess = self.tier_guess()
        for r in results:
            j = self.pos[r["id"]]
            r["match"] = None if np.isnan(match[j]) else round(float(match[j]), 1)
            r["tier_guess"] = None
            if r.get("tier") is None and not np.isnan(guess[j]):
                r["tier_guess"] = next((letter for letter, limit in TIER_GUESS_LIMITS if guess[j] >= limit), "D")
        return results

    def map_match(self) -> list:
        """Return the match of each point of the map, in the order of the points of get_vector_map.

        A value is the match in percent with one decimal, or None for a show without a match.
        The map uses the values for its match gradient.
        """
        match = self.match_percent()
        return [None if np.isnan(match[i]) else round(float(match[i]), 1)
                for i, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]

    def _predicted_tier(self, indices: list[int], leave_out: str | None = None) -> np.ndarray:
        """Predict the tier that the user will give to each row, as a number (4 = S, 0 = D).

        The model is a ridge regression on the tags of the shows that the user rated: it learns
        which tags go with high tiers and which go with low tiers. The crowd score of a show does
        not predict the tier of this user, but the tiers of the user for shows with the same tags do.
        All predictions are 0 if the user has too few ratings.

        `leave_out` selects the model for a row that is in the data of the model, or near it:
          "row"        A row that the model learned from gets the prediction of a model that did
                       not learn from this row. The other shows of its franchise still count:
                       the tier of one season is a good guess for the next season.
          "franchise"  A row gets the prediction of a model that did not learn from the shows of
                       the franchise of the row.
        """
        if leave_out not in (None, "row", "franchise"):
            raise ValueError(f"unknown leave_out {leave_out}")
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
        if leave_out == "row":
            # For a ridge regression, the fit without one row comes from the fit with all rows:
            # (fit of the row - leverage * value of the row) / (1 - leverage). The model subtracts
            # the mean of the values first, and this mean is also different without the row.
            gram = R @ R.T
            hat = gram @ np.linalg.inv(gram + TIER_RIDGE * np.eye(len(values)))
            leverage = np.diag(hat)
            rest = np.clip(1.0 - leverage, 1e-6, None)
            fit_values = (hat @ values - leverage * values) / rest
            fit_ones = (hat.sum(axis=1) - leverage) / rest
            mean_without = (values.sum() - values) / max(len(values) - 1, 1)
            without = fit_values + mean_without * (1.0 - fit_ones)
            position = {row: n for n, row in enumerate(rated + dismissed)}
            for n, row in enumerate(indices):
                if row in position:
                    predicted[n] = without[position[row]]
        elif leave_out == "franchise":
            # One more model for each franchise that the model learned from: the model without
            # the shows of this franchise. A new solution of the equations for each franchise is
            # slow. The inverse matrix of the model with all shows gives the same result: the
            # solution without some rows is the solution with all rows, minus a correction that
            # uses only the columns of these rows.
            inverse = np.linalg.inv(R @ R.T + TIER_RIDGE * np.eye(len(values)))
            learned = self.row_fr[rated + dismissed]
            wanted: dict[int, list[int]] = {}
            for n, row in enumerate(indices):
                wanted.setdefault(int(self.row_fr[row]), []).append(n)
            for f in np.unique(learned):
                places = wanted.get(int(f))
                keep = learned != f
                if not places or not keep.any():
                    continue
                gone = np.nonzero(~keep)[0]
                mean = values[keep].mean()
                solution = inverse @ np.where(keep, values - mean, 0.0)
                solution -= inverse[:, gone] @ np.linalg.solve(inverse[np.ix_(gone, gone)], solution[gone])
                rows_of_f = [indices[n] for n in places]
                predicted[places] = self.tag_M[rows_of_f].astype(np.float64) @ (R.T @ solution) + mean
        return predicted.astype(np.float32)

    def _build_taste_model(self):
        """Prepare the part of the taste model that does not change with the ratings of the user.

        The taste model is a ridge regression on the tag vectors of all shows of the catalog.
        The value that it learns is positive for a liked show, negative for a disliked show and
        0 for each other show. Its weights are `taste_solver @ (sum of the centered tag vectors
        of the rated shows, each multiplied by its value)`. `taste_solver` comes only from the
        catalog. Thus a change of a tier needs no new calculation of the catalog.
        """
        unique = [i for i, r in enumerate(self.rows) if r["id"] not in self.duplicate_of]
        tags = self.tag_M[unique].astype(np.float64)
        size = self.tag_M.shape[1]
        self.taste_mean = tags.mean(axis=0) if unique else np.zeros(size)
        centered = tags - self.taste_mean
        gram = centered.T @ centered
        ridge = max(TASTE_RIDGE * float(np.trace(gram)) / size, 1e-9)
        self.taste_solver = np.linalg.inv(gram + ridge * np.eye(size))

    def _taste_scores(self, indices: list[int], leave_out: bool = False) -> np.ndarray:
        """Return the score of the taste model for each row. A higher score is nearer to the taste of the user.

        The model learns from the liked shows, from the C-tier and D-tier shows, and from the
        shows that the user removed from the recommendations. It also learns from the answers of
        the Discover deck, with a smaller weight. All scores are 0 if the user has none of these
        shows.

        If leave_out is true, a row gets the score of a model that did not learn from the shows
        of the franchise of the row. Thus a show of the user gets about the score that it would
        have if the user did not have it.
        """
        liked, liked_w = self._liked()
        disliked = [i for i in self.owned_idx if self.rows[i].get("tier") in ("C", "D")] + self._dismissed_rows()
        # The answers of the Discover deck, for the shows that the user does not have
        answers = [(self.pos[i], value) for i, value in sorted(self.interest.items()) if not self.by_id[i]["owned"]]
        rows = list(liked) + disliked + [j for j, _ in answers]
        if not rows or not len(indices):
            return np.zeros(len(indices), dtype=np.float32)
        values = np.concatenate([np.asarray(liked_w, dtype=np.float64), np.full(len(disliked), TASTE_DISLIKED),
                                 np.array([TASTE_INTERESTED if value else TASTE_NOT_INTERESTED for _, value in answers])])
        examples = (self.tag_M[rows].astype(np.float64) - self.taste_mean) * values[:, None]
        weights = self.taste_solver @ examples.sum(axis=0)
        # The score of a row is (tag vector - mean) @ weights. The two products are computed
        # apart: a centered copy of the tag vectors of all rows takes too much time.
        tags = self.tag_M[indices]
        scores = (tags @ weights.astype(np.float32)).astype(np.float64) - float(self.taste_mean @ weights)
        if leave_out:
            # The weights are a sum over the rated shows. Thus the model without one franchise
            # is the model with all shows, minus the part that the shows of this franchise gave.
            franchises, group = np.unique(self.row_fr[rows], return_inverse=True)
            sums = np.zeros((len(franchises), examples.shape[1]))
            np.add.at(sums, group, examples)
            own = sums @ self.taste_solver
            position = {int(f): g for g, f in enumerate(franchises)}
            which = np.array([position.get(int(f), -1) for f in self.row_fr[indices]])
            has = which >= 0
            centered = tags[has].astype(np.float64) - self.taste_mean
            scores[has] -= np.einsum("ij,ij->i", centered, own[which[has]])
        return scores.astype(np.float32)

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
        return self._kind_values(indices, self._kind_tables(indices, owned))

    def _kind_tables(self, indices: list[int], owned: set[str]) -> list:
        """Return for each property the value of each of its groups, and the value for a row without the property.

        The entry of a property is None if the rows or the library have no data for it.
        """
        library = [self.entry_row[f] for f in sorted(owned) if f in self.entry_row]
        tables: list = []
        for col, size in enumerate(KIND_SIZES):
            cand = self.kind_codes[indices, col] if len(indices) else np.zeros(0, dtype=np.int64)
            lib = self.kind_codes[library, col] if library else np.zeros(0, dtype=np.int64)
            lib = lib[lib >= 0]
            known = cand >= 0
            if not known.any() or not len(lib):
                tables.append(None)
                continue
            n_cand = np.bincount(cand[known], minlength=size)
            n_lib = np.bincount(lib, minlength=size)
            # Each group gets 0.5 more, so that an empty group does not give an infinite value
            ratio = (np.log((n_lib + 0.5) / (n_lib.sum() + 0.5 * size))
                     - np.log((n_cand + 0.5) / (n_cand.sum() + 0.5 * size)))
            tables.append((ratio, ratio[cand[known]].mean()))
        return tables

    def _kind_values(self, indices: list[int], tables: list) -> np.ndarray:
        """Return the kind score of each row from the tables of _kind_tables."""
        total = np.zeros(len(indices), dtype=np.float64)
        for col, table in enumerate(tables):
            if table is None or not len(indices):
                continue
            ratio, unknown = table
            codes = self.kind_codes[indices, col]
            total += np.where(codes >= 0, ratio[np.clip(codes, 0, None)], unknown)
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

    def _link_sources(self, liked: list[int], liked_w: np.ndarray) -> tuple[list[int], np.ndarray]:
        """Return the shows that give links, with their weights.

        These are the liked shows, and the shows of the user that have no tier. A show without a
        tier gives no links if its franchise has a C-tier or D-tier show.
        """
        liked_set = set(liked)
        disliked = {int(self.row_fr[i]) for i in self.owned_idx if self.rows[i].get("tier") in ("C", "D")}
        unrated = [i for i in self.owned_idx if self.rows[i].get("tier") is None and i not in liked_set
                   and int(self.row_fr[i]) not in disliked]
        if not unrated:
            return list(liked), liked_w
        weights = np.concatenate([liked_w, np.full(len(unrated), UNRATED_LINK_WEIGHT, dtype=np.float32)])
        return list(liked) + unrated, weights

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

        A removed show is never a recommendation. It is also an example of a show that the user
        does not want, for the taste model and for the tier model: shows with the same tags get
        a lower score. A removed show has no answer of the Discover deck: to remove a show
        replaces the answer, and to put a show back deletes the answer "not interested".
        """
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        self.store.set_dismissed(show_id, dismissed)
        if dismissed:
            self.dismissed.add(show_id)
        else:
            self.dismissed.discard(show_id)
        if dismissed or self.interest.get(show_id) == 0:
            self._drop_interest(show_id)
        self.by_id[show_id]["dismissed"] = 1 if self._refused(show_id) else 0

    def _refused(self, show_id: str) -> bool:
        """Return True if the user does not want the show: the user removed it, or the answer was "not interested"."""
        return show_id in self.dismissed or self.interest.get(show_id) == 0

    def _refused_ids(self) -> set[str]:
        return self.dismissed | {i for i, value in self.interest.items() if value == 0}

    def dismissed_shows(self) -> list[dict]:
        """Return the shows that the user does not want: see _refused."""
        return [self._result(self.pos[show_id]) for show_id in sorted(self._refused_ids())]

    def _drop_interest(self, show_id: str):
        if show_id in self.interest:
            self.store.set_interest(show_id, None)
            del self.interest[show_id]
        self.by_id[show_id]["interest"] = None

    def set_interest(self, show_id: str, value: bool | None, source: str = "deck"):
        """Record the answer of the user for a show that the user does not have. None deletes the answer.

        True is "interested": the show stays a possible recommendation, and it is on the watch
        list. False is "not interested": the show is never a recommendation. The two answers
        are weak examples for the taste model (see TASTE_INTERESTED). The database keeps the
        match that the show had before the answer, as a record. `source` is "deck" for an answer
        of the Discover deck, which draws its shows at random, and "page" for other answers.
        """
        if show_id not in self.by_id:
            raise KeyError(f"unknown show id {show_id}")
        row = self.by_id[show_id]
        if value is None:
            self._drop_interest(show_id)
        else:
            if row["owned"]:
                raise ValueError("the user has this show: it gets a tier, not an answer")
            # The match that the deck showed for the show. An answer from a page uses the match of now.
            # Thus an answer of the deck needs no new calculation of the match, and it is fast.
            match = self._deck_match.pop(show_id, None)
            if match is None:
                match = float(self.match_percent()[self.pos[show_id]])
            self.store.set_interest(show_id, int(value), None if np.isnan(match) else match, source)
            self.interest[show_id] = int(value)
            row["interest"] = int(value)
            if value and show_id in self.dismissed:
                # "Interested" puts a removed show back
                self.store.set_dismissed(show_id, False)
                self.dismissed.discard(show_id)
        row["dismissed"] = 1 if self._refused(show_id) else 0

    def interest_counts(self) -> dict[str, int]:
        interested = sum(1 for value in self.interest.values() if value)
        return {"interested": interested, "not_interested": len(self.interest) - interested}

    def interest_shows(self) -> list[dict]:
        """Return the shows with the answer "interested", the highest match first: the watch list."""
        out = self.with_match([self._result(self.pos[i]) for i, value in sorted(self.interest.items())
                               if value and not self.by_id[i]["owned"]])
        return sorted(out, key=lambda r: -(r.get("match") or 0.0))

    def discover(self, count: int = 12, seed: int | None = None) -> list[dict]:
        """Return random shows for the Discover deck.

        A card is the entry point of a franchise that the user does not have. It has no answer,
        and the user did not remove it. The draw is random in the groups of DISCOVER_GROUPS.
        `seed` makes the draw the same each time, for the tests.
        """
        owned = self.owned_franchises()
        match = self.match_percent()
        groups: list[list[int]] = [[] for _ in DISCOVER_GROUPS]
        for j, r in enumerate(self.rows):
            if (r["owned"] or r["id"] in self.duplicate_of or self.franchise[r["id"]] in owned or not _watchable(r)
                    or self._refused(r["id"]) or r["id"] in self.interest
                    or self.entry_row[self.franchise[r["id"]]] != j or np.isnan(match[j])):
                continue
            groups[next(n for n, (low, _) in enumerate(DISCOVER_GROUPS) if match[j] >= low)].append(j)
        rng = random.Random(seed)
        picked: list[int] = []
        while len(picked) < count:
            filled = [n for n, group in enumerate(groups) if group]
            if not filled:
                break
            parts = [DISCOVER_GROUPS[n][1] for n in filled]
            n = rng.choices(filled, weights=parts if sum(parts) > 0 else None)[0]
            picked.append(groups[n].pop(rng.randrange(len(groups[n]))))
        for j in picked:
            self._deck_match[self.ids[j]] = float(match[j])
        return self.with_match([self._result(j) for j in picked])

    def interest_results(self) -> dict:
        """Compare the answers of the Discover deck with the match of the shows.

        `groups` has the answers of the deck in the groups of DISCOVER_GROUPS, by the match of
        the show. This match does not know the answer of the show: see match_percent. If the
        match is good, a group with a higher match has a larger part of "interested". An answer
        from a page is not in the groups, because the user selected its show.

        `model` tells how well the taste model predicts an answer that it does not know: the
        part of the pairs (interested show, not-interested show) in which the interested show
        has the higher score. 0.5 is the result of a random order. It is None for fewer than 3
        answers of one kind.
        """
        stored = self.store.get_interest()
        match = self.match_percent()
        deck = [(float(match[self.pos[i]]), value) for i, value in self.interest.items()
                if stored.get(i, {}).get("source") == "deck" and not self.by_id[i]["owned"]
                and not np.isnan(match[self.pos[i]])]
        groups = []
        high = None
        for low, _ in DISCOVER_GROUPS:
            inside = [value for match, value in deck if match >= low and (high is None or match < high)]
            groups.append({"low": low, "high": 100.0 if high is None else high, "answers": len(inside), "interested": int(sum(inside))})
            high = low
        answers = [(self.pos[i], value) for i, value in sorted(self.interest.items()) if not self.by_id[i]["owned"]]
        yes = [n for n, (_, value) in enumerate(answers) if value]
        no = [n for n, (_, value) in enumerate(answers) if not value]
        model = None
        if len(yes) >= 3 and len(no) >= 3:
            scores = self._taste_scores([j for j, _ in answers], leave_out=True).astype(np.float64)
            above = scores[yes][:, None] - scores[no][None, :]
            model = {"pairs": len(yes) * len(no), "auc": round(float(((above > 0).sum() + 0.5 * (above == 0).sum()) / above.size), 3)}
        counts = self.interest_counts()
        return {"answers": len(self.interest), **counts, "groups": groups, "model": model}

    def manual_shows(self) -> list[dict]:
        manual_ids = self.store.get_manual_watched_ids()
        # A show that the library has now is not a manually added show
        return [self._result(i) for i, r in enumerate(self.rows)
                if r["id"] in manual_ids and r["id"] not in self.duplicate_of]

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
        """Return the shows of the user: the shows without a tier first, then the rated shows by their match.

        A show without a tier is frequently a show that the user did not watch yet. These shows
        have the order of watch_next_order, thus the start of the list is also the answer to
        "which show of mine do I watch next?".
        """
        match = np.nan_to_num(self.match_percent(), nan=-1.0)
        order = self.watch_next_order([i for i in self.owned_idx if self.rows[i].get("tier") is None])
        if not unrated_only:
            order += sorted((i for i in self.owned_idx if self.rows[i].get("tier") is not None),
                            key=lambda i: -float(match[i]))
        return self.with_match([self._result(i) for i in order])

    def rated_shows(self) -> list[dict]:
        """Return the shows that the user rated: by tier, then by their match."""
        out = self.with_match([self._result(i) for i in self.owned_idx if self.rows[i].get("tier") is not None])
        tier_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
        return sorted(out, key=lambda x: (tier_order.get(x.get("tier"), 99), -(x.get("match") or 0.0)))

    def recommendation_results(self) -> dict:
        """Compare the log of the recommendations with what the user did later.

        The log has each show of a new franchise that a list of recommendations gave. A show
        counts as "added" if the user now has a show of its franchise. Its tier is the best tier
        of these shows. The result cannot tell if the user added a show because of the list.

        `formulas` has the numbers for the lists with the crowd links and for the lists without
        them. A show counts for the formula of the first list that gave it.
        """
        log = self.store.get_rec_log()
        mine: dict[str, list[int]] = {}
        for i in self.owned_idx:
            mine.setdefault(self.franchise[self.ids[i]], []).append(i)
        order = ["S", "A", "B", "C", "D"]
        out = {"since": None, "shown": 0, "added": 0, "unrated": 0, "removed": 0,
               "tiers": {t: 0 for t in order}, "shows": [],
               "formulas": {name: {"shown": 0, "added": 0, "removed": 0} for name in ("links", "no links")}}
        for show_id, entry in log.items():
            if show_id not in self.by_id:
                continue
            formula = out["formulas"]["no links" if (entry.get("kinds") or "").endswith("no links") else "links"]
            out["shown"] += 1
            formula["shown"] += 1
            if out["since"] is None or entry["first_seen"] < out["since"]:
                out["since"] = entry["first_seen"]
            rows = mine.get(self.franchise[show_id])
            if rows:
                out["added"] += 1
                formula["added"] += 1
                rated = sorted((self.rows[i]["tier"] for i in rows if self.rows[i].get("tier") in order), key=order.index)
                tier = rated[0] if rated else None
                if tier:
                    out["tiers"][tier] += 1
                else:
                    out["unrated"] += 1
                r = self.rows[rows[0]]
                out["shows"].append({"id": r["id"], "title": r.get("title"), "title_native": r.get("title_native"),
                                     "tier": tier, "first_seen": entry["first_seen"], "best_rank": entry["best_rank"]})
            elif self._refused(show_id):
                out["removed"] += 1
                formula["removed"] += 1
        out["shows"].sort(key=lambda x: (x["first_seen"], x["id"]), reverse=True)
        return out

    def tier_summary(self) -> dict[str, int]:
        counts = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0, "unrated": 0}
        for i in self.owned_idx:
            tier = self.rows[i].get("tier")
            if tier and tier in counts:
                counts[tier] += 1
            else:
                counts["unrated"] += 1
        return counts

    def poster_of(self, j: int) -> str | None:
        """Return the address of the poster of row j for the interface.

        The poster of a library row is on the Jellyfin server. Its address is frequently
        "localhost", which a browser on a different computer cannot load. Thus a library row uses
        the poster of its AniList entry (the first TV season). A library row without an AniList
        entry gets an address of this server (/api/poster/<id>), which passes the poster on from
        Jellyfin.
        """
        r = self.rows[j]
        if r.get("source") != "library":
            return r.get("poster")
        entry = self._tag_source(j)
        if entry is not r and entry.get("poster"):
            return entry["poster"]
        return f"/api/poster/{r['id']}" if r.get("poster") else None

    def other_titles(self, j: int) -> list[str]:
        """Return the titles of row j that are not its two main titles, for the search of the interface.

        An AniList row has its English title. A library row has only its title from Jellyfin,
        which is in one language. Thus a library row also gets the romaji title, the English title
        and the Japanese title of each of its AniList entries.
        """
        r = self.rows[j]
        names = [r.get("title_english")]
        if r.get("source") == "library":
            for other_id in self.counterparts.get(r["id"], []):
                other = self.by_id.get(other_id) or {}
                names += [other.get("title"), other.get("title_english"), other.get("title_native")]
        seen = {(r.get("title") or "").strip().lower(), (r.get("title_native") or "").strip().lower()}
        out = []
        for name in names:
            name = (name or "").strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                out.append(name)
        return out

    def public_row(self, j: int) -> dict:
        """Return a copy of row j for the interface.

        A library row has no AniList data of its own: its score is the rating from Jellyfin. It
        gets the AniList id and the crowd score of its AniList entry (the first TV season), so
        that the interface can link to AniList and shows the same kind of score for all shows.
        The rating from Jellyfin moves to `library_score`. The poster is the poster from
        `poster_of`. The other data of a library row without an AniList entry does not change.
        """
        r = self.rows[j]
        out = dict(r)
        out.pop("text_hash", None)
        out["poster"] = self.poster_of(j)
        entry = self._tag_source(j)
        if entry is not r:
            out["anilist_id"] = entry.get("anilist_id")
            out["library_score"] = r.get("score")
            out["score"] = entry.get("score")
        return out

    def _result(self, j: int, sim: float | None = None, seed=None, matched_favorite: str | None = None) -> dict:
        r = self.rows[j]
        out = self.public_row(j)
        if sim is not None:
            # The similarity to the seed show of the list
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
            poster = self.poster_of(i)
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
            # The other titles of the show, for the search of the map
            aka = self.other_titles(i)
            if aka:
                points[-1]["aka"] = aka
        return {
            "center": {"x": round(c_proj[0], 4), "y": round(c_proj[1], 4)} if c_proj else None,
            "points": points,
            "regions": self.regions,
            "cell": {"w": float(self.cell[0]), "h": float(self.cell[1])},
        }
