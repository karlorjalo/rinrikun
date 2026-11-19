//! The anime of AniList for the catalog: the most popular anime (the pool), and more anime by
//! their ids. Each answer stays in a file of
//! anilist_cache, thus a build asks AniList only for the data that is old or missing.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use anyhow::{Context, Result, anyhow, bail};
use serde_json::{Value, json};

use super::ShowRow;
use crate::anilist;

/// The fields of one anime. The page query and the id query use the same fields.
const MEDIA_FIELDS: &str = "id title { romaji english native } format seasonYear startDate { year } status episodes genres
tags { name rank } studios(isMain: true) { nodes { name } }
description(asHtml: false) averageScore coverImage { medium }
relations { edges { relationType node { id type } } }
recommendations(sort: RATING_DESC, perPage: 25) { nodes { rating mediaRecommendation { id type } } }";
/// A cached answer without these keys is from an older query
const REQUIRED_KEYS: [&str; 4] = ["relations", "recommendations", "status", "startDate"];
/// The time between two requests. AniList permits 30 requests in one minute.
const PAUSE: Duration = Duration::from_millis(2100);
/// AniList gives a maximum of 5000 results (100 pages) for one sorted query
const MAX_PAGES: u32 = 100;
/// The cache of a page is good for this number of days. The popularity order changes slowly.
const PAGE_MAX_AGE_DAYS: f64 = 30.0;
/// The cache of an anime that is not finished is good for this number of days. Without this
/// limit an announced anime stays "not released" in the cache.
const MEDIA_MAX_AGE_DAYS: f64 = 7.0;
/// The relation types that connect two entries of the same franchise
const FRANCHISE_RELATIONS: [&str; 6] = ["SEQUEL", "PREQUEL", "PARENT", "SIDE_STORY", "SUMMARY", "ALTERNATIVE"];
const TIMEOUT: Duration = Duration::from_secs(60);

fn query() -> String {
    format!("query ($page: Int) {{ Page(page: $page, perPage: 50) {{ pageInfo {{ lastPage }} media(type: ANIME, sort: POPULARITY_DESC, isAdult: false) {{ {MEDIA_FIELDS} }} }} }}")
}

fn id_query() -> String {
    format!("query ($ids: [Int]) {{ Page(perPage: 50) {{ media(id_in: $ids, type: ANIME, isAdult: false) {{ {MEDIA_FIELDS} }} }} }}")
}

/// `franchise_relations`: the AniList ids of the anime in the same franchise as this anime
pub fn franchise_relations(m: &Value) -> Vec<i64> {
    let mut out = BTreeSet::new();
    for edge in m.pointer("/relations/edges").and_then(Value::as_array).into_iter().flatten() {
        let relation = edge.get("relationType").and_then(Value::as_str).unwrap_or("");
        let node = edge.get("node").filter(|n| n.is_object());
        if FRANCHISE_RELATIONS.contains(&relation) && node.and_then(|n| n.get("type")).and_then(Value::as_str) == Some("ANIME") {
            if let Some(id) = node.and_then(|n| n.get("id")).and_then(Value::as_i64) {
                out.insert(id);
            }
        }
    }
    out.into_iter().collect()
}

/// `user_recommendations`: [AniList id, rating] pairs of the anime that AniList users recommend
pub fn user_recommendations(m: &Value) -> Vec<(i64, i64)> {
    let mut out = Vec::new();
    for node in m.pointer("/recommendations/nodes").and_then(Value::as_array).into_iter().flatten() {
        let other = node.get("mediaRecommendation").filter(|o| o.is_object());
        let rating = node.get("rating").and_then(Value::as_i64).unwrap_or(0);
        let kind = other.and_then(|o| o.get("type")).and_then(Value::as_str);
        if let (Some("ANIME"), Some(id)) = (kind, other.and_then(|o| o.get("id")).and_then(Value::as_i64)) {
            if rating > 0 {
                out.push((id, rating));
            }
        }
    }
    out
}

/// A text value; an empty text and null are None
fn text(value: Option<&Value>) -> Option<String> {
    value.and_then(Value::as_str).filter(|s| !s.is_empty()).map(str::to_string)
}

/// `row_from_media`: the row of one anime
pub fn row_from_media(m: &Value) -> ShowRow {
    let title = m.get("title").filter(|t| t.is_object());
    let part = |key: &str| text(title.and_then(|t| t.get(key)));
    let id = m["id"].as_i64().unwrap_or(0);
    let tags: Vec<&Value> = m.get("tags").and_then(Value::as_array).map(|t| t.iter().collect()).unwrap_or_default();
    // `(averageScore or 0) / 10.0 or None`
    let score = m.get("averageScore").and_then(Value::as_f64).map(|s| s / 10.0).filter(|s| *s != 0.0);
    let year = m.get("seasonYear").filter(|v| crate::store::truthy(v)).cloned().or_else(|| m.pointer("/startDate/year").cloned()).filter(|v| !v.is_null());
    ShowRow {
        id: format!("al:{id}"),
        source: "anilist".into(),
        title: part("romaji").or_else(|| part("english")).or_else(|| part("native")).unwrap_or_default(),
        title_native: part("native").unwrap_or_default(),
        title_english: Some(part("english").unwrap_or_default()),
        year,
        format: text(m.get("format")).map(|f| f.to_lowercase()),
        genres: m.get("genres").and_then(Value::as_array).map(|g| g.iter().filter_map(|v| v.as_str().map(str::to_string)).collect()).unwrap_or_default(),
        tags: tags.iter().filter_map(|t| t.get("name").and_then(Value::as_str).map(str::to_string)).collect(),
        tag_ranks: tags.iter().map(|t| t.get("rank").and_then(Value::as_i64).unwrap_or(0)).collect(),
        studios: m.pointer("/studios/nodes").and_then(Value::as_array).map(|n| n.iter().filter_map(|s| s.get("name").and_then(Value::as_str).map(str::to_string)).collect()).unwrap_or_default(),
        overview: m.get("description").and_then(Value::as_str).unwrap_or("").replace("<br>", "\n"),
        score: score.map(Value::from),
        owned: 0,
        anilist_id: Some(id),
        poster: m.pointer("/coverImage/medium").and_then(Value::as_str).map(str::to_string),
        relations: franchise_relations(m),
        recommendations: user_recommendations(m),
        status: m.get("status").and_then(Value::as_str).map(str::to_string),
        episodes: m.get("episodes").cloned().filter(|v| !v.is_null()),
        ..ShowRow::default()
    }
}

fn age_days(path: &Path) -> f64 {
    let modified = std::fs::metadata(path).and_then(|m| m.modified()).unwrap_or(SystemTime::now());
    SystemTime::now().duration_since(modified).map(|d| d.as_secs_f64()).unwrap_or(0.0) / 86400.0
}

/// Ask AniList up to 5 times, with a longer pause after each failure, as `_fetch_page` and `_fetch_ids`
fn with_retries(what: &str, mut work: impl FnMut() -> Result<Value>) -> Result<Value> {
    let mut last = anyhow!("no request");
    for attempt in 0..5u64 {
        match work() {
            Ok(value) => return Ok(value),
            Err(error) => last = error,
        }
        if attempt < 4 {
            std::thread::sleep(Duration::from_secs(10 * (attempt + 1)));
        }
    }
    Err(last.context(format!("AniList unreachable for {what}")))
}

fn has_page(data: &Value) -> bool {
    data.get("data").and_then(|d| d.get("Page")).is_some_and(crate::store::truthy)
}

fn fetch_page(page: u32) -> Result<Value> {
    with_retries(&format!("page {page}"), || {
        let data = anilist::post(&query(), json!({ "page": page }), TIMEOUT)?;
        if !has_page(&data) {
            bail!("AniList returned no data for page {page}: {}", data.to_string().chars().take(200).collect::<String>());
        }
        Ok(data)
    })
}

/// `_read_cache`: the cached page, or None if the file is not correct, too old, or from an older query
fn read_page(cache: &Path) -> Option<Value> {
    let data: Value = serde_json::from_str(&std::fs::read_to_string(cache).ok()?).ok()?;
    let page = data.get("data")?.get("Page")?.clone();
    let media = page.get("media")?.as_array()?;
    if let Some(first) = media.first() {
        if REQUIRED_KEYS.iter().any(|key| first.get(key).is_none()) {
            return None;
        }
    }
    page.get("pageInfo")?.get("lastPage")?;
    if age_days(cache) > PAGE_MAX_AGE_DAYS {
        return None;
    }
    Some(page)
}

/// `fetch_pool`: the rows of the most popular anime on AniList, the most popular anime first.
/// Each row gets its place in this order as `popularity_place`: 1 is the most popular anime.
pub fn fetch_pool(cache_dir: &Path, force: bool) -> Result<Vec<ShowRow>> {
    std::fs::create_dir_all(cache_dir)?;
    let mut rows: Vec<ShowRow> = Vec::new();
    let mut page = 1;
    while page <= MAX_PAGES {
        let cache = cache_dir.join(format!("page_{page}.json"));
        let mut data = if force || !cache.exists() { None } else { read_page(&cache) };
        if data.is_none() {
            let _ = std::fs::remove_file(&cache);
            std::fs::write(&cache, ascii_json(&fetch_page(page)?))?;
            std::thread::sleep(PAUSE);
            let written: Value = serde_json::from_str(&std::fs::read_to_string(&cache)?)?;
            data = Some(written["data"]["Page"].clone());
        }
        let data = data.unwrap();
        rows.extend(data["media"].as_array().context("a page without media")?.iter().map(row_from_media));
        if i64::from(page) >= data["pageInfo"]["lastPage"].as_i64().context("a page without lastPage")? {
            break;
        }
        page += 1;
    }
    // The order can change between two pages, thus one anime can be on two pages. Each of its
    // rows gets the first place of the anime.
    let mut places: HashMap<String, i64> = HashMap::new();
    for (n, row) in rows.iter_mut().enumerate() {
        let place = *places.entry(row.id.clone()).or_insert(n as i64 + 1);
        row.popularity_place = Some(place);
    }
    Ok(rows)
}

/// `related_ids`: the AniList ids that the rows point to and do not have
pub fn related_ids(rows: &[&ShowRow]) -> BTreeSet<i64> {
    let have: HashSet<i64> = rows.iter().filter_map(|r| r.anilist_id).collect();
    let mut wanted = BTreeSet::new();
    for r in rows {
        wanted.extend(r.recommendations.iter().map(|(other, _)| *other));
        wanted.extend(r.relations.iter().copied());
    }
    wanted.retain(|i| !have.contains(i));
    wanted
}

/// `_read_media`: one cached anime, or None if the file is not correct, older than the query, or
/// (for an anime that is not finished) older than MEDIA_MAX_AGE_DAYS
fn read_media(cache: &Path) -> Option<Value> {
    let media: Value = serde_json::from_str(&std::fs::read_to_string(cache).ok()?).ok()?;
    if !media.is_object() || REQUIRED_KEYS.iter().any(|key| media.get(key).is_none()) {
        return None;
    }
    if anilist::unfinished(media.get("status").and_then(Value::as_str)) && age_days(cache) > MEDIA_MAX_AGE_DAYS {
        return None;
    }
    Some(media)
}

fn fetch_ids(ids: &[i64]) -> Result<Vec<Value>> {
    let data = with_retries(&format!("ids {:?}", &ids[..ids.len().min(3)]), || {
        let data = anilist::post(&id_query(), json!({ "ids": ids }), TIMEOUT)?;
        if !has_page(&data) {
            bail!("AniList returned no data for ids {:?}: {}", &ids[..ids.len().min(3)], data.to_string().chars().take(200).collect::<String>());
        }
        Ok(data)
    })?;
    Ok(data["data"]["Page"]["media"].as_array().cloned().unwrap_or_default())
}

/// `fetch_by_ids`: the rows of the anime with these AniList ids. Each anime has its own cache
/// file. AniList does not return adult anime or removed entries: the function keeps these ids in
/// media_absent.json, so that it does not ask for them again.
pub fn fetch_by_ids(cache_dir: &Path, ids: &BTreeSet<i64>, force: bool) -> Result<Vec<ShowRow>> {
    let media_dir = cache_dir.join("media");
    std::fs::create_dir_all(&media_dir)?;
    let absent_file = cache_dir.join("media_absent.json");
    let mut absent: BTreeSet<i64> = BTreeSet::new();
    if absent_file.exists() && !force {
        absent = std::fs::read_to_string(&absent_file).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
    }
    let media_file = |i: i64| -> PathBuf { media_dir.join(format!("{i}.json")) };
    let mut found: BTreeMap<i64, Value> = BTreeMap::new();
    let mut todo: Vec<i64> = Vec::new();
    for &i in ids {
        let media = if force { None } else { read_media(&media_file(i)) };
        match media {
            Some(media) => {
                found.insert(i, media);
            }
            None if !absent.contains(&i) => todo.push(i),
            None => {}
        }
    }
    for batch in todo.chunks(50) {
        let got: HashMap<i64, Value> = fetch_ids(batch)?.into_iter().filter_map(|m| Some((m["id"].as_i64()?, m))).collect();
        for &i in batch {
            match got.get(&i) {
                Some(media) => {
                    std::fs::write(media_file(i), ascii_json(media))?;
                    found.insert(i, media.clone());
                }
                None => {
                    absent.insert(i);
                }
            }
        }
        std::fs::write(&absent_file, ascii_json(&json!(absent)))?;
        std::thread::sleep(PAUSE);
    }
    if !todo.is_empty() {
        println!("  asked AniList for {} anime by id", todo.len());
    }
    Ok(found.values().map(row_from_media).collect())
}

/// `fetch_extras`: the rows of the anime with these ids, and of the anime that the catalog points
/// to. A new row can point to more anime, thus the function asks again, `rounds` times at most.
pub fn fetch_extras(cache_dir: &Path, pool: &[ShowRow], ids: &BTreeSet<i64>, force: bool) -> Result<Vec<ShowRow>> {
    let mut wanted = ids.clone();
    let mut extra: Vec<ShowRow> = Vec::new();
    for _ in 0..3 {
        let all: Vec<&ShowRow> = pool.iter().chain(extra.iter()).collect();
        let have: HashSet<i64> = all.iter().filter_map(|r| r.anilist_id).collect();
        wanted.extend(related_ids(&all));
        let todo: BTreeSet<i64> = wanted.iter().copied().filter(|i| !have.contains(i)).collect();
        let new_rows = fetch_by_ids(cache_dir, &todo, force)?;
        if new_rows.is_empty() {
            break;
        }
        extra.extend(new_rows);
    }
    Ok(extra)
}

/// JSON text with only ASCII characters, as the files of the cache had from the first version of
/// the app (`json.dumps` of Python)
pub fn ascii_json(value: &Value) -> String {
    let text = super::pyjson::dumps(value);
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let mut units = [0u16; 2];
            for unit in c.encode_utf16(&mut units) {
                out.push_str(&format!("\\u{unit:04x}"));
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_row_has_the_fields_of_an_anime() {
        let media = json!({
            "id": 21, "title": {"romaji": "One Piece", "english": null, "native": "ワンピース"},
            "format": "TV", "seasonYear": null, "startDate": {"year": 1999}, "status": "RELEASING", "episodes": null,
            "genres": ["Action"], "tags": [{"name": "Pirates", "rank": 95}, {"name": "Ensemble Cast", "rank": null}],
            "studios": {"nodes": [{"name": "Toei Animation"}]}, "description": "A<br>B", "averageScore": 88,
            "coverImage": {"medium": "https://img/21.jpg"},
            "relations": {"edges": [{"relationType": "SEQUEL", "node": {"id": 9, "type": "ANIME"}},
                                    {"relationType": "ADAPTATION", "node": {"id": 3, "type": "MANGA"}},
                                    {"relationType": "PREQUEL", "node": {"id": 5, "type": "ANIME"}}]},
            "recommendations": {"nodes": [{"rating": 40, "mediaRecommendation": {"id": 7, "type": "ANIME"}},
                                          {"rating": 0, "mediaRecommendation": {"id": 8, "type": "ANIME"}},
                                          {"rating": 3, "mediaRecommendation": null}]}
        });
        let r = row_from_media(&media);
        assert_eq!(r.id, "al:21");
        assert_eq!(r.title, "One Piece");
        assert_eq!(r.title_english.as_deref(), Some(""));
        assert_eq!(r.year, Some(json!(1999)));
        assert_eq!(r.format.as_deref(), Some("tv"));
        assert_eq!(r.tag_ranks, vec![95, 0]);
        assert_eq!(r.overview, "A\nB");
        assert_eq!(r.score, Some(json!(8.8)));
        assert_eq!(r.relations, vec![5, 9]);
        assert_eq!(r.recommendations, vec![(7, 40)]);
        assert_eq!(r.episodes, None);
        let no_score = row_from_media(&json!({"id": 1, "averageScore": 0}));
        assert_eq!(no_score.score, None);
    }

    #[test]
    fn the_cache_text_is_ascii() {
        let expected = format!("[\"{b}u30ef\", \"{b}u00e9\", \"{b}ud83d{b}ude00\"]", b = '\\');
        assert_eq!(ascii_json(&json!(["\u{30ef}", "\u{e9}", "\u{1f600}"])), expected);
    }
}
