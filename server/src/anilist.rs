//! Requests to the GraphQL API of AniList, with the rules of anime_vec/anilist_pull.py.

use std::time::Duration;

use anyhow::{Context, Result};
use serde_json::{Value, json};

/// The address of the API
const URL: &str = "https://graphql.anilist.co";
/// The User-Agent of the Python build (UA in anilist_pull.py)
const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
/// The states of an anime that is not finished: its data changes with time
pub const UNFINISHED: [&str; 3] = ["NOT_YET_RELEASED", "RELEASING", "HIATUS"];

/// `_post`: send one query and return the answer. An HTTP error status is an error, as in urllib.
pub fn post(query: &str, variables: Value, timeout: Duration) -> Result<Value> {
    let agent: ureq::Agent = ureq::Agent::config_builder().timeout_global(Some(timeout)).build().into();
    let body = json!({"query": query, "variables": variables}).to_string();
    let mut answer = agent
        .post(URL)
        .header("Content-Type", "application/json")
        .header("User-Agent", UA)
        .send(body)
        .context("no answer from AniList")?;
    let text = answer.body_mut().with_config().limit(64 << 20).read_to_string().context("the answer of AniList is not complete")?;
    serde_json::from_str(&text).context("the answer of AniList is not JSON")
}

/// True if the status of an anime is one of UNFINISHED
pub fn unfinished(status: Option<&str>) -> bool {
    status.is_some_and(|s| UNFINISHED.contains(&s))
}
