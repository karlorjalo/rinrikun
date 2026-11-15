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
"""


class Store:
    def __init__(self, path):
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self.con.executescript(SCHEMA)

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

    def upsert_rows(self, rows: list[dict]):
        for r in rows:
            self.con.execute(
                "INSERT INTO shows (id,source,title,title_native,year,format,genres,tags,"
                "tag_ranks,studios,overview,score,owned,tmdbid,anilist_id,poster) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, title_native=excluded.title_native,"
                "year=excluded.year, format=excluded.format, genres=excluded.genres, tags=excluded.tags,"
                "tag_ranks=excluded.tag_ranks, studios=excluded.studios, overview=excluded.overview,"
                "score=excluded.score, owned=excluded.owned, tmdbid=excluded.tmdbid,"
                "anilist_id=excluded.anilist_id, poster=excluded.poster",
                (r["id"], r["source"], r["title"], r["title_native"], r["year"], r["format"],
                 json.dumps(r["genres"], ensure_ascii=False), json.dumps(r["tags"], ensure_ascii=False),
                 json.dumps(r["tag_ranks"]), json.dumps(r["studios"], ensure_ascii=False),
                 r["overview"], r["score"], r["owned"], r["tmdbid"], r["anilist_id"], r["poster"]))
        self.con.commit()

    def load_rows(self) -> list[dict]:
        manual_ids = self.get_manual_watched_ids()
        cur = self.con.execute(
            "SELECT id,source,title,title_native,year,format,genres,tags,tag_ranks,studios,"
            "overview,score,owned,tmdbid,anilist_id,poster,text_hash FROM shows ORDER BY id")
        out = []
        for t in cur.fetchall():
            row_id = t[0]
            is_manual = row_id in manual_ids
            owned = 1 if (t[12] or is_manual) else 0
            out.append({"id": t[0], "source": t[1], "title": t[2], "title_native": t[3],
                        "year": t[4], "format": t[5], "genres": json.loads(t[6]),
                        "tags": json.loads(t[7]), "tag_ranks": json.loads(t[8]),
                        "studios": json.loads(t[9]), "overview": t[10], "score": t[11],
                        "owned": owned, "manual_watched": 1 if is_manual else 0,
                        "tmdbid": t[13], "anilist_id": t[14],
                        "poster": t[15], "text_hash": t[16]})
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
