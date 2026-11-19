//! The database of the shows. It is the same file with the same tables as anime_vec/store.py.
//! In this phase the Rust server only reads the database: the Python server writes it.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use anyhow::{Context, Result};
use rusqlite::types::Value as SqlValue;
use rusqlite::{Connection, OpenFlags};
use serde_json::{Map, Number, Value};

/// The columns of the shows table that the build writes (store.COLUMNS), in their order
pub const COLUMNS: [&str; 26] = [
    "id", "source", "title", "title_native", "year", "format", "genres", "tags", "tag_ranks", "studios",
    "overview", "score", "owned", "tmdbid", "anilist_id", "poster", "relations", "recommendations",
    "library_id", "provider_ids", "seasons", "added_at", "status", "episodes", "title_english",
    "popularity_place",
];

/// The columns that hold JSON, with the value for a row that has no data
const JSON_COLUMNS: [(&str, bool); 8] = [
    // (name, the empty value is a map and not a list)
    ("genres", false),
    ("tags", false),
    ("tag_ranks", false),
    ("studios", false),
    ("relations", false),
    ("recommendations", false),
    ("provider_ids", true),
    ("seasons", false),
];

/// One show of the database, as anime_vec/store.py load_rows gives it
#[derive(Clone, Debug)]
pub struct Row {
    pub id: String,
    pub source: String,
    /// All columns as the API gives them: the JSON columns are parsed. It also has
    /// "manual_watched", "tier" and "weight".
    pub data: Map<String, Value>,
    /// The user has the show: it is in the library, or the user marked it as watched by hand
    pub owned: bool,
    pub manual_watched: bool,
    pub tier: Option<String>,
    pub weight: f64,
    pub anilist_id: Option<i64>,
    pub library_id: Option<String>,
    pub format: Option<String>,
    pub status: Option<String>,
    pub title: Option<String>,
    pub title_native: Option<String>,
    pub year: Option<f64>,
    pub episodes: Option<f64>,
    pub score: Option<f64>,
    pub popularity_place: Option<f64>,
    pub tags: Vec<String>,
    /// The rank of each tag. None is a missing rank.
    pub tag_ranks: Vec<Option<f64>>,
    pub genres: Vec<String>,
    /// The AniList ids of the related anime (sequel, prequel, side story)
    pub relations: Vec<i64>,
    /// The AniList user recommendations: (AniList id, rating)
    pub recommendations: Vec<(i64, f64)>,
}

/// An answer of the Discover deck
#[derive(Clone, Debug)]
pub struct Answer {
    pub value: i64,
    pub source: Option<String>,
}

/// One show of the log of the recommendations
#[derive(Clone, Debug)]
pub struct LogEntry {
    pub id: String,
    pub first_seen: String,
    pub best_rank: i64,
    pub kinds: Option<String>,
}

/// The map layout that the Python engine keeps in the database
pub struct Layout {
    pub coords: HashMap<String, (f64, f64)>,
    pub grid: HashMap<String, (f64, f64)>,
    pub cell: (f64, f64),
}

pub struct Store {
    con: Connection,
}

/// A value of the database as JSON
fn to_json(value: SqlValue) -> Value {
    match value {
        SqlValue::Null | SqlValue::Blob(_) => Value::Null,
        SqlValue::Integer(v) => Value::Number(v.into()),
        SqlValue::Real(v) => Number::from_f64(v).map(Value::Number).unwrap_or(Value::Null),
        SqlValue::Text(v) => Value::String(v),
    }
}

/// A value as a number, as `float(value)` in Python. A text with a number is a number too.
pub fn number(value: &Value) -> Option<f64> {
    match value {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.trim().parse().ok(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        _ => None,
    }
}

fn text(value: &Value) -> Option<String> {
    match value {
        Value::String(s) => Some(s.clone()),
        Value::Null => None,
        other => Some(other.to_string()),
    }
}

/// True for a value that Python counts as true: not empty, not 0, not None
pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|v| v != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn strings(value: &Value) -> Vec<String> {
    value.as_array().map(|items| items.iter().filter_map(text).collect()).unwrap_or_default()
}

impl Store {
    /// Open the database without the right to change it
    pub fn open_read_only(path: &Path) -> Result<Store> {
        let con = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX)
            .with_context(|| format!("cannot open the database {}", path.display()))?;
        Ok(Store { con })
    }

    fn ids(&self, sql: &str) -> HashSet<String> {
        // A database from an older version does not have each table
        let Ok(mut statement) = self.con.prepare(sql) else { return HashSet::new() };
        let Ok(rows) = statement.query_map([], |row| row.get::<_, String>(0)) else { return HashSet::new() };
        rows.filter_map(|r| r.ok()).collect()
    }

    pub fn manual_watched_ids(&self) -> HashSet<String> {
        self.ids("SELECT id FROM watched_manual")
    }

    pub fn dismissed_ids(&self) -> HashSet<String> {
        self.ids("SELECT id FROM dismissed")
    }

    /// The answers of the Discover deck, by the id of the show
    pub fn interest(&self) -> HashMap<String, Answer> {
        let Ok(mut statement) = self.con.prepare("SELECT id, value, source FROM interest") else { return HashMap::new() };
        let Ok(rows) = statement.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, Answer { value: row.get(1)?, source: row.get(2)? }))
        }) else {
            return HashMap::new();
        };
        rows.filter_map(|r| r.ok()).collect()
    }

    /// The log of the recommendations, in the order of the table
    pub fn rec_log(&self) -> Vec<LogEntry> {
        let Ok(mut statement) = self.con.prepare("SELECT id, first_seen, last_seen, best_rank, days, kinds FROM rec_log") else {
            return Vec::new();
        };
        let Ok(rows) = statement.query_map([], |row| {
            Ok(LogEntry { id: row.get(0)?, first_seen: row.get(1)?, best_rank: row.get(3)?, kinds: row.get(5)? })
        }) else {
            return Vec::new();
        };
        rows.filter_map(|r| r.ok()).collect()
    }

    /// The tiers: (id, tier, weight), in the order of the table. The order is the order of
    /// `get_weights` in Python, which decides which tier a counterpart gets.
    pub fn weights(&self) -> Result<Vec<(String, String, f64)>> {
        let mut statement = self.con.prepare("SELECT id, tier, weight FROM show_weights")?;
        let rows = statement.query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?;
        Ok(rows.collect::<rusqlite::Result<_>>()?)
    }

    /// The shows, in the order of their ids
    pub fn load_rows(&self) -> Result<Vec<Row>> {
        let manual = self.manual_watched_ids();
        let weights: HashMap<String, (String, f64)> =
            self.weights()?.into_iter().map(|(id, tier, weight)| (id, (tier, weight))).collect();
        // A database from an older version does not have the newest columns
        let existing: HashSet<String> = {
            let mut statement = self.con.prepare("PRAGMA table_info(shows)")?;
            let names = statement.query_map([], |row| row.get::<_, String>(1))?;
            names.collect::<rusqlite::Result<_>>()?
        };
        let names: Vec<&str> = COLUMNS.iter().copied().filter(|c| existing.contains(*c)).collect();
        let sql = format!("SELECT {} FROM shows ORDER BY id", names.join(","));
        let mut statement = self.con.prepare(&sql)?;
        let mut cursor = statement.query([])?;
        let mut out = Vec::new();
        while let Some(record) = cursor.next()? {
            let mut data = Map::new();
            for column in COLUMNS {
                data.insert(column.to_string(), Value::Null);
            }
            for (n, name) in names.iter().enumerate() {
                data.insert(name.to_string(), to_json(record.get::<_, SqlValue>(n)?));
            }
            for (column, is_map) in JSON_COLUMNS {
                let parsed = match data.get(column) {
                    Some(Value::String(s)) if !s.is_empty() => serde_json::from_str(s).unwrap_or(Value::Null),
                    _ => Value::Null,
                };
                let empty = if is_map { Value::Object(Map::new()) } else { Value::Array(Vec::new()) };
                data.insert(column.to_string(), if parsed.is_null() { empty } else { parsed });
            }
            let id = text(&data["id"]).unwrap_or_default();
            let is_manual = manual.contains(&id);
            let owned = truthy(&data["owned"]) || is_manual;
            data.insert("owned".into(), Value::from(owned as i64));
            data.insert("manual_watched".into(), Value::from(is_manual as i64));
            let (tier, weight) = match weights.get(&id) {
                Some((tier, weight)) => (Some(tier.clone()), *weight),
                None => (None, 1.0),
            };
            data.insert("tier".into(), tier.clone().map(Value::String).unwrap_or(Value::Null));
            data.insert("weight".into(), Value::from(weight));
            let ranks = data["tag_ranks"]
                .as_array()
                .map(|items| items.iter().map(number).collect())
                .unwrap_or_default();
            let relations = data["relations"].as_array().map(|items| items.iter().filter_map(|v| v.as_i64()).collect()).unwrap_or_default();
            let recommendations = data["recommendations"]
                .as_array()
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|pair| {
                            let pair = pair.as_array()?;
                            Some((pair.first()?.as_i64()?, number(pair.get(1)?)?))
                        })
                        .collect()
                })
                .unwrap_or_default();
            out.push(Row {
                source: text(&data["source"]).unwrap_or_default(),
                owned,
                manual_watched: is_manual,
                tier,
                weight,
                anilist_id: data["anilist_id"].as_i64().or_else(|| number(&data["anilist_id"]).map(|v| v as i64)),
                library_id: text(&data["library_id"]).filter(|s| !s.is_empty()),
                format: text(&data["format"]),
                status: text(&data["status"]),
                title: text(&data["title"]),
                title_native: text(&data["title_native"]),
                year: number(&data["year"]),
                episodes: number(&data["episodes"]),
                score: number(&data["score"]),
                popularity_place: number(&data["popularity_place"]),
                tags: strings(&data["tags"]),
                tag_ranks: ranks,
                genres: strings(&data["genres"]),
                relations,
                recommendations,
                id,
                data,
            });
        }
        Ok(out)
    }

    /// The embedding of each show that has one
    pub fn embeddings(&self) -> Result<HashMap<String, Vec<f32>>> {
        let mut statement = self.con.prepare("SELECT id, embedding FROM shows WHERE embedding IS NOT NULL")?;
        let rows = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, Vec<u8>>(1)?)))?;
        let mut out = HashMap::new();
        for row in rows {
            let (id, blob) = row?;
            if blob.is_empty() {
                continue;
            }
            let values = blob.chunks_exact(4).map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]])).collect();
            out.insert(id, values);
        }
        Ok(out)
    }

    /// The map layout that the Python engine keeps in the database, or None. The Rust engine does
    /// not compute the layout in this phase: it uses the layout of the Python engine.
    pub fn layout(&self) -> Option<Layout> {
        let cell: String = self.con.query_row("SELECT value FROM meta WHERE key='layout_cell'", [], |row| row.get(0)).ok()?;
        let (width, height) = cell.split_once(',')?;
        let read = |table: &str| -> Option<HashMap<String, (f64, f64)>> {
            let mut statement = self.con.prepare(&format!("SELECT id, x, y FROM {table}")).ok()?;
            let rows = statement.query_map([], |row| Ok((row.get::<_, String>(0)?, (row.get(1)?, row.get(2)?)))).ok()?;
            Some(rows.filter_map(|r| r.ok()).collect())
        };
        Some(Layout { coords: read("layout")?, grid: read("layout_grid")?, cell: (width.parse().ok()?, height.parse().ok()?) })
    }

    /// The areas of the map that the Python engine keeps in the database, if they are for the layout of now
    pub fn regions(&self) -> Option<Value> {
        let value = |key: &str| -> Option<String> { self.con.query_row("SELECT value FROM meta WHERE key=?", [key], |row| row.get(0)).ok() };
        if value("regions_signature")? != value("layout_signature")? {
            return None;
        }
        serde_json::from_str(&value("regions")?).ok()
    }
}
