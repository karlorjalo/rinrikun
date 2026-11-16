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
CREATE TABLE IF NOT EXISTS layout (
  id TEXT PRIMARY KEY,
  x REAL NOT NULL,
  y REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
"""

# The columns of the shows table that the build writes
COLUMNS = ("id", "source", "title", "title_native", "year", "format", "genres", "tags", "tag_ranks", "studios",
           "overview", "score", "owned", "tmdbid", "anilist_id", "poster", "relations", "recommendations",
           "library_id", "provider_ids", "seasons", "added_at")
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
        for column in ("relations", "recommendations", "library_id", "provider_ids", "seasons", "added_at"):
            if column not in columns:
                self.con.execute(f"ALTER TABLE shows ADD COLUMN {column} TEXT")
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

    def get_layout(self, signature: str) -> dict[str, tuple[float, float]] | None:
        """Return the cached map layout, or None if the cache is for other embeddings."""
        t = self.con.execute("SELECT value FROM meta WHERE key='layout_signature'").fetchone()
        if not t or t[0] != signature:
            return None
        return {r[0]: (r[1], r[2]) for r in self.con.execute("SELECT id, x, y FROM layout")}

    def save_layout(self, signature: str, coords: dict[str, tuple[float, float]]):
        if self.read_only:
            return
        self.con.execute("DELETE FROM layout")
        self.con.executemany("INSERT INTO layout (id, x, y) VALUES (?, ?, ?)",
                             [(k, float(v[0]), float(v[1])) for k, v in coords.items()])
        self.con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('layout_signature', ?)", (signature,))
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
        cur = self.con.execute(f"SELECT {','.join(COLUMNS)},text_hash FROM shows ORDER BY id")
        out = []
        for t in cur.fetchall():
            r = dict(zip(COLUMNS + ("text_hash",), t))
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
