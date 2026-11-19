//! The command `rinrikun serve`: the HTTP server of the app. It answers the API (/api/...), and it
//! passes each other request on to the page server, a Node server that renders the page (node
//! web/build). Thus the browser sees one address.
//!
//! The server changes the data of the user (tiers, watched marks, removed shows, answers). With
//! --read-only it only reads: a request that changes data gets the answer 405. When a different
//! program (the weekly build) changes the database, the server loads the data again.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, SystemTime};

use anyhow::{Context, Result, bail};
use axum::Json;
use axum::Router;
use axum::body::Body;
use axum::extract::{Path as UrlPath, Query, Request, State};
use axum::http::{HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use serde_json::{Map, Value, json};
use tower_http::compression::CompressionLayer;

use crate::api::RecommendOptions;
use crate::changes::Refused;
use crate::engine::Engine;
use crate::frames;
use crate::lists::Random;
use crate::store::{Store, truthy};

/// The headers of a request that go on to the page server, and the headers of its answer that come back
const REQUEST_HEADERS: [&str; 6] = ["accept", "accept-language", "cookie", "if-none-match", "if-modified-since", "user-agent"];
const ANSWER_HEADERS: [&str; 7] = ["content-type", "cache-control", "etag", "last-modified", "location", "set-cookie", "vary"];
/// The largest number of shows in one request for pictures
const FRAMES_MAX: usize = 50;

struct App {
    engine: RwLock<Engine>,
    /// The database with the right to change it. With --read-only there is none.
    store: Option<Mutex<Store>>,
    /// The time and the size of the database files after the last change of this server. The
    /// watcher does not load the data again for a change of this server.
    own_stamp: Mutex<Vec<Option<(SystemTime, u64)>>>,
    random: Mutex<Random>,
    root: PathBuf,
    db: PathBuf,
    /// The page server, and the client for its requests
    web: String,
    client: ureq::Agent,
    /// The client for the posters of Jellyfin. It follows redirects, and an error status is an error.
    posters: ureq::Agent,
}

type Shared = Arc<App>;
type Params = Query<HashMap<String, String>>;

/// An error answer: {"detail": text}
struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({ "detail": self.1 }))).into_response()
    }
}

type Answer = std::result::Result<Json<Value>, ApiError>;

fn not_found(text: &str) -> ApiError {
    ApiError(StatusCode::NOT_FOUND, text.into())
}

fn invalid(name: &str) -> ApiError {
    ApiError(StatusCode::UNPROCESSABLE_ENTITY, format!("the value of {name} is not valid"))
}

/// A yes/no value of a query: true, 1, yes, on or false, 0, no, off
fn flag(p: &HashMap<String, String>, name: &str, default: bool) -> std::result::Result<bool, ApiError> {
    match p.get(name).map(|v| v.to_ascii_lowercase()) {
        None => Ok(default),
        Some(v) if ["true", "1", "yes", "on"].contains(&v.as_str()) => Ok(true),
        Some(v) if ["false", "0", "no", "off"].contains(&v.as_str()) => Ok(false),
        Some(_) => Err(invalid(name)),
    }
}

/// A whole number of a query, from `low` to `high`
fn whole(p: &HashMap<String, String>, name: &str, default: usize, low: usize, high: usize) -> std::result::Result<usize, ApiError> {
    match p.get(name) {
        None => Ok(default),
        Some(v) => v.trim().parse::<usize>().ok().filter(|n| (low..=high).contains(n)).ok_or_else(|| invalid(name)),
    }
}

fn choice<'a>(p: &'a HashMap<String, String>, name: &str, default: &'a str, allowed: &[&str]) -> std::result::Result<&'a str, ApiError> {
    let value = p.get(name).map(String::as_str).unwrap_or(default);
    if allowed.contains(&value) { Ok(value) } else { Err(invalid(name)) }
}

/// Run work of the engine on a thread for blocking work: the computation of a list takes some time
async fn compute<T: Send + 'static>(app: &Shared, work: impl FnOnce(&Engine) -> T + Send + 'static) -> T {
    let app = app.clone();
    tokio::task::spawn_blocking(move || {
        let engine = app.engine.read().unwrap();
        work(&engine)
    })
    .await
    .expect("the work of the engine stopped")
}

/// The answer for a change that failed: 400 for a change that the user cannot make, else 500
fn change_error(error: anyhow::Error) -> ApiError {
    match error.downcast_ref::<Refused>() {
        Some(refused) => ApiError(StatusCode::BAD_REQUEST, refused.to_string()),
        None => ApiError(StatusCode::INTERNAL_SERVER_ERROR, format!("{error:#}")),
    }
}

/// The answer of a server with --read-only to a change
fn read_only() -> ApiError {
    ApiError(StatusCode::METHOD_NOT_ALLOWED, "this server only reads: start it without --read-only to change the data".into())
}

/// Run a change of the data: one change at a time, while no request reads the engine. A server
/// with --read-only gives 405.
async fn change(app: &Shared, work: impl FnOnce(&mut Engine, &mut Store) -> Result<Value> + Send + 'static) -> Answer {
    let app = app.clone();
    tokio::task::spawn_blocking(move || {
        let Some(store) = &app.store else {
            return Err(read_only());
        };
        let mut store = store.lock().unwrap();
        let mut engine = app.engine.write().unwrap();
        let result = work(&mut engine, &mut store);
        *app.own_stamp.lock().unwrap() = stamp(&app.db);
        result.map(Json).map_err(change_error)
    })
    .await
    .expect("the change of the data stopped")
}

/// The id of the show of a change. A missing id or an id that is not in the data gives 404. A
/// server with --read-only gives 405 first.
fn known_id(app: &App, id: Option<&str>) -> std::result::Result<String, ApiError> {
    if app.store.is_none() {
        return Err(read_only());
    }
    match id {
        Some(id) if !id.is_empty() && app.engine.read().unwrap().pos.contains_key(id) => Ok(id.to_string()),
        _ => Err(not_found("unknown show id")),
    }
}

/// A yes/no value of a change: a missing value has the default, and an empty or zero value is false
fn yes(body: &Value, name: &str, default: bool) -> bool {
    body.get(name).map(truthy).unwrap_or(default)
}

/// POST /api/weights {id, tier}: give a show a tier. A tier of null takes the tier away.
async fn post_weights(State(app): State<Shared>, Json(body): Json<Value>) -> Answer {
    let id = known_id(&app, body["id"].as_str())?;
    let tier = body["tier"].as_str().map(str::to_string);
    change(&app, move |e, s| e.set_show_tier(s, &id, tier.as_deref())).await
}

/// DELETE /api/weights?id=...: take the tier away
async fn delete_weights(State(app): State<Shared>, Query(p): Params) -> Answer {
    let id = p.get("id").ok_or_else(|| invalid("id"))?;
    let id = known_id(&app, Some(id))?;
    change(&app, move |e, s| e.set_show_tier(s, &id, None)).await
}

/// POST /api/watched {id, watched}: mark a show as watched, or take the mark away
async fn post_watched(State(app): State<Shared>, Json(body): Json<Value>) -> Answer {
    let id = known_id(&app, body["id"].as_str())?;
    let watched = yes(&body, "watched", true);
    change(&app, move |e, s| {
        let owned = e.set_watched(s, &id, watched)?;
        Ok(json!({"id": id, "watched": watched, "owned": owned}))
    })
    .await
}

/// POST /api/dismissed {id, dismissed}: remove a show from the recommendations, or put it back
async fn post_dismissed(State(app): State<Shared>, Json(body): Json<Value>) -> Answer {
    let id = known_id(&app, body["id"].as_str())?;
    let dismissed = yes(&body, "dismissed", true);
    change(&app, move |e, s| {
        e.set_dismissed(s, &id, dismissed)?;
        Ok(json!({"id": id, "dismissed": dismissed}))
    })
    .await
}

/// POST /api/interest {id, value, source}: the answer of the user for a show. A value of null deletes the answer.
async fn post_interest(State(app): State<Shared>, Json(body): Json<Value>) -> Answer {
    let id = known_id(&app, body["id"].as_str())?;
    let value = body.get("value").filter(|v| !v.is_null()).map(truthy);
    let source = if body["source"].as_str() == Some("deck") { "deck" } else { "page" };
    change(&app, move |e, s| {
        e.set_interest(s, &id, value, source)?;
        let interest = e.interest.get(&id).copied();
        Ok(json!({"id": id, "interest": interest, "dismissed": e.refused(&id) as i64, "counts": e.interest_counts()}))
    })
    .await
}

async fn simple(State(app): State<Shared>, work: fn(&Engine) -> Value) -> Json<Value> {
    Json(compute(&app, work).await)
}

async fn review_queue(State(app): State<Shared>, Query(p): Params) -> Answer {
    let unrated_only = flag(&p, "unrated_only", false)?;
    Ok(Json(compute(&app, move |e| e.api_review_queue(unrated_only)).await))
}

async fn discover(State(app): State<Shared>, Query(p): Params) -> Answer {
    let count = whole(&p, "count", 12, 1, 50)?;
    let seed = app.random.lock().unwrap().unit().to_bits();
    Ok(Json(compute(&app, move |e| e.api_discover(count, &mut Random::new(seed))).await))
}

async fn similar(State(app): State<Shared>, Query(p): Params) -> Answer {
    let id = p.get("id").cloned().ok_or_else(|| invalid("id"))?;
    let k = whole(&p, "k", 24, 1, 100)?;
    compute(&app, move |e| {
        if !e.pos.contains_key(&id) {
            return Err(not_found("unknown id"));
        }
        e.api_similar(&id, k).map(Json).map_err(|err| ApiError(StatusCode::INTERNAL_SERVER_ERROR, err.to_string()))
    })
    .await
}

async fn show(State(app): State<Shared>, UrlPath(id): UrlPath<String>) -> Answer {
    compute(&app, move |e| e.api_show(&id).map(Json).ok_or_else(|| not_found("unknown id"))).await
}

async fn recommend(State(app): State<Shared>, Query(p): Params) -> Answer {
    let k = whole(&p, "k", 20, 1, 100)?;
    let seed = p.get("seed").filter(|s| !s.is_empty()).cloned();
    let diverse = choice(&p, "mode", "hybrid", &["hybrid", "diverse"])? == "diverse";
    let new_only = flag(&p, "new_only", false)?;
    let usual = choice(&p, "kinds", "all", &["all", "usual"])? == "usual";
    let links = flag(&p, "links", true)?;
    let has_seed = seed.is_some();
    let list = compute(&app, move |e| {
        if seed.as_ref().is_some_and(|s| !e.pos.contains_key(s)) {
            return Err(not_found("unknown seed"));
        }
        let options = RecommendOptions { k, seed: seed.as_deref(), diverse, new_only, usual, links };
        e.api_recommend(&options).map(Json).map_err(|err| ApiError(StatusCode::INTERNAL_SERVER_ERROR, err.to_string()))
    })
    .await?;
    // The log of a list without a seed, with its formula (the API of the Recommendations tab shows it)
    if !has_seed && app.store.is_some() {
        let shows = list.0.clone();
        let kinds = format!("{}{}", if usual { "usual" } else { "all" }, if links { "" } else { ", no links" });
        let _ = change(&app, move |e, s| e.log_list(s, &shows, &kinds).map(|_| Value::Null)).await?;
    }
    Ok(list)
}

async fn steps(State(app): State<Shared>, Query(p): Params) -> Answer {
    let k = whole(&p, "k", 40, 1, 100)?;
    let new_only = flag(&p, "new_only", true)?;
    let usual = choice(&p, "kinds", "all", &["all", "usual"])? == "usual";
    let links = flag(&p, "links", true)?;
    Ok(Json(compute(&app, move |e| e.api_steps(k, usual, links, new_only)).await))
}

/// GET /api/frames: the pictures of some shows, by the id of the show. The server asks AniList for
/// a show without a good file, and it keeps the answer in a file (see frames.rs). A show is not
/// in the result if it has no AniList entry, or if AniList gave no answer.
async fn pictures(State(app): State<Shared>, Query(p): Params) -> Answer {
    let ids = p.get("ids").filter(|ids| ids.len() <= 2000).cloned().ok_or_else(|| invalid("ids"))?;
    let wanted = compute(&app, move |e| {
        let mut wanted: Vec<(String, i64)> = Vec::new();
        for id in ids.split(',') {
            let Some(&j) = e.pos.get(id) else { continue };
            if let Some(anilist) = e.public_row(j)["anilist_id"].as_i64() {
                if !wanted.iter().any(|(w, _)| w == id) {
                    wanted.push((id.to_string(), anilist));
                }
            }
        }
        wanted
    })
    .await;
    if wanted.len() > FRAMES_MAX {
        return Err(ApiError(StatusCode::BAD_REQUEST, format!("too many shows: the limit is {FRAMES_MAX}")));
    }
    // The request to AniList runs without the lock of the engine: a change of the data does not wait for it
    let cache = app.root.join("anilist_cache").join("frames");
    let out = tokio::task::spawn_blocking(move || {
        let mut found = frames::get_pictures(&cache, wanted.iter().map(|(_, anilist)| *anilist));
        let out: Map<String, Value> = wanted.into_iter().filter_map(|(id, anilist)| found.remove(&anilist).map(|p| (id, p))).collect();
        out
    })
    .await
    .expect("the request for the pictures stopped");
    Ok(Json(Value::Object(out)))
}

/// GET /api/poster/{id}: pass the poster of a library show on from Jellyfin.
///
/// The address of a poster of the library is on the Jellyfin server. A browser on a different
/// computer frequently cannot reach that server, but this server can. Only a library show without
/// an AniList entry uses this address: the other shows use the poster from AniList.
async fn poster(State(app): State<Shared>, UrlPath(id): UrlPath<String>) -> Response {
    let address = compute(&app, move |e| {
        let r = &e.rows[*e.pos.get(&id)?];
        let poster = r.data.get("poster")?.as_str().filter(|p| !p.is_empty())?;
        (r.source == "library").then(|| poster.to_string())
    })
    .await;
    let Some(address) = address else { return not_found("no poster").into_response() };
    // A poster in the interface is small, thus ask Jellyfin for a small picture
    let url = format!("{address}{}maxWidth=400&quality=90", if address.contains('?') { '&' } else { '?' });
    let client = app.posters.clone();
    let answer = tokio::task::spawn_blocking(move || -> std::result::Result<(String, Vec<u8>), ureq::Error> {
        let mut answer = client.get(&url).call()?;
        // The type without its parameters. Without a type: text/plain.
        let kind = answer
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.split(';').next())
            .map(|v| v.trim().to_ascii_lowercase())
            .filter(|v| v.contains('/'))
            .unwrap_or_else(|| "text/plain".into());
        let body = answer.body_mut().with_config().limit(32 << 20).read_to_vec()?;
        Ok((kind, body))
    })
    .await;
    match answer {
        Ok(Ok((kind, body))) => {
            let mut response = Response::new(Body::from(body));
            let headers = response.headers_mut();
            headers.insert(header::CONTENT_TYPE, HeaderValue::from_str(&kind).unwrap_or(HeaderValue::from_static("text/plain")));
            headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("max-age=86400"));
            response
        }
        _ => ApiError(StatusCode::BAD_GATEWAY, "the library server did not give the poster".into()).into_response(),
    }
}

/// Pass a request on to the page server, and give back its answer (status, headers, body)
fn forward(client: &ureq::Agent, url: &str, headers: &[(String, String)]) -> std::result::Result<(u16, Vec<(String, String)>, Vec<u8>), ureq::Error> {
    // This server compresses the answer itself
    let mut request = client.get(url).header("accept-encoding", "identity");
    for (name, value) in headers {
        request = request.header(name.as_str(), value.as_str());
    }
    let mut answer = request.call()?;
    let status = answer.status().as_u16();
    let mut out = Vec::new();
    for name in ANSWER_HEADERS {
        for value in answer.headers().get_all(name) {
            if let Ok(value) = value.to_str() {
                out.push((name.to_string(), value.to_string()));
            }
        }
    }
    let body = answer.body_mut().with_config().limit(64 << 20).read_to_vec()?;
    Ok((status, out, body))
}

/// A page: the page server renders it
async fn page(app: &App, request: Request) -> Response {
    let path = request.uri().path_and_query().map(|p| p.as_str().to_string()).unwrap_or_else(|| "/".into());
    let url = format!("{}{}", app.web.trim_end_matches('/'), path);
    let headers: Vec<(String, String)> = REQUEST_HEADERS
        .iter()
        .filter_map(|name| request.headers().get(*name).and_then(|v| v.to_str().ok()).map(|v| (name.to_string(), v.to_string())))
        .collect();
    let client = app.client.clone();
    let answer = tokio::task::spawn_blocking(move || forward(&client, &url, &headers)).await;
    let Ok(Ok((status, headers, body))) = answer else {
        return (StatusCode::BAD_GATEWAY, "The page server does not run. Start it with scripts/restart_servers.ps1.").into_response();
    };
    let mut response = Response::new(Body::from(body));
    *response.status_mut() = StatusCode::from_u16(status).unwrap_or(StatusCode::BAD_GATEWAY);
    for (name, value) in headers {
        if let (Ok(name), Ok(value)) = (header::HeaderName::try_from(name), HeaderValue::from_str(&value)) {
            response.headers_mut().append(name, value);
        }
    }
    response
}

/// Each address that has no route of this server. A GET request outside /api is a page. An
/// unknown address of the API gets 404, and a change of a page gets 405.
async fn fallback(State(app): State<Shared>, request: Request) -> Response {
    let path = request.uri().path();
    if path == "/api" || path.starts_with("/api/") {
        return not_found("Not Found").into_response();
    }
    if request.method() == Method::GET || request.method() == Method::HEAD {
        return page(&app, request).await;
    }
    wrong_method().await.into_response()
}

/// /next and each address below it: the address of the page while it was new. It now goes to the
/// same address without /next (a permanent redirect).
async fn old_address(request: Request) -> Response {
    let rest = request.uri().path().strip_prefix("/next").unwrap_or("");
    let rest = if rest.is_empty() { "/" } else { rest };
    let query = request.uri().query().map(|q| format!("?{q}")).unwrap_or_default();
    match HeaderValue::from_str(&format!("{rest}{query}")) {
        Ok(location) => (StatusCode::PERMANENT_REDIRECT, [(header::LOCATION, location)]).into_response(),
        Err(_) => not_found("Not Found").into_response(),
    }
}

/// A known address with a method that it does not have
async fn wrong_method() -> ApiError {
    ApiError(StatusCode::METHOD_NOT_ALLOWED, "Method Not Allowed".into())
}

fn router(app: Shared) -> Router {
    Router::new()
        .route("/api/profile", get(|s| simple(s, Engine::api_profile)))
        .route("/api/vector-map", get(|s| simple(s, Engine::api_vector_map)))
        .route("/api/vector-map/match", get(|s| simple(s, Engine::api_map_match)))
        .route("/api/weights", get(|s| simple(s, Engine::api_weights)).post(post_weights).delete(delete_weights))
        .route("/api/review-queue", get(review_queue))
        .route("/api/ratings", get(|s| simple(s, Engine::api_ratings)))
        .route("/api/watched", get(|s| simple(s, Engine::api_watched)).post(post_watched))
        .route("/api/dismissed", get(|s| simple(s, Engine::api_dismissed)).post(post_dismissed))
        .route("/api/discover", get(discover))
        .route("/api/interest", get(|s| simple(s, Engine::api_watch_list)).post(post_interest))
        .route("/api/interest/results", get(|s| simple(s, Engine::api_interest_results)))
        .route("/api/frames", get(pictures))
        .route("/api/similar", get(similar))
        .route("/api/show/{*id}", get(show))
        .route("/api/recommend", get(recommend))
        .route("/api/recommend/steps", get(steps))
        .route("/api/rec-log", get(|s| simple(s, Engine::api_rec_log)))
        .route("/api/shows", get(|s| simple(s, Engine::api_titles)))
        .route("/api/poster/{*id}", get(poster))
        // A wildcard does not match an empty rest: "/next/" needs its own route
        .route("/next", get(old_address))
        .route("/next/", get(old_address))
        .route("/next/{*rest}", get(old_address))
        .fallback(fallback)
        .method_not_allowed_fallback(wrong_method)
        .layer(CompressionLayer::new())
        .with_state(app)
}

/// The time and the size of the database files: a change of them is a change of the data
fn stamp(db: &Path) -> Vec<Option<(SystemTime, u64)>> {
    ["", "-wal", "-journal"]
        .iter()
        .map(|end| {
            let mut name = db.as_os_str().to_owned();
            name.push(end);
            std::fs::metadata(PathBuf::from(name)).ok().and_then(|m| Some((m.modified().ok()?, m.len())))
        })
        .collect()
}

/// Load the engine, and compute the match and the tier guess: almost each answer needs them
fn load(db: &Path) -> Result<Engine> {
    let store = Store::open_read_only(db)?;
    let engine = Engine::load(&store)?;
    engine.match_percent();
    engine.tier_guess();
    Ok(engine)
}

/// Load the data again a short time after a change of the database
fn watch(app: Shared) {
    std::thread::spawn(move || {
        let mut seen = stamp(&app.db);
        loop {
            std::thread::sleep(Duration::from_secs(3));
            let now = stamp(&app.db);
            if now == seen {
                continue;
            }
            if now == *app.own_stamp.lock().unwrap() {
                // A change of this server: the engine has it already
                seen = now;
                continue;
            }
            // Wait until the other program ends its writes
            std::thread::sleep(Duration::from_secs(1));
            if stamp(&app.db) != now {
                continue;
            }
            let started = std::time::Instant::now();
            match load(&app.db) {
                Ok(engine) => {
                    *app.engine.write().unwrap() = engine;
                    eprintln!("the database changed: data loaded again in {:.2?}", started.elapsed());
                }
                Err(error) => eprintln!("the database changed, but the load failed: {error:#}"),
            }
            seen = now;
        }
    });
}

pub fn run(args: &[String]) -> Result<()> {
    let mut db: Option<PathBuf> = None;
    let mut addresses: Vec<SocketAddr> = Vec::new();
    let mut root: Option<PathBuf> = None;
    let mut web: Option<String> = None;
    let mut write = true;
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--listen" => addresses.push(rest.next().context("--listen needs an address")?.parse().context("the address is not valid")?),
            "--root" => root = Some(PathBuf::from(rest.next().context("--root needs a folder")?)),
            "--web" => web = Some(rest.next().context("--web needs an address")?.clone()),
            "--read-only" => write = false,
            other if db.is_none() && !other.starts_with("--") => db = Some(PathBuf::from(other)),
            other => bail!("unknown argument {other}"),
        }
    }
    let db = db.context("usage: rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--read-only]")?;
    // The page server
    let web = web.or_else(|| std::env::var("RINRIKUN_WEB").ok()).unwrap_or_else(|| "http://127.0.0.1:8780".into());
    let client: ureq::Agent = ureq::Agent::config_builder()
        .max_redirects(0)
        .max_redirects_will_error(false)
        .http_status_as_error(false)
        .timeout_global(Some(Duration::from_secs(30)))
        .build()
        .into();
    let db = std::fs::canonicalize(&db).with_context(|| format!("no database at {}", db.display()))?;
    if addresses.is_empty() {
        addresses.push("127.0.0.1:8775".parse()?);
    }
    // The folder of the project: it has anilist_cache/ (the pictures of the Discover deck). By default it is the folder of the database.
    let root = root.unwrap_or_else(|| db.parent().map(Path::to_path_buf).unwrap_or_default());
    let started = std::time::Instant::now();
    let engine = load(&db)?;
    eprintln!("{} shows loaded in {:.2?}", engine.len(), started.elapsed());
    let store = if write { Some(Mutex::new(Store::open_write(&db)?)) } else { None };
    eprintln!("{}", if write { "this server changes the data" } else { "this server only reads" });
    let own_stamp = Mutex::new(stamp(&db));
    let posters: ureq::Agent = ureq::Agent::config_builder().timeout_global(Some(Duration::from_secs(15))).build().into();
    let app = Arc::new(App { engine: RwLock::new(engine), store, own_stamp, random: Mutex::new(Random::from_time()), root, db, web, client, posters });
    watch(app.clone());
    let runtime = tokio::runtime::Builder::new_multi_thread().enable_all().build()?;
    runtime.block_on(async move {
        let mut servers = Vec::new();
        for address in &addresses {
            let listener = tokio::net::TcpListener::bind(address).await.with_context(|| format!("cannot listen on {address}"))?;
            eprintln!("listening on http://{address}");
            servers.push(tokio::spawn(axum::serve(listener, router(app.clone())).into_future()));
        }
        for server in servers {
            server.await??;
        }
        Ok(())
    })
}
