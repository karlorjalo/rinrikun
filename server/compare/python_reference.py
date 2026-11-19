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
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{args.out}: {len(engine.ids)} rows")


if __name__ == "__main__":
    main()
