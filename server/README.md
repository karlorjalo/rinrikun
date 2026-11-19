# rinrikun server (Rust)

The Rust version of the server and of the build. It reads the same database as the Python server and
computes the same results. With `--write` it also changes the data of the user, as the Python server
does. `rinrikun build` is the weekly rebuild of `build.py`. The Python server stays the live server
until the switch.

## Build

```sh
cargo build --release
```

The program is `target/release/rinrikun.exe`. The PC of the live server has no Rust: build here,
and copy the program to `server\target\release\rinrikun.exe` on the PC (the scripts look for it
there). The build of the program downloads ONNX Runtime one time (the crate `ort` 2.0.0-rc.13: the
newer versions need Rust 1.92) and links it into the program.

## The weekly rebuild

```sh
rinrikun build [--root <project folder>] [--db <file>] [--refresh-anilist] [--pool-only]
```

The command has the steps of `build.py` (`src/build/`):

1. The shows of the Jellyfin library (`secrets.json` in the project folder, or `JELLYFIN_API_KEY`
   and `JELLYFIN_USER_ID`).
2. The 5000 most popular anime of AniList, the anime of the id map of Fribb/anime-lists, and the
   anime that the catalog points to. The answers stay in `anilist_cache/` and `idmap_cache/`, the
   same files as the files of the Python build.
3. The connection of the AniList rows to the library rows: the id map, then the titles (the ratio
   of `difflib.SequenceMatcher`, with the same algorithm).
4. The rows in the database. The tiers and the other data of the user stay.
5. The embeddings of the rows whose text changed: EmbeddingGemma 2 (ONNX) on the CPU, with the
   model files from the cache of Hugging Face (or a download to `model_cache/`). One text takes
   about 0.2 seconds; a weekly build has a few texts.
6. The map: t-SNE with the steps of sklearn, the grid of the close view, and the named areas.

`--root` is the project folder (default: the folder of now); `--db` is the database (default:
`anime_vec.db` in the project folder). `scripts\weekly_rebuild.ps1 -Builder rust` runs the command.

The signature of the map (`layout_signature` in the table `meta`) is a hash of the ids of the rows
and of the stored embedding bytes. The Python engine computes the same value, thus each program uses
the map of the other, and a build without a change keeps the map.

Compared with `build.py` on two copies of the dev database (21,240 shows):

- The shows table was equal in all columns and in the types of the values, also after changes
  (changed rows, deleted rows, rows without a hash, an old library row). The tables of the user
  were equal.
- The text hash of each row was equal, thus the two builds embed the same rows. The Rust
  embeddings had the cosine 1.000000 to the embeddings of Python.
- The map is a different t-SNE result, of the same quality: 34.7% of the 10 nearest neighbours of
  each show are also its neighbours on the map (sklearn: 34.8%). The areas get other names.
- The Rust build took 32 seconds with a new map (t-SNE: 21 seconds), the Python build 105 seconds.

`rinrikun build-check <database> [--embed N] [--tsne]` reads a database and shows the rows whose
text hash differs, the signature of the map, and with the options the cosine of N new embeddings to
the stored embeddings and the quality of the stored map and of a new map.

## Run

```sh
rinrikun serve <database> [--listen 127.0.0.1:8775]... [--root <project folder>] [--web <page server>] [--write]
```

The server gives the routes of `serve.py`, the old page at `/` and the new page at `/next`.
The project folder has `ui/` and `anilist_cache/`; by default it is the folder of the database.
`--listen` can be given more than one time. The Node server of the new page renders `/next`: this
server passes the requests on to it, as the Python server does. Its address is `--web`, or the
environment variable `RINRIKUN_WEB`, or `http://127.0.0.1:8780`.

### With --write

The server changes the data of the user with the rules of `anime_vec/engine.py`:

- `POST /api/weights` and `DELETE /api/weights`: the tier of a show and of its counterparts.
- `POST /api/watched`: a show marked as watched by hand.
- `POST /api/dismissed`: a show removed from the recommendations.
- `POST /api/interest`: an answer of the Discover deck or of a page. The database keeps the match
  that the deck showed for the card.
- A list of recommendations without a seed goes into the log of the lists.

One change runs at a time, and no request reads the data during a change. Let only one server change
a database: do not start the Python server and a Rust server with `--write` on the same file.

### Without --write

The server only reads:

- A request that changes data gets the answer 405.
- A list of recommendations is not written to the log of the lists.

### In the two modes

- When a different program changes the database, this server loads the data again (in about 1
  second). Its own changes do not start a load.
- The pictures of the Discover deck (`/api/frames`): the server asks AniList for a show without a
  good file, and it keeps the answer in `anilist_cache/frames`, with the rules of
  `anime_vec/frames.py`. The Python server uses the same files. A file with frames is good for 30
  days; a file without frames, or of a show that is not finished, for 7 days.
- The poster of a library show without an AniList entry (`/api/poster/{id}`): the server passes
  it on from Jellyfin, as a small picture.

## Compare with the Python engine

Each part of the engine has the rules of the function with the same name in `anime_vec/engine.py`.
The scripts in `compare/` check that the two engines give the same results:

```sh
python compare/make_db.py test.db                                  # a database with invented shows
python compare/python_reference.py test.db py.json --write-layout  # the results of the Python engine
target/release/rinrikun reference test.db rs.json                  # the results of the Rust engine
python compare/compare.py py.json rs.json
```

`compare/http_check.py` sends the same requests to a Python server and to a Rust server that read
the same database, and compares the answers. Use a test server with a copy of the database: the
Python server writes each list of recommendations without a seed into its log.

`compare/write_check.py` compares the changes. Start the Python server on one copy of a database
and the Rust server with `--write` on a second copy. The script sends the same changes to the two
servers, and compares each answer, the tables of the data of the user, and the lists after the
changes. It changes the data: never use it on the live database.

The two engines add numbers in a different order. Thus a value can differ in its last digits, and a
show near a limit can move by one place. The scripts tell the differences and fail if one is
larger than its tolerance.

The results from the real database have personal data: keep them out of the repository.

## Tests

`cargo test` runs the tests of the small number functions and of the picture rules.
