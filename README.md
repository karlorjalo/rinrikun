# rinrikun

Semantic taste map for your anime library: embeds your Jellyfin library plus a pool of popular AniList anime into a local vector index, then serves a web UI for taste profiling, similar-to search, and recommendations.

## What it does

- **Profile** — computes the "taste center" (tier-weighted mean of the mean-centered embeddings) of your collection, lists the 15 shows nearest to it, and a tag-frequency summary.
- **Similar** — type any title, get nearest neighbors with similarity % and shared tags.
- **Recommendations** — unowned AniList anime ranked by similarity to your nearest liked shows (text embedding plus tag TF-IDF), with one result for each franchise. You can also seed the list from any show you click.
- **Map** — a 2D t-SNE layout of the index. Shows that are neighbors in the embedding space are neighbors on the map.

## Setup

```
python -m pip install -r requirements.txt
# secrets.json (gitignored): {"jellyfin_api_key": "...", "jellyfin_user_id": "..."}
# or set JELLYFIN_API_KEY + JELLYFIN_USER_ID env vars.
# Jellyfin URL / user id live in anime_vec/jellyfin_pull.py (localhost by default).
```

First build downloads the ~100 MB local embedding model (fastembed, BAAI/bge-small-en-v1.5 — no API keys, fully offline).

## Run

```
python build.py                # pull Jellyfin + AniList pool, embed, persist to anime_vec.db
python build.py --refresh-anilist   # force re-pull of the AniList pool
python serve.py                # serves http://localhost:8765 and opens it
```

Rebuilds are incremental: unchanged rows keep their cached embeddings. The build also computes the map layout (about 1 minute) and keeps it in the database until the embeddings change.

## Notes

- AniList pages are cached in `anilist_cache/` (corrupt files are refetched automatically; requires a browser User-Agent, which is handled for you).
- Index + cache + secrets are gitignored; everything runs on 127.0.0.1, no auth — keep it that way.
- Scale target: ~20k titles (brute-force numpy cosine).
- All similarities use mean-centered vectors: the engine subtracts the corpus mean before it computes a cosine.
- Without scikit-learn, or with less than 100 titles, the map uses PCA.
