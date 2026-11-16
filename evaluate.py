"""Print the offline test of the recommendations. The database is opened read-only.

    python evaluate.py              # the hidden franchise test for the formulas
    python evaluate.py --tiers      # also the mean percentile of a hidden show for each tier
    python evaluate.py --recent 20  # also hide the 20 franchises that you added last, all at the same time
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from anime_vec.engine import Engine
from anime_vec.evaluation import hidden_franchise_test, recent_test
from anime_vec.store import Store

DB = Path(__file__).resolve().parent / "anime_vec.db"


def main(argv: list[str]):
    db = Path(argv[argv.index("--db") + 1]) if "--db" in argv else DB
    engine = Engine(Store(db, read_only=True))
    candidates = len({engine.franchise[r["id"]] for r in engine.rows
                      if not r["owned"] and r["id"] not in engine.duplicate_of})
    print(f"rows {len(engine.rows)}, owned {len(engine.owned_idx)}, candidate franchises about {candidates}")
    print(f"a random list: first 40 = {40 / max(candidates, 1):.1%}")
    print()
    print(f"{'hidden S and A franchises':<36}{'n':>5}{'first 20':>10}{'first 40':>10}{'first 100':>11}{'median':>8}")
    for label, mode, kinds, k in (("all kinds", "hybrid", "all", 100000), ("usual kinds", "hybrid", "usual", 100000),
                                  ("all kinds, more variety (first 100)", "diverse", "all", 100),
                                  ("usual kinds, more variety (first 100)", "diverse", "usual", 100)):
        s = hidden_franchise_test(engine, ("S", "A"), mode, k, kinds)
        median = str(s["median"]) if mode == "hybrid" else "-"
        print(f"{label:<36}{s['n']:>5}{s['hit20']:>10.1%}{s['hit40']:>10.1%}{s['hit100']:>11.1%}{median:>8}")
    if "--recent" in argv:
        count = int(argv[argv.index("--recent") + 1])
        print()
        print(f"the {count} S and A franchises that you added last, hidden at the same time:")
        for kinds in ("all", "usual"):
            s = recent_test(engine, count, kinds=kinds)
            print(f"  {kinds + ' kinds:':<13} first 20: {s['hit20']:.1%}   first 40: {s['hit40']:.1%}   "
                  f"first 100: {s['hit100']:.1%}   median rank: {s['median']}")
    if "--tiers" in argv:
        print()
        print("mean percentile of a hidden franchise by its tier (1.0 = top of the list), all kinds:")
        for tier in "SABCD":
            s = hidden_franchise_test(engine, (tier,))
            if s["n"]:
                print(f"  {tier}: {s['percentile']:.3f}  (n={s['n']})")


if __name__ == "__main__":
    main(sys.argv[1:])
