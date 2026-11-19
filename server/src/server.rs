//! The command `rinrikun serve`: the HTTP server with the GET routes of serve.py, the old page at
//! `/` and the new page at `/next`. In this phase it only reads: a request that changes data gets
//! the answer 405. When the Python server changes the database, this server loads the data again.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::{Component, Path, PathBuf};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, SystemTime};

use anyhow::{Context, Result, bail};
use axum::Json;
use axum::Router;
use axum::body::Body;
use axum::extract::{Path as UrlPath, Query, Request, State};
use axum::http::{HeaderValue, Method, StatusCode, header};
use axum::response::{IntoResponse, Redirect, Response};
use axum::routing::get;
use serde_json::{Map, Value, json};
use tower::ServiceExt;
use tower_http::compression::CompressionLayer;
use tower_http::services::ServeFile;

use crate::api::RecommendOptions;
use crate::engine::Engine;
use crate::frames;
use crate::lists::Random;
use crate::store::Store;

/// The browser asks again each time if a file of a page changed (see PAGE_HEADERS in anime_vec/pages.py)
const NO_CACHE: &str = "no-cache";
/// A file of the new page with a hash in its name can stay in the browser
const IMMUTABLE: &str = "public, max-age=31536000, immutable";
/// The largest number of shows in one request for pictures
const FRAMES_MAX: usize = 50;

struct App {
    engine: RwLock<Arc<Engine>>,
    random: Mutex<Random>,
    root: PathBuf,
    db: PathBuf,
}

type Shared = Arc<App>;
type Params = Query<HashMap<String, String>>;

/// An error answer with the shape of FastAPI: {"detail": text}
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

/// A yes/no value of a query, with the words that FastAPI accepts
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

fn engine(app: &App) -> Arc<Engine> {
    app.engine.read().unwrap().clone()
}

/// Run work of the engine on a thread for blocking work: the computation of a list takes some time
async fn compute<T: Send + 'static>(app: &Shared, work: impl FnOnce(&Engine) -> T + Send + 'static) -> T {
    let engine = engine(app);
    tokio::task::spawn_blocking(move || work(&engine)).await.expect("the work of the engine stopped")
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
    compute(&app, move |e| {
        if seed.as_ref().is_some_and(|s| !e.pos.contains_key(s)) {
            return Err(not_found("unknown seed"));
        }
        let options = RecommendOptions { k, seed: seed.as_deref(), diverse, new_only, usual, links };
        e.api_recommend(&options).map(Json).map_err(|err| ApiError(StatusCode::INTERNAL_SERVER_ERROR, err.to_string()))
    })
    .await
}

async fn steps(State(app): State<Shared>, Query(p): Params) -> Answer {
    let k = whole(&p, "k", 40, 1, 100)?;
    let new_only = flag(&p, "new_only", true)?;
    let usual = choice(&p, "kinds", "all", &["all", "usual"])? == "usual";
    let links = flag(&p, "links", true)?;
    Ok(Json(compute(&app, move |e| e.api_steps(k, usual, links, new_only)).await))
}

/// GET /api/frames: the pictures from the files of the Python server. A show without a file is not in the answer.
async fn pictures(State(app): State<Shared>, Query(p): Params) -> Answer {
    let ids = p.get("ids").filter(|ids| ids.len() <= 2000).cloned().ok_or_else(|| invalid("ids"))?;
    let cache = app.root.join("anilist_cache").join("frames");
    compute(&app, move |e| {
        let mut wanted: Vec<(String, i64)> = Vec::new();
        for id in ids.split(',') {
            let Some(&j) = e.pos.get(id) else { continue };
            if let Some(anilist) = e.public_row(j)["anilist_id"].as_i64() {
                if !wanted.iter().any(|(w, _)| w == id) {
                    wanted.push((id.to_string(), anilist));
                }
            }
        }
        if wanted.len() > FRAMES_MAX {
            return Err(ApiError(StatusCode::BAD_REQUEST, format!("too many shows: the limit is {FRAMES_MAX}")));
        }
        let out: Map<String, Value> = wanted.into_iter().filter_map(|(id, anilist)| frames::read(&cache, anilist).map(|p| (id, p))).collect();
        Ok(Json(Value::Object(out)))
    })
    .await
}

/// A path below a folder, without ".." and without a root
fn below(folder: &Path, rest: &str) -> Option<PathBuf> {
    let rest = Path::new(rest);
    rest.components().all(|c| matches!(c, Component::Normal(_))).then(|| folder.join(rest))
}

/// Give a file with its type, with conditional requests, and with the cache header
async fn send_file(path: PathBuf, cache: &'static str, request: Request) -> Response {
    match ServeFile::new(&path).oneshot(request).await {
        Ok(response) => {
            let mut response = response.map(Body::new);
            response.headers_mut().insert(header::CACHE_CONTROL, HeaderValue::from_static(cache));
            response
        }
        Err(_) => not_found("Not Found").into_response(),
    }
}

async fn old_page(State(app): State<Shared>, request: Request) -> Response {
    send_file(app.root.join("ui").join("index.html"), NO_CACHE, request).await
}

async fn favicon(State(app): State<Shared>, request: Request) -> Response {
    send_file(app.root.join("ui").join("favicon.svg"), NO_CACHE, request).await
}

async fn old_page_file(State(app): State<Shared>, UrlPath(rest): UrlPath<String>, request: Request) -> Response {
    match below(&app.root.join("ui"), &rest).filter(|p| p.is_file()) {
        Some(path) => send_file(path, NO_CACHE, request).await,
        None => not_found("Not Found").into_response(),
    }
}

/// The new page is a single-page app: an address without a file is a tab, and it gets the page
/// file. A missing file with a file ending is a missing file. See NewPage in anime_vec/pages.py.
async fn new_page(app: &App, rest: &str, request: Request) -> Response {
    let build = app.root.join("web").join("build");
    if !build.join("index.html").is_file() {
        return not_found("Not Found").into_response();
    }
    let rest = rest.trim_start_matches('/');
    if let Some(path) = below(&build, rest).filter(|p| p.is_file()) {
        let cache = if rest.starts_with("_app/immutable/") { IMMUTABLE } else { NO_CACHE };
        return send_file(path, cache, request).await;
    }
    if rest.rsplit('/').next().is_some_and(|name| name.contains('.')) {
        return not_found("Not Found").into_response();
    }
    send_file(build.join("index.html"), NO_CACHE, request).await
}

async fn new_page_root(State(app): State<Shared>, request: Request) -> Response {
    new_page(&app, "", request).await
}

async fn new_page_file(State(app): State<Shared>, UrlPath(rest): UrlPath<String>, request: Request) -> Response {
    new_page(&app, &rest, request).await
}

async fn fallback(method: Method) -> ApiError {
    if method == Method::GET || method == Method::HEAD {
        not_found("Not Found")
    } else {
        ApiError(StatusCode::METHOD_NOT_ALLOWED, "this server only reads: change the data through the Python server".into())
    }
}

fn router(app: Shared) -> Router {
    Router::new()
        .route("/api/profile", get(|s| simple(s, Engine::api_profile)))
        .route("/api/vector-map", get(|s| simple(s, Engine::api_vector_map)))
        .route("/api/vector-map/match", get(|s| simple(s, Engine::api_map_match)))
        .route("/api/weights", get(|s| simple(s, Engine::api_weights)))
        .route("/api/review-queue", get(review_queue))
        .route("/api/ratings", get(|s| simple(s, Engine::api_ratings)))
        .route("/api/watched", get(|s| simple(s, Engine::api_watched)))
        .route("/api/dismissed", get(|s| simple(s, Engine::api_dismissed)))
        .route("/api/discover", get(discover))
        .route("/api/interest", get(|s| simple(s, Engine::api_watch_list)))
        .route("/api/interest/results", get(|s| simple(s, Engine::api_interest_results)))
        .route("/api/frames", get(pictures))
        .route("/api/similar", get(similar))
        .route("/api/show/{*id}", get(show))
        .route("/api/recommend", get(recommend))
        .route("/api/recommend/steps", get(steps))
        .route("/api/rec-log", get(|s| simple(s, Engine::api_rec_log)))
        .route("/api/shows", get(|s| simple(s, Engine::api_titles)))
        // The Python server passes a poster of the library on from Jellyfin. This server does not.
        .route("/api/poster/{*id}", get(|| async { not_found("no poster") }))
        .route("/", get(old_page))
        .route("/favicon.ico", get(favicon))
        .route("/ui/{*path}", get(old_page_file))
        .route("/next", get(|| async { Redirect::temporary("/next/") }))
        .route("/next/", get(new_page_root))
        .route("/next/{*path}", get(new_page_file))
        .fallback(fallback)
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
            // Wait until the Python server ends its writes
            std::thread::sleep(Duration::from_secs(1));
            if stamp(&app.db) != now {
                continue;
            }
            let started = std::time::Instant::now();
            match load(&app.db) {
                Ok(engine) => {
                    *app.engine.write().unwrap() = Arc::new(engine);
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
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--listen" => addresses.push(rest.next().context("--listen needs an address")?.parse().context("the address is not valid")?),
            "--root" => root = Some(PathBuf::from(rest.next().context("--root needs a folder")?)),
            other if db.is_none() && !other.starts_with("--") => db = Some(PathBuf::from(other)),
            other => bail!("unknown argument {other}"),
        }
    }
    let db = db.context("usage: rinrikun serve <database> [--listen address]... [--root folder]")?;
    let db = std::fs::canonicalize(&db).with_context(|| format!("no database at {}", db.display()))?;
    if addresses.is_empty() {
        addresses.push("127.0.0.1:8775".parse()?);
    }
    // The folder of the project: it has ui/, web/build/ and anilist_cache/. By default it is the folder of the database.
    let root = root.unwrap_or_else(|| db.parent().map(Path::to_path_buf).unwrap_or_default());
    let started = std::time::Instant::now();
    let engine = load(&db)?;
    eprintln!("{} shows loaded in {:.2?}", engine.len(), started.elapsed());
    let app = Arc::new(App { engine: RwLock::new(Arc::new(engine)), random: Mutex::new(Random::from_time()), root, db });
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
