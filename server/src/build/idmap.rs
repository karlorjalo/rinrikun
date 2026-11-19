//! The map from the provider ids of a Jellyfin item (TMDB, TVDB, IMDb) to AniList ids, with the
//! rules of anime_vec/idmap.py.
//!
//! Jellyfin gives one item for a series. AniList has one entry for each season. The public id map
//! of the Fribb/anime-lists project connects the ids, with the season number of each AniList entry.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use std::time::{Duration, SystemTime};

use anyhow::{Context, Result};
use serde_json::Value;

use super::pyjson::Ordered;

const URL: &str = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json";
const MAX_AGE_DAYS: f64 = 7.0;

/// `load_entries`: the entries of the id map. The file stays in the cache for MAX_AGE_DAYS.
pub fn load_entries(cache_dir: &Path, force: bool) -> Result<Vec<Value>> {
    let cache = cache_dir.join("anime-list-full.json");
    let fresh = std::fs::metadata(&cache)
        .and_then(|m| m.modified())
        .ok()
        .and_then(|t| SystemTime::now().duration_since(t).ok())
        .is_some_and(|age| age.as_secs_f64() < MAX_AGE_DAYS * 86400.0);
    if force || !fresh {
        let download = || -> Result<String> {
            let agent: ureq::Agent = ureq::Agent::config_builder().timeout_global(Some(Duration::from_secs(120))).build().into();
            let text = agent.get(URL).call()?.body_mut().with_config().limit(512 << 20).read_to_string()?;
            serde_json::from_str::<Value>(&text).context("the id map is not JSON")?;
            Ok(text)
        };
        match download() {
            Ok(text) => {
                std::fs::create_dir_all(cache_dir)?;
                std::fs::write(&cache, text)?;
            }
            // An old cache is better than no id map
            Err(error) if cache.exists() => eprintln!("WARNING the id map was not downloaded ({error:#}): the old file stays in use"),
            Err(error) => return Err(error),
        }
    }
    let text = std::fs::read_to_string(&cache)?;
    let entries: Vec<Value> = serde_json::from_str(&text).context("the id map is not a list")?;
    Ok(entries)
}

/// `_as_list`: a value as a list of values
fn as_list(value: Option<&Value>) -> Vec<&Value> {
    match value {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items.iter().collect(),
        Some(other) => vec![other],
    }
}

/// The text of a key as `str(key)` in Python
fn key_text(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) if n.is_f64() => super::pyjson::float_repr(n.as_f64().unwrap()),
        other => other.to_string(),
    }
}

/// `_season_number`: the season number of an entry. Season 0 is a special, an OVA or a movie.
/// The TVDB number is the first choice. An entry without a number is season 1 if it is a TV series.
fn season_number(season: Option<&Value>, kind: &str) -> i64 {
    for source in ["tvdb", "tmdb"] {
        if let Some(n) = season.and_then(|s| s.get(source)).filter(|v| !v.is_null()) {
            return n.as_i64().unwrap_or(0);
        }
    }
    if kind == "TV" { 1 } else { 0 }
}

/// (AniList id, season number)
type Item = (i64, i64);

#[derive(Default)]
pub struct IdMap {
    tmdb_tv: HashMap<String, Vec<Item>>,
    tmdb_movie: HashMap<String, Vec<Item>>,
    tvdb: HashMap<String, Vec<Item>>,
    imdb: HashMap<String, Vec<Item>>,
    /// All AniList ids of the id map: the anime that the other anime databases know
    pub all_ids: BTreeSet<i64>,
}

impl IdMap {
    pub fn new(entries: &[Value]) -> IdMap {
        let mut map = IdMap::default();
        for e in entries {
            let Some(anilist_id) = e.get("anilist_id").and_then(Value::as_i64) else { continue };
            map.all_ids.insert(anilist_id);
            let kind = e.get("type").and_then(Value::as_str).unwrap_or("").to_uppercase();
            let season = e.get("season").filter(|s| s.is_object());
            let item = (anilist_id, season_number(season, &kind));
            let add = |index: &mut HashMap<String, Vec<Item>>, value: Option<&Value>| {
                for key in as_list(value) {
                    index.entry(key_text(key)).or_default().push(item);
                }
            };
            match e.get("themoviedb_id") {
                Some(tmdb @ Value::Object(_)) => {
                    add(&mut map.tmdb_tv, tmdb.get("tv"));
                    add(&mut map.tmdb_movie, tmdb.get("movie"));
                }
                Some(Value::Null) | None => {}
                Some(tmdb) => {
                    if kind == "MOVIE" {
                        add(&mut map.tmdb_movie, Some(tmdb));
                    } else {
                        add(&mut map.tmdb_tv, Some(tmdb));
                    }
                }
            }
            add(&mut map.tvdb, e.get("tvdb_id"));
            add(&mut map.imdb, e.get("imdb_id"));
        }
        map
    }

    /// `anilist_ids`: the AniList ids of a library item.
    ///
    /// For a series, `seasons` are the seasons that the library has. An AniList entry is in the
    /// result if its season is not later than the last of these seasons. If `seasons` is empty,
    /// all seasons are in the result. A series never gives the entries of season 0.
    pub fn anilist_ids(&self, provider_ids: Option<&Ordered>, is_movie: bool, seasons: &[i64]) -> HashSet<i64> {
        let get = |key: &str| -> String {
            provider_ids.and_then(|p| p.0.iter().find(|(k, _)| k == key)).map(|(_, v)| key_text(v)).unwrap_or_else(|| "None".into())
        };
        let lookup = |index: &HashMap<String, Vec<Item>>, key: String| index.get(&key).cloned().unwrap_or_default();
        if is_movie {
            let found = [lookup(&self.tmdb_movie, get("tmdb")), lookup(&self.imdb, get("imdb"))].concat();
            return found.into_iter().map(|(id, _)| id).collect();
        }
        let regular: Vec<i64> = seasons.iter().copied().filter(|&s| s != 0).collect();
        if !seasons.is_empty() && regular.is_empty() {
            // The library has only a Specials folder
            return HashSet::new();
        }
        let last = regular.iter().copied().max();
        let found = [lookup(&self.tmdb_tv, get("tmdb")), lookup(&self.tvdb, get("tvdb"))].concat();
        found.into_iter().filter(|&(_, season)| season != 0 && last.is_none_or(|l| season <= l)).map(|(id, _)| id).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn provider(text: &str) -> Ordered {
        serde_json::from_str(text).unwrap()
    }

    #[test]
    fn a_series_gives_its_seasons_up_to_the_last_season_of_the_library() {
        let map = IdMap::new(&[
            json!({"anilist_id": 1, "type": "TV", "themoviedb_id": 100, "tvdb_id": 500, "season": {"tvdb": 1}}),
            json!({"anilist_id": 2, "type": "TV", "tvdb_id": 500, "season": {"tvdb": 2, "tmdb": 1}}),
            json!({"anilist_id": 3, "type": "TV", "tvdb_id": 500, "season": {"tvdb": 3}}),
            json!({"anilist_id": 4, "type": "OVA", "tvdb_id": 500, "season": {"tvdb": 0}}),
            json!({"anilist_id": 5, "type": "MOVIE", "themoviedb_id": {"movie": [77]}, "imdb_id": "tt9"}),
            json!({"anilist_id": 6, "type": "TV", "tvdb_id": [600, 601]}),
            json!({"type": "TV", "tvdb_id": 500}),
        ]);
        let series = provider(r#"{"tvdb": "500"}"#);
        let sorted = |s: HashSet<i64>| { let mut v: Vec<i64> = s.into_iter().collect(); v.sort(); v };
        assert_eq!(sorted(map.anilist_ids(Some(&series), false, &[2])), vec![1, 2]);
        assert_eq!(sorted(map.anilist_ids(Some(&series), false, &[])), vec![1, 2, 3]);
        assert_eq!(sorted(map.anilist_ids(Some(&series), false, &[0])), Vec::<i64>::new());
        assert_eq!(sorted(map.anilist_ids(Some(&provider(r#"{"tmdb": "100"}"#)), false, &[1])), vec![1]);
        assert_eq!(sorted(map.anilist_ids(Some(&provider(r#"{"tmdb": "77"}"#)), true, &[])), vec![5]);
        assert_eq!(sorted(map.anilist_ids(Some(&provider(r#"{"imdb": "tt9"}"#)), true, &[])), vec![5]);
        assert_eq!(sorted(map.anilist_ids(Some(&provider(r#"{"tvdb": "601"}"#)), false, &[1])), vec![6]);
        assert_eq!(map.all_ids.len(), 6);
    }
}
