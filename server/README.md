# rinrikun server (Rust)

The Rust version of the server. It reads the same database as the Python server and computes the
same results. In this phase the Python server stays the live server, and the Rust server only reads.

## Build

```sh
cargo build --release
```

The program is `target/release/rinrikun.exe`. The PC of the live server has no Rust: build here,
and copy the program.

## Compare with the Python engine

Each part of the engine has the rules of the function with the same name in `anime_vec/engine.py`.
The scripts in `compare/` check that the two engines give the same results:

```sh
python compare/make_db.py test.db                                  # a database with invented shows
python compare/python_reference.py test.db py.json --write-layout  # the results of the Python engine
target/release/rinrikun reference test.db rs.json                  # the results of the Rust engine
python compare/compare.py py.json rs.json
```

The two engines add numbers in a different order. Thus a value can differ in its last digits, and a
show near a limit can move by one place. `compare.py` tells the differences and fails if one is
larger than its tolerance.

The results from the real database have personal data: keep them out of the repository.

## Tests

`cargo test` runs the tests of the small number functions.
