"""Compare the results of the Python engine and of the Rust engine for one database.

    python server/compare/compare.py <python.json> <rust.json>

The two engines add numbers in a different order, thus a value can differ in its last digits,
and a show near a limit can move by one place. The script prints the differences, and it ends
with code 1 if a difference is larger than these tolerances.
"""
import json
import sys

# The match is a place in a sorted list, in percent. One place of a list of 2000 franchises is 0.05.
MATCH_TOLERANCE = 0.25
# The part of the shows whose match can differ by more than 0.05
MATCH_CHANGED_PART = 0.01
GUESS_TOLERANCE = 1e-3
# A tier guess near a limit can get the next letter
LETTER_CHANGED_PART = 0.002
SIMILARITY_TOLERANCE = 0.11


def main():
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    b = json.load(open(sys.argv[2], encoding="utf-8"))
    failed = []

    def check(name, ok, detail=""):
        print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
        if not ok:
            failed.append(name)

    check("ids", a["ids"] == b["ids"], f"{len(a['ids'])} and {len(b['ids'])} rows")
    if a["ids"] != b["ids"]:
        sys.exit(1)
    n = len(a["ids"])
    check("shows of the user", a["owned_idx"] == b["owned_idx"], f"{len(a['owned_idx'])} shows")
    check("tiers", a["tier"] == b["tier"])
    # The names of the franchises: the same groups with the same names
    same_fr = sum(x == y for x, y in zip(a["franchise"], b["franchise"]))
    check("franchises", same_fr == n, f"{same_fr} of {n} rows")
    check("entry points", a["entry"] == b["entry"], f"{len(a['entry'])} franchises")

    pairs = [(i, x, y) for i, (x, y) in enumerate(zip(a["match"], b["match"]))]
    none_diff = [i for i, x, y in pairs if (x is None) != (y is None)]
    check("rows with a match", not none_diff, f"{len(none_diff)} rows differ")
    diffs = sorted(((abs(x - y), i) for i, x, y in pairs if x is not None and y is not None), reverse=True)
    exact = sum(d == 0 for d, _ in diffs)
    changed = sum(d > 0.05 + 1e-9 for d, _ in diffs)
    worst = ", ".join(f"{a['ids'][i]} {a['match'][i]} / {b['match'][i]}" for _, i in diffs[:3])
    check("match", diffs[0][0] <= MATCH_TOLERANCE and changed <= MATCH_CHANGED_PART * len(diffs),
          f"{exact} of {len(diffs)} equal, {changed} differ by more than 0.05, largest: {worst}")

    g = [(abs(x - y), i) for i, (x, y) in enumerate(zip(a["guess"], b["guess"])) if x is not None and y is not None]
    g_none = sum((x is None) != (y is None) for x, y in zip(a["guess"], b["guess"]))
    largest = max(g)[0] if g else 0.0
    check("tier guess value", g_none == 0 and largest <= GUESS_TOLERANCE, f"largest difference {largest:.2e}")
    letters = sum(x != y for x, y in zip(a["tier_guess"], b["tier_guess"]))
    check("tier guess letter", letters <= LETTER_CHANGED_PART * n, f"{letters} rows differ")

    for seed in a["similar"]:
        x, y = a["similar"][seed], b["similar"].get(seed, [])
        # Two rows with the same vector (a library show and its AniList row) can change places
        same = [i for i, _ in x] == [i for i, _ in y]
        overlap = len({i for i, _ in x} & {i for i, _ in y})
        sims = max((abs(p[1] - q[1]) for p, q in zip(x, y)), default=0.0)
        check(f"similar to {seed}", (same or overlap >= len(x) - 2) and sims <= SIMILARITY_TOLERANCE,
              f"{overlap} of {len(x)} shows, same order: {same}, largest difference {sims:.2f}")
    print("all equal within the tolerances" if not failed else f"{len(failed)} checks failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
