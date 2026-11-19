"""Send the same GET requests to the Python server and to the Rust server, and compare the answers.

    python server/compare/http_check.py <python address> <rust address>

For example: python server/compare/http_check.py http://127.0.0.1:8773 http://127.0.0.1:8775

Use a test server with a copy of the database: the Python server writes a list of
recommendations without a seed into its log. The two servers must read the same database. The
script uses the rules of compare.py, and it ends with code 1 if a check fails.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

from compare import MATCH_TOLERANCE, compare_shows

PYTHON, RUST = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")
failed = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failed.append(name)


def get(base: str, path: str):
    """Return (status, headers, JSON or text) of one request"""
    try:
        with urllib.request.urlopen(base + path, timeout=60) as res:
            body = res.read()
            status, headers = res.status, {k.lower(): v for k, v in res.headers.items()}
    except urllib.error.HTTPError as error:
        body, status, headers = error.read(), error.code, {k.lower(): v for k, v in error.headers.items()}
    try:
        return status, headers, json.loads(body)
    except ValueError:
        return status, headers, body.decode("utf-8", "replace")


def both(path: str):
    a, b = get(PYTHON, path), get(RUST, path)
    if a[0] != b[0]:
        check(f"status {path}", False, f"{a[0]} / {b[0]}")
    return a[2], b[2]


# Lists and data without the log of the recommendations: the log changes when the Python server gives a list
for path in ("/api/profile", "/api/shows", "/api/weights", "/api/rec-log", "/api/interest/results"):
    a, b = both(path)
    if path == "/api/interest/results":
        same = {k: v for k, v in a.items() if k != "model"} == {k: v for k, v in b.items() if k != "model"}
        same = same and (a["model"] is None) == (b["model"] is None) and (a["model"] is None or abs(a["model"]["auc"] - b["model"]["auc"]) <= 0.002)
    else:
        same = a == b
    check(path, same)
for path in ("/api/ratings", "/api/watched", "/api/dismissed", "/api/review-queue?unrated_only=true", "/api/review-queue", "/api/interest"):
    a, b = both(path)
    compare_shows(path, a, b, check, order_changes=2)

titles = get(PYTHON, "/api/shows")[2]
seeds = [t["id"] for t in titles if t["owned"]][::50][:4] + [t["id"] for t in titles if not t["owned"]][::2000][:4]
for seed in seeds:
    a, b = both(f"/api/show/{seed}")
    compare_shows(f"/api/show/{seed}", [a], [b], check)
    a, b = both(f"/api/similar?id={seed}&k=24")
    compare_shows(f"/api/similar {seed}", a, b, check, order_changes=2)
for path in ("/api/show/no-such-show", "/api/similar?id=no-such-show", "/api/recommend?seed=no-such-show", "/api/recommend?k=500"):
    a, b = get(PYTHON, path)[0], get(RUST, path)[0]
    check(f"error {path}", a == b, f"{a} / {b}")

a, b = both("/api/vector-map")
check("/api/vector-map points", a["points"] == b["points"] and a["cell"] == b["cell"] and a["center"] == b["center"], f"{len(a['points'])} points")
check("/api/vector-map regions", a["regions"] == b["regions"], f"{len(a['regions'])} / {len(b['regions'])} areas")
a, b = both("/api/vector-map/match")
diff = max((abs(x - y) for x, y in zip(a, b) if x is not None and y is not None), default=0.0)
check("/api/vector-map/match", len(a) == len(b) and diff <= MATCH_TOLERANCE, f"largest difference {diff:.2f}")

for options in ("kinds=usual&links=true", "kinds=all&links=false"):
    a, b = both(f"/api/recommend/steps?k=40&new_only=true&{options}")
    check(f"/api/recommend/steps {options}", [(s["key"], s["count"]) for s in a["steps"]] == [(s["key"], s["count"]) for s in b["steps"]]
          and a["info"] == b["info"], str([s["count"] for s in a["steps"]]))
for options in ("mode=hybrid&new_only=true&kinds=usual&links=true", "mode=hybrid&new_only=true&kinds=all&links=false",
                "mode=diverse&new_only=true&kinds=usual&links=true", "mode=hybrid&new_only=false&kinds=usual&links=true",
                f"seed={seeds[-1]}&new_only=true&kinds=usual&links=true"):
    a, b = both(f"/api/recommend?k=40&{options}")
    compare_shows(f"/api/recommend {options}", a, b, check, order_changes=2)

# Discover: random cards, thus only the shape and the numbers
a, b = both("/api/discover?count=12")
check("/api/discover", len(a["cards"]) == len(b["cards"]) == 12 and a["counts"] == b["counts"], f"counts {b['counts']}")
ids = ",".join(c["id"] for c in b["cards"])
a, b = both(f"/api/frames?ids={ids}")
# The Python server asks AniList for a show without a file, and it writes the file. Thus ask the Rust server again.
time.sleep(0.5)
b = get(RUST, f"/api/frames?ids={ids}")[2]
check("/api/frames", a == b, f"{len(a)} / {len(b)} shows with pictures")

# The pages
for path in ("/", "/ui/app.js", "/next/", "/next/ratings", "/next/_app/immutable/missing.js", "/next/missing.css"):
    a, b = get(PYTHON, path), get(RUST, path)
    same_page = a[0] == b[0] and a[1].get("cache-control") == b[1].get("cache-control") and (a[0] != 200 or a[2] == b[2])
    check(f"page {path}", same_page, f"{a[0]} {a[1].get('cache-control')} / {b[0]} {b[1].get('cache-control')}")
# A file of the build with a hash in its name. The page has relative addresses: "./_app/immutable/..."
status, _, page = get(RUST, "/next/")
found = re.search(r'_app/immutable/[^"]+?\.js', page) if isinstance(page, str) else None
asset = found.group(0) if found else ""
a, b = get(PYTHON, f"/next/{asset}"), get(RUST, f"/next/{asset}")
check(f"page /next/{asset[:40]}", bool(asset) and a[0] == b[0] == 200 and a[1].get("cache-control") == b[1].get("cache-control") and "immutable" in (b[1].get("cache-control") or ""),
      f"{a[1].get('cache-control')} / {b[1].get('cache-control')}")
# A change of an unknown show: 404, or 405 from a Rust server without --write. The script does
# not change data: write_check.py compares the changes.
request = urllib.request.Request(RUST + "/api/weights", data=b'{"id": "no-such-show", "tier": "S"}', method="POST",
                                 headers={"content-type": "application/json"})
try:
    urllib.request.urlopen(request, timeout=10)
    check("a change of an unknown show", False, "the Rust server accepted the change")
except urllib.error.HTTPError as error:
    check("a change of an unknown show", error.code in (404, 405), f"{error.code} ({'reads only' if error.code == 405 else 'changes data'})")

print("all equal within the tolerances" if not failed else f"{len(failed)} checks failed")
sys.exit(1 if failed else 0)
