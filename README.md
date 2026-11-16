# rinrikun

Semantic taste map for your anime library: embeds your Jellyfin library plus a pool of popular AniList anime into a local vector index, then serves a web UI for taste profiling, similar-to search, and recommendations.

## What it does

- **Profile** — computes the "taste center" (tier-weighted mean of the mean-centered embeddings) of your collection, lists the 15 shows nearest to it, and a tag-frequency summary.
- **Similar** — type any title, get nearest neighbors with similarity % and shared tags.
- **Recommendations** — unowned AniList anime, with one result for each franchise. The Hybrid score has three parts: the similarity to your nearest liked shows (text embedding plus tag TF-IDF), the AniList user recommendations that connect your liked shows to the candidate, and a penalty for the similarity to your C-tier and D-tier shows. A franchise that you do not own appears as its first TV season. You can also seed the list from any show you click.
- **Map** — a 2D t-SNE layout of the index. Shows that are neighbors in the embedding space are neighbors on the map.

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
python serve.py                # serves http://localhost:8765 and opens it
python serve.py --host 0.0.0.0 --port 8771   # also accepts connections from other computers
```

Rebuilds are incremental: unchanged rows keep their cached embeddings. A change of the model or of the prompt in `anime_vec/embed.py` makes all embeddings stale. The build also computes the map layout (about 1 minute) and keeps it in the database until the embeddings change.

## Notes

- AniList pages are cached in `anilist_cache/` (corrupt files are refetched automatically; requires a browser User-Agent, which is handled for you).
- Index + cache + secrets are gitignored. The default host is 127.0.0.1 and the API has no auth. With `--host 0.0.0.0`, each computer that can connect to the port can read and change the ratings, so use it only on a network that you trust (for example behind a firewall rule for your VPN).
- Scale target: ~20k titles (brute-force numpy cosine).
- All similarities use mean-centered vectors: the engine subtracts the corpus mean before it computes a cosine.
- Without scikit-learn, or with less than 100 titles, the map uses PCA.
