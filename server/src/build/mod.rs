//! The command `rinrikun build`: the weekly rebuild of the catalog, with the steps of build.py.
//!
//!   1. The shows of the Jellyfin library.
//!   2. The most popular anime of AniList, and the anime that the id map and the catalog point to.
//!   3. The connection of the AniList rows to the library rows (the id map, then the titles).
//!   4. The rows in the database. The tiers and the other data of the user stay.
//!   5. The embeddings of the rows whose text changed.
//!   6. The map layout and the named areas of the map.
//!
//! The files of the AniList answers and of the id map are the same files as the files of the
//! Python build: anilist_cache and idmap_cache in the project folder.

mod embed;
mod idmap;
mod jellyfin;
mod layout;
mod matching;
mod pool;
mod pyjson;
mod tsne;

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::Instant;

use anyhow::{Context, Result, bail};
use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, params};
use serde_json::Value;

use crate::engine::Engine;
use crate::store::Store;
use pyjson::{Ordered, dumps, dumps_ordered};

/// One row of the shows table, as the build makes it (a dict of build.py)
#[derive(Clone, Debug, Default)]
pub struct ShowRow {
    pub id: String,
    pub source: String,
    pub title: String,
    pub title_native: String,
    /// Only an AniList row has this column; a library row writes NULL
    pub title_english: Option<String>,
    pub year: Option<Value>,
    pub format: Option<String>,
    pub genres: Vec<String>,
    pub tags: Vec<String>,
    pub tag_ranks: Vec<i64>,
    pub studios: Vec<String>,
    pub overview: String,
    pub score: Option<Value>,
    pub owned: i64,
    pub tmdbid: Option<String>,
    pub anilist_id: Option<i64>,
    pub poster: Option<String>,
    pub relations: Vec<i64>,
    pub recommendations: Vec<(i64, i64)>,
    pub library_id: Option<String>,
    pub provider_ids: Option<Ordered>,
    pub seasons: Vec<i64>,
    pub added_at: Option<String>,
    pub status: Option<String>,
    pub episodes: Option<Value>,
    pub popularity_place: Option<i64>,
    /// The library rows of the other Jellyfin items of the same show (not a column)
    pub merged_ids: Vec<String>,
}

/// The tables of store.py (SCHEMA)
const SCHEMA: &str = "
CREATE TABLE IF NOT EXISTS shows (id TEXT PRIMARY KEY, source TEXT, title TEXT, title_native TEXT, year INTEGER,
  format TEXT, genres TEXT, tags TEXT, tag_ranks TEXT, studios TEXT, overview TEXT, score REAL, owned INTEGER,
  tmdbid TEXT, anilist_id INTEGER, poster TEXT, text_hash TEXT, embedding BLOB);
CREATE TABLE IF NOT EXISTS watched_manual (id TEXT PRIMARY KEY, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS show_weights (id TEXT PRIMARY KEY, tier TEXT NOT NULL, weight REAL NOT NULL, updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS dismissed (id TEXT PRIMARY KEY, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS interest (id TEXT PRIMARY KEY, value INTEGER NOT NULL, match REAL, source TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS layout (id TEXT PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL);
CREATE TABLE IF NOT EXISTS layout_grid (id TEXT PRIMARY KEY, x REAL NOT NULL, y REAL NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rec_log (id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, best_rank INTEGER NOT NULL, days INTEGER NOT NULL, kinds TEXT);
";

/// A JSON number or text as a value of SQLite, as the sqlite3 module of Python binds it
fn sql(value: &Option<Value>) -> SqlValue {
    match value {
        None | Some(Value::Null) => SqlValue::Null,
        Some(Value::Bool(b)) => SqlValue::Integer(*b as i64),
        Some(Value::Number(n)) => n.as_i64().map(SqlValue::Integer).unwrap_or_else(|| SqlValue::Real(n.as_f64().unwrap_or(0.0))),
        Some(Value::String(s)) => SqlValue::Text(s.clone()),
        Some(other) => SqlValue::Text(other.to_string()),
    }
}

fn text(value: &Option<String>) -> SqlValue {
    value.clone().map(SqlValue::Text).unwrap_or(SqlValue::Null)
}

/// The database with the right to change it, with the tables and the columns of store.py
struct Writer {
    con: Connection,
}

impl Writer {
    fn open(path: &Path) -> Result<Writer> {
        let con = Connection::open(path).with_context(|| format!("cannot open the database {}", path.display()))?;
        // The server can write at the same time: wait for its lock
        con.busy_timeout(std::time::Duration::from_secs(30))?;
        con.execute_batch(SCHEMA)?;
        // Older databases do not have the columns that later features added
        let columns: HashSet<String> = {
            let mut statement = con.prepare("PRAGMA table_info(shows)")?;
            let names = statement.query_map([], |row| row.get::<_, String>(1))?;
            names.collect::<rusqlite::Result<_>>()?
        };
        for column in ["relations", "recommendations", "library_id", "provider_ids", "seasons", "added_at", "status", "episodes", "title_english", "popularity_place"] {
            if !columns.contains(column) {
                let kind = if column == "episodes" || column == "popularity_place" { "INTEGER" } else { "TEXT" };
                con.execute_batch(&format!("ALTER TABLE shows ADD COLUMN {column} {kind}"))?;
            }
        }
        Ok(Writer { con })
    }

    fn weights(&self) -> Result<HashMap<String, (String, f64)>> {
        let mut statement = self.con.prepare("SELECT id, tier, weight FROM show_weights")?;
        let rows = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, (row.get::<_, String>(1)?, row.get::<_, f64>(2)?))))?;
        Ok(rows.collect::<rusqlite::Result<_>>()?)
    }

    /// `copy_weight`: give the tier of one show to a show that has no tier
    fn copy_weight(&self, from: &str, to: &str) -> Result<bool> {
        let weights = self.weights()?;
        let (Some((tier, weight)), false) = (weights.get(from), weights.contains_key(to)) else { return Ok(false) };
        self.con.execute(
            "INSERT OR REPLACE INTO show_weights (id, tier, weight, updated_at) VALUES (?1, ?2, ?3, datetime('now'))",
            params![to, tier.to_uppercase(), weight],
        )?;
        Ok(true)
    }

    /// `delete_library_rows_except`: delete the library rows that the library does not have now.
    /// The tier of such a show stays: if the show comes back with the same id, it has its tier again.
    fn delete_library_rows_except(&self, keep: &HashSet<&str>) -> Result<usize> {
        let ids: Vec<String> = {
            let mut statement = self.con.prepare("SELECT id FROM shows WHERE source='library'")?;
            let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
            rows.collect::<rusqlite::Result<_>>()?
        };
        let gone: Vec<&String> = ids.iter().filter(|id| !keep.contains(id.as_str())).collect();
        for id in &gone {
            self.con.execute("DELETE FROM shows WHERE id=?1", [id])?;
        }
        Ok(gone.len())
    }

    fn manual_watched_ids(&self) -> Result<HashSet<String>> {
        let mut statement = self.con.prepare("SELECT id FROM watched_manual")?;
        let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
        Ok(rows.collect::<rusqlite::Result<_>>()?)
    }

    /// `upsert_rows`: a new row is added, a row that is there gets the new values (not its
    /// text_hash and its embedding)
    fn upsert_rows(&mut self, rows: &[&ShowRow]) -> Result<()> {
        let columns = crate::store::COLUMNS;
        let updates: Vec<String> = columns.iter().filter(|c| **c != "id" && **c != "source").map(|c| format!("{c}=excluded.{c}")).collect();
        let statement = format!(
            "INSERT INTO shows ({}) VALUES ({}) ON CONFLICT(id) DO UPDATE SET {}",
            columns.join(","),
            (1..=columns.len()).map(|i| format!("?{i}")).collect::<Vec<_>>().join(","),
            updates.join(", ")
        );
        let change = self.con.transaction()?;
        {
            let mut insert = change.prepare(&statement)?;
            for r in rows {
                let list = |items: &[String]| SqlValue::Text(dumps(&Value::from(items.to_vec())));
                let numbers = |items: &[i64]| SqlValue::Text(dumps(&Value::from(items.to_vec())));
                let values: [SqlValue; 26] = [
                    SqlValue::Text(r.id.clone()),
                    SqlValue::Text(r.source.clone()),
                    SqlValue::Text(r.title.clone()),
                    SqlValue::Text(r.title_native.clone()),
                    sql(&r.year),
                    text(&r.format),
                    list(&r.genres),
                    list(&r.tags),
                    numbers(&r.tag_ranks),
                    list(&r.studios),
                    SqlValue::Text(r.overview.clone()),
                    sql(&r.score),
                    SqlValue::Integer(r.owned),
                    text(&r.tmdbid),
                    r.anilist_id.map(SqlValue::Integer).unwrap_or(SqlValue::Null),
                    text(&r.poster),
                    numbers(&r.relations),
                    SqlValue::Text(dumps(&Value::from(r.recommendations.iter().map(|&(a, b)| Value::from(vec![a, b])).collect::<Vec<_>>()))),
                    text(&r.library_id),
                    SqlValue::Text(r.provider_ids.as_ref().map(dumps_ordered).unwrap_or_else(|| "{}".into())),
                    numbers(&r.seasons),
                    text(&r.added_at),
                    text(&r.status),
                    sql(&r.episodes),
                    text(&r.title_english),
                    r.popularity_place.map(SqlValue::Integer).unwrap_or(SqlValue::Null),
                ];
                insert.execute(rusqlite::params_from_iter(values.iter()))?;
            }
        }
        change.commit()?;
        Ok(())
    }

    /// The id, the text_hash and "has an embedding" of each row
    fn hashes(&self) -> Result<HashMap<String, (Option<String>, bool)>> {
        let mut statement = self.con.prepare("SELECT id, text_hash, embedding IS NOT NULL AND length(embedding) > 0 FROM shows")?;
        let rows = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, (row.get::<_, Option<String>>(1)?, row.get::<_, bool>(2)?))))?;
        Ok(rows.collect::<rusqlite::Result<_>>()?)
    }

    fn save_embeddings(&mut self, items: &[(&str, &[f32], String)]) -> Result<()> {
        let change = self.con.transaction()?;
        for (id, vector, hash) in items {
            let blob: Vec<u8> = vector.iter().flat_map(|x| x.to_le_bytes()).collect();
            change.execute("UPDATE shows SET embedding=?1 WHERE id=?2", params![blob, id])?;
            change.execute("UPDATE shows SET text_hash=?1 WHERE id=?2", params![hash, id])?;
        }
        change.commit()?;
        Ok(())
    }

    fn meta(&self, key: &str) -> Option<String> {
        self.con.query_row("SELECT value FROM meta WHERE key=?1", [key], |row| row.get(0)).ok()
    }

    /// The kept layout if its signature is `signature`: the position and the cell of each row, and the size of a cell
    fn kept_layout(&self, signature: &str) -> Result<Option<(layout::Kept, (f64, f64))>> {
        if self.meta("layout_signature").as_deref() != Some(signature) {
            return Ok(None);
        }
        let Some(cell) = self.meta("layout_cell") else { return Ok(None) };
        let Some((w, h)) = cell.split_once(',') else { return Ok(None) };
        let read = |table: &str| -> Result<HashMap<String, [f32; 2]>> {
            let mut statement = self.con.prepare(&format!("SELECT id, x, y FROM {table}"))?;
            let rows = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, [row.get::<_, f64>(1)? as f32, row.get::<_, f64>(2)? as f32])))?;
            Ok(rows.collect::<rusqlite::Result<_>>()?)
        };
        let coords = read("layout")?;
        let grid = read("layout_grid")?;
        let both = coords.into_iter().filter_map(|(id, p)| grid.get(&id).map(|c| (id, (p, *c)))).collect();
        Ok(Some((both, (w.parse()?, h.parse()?))))
    }

    /// `save_layout` and `save_regions`
    fn save_layout(&mut self, map: &layout::Layout) -> Result<()> {
        let Some(signature) = &map.signature else { return Ok(()) };
        let change = self.con.transaction()?;
        change.execute("DELETE FROM layout", [])?;
        change.execute("DELETE FROM layout_grid", [])?;
        {
            let mut position = change.prepare("INSERT INTO layout (id, x, y) VALUES (?1, ?2, ?3)")?;
            let mut cell = change.prepare("INSERT INTO layout_grid (id, x, y) VALUES (?1, ?2, ?3)")?;
            for (id, p, c) in &map.rows {
                position.execute(params![id, p[0] as f64, p[1] as f64])?;
                cell.execute(params![id, c[0] as f64, c[1] as f64])?;
            }
        }
        let set = "INSERT OR REPLACE INTO meta (key, value) VALUES (?1, ?2)";
        change.execute(set, params!["layout_signature", signature])?;
        change.execute(set, params!["layout_cell", format!("{},{}", pyjson::float_repr(map.cell.0), pyjson::float_repr(map.cell.1))])?;
        let regions = format!("[{}]", map.regions.iter().map(layout::Region::json).collect::<Vec<_>>().join(", "));
        change.execute(set, params!["regions", regions])?;
        change.execute(set, params!["regions_signature", signature])?;
        change.commit()?;
        Ok(())
    }
}

/// The options of the command
struct Options {
    root: PathBuf,
    db: PathBuf,
    refresh_anilist: bool,
    pool_only: bool,
}

fn options(args: &[String]) -> Result<Options> {
    let mut root: Option<PathBuf> = None;
    let mut db: Option<PathBuf> = None;
    let (mut refresh_anilist, mut pool_only) = (false, false);
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--root" => root = Some(PathBuf::from(rest.next().context("--root needs a folder")?)),
            "--db" => db = Some(PathBuf::from(rest.next().context("--db needs a file")?)),
            "--refresh-anilist" => refresh_anilist = true,
            "--pool-only" => pool_only = true,
            other => bail!("unknown argument {other}\nusage: rinrikun build [--root folder] [--db file] [--refresh-anilist] [--pool-only]"),
        }
    }
    let root = root.map(Ok).unwrap_or_else(std::env::current_dir)?;
    let db = db.unwrap_or_else(|| root.join("anime_vec.db"));
    Ok(Options { root, db, refresh_anilist, pool_only })
}

pub fn run(args: &[String]) -> Result<()> {
    let options = options(args)?;
    let started = Instant::now();
    let mut writer = Writer::open(&options.db)?;
    let cache = options.root.join("anilist_cache");

    let lib_rows = jellyfin::fetch_library(&options.root)?;
    println!("library rows: {}", lib_rows.len());
    if !lib_rows.is_empty() {
        // Two Jellyfin items of one show are one row: the row keeps the tier of the other item
        for lib in &lib_rows {
            for other in &lib.merged_ids {
                writer.copy_weight(other, &lib.id)?;
            }
        }
        let keep: HashSet<&str> = lib_rows.iter().map(|r| r.id.as_str()).collect();
        let removed = writer.delete_library_rows_except(&keep)?;
        if removed > 0 {
            println!("library rows that Jellyfin does not have now, removed: {removed}");
        }
    }
    let mut pool_rows = pool::fetch_pool(&cache, options.refresh_anilist)?;
    println!("anilist pool rows: {}", pool_rows.len());

    let idmap = match idmap::load_entries(&options.root.join("idmap_cache"), false) {
        Ok(entries) => Some(idmap::IdMap::new(&entries)),
        Err(error) => {
            println!("WARNING no id map ({error:#}): the match uses only titles");
            None
        }
    };
    if !options.pool_only {
        // AniList gives only the 5000 most popular anime for one query. The id map lists all
        // anime that the other anime databases know, thus the build asks for these by id. It
        // also asks for the anime that the catalog points to.
        let wanted = idmap.as_ref().map(|m| m.all_ids.clone()).unwrap_or_default();
        let extra = pool::fetch_extras(&cache, &pool_rows, &wanted, options.refresh_anilist)?;
        println!("anilist rows outside the pool: {}", extra.len());
        pool_rows.extend(extra);
    }

    let links = matching::link_library(&lib_rows, &mut pool_rows, idmap.as_ref());
    println!("pool rows matched to library: {} by id, {} by title", links.by_id, links.by_title);
    println!("library rows without a pool row: {}", links.unlinked_library_rows);
    println!("AniList entries of the library that are not in the pool: {}", links.missing_ids);

    let manual = writer.manual_watched_ids()?;
    for r in pool_rows.iter_mut() {
        if manual.contains(&r.id) {
            r.owned = 1;
        }
    }
    let all: Vec<&ShowRow> = lib_rows.iter().chain(pool_rows.iter()).collect();
    writer.upsert_rows(&all)?;

    // The embeddings of the rows whose text changed
    let store = Store::open_read_only(&options.db)?;
    let rows = store.load_rows()?;
    let hashes = writer.hashes()?;
    let todo: Vec<(&crate::store::Row, String)> = rows
        .iter()
        .map(|r| (r, embed::text_hash(&r.data)))
        .filter(|(r, hash)| hashes.get(&r.id).is_none_or(|(kept, has)| kept.as_deref() != Some(hash.as_str()) || !has))
        .collect();
    println!("embedding {} rows (skipped {} unchanged)", todo.len(), rows.len() - todo.len());
    let missing: Vec<&str> = rows.iter().filter(|r| !r.data.get("overview").is_some_and(crate::store::truthy)).map(|r| r.data["title"].as_str().unwrap_or("")).collect();
    if !missing.is_empty() {
        println!("WARNING rows without overview: {} e.g. {:?}", missing.len(), &missing[..missing.len().min(5)]);
    }
    if !todo.is_empty() {
        let mut embedder = embed::Embedder::load(&options.root)?;
        for (start, batch) in todo.chunks(64).enumerate().map(|(k, b)| (k * 64, b)) {
            let texts: Vec<String> = batch.iter().map(|(r, _)| embed::build_text(&r.data)).collect();
            let vectors = embedder.embed(&texts)?;
            let items: Vec<(&str, &[f32], String)> = batch.iter().zip(&vectors).map(|((r, hash), v)| (r.id.as_str(), v.as_slice(), hash.clone())).collect();
            writer.save_embeddings(&items)?;
            println!("  {}/{}", (start + 64).min(todo.len()), todo.len());
        }
    }

    // The map layout: the server reads it from the database
    println!("computing the map layout");
    let store = Store::open_read_only(&options.db)?;
    let engine = Engine::load(&store)?;
    let raw = store.embeddings()?;
    let unique = engine.unique_rows();
    let ids: Vec<&str> = unique.iter().map(|&i| engine.rows[i].id.as_str()).collect();
    let vectors: Vec<&[f32]> = unique.iter().map(|&i| raw[&engine.rows[engine.tag_source(i)].id].as_slice()).collect();
    let signature = layout::signature(&ids, &vectors);
    let (kept, kept_cell) = writer.kept_layout(&signature)?.map(|(k, c)| (Some(k), Some(c))).unwrap_or((None, None));
    let map = layout::compute(&engine, &raw, kept, kept_cell);
    writer.save_layout(&map)?;
    println!("done -> {} in {:.1?}", options.db.display(), started.elapsed());
    Ok(())
}

/// `rinrikun build-check <database> [--embed N] [--tsne]`: compare the text hashes of the rows
/// with the hashes that the database keeps, and compute the layout signature. It reads only.
///
/// --embed N  embed N rows again and compare the vectors with the vectors of the database
/// --tsne     compute a new map and compare its quality with the map of the database: the part of
///            the 10 nearest neighbours of each show that are also its neighbours on the map
pub fn check(args: &[String]) -> Result<()> {
    let usage = "usage: rinrikun build-check <database> [--embed N] [--tsne]";
    let db = PathBuf::from(args.first().context(usage)?);
    let mut embed_count = 0usize;
    let mut with_tsne = false;
    let mut rest = args[1..].iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--embed" => embed_count = rest.next().context(usage)?.parse()?,
            "--tsne" => with_tsne = true,
            _ => bail!("{usage}"),
        }
    }
    let store = Store::open_read_only(&db)?;
    let rows = store.load_rows()?;
    let con = Connection::open_with_flags(&db, rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let mut statement = con.prepare("SELECT id, text_hash FROM shows")?;
    let kept: HashMap<String, Option<String>> = statement.query_map([], |row| Ok((row.get(0)?, row.get(1)?)))?.collect::<rusqlite::Result<_>>()?;
    let differ: Vec<&str> = rows.iter().filter(|r| kept.get(&r.id).cloned().flatten().as_deref() != Some(embed::text_hash(&r.data).as_str())).map(|r| r.id.as_str()).collect();
    println!("rows: {}, text hashes that differ: {} {:?}", rows.len(), differ.len(), &differ[..differ.len().min(5)]);
    let engine = Engine::load(&store)?;
    let raw = store.embeddings()?;
    let unique = engine.unique_rows();
    let ids: Vec<&str> = unique.iter().map(|&i| engine.rows[i].id.as_str()).collect();
    let vectors: Vec<&[f32]> = unique.iter().map(|&i| raw[&engine.rows[engine.tag_source(i)].id].as_slice()).collect();
    println!("layout signature: {}", layout::signature(&ids, &vectors));

    if embed_count > 0 {
        let root = db.parent().map(Path::to_path_buf).unwrap_or_default();
        let mut embedder = embed::Embedder::load(&root)?;
        let step = (rows.len() / embed_count).max(1);
        let sample: Vec<&crate::store::Row> = rows.iter().step_by(step).take(embed_count).filter(|r| raw.contains_key(&r.id)).collect();
        let texts: Vec<String> = sample.iter().map(|r| embed::build_text(&r.data)).collect();
        let started = Instant::now();
        let vectors = embedder.embed(&texts)?;
        let elapsed = started.elapsed();
        let cosines: Vec<f64> = sample
            .iter()
            .zip(&vectors)
            .map(|(r, v)| {
                let kept = &raw[&r.id];
                let dot: f64 = v.iter().zip(kept).map(|(a, b)| *a as f64 * *b as f64).sum();
                let norm = |x: &[f32]| x.iter().map(|a| (*a as f64).powi(2)).sum::<f64>().sqrt();
                dot / (norm(v) * norm(kept)).max(1e-12)
            })
            .collect();
        let min = cosines.iter().copied().fold(f64::INFINITY, f64::min);
        let mean = cosines.iter().sum::<f64>() / cosines.len().max(1) as f64;
        println!("embeddings of {} rows: cosine to the kept vectors min {min:.6}, mean {mean:.6}, {:.2?} for each text", sample.len(), elapsed / sample.len().max(1) as u32);
    }

    if with_tsne {
        let x: Vec<f32> = unique.iter().flat_map(|&i| engine.eff_row(i).iter().copied()).collect();
        let n = unique.len();
        let kept: Vec<[f32; 2]> = unique.iter().map(|&i| [engine.coords[i].0, engine.coords[i].1]).collect();
        println!("map of the database: {:.1}% of the 10 nearest neighbours kept", 100.0 * tsne::neighbour_overlap(&x, n, engine.dim, &kept, 10));
        let started = Instant::now();
        let map = layout::fit_unit_square(&tsne::tsne(&x, n, engine.dim));
        println!("new Rust map ({:.1?}): {:.1}% of the 10 nearest neighbours kept", started.elapsed(), 100.0 * tsne::neighbour_overlap(&x, n, engine.dim, &map, 10));
    }
    Ok(())
}
