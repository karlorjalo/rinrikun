"""Benchmark of the recommendations: run the offline tests and write the results to a JSON file.

Usage: python scripts/benchmark.py <label>

The result is scratch/bench-<label>.json. The script opens the database read-only, thus it
changes no data. It also runs on an older version of the code that has no switch for the crowd
links. Run it before and after a change of the formula, then compare the two files.

The tests:
  hidden   Hide one rated franchise, then find its place in the list of new franchises.
           The formula "usual" gets all rated franchises, the formula "all" only the S and A tiers.
  recent   Hide the 20 S and A franchises that the user added last, all at the same time.
  top      The first 40 shows of the list of today.
  timing   The time of the engine start, of one list and of the match of all shows.
"""
import datetime
import inspect
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np

import anime_vec.engine as eng
from anime_vec.engine import TIER_VALUES, Engine
from anime_vec.evaluation import franchise_members, hidden, rated_shows
from anime_vec.store import Store

HAS_SWITCH = "links" in inspect.signature(Engine.recommend).parameters
# An older version has one match for each formula
MATCH_ARGS = ("usual",) if "kinds" in inspect.signature(Engine.match_percent).parameters else ()
VARIANTS = (("usual", True), ("usual", False), ("all", True), ("all", False))
RECENT_COUNT = 20


def variant_name(kinds: str, links: bool) -> str:
    return f"{kinds}, {'links' if links else 'no links'}"


def full_list(engine, kinds: str, links: bool, k: int = 100000) -> list[dict]:
    """Return the list of the new franchises for one formula."""
    if HAS_SWITCH:
        return engine.recommend(k=k, new_only=True, kinds=kinds, links=links)
    # An older version has no switch. A link weight of 0 gives the list without the links.
    saved = eng.LINK_WEIGHT
    eng.LINK_WEIGHT = saved if links else 0.0
    try:
        return engine.recommend(k=k, new_only=True, kinds=kinds)
    finally:
        eng.LINK_WEIGHT = saved


def latin_title(engine, show_id: str) -> str:
    """Return a title of the show in Latin letters, if the show has one."""
    r = engine.by_id[show_id]
    titles = [r.get("title") or ""]
    if hasattr(engine, "other_titles"):
        titles += engine.other_titles(engine.pos[show_id])
    for title in titles:
        if title and title.isascii():
            return title
    return titles[0]


def hidden_rank(engine, show_id: str, kinds: str, links: bool) -> tuple[int, int]:
    """Hide the franchise of a show and return (place of the franchise in the list, length of the list)."""
    franchise = engine.franchise[show_id]
    with hidden(engine, franchise_members(engine, franchise)):
        results = full_list(engine, kinds, links)
    for place, r in enumerate(results):
        if engine.franchise[r["id"]] == franchise:
            return place, len(results)
    return len(results), len(results)


def recent_ranks(engine, kinds: str, links: bool) -> list[dict]:
    """Hide the newest S and A franchises together and return the place of each of them."""
    dated = sorted((engine.by_id[s].get("added_at"), s) for s in rated_shows(engine, ("S", "A"))
                   if engine.by_id[s].get("added_at"))
    newest = [s for _, s in dated[-RECENT_COUNT:]]
    by_franchise = {engine.franchise[s]: s for s in newest}
    members = [m for f in by_franchise for m in franchise_members(engine, f)]
    with hidden(engine, members):
        results = full_list(engine, kinds, links)
    place = {}
    for rank, r in enumerate(results):
        place.setdefault(engine.franchise[r["id"]], rank)
    return [{"id": s, "title": latin_title(engine, s), "rank": place.get(f, len(results)), "length": len(results)}
            for f, s in by_franchise.items()]


def main(label: str):
    out_path = ROOT / "scratch" / f"bench-{label}.json"
    out_path.parent.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    engine = Engine(Store(ROOT / "anime_vec.db", read_only=True))
    ready = time.perf_counter() - t0

    # The time of one list, and of the match of all shows after a change of the data
    t = time.perf_counter()
    full_list(engine, "usual", True, k=40)
    first = time.perf_counter() - t
    times = []
    for _ in range(5):
        t = time.perf_counter()
        full_list(engine, "usual", True, k=40)
        times.append(time.perf_counter() - t)
    engine._match_cache.clear()
    t = time.perf_counter()
    engine.match_percent(*MATCH_ARGS)
    match_time = time.perf_counter() - t
    engine._match_cache.clear()
    timing = {"engine_ready_s": round(ready, 2), "list_first_s": round(first, 3),
              "list_s": round(float(np.median(times)), 3), "match_s": round(match_time, 3)}
    print(f"engine ready in {ready:.1f} s, one list in {timing['list_s']} s, the match in {match_time:.2f} s")

    # The tier of a franchise is the best tier of its shows
    best = {}
    for i in engine.owned_idx:
        tier, f = engine.rows[i].get("tier"), engine.franchise[engine.ids[i]]
        if tier in TIER_VALUES and (f not in best or TIER_VALUES[tier] > TIER_VALUES[best[f]]):
            best[f] = tier
    targets = rated_shows(engine, tuple(TIER_VALUES))
    tier_of = {s: best[engine.franchise[s]] for s in targets}

    try:
        commit = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=ROOT, capture_output=True,
                                text=True).stdout.strip()
    except OSError:
        commit = ""
    result = {
        "label": label, "commit": commit, "date": datetime.date.today().isoformat(), "has_switch": HAS_SWITCH,
        "data": {"rows": len(engine.rows), "owned": len(engine.owned_idx),
                 "tiers": dict(Counter(engine.rows[i].get("tier") or "none" for i in engine.owned_idx)),
                 "rated_franchises": dict(Counter(tier_of.values())), "removed": len(engine.dismissed)},
        "timing": timing, "variants": {},
    }
    for kinds, links in VARIANTS:
        name = variant_name(kinds, links)
        t = time.perf_counter()
        # The formula "all" gets only the S and A franchises, to keep the time of the benchmark short
        chosen = targets if kinds == "usual" else [s for s in targets if tier_of[s] in ("S", "A")]
        rows = []
        for s in chosen:
            rank, length = hidden_rank(engine, s, kinds, links)
            rows.append({"id": s, "title": latin_title(engine, s), "tier": tier_of[s], "rank": rank, "length": length})
        top = [{"id": r["id"], "title": latin_title(engine, r["id"])} for r in full_list(engine, kinds, links, k=40)]
        result["variants"][name] = {"hidden": rows, "recent": recent_ranks(engine, kinds, links), "top": top}
        result["data"]["candidates"] = rows[0]["length"] if rows else 0
        ranks = np.array([r["rank"] for r in rows if r["tier"] in ("S", "A")], dtype=float)
        print(f"{name:<18} S and A franchises: {len(ranks)}, first 20 {(ranks < 20).mean():.1%}, "
              f"first 100 {(ranks < 100).mean():.1%}, median {int(np.median(ranks))}   ({time.perf_counter() - t:.0f} s)")
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "run")
