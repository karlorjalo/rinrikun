# Loading Times Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each tab of rinrikun load and change faster, on the server and in the browser, with a measurement before and after each change.

**Architecture:** The server work removes repeated computation: one computation of the match at a time, the next computation in the background after a change, and caches for the lists and for the large answers. The page work removes data and work that the screen does not need: smaller lists, one tooltip for the cards, the next Review card at once, fewer map draws and fewer font files.

**Tech Stack:** Rust (axum 0.8, rayon, nalgebra, serde_json, flate2), SvelteKit 3 / Svelte 5, bits-ui 2, Playwright, PowerShell scripts on the PC.

**Spec:** There is no separate spec. The section "Findings" below is the base of this plan: the measurements of 2026-11-19.

## Findings (2026-11-19)

The server numbers come from the PC (Ryzen 5 3600) and the dev copy (`127.0.0.1:8773`, a copy of the real data: 20 862 map points, 222 rated shows). The browser numbers come from the second computer through Tailscale (9 ms round trip) and the live page (`PC_ADDRESS:8771`, without the Recommendations tab). "4x" is Chrome with a CPU that is 4 times slower, near the speed of a phone.

| # | What | Now | Cause |
|---|---|---|---|
| F1 | The first request that needs the match after a change (tier, answer, removal) | 320–340 ms | `compute_match` and `tier_guess` run again (`server/src/engine.rs:874`, `:934`) |
| F2 | The Ratings data (`/ratings/__data.json`) right after a change | 899 ms (49 ms normally) | Most likely, 3 requests compute the same match at the same time: the cache has no single flight (899 ms is about 3 × 330 ms) |
| F3 | A list of recommendations | 130 ms (with variety 170 ms) for each request; `/api/recommend/steps` 130 ms | No cache. A list with a seed takes 6 ms. |
| F4 | `/api/vector-map` (the Profile map) | 7.0 MB JSON, 1.7 MB gzip, 440 ms on the server. Each load of the Profile tab downloads it again. | No cache headers. The server makes it for each request. |
| F5 | The Profile tab in the browser | 4 full map draws during the load. Long tasks: 297 ms (1x), 1.3–1.6 s (4x). | Each poster that loads draws the full map again (`web/src/lib/map/engine.js:522-525`) |
| F6 | `/api/shows` (the search box of Similar) | 6.1 MB, 1.3 MB gzip, 225 ms | The same as F4 |
| F7 | The list answers have fields that the cards do not show | `/api/ratings` is 385 KB: `overview` is 40% of it. `recommendations`, `provider_ids` and `added_at` are in each answer, and the page never reads them. | `public_row` copies all data of a row (`server/src/api.rs:65`) |
| F8 | The Ratings tab | HTML 1.29 MB. At 4x: the first load has a long task of 1 035 ms. A change to the tab takes 1 172 ms (layout 648 ms, bits-ui tooltips about 140 ms). | 222 cards, and each card has its own tooltips (`MatchText`, `GuessText`) |
| F9 | Review: give a tier | The next card waits for the answer of the server (`web/src/lib/state/review.svelte.ts:45`) | With F1, the wait can be 330 ms |
| F10 | The first page after a restart of the page server | 1.0 s (dev), 2.8 s one time on live | Node loads the code of the routes at the first request |
| F11 | Fonts on a first visit (empty cache) | Ratings: 35 font files, 1.16 MB | 4 weights of Noto Sans JP and 3 of Noto Serif JP, each in many files |

These are good now, and no task changes them: the other API answers take 1–25 ms, a page render takes 15–25 ms, the static files have `immutable` cache headers, gzip is on, and the scripts are 177 KB gzip.

## Global Constraints

- Simple English (ASD-STE100, pragmatic) for each code comment, doc comment, README text and terminal output.
- One commit for each task, after its tests pass. Write the message to a file and use `git commit -F <file>`. No `Co-Authored-By` line. Do not push.
- Rust 1.91 on the computer of the builds. Do not update the toolchain. `ort` stays at `=2.0.0-rc.13`. `flate2` 1.1.11 is already in `Cargo.lock`.
- No task changes a result of a formula: `rinrikun evaluate` gives the same output before and after each server task.
- Never load the Recommendations tab or `/api/recommend` without a seed on the live server: each such list goes into the log of the user. Measure the lists only on the dev copy (API `127.0.0.1:8773`, page server `8781`).
- Deploy each task to the dev copy first, then to live. The server exe: copy it to `scratch\`, stop the processes on the ports, move it into `server\target\release\`, then `scripts\restart_servers.ps1`. The page: `scripts\build_web.ps1 -NoInstall`, then `scripts\restart_servers.ps1 -WebOnly`.
- The PC runs PowerShell scripts only with `powershell -NoProfile -ExecutionPolicy Bypass`. Ask the user for the SSH password, and do not store it.
- Keep the look. New UI parts use the existing components (`#lib/components/ui/tooltip`) and the colors of `layout.css`. Fades only for loading, new items and open/close.
- At the end of each task these pass: `cargo test` (in `server/`), and `npm run check`, `npx vitest --run`, `npx playwright test` (in `web/`).

## Review Focus

1. A tier change while the server computes in the background: no answer after the change can use a match from before it. Test: Task 1, `memo_drops_value_of_old_generation`.
2. A full reload of the Profile tab after a tier change must show the new tier on the map: the ETag must change when a tier changes. Test: Task 5, `prepared_etag_changes_with_body`.
3. A list from the cache must still go into the log of the lists. Test: Task 4, step 4 (a row that is not in the log comes back with a list from the cache, on the dev copy).
4. A card of a smaller list must open a detail window with the overview. Test: Task 6, `the detail window of a rated show shows the overview`.
5. Fast keys in Review (a tier, then undo at once) must reach the server in the order of the keys. Test: Task 8, `rate then undo keeps the order`.

---

### Task 0: Measurement tools in the repository

The drafts are in `.work/` of the local clone (`measure.ps1`, `change.ps1`, `load_probe.mjs`, `load_trace.mjs`, `map_draws.mjs`, `ratings_trace.mjs`). This task puts them in the repository, so that each later task can measure the same way.

**Files:**
- Create: `scripts/perf/api_times.ps1`
- Create: `web/perf/load_probe.mjs`, `web/perf/load_trace.mjs`, `web/perf/map_draws.mjs`, `web/perf/tab_trace.mjs`
- Create: `web/perf/README.md`

**Interfaces:**
- Produces: `api_times.ps1 [-Base http://127.0.0.1:8773] [-Web http://127.0.0.1:8781]`. It stops with an error if the process on the port of `-Base` is not in the folder `rinrikun-dev`. Its output has these sections:
  - "API": each endpoint of the page (the list of `measure.ps1`), 3 runs. A line has the first time, the next times, the time to the first byte, the gzip size and the raw size.
  - "Pages": the pages through the Rust server, and directly on the page server.
  - "Data": the `__data.json` of each tab.
  - "After a change": a `POST /api/weights` that gives a show the tier that it has already, then each of these: `GET /api/show/{id}` at once, `GET /api/show/{id}` 1 s after the POST, `/ratings/__data.json` at once, `/review/__data.json` at once, `/api/recommend` (the default list) 1 s after the POST.
- Produces: `node web/perf/load_probe.mjs <address> [slowdown] [tabs]`, `node web/perf/load_trace.mjs <address> <path> [slowdown]`, `node web/perf/map_draws.mjs <address> <path> [slowdown]` and `node web/perf/tab_trace.mjs <address> <tab> [slowdown]` (from `ratings_trace.mjs`, with the tab as a parameter). Each imports Playwright from `../node_modules/playwright/index.mjs`. Run them from PowerShell: Git Bash changes the path `/` into a Windows path.

- [ ] **Step 1:** Make the six files from the drafts. Each file starts with a comment: what it measures, how to run it, and "never the Recommendations tab against the live server" where it applies. `web/perf/README.md` lists the tools and the dev tunnel: `ssh -N -L 8790:127.0.0.1:8773 USER@PC_ADDRESS`.
- [ ] **Step 2:** Run `api_times.ps1` on the PC and save the output as `scratch\perf-baseline.txt` on the PC. Run `load_probe.mjs http://PC_ADDRESS:8771 1` and `... 4 Profile,Discover,Ratings,Review,Settings` and keep the output with the baseline. Expected: the numbers of "Findings", within about 20%.
- [ ] **Step 3:** `npm run check` and `npx eslint perf` in `web/` pass (add `perf/` to the lint scope if it is not in it).
- [ ] **Step 4:** Commit: `chore(perf): tools that measure the load times`.

### Task 1: One computation of the match at a time

**Files:**
- Create: `server/src/memo.rs`
- Modify: `server/src/main.rs` (add `mod memo;`)
- Modify: `server/src/engine.rs:103-107` (`Cache`), `:157` (the field), `:295`, `:336-338` (`clear_cache`), `:874-881` (`match_percent`), `:934-956` (`tier_guess`)

**Interfaces:**
- Produces (`memo.rs`):
  ```rust
  /// A value that is computed one time. Callers at the same time wait for the same computation.
  #[derive(Default)]
  pub struct Memo<T> { /* Mutex<Arc<OnceLock<T>>> */ }
  impl<T: Clone> Memo<T> {
      pub fn get_or_compute(&self, compute: impl FnOnce() -> T) -> T;
      pub fn get(&self) -> Option<T>;
      pub fn clear(&self);
  }
  /// One Memo for each key
  #[derive(Default)]
  pub struct MemoMap<K, V> { /* Mutex<HashMap<K, Arc<OnceLock<V>>>> */ }
  impl<K: Eq + Hash + Clone, V: Clone> MemoMap<K, V> {
      pub fn get_or_compute(&self, key: &K, compute: impl FnOnce() -> V) -> V;
      pub fn clear(&self);
  }
  ```
  Approach: `get_or_compute` clones the `Arc` while it holds the mutex, then it calls `OnceLock::get_or_init` after it releases the mutex. `clear` puts a new `Arc` in place. A computation that started before `clear` fills the old cell, and no caller reads that cell again.
- Produces: `Engine::match_percent` and `Engine::tier_guess` keep their signatures. `Cache` has `matches: Memo<Vec<f32>>` and `guesses: Memo<Vec<f32>>`, and the field `cache` is a `Cache`, not a `Mutex<Cache>`. The body of `tier_guess` moves to `fn compute_guess(&self) -> Vec<f32>`.
- Rule: do not call `get_or_compute` inside a rayon closure. A rayon thread that waits can block the work that it waits for. Write this rule in the doc comment of `Memo`.

- [ ] **Step 1: Write the failing tests** in `memo.rs`:
  - `memo_computes_once_for_parallel_callers`: 4 threads call `get_or_compute` with a closure that sleeps 50 ms, adds 1 to an `AtomicUsize` and returns 7. Assert: the counter is 1, and each thread got 7.
  - `memo_computes_again_after_clear`: get (counter 1), `clear`, get (counter 2).
  - `memo_drops_value_of_old_generation`: thread A calls `get_or_compute(|| { sleep 100 ms; 1 })`. After 20 ms the main thread calls `clear`, then `get_or_compute(|| 2)` and gets 2. After thread A ends, `get()` is `Some(2)`.
  - `memo_map_keeps_one_value_per_key`: keys 1 and 2 give their own values. `clear` removes both.
- [ ] **Step 2:** `cargo test memo` fails: the module does not exist.
- [ ] **Step 3:** Write `memo.rs`, and change `engine.rs` to use it.
- [ ] **Step 4:** `cargo test` passes. `cargo build --release`.
- [ ] **Step 5:** On the PC, copy the new exe to `C:\Users\USER\rinrikun-dev\scratch\rinrikun-new.exe`. Run `rinrikun evaluate --db anime_vec.db` in the dev folder with the old exe and with the new exe, each to a file. `fc` shows no difference.
- [ ] **Step 6:** Deploy the server to the dev copy. Run `api_times.ps1`. Expected: in "After a change", `/ratings/__data.json` at once takes 450 ms or less (it was 899 ms).
- [ ] **Step 7:** Commit: `perf(server): one computation of the match at a time`.

### Task 2: Compute the match in the background after a change

**Files:**
- Modify: `server/src/server.rs` (`App` at `:38-54`, `change` at `:127-141`, `run` at `:548`)

**Interfaces:**
- Consumes: `Engine::match_percent`, `Engine::tier_guess` (Task 1).
- Produces:
  - `App.changes: AtomicU64`: the number of changes of this server.
  - `const WARM_QUIET: Duration = Duration::from_millis(400);`
  - `fn warm_later(app: &Shared)`: it reads `changes`, then a tokio task waits `WARM_QUIET`. If `changes` is the same then, the task computes the match and the tier guess with `compute` (on a blocking thread, with the read lock of the engine). If a new change came, it does nothing: the next change starts its own wait.
  - `change()` adds 1 to `changes` and calls `warm_later` after each change, also after a change that failed.

The list log (`recommend()` calls `change` with `log_list`) also calls `warm_later`. The match is still in the cache then, thus that warm-up ends at once.

- [ ] **Step 1:** Write the code.
- [ ] **Step 2:** `cargo test` passes. `cargo build --release`. Deploy to the dev copy.
- [ ] **Step 3:** Run `api_times.ps1`. Expected in "After a change": `GET /api/show/{id}` 1 s after the POST takes 15 ms or less (it was 330 ms). The POST takes 30 ms or less.
- [ ] **Step 4:** Commit: `perf(server): compute the match in the background after a change`.

### Task 3: The time of each stage of the engine, and the Gram matrix without copies

**Files:**
- Create: `server/src/timing.rs`
- Modify: `server/src/main.rs` (the command `timing`, the usage text and the doc comment at the top)
- Modify: `server/src/engine.rs:724-734` (the Gram matrix in `predicted_tier`)
- Modify: `server/README.md` (one paragraph for the command)

**Interfaces:**
- Produces: `pub fn run(args: &[String]) -> Result<()>` in `timing.rs`, for `rinrikun timing <database>`. It reads only. It loads the engine, and it prints one line for each stage: `load`, `match`, `tier guess`, `candidates`, `content (candidates)`, `predicted tier (candidates)`, `list`, `list with variety`, `steps`, `vector map JSON`, `titles JSON`. Each value is the best of 3 runs, in ms. It calls `clear_cache` before each run of `match` and `tier guess`. Make `owned_franchises` or another function `pub(crate)` only if the command needs it.

- [ ] **Step 1:** Write `timing.rs` and the command. `cargo build --release`.
- [ ] **Step 2:** Run `rinrikun timing anime_vec.db` in the dev folder on the PC (use the exe in `scratch\`). Save the output as `scratch\timing-before.txt`.
- [ ] **Step 3:** In `predicted_tier`, make `dense64: Vec<Vec<f64>>` (one `f64` copy of each learned row) one time before the double loop. The loop uses `&dense64[b]`, and it makes no new vector for each pair. The values are the same, thus the result is the same bit for bit.
- [ ] **Step 4:** `cargo test` passes. Run `timing` again. Expected: `predicted tier (candidates)` and `match` are lower than before. `rinrikun evaluate` gives the same output as the file of Task 1.
- [ ] **Step 5:** If a different stage that no later task changes takes more than 100 ms, add one line for it to "Not in this plan" below. Do not change a formula in this task.
- [ ] **Step 6:** Commit: `perf(server): a timing command, and the Gram matrix without copies`.

### Task 4: Cache the lists of recommendations and the steps

**Files:**
- Modify: `server/src/engine.rs` (`Cache` gets `lists` and `steps`, and `clear_cache` clears them)
- Modify: `server/src/api.rs:233-263` (`api_recommend`, `api_steps`)
- Modify: `server/src/server.rs` (`App.last_list`, `recommend` at `:240-263`, `warm_later`)

**Interfaces:**
- Consumes: `MemoMap` (Task 1), `warm_later` (Task 2).
- Produces:
  ```rust
  #[derive(Clone, Copy, PartialEq, Eq, Hash)]
  pub struct ListKey { pub k: usize, pub diverse: bool, pub new_only: bool, pub usual: bool, pub links: bool }
  #[derive(Clone, Copy, PartialEq, Eq, Hash)]
  pub struct StepsKey { pub k: usize, pub usual: bool, pub links: bool, pub new_only: bool }
  // In Cache:
  lists: MemoMap<ListKey, Result<Value, String>>,
  steps: MemoMap<StepsKey, Value>,
  ```
  - `api_recommend` gets a list without a seed from `cache.lists`. A list with a seed is not in the cache (it takes 6 ms).
  - `App.last_list: Mutex<Option<ListKey>>`. `recommend()` keeps the key of each list without a seed. `warm_later` then also computes `api_recommend` for that key, after the match.
  - `recommend()` keeps its call of `change(... log_list ...)` after it gets the list, thus a list from the cache also goes into the log.

- [ ] **Step 1:** Write the code. `cargo test` passes. `cargo build --release`. `rinrikun evaluate` gives the same output as the file of Task 1 (the test does not use the API, but it uses the same engine).
- [ ] **Step 2:** Deploy to the dev copy.
- [ ] **Step 3:** Run `api_times.ps1`. Expected: the second and third `/api/recommend` (hybrid and variety) and `/api/recommend/steps` take 15 ms or less (they were 130–170 ms). In "After a change", `/api/recommend` 1 s after the POST takes 15 ms or less.
- [ ] **Step 4:** The log. The log has one row for each show and day, thus a second list on the same day changes no row. On the dev copy only: request the default list one time (now it is in the cache). Delete the row of its first show from `rec_log` (Python with `sqlite3` on `C:\Users\USER\rinrikun-dev\anime_vec.db`). Request the same list again within 1 s. Expected: the request takes 15 ms or less (the cache), and the row is in `rec_log` again.
- [ ] **Step 5:** Commit: `perf(server): cache the lists of recommendations`.

### Task 5: The large answers one time for each version of the data, with an ETag

**Files:**
- Create: `server/src/prepared.rs`
- Modify: `server/Cargo.toml` (`flate2 = "1.1.11"`), `server/src/main.rs` (`mod prepared;`)
- Modify: `server/src/engine.rs` (`Cache` gets `vector_map` and `titles`)
- Modify: `server/src/server.rs:426` and `:442` (the routes `/api/vector-map` and `/api/shows`)

**Interfaces:**
- Consumes: `Memo` (Task 1).
- Produces:
  ```rust
  /// A large answer that stays the same until the data changes: the JSON, its gzip bytes and its ETag
  pub struct Prepared { pub json: Vec<u8>, pub gzip: Vec<u8>, pub etag: String }
  impl Prepared { pub fn new(value: &Value) -> Prepared }   // etag: "\"" + sha1 hex of json + "\""
  pub fn answer(prepared: &Prepared, request: &HeaderMap) -> Response
  // In Cache:
  vector_map: Memo<Arc<Prepared>>,
  titles: Memo<Arc<Prepared>>,
  ```
  - `answer`: if `If-None-Match` is the ETag, the answer is 304 with the ETag and no body. Else, if `Accept-Encoding` has `gzip`, the body is `gzip` with `Content-Encoding: gzip`. Else the body is `json`. Each answer has `Content-Type: application/json`, `ETag`, `Cache-Control: no-cache` and `Vary: Accept-Encoding`.
  - The `CompressionLayer` must not compress the gzip body again: it leaves an answer that has `Content-Encoding`. Check this with curl in step 5.
  - A change of the data clears both (they are in `Cache`). The ETag is a hash of the body: an answer of the Discover deck changes no point of the map, thus the browser gets 304 after it.

- [ ] **Step 1: Write the failing tests** in `prepared.rs`:
  - `prepared_etag_changes_with_body`: two values that differ only in the tier of one point have different ETags. The same value gives the same ETag.
  - `answer_gives_304_for_same_etag`: status 304, the ETag header, and an empty body.
  - `answer_gives_gzip_when_accepted`: `Content-Encoding: gzip`, and the body unpacks (with `flate2::read::GzDecoder`) to the JSON.
  - `answer_gives_json_without_gzip`: no `Content-Encoding`, and the body is the JSON.
- [ ] **Step 2:** `cargo test prepared` fails.
- [ ] **Step 3:** Write `prepared.rs` and the two routes.
- [ ] **Step 4:** `cargo test` passes. Deploy to the dev copy.
- [ ] **Step 5:** On the PC: `curl.exe -s -D - -o NUL -H "Accept-Encoding: gzip" http://127.0.0.1:8773/api/vector-map` shows one `content-encoding: gzip` and an `etag`. The same request with `-H "If-None-Match: <etag>"` gives 304 in 5 ms or less. A second request without it takes 20 ms or less (it was 440 ms).
- [ ] **Step 6:** Through the dev tunnel (port 8790): `load_probe.mjs http://127.0.0.1:8790 1 Profile`. Expected: the second load of Profile ("warm") moves 150 KB or less (it was 1 670 KB).
- [ ] **Step 7:** Commit: `perf(server): the map and the titles one time for each data version, with an ETag`.

### Task 6: Smaller list answers

**Files:**
- Modify: `server/src/api.rs` (`public_row` at `:65`, `result` at `:85`, `listed` at `:120`, `api_ratings`, `api_watched`, `api_dismissed`, `api_watch_list`, `api_similar`, `api_recommend`)
- Modify: `web/src/lib/api/types.ts` (`Show`)
- Modify: `web/tests/mock/server.mjs` (`open` at `:196`, and the routes at `:368-372`, `:410`, `:426-430`)
- Test: `web/tests/ratings.e2e.ts`

**Interfaces:**
- Produces (Rust):
  - `const UNUSED_FIELDS: [&str; 3] = ["recommendations", "provider_ids", "added_at"];` `public_row` removes them from each answer: the page never reads them.
  - `const CARD_LEFT_OUT: [&str; 3] = ["overview", "studios", "tag_ranks"];`
  - `fn card(&self, j: usize, similarity: Option<f32>, seed: Option<usize>) -> Map<String, Value>`: `result` without `CARD_LEFT_OUT`. `fn listed_cards(&self, rows: impl IntoIterator<Item = usize>) -> Vec<Value>`: `listed` with `card`.
  - The card shape is in `/api/ratings`, `/api/watched`, `/api/dismissed`, `/api/interest`, `/api/similar` and `/api/recommend`. The full shape stays in `/api/show`, `/api/discover` and `/api/review-queue`: `DeckCard` shows the overview, the studios and the tags.
- Produces (TypeScript): in `Show`, `overview?: string`, `studios?: string[]`, `tag_ranks?: number[]`. The detail window gets the full show when `overview` is `undefined` (`web/src/lib/state/detail.svelte.ts:12`).
- Produces (mock): `card(row, more = {})`: `open(row, more)` without `overview`, `studios` and `tag_ranks`. The same routes as in the real server use it.

- [ ] **Step 1: Write the guard test** in `ratings.e2e.ts`: `the detail window of a rated show shows the overview`. Open `/ratings`, click the title of the first card, and expect the dialog to contain `An invented show for the tests`. Then change the mock (`card` for the list routes). The test now passes only if the window gets the full show with `/api/show`.
- [ ] **Step 2:** `npx playwright test ratings` passes with the changed mock. (If it fails, fix the page code that opens the window, not the test.)
- [ ] **Step 3:** Change `api.rs` and `types.ts`. `npm run check` passes.
- [ ] **Step 4:** `cargo test` passes. Deploy the server to the dev copy. On the PC: `/api/ratings` has 220 KB or less (it was 385 KB) and no key `overview`. `/api/show/{id}` still has `overview`. `/ratings` (the page) is smaller than 1.29 MB.
- [ ] **Step 5:** All e2e tests pass.
- [ ] **Step 6:** Commit: `perf: smaller list answers`.

### Task 7: Warm the page server after a restart

**Files:**
- Modify: `scripts/restart_servers.ps1:69-78`

**Interfaces:**
- Produces: `function Request-Pages([int]$WebPort, [string]$Api)`. It waits until `$Api/api/profile` answers (at most 60 s, every 0.5 s), then until `http://127.0.0.1:$WebPort/settings` answers (at most 30 s). Then it requests each of `/`, `/discover`, `/ratings`, `/review`, `/similar`, `/settings` one time on the page server. It never requests `/recommendations`: that page writes a list into the log. It prints `page server warm in N ms`. The script calls it after it starts the page server.

- [ ] **Step 1:** Write the function and the call. Check the script with the PowerShell parser (`[System.Management.Automation.Language.Parser]::ParseFile`): no errors.
- [ ] **Step 2:** On the PC: `restart_servers.ps1` for the dev copy with `-WebOnly` (the arguments of the deploy notes). Then the first `curl.exe` to `http://127.0.0.1:8773/` takes 100 ms or less (it was 1 024 ms).
- [ ] **Step 3:** Commit: `perf(scripts): warm the page server after a restart`.

### Task 8: Review shows the next card at once

**Files:**
- Modify: `web/src/lib/state/review.svelte.ts:36-65` (`rate`, `undoLast`)
- Test: `web/tests/review.e2e.ts`

**Interfaces:**
- Produces: `private saving: Promise<void> = Promise.resolve()`: the tier requests, in their order. `rate(tier)` changes the state at once (the undo entry, the tier of the show, the count, `index += 1`), then adds `library.setTier(show, tier)` to the end of `saving`. `undoLast()` does the same with its own change. An error goes to `console.error`, as now.

- [ ] **Step 1: Write the failing tests** in `review.e2e.ts`. They use `POST /api/__delay` of the mock.
  - `the next card comes before the answer of the server`: set the delay to 800 ms. Read the title of the card, press `b`. Expect a different title within 300 ms.
  - `rate then undo keeps the order`: set the delay to 400 ms. Read the id of the card, press `a`, then `Backspace` at once. After 1.5 s, `GET /api/show/{id}` (with `page.request`) gives the tier that the show had before (null for an unrated show). `GET /api/__requests` has the POST before the DELETE.
- [ ] **Step 2:** `npx playwright test review` fails (the first test).
- [ ] **Step 3:** Change `review.svelte.ts`.
- [ ] **Step 4:** All e2e tests pass.
- [ ] **Step 5:** Commit: `perf(web): Review shows the next card at once`.

### Task 9: One tooltip for the match and the guess of all cards

**Files:**
- Create: `web/src/lib/components/HintLayer.svelte`
- Modify: `web/src/lib/components/show/MatchText.svelte`, `web/src/lib/components/show/GuessText.svelte`
- Modify: `web/src/routes/+layout.svelte` (mount `HintLayer` one time)
- Test: `web/tests/ratings.e2e.ts`

**Interfaces:**
- Produces: a trigger is an element with `data-hint="<text>"`. `MatchText` and `GuessText` render their button with `data-hint` and without `Hint`. `HintLayer` has one `Tooltip.Root` with `Tooltip.Content` (`#lib/components/ui/tooltip`). Its `customAnchor` is the element of the trigger: bits-ui 2 has this property (`node_modules/bits-ui/dist/bits/tooltip/components/tooltip-content.svelte`). Its listeners are on `document`:
  - `pointerover` on a trigger opens the tooltip after the delay of the other tooltips (read it from `Tooltip.Provider` in the code). `pointerout` closes it.
  - `focusin` on a trigger opens it at once. `focusout` and `Escape` close it.
  - On a touch screen, a tap opens it, and a later tap closes it (the rule of `Hint.svelte`: a tap that comes 500 ms or less after the open does not close it).
  - While it is open, the trigger has `aria-describedby` set to the id of the content.
- `Hint.svelte` stays for `InfoDot`, the Settings page and the Recommendations page (few elements, some with rich content).

- [ ] **Step 1: Write the failing tests** in `ratings.e2e.ts`:
  - `the match of a card shows its tooltip`: hover the first `[data-testid=match]`. Expect one `getByRole('tooltip')` that is visible, with the text of `matchAbout` for that show. The trigger has `aria-describedby` with the id of the tooltip.
  - `the keyboard focus on a match shows its tooltip, and Escape closes it`.
- [ ] **Step 2:** The tests fail (no `aria-describedby` from one shared tooltip yet, or no tooltip on focus).
- [ ] **Step 3:** Write `HintLayer.svelte` and change the two components.
- [ ] **Step 4:** All e2e tests pass, also `The window opens without an open tooltip above its buttons`.
- [ ] **Step 5:** Deploy the page to the dev copy. Through the tunnel: `tab_trace.mjs http://127.0.0.1:8790 Ratings 4`. Expected: the time in the chunk of bits-ui is 30 ms or less (it was about 140 ms). Write the new tab change time in the commit message.
- [ ] **Step 6:** Commit: `perf(web): one tooltip for the match and the guess of the cards`.

### Task 10: Fewer map draws while the posters load

**Files:**
- Modify: `web/src/lib/map/engine.js` (`scheduleDraw` at `:267`, `posterImage` at `:518-526`)

**Interfaces:**
- Produces: `const POSTER_DRAW_DELAY = 150;` and `function schedulePosterDraw()`. A poster that loads asks for one draw 150 ms later. The posters that load in that time use the same draw. `posterImage` gives `schedulePosterDraw` to `getPosterImage`. A draw for zoom, pan or resize stays `scheduleDraw` (the next frame). The check `destroyed` applies to both.

- [ ] **Step 1:** Write the change.
- [ ] **Step 2:** All e2e tests pass (`profile.e2e.ts` checks the map tooltip).
- [ ] **Step 3:** Deploy the page to the dev copy. Through the tunnel: `map_draws.mjs http://127.0.0.1:8790 / 1`. Expected: 2 large draws or fewer (it was 4). Write the long task total of `load_probe.mjs ... 4 Profile` in the commit message.
- [ ] **Step 4:** Commit: `perf(web): one map draw for the posters that load together`.

### Task 11: Fewer font files

**Files:**
- Modify: `web/src/app.html:12-15`

**Interfaces:**
- Produces: the font address `https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@500..700&family=Noto+Sans+JP:wght@400..700&display=swap`. Google then gives one variable font file for each part of the characters, for all weights. The second link (weight 200, three kana) stays.

- [ ] **Step 1:** Take screenshots of Ratings and Profile (light and dark) before the change.
- [ ] **Step 2:** Change the address. Build, and deploy the page to the dev copy.
- [ ] **Step 3:** Through the tunnel: `load_probe.mjs http://127.0.0.1:8790 1 Ratings,Profile`. Compare the font requests and KB of the cold load with the old numbers (Ratings: 35 requests, 1 158 KB). Keep the change only if both numbers are lower. Else restore the file, and give the numbers in the final report.
- [ ] **Step 4:** Take the same screenshots. The weights must look the same.
- [ ] **Step 5:** Commit: `perf(web): variable font files`.

### Task 12 (needs a decision of the user): long lists render on scroll

After Tasks 6 and 9, the Ratings tab still makes all 222 cards in parts, and the layout of each part costs time (648 ms in all at 4x). This task makes the first 24 cards, and 24 more each time that the end of the list comes within one screen of the window. The server render has the first 48 cards.

The effects that the user sees: the search of the browser (Ctrl+F) finds only the cards that are on the page, and without JavaScript the page has 48 cards. Do this task only if the user accepts these effects.

**Files:**
- Modify: `web/src/lib/state/progressive.svelte.ts`, `web/src/routes/ratings/+page.svelte`, `web/src/routes/ratings/+page.server.ts` (no change of the data, only of the render)
- Test: `web/tests/ratings.e2e.ts:5-13`, `web/tests/ssr.e2e.ts:12-14`

**Interfaces:**
- Produces: `export function onScroll(length: () => number, serverFirst = 48): { readonly limit: number; more: Action<HTMLElement> }`. `more` goes on an empty element after the list. An `IntersectionObserver` with `rootMargin: '100% 0px'` adds 24 to `limit` when the element comes near.

- [ ] **Step 1: Change the tests first:** `ratings.e2e.ts` scrolls to the end until the count is the total. `ssr.e2e.ts` expects `Math.min(total, 48)` cards on `/ratings`. New test: `the Ratings list adds cards when the end comes near` (24 cards after a change of the tab, more after a scroll).
- [ ] **Step 2:** The new test fails.
- [ ] **Step 3:** Write `onScroll`, and use it in the Ratings page.
- [ ] **Step 4:** All tests pass. Through the tunnel: `load_probe.mjs http://127.0.0.1:8790 4 Ratings`. Expected: the tab change takes 400 ms or less (it was 1 172 ms).
- [ ] **Step 5:** Commit: `perf(web): the Ratings list renders on scroll`.

### Task 13: Measure again and report

- [ ] **Step 1:** Run `api_times.ps1` on the dev copy, and `load_probe.mjs` at 1x and 4x on the live page (without Recommendations), after the deploy of all tasks to live.
- [ ] **Step 2:** Give the user a table: each row of "Findings" with the old and the new number. No commit.

## Not in this plan

- `content` (the nearest liked shows of each candidate, for the text and for the tags) takes 110 ms for the candidates, and most of the 276 ms of the match (measured with `rinrikun timing` in Task 3). A faster method, for example a matrix product in blocks, could make it some times faster. It must not change a formula: `rinrikun evaluate` must give the same output. After Tasks 2 and 4, this time comes only at the first request right after a change.
- The load of the engine takes about 0.95 s. It comes only when the server starts and after the weekly build.

- Split the map data into a fixed part (positions, titles, posters) and a part of the user (tier, owned). Do it only if Task 5 is not enough: after a tier change, the ETag changes and the browser downloads the full map one time.
- A cached picture of the catalog points of the map, so that a draw paints only the parts that change. Do it only if Task 10 is not enough.
- Brotli, or the static files directly from the Rust server: a small effect at a round trip of 9 ms.
- One script file for the whole page (`bundleStrategy: 'single'`): the 46 files load in parallel, and the browser keeps them for a year.
