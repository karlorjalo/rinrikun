import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS shows (
  id TEXT PRIMARY KEY, source TEXT, title TEXT, title_native TEXT, year INTEGER,
  format TEXT, genres TEXT, tags TEXT, tag_ranks TEXT, studios TEXT,
  overview TEXT, score REAL, owned INTEGER, tmdbid TEXT, anilist_id INTEGER,
  poster TEXT, text_hash TEXT, embedding BLOB
);
CREATE TABLE IF NOT EXISTS watched_manual (
  id TEXT PRIMARY KEY,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS show_weights (
  id TEXT PRIMARY KEY,
  tier TEXT NOT NULL,
  weight REAL NOT NULL,
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS dismissed (
  id TEXT PRIMARY KEY,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS interest (
  id TEXT PRIMARY KEY,
  value INTEGER NOT NULL,
  match REAL,
  source TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS layout (
  id TEXT PRIMARY KEY,
  x REAL NOT NULL,
  y REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS layout_grid (
  id TEXT PRIMARY KEY,
  x REAL NOT NULL,
  y REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS rec_log (
  id TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  best_rank INTEGER NOT NULL,
  days INTEGER NOT NULL,
  kinds TEXT
);
"""

# The columns of the shows table that the build writes
COLUMNS = ("id", "source", "title", "title_native", "year", "format", "genres", "tags", "tag_ranks", "studios",
           "overview", "score", "owned", "tmdbid", "anilist_id", "poster", "relations", "recommendations",
           "library_id", "provider_ids", "seasons", "added_at", "status", "episodes", "title_english")
# The columns that hold JSON, with the value for a row that has no data
JSON_COLUMNS = {"genres": [], "tags": [], "tag_ranks": [], "studios": [], "relations": [], "recommendations": [],
                "provider_ids": {}, "seasons": []}

TIER_WEIGHTS = {
    "S": 2.0,
    "A": 1.5,
    "B": 1.0,
    "C": 0.3,
    "D": 0.0,
}


class Store:
    def __init__(self, path, read_only: bool = False):
        self.read_only = read_only
        if read_only:
            # A test or a report must not change the database
            self.con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
            return
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.executescript(SCHEMA)
        # Older databases do not have the columns that later features added
        columns = {r[1] for r in self.con.execute("PRAGMA table_info(shows)")}
        for column in ("relations", "recommendations", "library_id", "provider_ids", "seasons", "added_at",
                       "status", "episodes", "title_english"):
            if column not in columns:
                kind = "INTEGER" if column == "episodes" else "TEXT"
                self.con.execute(f"ALTER TABLE shows ADD COLUMN {column} {kind}")
        self.con.commit()

    def get_manual_watched_ids(self) -> set[str]:
        cur = self.con.execute("SELECT id FROM watched_manual")
        return {r[0] for r in cur.fetchall()}

    def set_manual_watched(self, show_id: str, watched: bool = True):
        if watched:
            self.con.execute("INSERT OR REPLACE INTO watched_manual (id) VALUES (?)", (show_id,))
            self.con.execute("UPDATE shows SET owned=1 WHERE id=?", (show_id,))
        else:
            self.con.execute("DELETE FROM watched_manual WHERE id=?", (show_id,))
            self.con.execute("UPDATE shows SET owned=0 WHERE id=? AND source != 'library'", (show_id,))
        self.con.commit()

    def get_dismissed_ids(self) -> set[str]:
        """Return the ids of the shows that the user removed from the recommendations."""
        try:
            cur = self.con.execute("SELECT id FROM dismissed")
        except sqlite3.OperationalError:
            # A read-only database from an older version does not have this table
            return set()
        return {r[0] for r in cur.fetchall()}

    def set_dismissed(self, show_id: str, dismissed: bool = True):
        if dismissed:
            self.con.execute("INSERT OR REPLACE INTO dismissed (id) VALUES (?)", (show_id,))
        else:
            self.con.execute("DELETE FROM dismissed WHERE id=?", (show_id,))
        self.con.commit()

    def get_interest(self) -> dict[str, dict]:
        """Return the answers of the Discover deck, by the id of the show.

        An answer has the value (1 = interested, 0 = not interested), the match of the show at
        the time of the answer, and the source: "deck" for the Discover deck, "page" for a
        button on a page.
        """
        try:
            cur = self.con.execute("SELECT id, value, match, source FROM interest")
        except sqlite3.OperationalError:
            # A read-only database from an older version does not have this table
            return {}
        return {r[0]: {"value": int(r[1]), "match": r[2], "source": r[3]} for r in cur.fetchall()}

    def set_interest(self, show_id: str, value: int | None, match: float | None = None, source: str = "deck"):
        """Record an answer of the user for a show. The value None deletes the answer."""
        if value is None:
            self.con.execute("DELETE FROM interest WHERE id=?", (show_id,))
        else:
            self.con.execute("INSERT OR REPLACE INTO interest (id, value, match, source) VALUES (?, ?, ?, ?)",
                             (show_id, int(value), match, source))
        self.con.commit()

    def log_recommendations(self, items: list[tuple[str, int]], kinds: str, today: str):
        """Record the shows of a list of recommendations. Each item is (id, place in the list).

        The log keeps for each show the first day and the last day on which a list had it, its
        best place, the number of days, and the formula of the first list.
        """
        if self.read_only:
            return
        for show_id, rank in items:
            self.con.execute(
                "INSERT INTO rec_log (id, first_seen, last_seen, best_rank, days, kinds) VALUES (?, ?, ?, ?, 1, ?) "
                "ON CONFLICT(id) DO UPDATE SET best_rank = MIN(best_rank, excluded.best_rank), "
                "days = days + (last_seen != excluded.last_seen), last_seen = excluded.last_seen",
                (show_id, today, today, int(rank), kinds))
        self.con.commit()

    def get_rec_log(self) -> dict[str, dict]:
        """Return the log of the recommendations, by the id of the show."""
        try:
            cur = self.con.execute("SELECT id, first_seen, last_seen, best_rank, days, kinds FROM rec_log")
        except sqlite3.OperationalError:
            # A read-only database from an older version does not have this table
            return {}
        return {r[0]: {"first_seen": r[1], "last_seen": r[2], "best_rank": r[3], "days": r[4], "kinds": r[5]}
                for r in cur.fetchall()}

    def get_weights(self) -> dict[str, dict]:
        cur = self.con.execute("SELECT id, tier, weight FROM show_weights")
        return {r[0]: {"tier": r[1], "weight": float(r[2])} for r in cur.fetchall()}

    def set_weight(self, show_id: str, tier: str, weight: float | None = None):
        tier_upper = tier.upper()
        if weight is None:
            weight = TIER_WEIGHTS.get(tier_upper, 1.0)
        self.con.execute(
            "INSERT OR REPLACE INTO show_weights (id, tier, weight, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (show_id, tier_upper, weight),
        )
        self.con.commit()

    def delete_weight(self, show_id: str):
        self.con.execute("DELETE FROM show_weights WHERE id=?", (show_id,))
        self.con.commit()

    def copy_weight(self, from_id: str, to_id: str) -> bool:
        """Give the tier of one show to a show that has no tier. Return True if the tier was copied."""
        weights = self.get_weights()
        if from_id not in weights or to_id in weights:
            return False
        self.set_weight(to_id, weights[from_id]["tier"], weights[from_id]["weight"])
        return True

    def delete_library_rows_except(self, keep_ids) -> int:
        """Delete the library rows whose id is not in `keep_ids`. Return the number of deleted rows.

        A show that the library does not have now must not stay in the lists. Its tier stays in
        the database: if the show comes back with the same id, it has its tier again.
        """
        keep = set(keep_ids)
        gone = [r[0] for r in self.con.execute("SELECT id FROM shows WHERE source='library'") if r[0] not in keep]
        for row_id in gone:
            self.con.execute("DELETE FROM shows WHERE id=?", (row_id,))
        self.con.commit()
        return len(gone)

    def get_layout(self, signature: str) -> dict | None:
        """Return the cached map layout, or None if the cache is for other embeddings.

        The result has "coords" (the map position of each show), "grid" (the cell of each show in
        the close view) and "cell" (the width and the height of a cell).
        """
        try:
            meta = dict(self.con.execute("SELECT key, value FROM meta WHERE key IN ('layout_signature', 'layout_cell')"))
            if meta.get("layout_signature") != signature or not meta.get("layout_cell"):
                return None
            coords = {r[0]: (r[1], r[2]) for r in self.con.execute("SELECT id, x, y FROM layout")}
            grid = {r[0]: (r[1], r[2]) for r in self.con.execute("SELECT id, x, y FROM layout_grid")}
        except sqlite3.OperationalError:
            # A read-only database from an older version does not have the grid table
            return None
        width, height = (float(v) for v in meta["layout_cell"].split(","))
        return {"coords": coords, "grid": grid, "cell": (width, height)}

    def save_layout(self, signature: str, coords: dict, grid: dict, cell: tuple[float, float]):
        if self.read_only:
            return
        self.con.execute("DELETE FROM layout")
        self.con.execute("DELETE FROM layout_grid")
        self.con.executemany("INSERT INTO layout (id, x, y) VALUES (?, ?, ?)",
                             [(k, float(v[0]), float(v[1])) for k, v in coords.items()])
        self.con.executemany("INSERT INTO layout_grid (id, x, y) VALUES (?, ?, ?)",
                             [(k, float(v[0]), float(v[1])) for k, v in grid.items()])
        self.con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('layout_signature', ?)", (signature,))
        self.con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('layout_cell', ?)",
                         (f"{float(cell[0])!r},{float(cell[1])!r}",))
        self.con.commit()

    def upsert_rows(self, rows: list[dict]):
        updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c not in ("id", "source"))
        sql = (f"INSERT INTO shows ({','.join(COLUMNS)}) VALUES ({','.join('?' * len(COLUMNS))}) "
               f"ON CONFLICT(id) DO UPDATE SET {updates}")
        for r in rows:
            values = []
            for c in COLUMNS:
                v = r.get(c)
                if c in JSON_COLUMNS:
                    v = json.dumps(v if v is not None else JSON_COLUMNS[c], ensure_ascii=False)
                values.append(v)
            self.con.execute(sql, values)
        self.con.commit()

    def load_rows(self) -> list[dict]:
        manual_ids = self.get_manual_watched_ids()
        weights = self.get_weights()
        # A read-only database from an older version does not have the newest columns
        existing = {r[1] for r in self.con.execute("PRAGMA table_info(shows)")}
        names = [c for c in COLUMNS + ("text_hash",) if c in existing]
        cur = self.con.execute(f"SELECT {','.join(names)} FROM shows ORDER BY id")
        out = []
        for t in cur.fetchall():
            r = dict.fromkeys(COLUMNS + ("text_hash",))
            r.update(zip(names, t))
            for c, default in JSON_COLUMNS.items():
                r[c] = json.loads(r[c]) if r[c] else type(default)()
            is_manual = r["id"] in manual_ids
            r["owned"] = 1 if (r["owned"] or is_manual) else 0
            r["manual_watched"] = 1 if is_manual else 0
            w_info = weights.get(r["id"])
            r["tier"] = w_info["tier"] if w_info else None
            r["weight"] = w_info["weight"] if w_info else 1.0
            out.append(r)
        return out

    def save_embedding(self, row_id: str, blob: bytes):
        self.con.execute("UPDATE shows SET embedding=? WHERE id=?", (blob, row_id))
        self.con.commit()

    def save_hash(self, row_id: str, h: str):
        self.con.execute("UPDATE shows SET text_hash=? WHERE id=?", (h, row_id))
        self.con.commit()

    def get_embedding(self, row_id: str):
        t = self.con.execute("SELECT embedding FROM shows WHERE id=?", (row_id,)).fetchone()
        return t[0] if t and t[0] else None

    def get_hash(self, row_id: str):
        t = self.con.execute("SELECT text_hash FROM shows WHERE id=?", (row_id,)).fetchone()
        return t[0] if t else None
