import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from anime_vec.anilist_pull import fetch_extras, fetch_pool
from anime_vec.embed import build_text, embed_texts, text_hash, vec_to_blob
from anime_vec.jellyfin_pull import fetch_library
from anime_vec.idmap import IdMap, load_entries
from anime_vec.match import link_library
from anime_vec.store import Store

DB = Path(__file__).resolve().parent / "anime_vec.db"


def main(refresh_anilist: bool = False, pool_only: bool = False):
    store = Store(DB)
    lib_rows = fetch_library()
    print(f"library rows: {len(lib_rows)}")
    if lib_rows:
        # Two Jellyfin items of one show are one row: the row keeps the tier of the other item
        for lib in lib_rows:
            for other in lib["merged_ids"]:
                store.copy_weight(other, lib["id"])
        removed = store.delete_library_rows_except(r["id"] for r in lib_rows)
        if removed:
            print(f"library rows that Jellyfin does not have now, removed: {removed}")
    pool_rows = fetch_pool(force=refresh_anilist)
    print(f"anilist pool rows: {len(pool_rows)}")

    try:
        idmap = IdMap(load_entries())
    except Exception as err:
        print(f"WARNING no id map ({err!r}): the match uses only titles")
        idmap = None
    if not pool_only:
        # AniList gives only the 5000 most popular anime for one query. The id map lists all anime
        # that the other anime databases know, thus the build asks for these by id. It also asks
        # for the anime that the catalog points to: an anime that was announced a short time ago
        # is frequently not in the id map.
        extra_rows = fetch_extras(pool_rows, idmap.all_ids if idmap is not None else (), force=refresh_anilist)
        print(f"anilist rows outside the pool: {len(extra_rows)}")
        pool_rows += extra_rows

    links = link_library(lib_rows, pool_rows, idmap)
    print(f"pool rows matched to library: {links['by_id']} by id, {links['by_title']} by title")
    print(f"library rows without a pool row: {len(links['unlinked_library_rows'])}")
    print(f"AniList entries of the library that are not in the pool: {len(links['missing_ids'])}")

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
    main(refresh_anilist="--refresh-anilist" in sys.argv, pool_only="--pool-only" in sys.argv)
