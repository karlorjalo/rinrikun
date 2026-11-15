import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from anime_vec.anilist_pull import fetch_pool
from anime_vec.embed import build_text, embed_texts, text_hash, vec_to_blob
from anime_vec.jellyfin_pull import fetch_library
from anime_vec.match import OwnershipMatcher
from anime_vec.store import Store

DB = Path(__file__).resolve().parent / "anime_vec.db"


def main(refresh_anilist: bool = False):
    store = Store(DB)
    lib_rows = fetch_library()
    print(f"library rows: {len(lib_rows)}")
    pool_rows = fetch_pool(force=refresh_anilist)
    print(f"anilist pool rows: {len(pool_rows)}")

    matcher = OwnershipMatcher([(r["id"], r["title_native"], r["title"]) for r in lib_rows])
    flagged = 0
    for r in pool_rows:
        hit = matcher.match(r["title"], r["title_native"])
        if hit:
            r["owned"] = 1
            flagged += 1
    print(f"pool rows matched to library: {flagged}")

    manual_ids = store.get_manual_watched_ids()
    for r in pool_rows:
        if r["id"] in manual_ids:
            r["owned"] = 1

    store.upsert_rows(lib_rows + pool_rows)

    rows = store.load_rows()
    todo = [r for r in rows if not r["text_hash"] or r["text_hash"] != text_hash(r)
            or not store.get_embedding(r["id"])]
    print(f"embedding {len(todo)} rows (skipped {len(rows) - len(todo)} unchanged)")
    missing_overview = [r["title"] for r in rows if not r["overview"]]
    if missing_overview:
        print(f"WARNING rows without overview: {len(missing_overview)} e.g. {missing_overview[:5]}")
    for i in range(0, len(todo), 64):
        batch = todo[i:i + 64]
        vecs = embed_texts([build_text(r) for r in batch])
        for r, v in zip(batch, vecs):
            store.save_embedding(r["id"], vec_to_blob(v))
            store.save_hash(r["id"], text_hash(r))
        print(f"  {min(i + 64, len(todo))}/{len(todo)}")
    # The engine computes the map layout and keeps it in the database, thus the server starts quickly
    print("computing the map layout")
    from anime_vec.engine import Engine
    Engine(store)
    print(f"done -> {DB}")


if __name__ == "__main__":
    main(refresh_anilist="--refresh-anilist" in sys.argv)
