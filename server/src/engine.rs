//! The engine: the data of all shows and the formulas of the recommender. A name in backticks
//! (`_liked`) is the name of the function in the first version of the app (Python), which was the
//! reference of this code. The git history of that version tells why each formula is as it is.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::{Arc, Mutex};

use anyhow::{Context, Result, bail};
use nalgebra::{DMatrix, DVector};
use rayon::prelude::*;
use serde_json::Value;

use crate::api::{ListKey, StepsKey};
use crate::math::{self, Sparse, dot};
use crate::memo::{Memo, MemoMap, Resettable};
use crate::prepared::Prepared;
use crate::simcache::SimColumns;
use crate::store::{LogEntry, Row, Store};

/// Centered cosine similarity at which the D-tier penalty starts
const D_SIM_START: f64 = 0.5;
/// Number of nearest liked shows that give the score of a candidate
const LIKED_K: usize = 5;
/// Weight of the D-tier penalty, in standard deviations
const D_PENALTY: f64 = 1.0;
/// Strength of the ridge regression of the tier model
const TIER_RIDGE: f64 = 3.0;
/// The tier model needs this number of rated shows
const TIER_MODEL_MIN_RATED: usize = 20;
/// A removed show counts as a C-tier show in the tier model
const DISMISSED_TIER: f64 = 1.0;
/// The letter of a tier guess: the first limit that the guess reaches
const TIER_GUESS_LIMITS: [(&str, f64); 4] = [("S", 3.5), ("A", 2.5), ("B", 1.5), ("C", 0.5)];
/// Strength of the ridge regression of the taste model, relative to the mean variance of one tag
const TASTE_RIDGE: f64 = 1.0;
/// The values that the taste model learns for a disliked show and for the answers of the Discover deck
const TASTE_DISLIKED: f64 = -1.0;
const TASTE_INTERESTED: f64 = 0.5;
const TASTE_NOT_INTERESTED: f64 = -0.5;
/// The weight of the predicted tier in the match
const MATCH_TIER_WEIGHT: f64 = 0.25;
/// The limits between the groups of the kinds of a show
const KIND_YEARS: [f64; 6] = [1990.0, 2000.0, 2005.0, 2010.0, 2015.0, 2020.0];
const KIND_EPISODES: [f64; 5] = [2.0, 7.0, 14.0, 27.0, 61.0];
const KIND_SCORES: [f64; 1] = [6.5];

/// The tier as a number: 4 = S, 0 = D
pub fn tier_value(tier: Option<&str>) -> Option<f64> {
    match tier? {
        "S" => Some(4.0),
        "A" => Some(3.0),
        "B" => Some(2.0),
        "C" => Some(1.0),
        "D" => Some(0.0),
        _ => None,
    }
}

/// `display_similarity`: a centered cosine (-1 to 1) as a percentage (0 to 100)
pub fn display_similarity(sim: f32) -> f64 {
    math::round1((1.0 + sim as f64) * 50.0)
}

/// `_watchable`: the show can be a recommendation. It is released, and it is not a music video.
pub fn watchable(row: &Row) -> bool {
    row.status.as_deref() != Some("NOT_YET_RELEASED") && row.format.as_deref() != Some("music")
}

/// `_entry_key`: the order that puts the entry point of a franchise first
fn entry_key(row: &Row) -> (bool, u8, f64, String) {
    let format_rank = match row.format.as_deref() {
        Some("tv") | Some("series") => 0,
        Some("tv_short") | Some("ona") => 1,
        _ => 2,
    };
    let year = match row.year {
        Some(y) if y != 0.0 => y,
        _ => 9999.0,
    };
    (!watchable(row), format_rank, year, row.id.clone())
}

fn key_less(a: &(bool, u8, f64, String), b: &(bool, u8, f64, String)) -> bool {
    (a.0, a.1).cmp(&(b.0, b.1)).then(a.2.total_cmp(&b.2)).then_with(|| a.3.cmp(&b.3)).is_lt()
}

/// For a model prediction: which rows get the prediction of a model without some data
#[derive(Clone, Copy, PartialEq)]
pub enum LeaveOut {
    Nothing,
    /// A row that the model learned from gets the prediction of a model without this row
    Row,
    /// A row gets the prediction of a model without the shows of its franchise
    Franchise,
}

/// The result of `_content`
pub struct Content {
    pub scores: Vec<f64>,
    pub extra_scores: Vec<f64>,
    /// For each candidate: the position in `liked` of its nearest liked show
    pub best: Vec<usize>,
    pub liked: Vec<usize>,
    pub liked_w: Vec<f32>,
}

/// The results that the engine keeps until the data of the user changes. Requests at the same
/// time wait for one computation of a value (see memo.rs). The engine forgets all of them at the
/// same time (`clear_cache` puts a new, empty Cache in place): a new field needs no other code.
#[derive(Default)]
struct Cache {
    matches: Memo<Vec<f32>>,
    guesses: Memo<Vec<f32>>,
    /// The lists of recommendations without a seed, as the API gives them
    lists: MemoMap<ListKey, Result<Value, String>>,
    /// The steps of the lists, as the API gives them
    steps: MemoMap<StepsKey, Value>,
    /// The answer of /api/shows, with its gzip bytes and its ETag
    titles: Memo<Arc<Prepared>>,
}

pub struct Engine {
    pub rows: Vec<Row>,
    pub pos: HashMap<String, usize>,
    /// The shows that the user removed from the recommendations
    pub dismissed: HashSet<String>,
    /// The answers of the Discover deck (1 = interested, 0 = not interested), in the order of the ids
    pub interest: BTreeMap<String, i64>,
    /// The source of each answer: "deck" or "page"
    pub interest_source: HashMap<String, Option<String>>,
    pub has_places: bool,
    /// The number of the shows that the user marked as watched by hand, as the database has them
    pub manual_count: usize,
    /// The tiers as the database has them: (id, tier, weight)
    pub stored_weights: Vec<(String, String, f64)>,
    /// The log of the recommendations
    pub rec_log: Vec<LogEntry>,
    /// The map position and the grid cell of each row, and the size of a cell
    pub coords: Vec<(f32, f32)>,
    pub grid: Vec<(f32, f32)>,
    pub cell: (f64, f64),
    /// The named areas of the map, as the build keeps them in the database
    pub regions: serde_json::Value,
    /// For an AniList row of a library show: the library row
    pub duplicate_of: Vec<Option<usize>>,
    /// The rows that are the same show as the row: the AniList rows of a library row, and the
    /// library row of an AniList row
    pub counterparts: Vec<Vec<usize>>,
    /// The shows of the user, without the AniList rows of the library shows
    pub owned_idx: Vec<usize>,
    /// The weight of each row that has a tier
    pub weights: HashMap<String, f64>,
    pub dim: usize,
    /// The centered and normalized embeddings, `dim` values for each row
    pub eff: Vec<f32>,
    /// The TF-IDF vector of the tags and the genres of each row
    pub tags: Vec<Sparse>,
    pub tag_names: Vec<String>,
    taste_mean: Vec<f64>,
    taste_solver: DMatrix<f64>,
    /// The franchise of each row, as a position in `franchise_names`
    pub row_fr: Vec<usize>,
    pub franchise_names: Vec<String>,
    /// The franchises with a link to each franchise, and the weights of the links
    pub links: Vec<(Vec<usize>, Vec<f32>)>,
    /// The entry point of each franchise
    pub entry_row: Vec<Option<usize>>,
    /// The group of each row for the year, the format, the number of episodes and the crowd score. -1 = not known.
    pub kind_codes: Vec<[i64; 4]>,
    cache: Resettable<Cache>,
    /// The text similarity of each show to the liked shows and the D shows (simcache.rs). The
    /// vectors do not change while this engine lives, thus a change of the user does not clear it.
    sims: SimColumns,
    /// The answer for the fixed part of the map (see `prepared_vector_map`)
    fixed_map: Memo<Arc<Prepared>>,
    /// The match of each card that the Discover deck gave, until the user answers it
    pub deck_match: Mutex<HashMap<String, f32>>,
}

impl Engine {
    pub fn load(store: &Store) -> Result<Engine> {
        let embeddings = store.embeddings()?;
        let mut rows: Vec<Row> = store.load_rows()?.into_iter().filter(|r| embeddings.contains_key(&r.id)).collect();
        let n = rows.len();
        if n == 0 {
            bail!("the database has no shows with an embedding: run `rinrikun build` first");
        }
        let pos: HashMap<String, usize> = rows.iter().enumerate().map(|(i, r)| (r.id.clone(), i)).collect();
        let dismissed: HashSet<String> = store.dismissed_ids().into_iter().filter(|i| pos.contains_key(i)).collect();
        let answers: Vec<(String, crate::store::Answer)> = store.interest().into_iter().filter(|(i, _)| pos.contains_key(i)).collect();
        let interest: BTreeMap<String, i64> = answers.iter().map(|(i, a)| (i.clone(), a.value)).collect();
        let interest_source: HashMap<String, Option<String>> = answers.into_iter().map(|(i, a)| (i, a.source)).collect();
        let has_places = rows.iter().any(|r| r.popularity_place.is_some_and(|p| p != 0.0));

        let dim = embeddings[&rows[0].id].len();
        let mut m = vec![0f32; n * dim];
        for (i, r) in rows.iter().enumerate() {
            let v = &embeddings[&r.id];
            if v.len() != dim {
                bail!("the embedding of {} has {} values, not {dim}", r.id, v.len());
            }
            let norm = v.iter().map(|x| (*x as f64) * (*x as f64)).sum::<f64>().sqrt().max(1e-9);
            for (k, x) in v.iter().enumerate() {
                m[i * dim + k] = (*x as f64 / norm) as f32;
            }
        }

        // The AniList rows of the library shows: the build connects them (the column library_id)
        let mut duplicate_of = vec![None; n];
        let mut counterparts: Vec<Vec<usize>> = vec![Vec::new(); n];
        for (i, r) in rows.iter().enumerate() {
            if r.source == "anilist" {
                if let Some(&lib) = r.library_id.as_ref().and_then(|l| pos.get(l)) {
                    duplicate_of[i] = Some(lib);
                    counterparts[lib].push(i);
                    counterparts[i].push(lib);
                }
            }
        }
        for (i, r) in rows.iter().enumerate() {
            if r.source == "library" && !counterparts[i].is_empty() {
                let mut list = counterparts[i].clone();
                list.sort_by(|&a, &b| {
                    let (ka, kb) = (entry_key(&rows[a]), entry_key(&rows[b]));
                    if key_less(&ka, &kb) {
                        std::cmp::Ordering::Less
                    } else if key_less(&kb, &ka) {
                        std::cmp::Ordering::Greater
                    } else {
                        std::cmp::Ordering::Equal
                    }
                });
                counterparts[i] = list;
            }
        }
        // A tier goes to the counterparts that have no tier
        let stored_weights = store.weights()?;
        for (id, tier, weight) in stored_weights.clone() {
            if tier.is_empty() {
                continue;
            }
            if let Some(&i) = pos.get(&id) {
                for c in counterparts[i].clone() {
                    if rows[c].tier.as_deref().is_none_or(|t| t.is_empty()) {
                        rows[c].tier = Some(tier.clone());
                        rows[c].weight = weight;
                    }
                }
            }
        }
        let owned_idx: Vec<usize> = (0..n).filter(|&i| rows[i].owned && duplicate_of[i].is_none()).collect();
        let weights: HashMap<String, f64> = rows.iter().filter(|r| r.tier.is_some()).map(|r| (r.id.clone(), r.weight)).collect();

        // A library row has the vector of its first AniList row
        let mut bridged = m.clone();
        for i in 0..n {
            if rows[i].source == "library" {
                if let Some(&c) = counterparts[i].first() {
                    bridged.copy_within(c * dim..(c + 1) * dim, i * dim);
                }
            }
        }
        // Subtract the mean of the catalog and normalize again
        let unique: Vec<usize> = (0..n).filter(|&i| duplicate_of[i].is_none()).collect();
        let mut center = vec![0f64; dim];
        for &i in &unique {
            for k in 0..dim {
                center[k] += bridged[i * dim + k] as f64;
            }
        }
        for c in center.iter_mut() {
            *c /= unique.len().max(1) as f64;
        }
        let center: Vec<f32> = center.iter().map(|&c| c as f32).collect();
        let mut eff = vec![0f32; n * dim];
        for i in 0..n {
            let row: Vec<f32> = (0..dim).map(|k| bridged[i * dim + k] - center[k]).collect();
            let norm = row.iter().map(|x| (*x as f64) * (*x as f64)).sum::<f64>().sqrt().max(1e-9);
            for k in 0..dim {
                eff[i * dim + k] = (row[k] as f64 / norm) as f32;
            }
        }

        let mut engine = Engine {
            rows,
            pos,
            dismissed,
            interest,
            interest_source,
            has_places,
            manual_count: store.manual_watched_ids().len(),
            stored_weights,
            rec_log: store.rec_log(),
            coords: Vec::new(),
            grid: Vec::new(),
            cell: (1.0, 1.4),
            regions: serde_json::Value::Array(Vec::new()),
            duplicate_of,
            counterparts,
            owned_idx,
            weights,
            dim,
            eff,
            tags: Vec::new(),
            tag_names: Vec::new(),
            taste_mean: Vec::new(),
            taste_solver: DMatrix::zeros(0, 0),
            row_fr: Vec::new(),
            franchise_names: Vec::new(),
            links: Vec::new(),
            entry_row: Vec::new(),
            kind_codes: Vec::new(),
            cache: Resettable::default(),
            sims: SimColumns::default(),
            fixed_map: Memo::default(),
            deck_match: Mutex::new(HashMap::new()),
        };
        engine.build_tag_matrix();
        engine.build_taste_model()?;
        engine.build_franchises();
        engine.build_links();
        engine.build_entry_rows();
        engine.build_kind_codes();
        engine.read_layout(store);
        Ok(engine)
    }

    /// The map layout and the areas that the build keeps in the database. A row
    /// without a position is in the middle. The Rust engine does not compute the layout in this phase.
    fn read_layout(&mut self, store: &Store) {
        let n = self.len();
        self.coords = vec![(0.5, 0.5); n];
        self.grid = vec![(0.5, 0.5); n];
        if let Some(layout) = store.layout() {
            for i in 0..n {
                if let Some(&(x, y)) = layout.coords.get(&self.rows[i].id) {
                    self.coords[i] = (x as f32, y as f32);
                }
                if let Some(&(x, y)) = layout.grid.get(&self.rows[i].id) {
                    self.grid[i] = (x as f32, y as f32);
                }
            }
            self.cell = layout.cell;
        }
        // An AniList row of a library show is at the position of the library show
        for i in 0..n {
            if let Some(lib) = self.duplicate_of[i] {
                self.coords[i] = self.coords[lib];
                self.grid[i] = self.grid[lib];
            }
        }
        self.regions = store.regions().unwrap_or(serde_json::Value::Array(Vec::new()));
    }

    /// Forget each kept result (the match, the tier guess, the lists, the large answers): the data
    /// of the user changed. The similarity columns stay: they do not depend on the user.
    pub fn clear_cache(&self) {
        self.cache.reset();
    }

    /// The number of similarity columns that the engine keeps (for the timing command)
    pub(crate) fn sim_column_count(&self) -> usize {
        self.sims.len()
    }

    /// The answer of /api/vector-map (the fixed part of the map), made one time and kept while
    /// this engine lives: a change of the user does not change it
    pub(crate) fn prepared_vector_map(&self) -> Arc<Prepared> {
        self.fixed_map.get_or_compute(|| Arc::new(Prepared::new(&self.api_vector_map())))
    }

    /// The answer of /api/shows: from the cache, or made and kept
    pub(crate) fn prepared_titles(&self) -> Arc<Prepared> {
        self.cache.get().titles.get_or_compute(|| Arc::new(Prepared::new(&self.api_titles())))
    }

    /// A list of recommendations without a seed: from the cache, or computed and kept
    pub(crate) fn cached_list(&self, key: ListKey, compute: impl FnOnce() -> Result<Value, String>) -> Result<Value, String> {
        self.cache.get().lists.get_or_compute(&key, compute)
    }

    /// The steps of a list: from the cache, or computed and kept
    pub(crate) fn cached_steps(&self, key: StepsKey, compute: impl FnOnce() -> Value) -> Value {
        self.cache.get().steps.get_or_compute(&key, compute)
    }

    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn eff_row(&self, i: usize) -> &[f32] {
        &self.eff[i * self.dim..(i + 1) * self.dim]
    }

    pub fn is_duplicate(&self, i: usize) -> bool {
        self.duplicate_of[i].is_some()
    }

    /// The rows that are not AniList rows of a library show
    pub fn unique_rows(&self) -> Vec<usize> {
        (0..self.len()).filter(|&i| !self.is_duplicate(i)).collect()
    }

    /// `_tag_source`: the row that supplies the tags and the AniList data of row i
    pub fn tag_source(&self, i: usize) -> usize {
        if self.rows[i].source == "library" {
            if let Some(&c) = self.counterparts[i].first() {
                return c;
            }
        }
        i
    }

    /// `_refused`: the user removed the show, or answered "not interested"
    pub fn refused(&self, id: &str) -> bool {
        self.dismissed.contains(id) || self.interest.get(id) == Some(&0)
    }

    /// `_dismissed_rows`: the rows that the user removed and does not have
    pub fn dismissed_rows(&self) -> Vec<usize> {
        let mut ids: Vec<&String> = self.dismissed.iter().collect();
        ids.sort();
        ids.into_iter()
            .map(|id| self.pos[id])
            .filter(|&i| !self.rows[i].owned && !self.is_duplicate(i))
            .collect()
    }

    pub fn owned_franchises(&self) -> HashSet<usize> {
        self.owned_idx.iter().map(|&i| self.row_fr[i]).collect()
    }

    /// `_liked`: the shows of the user that describe what the user likes, with their weights
    pub fn liked(&self) -> (Vec<usize>, Vec<f32>) {
        let liked: Vec<usize> =
            self.owned_idx.iter().copied().filter(|&i| self.weights.get(&self.rows[i].id).copied().unwrap_or(0.0) >= 1.0).collect();
        if !liked.is_empty() {
            let w = liked.iter().map(|&i| self.weights[&self.rows[i].id] as f32).collect();
            return (liked, w);
        }
        let mut liked: Vec<usize> =
            self.owned_idx.iter().copied().filter(|&i| !matches!(self.rows[i].tier.as_deref(), Some("C") | Some("D"))).collect();
        if liked.is_empty() {
            liked = self.owned_idx.clone();
        }
        let w = vec![1f32; liked.len()];
        (liked, w)
    }

    /// `_build_tag_matrix`: one TF-IDF vector for each row from its genres and its tags, weighted by tag rank
    fn build_tag_matrix(&mut self) {
        let n = self.len();
        let mut vocab: HashMap<String, usize> = HashMap::new();
        let mut names: Vec<String> = Vec::new();
        let mut column = |key: String| -> usize {
            if let Some(&c) = vocab.get(&key) {
                return c;
            }
            vocab.insert(key.clone(), names.len());
            names.push(key[2..].to_string());
            names.len() - 1
        };
        let mut feats: Vec<BTreeMap<usize, f32>> = Vec::with_capacity(n);
        for i in 0..n {
            let r = &self.rows[self.tag_source(i)];
            let mut f = BTreeMap::new();
            for (k, t) in r.tags.iter().enumerate() {
                let rank = match r.tag_ranks.get(k).copied().flatten() {
                    Some(v) if v != 0.0 => v,
                    _ => 50.0,
                };
                f.insert(column(format!("t:{t}")), (rank / 100.0) as f32);
            }
            for g in &r.genres {
                f.insert(column(format!("g:{g}")), 1.0);
            }
            feats.push(f);
        }
        let size = names.len().max(1);
        let mut df = vec![0usize; size];
        for f in &feats {
            for (&c, &v) in f {
                if v > 0.0 {
                    df[c] += 1;
                }
            }
        }
        let idf: Vec<f32> = df.iter().map(|&d| (((n + 1) as f64 / (d + 1) as f64).ln() + 1.0) as f32).collect();
        self.tags = feats
            .into_iter()
            .map(|f| {
                let mut out = Sparse::default();
                for (c, v) in f {
                    out.index.push(c);
                    out.value.push(v * idf[c]);
                }
                let norm = out.value.iter().map(|x| (*x as f64) * (*x as f64)).sum::<f64>().sqrt().max(1e-9);
                for v in out.value.iter_mut() {
                    *v = (*v as f64 / norm) as f32;
                }
                out
            })
            .collect();
        self.tag_names = names;
    }

    fn tag_size(&self) -> usize {
        self.tag_names.len().max(1)
    }

    /// `_build_taste_model`: the part of the taste model that comes only from the catalog
    fn build_taste_model(&mut self) -> Result<()> {
        let size = self.tag_size();
        let unique = self.unique_rows();
        let mut mean = vec![0f64; size];
        for &i in &unique {
            for (&c, &v) in self.tags[i].index.iter().zip(&self.tags[i].value) {
                mean[c] += v as f64;
            }
        }
        for v in mean.iter_mut() {
            *v /= unique.len().max(1) as f64;
        }
        // The Gram matrix of the centered tag vectors: the sum of t t' minus n m m'
        let mut gram = DMatrix::<f64>::zeros(size, size);
        for &i in &unique {
            let t = &self.tags[i];
            for (a, &va) in t.index.iter().zip(&t.value) {
                for (b, &vb) in t.index.iter().zip(&t.value) {
                    gram[(*a, *b)] += va as f64 * vb as f64;
                }
            }
        }
        let count = unique.len() as f64;
        for a in 0..size {
            for b in 0..size {
                gram[(a, b)] -= count * mean[a] * mean[b];
            }
        }
        let ridge = (TASTE_RIDGE * gram.trace() / size as f64).max(1e-9);
        for a in 0..size {
            gram[(a, a)] += ridge;
        }
        self.taste_solver = gram.cholesky().context("the taste model has no solution")?.inverse();
        self.taste_mean = mean;
        Ok(())
    }

    /// `_build_franchises`: group the rows into franchises with the AniList relations
    fn build_franchises(&mut self) {
        let mut parent: HashMap<i64, i64> = HashMap::new();
        fn find(parent: &mut HashMap<i64, i64>, a: i64) -> i64 {
            parent.entry(a).or_insert(a);
            let mut a = a;
            while parent[&a] != a {
                let grand = parent[&parent[&a]];
                parent.insert(a, grand);
                a = grand;
            }
            a
        }
        for r in &self.rows {
            if let Some(id) = r.anilist_id {
                for &other in &r.relations {
                    // The order of the two finds decides the root of the franchise: find(b) first
                    let root = find(&mut parent, other);
                    let key = find(&mut parent, id);
                    parent.insert(key, root);
                }
            }
        }
        let mut franchise: HashMap<String, String> = HashMap::new();
        for r in &self.rows {
            if let Some(id) = r.anilist_id {
                franchise.insert(r.id.clone(), format!("al:{}", find(&mut parent, id)));
            }
        }
        let mut of_row = Vec::with_capacity(self.len());
        for i in 0..self.len() {
            let id = &self.rows[i].id;
            let name = match franchise.get(id) {
                Some(f) => f.clone(),
                None => {
                    let source = &self.rows[self.tag_source(i)].id;
                    let f = franchise.get(source).cloned().unwrap_or_else(|| id.clone());
                    franchise.insert(id.clone(), f.clone());
                    f
                }
            };
            of_row.push(name);
        }
        let mut names: Vec<String> = of_row.iter().cloned().collect::<HashSet<_>>().into_iter().collect();
        names.sort();
        let index: HashMap<&String, usize> = names.iter().enumerate().map(|(k, f)| (f, k)).collect();
        self.row_fr = of_row.iter().map(|f| index[f]).collect();
        self.franchise_names = names;
    }

    /// `_build_links`: the links between franchises from the AniList user recommendations
    fn build_links(&mut self) {
        let count = self.franchise_names.len();
        let mut by_anilist: HashMap<i64, usize> = HashMap::new();
        for (i, r) in self.rows.iter().enumerate() {
            if let Some(id) = r.anilist_id {
                by_anilist.insert(id, self.row_fr[i]);
            }
        }
        let mut directed: HashMap<(usize, usize), f64> = HashMap::new();
        for (i, r) in self.rows.iter().enumerate() {
            let a = self.row_fr[i];
            for &(other, rating) in &r.recommendations {
                if let Some(&b) = by_anilist.get(&other) {
                    if b != a && rating > 0.0 {
                        *directed.entry((a, b)).or_insert(0.0) += rating;
                    }
                }
            }
        }
        let mut pairs: HashMap<(usize, usize), f64> = HashMap::new();
        for (&(a, b), &rating) in &directed {
            let key = if a < b { (a, b) } else { (b, a) };
            let value = pairs.entry(key).or_insert(0.0);
            *value = value.max(rating);
        }
        let mut degree = vec![0f64; count];
        for (&(a, b), &rating) in &pairs {
            degree[a] += rating;
            degree[b] += rating;
        }
        for d in degree.iter_mut() {
            *d = d.max(1.0);
        }
        let mut neighbors: Vec<Vec<(usize, f32)>> = vec![Vec::new(); count];
        for (&(a, b), &rating) in &pairs {
            let weight = (rating / (degree[a] * degree[b]).sqrt()) as f32;
            neighbors[a].push((b, weight));
            neighbors[b].push((a, weight));
        }
        self.links = neighbors
            .into_iter()
            .map(|mut row| {
                row.sort_by_key(|&(b, _)| b);
                (row.iter().map(|&(b, _)| b).collect(), row.iter().map(|&(_, w)| w).collect())
            })
            .collect();
    }

    /// `_build_entry_rows`: the entry point of each franchise
    fn build_entry_rows(&mut self) {
        let mut best: Vec<Option<(usize, (bool, u8, f64, String))>> = vec![None; self.franchise_names.len()];
        for j in 0..self.len() {
            if self.is_duplicate(j) {
                continue;
            }
            let key = entry_key(&self.rows[j]);
            let slot = &mut best[self.row_fr[j]];
            if slot.as_ref().is_none_or(|(_, old)| key_less(&key, old)) {
                *slot = Some((j, key));
            }
        }
        self.entry_row = best.into_iter().map(|b| b.map(|(j, _)| j)).collect();
    }

    /// `_build_kind_codes`: the group of each row for each property of its kind
    fn build_kind_codes(&mut self) {
        self.kind_codes = (0..self.len())
            .map(|i| {
                let r = &self.rows[self.tag_source(i)];
                let mut codes = [-1i64; 4];
                if r.anilist_id.is_none() {
                    return codes;
                }
                let (year, episodes, score) = (r.year.unwrap_or(0.0), r.episodes.unwrap_or(0.0), r.score.unwrap_or(0.0));
                if year > 0.0 {
                    codes[0] = math::bisect_right(&KIND_YEARS, year);
                }
                codes[1] = match r.format.as_deref().unwrap_or("") {
                    "tv" | "series" => 0,
                    "movie" => 1,
                    "ova" => 2,
                    "ona" => 3,
                    "special" => 4,
                    "tv_short" => 5,
                    _ => 6,
                };
                if episodes > 0.0 {
                    codes[2] = math::bisect_right(&KIND_EPISODES, episodes);
                }
                if score > 0.0 {
                    codes[3] = math::bisect_right(&KIND_SCORES, score);
                }
                codes
            })
            .collect();
    }

    /// `_taste_scores`: the score of the taste model for each row. With `leave_out`, a row gets the
    /// score of a model that did not learn from the shows of its franchise.
    pub fn taste_scores(&self, indices: &[usize], leave_out: bool) -> Vec<f64> {
        let (liked, liked_w) = self.liked();
        let mut disliked: Vec<usize> =
            self.owned_idx.iter().copied().filter(|&i| matches!(self.rows[i].tier.as_deref(), Some("C") | Some("D"))).collect();
        disliked.extend(self.dismissed_rows());
        let answers: Vec<(usize, i64)> = self
            .interest
            .iter()
            .map(|(id, &v)| (self.pos[id], v))
            .filter(|&(j, _)| !self.rows[j].owned)
            .collect();
        let mut examples: Vec<(usize, f64)> = liked.iter().zip(&liked_w).map(|(&i, &w)| (i, w as f64)).collect();
        examples.extend(disliked.iter().map(|&i| (i, TASTE_DISLIKED)));
        examples.extend(answers.iter().map(|&(j, v)| (j, if v != 0 { TASTE_INTERESTED } else { TASTE_NOT_INTERESTED })));
        if examples.is_empty() || indices.is_empty() {
            return vec![0.0; indices.len()];
        }
        let size = self.tag_size();
        // The sum of the centered tag vectors of the examples, each multiplied by its value
        let centered_sum = |list: &[(usize, f64)]| -> DVector<f64> {
            let mut sum = DVector::<f64>::zeros(size);
            for &(row, value) in list {
                for c in 0..size {
                    sum[c] -= self.taste_mean[c] * value;
                }
                for (&c, &v) in self.tags[row].index.iter().zip(&self.tags[row].value) {
                    sum[c] += v as f64 * value;
                }
            }
            sum
        };
        let weights = &self.taste_solver * centered_sum(&examples);
        let weights: Vec<f64> = weights.iter().copied().collect();
        let offset: f64 = self.taste_mean.iter().zip(&weights).map(|(m, w)| m * w).sum();
        let mut scores: Vec<f64> = indices.iter().map(|&i| self.tags[i].dot_dense64(&weights) - offset).collect();
        if leave_out {
            // The model without one franchise: the weights minus the part of the examples of this franchise
            let mut by_franchise: HashMap<usize, Vec<(usize, f64)>> = HashMap::new();
            for &(row, value) in &examples {
                by_franchise.entry(self.row_fr[row]).or_default().push((row, value));
            }
            let own: HashMap<usize, (Vec<f64>, f64)> = by_franchise
                .into_iter()
                .map(|(f, list)| {
                    let w: Vec<f64> = (&self.taste_solver * centered_sum(&list)).iter().copied().collect();
                    let offset = self.taste_mean.iter().zip(&w).map(|(m, x)| m * x).sum();
                    (f, (w, offset))
                })
                .collect();
            for (n, &i) in indices.iter().enumerate() {
                if let Some((w, offset)) = own.get(&self.row_fr[i]) {
                    scores[n] -= self.tags[i].dot_dense64(w) - offset;
                }
            }
        }
        scores.into_iter().map(|v| v as f32 as f64).collect()
    }

    /// `_predicted_tier`: the tier that the tier model predicts for each row, as a number (4 = S, 0 = D)
    pub fn predicted_tier(&self, indices: &[usize], leave_out: LeaveOut) -> Vec<f64> {
        let rated: Vec<usize> = self.owned_idx.iter().copied().filter(|&i| tier_value(self.rows[i].tier.as_deref()).is_some()).collect();
        let dismissed = self.dismissed_rows();
        let mut learned = rated.clone();
        learned.extend(&dismissed);
        let values: Vec<f64> = rated
            .iter()
            .map(|&i| tier_value(self.rows[i].tier.as_deref()).unwrap())
            .chain(dismissed.iter().map(|_| DISMISSED_TIER))
            .collect();
        if rated.len() < TIER_MODEL_MIN_RATED || math::std(&values) < 1e-9 {
            return vec![0.0; indices.len()];
        }
        let size = self.tag_size();
        let count = learned.len();
        // One f64 copy of each learned row, made one time: the loop below uses each row many times
        let dense64: Vec<Vec<f64>> = learned.iter().map(|&i| self.tags[i].to_dense(size).into_iter().map(f64::from).collect()).collect();
        let mut gram = DMatrix::<f64>::zeros(count, count);
        for a in 0..count {
            for b in a..count {
                let v = self.tags[learned[a]].dot_dense64(&dense64[b]);
                gram[(a, b)] = v;
                gram[(b, a)] = v;
            }
        }
        let mut system = gram.clone();
        for a in 0..count {
            system[(a, a)] += TIER_RIDGE;
        }
        let mean = math::mean(&values);
        let inverse = system.clone().cholesky().map(|c| c.inverse()).unwrap_or_else(|| system.clone().try_inverse().unwrap_or(DMatrix::zeros(count, count)));
        // R' alpha: the weights of the tags
        let tag_weights = |solution: &DVector<f64>| -> Vec<f64> {
            let mut w = vec![0f64; size];
            for (n, &row) in learned.iter().enumerate() {
                for (&c, &v) in self.tags[row].index.iter().zip(&self.tags[row].value) {
                    w[c] += v as f64 * solution[n];
                }
            }
            w
        };
        let centered = DVector::from_iterator(count, values.iter().map(|v| v - mean));
        let alpha = &inverse * &centered;
        let w = tag_weights(&alpha);
        let mut predicted: Vec<f64> = indices.iter().map(|&i| self.tags[i].dot_dense64(&w) + mean).collect();
        match leave_out {
            LeaveOut::Nothing => {}
            LeaveOut::Row => {
                let hat = &gram * &inverse;
                let v = DVector::from_vec(values.clone());
                let hat_values = &hat * &v;
                let total: f64 = values.iter().sum();
                let mut without = vec![0f64; count];
                for a in 0..count {
                    let leverage = hat[(a, a)];
                    let rest = (1.0 - leverage).max(1e-6);
                    let fit_values = (hat_values[a] - leverage * values[a]) / rest;
                    let fit_ones = (hat.row(a).sum() - leverage) / rest;
                    let mean_without = (total - values[a]) / (count.max(2) - 1) as f64;
                    without[a] = fit_values + mean_without * (1.0 - fit_ones);
                }
                let position: HashMap<usize, usize> = learned.iter().enumerate().map(|(n, &row)| (row, n)).collect();
                for (n, row) in indices.iter().enumerate() {
                    if let Some(&p) = position.get(row) {
                        predicted[n] = without[p];
                    }
                }
            }
            LeaveOut::Franchise => {
                let learned_fr: Vec<usize> = learned.iter().map(|&i| self.row_fr[i]).collect();
                let mut wanted: HashMap<usize, Vec<usize>> = HashMap::new();
                for (n, &row) in indices.iter().enumerate() {
                    wanted.entry(self.row_fr[row]).or_default().push(n);
                }
                let mut franchises: Vec<usize> = learned_fr.clone();
                franchises.sort();
                franchises.dedup();
                for f in franchises {
                    let Some(places) = wanted.get(&f) else { continue };
                    let keep: Vec<bool> = learned_fr.iter().map(|&g| g != f).collect();
                    if !keep.iter().any(|&k| k) {
                        continue;
                    }
                    let gone: Vec<usize> = (0..count).filter(|&a| !keep[a]).collect();
                    let kept: Vec<f64> = (0..count).filter(|&a| keep[a]).map(|a| values[a]).collect();
                    let mean_f = math::mean(&kept);
                    let rhs = DVector::from_iterator(count, (0..count).map(|a| if keep[a] { values[a] - mean_f } else { 0.0 }));
                    let mut solution = &inverse * rhs;
                    let small = DMatrix::from_fn(gone.len(), gone.len(), |a, b| inverse[(gone[a], gone[b])]);
                    let part = DVector::from_iterator(gone.len(), gone.iter().map(|&a| solution[a]));
                    if let Some(fix) = small.lu().solve(&part) {
                        for a in 0..count {
                            let correction: f64 = gone.iter().enumerate().map(|(g, &b)| inverse[(a, b)] * fix[g]).sum();
                            solution[a] -= correction;
                        }
                    }
                    let w = tag_weights(&solution);
                    for &n in places {
                        predicted[n] = self.tags[indices[n]].dot_dense64(&w) + mean_f;
                    }
                }
            }
        }
        // The predictions are float32 values
        predicted.iter().map(|&v| v as f32 as f64).collect()
    }

    /// `_content`: the content score of each candidate, and of each extra row on the scale of the candidates
    pub fn content(&self, cand: &[usize], extra: &[usize]) -> Content {
        let d_rows: Vec<usize> = self.owned_idx.iter().copied().filter(|&i| self.rows[i].tier.as_deref() == Some("D")).collect();
        let (liked, liked_w) = self.liked();
        // The text similarity of each show to each D show and to each liked show. The engine keeps
        // these columns (simcache.rs): `column[j]` is the similarity of show j to the show of the
        // column, with the same bits as `dot(self.eff_row(j), self.eff_row(show))`.
        let d_columns = self.sims.get(&self.eff, self.dim, &d_rows);
        let liked_columns = self.sims.get(&self.eff, self.dim, &liked);
        let penalty = |best: f32| (0f64).max(best as f64 - D_SIM_START) / (1.0 - D_SIM_START);
        let mut d_penalty = vec![0f64; cand.len()];
        let mut extra_d = vec![0f64; extra.len()];
        if !d_rows.is_empty() {
            d_penalty = cand.par_iter().map(|&c| penalty(d_columns.iter().map(|column| column[c]).fold(f32::NEG_INFINITY, f32::max))).collect();
            extra_d = extra
                .par_iter()
                .map(|&e| {
                    let best = d_rows
                        .iter()
                        .zip(&d_columns)
                        .filter(|&(&d, _)| self.row_fr[d] != self.row_fr[e])
                        .map(|(_, column)| column[e])
                        .fold(f32::NEG_INFINITY, f32::max);
                    if best == f32::NEG_INFINITY { 0.0 } else { penalty(best) }
                })
                .collect();
        }
        let size = self.tag_size();
        let liked_tags: Vec<Vec<f32>> = liked.iter().map(|&l| self.tags[l].to_dense(size)).collect();
        let text_sim = |rows: &[usize]| {
            let rows = rows.to_vec();
            let liked_columns = &liked_columns;
            move |c: usize, l: usize| liked_columns[l][rows[c]]
        };
        let tag_sim = |rows: &[usize]| {
            let rows = rows.to_vec();
            let liked_tags = &liked_tags;
            move |c: usize, l: usize| self.tags[rows[c]].dot_dense(&liked_tags[l])
        };
        let (text_score, best) = math::knn_score(cand.len(), &liked_w, text_sim(cand), LIKED_K);
        let (tag_score, _) = math::knn_score(cand.len(), &liked_w, tag_sim(cand), LIKED_K);
        let half_sum = |a: &[f64], b: &[f64]| -> Vec<f64> { a.iter().zip(b).map(|(x, y)| 0.5 * x + 0.5 * y).collect() };
        let nearest = half_sum(&math::zscore(&text_score), &math::zscore(&tag_score));
        let taste = self.taste_scores(cand, false);
        let content = half_sum(&math::zscore(&nearest), &math::zscore(&taste));
        let scores: Vec<f64> = math::zscore(&content).iter().zip(&d_penalty).map(|(s, d)| s - D_PENALTY * d).collect();
        let mut extra_scores = vec![0f64; extra.len()];
        if !extra.is_empty() {
            let skip = |e: usize, l: usize| self.row_fr[extra[e]] == self.row_fr[liked[l]];
            let extra_text = math::knn_score_without(extra.len(), &liked_w, text_sim(extra), skip, LIKED_K);
            let extra_tag = math::knn_score_without(extra.len(), &liked_w, tag_sim(extra), skip, LIKED_K);
            let extra_nearest = half_sum(&math::scale_like(&text_score, &extra_text), &math::scale_like(&tag_score, &extra_tag));
            let extra_taste = self.taste_scores(extra, true);
            let extra_content = half_sum(&math::scale_like(&nearest, &extra_nearest), &math::scale_like(&taste, &extra_taste));
            extra_scores = math::scale_like(&content, &extra_content).iter().zip(&extra_d).map(|(s, d)| s - D_PENALTY * d).collect();
        }
        Content { scores, extra_scores, best, liked, liked_w }
    }

    /// `match_percent`: the match of each row in percent, NaN for a row without a match
    pub fn match_percent(&self) -> Vec<f32> {
        self.cache.get().matches.get_or_compute(|| self.compute_match())
    }

    fn compute_match(&self) -> Vec<f32> {
        let n = self.len();
        let mut out = vec![f32::NAN; n];
        let owned = self.owned_franchises();
        let unique = self.unique_rows();
        let cand: Vec<usize> = unique
            .iter()
            .copied()
            .filter(|&j| {
                let r = &self.rows[j];
                let f = self.row_fr[j];
                !r.owned
                    && watchable(r)
                    && !self.refused(&r.id)
                    && (owned.contains(&f) || (self.entry_row[f] == Some(j) && !self.interest.contains_key(&r.id)))
            })
            .collect();
        if cand.is_empty() || self.owned_idx.is_empty() {
            return out;
        }
        let in_cand: HashSet<usize> = cand.iter().copied().collect();
        let extra: Vec<usize> = unique.iter().copied().filter(|j| !in_cand.contains(j)).collect();
        let content = self.content(&cand, &extra);
        let predicted = self.predicted_tier(&cand, LeaveOut::Nothing);
        let z = math::zscore(&predicted);
        let scores: Vec<f64> = content.scores.iter().zip(&z).map(|(s, p)| (s + MATCH_TIER_WEIGHT * p) as f32 as f64).collect();
        // The reference: the franchises that the user does not have
        let new: Vec<f64> = cand.iter().zip(&scores).filter(|(j, _)| !owned.contains(&self.row_fr[**j])).map(|(_, &s)| s).collect();
        let mut reference = if new.is_empty() { scores.clone() } else { new };
        reference.sort_by(f64::total_cmp);
        let percent = |s: f64| (100.0 * math::count_below(&reference, s) as f64 / reference.len() as f64) as f32;
        for (k, &j) in cand.iter().enumerate() {
            out[j] = percent(scores[k]);
        }
        if !extra.is_empty() {
            let extra_predicted = self.predicted_tier(&extra, LeaveOut::Franchise);
            let scaled = math::scale_like(&predicted, &extra_predicted);
            for (k, &j) in extra.iter().enumerate() {
                out[j] = percent((content.extra_scores[k] + MATCH_TIER_WEIGHT * scaled[k]) as f32 as f64);
            }
        }
        // An AniList row of a library show has the match of the library show
        for i in 0..n {
            if let Some(lib) = self.duplicate_of[i] {
                out[i] = out[lib];
            }
        }
        out
    }

    /// `tier_guess`: the tier that the tier model predicts for each row, NaN if the user has too few ratings
    pub fn tier_guess(&self) -> Vec<f32> {
        self.cache.get().guesses.get_or_compute(|| self.compute_guess())
    }

    fn compute_guess(&self) -> Vec<f32> {
        let n = self.len();
        let mut out = vec![f32::NAN; n];
        let rated: Vec<&str> = self.owned_idx.iter().filter_map(|&i| self.rows[i].tier.as_deref()).filter(|t| tier_value(Some(t)).is_some()).collect();
        let distinct: HashSet<&&str> = rated.iter().collect();
        if rated.len() >= TIER_MODEL_MIN_RATED && distinct.len() > 1 {
            let unique = self.unique_rows();
            let predicted = self.predicted_tier(&unique, LeaveOut::Row);
            for (k, &j) in unique.iter().enumerate() {
                out[j] = predicted[k] as f32;
            }
            for i in 0..n {
                if let Some(lib) = self.duplicate_of[i] {
                    out[i] = out[lib];
                }
            }
        }
        out
    }

    /// The letter of a tier guess
    pub fn guess_letter(guess: f32) -> Option<&'static str> {
        if guess.is_nan() {
            return None;
        }
        Some(TIER_GUESS_LIMITS.iter().find(|(_, limit)| guess as f64 >= *limit).map(|(l, _)| *l).unwrap_or("D"))
    }

    /// `similar_to`: the k shows that are most similar to a show, with their similarity
    pub fn similar_to(&self, id: &str, k: usize) -> Result<Vec<(usize, f32)>> {
        let &i = self.pos.get(id).with_context(|| format!("unknown id {id}"))?;
        let sims: Vec<f32> = (0..self.len()).into_par_iter().map(|j| dot(self.eff_row(j), self.eff_row(i))).collect();
        let order = math::argsort_desc(&sims.iter().map(|&s| s as f64).collect::<Vec<_>>());
        let exclude: HashSet<usize> = std::iter::once(i).chain(self.counterparts[i].iter().copied()).collect();
        Ok(order.into_iter().filter(|j| !exclude.contains(j)).take(k).map(|j| (j, sims[j])).collect())
    }
}
