//! The command `rinrikun reference`: write the results of the Rust engine as JSON, for the
//! comparison with the Python engine (server/compare/python_reference.py writes the same keys).

use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use serde_json::{Map, Value, json};

use crate::api::RecommendOptions;
use crate::engine::{Engine, display_similarity};
use crate::lists::Random;
use crate::math::round1;
use crate::store::Store;

/// Some shows of the user and some shows of the catalog: the same choice as the Python script
fn seeds(engine: &Engine) -> Vec<String> {
    let mine = engine.owned_idx.iter().step_by(37).take(6).map(|&i| engine.rows[i].id.clone());
    let other: Vec<usize> = engine.unique_rows().into_iter().filter(|&i| !engine.rows[i].owned).collect();
    let other = other.into_iter().step_by(997).take(6).map(|i| engine.rows[i].id.clone());
    mine.chain(other).collect()
}

/// The answers of the API functions: the same keys as `api` of the Python script
fn api(engine: &Engine) -> Result<Value> {
    let all_seeds = seeds(engine);
    let first_seed = all_seeds.last().cloned();
    let options = |seed, diverse, new_only, usual, links| RecommendOptions { k: 40, seed, diverse, new_only, usual, links };
    let mut recommend = Map::new();
    recommend.insert("usual".into(), engine.api_recommend(&options(None, false, true, true, true))?);
    recommend.insert("all, no links".into(), engine.api_recommend(&options(None, false, true, false, false))?);
    recommend.insert("diverse".into(), engine.api_recommend(&options(None, true, true, true, true))?);
    recommend.insert("sequels".into(), engine.api_recommend(&options(None, false, false, true, true))?);
    recommend.insert("seed".into(), engine.api_recommend(&options(first_seed.as_deref(), false, true, true, true))?);
    let mut steps = Map::new();
    steps.insert("usual".into(), engine.api_steps(40, true, true, true));
    steps.insert("all, no links".into(), engine.api_steps(40, false, false, true));
    let mut show = Map::new();
    let mut similar = Map::new();
    for seed in &all_seeds {
        show.insert(seed.clone(), engine.api_show(seed).unwrap_or(Value::Null));
        similar.insert(seed.clone(), engine.api_similar(seed, 24)?);
    }
    let mut pool: Vec<String> =
        engine.discover(usize::MAX, &mut Random::new(1)).into_iter().map(|(j, _)| engine.rows[j].id.clone()).collect();
    pool.sort();
    Ok(json!({
        "profile": engine.api_profile(),
        "titles": engine.api_titles(),
        "ratings": engine.api_ratings(),
        "watched": engine.api_watched(),
        "dismissed": engine.api_dismissed(),
        "review_unrated": engine.api_review_queue(true),
        "review_all": engine.api_review_queue(false),
        "interest": engine.api_watch_list(),
        "interest_results": engine.api_interest_results(),
        "rec_log": engine.api_rec_log(),
        "recommend": recommend,
        "steps": steps,
        "show": show,
        "similar": similar,
        "map": engine.api_vector_map(),
        "map_match": engine.api_map_match(),
        "discover_pool": pool,
        "weights": engine.api_weights(),
    }))
}

pub fn run(args: &[String]) -> Result<()> {
    if args.len() != 2 {
        bail!("usage: rinrikun reference <database> <out.json>");
    }
    let started = std::time::Instant::now();
    let store = Store::open_read_only(&PathBuf::from(&args[0]))?;
    let engine = Engine::load(&store)?;
    let loaded = started.elapsed();
    let matches = engine.match_percent();
    let matched = started.elapsed();
    let guesses = engine.tier_guess();
    let n = engine.len();
    let ids: Vec<&str> = engine.rows.iter().map(|r| r.id.as_str()).collect();
    let mut similar = Map::new();
    for seed in seeds(&engine) {
        let list = engine.similar_to(&seed, 24)?;
        similar.insert(seed, list.iter().map(|&(j, s)| json!([engine.rows[j].id, display_similarity(s)])).collect());
    }
    let out = json!({
        "ids": ids,
        "owned_idx": engine.owned_idx,
        "franchise": (0..n).map(|i| engine.franchise(i)).collect::<Vec<_>>(),
        "entry": engine.franchise_names.iter().zip(&engine.entry_row)
            .filter_map(|(f, e)| e.map(|j| (f.clone(), Value::from(engine.rows[j].id.clone()))))
            .collect::<Map<_, _>>(),
        "tier": engine.rows.iter().map(|r| r.tier.clone()).collect::<Vec<_>>(),
        "match": matches.iter().map(|&m| if m.is_nan() { Value::Null } else { Value::from(round1(m as f64)) }).collect::<Vec<_>>(),
        "match_raw": matches.iter().map(|&m| if m.is_nan() { Value::Null } else { Value::from(m as f64) }).collect::<Vec<_>>(),
        "guess": guesses.iter().map(|&g| if g.is_nan() { Value::Null } else { Value::from(g as f64) }).collect::<Vec<_>>(),
        "tier_guess": engine.rows.iter().zip(&guesses)
            .map(|(r, &g)| if r.tier.is_some() { Value::Null } else { Engine::guess_letter(g).map(Value::from).unwrap_or(Value::Null) })
            .collect::<Vec<_>>(),
        "similar": similar,
        "api": api(&engine)?,
    });
    std::fs::write(&args[1], serde_json::to_string(&out)?).with_context(|| format!("cannot write {}", args[1]))?;
    eprintln!("{}: {n} rows; load {:.2?}, match {:.2?}, all {:.2?}", args[1], loaded, matched - loaded, started.elapsed());
    Ok(())
}
