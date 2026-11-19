//! The pictures of a show for the Discover deck: frames of its episodes and of its trailer. The
//! rules are the rules of anime_vec/frames.py.
//!
//! The catalog has only the poster of an anime. AniList has more pictures: one picture for each
//! episode that a streaming site has, the trailer, and a banner. The server asks AniList when the
//! deck shows its cards, and it keeps each answer in a file of anilist_cache/frames. The Python
//! server uses the same files.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

use anyhow::{Result, bail};
use serde_json::{Value, json};

use crate::anilist;

const QUERY: &str = "query ($ids: [Int]) { Page(perPage: 50) { media(id_in: $ids, type: ANIME) { \
                     id status bannerImage trailer { id site thumbnail } streamingEpisodes { title thumbnail } } } }";
/// The largest number of anime in one request to AniList
const BATCH: usize = 50;
/// The number of frames from the episodes, and from the trailer
const EPISODE_FRAMES: usize = 3;
const TRAILER_FRAMES: usize = 3;
/// The file of an anime is good for this number of days
const MAX_AGE_DAYS: f64 = 30.0;
/// An anime that is not finished, or an anime without pictures, can get pictures later. Its file
/// is good for this number of days.
const SHORT_MAX_AGE_DAYS: f64 = 7.0;
/// The time to wait for the answer of AniList. The deck works without the pictures, thus the time is short.
const TIMEOUT: Duration = Duration::from_secs(15);
/// Only one thread asks AniList at a time. A second request for the same anime then finds the file.
static LOCK: Mutex<()> = Mutex::new(());

/// `_address`: the text if it is a safe address of a picture
fn address(value: Option<&Value>) -> Option<String> {
    let text = value?.as_str()?;
    (text.starts_with("https://") && !text.chars().any(|c| "\"'<> \\\n\r\t".contains(c))).then(|| text.to_string())
}

/// The number of an episode title "Episode 12 - ...", as the text of the number
fn episode_number(title: &str) -> Option<String> {
    let rest = title.trim_start();
    if rest.len() < 7 || !rest[..7].eq_ignore_ascii_case("episode") {
        return None;
    }
    let after = &rest[7..];
    let digits = after.trim_start();
    if digits.len() == after.len() {
        // "Episode" needs a space before the number
        return None;
    }
    let whole: String = digits.chars().take_while(|c| c.is_ascii_digit()).collect();
    if whole.is_empty() {
        return None;
    }
    let tail = &digits[whole.len()..];
    if let Some(fraction) = tail.strip_prefix('.') {
        let part: String = fraction.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !part.is_empty() {
            return Some(format!("{whole}.{part}"));
        }
    }
    Some(whole)
}

fn id_like(text: &str, extra: &str, low: usize, high: usize) -> bool {
    (low..=high).contains(&text.len()) && text.chars().all(|c| c.is_ascii_alphanumeric() || extra.contains(c))
}

/// `pictures_from_media`: the pictures of one anime from the answer of AniList
pub fn pictures_from_media(media: &Value) -> Value {
    let mut frames: Vec<Value> = Vec::new();
    // (no number, number, position, picture, label)
    let mut episodes: Vec<(bool, f64, usize, String, String)> = Vec::new();
    for (position, episode) in media.get("streamingEpisodes").and_then(Value::as_array).into_iter().flatten().enumerate() {
        let Some(picture) = address(episode.get("thumbnail")) else { continue };
        let title = match episode.get("title") {
            Some(Value::String(s)) => s.clone(),
            Some(Value::Null) | None => String::new(),
            Some(other) => other.to_string(),
        };
        match episode_number(&title) {
            Some(number) => episodes.push((false, number.parse().unwrap_or(0.0), position, picture, format!("Episode {number}"))),
            None => {
                let label: String = title.chars().take(40).collect();
                episodes.push((true, 0.0, position, picture, if label.is_empty() { "Episode".into() } else { label }));
            }
        }
    }
    episodes.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)).then(a.2.cmp(&b.2)));
    let mut seen = std::collections::HashSet::new();
    for (_, _, _, picture, label) in episodes {
        if !seen.insert(picture.clone()) {
            continue;
        }
        frames.push(json!({"small": picture, "large": picture, "label": label}));
        if frames.len() >= EPISODE_FRAMES {
            break;
        }
    }
    let trailer = media.get("trailer").filter(|t| t.is_object());
    let site = trailer.and_then(|t| t.get("site")).and_then(Value::as_str);
    let video = match trailer.and_then(|t| t.get("id")) {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) | None => String::new(),
        Some(other) => other.to_string(),
    };
    let mut link = None;
    if site == Some("youtube") && id_like(&video, "_-", 6, 20) {
        link = Some(format!("https://www.youtube.com/watch?v={video}"));
        for n in 1..=TRAILER_FRAMES {
            frames.push(json!({
                "small": format!("https://i.ytimg.com/vi/{video}/mq{n}.jpg"),
                "large": format!("https://i.ytimg.com/vi/{video}/maxres{n}.jpg"),
                "label": "Trailer",
            }));
        }
    } else if site == Some("dailymotion") && id_like(&video, "", 4, 20) {
        link = Some(format!("https://www.dailymotion.com/video/{video}"));
        if let Some(picture) = address(trailer.and_then(|t| t.get("thumbnail"))) {
            frames.push(json!({"small": picture, "large": picture, "label": "Trailer"}));
        }
    }
    json!({"frames": frames, "trailer": link, "banner": address(media.get("bannerImage"))})
}

fn file(cache: &Path, anilist_id: i64) -> PathBuf {
    cache.join(format!("{anilist_id}.json"))
}

/// `_read`: the answer of AniList for one anime from its file. None if there is no good file: no
/// file, a file that is not correct, or (without `any_age`) a file that is too old.
fn read_media(cache: &Path, anilist_id: i64, any_age: bool) -> Option<Value> {
    let path = file(cache, anilist_id);
    let media: Value = serde_json::from_str(&std::fs::read_to_string(&path).ok()?).ok()?;
    let modified = std::fs::metadata(&path).ok()?.modified().ok()?;
    if !media.is_object() {
        return None;
    }
    if any_age {
        return Some(media);
    }
    let age_days = SystemTime::now().duration_since(modified).map(|d| d.as_secs_f64()).unwrap_or(0.0) / 86400.0;
    let short = crate::store::truthy(&media["absent"])
        || anilist::unfinished(media["status"].as_str())
        || pictures_from_media(&media)["frames"].as_array().is_none_or(|f| f.is_empty());
    (age_days <= if short { SHORT_MAX_AGE_DAYS } else { MAX_AGE_DAYS }).then_some(media)
}

/// `_fetch`: ask AniList for the pictures of some anime
fn fetch(ids: &[i64]) -> Result<Vec<Value>> {
    let data = anilist::post(QUERY, json!({ "ids": ids }), TIMEOUT)?;
    let Some(page) = data.get("data").and_then(|d| d.get("Page")).filter(|p| crate::store::truthy(p)) else {
        let text: String = data.to_string().chars().take(200).collect();
        bail!("AniList returned no data for ids {:?}: {text}", &ids[..ids.len().min(3)]);
    };
    Ok(page["media"].as_array().cloned().unwrap_or_default())
}

/// `get_pictures`: the pictures of the anime with these AniList ids, by the id.
///
/// The function asks AniList only for the anime that have no good file. If AniList does not
/// answer, an anime with an old file gets its old pictures, and an anime without a file is not in
/// the result. The function gives no error for this: the caller works without the pictures.
pub fn get_pictures(cache: &Path, anilist_ids: impl IntoIterator<Item = i64>) -> BTreeMap<i64, Value> {
    let wanted: std::collections::BTreeSet<i64> = anilist_ids.into_iter().collect();
    let mut out = BTreeMap::new();
    let mut todo = Vec::new();
    for i in wanted {
        match read_media(cache, i, false) {
            Some(media) => {
                out.insert(i, pictures_from_media(&media));
            }
            None => todo.push(i),
        }
    }
    if todo.is_empty() {
        return out;
    }
    let _only_one = LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    for part in todo.chunks(BATCH) {
        let mut batch = Vec::new();
        for &i in part {
            // A different thread wrote the file in the time that this thread waited
            match read_media(cache, i, false) {
                Some(media) => {
                    out.insert(i, pictures_from_media(&media));
                }
                None => batch.push(i),
            }
        }
        if batch.is_empty() {
            continue;
        }
        let got: BTreeMap<i64, Value> = match fetch(&batch) {
            Ok(media) => media.into_iter().filter_map(|m| Some((m["id"].as_i64()?, m))).collect(),
            Err(error) => {
                eprintln!("WARNING no pictures from AniList for {} anime ({error:#})", batch.len());
                for &i in &batch {
                    if let Some(media) = read_media(cache, i, true) {
                        out.insert(i, pictures_from_media(&media));
                    }
                }
                continue;
            }
        };
        if let Err(error) = std::fs::create_dir_all(cache) {
            eprintln!("WARNING cannot make the folder {}: {error}", cache.display());
        }
        for &i in &batch {
            // AniList does not return an adult anime or a removed entry. The file keeps this
            // result, so that the server does not ask again each time.
            let media = got.get(&i).cloned().unwrap_or_else(|| json!({"id": i, "absent": true}));
            if let Err(error) = std::fs::write(file(cache, i), media.to_string()) {
                eprintln!("WARNING cannot write the pictures of {i}: {error}");
            }
            out.insert(i, pictures_from_media(&media));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn episodes_come_in_the_order_of_their_numbers_and_the_trailer_after_them() {
        let media = json!({
            "streamingEpisodes": [
                {"title": "Episode 10 - Late", "thumbnail": "https://a/10.jpg"},
                {"title": "Teaser", "thumbnail": "https://a/t.jpg"},
                {"title": "episode 2 - Second", "thumbnail": "https://a/2.jpg"},
                {"title": "Episode 1.5", "thumbnail": "https://a/1.5.jpg"},
                {"title": "Episode 3", "thumbnail": "http://unsafe/3.jpg"}
            ],
            "trailer": {"site": "youtube", "id": "abcDEF_12"},
            "bannerImage": "https://a/banner.jpg"
        });
        let p = pictures_from_media(&media);
        let labels: Vec<&str> = p["frames"].as_array().unwrap().iter().map(|f| f["label"].as_str().unwrap()).collect();
        assert_eq!(labels, ["Episode 1.5", "Episode 2", "Episode 10", "Trailer", "Trailer", "Trailer"]);
        assert_eq!(p["trailer"], "https://www.youtube.com/watch?v=abcDEF_12");
        assert_eq!(p["frames"][3]["large"], "https://i.ytimg.com/vi/abcDEF_12/maxres1.jpg");
        assert_eq!(p["banner"], "https://a/banner.jpg");
    }

    /// Write a file of the cache with the given age in days
    fn cache_file(cache: &Path, id: i64, media: &Value, days: u64) {
        std::fs::write(file(cache, id), media.to_string()).unwrap();
        let time = SystemTime::now() - Duration::from_secs(days * 86400);
        std::fs::File::options().write(true).open(file(cache, id)).unwrap().set_modified(time).unwrap();
    }

    #[test]
    fn a_file_with_frames_is_good_for_30_days_and_a_file_without_frames_for_7_days() {
        let cache = std::env::temp_dir().join(format!("rinrikun-frames-test-{}", std::process::id()));
        std::fs::create_dir_all(&cache).unwrap();
        let with_frames = json!({"id": 1, "status": "FINISHED", "trailer": {"site": "youtube", "id": "abcDEF_12"}});
        let releasing = json!({"id": 2, "status": "RELEASING", "trailer": {"site": "youtube", "id": "abcDEF_12"}});
        let absent = json!({"id": 3, "absent": true});
        let cases = [(1, &with_frames, 20, true), (1, &with_frames, 31, false), (2, &releasing, 6, true), (2, &releasing, 8, false), (3, &absent, 6, true), (3, &absent, 8, false)];
        for (id, media, days, good) in cases {
            cache_file(&cache, id, media, days);
            assert_eq!(read_media(&cache, id, false).is_some(), good, "anime {id}, {days} days");
            assert!(read_media(&cache, id, true).is_some(), "any age: anime {id}");
        }
        assert!(read_media(&cache, 99, true).is_none());
        std::fs::remove_dir_all(&cache).unwrap();
    }

    #[test]
    fn an_absent_anime_has_no_pictures() {
        let p = pictures_from_media(&json!({"id": 5, "absent": true}));
        assert_eq!(p, json!({"frames": [], "trailer": null, "banner": null}));
    }
}
