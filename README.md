# rinrikun

Semantic taste map for your anime library: embeds your Jellyfin library plus a pool of popular AniList anime into a local vector index, then serves a web UI for taste profiling, similar-to search, and recommendations.

The name is the nickname 倫理君 (rinri-kun) that Utaha Kasumigaoka gives to Tomoya Aki in 冴えない彼女の育てかた (Saekano). The interface has some design choices from that series: a title in the style of the later logo of the circle blessing software (the logo of 6 years later, in Saekano Fine), cherry blossom petals, and message windows as in a visual novel. The lines in these windows are in the voice of Utaha. They are new text, not quotations from the series.

## What it does

- **Profile** — the number of shows in each tier and the map of the index, with your S-tier shows as posters. It also has the numbers of the recommendations: the server keeps a log of the new franchises that the list gave you, and the tab tells how many of them you added later and which tiers you gave them. The boxes of the tab have only numbers. The "i" mark of a box shows a text that explains them.
- **Similar** — type any title, get nearest neighbors with similarity % and shared tags. The search finds a show by its romaji title, its English title or its Japanese title. A show of your library has only its title from Jellyfin, thus the search also uses the titles of its AniList entries.
- **Ratings** — the shows that you rated, by tier, and the shows that you marked as watched by hand. This tab and the Review tab have a help card with one question for each tier. The questions say what a tier does: S, A and B give you more shows like the show, and C and D give you fewer.

- **Discover** — a mode of the Review tab for shows that you do not have. Your library has only shows that you selected, thus it has few shows that you dislike. The Discover deck draws shows at random, most of them with a high match, and you answer **Interested**, **Not interested** or **Seen it** (then you give a tier). An answer is a weak example for the taste model: it has one half of the weight of a tier, and the tier model does not use it. A show with the answer "not interested" is never a recommendation: it is in the same list as the shows that you removed with ✕. The shows with the answer "interested" are the **Watch list** of the Ratings tab. The Profile tab compares the answers with the match: if the match is good, a group of shows with a higher match has a larger part of "interested".
- **Recommendations** — unowned AniList anime from franchises that you do not own, with one result for each franchise. **Formula** selects one of two formulas. **My usual kinds** gives a higher score to the kinds of shows that your library has many of. The kind of a show is its year, its format and its number of episodes. A show with an AniList crowd score below 6.5 also moves down, because your library has few of these shows. A higher crowd score gives no advantage: the crowd score does not predict your tiers. **All kinds** gives each kind of show the same chance. The button **How this works** shows a tooltip that tells which formula made the list. Two switches change the list: **More variety** gives results that are less similar to each other, and **Include sequels** adds the franchises that you own. The score has these parts: the content score, and the AniList user recommendations that connect your liked shows to the candidate (a show of yours without a tier also counts there, with a smaller weight). The score has no penalty for the similarity to your C-tier and D-tier shows: a test with the answers of the Discover deck showed that a show near these shows is more frequently a show that you want. The content score is the mean of two values: the similarity to your nearest liked shows (text embedding plus tag TF-IDF), and a taste model. The taste model is a ridge regression on the tags of all shows of the catalog. It learns what your liked shows have and the catalog does not have. **Crowd links** turns the AniList user recommendations off. The list then comes only from your ratings, and from the tags and the text of the shows. The numbers on the Profile tab count the lists with the crowd links and the lists without them apart. A small model also learns from the tags of your rated shows which tier you will give. A candidate with a low predicted tier moves down. The ✕ button on a recommendation removes the show from the list. The taste model and the tier model then learn from it as a show that you do not want. The Ratings tab lists the removed shows, and the detail window of a show can put it back. A franchise that you do not own appears as its first TV season. You can also seed the list from any show you click. **How the list is made** plays an animation on the map. It starts with all shows of the catalog, and each step is one part of the formula: the dots of the shows that stay are strong, and a panel gives the number of these shows and a short text. The animation plays one time by itself, with your first list in a browser.
- **Match** — each show has a match in percent. It tells how near the show is to you. Its score has two parts: the content score (your nearest liked shows and the taste model), and the tier that a small model predicts for the show. The predicted tier has one quarter of the weight of the content score. The match is the part of the franchises that you do not have, which have a lower score. A match of 99 means: the show is nearer to you than 99% of these franchises. The match does not use the crowd links or the formula of a list, thus a list of recommendations is not always in the order of the match. For a show of yours, the match is the value that the show would have if you did not have its franchise. For a show with an answer of the Discover deck, it is the value without this answer. The predicted tier has a small weight because it does not predict your interest in a new show. In a test with 113 answers of the Discover deck, the match put an interested show above a not-interested show in 83% of the pairs, and in 74% with the same weight for the two parts. The match is a weak prediction of the tier of one show: with each of your rated franchises hidden in turn, the median match was 98.8 for the S tier, 96.3 for A, 97.3 for B and 98.6 for C. A show without a tier also has a tier guess: the tier that a small model (a ridge regression on the tags of your rated shows) predicts. The guess is weak: in a test with each franchise hidden from the model, 64% of the shows with the highest guesses were S or A, and 36% of the shows with the lowest guesses. The Review tab has your shows without a tier first, in an order that uses the match and the tier guess together: this is also the order in which to watch them. A list with a seed also has the similarity of each show to the seed.
- **Map** — a 2D t-SNE layout of the index. Shows that are neighbors in the embedding space are neighbors on the map. In the far view each show is a dot. When you zoom in, each show moves to its own cell of a grid and becomes a poster, so that no poster covers another poster and you can see which shows are near a show. At the largest zoom a poster has its title. A show of yours has a frame in the color of its tier and a badge with the tier letter. A recommendation has a ✦ badge. Labels name the areas of the map by their typical tags. The far view has the labels of the large areas. The smaller areas get their labels when you zoom in. Each map has a search box: type a part of a title, in romaji, in English or in Japanese. The map shows the found shows with a frame and makes the other shows faint. Enter moves the view to the next found show, and Shift+Enter to the one before. The button "Match gradient" makes the brightness of a poster show its match: a show with a high match is bright, and a show with a low match is dark. In the far view the dots of the catalog are stronger for a higher match. The pointer on a show then also gives its match.
- **Settings** — choices for the look of the interface. The browser keeps them. The typeface setting has two options: serif titles (Noto Serif JP for titles and headings), and Noto Sans JP for all text. A second setting turns the cherry blossom petals of the page header on or off. A third setting turns the match gradient of the maps on or off. A setting has no text: the "i" mark of a setting, and the pointer on its options, show a tooltip with a picture of each option.

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
python serve.py --also 0.0.0.0:8771   # the same server also accepts connections from other computers, on port 8771
python evaluate.py --tiers     # offline test of the recommendations (read-only)
python scripts/benchmark.py after   # write the results of the offline tests to scratch/bench-after.json (read-only)
```

Use one server process. The server keeps your tiers and your answers in memory, and it reads the database only when it starts. Two processes thus do not agree after you change a tier through one of them. `--also` gives one process more than one address. `--no-browser` starts the server without the browser.

Rebuilds are incremental: unchanged rows keep their cached embeddings. A change of the model or of the prompt in `anime_vec/embed.py` makes all embeddings stale. The build also computes the map layout (about 1 minute) and keeps it in the database until the embeddings change.

### Automatic rebuild (Windows)

A new anime has few links on AniList at first, and it gets more with time. A build each week keeps the catalog and the links fresh. The folder `scripts/` has three PowerShell scripts for this:

```
powershell -ExecutionPolicy Bypass -File scripts\install_weekly_task.ps1    # create the scheduled task (Monday 04:30)
powershell -ExecutionPolicy Bypass -File scripts\weekly_rebuild.ps1         # what the task runs: build, then start the server again
powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1        # only start the server again
```

- The task runs as your user, also when you are not logged on. If the computer is off at the time of the task, the task runs when the computer is on again.
- `install_weekly_task.ps1 -Day Sunday -Time 03:00` selects a different time. `Unregister-ScheduledTask -TaskName "rinrikun weekly rebuild"` removes the task.
- The build keeps one copy of the database from before the build in `scratch\anime_vec.db.bak-weekly`. Its log is `scratch\rebuild.log`.
- If the build fails, the server continues with the old index.
- `restart_servers.ps1` starts one server process that listens on two addresses: `127.0.0.1:8765` and `0.0.0.0:8771`. Its parameter `-Addresses` selects other addresses. The log of the server is `serve.log`.
- When the build adds shows, it computes the map again. The positions of the shows on the map can then be different.

## Notes

- The build connects each library show to its AniList entries with the public id map of the Fribb/anime-lists project (TMDB, TVDB and IMDb ids, with season numbers). The file stays in `idmap_cache/` for 7 days. A title match finds the shows that the id map does not have.
- The catalog is all anime that the build can find: the 5000 most popular anime on AniList (the maximum for one query), all anime of the public id map, and the anime that these point to with a user recommendation or a franchise relation. That is about 21 000 anime. A show that is not released and a music video are in the catalog but not in the recommendations. The first build asks AniList for about 450 pages, which takes about 20 minutes. Later builds use the cache. The cache of a page is good for 30 days, and the cache of an anime that is not finished for 7 days.
- Two Jellyfin items with the same type and the same TMDB id are one show (for example two files of one movie). A show that Jellyfin does not have now goes out of the index at the next build. Its tier stays in the database.
- AniList pages are cached in `anilist_cache/` (corrupt files are refetched automatically; requires a browser User-Agent, which is handled for you).
- Index + cache + secrets are gitignored. The default host is 127.0.0.1 and the API has no auth. With `--host 0.0.0.0` or `--also 0.0.0.0:8771`, each computer that can connect to the port can read and change the ratings, so use it only on a network that you trust (for example behind a firewall rule for your VPN).
- Scale target: ~20k titles (brute-force numpy cosine).
- All similarities use mean-centered vectors: the engine subtracts the corpus mean before it computes a cosine.
- Without scikit-learn, or with less than 100 titles, the map uses PCA.
