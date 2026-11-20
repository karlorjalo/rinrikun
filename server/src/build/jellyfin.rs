//! The shows of the Jellyfin library.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::Path;
use std::sync::LazyLock;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use regex::Regex;
use serde_json::Value;

use super::ShowRow;
use super::pyjson::Ordered;

const JELLYFIN: &str = "http://localhost:8096";
const FIELDS: &str = "Genres,Tags,Studios,CommunityRating,ProviderIds,ProductionYear,Overview,DateCreated";

/// The key and the user of the Jellyfin API: from secrets.json in the project folder, else from
/// the environment variables JELLYFIN_API_KEY and JELLYFIN_USER_ID
struct Secrets {
    api_key: String,
    user_id: String,
}

fn secrets(root: &Path) -> Result<Secrets> {
    let file = root.join("secrets.json");
    let data: Value = if file.exists() {
        serde_json::from_str(&std::fs::read_to_string(&file)?).with_context(|| format!("{} is not JSON", file.display()))?
    } else {
        Value::Null
    };
    let get = |key: &str, env: &str| -> Option<String> {
        match data.get(key) {
            Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
            Some(Value::String(_)) | Some(Value::Null) => None,
            Some(other) => Some(other.to_string()),
            None => std::env::var(env).ok().filter(|v| !v.is_empty()),
        }
    };
    let api_key = get("jellyfin_api_key", "JELLYFIN_API_KEY");
    let user_id = get("jellyfin_user_id", "JELLYFIN_USER_ID");
    let mut missing = Vec::new();
    if api_key.is_none() {
        missing.push("jellyfin_api_key");
    }
    if user_id.is_none() {
        missing.push("jellyfin_user_id");
    }
    if !missing.is_empty() {
        bail!("missing secrets: {missing:?}: set the environment variables or secrets.json");
    }
    Ok(Secrets { api_key: api_key.unwrap(), user_id: user_id.unwrap() })
}

/// The provider ids of the items in the order of Jellyfin. A `Value` sorts the keys of an
/// object, but the build writes the provider ids in their order.
#[derive(serde::Deserialize)]
struct OrderedItems {
    #[serde(rename = "Items")]
    items: Vec<OrderedItem>,
}

#[derive(serde::Deserialize)]
struct OrderedItem {
    #[serde(rename = "Id", default)]
    id: Option<Value>,
    #[serde(rename = "ProviderIds", default)]
    provider_ids: Option<Ordered>,
}

/// The provider ids of each item, by the id of the item
pub type ProviderIds = HashMap<String, Ordered>;

/// The items of the answer of Jellyfin, and their provider ids in their order
pub fn parse_items(text: &str) -> Result<(Vec<Value>, ProviderIds)> {
    let data: Value = serde_json::from_str(text).context("the answer of Jellyfin is not JSON")?;
    let items = data["Items"].as_array().cloned().context("the answer of Jellyfin has no Items")?;
    let ordered: OrderedItems = serde_json::from_str(text)?;
    let providers = ordered.items.into_iter().filter_map(|item| Some((text_of(item.id.as_ref())?, item.provider_ids?))).collect();
    Ok((items, providers))
}

fn items(secrets: &Secrets, item_types: &str, fields: &str) -> Result<(Vec<Value>, ProviderIds)> {
    let url = format!(
        "{JELLYFIN}/Items?api_key={}&UserId={}&Recursive=true&IncludeItemTypes={item_types}&Fields={fields}&Limit=5000",
        secrets.api_key, secrets.user_id
    );
    let agent: ureq::Agent = ureq::Agent::config_builder().timeout_global(Some(Duration::from_secs(120))).build().into();
    let text = agent.get(&url).call().context("no answer from Jellyfin")?.body_mut().with_config().limit(256 << 20).read_to_string()?;
    parse_items(&text)
}

/// `seasons_by_series`: the season numbers that the library has for each series id
pub fn seasons_by_series(season_items: &[Value]) -> HashMap<String, Vec<i64>> {
    let mut out: HashMap<String, BTreeSet<i64>> = HashMap::new();
    for s in season_items {
        // A virtual season has no files. A season without a number cannot be matched.
        let Some(number) = s.get("IndexNumber").and_then(Value::as_i64) else { continue };
        if s.get("LocationType").and_then(Value::as_str) == Some("Virtual") {
            continue;
        }
        let Some(series) = s.get("SeriesId").and_then(Value::as_str) else { continue };
        out.entry(series.to_string()).or_default().insert(number);
    }
    out.into_iter().map(|(k, v)| (k, v.into_iter().collect())).collect()
}

fn text_of(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::String(s) => Some(s.clone()),
        Value::Null => None,
        other => Some(other.to_string()),
    }
}

/// `merge_same_items`: one item for each show. Two items with the same type and the same TMDB id
/// are one show: the item that the library got first stays, and it gets the ids of the others.
pub fn merge_same_items(items: &[Value]) -> Vec<(Value, Vec<String>)> {
    let mut sorted: Vec<&Value> = items.iter().collect();
    // A stable sort: an item without a date has the empty text
    sorted.sort_by_key(|item| item.get("DateCreated").and_then(Value::as_str).unwrap_or("").to_string());
    let mut first: BTreeMap<(Option<String>, String), usize> = BTreeMap::new();
    let mut out: Vec<(Value, Vec<String>)> = Vec::new();
    for item in sorted {
        let tmdb = text_of(item.get("ProviderIds").and_then(|p| p.get("Tmdb"))).filter(|t| !t.is_empty());
        if let Some(tmdb) = tmdb {
            let key = (text_of(item.get("Type")), tmdb);
            if let Some(&at) = first.get(&key) {
                if let Some(id) = text_of(item.get("Id")) {
                    out[at].1.push(id);
                }
                continue;
            }
            first.insert(key, out.len());
        }
        out.push((item.clone(), Vec::new()));
    }
    out
}

static FOLDER_ID: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s*\[(tmdbid|tvdbid|imdbid)-[^\]]+\]").unwrap());
static FOLDER_YEAR: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s*\((19|20)\d{2}\)\s*$").unwrap());

/// `clean_name`: the title without the suffix of its folder, for example "Title (2015) [tmdbid-86561]"
pub fn clean_name(name: &str) -> String {
    let cleaned = FOLDER_ID.replace_all(name, "");
    let cleaned = FOLDER_YEAR.replace_all(&cleaned, "").trim().to_string();
    if cleaned.is_empty() { name.to_string() } else { cleaned }
}

fn strings(value: Option<&Value>) -> Vec<String> {
    value.and_then(Value::as_array).map(|a| a.iter().filter_map(|v| text_of(Some(v))).collect()).unwrap_or_default()
}

/// `row_from_item`: the row of one library show. `provider` is the ProviderIds object in its order.
pub fn row_from_item(item: &Value, provider: Option<&Ordered>, merged: &[String], seasons: Vec<i64>) -> ShowRow {
    let id = text_of(item.get("Id")).unwrap_or_default();
    let name = clean_name(item.get("Name").and_then(Value::as_str).unwrap_or(""));
    let provider: Ordered = provider.cloned().unwrap_or_default();
    ShowRow {
        id: format!("jf:{id}"),
        source: "library".into(),
        title: name.clone(),
        title_native: name,
        year: item.get("ProductionYear").cloned().filter(|v| !v.is_null()),
        format: item.get("Type").and_then(Value::as_str).map(str::to_lowercase).filter(|f| !f.is_empty()),
        genres: strings(item.get("Genres")),
        tags: strings(item.get("Tags")),
        studios: item.get("Studios").and_then(Value::as_array).map(|a| a.iter().filter_map(|s| text_of(s.get("Name"))).collect()).unwrap_or_default(),
        overview: item.get("Overview").and_then(Value::as_str).unwrap_or("").to_string(),
        score: item.get("CommunityRating").cloned().filter(|v| !v.is_null()),
        owned: 1,
        tmdbid: text_of(item.get("ProviderIds").and_then(|p| p.get("Tmdb"))),
        poster: Some(format!("{JELLYFIN}/Items/{id}/Images/Primary")),
        provider_ids: Some(Ordered(provider.0.into_iter().map(|(k, v)| (k.to_lowercase(), v)).collect())),
        seasons,
        added_at: text_of(item.get("DateCreated")),
        merged_ids: merged.iter().map(|other| format!("jf:{other}")).collect(),
        ..ShowRow::default()
    }
}

/// `fetch_library`: the rows of the library
pub fn fetch_library(root: &Path) -> Result<Vec<ShowRow>> {
    let secrets = secrets(root)?;
    let seasons = seasons_by_series(&items(&secrets, "Season", "ProviderIds")?.0);
    let (shows, providers) = items(&secrets, "Series,Movie", FIELDS)?;
    let mut rows = Vec::new();
    for (item, merged) in merge_same_items(&shows) {
        let id = text_of(item.get("Id")).unwrap_or_default();
        let mut own: BTreeSet<i64> = seasons.get(&id).cloned().unwrap_or_default().into_iter().collect();
        for other in &merged {
            own.extend(seasons.get(other).cloned().unwrap_or_default());
        }
        rows.push(row_from_item(&item, providers.get(&id), &merged, own.into_iter().collect()));
    }
    Ok(rows)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn clean_name_removes_the_folder_suffix() {
        assert_eq!(clean_name("Title (2015) [tmdbid-86561]"), "Title");
        assert_eq!(clean_name("Title [tvdbid-1] [imdbid-tt2]"), "Title");
        assert_eq!(clean_name("(2015)"), "(2015)");
        assert_eq!(clean_name("Plain"), "Plain");
    }

    #[test]
    fn two_items_of_one_show_are_one_row_with_the_seasons_of_both() {
        let items = vec![
            json!({"Id": "b", "Type": "Series", "DateCreated": "2024-02-01", "ProviderIds": {"Tmdb": "7"}}),
            json!({"Id": "a", "Type": "Series", "DateCreated": "2024-01-01", "ProviderIds": {"Tmdb": "7"}}),
            json!({"Id": "c", "Type": "Movie", "DateCreated": "2024-01-05", "ProviderIds": {"Tmdb": "7"}}),
            json!({"Id": "d", "Type": "Series", "ProviderIds": {}}),
        ];
        let merged = merge_same_items(&items);
        let ids: Vec<(&str, Vec<String>)> = merged.iter().map(|(i, m)| (i["Id"].as_str().unwrap(), m.clone())).collect();
        assert_eq!(ids, vec![("d", vec![]), ("a", vec!["b".to_string()]), ("c", vec![])]);
        let seasons = seasons_by_series(&[
            json!({"SeriesId": "a", "IndexNumber": 1}),
            json!({"SeriesId": "b", "IndexNumber": 2}),
            json!({"SeriesId": "a", "IndexNumber": 3, "LocationType": "Virtual"}),
            json!({"SeriesId": "a"}),
        ]);
        assert_eq!(seasons["a"], vec![1]);
        assert_eq!(seasons["b"], vec![2]);
    }

    #[test]
    fn a_row_keeps_the_provider_ids_in_their_order_with_lower_case_keys() {
        let text = r#"{"Items": [{"Id": "x1", "Name": "Show (2020)", "Type": "Series", "ProviderIds": {"Tvdb": "5", "Tmdb": "6"}, "Studios": [{"Name": "S"}]}]}"#;
        let (items, providers) = parse_items(text).unwrap();
        let row = row_from_item(&items[0], providers.get("x1"), &["x2".to_string()], vec![1, 2]);
        assert_eq!(row.title, "Show");
        assert_eq!(row.format.as_deref(), Some("series"));
        assert_eq!(super::super::pyjson::dumps_ordered(row.provider_ids.as_ref().unwrap()), r#"{"tvdb": "5", "tmdb": "6"}"#);
        assert_eq!(row.tmdbid.as_deref(), Some("6"));
        assert_eq!(row.merged_ids, vec!["jf:x2"]);
        assert_eq!(row.poster.as_deref(), Some("http://localhost:8096/Items/x1/Images/Primary"));
    }
}
