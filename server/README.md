# rinrikun server

The program `rinrikun` in Rust: the server of the app (the API, and the address of the page), the
weekly rebuild of the catalog, and the offline test of the recommendations.

## Build

```sh
cargo build --release
```

The program is `target/release/rinrikun.exe`. The PC of the server has no Rust: build on a
different computer, and copy the program to `server\target\release\rinrikun.exe` on the PC (the
scripts look for it there). The build of the program downloads ONNX Runtime one time (the crate
`ort` 2.0.0-rc.13: the newer versions need Rust 1.92) and links it into the program.

## The server

```sh
rinrikun serve <database> [--listen 127.0.0.1:8775]... [--root <project folder>] [--web <page server>] [--read-only]
```

The server answers the API (`/api/...`, `src/api.rs` and `src/server.rs`) and passes each other GET
request on to the page server (`web/`, `node web/build`), thus the browser sees one address. The
address of the page server is `--web`, or the environment variable `RINRIKUN_WEB`, or
`http://127.0.0.1:8780`. An address below `/next` (the address of the page while it was new) gets
a permanent redirect to the same address without `/next`. `--listen` can be given more than one
time. The project folder has `anilist_cache/`; by default it is the folder of the database.

The server changes the data of the user (`src/changes.rs`):

- `POST /api/weights` and `DELETE /api/weights`: the tier of a show and of its counterparts.
- `POST /api/watched`: a show marked as watched by hand.
- `POST /api/dismissed`: a show removed from the recommendations.
- `POST /api/interest`: an answer of the Discover deck or of a page. The database keeps the match
  that the deck showed for the card.
- A list of recommendations without a seed goes into the log of the lists.

One change runs at a time, and no request reads the data during a change. Let only one server
change a database. With `--read-only` the server only reads: a change gets the answer 405, and a
list does not go into the log (for a test on a copy of the database).

More:

- When a different program (the build) changes the database, the server loads the data again (in
  about 1 second). Its own changes do not start a load.
- The pictures of the Discover deck (`/api/frames`): the server asks AniList for a show without a
  good file, and it keeps the answer in `anilist_cache/frames`. A file with frames is good for 30
  days; a file without frames, or of a show that is not finished, for 7 days.
- The poster of a library show without an AniList entry (`/api/poster/{id}`): the server passes it
  on from Jellyfin, as a small picture.

## The weekly rebuild

```sh
rinrikun build [--root <project folder>] [--db <file>] [--refresh-anilist] [--pool-only]
```

The steps (`src/build/`):

1. The shows of the Jellyfin library (`secrets.json` in the project folder, or `JELLYFIN_API_KEY`
   and `JELLYFIN_USER_ID`).
2. The 5000 most popular anime of AniList, the anime of the id map of Fribb/anime-lists, and the
   anime that the catalog points to. The answers stay in `anilist_cache/` and `idmap_cache/`.
3. The connection of the AniList rows to the library rows: the id map, then the titles (the ratio
   of `difflib.SequenceMatcher`, with the same algorithm).
4. The rows in the database. The tiers and the other data of the user stay.
5. The embeddings of the rows whose text changed: EmbeddingGemma 2 (ONNX) on the CPU, with the
   model files from the cache of Hugging Face (or a download to `model_cache/`). One text takes
   about 0.2 seconds; a weekly build has a few texts.
6. The map: t-SNE with the steps of sklearn, the grid of the close view, and the named areas.

`--root` is the project folder (default: the folder of now); `--db` is the database (default:
`anime_vec.db` in the project folder). `scripts\weekly_rebuild.ps1` runs the command.

The signature of the map (`layout_signature` in the table `meta`) is a hash of the ids of the rows
and of the stored embedding bytes: a build without a change of the embeddings keeps the map.

`rinrikun build-check <database> [--embed N] [--tsne]` reads a database and shows the rows whose
text hash differs, the signature of the map, and with the options the cosine of N new embeddings to
the stored embeddings and the quality of the stored map and of a new map (the part of the 10 nearest
neighbours of each show that are also its neighbours on the map).

## The offline test

```sh
rinrikun evaluate [--db anime_vec.db] [--tiers] [--recent N] [--benchmark label]
```

The hidden franchise test (`src/evaluate.rs`): hide a franchise that you rated (the engine forgets
that you own and rated its shows), compute the list of new franchises, and find the place of the
hidden franchise in it. It measures if a rated S or A franchise comes back in the list. It cannot
measure interest in a show from outside the library: the answers of the Discover deck measure that
(the Profile tab). Use the two measures together for a change of a formula.

- Without an option: the S and A franchises, for the six formulas of the list.
- `--tiers`: also the mean percentile of a hidden franchise for each tier.
- `--recent N`: also hide the N S and A franchises that you added last, all at the same time.
- `--benchmark label`: the place of each show for the four formulas, the first 40 of each list,
  the data and the times, in `scratch/bench-<label>.json` next to the database. Run it before and
  after a change, and compare the two files.

The test reads only. On the real data it takes about 2 minutes.

## History

The first version of the app was in Python. Before the switch, the Rust code gave the same results
as the Python version on copies of the real data: each answer of the API (a match differs at most by
one step of the rounding), each change of the data, the tables of the build, the embeddings (cosine
1.000000), and the output of the offline test. The map of the Rust build is a different t-SNE
result of the same quality (34.7% of the 10 nearest neighbours kept; sklearn: 34.8%). The git
history has the Python code and the comparison scripts (`server/compare/`).

## Tests

`cargo test` runs the unit tests: the small number functions, the picture rules, the JSON format of
the build, the title match, the id map, the grid and the t-SNE, and the summary of the offline test.
