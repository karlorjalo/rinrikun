"""Write the results of the Python engine for a database as JSON, for the comparison with the Rust engine.

    python server/compare/python_reference.py <database> <out.json> [--write-layout]

The database is opened read-only. With --write-layout the engine can keep the map layout in the
database (the first run on a new test database). The Rust command `rinrikun reference` writes
the same keys: see server/src/reference.rs. A result from the real database has personal data:
keep it out of the repository.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from anime_vec.engine import Engine  # noqa: E402
from anime_vec.store import Store  # noqa: E402


def seeds(engine: Engine) -> list[str]:
    """Some shows of the user and some shows of the catalog: the same choice as the Rust command."""
    unique = [i for i, r in enumerate(engine.rows) if r["id"] not in engine.duplicate_of]
    mine = [engine.ids[i] for i in engine.owned_idx][::37][:6]
    other = [engine.ids[i] for i in unique if not engine.rows[i]["owned"]][::997][:6]
    return mine + other


# The lists of recommendations of the comparison: (name, arguments of Engine.recommend)
RECOMMEND = [
    ("usual", dict(mode="hybrid", new_only=True, kinds="usual", links=True)),
    ("all, no links", dict(mode="hybrid", new_only=True, kinds="all", links=False)),
    ("diverse", dict(mode="diverse", new_only=True, kinds="usual", links=True)),
    ("sequels", dict(mode="hybrid", new_only=False, kinds="usual", links=True)),
]
STEPS = [("usual", dict(kinds="usual", links=True)), ("all, no links", dict(kinds="all", links=False))]


def api(engine: Engine, store: Store) -> dict:
    """The answers of the API functions, as serve.py gives them (without the log of the lists)."""
    first_seed = seeds(engine)[-1]
    titles = [{"id": r["id"], "title": r["title"], "title_native": r["title_native"], "year": r["year"],
               "poster": engine.poster_of(i), "owned": r["owned"], "manual_watched": r.get("manual_watched", 0),
               "tier": r.get("tier"), "weight": r.get("weight", 1.0), "aka": engine.other_titles(i)}
              for i, r in enumerate(engine.rows)]
    out = {
        "profile": {
            "tier_summary": engine.tier_summary(), "owned_count": len(engine.owned_idx),
            "library_count": sum(1 for i in engine.owned_idx if engine.rows[i]["source"] == "library"),
            "manual_count": len(store.get_manual_watched_ids()), "total_count": len(engine.rows),
        },
        "titles": titles,
        "ratings": engine.rated_shows(),
        "watched": engine.with_match(engine.manual_shows()),
        "dismissed": engine.with_match(engine.dismissed_shows()),
        "review_unrated": engine.review_queue(unrated_only=True),
        "review_all": engine.review_queue(unrated_only=False),
        "interest": engine.interest_shows(),
        "interest_results": engine.interest_results(),
        "rec_log": engine.recommendation_results(),
        "recommend": {name: engine.with_match(engine.recommend(k=40, **options)) for name, options in RECOMMEND},
        "steps": {name: engine.recommendation_steps(k=40, new_only=True, **options) for name, options in STEPS},
        "show": {s: engine.with_match([engine.public_row(engine.pos[s])])[0] for s in seeds(engine)},
        "similar": {s: engine.with_match(engine.similar_to(s, 24)) for s in seeds(engine)},
        "map": engine.get_vector_map(),
        "map_match": engine.map_match(),
        # A draw of more cards than the deck has gives all shows that the deck can draw
        "discover_pool": sorted(r["id"] for r in engine.discover(count=10 ** 7, seed=1)),
        "weights": store.get_weights(),
    }
    out["recommend"]["seed"] = engine.with_match(engine.recommend(k=40, seed_id=first_seed, new_only=True, kinds="usual"))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("db")
    parser.add_argument("out")
    parser.add_argument("--write-layout", action="store_true")
    args = parser.parse_args()
    engine = Engine(Store(args.db, read_only=not args.write_layout))
    rows = engine.with_match([{"id": i, "tier": engine.by_id[i].get("tier")} for i in engine.ids])
    guess = engine.tier_guess()
    raw = engine.match_percent()
    out = {
        "ids": engine.ids,
        "owned_idx": engine.owned_idx,
        "franchise": [engine.franchise[i] for i in engine.ids],
        "entry": {f: engine.ids[j] for f, j in sorted(engine.entry_row.items())},
        "tier": [engine.by_id[i].get("tier") for i in engine.ids],
        "match": [r["match"] for r in rows],
        "match_raw": [None if np.isnan(v) else float(v) for v in raw],
        "guess": [None if np.isnan(v) else float(v) for v in guess],
        "tier_guess": [r["tier_guess"] for r in rows],
        "similar": {s: [[r["id"], r["similarity"]] for r in engine.similar_to(s, 24)] for s in seeds(engine)},
        "api": api(engine, Store(args.db, read_only=True)),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{args.out}: {len(engine.ids)} rows")


if __name__ == "__main__":
    main()
