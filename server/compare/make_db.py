"""Make a database with invented shows, for the comparison of the Python engine and the Rust engine.

The database has the same tables as the real database (it uses anime_vec.store), and each kind
of data that the engine uses: library shows with their AniList entries, franchises, the links of
AniList users, tiers (also on an AniList entry of a library show), shows marked as watched by
hand, removed shows, answers of the Discover deck, and the log of the recommendations. Each show
is invented, thus the results from this database can go into the public repository.

    python server/compare/make_db.py <file> [--rows 3000] [--seed 7]

The same seed gives the same database.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from anime_vec.store import Store  # noqa: E402

KINDS = 12
DIM = 96
TAGS_PER_KIND = 14
FORMATS = ["tv", "tv", "tv", "tv", "movie", "ova", "ona", "special", "tv_short", "music"]
GENRES = ["Action", "Comedy", "Drama", "Fantasy", "Romance", "Sci-Fi", "Slice of Life", "Mystery", "Music", "Sports"]
TIERS = ["S", "A", "A", "B", "B", "B", "C", "D"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--rows", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        out.unlink()
    rng = np.random.default_rng(args.seed)
    store = Store(out)

    # Each kind of show has its own tags and its own direction in the embedding space
    tag_names = [f"tag {k}-{n}" for k in range(KINDS) for n in range(TAGS_PER_KIND)] + [f"shared {n}" for n in range(20)]
    centers = rng.normal(size=(KINDS, DIM))
    common = rng.normal(size=DIM) * 2.0

    n = args.rows
    kind_of = rng.integers(KINDS, size=n)
    anilist_ids = 100000 + np.arange(n)
    # Franchises: groups of 1 to 4 neighbours in the list, connected with relations
    group = np.zeros(n, dtype=int)
    g = 0
    i = 0
    while i < n:
        size = int(rng.choice([1, 1, 1, 2, 2, 3, 4]))
        group[i:i + size] = g
        g += 1
        i += size
    members: dict[int, list[int]] = {}
    for j in range(n):
        members.setdefault(int(group[j]), []).append(j)
        kind_of[j] = kind_of[members[int(group[j])][0]]
    place = rng.permutation(n) + 1

    rows = []
    vectors = {}
    for j in range(n):
        k = int(kind_of[j])
        count = int(rng.integers(3, 12))
        own_tags = rng.choice(TAGS_PER_KIND, size=min(count, TAGS_PER_KIND), replace=False)
        tags = [tag_names[k * TAGS_PER_KIND + int(t)] for t in own_tags]
        if rng.random() < 0.5:
            tags.append(f"shared {int(rng.integers(20))}")
        # Some ranks are missing: the engine then uses 50
        ranks = [int(rng.integers(30, 100)) if rng.random() > 0.1 else 0 for _ in tags]
        genres = [GENRES[k % len(GENRES)]] + ([GENRES[int(rng.integers(len(GENRES)))]] if rng.random() < 0.6 else [])
        fmt = FORMATS[int(rng.integers(len(FORMATS)))]
        relations = [int(anilist_ids[m]) for m in members[int(group[j])] if m != j and rng.random() < 0.8]
        if rng.random() < 0.01:
            # A relation to an anime that is not in the database
            relations.append(int(9_000_000 + rng.integers(1000)))
        recs = []
        for _ in range(int(rng.integers(0, 6))):
            same = rng.random() < 0.7
            pool = np.nonzero(kind_of == k)[0] if same else np.arange(n)
            other = int(pool[int(rng.integers(len(pool)))])
            recs.append([int(anilist_ids[other]), int(rng.integers(-2, 40))])
        status = "NOT_YET_RELEASED" if rng.random() < 0.03 else "FINISHED"
        rows.append({
            "id": f"al:{anilist_ids[j]}", "source": "anilist", "title": f"Show {j}", "title_native": f"作品{j}" if j % 3 else "",
            "title_english": f"The Show {j}" if j % 4 == 0 else None,
            "year": int(rng.integers(1985, 2027)) if rng.random() > 0.02 else None, "format": fmt,
            "genres": genres, "tags": tags, "tag_ranks": ranks, "studios": [f"Studio {k}"], "overview": f"An invented show {j}.",
            "score": round(float(rng.uniform(5.0, 9.0)), 1) if rng.random() > 0.05 else None,
            "owned": 0, "tmdbid": None, "anilist_id": int(anilist_ids[j]), "poster": f"https://example.invalid/{j}.jpg",
            "relations": relations, "recommendations": recs, "status": status,
            "episodes": 1 if fmt == "movie" else (int(rng.integers(1, 60)) if rng.random() > 0.05 else None),
            "popularity_place": int(place[j]) if place[j] <= n * 0.7 else None,
        })
        vectors[rows[-1]["id"]] = common + centers[k] * 1.5 + rng.normal(size=DIM)

    # The library: shows of the user from the media server. Most have one or two AniList entries.
    library = []
    starts = rng.choice([members[f][0] for f in members], size=160, replace=False)
    for number, j in enumerate(starts):
        lib_id = f"jf:{number:04x}{int(rng.integers(1 << 16)):04x}"
        k = int(kind_of[j])
        library.append({
            "id": lib_id, "source": "library", "title": f"Library show {number}", "title_native": "",
            "year": rows[j]["year"], "format": "series", "genres": [], "tags": [], "tag_ranks": [], "studios": [],
            "overview": "", "score": round(float(rng.uniform(6, 9)), 1), "owned": 1, "tmdbid": str(number),
            "anilist_id": None, "poster": None, "status": None, "episodes": None,
        })
        vectors[lib_id] = common + centers[k] * 1.5 + rng.normal(size=DIM)
        if number < 150:
            # The AniList entries of this show: its franchise, from the first entry
            for m in members[int(group[j])][: int(rng.integers(1, 3))]:
                rows[m]["library_id"] = lib_id
                rows[m]["owned"] = 1
    store.upsert_rows(rows + library)
    for row_id, v in vectors.items():
        store.save_embedding(row_id, np.asarray(v, dtype=np.float32).tobytes())
    # One row without an embedding: the engine leaves it out
    store.upsert_rows([dict(rows[0], id="al:999999999", anilist_id=999999999, relations=[], recommendations=[])])

    catalog = [r["id"] for r in rows if not r.get("library_id")]
    manual = list(rng.choice(catalog, size=40, replace=False))
    for row_id in manual:
        store.set_manual_watched(row_id, True)
    lib_ids = [r["id"] for r in library]
    # Tiers: on library shows, on shows marked by hand, and on two AniList entries of library shows
    for row_id in lib_ids[:120] + manual[:30]:
        store.set_weight(row_id, TIERS[int(rng.integers(len(TIERS)))])
    entries = [r["id"] for r in rows if r.get("library_id") in lib_ids[120:150]]
    for row_id in entries[:2]:
        store.set_weight(row_id, "A")
    rest = [i for i in catalog if i not in set(manual)]
    removed = list(rng.choice(rest, size=50, replace=False))
    for row_id in removed:
        store.set_dismissed(row_id, True)
    answered = [i for i in rest if i not in set(removed)]
    for row_id in rng.choice(answered, size=90, replace=False):
        store.set_interest(row_id, int(rng.random() < 0.55), float(rng.uniform(0, 100)), "deck" if rng.random() < 0.8 else "page")
    # An answer for a show that the user has: the engine ignores it in the models
    store.set_interest(manual[0], 1, 50.0, "deck")
    store.log_recommendations([(i, int(rng.integers(40))) for i in rng.choice(answered, size=60, replace=False)], "usual", "2026-10-01")
    store.log_recommendations([(i, int(rng.integers(40))) for i in rng.choice(answered, size=20, replace=False)], "all, no links", "2026-10-08")
    print(f"{out}: {len(rows)} AniList rows, {len(library)} library rows")


if __name__ == "__main__":
    main()
