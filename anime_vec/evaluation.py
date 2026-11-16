"""Offline test of the recommendations: hide a franchise that the user rated, then look for it in the list.

The test assumes that a show which the user rated S or A is a show that the user wants. It cannot tell
if an unowned show in the list is a good find. Use it to compare two versions of the data or the formula.
"""
from contextlib import contextmanager

import numpy as np


@contextmanager
def hidden(engine, ids):
    """Make the engine forget that the user owns and rated these shows, for the time of one test."""
    ids = [i for i in ids if i in engine.by_id]
    saved = [(i, engine.by_id[i]["owned"], engine.by_id[i].get("tier"), engine.by_id[i].get("weight"),
              engine.weights.get(i)) for i in ids]
    owned_idx = list(engine.owned_idx)
    dismissed = set(engine.dismissed)
    hide = set(ids)
    try:
        # A hidden show must be a possible recommendation, also if the user removed it at some time
        engine.dismissed -= hide
        for i in ids:
            r = engine.by_id[i]
            r["owned"], r["tier"], r["weight"] = 0, None, 1.0
            engine.weights.pop(i, None)
        engine.owned_idx = [k for k in engine.owned_idx if engine.ids[k] not in hide]
        yield
    finally:
        for i, owned, tier, weight, w in saved:
            r = engine.by_id[i]
            r["owned"], r["tier"], r["weight"] = owned, tier, weight
            if w is not None:
                engine.weights[i] = w
        engine.owned_idx = owned_idx
        engine.dismissed = dismissed


def franchise_members(engine, franchise: str) -> list[str]:
    """Return the ids of the owned shows of a franchise, with their pool counterparts."""
    out = []
    for i in engine.owned_idx:
        rid = engine.ids[i]
        if engine.franchise[rid] == franchise:
            out.append(rid)
            out.extend(engine.counterparts.get(rid, []))
    return out


def rank_of_hidden(engine, show_id: str, mode: str = "hybrid", k: int = 100000, kinds: str = "all",
                   links: bool = True) -> tuple[int, int]:
    """Hide the franchise of a show and return (rank of the franchise in the list, length of the list).

    Rank 0 is the top of the list. If the franchise is not in the list, the rank is the length of the list.
    """
    franchise = engine.franchise[show_id]
    with hidden(engine, franchise_members(engine, franchise)):
        results = engine.recommend(k=k, mode=mode, new_only=True, kinds=kinds, links=links)
    for position, r in enumerate(results):
        if engine.franchise[r["id"]] == franchise:
            return position, len(results)
    return len(results), len(results)


def rated_shows(engine, tiers) -> list[str]:
    """Return one show for each rated franchise that has a tier from `tiers`."""
    seen, out = set(), []
    for i in engine.owned_idx:
        r = engine.rows[i]
        franchise = engine.franchise[r["id"]]
        if r.get("tier") in tiers and franchise not in seen:
            seen.add(franchise)
            out.append(r["id"])
    return out


def summarize(ranks: list[tuple[int, int]]) -> dict:
    """Return the hit rates and the mean percentile of a list of (rank, length) results."""
    if not ranks:
        return {"n": 0, "hit20": 0.0, "hit40": 0.0, "hit100": 0.0, "median": 0, "percentile": 0.0}
    r = np.array([a for a, _ in ranks], dtype=np.float64)
    n = np.array([max(b, 1) for _, b in ranks], dtype=np.float64)
    return {
        "n": len(ranks),
        "hit20": float((r < 20).mean()),
        "hit40": float((r < 40).mean()),
        "hit100": float((r < 100).mean()),
        "median": int(np.median(r)),
        "percentile": float((1.0 - r / n).mean()),
    }


def hidden_franchise_test(engine, tiers=("S", "A"), mode: str = "hybrid", k: int = 100000,
                          kinds: str = "all", links: bool = True) -> dict:
    """Run the test for each rated franchise with a tier from `tiers` and return the summary.

    `kinds` and `links` select the formula: see Engine.recommend.
    """
    return summarize([rank_of_hidden(engine, show_id, mode, k, kinds, links) for show_id in rated_shows(engine, tiers)])


def recent_test(engine, count: int = 20, tiers=("S", "A"), mode: str = "hybrid", k: int = 100000,
                kinds: str = "all", links: bool = True) -> dict:
    """Hide the `count` rated franchises that the user added last, all at the same time.

    This is nearer to real use than the test of one franchise: the engine sees only the older
    shows, and the test looks for the newer shows in one list.
    """
    dated = []
    for show_id in rated_shows(engine, tiers):
        added = engine.by_id[show_id].get("added_at")
        if added:
            dated.append((added, show_id))
    newest = [show_id for _, show_id in sorted(dated)[-count:]]
    franchises = {engine.franchise[i] for i in newest}
    members = [m for f in franchises for m in franchise_members(engine, f)]
    with hidden(engine, members):
        results = engine.recommend(k=k, mode=mode, new_only=True, kinds=kinds, links=links)
    position = {}
    for rank, r in enumerate(results):
        position.setdefault(engine.franchise[r["id"]], rank)
    return summarize([(position.get(f, len(results)), len(results)) for f in franchises])
