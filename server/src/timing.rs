//! The command `rinrikun timing <database>`: the time of each stage of the engine, on the real
//! data. It reads only. Use it before and after a change that must make the server faster.
//!
//! Each value is the best of 3 runs, in milliseconds. The engine forgets the match and the tier
//! guess before each run of these two stages, thus each run computes them.

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::Instant;

use anyhow::{Result, bail};

use crate::api::RecommendOptions;
use crate::engine::{Engine, LeaveOut};
use crate::store::Store;

const RUNS: usize = 3;

/// The best time of some runs of the work, in milliseconds
fn best<T>(mut work: impl FnMut() -> T) -> f64 {
    (0..RUNS)
        .map(|_| {
            let started = Instant::now();
            std::hint::black_box(work());
            started.elapsed().as_secs_f64() * 1000.0
        })
        .fold(f64::INFINITY, f64::min)
}

pub fn run(args: &[String]) -> Result<()> {
    let [db] = args else { bail!("usage: rinrikun timing <database>") };
    let db = PathBuf::from(db);
    let line = |name: &str, ms: f64| println!("{name:<30}{ms:>10.1} ms");

    let started = Instant::now();
    let store = Store::open_read_only(&db)?;
    let engine = Engine::load(&store)?;
    line("load", started.elapsed().as_secs_f64() * 1000.0);

    line("match", best(|| {
        engine.clear_cache();
        engine.match_percent()
    }));
    line("tier guess", best(|| {
        engine.clear_cache();
        engine.tier_guess()
    }));
    // The match and the tier guess for the stages below: an answer of the server has them in the cache
    engine.match_percent();
    engine.tier_guess();

    let owned = engine.owned_franchises();
    let skip: HashSet<usize> = owned.clone();
    line("candidates", best(|| engine.candidates(&skip, &owned)));
    let cand = engine.candidates(&skip, &owned);
    line("content (candidates)", best(|| engine.content(&cand, &[]).scores));
    line("predicted tier (candidates)", best(|| engine.predicted_tier(&cand, LeaveOut::Nothing)));

    // The default list of the Recommendations tab, and the list with more variety. The functions
    // without the cache: the API keeps a list until the data changes, and runs 2 and 3 would only
    // read the cache.
    let list = |diverse: bool| RecommendOptions { k: 40, seed: None, diverse, new_only: true, usual: true, links: true };
    line("list", best(|| engine.compute_recommend(&list(false)).map(|v| v.to_string().len())));
    line("list with variety", best(|| engine.compute_recommend(&list(true)).map(|v| v.to_string().len())));
    line("steps", best(|| engine.compute_steps(40, true, true, true)));
    line("vector map JSON", best(|| serde_json::to_vec(&engine.api_vector_map()).map(|v| v.len())));
    line("titles JSON", best(|| serde_json::to_vec(&engine.api_titles()).map(|v| v.len())));
    Ok(())
}
