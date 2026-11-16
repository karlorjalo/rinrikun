# rinrikun

Semantic taste map for your anime library: embeds your Jellyfin library plus a pool of popular AniList anime into a local vector index, then serves a web UI for taste profiling, similar-to search, and recommendations.

## What it does

- **Profile** — the number of shows in each tier and the map of the index, with your S-tier shows as posters.
- **Similar** — type any title, get nearest neighbors with similarity % and shared tags.
- **Ratings** — the shows that you rated, by tier, and the shows that you marked as watched by hand.
- **Recommendations** — unowned AniList anime from franchises that you do not own, with one result for each franchise. **Formula** selects one of two formulas. **My usual kinds** gives a higher score to the kinds of shows that your library has many of. The kind of a show is its year, its format, its number of episodes and its crowd score. **All kinds** gives each kind of show the same chance, and its list has more shows that are less well-known. A line above the list tells which formula made the list. Two switches change the list: **More variety** gives results that are less similar to each other, and **Include sequels** adds the franchises that you own. The score has these parts: the similarity to your nearest liked shows (text embedding plus tag TF-IDF), the AniList user recommendations that connect your liked shows to the candidate, and a penalty for the similarity to your C-tier and D-tier shows. A small model also learns from the tags of your rated shows which tier you will give. A candidate with a low predicted tier moves down. The ✕ button on a recommendation removes the show from the list. Shows like it then get a lower score. The Ratings tab lists the removed shows, and the detail window of a show can put it back. A franchise that you do not own appears as its first TV season. You can also seed the list from any show you click.
- **Map** — a 2D t-SNE layout of the index. Shows that are neighbors in the embedding space are neighbors on the map. In the far view each show is a dot. When you zoom in, each show moves to its own cell of a grid and becomes a poster, so that no poster covers another poster and you can see which shows are near a show. At the largest zoom a poster has its title. A show of yours has a frame in the color of its tier and a badge with the tier letter. A recommendation has a ✦ badge.
- **Settings** — choices for the look of the interface. The browser keeps them. The typeface setting has two options: serif titles (Noto Serif JP for titles and headings), and Noto Sans JP for all text.

## Setup

```
python -m pip install -r requirements.txt
# secrets.json (gitignored): {"jellyfin_api_key": "...", "jellyfin_user_id": "..."}
# or set JELLYFIN_API_KEY + JELLYFIN_USER_ID env vars.
# Jellyfin URL / user id live in anime_vec/jellyfin_pull.py (localhost by default).
```

First build downloads the ~1.1 GB local embedding model (EmbeddingGemma 2, the ONNX build `onnx-community/embeddinggemma-2-ONNX`, run with onnxruntime — no API keys, fully offline). The model is multilingual, because the Jellyfin rows are in Japanese and the AniList rows are in English.

### GPU (optional)

The build uses an NVIDIA GPU when the GPU packages are installed. A full build of 4300 titles then takes less than 1 minute.

```
python -m pip uninstall -y onnxruntime
python -m pip install "onnxruntime-gpu[cuda,cudnn]"
```

Without these packages the build uses the CPU. A full build is then much slower, but later builds embed only the changed rows.

## Run

```
python build.py                # pull Jellyfin + AniList pool, embed, persist to anime_vec.db
python build.py --refresh-anilist   # force re-pull of the AniList pool
python build.py --pool-only    # only the 5000 most popular anime (quicker first build)
python serve.py                # serves http://localhost:8765 and opens it
python serve.py --host 0.0.0.0 --port 8771   # also accepts connections from other computers
python evaluate.py --tiers     # offline test of the recommendations (read-only)
```

Rebuilds are incremental: unchanged rows keep their cached embeddings. A change of the model or of the prompt in `anime_vec/embed.py` makes all embeddings stale. The build also computes the map layout (about 1 minute) and keeps it in the database until the embeddings change.

## Notes

- The build connects each library show to its AniList entries with the public id map of the Fribb/anime-lists project (TMDB, TVDB and IMDb ids, with season numbers). The file stays in `idmap_cache/` for 7 days. A title match finds the shows that the id map does not have.
- The catalog is all anime that the build can find: the 5000 most popular anime on AniList (the maximum for one query), all anime of the public id map, and the anime that these point to with a user recommendation or a franchise relation. That is about 21 000 anime. A show that is not released and a music video are in the catalog but not in the recommendations. The first build asks AniList for about 450 pages, which takes about 20 minutes. Later builds use the cache. The cache of a page is good for 30 days, and the cache of an anime that is not finished for 7 days.
- Two Jellyfin items with the same type and the same TMDB id are one show (for example two files of one movie). A show that Jellyfin does not have now goes out of the index at the next build. Its tier stays in the database.
- AniList pages are cached in `anilist_cache/` (corrupt files are refetched automatically; requires a browser User-Agent, which is handled for you).
- Index + cache + secrets are gitignored. The default host is 127.0.0.1 and the API has no auth. With `--host 0.0.0.0`, each computer that can connect to the port can read and change the ratings, so use it only on a network that you trust (for example behind a firewall rule for your VPN).
- Scale target: ~20k titles (brute-force numpy cosine).
- All similarities use mean-centered vectors: the engine subtracts the corpus mean before it computes a cosine.
- Without scikit-learn, or with less than 100 titles, the map uses PCA.
