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
    if "api" in a and "api" in b:
        compare_api(a["api"], b["api"], check)
    print("all equal within the tolerances" if not failed else f"{len(failed)} checks failed")
    sys.exit(1 if failed else 0)


def show_differences(x: dict, y: dict) -> list[str]:
    """The keys of two shows of a list that have different values, with the tolerances of the numbers"""
    out = []
    for key in sorted(set(x) | set(y)):
        p, q = x.get(key, "<none>"), y.get(key, "<none>")
        if key == "match" and p is not None and q is not None and p != "<none>" and q != "<none>":
            if abs(p - q) > MATCH_TOLERANCE:
                out.append(f"{key} {p}/{q}")
        elif key == "similarity" and p != "<none>" and q != "<none>":
            if abs(p - q) > SIMILARITY_TOLERANCE:
                out.append(f"{key} {p}/{q}")
        elif key == "tier_guess":
            continue
        elif p != q:
            out.append(f"{key} {str(p)[:30]}/{str(q)[:30]}")
    return out


def compare_shows(name: str, xs: list, ys: list, check, order_changes: int = 0):
    """Two lists of shows: the same shows, in the same order (with `order_changes` places that can
    differ), and the same values"""
    ids_x, ids_y = [s["id"] for s in xs], [s["id"] for s in ys]
    # A place where the two lists have different shows with the same similarity is a tie: the
    # sort of NumPy puts equal values in any order. A library show and its AniList entry have the
    # same vector, thus the same similarity.
    moved = sum(p["id"] != q["id"] and not ("similarity" in p and p["similarity"] == q.get("similarity"))
                for p, q in zip(xs, ys))
    overlap = len(set(ids_x) & set(ids_y))
    by_id = {s["id"]: s for s in ys}
    fields = []
    letters = 0
    for s in xs:
        other = by_id.get(s["id"])
        if other is not None:
            fields += [f"{s['id']}: {d}" for d in show_differences(s, other)]
            letters += s.get("tier_guess") != other.get("tier_guess")
    ok = len(xs) == len(ys) and overlap >= len(xs) - order_changes and moved <= order_changes * 2 and not fields
    check(f"api {name}", ok, f"{len(xs)}/{len(ys)} shows, {overlap} in both, {moved} places differ, "
                             f"{letters} guess letters differ{'; ' + '; '.join(fields[:3]) if fields else ''}")


def compare_api(a: dict, b: dict, check):
    for key in ("profile", "titles", "weights", "rec_log"):
        same = a[key] == b[key]
        detail = ""
        if not same and isinstance(a[key], list):
            bad = [k for k, (x, y) in enumerate(zip(a[key], b[key])) if x != y]
            detail = f"{len(bad)} items differ, first: {bad[:1] and (a[key][bad[0]], b[key][bad[0]])}"
        elif not same:
            detail = f"{str(a[key])[:200]} / {str(b[key])[:200]}"
        check(f"api {key}", same, detail)
    for key in ("ratings", "watched", "dismissed", "review_unrated", "review_all", "interest"):
        compare_shows(key, a[key], b[key], check, order_changes=2)
    for seed in a["show"]:
        compare_shows(f"show {seed}", [a["show"][seed]], [b["show"][seed]], check)
        compare_shows(f"similar {seed}", a["similar"][seed], b["similar"][seed], check, order_changes=2)
    for name in a["recommend"]:
        compare_shows(f"recommend {name}", a["recommend"][name], b["recommend"][name], check, order_changes=2)
    ir_a, ir_b = a["interest_results"], b["interest_results"]
    auc_ok = (ir_a["model"] is None) == (ir_b["model"] is None) and (
        ir_a["model"] is None or (ir_a["model"]["pairs"] == ir_b["model"]["pairs"] and abs(ir_a["model"]["auc"] - ir_b["model"]["auc"]) <= 0.002))
    rest_a = {k: v for k, v in ir_a.items() if k != "model"}
    rest_b = {k: v for k, v in ir_b.items() if k != "model"}
    check("api interest results", auc_ok and rest_a == rest_b, f"{ir_a['model']} / {ir_b['model']}")
    for name in a["steps"]:
        sa, sb = a["steps"][name], b["steps"][name]
        same_head = {k: sa[k] for k in ("kinds", "links", "k", "info")} == {k: sb[k] for k in ("kinds", "links", "k", "info")}
        keys = [(s["key"], s["count"]) for s in sa["steps"]] == [(s["key"], s["count"]) for s in sb["steps"]]
        shares = []
        for p, q in zip(sa["steps"], sb["steps"]):
            if p["points"] is not None:
                shares.append(len(set(p["points"]) & set(q["points"] or [])) / max(len(p["points"]), 1))
        check(f"api steps {name}", same_head and keys and min(shares, default=1) >= 0.97,
              f"{[s['count'] for s in sa['steps']]} / {[s['count'] for s in sb['steps']]}, smallest share of the same points {min(shares, default=1):.3f}")
    ma, mb = a["map"], b["map"]
    center = ma["center"] == mb["center"] or (ma["center"] and mb["center"] and abs(ma["center"]["x"] - mb["center"]["x"]) <= 2e-4
                                               and abs(ma["center"]["y"] - mb["center"]["y"]) <= 2e-4)
    bad_points = [k for k, (p, q) in enumerate(zip(ma["points"], mb["points"])) if p != q]
    check("api map points", len(ma["points"]) == len(mb["points"]) and not bad_points and ma["cell"] == mb["cell"] and center,
          f"{len(ma['points'])} points, {len(bad_points)} differ, center {ma['center']} / {mb['center']}"
          + (f", first: {ma['points'][bad_points[0]]} / {mb['points'][bad_points[0]]}" if bad_points else ""))
    if mb["regions"]:
        check("api map regions", ma["regions"] == mb["regions"], f"{len(ma['regions'])} / {len(mb['regions'])} areas")
    else:
        print(f"note api map regions: the database has no areas for the Rust engine yet ({len(ma['regions'])} in Python)")
    ma_match = a["map_match"]
    mm = [abs(x - y) for x, y in zip(ma_match, b["map_match"]) if x is not None and y is not None]
    check("api map match", len(ma_match) == len(b["map_match"]) and max(mm, default=0) <= MATCH_TOLERANCE, f"largest difference {max(mm, default=0):.2f}")
    pa, pb = set(a["discover_pool"]), set(b["discover_pool"])
    check("api discover pool", pa == pb, f"{len(pa)} / {len(pb)} shows, {len(pa ^ pb)} differ")


if __name__ == "__main__":
    main()
