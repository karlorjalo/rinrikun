//! The pictures of a show for the Discover deck: frames of its episodes and of its trailer. The
//! rules are the rules of anime_vec/frames.py. In this phase the Rust server does not ask AniList:
//! it reads the files that the Python server keeps in anilist_cache/frames.

use std::path::Path;

use serde_json::{Value, json};

/// The number of frames from the episodes, and from the trailer
const EPISODE_FRAMES: usize = 3;
const TRAILER_FRAMES: usize = 3;

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

/// The pictures of an anime from the file of the Python server, or None if there is no file
pub fn read(cache: &Path, anilist_id: i64) -> Option<Value> {
    let text = std::fs::read_to_string(cache.join(format!("{anilist_id}.json"))).ok()?;
    let media: Value = serde_json::from_str(&text).ok()?;
    media.is_object().then(|| pictures_from_media(&media))
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

    #[test]
    fn an_absent_anime_has_no_pictures() {
        let p = pictures_from_media(&json!({"id": 5, "absent": true}));
        assert_eq!(p, json!({"frames": [], "trailer": null, "banner": null}));
    }
}
