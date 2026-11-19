# rinrikun server (Rust)

The Rust version of the server. It reads the same database as the Python server and computes the
same results. In this phase the Python server stays the live server, and the Rust server only reads.

## Build

```sh
cargo build --release
```

The program is `target/release/rinrikun.exe`. The PC of the live server has no Rust: build here,
and copy the program.

## Run

```sh
rinrikun serve <database> [--listen 127.0.0.1:8775]... [--root <project folder>] [--web <page server>]
```

The server gives the GET routes of `serve.py`, the old page at `/` and the new page at `/next`.
The project folder has `ui/` and `anilist_cache/`; by default it is the folder of the database.
`--listen` can be given more than one time. The Node server of the new page renders `/next`: this
server passes the requests on to it, as the Python server does. Its address is `--web`, or the
environment variable `RINRIKUN_WEB`, or `http://127.0.0.1:8780`.

In this phase the server only reads:

- A request that changes data gets the answer 405. Make the change through the Python server.
- When the Python server changes the database, this server loads the data again (in about 1 second).
- The pictures of the Discover deck come from the files that the Python server keeps in
  `anilist_cache/frames`. This server does not ask AniList.
- The poster of a library show without an AniList entry gets 404: the Python server passes these
  posters on from Jellyfin.
- A list of recommendations is not written to the log of the lists.

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

The two engines add numbers in a different order. Thus a value can differ in its last digits, and a
show near a limit can move by one place. The scripts tell the differences and fail if one is
larger than its tolerance.

The results from the real database have personal data: keep them out of the repository.

## Tests

`cargo test` runs the tests of the small number functions and of the picture rules.
