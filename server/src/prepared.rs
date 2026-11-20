//! Large answers of the API that stay the same until the data changes (the map, the titles).
//!
//! The server makes the JSON and its gzip bytes one time for each version of the data, not for
//! each request. The ETag is a hash of the JSON: the browser asks with If-None-Match, and an
//! answer that did not change is a 304 without a body.

use std::io::Write;

use axum::body::Body;
use axum::http::{HeaderMap, HeaderValue, StatusCode, header};
use axum::response::Response;
use flate2::Compression;
use flate2::write::GzEncoder;
use serde_json::Value;

/// A large answer that stays the same until the data changes: the JSON, its gzip bytes and its ETag
pub struct Prepared {
    pub json: Vec<u8>,
    pub gzip: Vec<u8>,
    pub etag: String,
}

impl Prepared {
    pub fn new(value: &Value) -> Prepared {
        let json = serde_json::to_vec(value).expect("a JSON value always gives text");
        let mut encoder = GzEncoder::new(Vec::with_capacity(json.len() / 4), Compression::default());
        encoder.write_all(&json).expect("gzip into memory does not fail");
        let gzip = encoder.finish().expect("gzip into memory does not fail");
        let etag = format!("\"{}\"", sha1_smol::Sha1::from(&json).digest());
        Prepared { json, gzip, etag }
    }
}

/// The request has an If-None-Match with this ETag (or "*")
fn not_changed(etag: &str, request: &HeaderMap) -> bool {
    request.get_all(header::IF_NONE_MATCH).iter().filter_map(|v| v.to_str().ok()).flat_map(|v| v.split(',')).any(|tag| {
        let tag = tag.trim();
        tag == "*" || tag.strip_prefix("W/").unwrap_or(tag) == etag
    })
}

/// The request accepts gzip: "gzip" (or "*") is in Accept-Encoding without the quality 0
fn accepts_gzip(request: &HeaderMap) -> bool {
    request.get_all(header::ACCEPT_ENCODING).iter().filter_map(|v| v.to_str().ok()).flat_map(|v| v.split(',')).any(|item| {
        let mut parts = item.split(';');
        let name = parts.next().unwrap_or("").trim().to_ascii_lowercase();
        let quality = parts.find_map(|p| p.trim().strip_prefix("q=").and_then(|q| q.trim().parse::<f64>().ok())).unwrap_or(1.0);
        (name == "gzip" || name == "*") && quality > 0.0
    })
}

/// The answer to a request: 304 if the browser has this version, else the gzip bytes or the JSON
pub fn answer(prepared: &Prepared, request: &HeaderMap) -> Response {
    let (status, body, gzip) = if not_changed(&prepared.etag, request) {
        (StatusCode::NOT_MODIFIED, Vec::new(), false)
    } else if accepts_gzip(request) {
        (StatusCode::OK, prepared.gzip.clone(), true)
    } else {
        (StatusCode::OK, prepared.json.clone(), false)
    };
    let mut response = Response::new(Body::from(body));
    *response.status_mut() = status;
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_TYPE, HeaderValue::from_static("application/json"));
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    headers.insert(header::VARY, HeaderValue::from_static("accept-encoding"));
    if let Ok(etag) = HeaderValue::from_str(&prepared.etag) {
        headers.insert(header::ETAG, etag);
    }
    if gzip {
        headers.insert(header::CONTENT_ENCODING, HeaderValue::from_static("gzip"));
    }
    response
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, HeaderValue, StatusCode, header};
    use serde_json::json;
    use std::io::Read;

    fn map(tier: &str) -> Value {
        json!({"points": [{"id": "al:1", "tier": tier}, {"id": "al:2", "tier": null}]})
    }

    async fn body(response: Response) -> Vec<u8> {
        axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap().to_vec()
    }

    fn request(pairs: &[(header::HeaderName, &str)]) -> HeaderMap {
        let mut headers = HeaderMap::new();
        for (name, value) in pairs {
            headers.insert(name.clone(), HeaderValue::from_str(value).unwrap());
        }
        headers
    }

    #[test]
    fn prepared_etag_changes_with_body() {
        let a = Prepared::new(&map("S"));
        let b = Prepared::new(&map("A"));
        assert_ne!(a.etag, b.etag);
        assert_eq!(a.etag, Prepared::new(&map("S")).etag);
        assert!(a.etag.starts_with('"') && a.etag.ends_with('"'));
    }

    #[tokio::test]
    async fn answer_gives_304_for_same_etag() {
        let prepared = Prepared::new(&map("S"));
        let response = answer(&prepared, &request(&[(header::IF_NONE_MATCH, &prepared.etag)]));
        assert_eq!(response.status(), StatusCode::NOT_MODIFIED);
        assert_eq!(response.headers()[header::ETAG], prepared.etag.as_str());
        assert!(body(response).await.is_empty());
    }

    #[tokio::test]
    async fn answer_gives_full_body_for_other_etag() {
        let prepared = Prepared::new(&map("S"));
        let old = Prepared::new(&map("A"));
        let response = answer(&prepared, &request(&[(header::IF_NONE_MATCH, &old.etag)]));
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(body(response).await, prepared.json);
    }

    #[tokio::test]
    async fn answer_gives_gzip_when_accepted() {
        let prepared = Prepared::new(&map("S"));
        let response = answer(&prepared, &request(&[(header::ACCEPT_ENCODING, "gzip, deflate, br")]));
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()[header::CONTENT_ENCODING], "gzip");
        assert_eq!(response.headers()[header::CONTENT_TYPE], "application/json");
        assert_eq!(response.headers()[header::CACHE_CONTROL], "no-cache");
        assert_eq!(response.headers()[header::ETAG], prepared.etag.as_str());
        let mut unpacked = Vec::new();
        flate2::read::GzDecoder::new(&body(response).await[..]).read_to_end(&mut unpacked).unwrap();
        assert_eq!(unpacked, prepared.json);
    }

    #[tokio::test]
    async fn answer_gives_json_without_gzip() {
        let prepared = Prepared::new(&map("S"));
        for accept in ["identity", "gzip;q=0", "br"] {
            let response = answer(&prepared, &request(&[(header::ACCEPT_ENCODING, accept)]));
            assert!(response.headers().get(header::CONTENT_ENCODING).is_none(), "{accept}");
            assert_eq!(body(response).await, prepared.json, "{accept}");
        }
    }
}
