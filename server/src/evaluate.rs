//! The command `rinrikun evaluate`: the offline test of the recommendations. It opens the
//! database read-only.
//!
//!   rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]
//!
//! The hidden franchise test: hide a franchise that the user rated (the engine forgets that the
//! user owns and rated its shows), compute the list of new franchises, and find the place of the
//! hidden franchise in it. The test assumes that a show with the tier S or A is a show that the
//! user wants. It cannot tell if an unowned show in the list is a good find: the answers of the
//! Discover deck measure that. Use it to compare two versions of the data or of the formula.
//!
//! --tiers      also the mean percentile of a hidden franchise for each tier
//! --recent N   also hide the N S and A franchises that the user added last, all at the same time
//! --benchmark  write the results of each show to scratch/bench-<label>.json, to compare two versions

use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::PathBuf;
use std::time::Instant;

use anyhow::{Context, Result, bail};
use serde_json::{Value, json};

use crate::engine::{Engine, tier_value};
use crate::store::Store;

/// The state of the engine that a test changes, to put it back after the test
struct Saved {
    rows: Vec<(usize, bool, Option<String>, f64, Option<f64>)>,
    owned_idx: Vec<usize>,
    dismissed: HashSet<String>,
}

/// One formula of the list: (usual kinds, crowd links)
type Formula = (bool, bool);

impl Engine {
    /// Make the engine forget that the user owns and rated these rows. A hidden show is a
    /// possible recommendation, also if the user removed it at some time.
    fn hide(&mut self, rows: &[usize]) -> Saved {
        let saved = Saved {
            rows: rows.iter().map(|&i| (i, self.rows[i].owned, self.rows[i].tier.clone(), self.rows[i].weight, self.weights.get(&self.rows[i].id).copied())).collect(),
            owned_idx: self.owned_idx.clone(),
            dismissed: self.dismissed.clone(),
        };
        let hide: HashSet<usize> = rows.iter().copied().collect();
        for &i in rows {
            self.dismissed.remove(&self.rows[i].id);
            let id = self.rows[i].id.clone();
            let row = &mut self.rows[i];
            row.owned = false;
            row.tier = None;
            row.weight = 1.0;
            self.weights.remove(&id);
        }
        self.owned_idx.retain(|i| !hide.contains(i));
        saved
    }

    fn restore(&mut self, saved: Saved) {
        for (i, owned, tier, weight, entry) in saved.rows {
            let id = self.rows[i].id.clone();
            let row = &mut self.rows[i];
            row.owned = owned;
            row.tier = tier;
            row.weight = weight;
            if let Some(w) = entry {
                self.weights.insert(id, w);
            }
        }
        self.owned_idx = saved.owned_idx;
        self.dismissed = saved.dismissed;
    }

    /// The owned rows of a franchise, with their counterparts
    fn franchise_members(&self, franchise: usize) -> Vec<usize> {
        let mut out = Vec::new();
        for &i in &self.owned_idx {
            if self.row_fr[i] == franchise {
                out.push(i);
                out.extend(self.counterparts[i].iter().copied());
            }
        }
        out
    }

    /// One row for each rated franchise with a tier of `tiers`, in the order of the shows of the user
    fn rated_shows(&self, tiers: &[&str]) -> Vec<usize> {
        let mut seen = HashSet::new();
        let mut out = Vec::new();
        for &i in &self.owned_idx {
            let franchise = self.row_fr[i];
            if self.rows[i].tier.as_deref().is_some_and(|t| tiers.contains(&t)) && seen.insert(franchise) {
                out.push(i);
            }
        }
        out
    }

    /// The list of the new franchises, as franchise numbers in the order of the list
    fn franchise_list(&self, k: usize, diverse: bool, (usual, links): Formula) -> Result<Vec<usize>> {
        Ok(self.recommend(k, None, diverse, true, usual, links)?.into_iter().map(|r| self.row_fr[r.row]).collect())
    }

    /// Hide the franchise of a row: (the place of the franchise in the list, the length of the list).
    /// Place 0 is the top. A franchise that is not in the list has the place of the length.
    fn rank_of_hidden(&mut self, row: usize, k: usize, diverse: bool, formula: Formula) -> Result<(usize, usize)> {
        let franchise = self.row_fr[row];
        let saved = self.hide(&self.franchise_members(franchise));
        let list = self.franchise_list(k, diverse, formula);
        self.restore(saved);
        let list = list?;
        Ok((list.iter().position(|&f| f == franchise).unwrap_or(list.len()), list.len()))
    }

    /// The `count` S and A franchises that the user added last, hidden at the same time: the
    /// first row of each franchise, and (place, length) of the franchise in the one list
    fn recent_ranks(&mut self, count: usize, k: usize, diverse: bool, formula: Formula) -> Result<Vec<(usize, usize, usize)>> {
        let mut dated: Vec<(String, String, usize)> = self
            .rated_shows(&["S", "A"])
            .into_iter()
            .filter_map(|i| {
                let added = self.rows[i].data.get("added_at").and_then(Value::as_str).filter(|a| !a.is_empty())?;
                Some((added.to_string(), self.rows[i].id.clone(), i))
            })
            .collect();
        dated.sort();
        let newest: Vec<usize> = dated.iter().rev().take(count).map(|(_, _, i)| *i).collect();
        let mut first_row: BTreeMap<usize, usize> = BTreeMap::new();
        for &i in newest.iter().rev() {
            first_row.insert(self.row_fr[i], i);
        }
        let members: Vec<usize> = first_row.keys().flat_map(|&f| self.franchise_members(f)).collect();
        let saved = self.hide(&members);
        let list = self.franchise_list(k, diverse, formula);
        self.restore(saved);
        let list = list?;
        let mut place: HashMap<usize, usize> = HashMap::new();
        for (rank, &f) in list.iter().enumerate() {
            place.entry(f).or_insert(rank);
        }
        Ok(first_row.iter().map(|(f, &i)| (i, place.get(f).copied().unwrap_or(list.len()), list.len())).collect())
    }

    /// A title of a row in Latin letters, if the row has one
    fn latin_title(&self, i: usize) -> String {
        let mut titles = vec![self.rows[i].title.clone().unwrap_or_default()];
        titles.extend(self.other_titles(i));
        titles.iter().find(|t| !t.is_empty() && t.is_ascii()).cloned().unwrap_or_else(|| titles[0].clone())
    }
}

/// The hit rates, the median place and the mean percentile of (place, length) results
struct Summary {
    n: usize,
    hit20: f64,
    hit40: f64,
    hit100: f64,
    median: usize,
    percentile: f64,
}

fn summarize(ranks: &[(usize, usize)]) -> Summary {
    if ranks.is_empty() {
        return Summary { n: 0, hit20: 0.0, hit40: 0.0, hit100: 0.0, median: 0, percentile: 0.0 };
    }
    let n = ranks.len() as f64;
    let part = |limit: usize| ranks.iter().filter(|(r, _)| *r < limit).count() as f64 / n;
    let mut sorted: Vec<usize> = ranks.iter().map(|(r, _)| *r).collect();
    sorted.sort_unstable();
    // The median: the mean of the two middle values for an even number, then cut to a whole number
    let half = sorted.len() / 2;
    let median = if sorted.len() % 2 == 1 { sorted[half] as f64 } else { (sorted[half - 1] + sorted[half]) as f64 / 2.0 };
    Summary {
        n: ranks.len(),
        hit20: part(20),
        hit40: part(40),
        hit100: part(100),
        median: median as usize,
        percentile: ranks.iter().map(|&(r, len)| 1.0 - r as f64 / len.max(1) as f64).sum::<f64>() / n,
    }
}

fn hidden_franchise_test(engine: &mut Engine, tiers: &[&str], k: usize, diverse: bool, formula: Formula) -> Result<Summary> {
    let ranks = engine.rated_shows(tiers).into_iter().map(|row| engine.rank_of_hidden(row, k, diverse, formula)).collect::<Result<Vec<_>>>()?;
    Ok(summarize(&ranks))
}

/// The length of a list of new franchises, without a limit
const ALL: usize = 100_000;
const RECENT_COUNT: usize = 20;

pub fn run(args: &[String]) -> Result<()> {
    let usage = "usage: rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]";
    let mut db = PathBuf::from("anime_vec.db");
    let (mut tiers, mut recent, mut benchmark) = (false, None, None);
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        match arg.as_str() {
            "--db" => db = PathBuf::from(rest.next().context(usage)?),
            "--tiers" => tiers = true,
            "--recent" => recent = Some(rest.next().context(usage)?.parse::<usize>()?),
            "--benchmark" => benchmark = Some(rest.next().context(usage)?.clone()),
            _ => bail!("{usage}"),
        }
    }
    let started = Instant::now();
    let store = Store::open_read_only(&db)?;
    let mut engine = Engine::load(&store)?;
    let ready = started.elapsed().as_secs_f64();
    if let Some(label) = benchmark {
        return write_benchmark(&mut engine, &db, &label, ready);
    }

    let candidates: HashSet<usize> = (0..engine.len()).filter(|&i| !engine.rows[i].owned && !engine.is_duplicate(i)).map(|i| engine.row_fr[i]).collect();
    println!("rows {}, owned {}, candidate franchises about {}", engine.len(), engine.owned_idx.len(), candidates.len());
    println!("a random list: first 40 = {:.1}%", 100.0 * 40.0 / candidates.len().max(1) as f64);
    println!();
    println!("{:<36}{:>5}{:>10}{:>10}{:>11}{:>8}", "hidden S and A franchises", "n", "first 20", "first 40", "first 100", "median");
    let variants: [(&str, bool, Formula, usize); 6] = [
        ("all kinds", false, (false, true), ALL),
        ("usual kinds", false, (true, true), ALL),
        ("all kinds, no crowd links", false, (false, false), ALL),
        ("usual kinds, no crowd links", false, (true, false), ALL),
        ("all kinds, more variety (first 100)", true, (false, true), 100),
        ("usual kinds, more variety (first 100)", true, (true, true), 100),
    ];
    for (label, diverse, formula, k) in variants {
        let s = hidden_franchise_test(&mut engine, &["S", "A"], k, diverse, formula)?;
        let median = if diverse { "-".to_string() } else { s.median.to_string() };
        println!(
            "{label:<36}{:>5}{:>10}{:>10}{:>11}{median:>8}",
            s.n,
            format!("{:.1}%", 100.0 * s.hit20),
            format!("{:.1}%", 100.0 * s.hit40),
            format!("{:.1}%", 100.0 * s.hit100)
        );
    }
    if let Some(count) = recent {
        println!();
        println!("the {count} S and A franchises that you added last, hidden at the same time:");
        for (name, usual) in [("all", false), ("usual", true)] {
            let ranks: Vec<(usize, usize)> = engine.recent_ranks(count, ALL, false, (usual, true))?.into_iter().map(|(_, r, n)| (r, n)).collect();
            let s = summarize(&ranks);
            println!(
                "  {:<13} first 20: {:.1}%   first 40: {:.1}%   first 100: {:.1}%   median rank: {}",
                format!("{name} kinds:"),
                100.0 * s.hit20,
                100.0 * s.hit40,
                100.0 * s.hit100,
                s.median
            );
        }
    }
    if tiers {
        println!();
        println!("mean percentile of a hidden franchise by its tier (1.0 = top of the list), all kinds:");
        for tier in ["S", "A", "B", "C", "D"] {
            let s = hidden_franchise_test(&mut engine, &[tier], ALL, false, (false, true))?;
            if s.n > 0 {
                println!("  {tier}: {:.3}  (n={})", s.percentile, s.n);
            }
        }
    }
    Ok(())
}

/// `--benchmark`: the results of each show for the four formulas, the first 40 of each list, the
/// data and the times, in scratch/bench-<label>.json next to the database
fn write_benchmark(engine: &mut Engine, db: &std::path::Path, label: &str, ready: f64) -> Result<()> {
    let root = db.parent().map(PathBuf::from).unwrap_or_default();
    let out = root.join("scratch").join(format!("bench-{label}.json"));
    std::fs::create_dir_all(out.parent().unwrap())?;
    // The time of one list, and of the match of all shows after a change of the data
    let started = Instant::now();
    engine.franchise_list(40, false, (true, true))?;
    let first = started.elapsed().as_secs_f64();
    let mut times: Vec<f64> = (0..5)
        .map(|_| {
            let t = Instant::now();
            engine.franchise_list(40, false, (true, true)).map(|_| t.elapsed().as_secs_f64())
        })
        .collect::<Result<_>>()?;
    times.sort_by(f64::total_cmp);
    engine.clear_cache();
    let t = Instant::now();
    engine.match_percent();
    let match_time = t.elapsed().as_secs_f64();
    engine.clear_cache();
    let round = |x: f64, n: i32| (x * 10f64.powi(n)).round() / 10f64.powi(n);
    println!("engine ready in {ready:.1} s, one list in {:.3} s, the match in {match_time:.2} s", times[2]);

    // The tier of a franchise is the best tier of its shows
    let mut best: HashMap<usize, String> = HashMap::new();
    for &i in &engine.owned_idx {
        let Some(tier) = engine.rows[i].tier.clone().filter(|t| tier_value(Some(t)).is_some()) else { continue };
        let f = engine.row_fr[i];
        if best.get(&f).is_none_or(|b| tier_value(Some(&tier)) > tier_value(Some(b))) {
            best.insert(f, tier);
        }
    }
    let targets = engine.rated_shows(&["S", "A", "B", "C", "D"]);
    let tier_of: HashMap<usize, String> = targets.iter().map(|&i| (i, best[&engine.row_fr[i]].clone())).collect();
    let count = |values: Vec<String>| -> BTreeMap<String, usize> {
        let mut out = BTreeMap::new();
        for v in values {
            *out.entry(v).or_insert(0) += 1;
        }
        out
    };
    let commit = std::process::Command::new("git").args(["describe", "--always", "--dirty"]).current_dir(&root).output().ok().map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string()).unwrap_or_default();
    let mut result = json!({
        "label": label,
        "commit": commit,
        "date": chrono::Local::now().date_naive().format("%Y-%m-%d").to_string(),
        "has_switch": true,
        "data": {
            "rows": engine.len(),
            "owned": engine.owned_idx.len(),
            "tiers": count(engine.owned_idx.iter().map(|&i| engine.rows[i].tier.clone().unwrap_or_else(|| "none".into())).collect()),
            "rated_franchises": count(tier_of.values().cloned().collect()),
            "removed": engine.dismissed.len(),
        },
        "timing": {"engine_ready_s": round(ready, 2), "list_first_s": round(first, 3), "list_s": round(times[2], 3), "match_s": round(match_time, 3)},
        "variants": {},
    });
    for (usual, links) in [(true, true), (true, false), (false, true), (false, false)] {
        let name = format!("{}, {}", if usual { "usual" } else { "all" }, if links { "links" } else { "no links" });
        let t = Instant::now();
        // The formula "all" gets only the S and A franchises, to keep the time of the benchmark short
        let chosen: Vec<usize> = targets.iter().copied().filter(|i| usual || matches!(tier_of[i].as_str(), "S" | "A")).collect();
        let mut rows = Vec::new();
        let mut ranks = Vec::new();
        for &i in &chosen {
            let (rank, length) = engine.rank_of_hidden(i, ALL, false, (usual, links))?;
            if matches!(tier_of[&i].as_str(), "S" | "A") {
                ranks.push((rank, length));
            }
            rows.push(json!({"id": engine.rows[i].id, "title": engine.latin_title(i), "tier": tier_of[&i], "rank": rank, "length": length}));
        }
        let top: Vec<Value> = engine
            .recommend(40, None, false, true, usual, links)?
            .into_iter()
            .map(|r| json!({"id": engine.rows[r.row].id, "title": engine.latin_title(r.row)}))
            .collect();
        let recent: Vec<Value> = engine
            .recent_ranks(RECENT_COUNT, ALL, false, (usual, links))?
            .into_iter()
            .map(|(i, rank, length)| json!({"id": engine.rows[i].id, "title": engine.latin_title(i), "rank": rank, "length": length}))
            .collect();
        result["data"]["candidates"] = json!(rows.first().map(|r| r["length"].clone()).unwrap_or(json!(0)));
        result["variants"][&name] = json!({"hidden": rows, "recent": recent, "top": top});
        let s = summarize(&ranks);
        println!(
            "{name:<18} S and A franchises: {}, first 20 {:.1}%, first 100 {:.1}%, median {}   ({:.0} s)",
            s.n,
            100.0 * s.hit20,
            100.0 * s.hit100,
            s.median,
            t.elapsed().as_secs_f64()
        );
        std::fs::write(&out, serde_json::to_string_pretty(&result)?)?;
    }
    println!("wrote {}", out.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_median_cuts_the_mean_of_the_two_middle_values() {
        let s = summarize(&[(0, 100), (10, 100), (30, 100), (250, 100)]);
        assert_eq!(s.n, 4);
        assert_eq!(s.median, 20);
        assert!((s.hit20 - 0.5).abs() < 1e-12 && (s.hit40 - 0.75).abs() < 1e-12 && (s.hit100 - 0.75).abs() < 1e-12);
        assert!((s.percentile - (1.0 + 0.9 + 0.7 - 1.5) / 4.0).abs() < 1e-12);
        assert_eq!(summarize(&[(3, 10), (4, 10)]).median, 3);
    }
}
