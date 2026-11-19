"""Send the same changes to the Python server and to the Rust server, and compare the answers and the tables.

    python server/compare/write_check.py <python address> <rust address> <python database> <rust database>

Start the two servers on two copies of one database: the Python server in a folder with its copy
as anime_vec.db, and the Rust server with --write on the other copy. The script changes the data
of the user on the two servers. It compares each answer, then the tables of the data of the user,
then the lists. At the end it answers some cards of the Discover deck on each server, and it checks
that the database keeps the match that the card showed. It ends with code 1 if a check fails.

Do not use the live database: the script changes tiers, marks and answers.
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.request

from compare import MATCH_TOLERANCE, compare_shows

PYTHON, RUST = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")
DATABASES = {PYTHON: sys.argv[3], RUST: sys.argv[4]}
failed = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    if not ok:
        failed.append(name)


def send(base: str, method: str, path: str, body=None):
    """Return (status, JSON) of one request"""
    data = None if body is None else json.dumps(body).encode()
    headers = {"content-type": "application/json"} if data is not None else {}
    request = urllib.request.Request(base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def both(method: str, path: str, body=None, status_only=False):
    """Send one request to the two servers: the same status and the same answer"""
    a, b = send(PYTHON, method, path, body), send(RUST, method, path, body)
    name = f"{method} {path}" + (f" {json.dumps(body)}" if body is not None else "")
    same = a[0] == b[0] if status_only else a == b
    check(name, same, f"{a} / {b}" if not same else f"{a[0]}")
    return a[1], b[1]


def table(base: str, sql: str) -> list:
    con = sqlite3.connect(f"file:{DATABASES[base]}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def compare_tables():
    for sql in ("SELECT id, tier, weight FROM show_weights ORDER BY rowid", "SELECT id FROM watched_manual ORDER BY rowid",
                "SELECT id FROM dismissed ORDER BY rowid", "SELECT id, first_seen, last_seen, best_rank, days, kinds FROM rec_log ORDER BY rowid",
                "SELECT id, owned FROM shows ORDER BY id"):
        a, b = table(PYTHON, sql), table(RUST, sql)
        check(f"table: {sql}", a == b, f"{len(a)} / {len(b)} rows")
    sql = "SELECT id, value, match, source FROM interest ORDER BY rowid"
    a, b = table(PYTHON, sql), table(RUST, sql)
    same = [(r[0], r[1], r[3]) for r in a] == [(r[0], r[1], r[3]) for r in b]
    diff = max((abs(x[2] - y[2]) for x, y in zip(a, b) if x[2] is not None and y[2] is not None), default=0.0)
    nulls = [r[2] is None for r in a] == [r[2] is None for r in b]
    check(f"table: {sql}", same and nulls and diff <= MATCH_TOLERANCE, f"{len(a)} / {len(b)} rows, largest difference of the match {diff:.3f}")


titles = send(PYTHON, "GET", "/api/shows")[1]
manual = {s["id"] for s in send(PYTHON, "GET", "/api/watched")[1]}
owned = [t["id"] for t in titles if t["owned"]]
library = [i for i in owned if i not in manual]
free = [t["id"] for t in titles if not t["owned"]]
o = owned[:: max(1, len(owned) // 8)][:6]
f = free[:: max(1, len(free) // 14)][:12]
print(f"{len(titles)} shows, {len(owned)} of the user, {len(library)} of the library")

# Tiers
both("POST", "/api/weights", {"id": o[0], "tier": "S"})
both("POST", "/api/weights", {"id": o[1], "tier": "c"})
both("POST", "/api/weights", {"id": o[2], "tier": "A"})
both("POST", "/api/weights", {"id": o[0], "tier": "B"})
both("DELETE", f"/api/weights?id={o[1]}")
both("POST", "/api/weights", {"id": o[2], "tier": None})
both("POST", "/api/weights", {"id": o[3], "tier": ""})
both("POST", "/api/weights", {"id": "no-such-show", "tier": "S"})
both("POST", "/api/weights", {})
both("DELETE", "/api/weights?id=no-such-show")
both("DELETE", "/api/weights", status_only=True)
# Shows marked as watched by hand
both("POST", "/api/watched", {"id": f[0]})
both("POST", "/api/watched", {"id": f[1], "watched": True})
both("POST", "/api/weights", {"id": f[1], "tier": "A"})
both("POST", "/api/watched", {"id": f[0], "watched": False})
both("POST", "/api/watched", {"id": f[9], "watched": "yes"})
if library:
    both("POST", "/api/watched", {"id": library[0], "watched": True})
    both("POST", "/api/watched", {"id": library[0], "watched": False})
both("POST", "/api/watched", {"id": "no-such-show"})
# Removed shows and answers
both("POST", "/api/dismissed", {"id": f[2]})
both("POST", "/api/dismissed", {"id": f[3], "dismissed": True})
both("POST", "/api/interest", {"id": f[3], "value": True, "source": "deck"})
both("POST", "/api/interest", {"id": f[4], "value": False, "source": "page"})
both("POST", "/api/dismissed", {"id": f[4], "dismissed": False})
both("POST", "/api/interest", {"id": f[5], "value": True})
both("POST", "/api/interest", {"id": f[5], "value": None})
both("POST", "/api/interest", {"id": f[6], "value": 0})
both("POST", "/api/interest", {"id": o[0], "value": True})
both("POST", "/api/interest", {"id": f[7], "value": True, "source": "deck"})
both("POST", "/api/dismissed", {"id": f[7]})
both("POST", "/api/dismissed", {"id": f[8], "dismissed": 0})
both("POST", "/api/interest", {"id": f[10], "value": False})
both("POST", "/api/interest", {"id": "no-such-show", "value": True})
# Lists without a seed go into the log; a list with a seed does not
for options in ("kinds=usual&links=false", "kinds=all&links=true", f"seed={o[0]}&kinds=usual&links=true"):
    a, b = both("GET", f"/api/recommend?k=20&{options}", status_only=True)
    compare_shows(f"/api/recommend {options}", a, b, check, order_changes=2)
both("POST", "/api/weights", {"id": o[4], "tier": "D"})

compare_tables()
for path in ("/api/profile", "/api/weights", "/api/rec-log", "/api/shows"):
    both("GET", path)
a, b = both("GET", "/api/interest/results", status_only=True)
same = {k: v for k, v in a.items() if k != "model"} == {k: v for k, v in b.items() if k != "model"}
same = same and (a["model"] is None) == (b["model"] is None) and (a["model"] is None or abs(a["model"]["auc"] - b["model"]["auc"]) <= 0.002)
check("/api/interest/results", same)
for path in ("/api/ratings", "/api/watched", "/api/dismissed", "/api/review-queue?unrated_only=true", "/api/review-queue", "/api/interest"):
    a, b = both("GET", path, status_only=True)
    compare_shows(path, a, b, check, order_changes=2)
for options in ("mode=hybrid&new_only=true&kinds=usual&links=true", "mode=diverse&new_only=true&kinds=all&links=false"):
    a, b = both("GET", f"/api/recommend?k=40&{options}", status_only=True)
    compare_shows(f"/api/recommend {options}", a, b, check, order_changes=2)
compare_tables()

# The Discover deck: each server draws its own random cards. The answer keeps the match of the card.
for base in (PYTHON, RUST):
    cards = send(base, "GET", "/api/discover?count=6")[1]["cards"]
    answers = {card["id"]: (card.get("match"), i % 2 == 0) for i, card in enumerate(cards[:4])}
    for card_id, (_, value) in answers.items():
        status, _ = send(base, "POST", "/api/interest", {"id": card_id, "value": value, "source": "deck"})
        check(f"deck answer on {base}", status == 200, str(status))
    stored = {r[0]: r for r in table(base, "SELECT id, value, match, source FROM interest")}
    for card_id, (shown, value) in answers.items():
        row = stored.get(card_id)
        ok = row is not None and row[1] == int(value) and row[3] == "deck" and (
            (shown is None and row[2] is None) or (shown is not None and row[2] is not None and abs(row[2] - shown) <= 0.051))
        check(f"deck match on {base} {card_id}", ok, f"shown {shown}, kept {row[2] if row else None}")

print("all equal within the tolerances" if not failed else f"{len(failed)} checks failed")
sys.exit(1 if failed else 0)
