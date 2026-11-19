//! The lists of the engine: the recommendations, the steps of a list, the Discover deck, the
//! review order and the numbers of the answers. Each function has the rules of the function with
//! the same name in anime_vec/engine.py.

use std::collections::{BTreeSet, HashMap, HashSet};

use anyhow::{Context, Result};
use rayon::prelude::*;

use crate::engine::{Engine, LeaveOut, tier_value, watchable};
use crate::math::{self, dot};

/// Weight of the AniList user recommendations in the hybrid score
const LINK_WEIGHT: f64 = 0.5;
/// Weight of a show of the user without a tier, as a source of links
const UNRATED_LINK_WEIGHT: f32 = 0.75;
/// The tier penalty starts this number of standard deviations below the mean of the candidates
const TIER_MARGIN: f64 = 0.5;
const TIER_PENALTY: f64 = 1.0;
/// Weight of the "usual kinds" part of the hybrid score
const KIND_WEIGHT: f64 = 1.0;
/// The number of groups of each property of a kind: year, format, number of episodes, crowd score
const KIND_SIZES: [usize; 4] = [7, 7, 6, 2];
/// The Discover deck draws only from this number of the most popular anime
pub const DISCOVER_POPULAR: f64 = 5000.0;
/// The groups of the Discover deck: (lowest match of the group, part of the cards)
pub const DISCOVER_GROUPS: [(f64, f64); 4] = [(99.0, 0.25), (95.0, 0.25), (80.0, 0.25), (0.0, 0.25)];
/// The weight of the relevance in the diverse list (maximal marginal relevance)
const DIVERSE_LAMBDA: f64 = 0.65;

/// One recommendation
pub struct Recommendation {
    pub row: usize,
    /// The similarity to the seed, for a list with a seed
    pub similarity: Option<f32>,
    pub matched_favorite: Option<String>,
    pub linked_favorite: Option<String>,
    pub franchise_owned: bool,
}

/// The result of `_hybrid`
pub struct Hybrid {
    pub scores: Vec<f64>,
    pub best: Vec<usize>,
    pub liked: Vec<usize>,
    /// For a franchise: the liked show with the strongest link to it
    pub link_source: HashMap<usize, usize>,
    /// The score after each part of the formula
    pub stages: Vec<(&'static str, Vec<f64>)>,
}

/// One step of the story of the list
pub struct Step {
    pub key: &'static str,
    pub count: usize,
    /// The map points of the shows that stay, or None for all shows
    pub points: Option<Vec<usize>>,
}

/// The numbers of the data of the user for the texts of the steps
pub struct StepInfo {
    pub shows: usize,
    pub franchises: usize,
    pub removed: usize,
    pub liked: usize,
    pub rated: usize,
    pub sources: usize,
}

/// One group of the answers of the Discover deck
pub struct AnswerGroup {
    pub low: f64,
    pub high: f64,
    pub answers: usize,
    pub interested: usize,
}

pub struct InterestResults {
    pub answers: usize,
    pub interested: usize,
    pub not_interested: usize,
    pub groups: Vec<AnswerGroup>,
    /// (pairs, auc)
    pub model: Option<(usize, f64)>,
    pub popular: Option<f64>,
}

/// A small random generator (SplitMix64) for the Discover deck
pub struct Random(u64);

impl Random {
    pub fn new(seed: u64) -> Random {
        Random(seed)
    }

    pub fn from_time() -> Random {
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1);
        Random(now)
    }

    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// A number from 0 to 1, without 1
    pub fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }

    /// A whole number below `n`
    pub fn below(&mut self, n: usize) -> usize {
        ((self.unit() * n as f64) as usize).min(n.saturating_sub(1))
    }
}

/// Round to 3 decimals as `round(x, 3)` in Python
pub fn round3(x: f64) -> f64 {
    format!("{x:.3}").parse().unwrap_or(x)
}

/// The values as float32 values, as in the NumPy code
fn as_f32(x: Vec<f64>) -> Vec<f64> {
    x.into_iter().map(|v| v as f32 as f64).collect()
}

impl Engine {
    /// `_refused_ids`: the shows that the user removed, and the shows with the answer "not interested"
    pub fn refused_ids(&self) -> BTreeSet<String> {
        let mut out: BTreeSet<String> = self.dismissed.iter().cloned().collect();
        out.extend(self.interest.iter().filter(|(_, v)| **v == 0).map(|(id, _)| id.clone()));
        out
    }

    /// `_link_sources`: the shows that give links, with their weights
    pub fn link_sources(&self, liked: &[usize], liked_w: &[f32]) -> (Vec<usize>, Vec<f32>) {
        let liked_set: HashSet<usize> = liked.iter().copied().collect();
        let disliked: HashSet<usize> = self
            .owned_idx
            .iter()
            .filter(|&&i| matches!(self.rows[i].tier.as_deref(), Some("C") | Some("D")))
            .map(|&i| self.row_fr[i])
            .collect();
        let unrated: Vec<usize> = self
            .owned_idx
            .iter()
            .copied()
            .filter(|&i| self.rows[i].tier.is_none() && !liked_set.contains(&i) && !disliked.contains(&self.row_fr[i]))
            .collect();
        let mut rows = liked.to_vec();
        let mut weights = liked_w.to_vec();
        weights.extend(std::iter::repeat_n(UNRATED_LINK_WEIGHT, unrated.len()));
        rows.extend(unrated);
        (rows, weights)
    }

    /// `_link_scores`: the link score of each franchise, and the source show with the strongest link to it
    pub fn link_scores(&self, sources: &[usize], weights: &[f32]) -> (Vec<f32>, HashMap<usize, usize>) {
        let count = self.links.len();
        let mut weight = vec![0f32; count];
        let mut best_row: HashMap<usize, usize> = HashMap::new();
        for (&i, &w) in sources.iter().zip(weights) {
            let f = self.row_fr[i];
            if w > weight[f] {
                weight[f] = w;
                best_row.insert(f, i);
            }
        }
        let mut score = vec![0f32; count];
        let mut strongest = vec![0f32; count];
        let mut strongest_source = vec![usize::MAX; count];
        for f in 0..count {
            if weight[f] == 0.0 {
                continue;
            }
            let (others, link_weights) = &self.links[f];
            for (&g, &lw) in others.iter().zip(link_weights) {
                let value = lw * weight[f];
                score[g] += value;
                if value > strongest[g] {
                    strongest[g] = value;
                    strongest_source[g] = f;
                }
            }
        }
        let source = (0..count).filter(|&g| strongest[g] > 0.0).map(|g| (g, best_row[&strongest_source[g]])).collect();
        (score, source)
    }

    /// `_one_per_franchise`: the first k entries of an order, with one entry for each franchise at most.
    /// With `index_map`, the entries are positions in it.
    pub fn one_per_franchise(&self, order: impl IntoIterator<Item = usize>, k: usize, index_map: Option<&[usize]>) -> Vec<usize> {
        let mut seen = HashSet::new();
        let mut out = Vec::new();
        if k == 0 {
            return out;
        }
        for j in order {
            let row = index_map.map_or(j, |m| m[j]);
            if seen.insert(self.row_fr[row]) {
                out.push(j);
                if out.len() >= k {
                    break;
                }
            }
        }
        out
    }

    /// `_kind_tables`: for each property, the value of each group and the value for a row without the property
    fn kind_tables(&self, indices: &[usize], owned: &HashSet<usize>) -> Vec<Option<(Vec<f64>, f64)>> {
        let library: Vec<usize> = owned.iter().filter_map(|&f| self.entry_row[f]).collect();
        KIND_SIZES
            .iter()
            .enumerate()
            .map(|(col, &size)| {
                let cand: Vec<i64> = indices.iter().map(|&i| self.kind_codes[i][col]).filter(|&c| c >= 0).collect();
                let lib: Vec<i64> = library.iter().map(|&i| self.kind_codes[i][col]).filter(|&c| c >= 0).collect();
                if cand.is_empty() || lib.is_empty() {
                    return None;
                }
                let count = |codes: &[i64]| {
                    let mut n = vec![0f64; size];
                    for &c in codes {
                        n[c as usize] += 1.0;
                    }
                    n
                };
                let (n_cand, n_lib) = (count(&cand), count(&lib));
                let (sum_cand, sum_lib) = (n_cand.iter().sum::<f64>(), n_lib.iter().sum::<f64>());
                let ratio: Vec<f64> = (0..size)
                    .map(|g| ((n_lib[g] + 0.5) / (sum_lib + 0.5 * size as f64)).ln() - ((n_cand[g] + 0.5) / (sum_cand + 0.5 * size as f64)).ln())
                    .collect();
                let unknown = math::mean(&cand.iter().map(|&c| ratio[c as usize]).collect::<Vec<_>>());
                Some((ratio, unknown))
            })
            .collect()
    }

    /// `_kind_values`: the kind score of each row
    fn kind_values(&self, indices: &[usize], tables: &[Option<(Vec<f64>, f64)>]) -> Vec<f64> {
        let mut total = vec![0f64; indices.len()];
        for (col, table) in tables.iter().enumerate() {
            let Some((ratio, unknown)) = table else { continue };
            for (n, &i) in indices.iter().enumerate() {
                let code = self.kind_codes[i][col];
                total[n] += if code >= 0 { ratio[code as usize] } else { *unknown };
            }
        }
        as_f32(total)
    }

    /// The candidates of a list: the shows that the user does not have, and for a new franchise only its entry point
    pub fn candidates(&self, skip: &HashSet<usize>, owned: &HashSet<usize>) -> Vec<usize> {
        (0..self.len())
            .filter(|&j| {
                let r = &self.rows[j];
                let f = self.row_fr[j];
                !r.owned
                    && !self.is_duplicate(j)
                    && !skip.contains(&f)
                    && watchable(r)
                    && !self.refused(&r.id)
                    && (owned.contains(&f) || self.entry_row[f] == Some(j))
            })
            .collect()
    }

    /// `_hybrid`: the score of each candidate that gives the order of a list
    pub fn hybrid(&self, cand: &[usize], usual: bool, owned: &HashSet<usize>, links: bool) -> Hybrid {
        let content = self.content(cand, &[]);
        let mut scores = as_f32(content.scores);
        let mut stages = vec![("content", scores.clone())];
        let mut link_source = HashMap::new();
        if links {
            let (sources, weights) = self.link_sources(&content.liked, &content.liked_w);
            let (link_score, source) = self.link_scores(&sources, &weights);
            link_source = source;
            let cand_links: Vec<f64> = cand.iter().map(|&j| link_score[self.row_fr[j]] as f64).collect();
            let z = math::zscore(&cand_links);
            scores = as_f32(scores.iter().zip(&z).map(|(s, l)| s + LINK_WEIGHT * l).collect());
            stages.push(("links", scores.clone()));
        }
        let predicted = self.predicted_tier(cand, LeaveOut::Nothing);
        let low: Vec<f64> = math::zscore(&predicted).iter().map(|z| (0f64).max(-z - TIER_MARGIN)).collect();
        scores = as_f32(scores.iter().zip(&low).map(|(s, l)| s - TIER_PENALTY * l).collect());
        if low.iter().any(|&l| l != 0.0) {
            stages.push(("tier", scores.clone()));
        }
        if usual {
            let tables = self.kind_tables(cand, owned);
            let kind = self.kind_values(cand, &tables);
            let z = math::zscore(&kind);
            scores = as_f32(scores.iter().zip(&z).map(|(s, k)| s + KIND_WEIGHT * k).collect());
            stages.push(("kind", scores.clone()));
        }
        Hybrid { scores, best: content.best, liked: content.liked, link_source, stages }
    }

    /// `_favorite_title`: the title of a liked show for the reason of a recommendation
    pub fn favorite_title(&self, i: usize) -> Option<String> {
        let r = &self.rows[i];
        r.title_native.clone().filter(|t| !t.is_empty()).or_else(|| r.title.clone())
    }

    /// `recommend`: the recommendations. `diverse` gives the list with more variety, `new_only`
    /// leaves out the franchises of the user, `usual` selects the formula "usual kinds", and
    /// `links` adds the crowd links. A list with a seed is in the order of the similarity to the seed.
    pub fn recommend(&self, k: usize, seed: Option<&str>, diverse: bool, new_only: bool, usual: bool, links: bool) -> Result<Vec<Recommendation>> {
        let owned = self.owned_franchises();
        let skip = if new_only { owned.clone() } else { HashSet::new() };
        let mut out = Vec::new();
        if k == 0 {
            return Ok(out);
        }
        if let Some(seed) = seed {
            let &s = self.pos.get(seed).with_context(|| format!("unknown seed id {seed}"))?;
            let sims: Vec<f32> = (0..self.len()).into_par_iter().map(|j| dot(self.eff_row(j), self.eff_row(s))).collect();
            let exclude: HashSet<usize> = std::iter::once(s).chain(self.counterparts[s].iter().copied()).collect();
            let order = math::argsort_desc(&sims.iter().map(|&v| v as f64).collect::<Vec<_>>());
            let allowed = order.into_iter().filter(|&j| {
                let r = &self.rows[j];
                !exclude.contains(&j) && !r.owned && !skip.contains(&self.row_fr[j]) && watchable(r) && !self.refused(&r.id)
            });
            for j in self.one_per_franchise(allowed, k, None) {
                out.push(Recommendation {
                    row: j,
                    similarity: Some(sims[j]),
                    matched_favorite: None,
                    linked_favorite: None,
                    franchise_owned: owned.contains(&self.row_fr[j]),
                });
            }
            return Ok(out);
        }
        let cand = self.candidates(&skip, &owned);
        if cand.is_empty() {
            return Ok(out);
        }
        let hybrid = self.hybrid(&cand, usual, &owned, links);
        let order = if diverse { self.diverse_order(&cand, &hybrid.scores, k) } else {
            self.one_per_franchise(math::argsort_desc(&hybrid.scores), k, Some(&cand))
        };
        for j in order {
            let row = cand[j];
            out.push(Recommendation {
                row,
                similarity: None,
                matched_favorite: self.favorite_title(hybrid.liked[hybrid.best[j]]),
                linked_favorite: hybrid.link_source.get(&self.row_fr[row]).and_then(|&source| self.favorite_title(source)),
                franchise_owned: owned.contains(&self.row_fr[row]),
            });
        }
        Ok(out)
    }

    /// Maximal marginal relevance: balance the score against the similarity to the shows already selected
    fn diverse_order(&self, cand: &[usize], scores: &[f64], k: usize) -> Vec<usize> {
        let (min, max) = scores.iter().fold((f64::INFINITY, f64::NEG_INFINITY), |(a, b), &s| (a.min(s), b.max(s)));
        let span = max - min;
        let base: Vec<f64> = scores.iter().map(|&s| if span > 1e-9 { ((s - min) / span) as f32 as f64 } else { 0.0 }).collect();
        let mut open: Vec<bool> = vec![true; cand.len()];
        let mut nearest = vec![f32::NEG_INFINITY; cand.len()];
        let mut selected: Vec<usize> = Vec::new();
        while selected.len() < k && open.iter().any(|&o| o) {
            let pick = if selected.is_empty() {
                (0..cand.len()).fold(0, |best, j| if base[j] > base[best] { j } else { best })
            } else {
                let mut best: Option<(usize, f64)> = None;
                for j in (0..cand.len()).filter(|&j| open[j]) {
                    let mmr = (DIVERSE_LAMBDA * base[j] - (1.0 - DIVERSE_LAMBDA) * nearest[j] as f64) as f32 as f64;
                    if best.is_none_or(|(_, b)| mmr > b) {
                        best = Some((j, mmr));
                    }
                }
                best.unwrap().0
            };
            selected.push(pick);
            let f = self.row_fr[cand[pick]];
            for j in 0..cand.len() {
                if open[j] && self.row_fr[cand[j]] == f {
                    open[j] = false;
                }
            }
            let picked = self.eff_row(cand[pick]);
            let open_rows: Vec<usize> = (0..cand.len()).filter(|&j| open[j]).collect();
            let sims: Vec<f32> = open_rows.par_iter().map(|&j| dot(self.eff_row(cand[j]), picked)).collect();
            for (&j, &s) in open_rows.iter().zip(&sims) {
                nearest[j] = nearest[j].max(s);
            }
        }
        selected
    }

    /// The position of each row on the map: the rows that are not AniList rows of a library show
    pub fn map_points(&self) -> Vec<Option<usize>> {
        let mut out = vec![None; self.len()];
        let mut n = 0;
        for (i, slot) in out.iter_mut().enumerate() {
            if !self.is_duplicate(i) {
                *slot = Some(n);
                n += 1;
            }
        }
        out
    }

    /// `recommendation_steps`: the steps from the catalog to the list, for the animation of the map
    pub fn recommendation_steps(&self, k: usize, usual: bool, links: bool, new_only: bool) -> (StepInfo, Vec<Step>) {
        let owned = self.owned_franchises();
        let skip = if new_only { owned.clone() } else { HashSet::new() };
        let cand = self.candidates(&skip, &owned);
        let point_of = self.map_points();
        let (liked, liked_w) = self.liked();
        let rated = self.owned_idx.iter().filter(|&&i| tier_value(self.rows[i].tier.as_deref()).is_some()).count();
        let sources: HashSet<usize> = self.link_sources(&liked, &liked_w).0.iter().map(|&i| self.row_fr[i]).collect();
        let has_shows = !self.owned_idx.is_empty();
        let info = StepInfo {
            shows: self.owned_idx.len(),
            franchises: owned.len(),
            removed: self.refused_ids().len(),
            liked: if has_shows { liked.len() } else { 0 },
            rated,
            sources: if has_shows { sources.len() } else { 0 },
        };
        let points = |keep: &[usize]| keep.iter().map(|&j| point_of[cand[j]].unwrap()).collect::<Vec<_>>();
        let mut steps = vec![
            Step { key: "catalog", count: point_of.iter().filter(|p| p.is_some()).count(), points: None },
            Step { key: "new", count: cand.len(), points: Some(cand.iter().map(|&j| point_of[j].unwrap()).collect()) },
        ];
        if !cand.is_empty() && has_shows {
            let stages = self.hybrid(&cand, usual, &owned, links).stages;
            let ratio = (k as f64 / cand.len() as f64).min(1.0).powf(1.0 / (stages.len() + 1) as f64);
            for (n, (key, scores)) in stages.iter().enumerate() {
                let size = k.max((cand.len() as f64 * ratio.powi(n as i32 + 1)).round_ties_even() as usize);
                let keep = self.one_per_franchise(math::argsort_desc(scores), size, Some(&cand));
                steps.push(Step { key, count: keep.len(), points: Some(points(&keep)) });
            }
            let keep = self.one_per_franchise(math::argsort_desc(&stages.last().unwrap().1), k, Some(&cand));
            steps.push(Step { key: "list", count: keep.len(), points: Some(points(&keep)) });
        }
        (info, steps)
    }

    /// `_well_known`: the row is one of the most popular anime, or the database has no popularity places
    pub fn well_known(&self, j: usize) -> bool {
        !self.has_places || self.rows[j].popularity_place.is_some_and(|p| p != 0.0 && p <= DISCOVER_POPULAR)
    }

    /// `discover`: random shows for the Discover deck, in the groups of DISCOVER_GROUPS.
    /// Return the rows and their match.
    pub fn discover(&self, count: usize, random: &mut Random) -> Vec<(usize, f32)> {
        let owned = self.owned_franchises();
        let matches = self.match_percent();
        let mut groups: Vec<Vec<usize>> = vec![Vec::new(); DISCOVER_GROUPS.len()];
        for j in 0..self.len() {
            let r = &self.rows[j];
            let f = self.row_fr[j];
            if r.owned
                || self.is_duplicate(j)
                || owned.contains(&f)
                || !watchable(r)
                || self.refused(&r.id)
                || self.interest.contains_key(&r.id)
                || !self.well_known(j)
                || self.entry_row[f] != Some(j)
                || matches[j].is_nan()
            {
                continue;
            }
            let m = matches[j] as f64;
            let g = DISCOVER_GROUPS.iter().position(|(low, _)| m >= *low).unwrap_or(DISCOVER_GROUPS.len() - 1);
            groups[g].push(j);
        }
        let mut picked = Vec::new();
        while picked.len() < count {
            let filled: Vec<usize> = (0..groups.len()).filter(|&g| !groups[g].is_empty()).collect();
            if filled.is_empty() {
                break;
            }
            let parts: Vec<f64> = filled.iter().map(|&g| DISCOVER_GROUPS[g].1).collect();
            let total: f64 = parts.iter().sum();
            let g = if total > 0.0 {
                let mut point = random.unit() * total;
                let mut chosen = *filled.last().unwrap();
                for (&g, &p) in filled.iter().zip(&parts) {
                    if point < p {
                        chosen = g;
                        break;
                    }
                    point -= p;
                }
                chosen
            } else {
                filled[random.below(filled.len())]
            };
            let at = random.below(groups[g].len());
            let j = groups[g].swap_remove(at);
            picked.push((j, matches[j]));
        }
        // The answer of a card keeps the match that the deck showed: see set_interest
        let mut deck = self.deck_match.lock().unwrap();
        for &(j, m) in &picked {
            deck.insert(self.rows[j].id.clone(), m);
        }
        picked
    }

    /// `interest_results`: the answers of the Discover deck by the match of the shows
    pub fn interest_results(&self) -> InterestResults {
        let matches = self.match_percent();
        let deck: Vec<(f64, i64)> = self
            .interest
            .iter()
            .filter(|(id, _)| self.interest_source.get(*id).and_then(|s| s.as_deref()) == Some("deck"))
            .map(|(id, &v)| (self.pos[id], v))
            .filter(|&(j, _)| !self.rows[j].owned && self.well_known(j) && !matches[j].is_nan())
            .map(|(j, v)| (matches[j] as f64, v))
            .collect();
        let mut groups = Vec::new();
        let mut high: Option<f64> = None;
        for (low, _) in DISCOVER_GROUPS {
            let inside: Vec<i64> = deck.iter().filter(|(m, _)| *m >= low && high.is_none_or(|h| *m < h)).map(|&(_, v)| v).collect();
            groups.push(AnswerGroup {
                low,
                high: high.unwrap_or(100.0),
                answers: inside.len(),
                interested: inside.iter().sum::<i64>() as usize,
            });
            high = Some(low);
        }
        let answers: Vec<(usize, i64)> = self.interest.iter().map(|(id, &v)| (self.pos[id], v)).filter(|&(j, _)| !self.rows[j].owned).collect();
        let yes: Vec<usize> = (0..answers.len()).filter(|&n| answers[n].1 != 0).collect();
        let no: Vec<usize> = (0..answers.len()).filter(|&n| answers[n].1 == 0).collect();
        let mut model = None;
        if yes.len() >= 3 && no.len() >= 3 {
            let rows: Vec<usize> = answers.iter().map(|&(j, _)| j).collect();
            let scores = self.taste_scores(&rows, true);
            let mut above = 0f64;
            for &y in &yes {
                for &n in &no {
                    let d = scores[y] - scores[n];
                    above += if d > 0.0 { 1.0 } else if d == 0.0 { 0.5 } else { 0.0 };
                }
            }
            let pairs = yes.len() * no.len();
            model = Some((pairs, round3(above / pairs as f64)));
        }
        let interested = self.interest.values().filter(|&&v| v != 0).count();
        InterestResults {
            answers: self.interest.len(),
            interested,
            not_interested: self.interest.len() - interested,
            groups,
            model,
            popular: self.has_places.then_some(DISCOVER_POPULAR),
        }
    }

    /// `watch_next_order`: shows without a tier, the shows that the user will probably rate highest first
    pub fn watch_next_order(&self, rows: Vec<usize>) -> Vec<usize> {
        if rows.len() < 2 {
            return rows;
        }
        let matches = self.match_percent();
        let values: Vec<f64> = rows.iter().map(|&j| if matches[j].is_nan() { 0.0 } else { matches[j] as f64 }).collect();
        let mut score = math::zscore(&math::ranks(&values));
        let guesses = self.tier_guess();
        let guess: Vec<f64> = rows.iter().map(|&j| guesses[j] as f64).collect();
        if !guess.iter().any(|g| g.is_nan()) {
            let z = math::zscore(&guess);
            for (s, g) in score.iter_mut().zip(&z) {
                *s += g;
            }
        }
        math::argsort_desc(&score).into_iter().map(|k| rows[k]).collect()
    }

    /// `review_queue`: the shows of the user, the shows without a tier first
    pub fn review_queue(&self, unrated_only: bool) -> Vec<usize> {
        let unrated: Vec<usize> = self.owned_idx.iter().copied().filter(|&i| self.rows[i].tier.is_none()).collect();
        let mut order = self.watch_next_order(unrated);
        if !unrated_only {
            let matches = self.match_percent();
            let value = |i: usize| if matches[i].is_nan() { -1.0 } else { matches[i] as f64 };
            let mut rated: Vec<usize> = self.owned_idx.iter().copied().filter(|&i| self.rows[i].tier.is_some()).collect();
            rated.sort_by(|&a, &b| value(b).total_cmp(&value(a)));
            order.extend(rated);
        }
        order
    }

    /// `taste_center`: the mean direction of the shows of the user, weighted by their tiers
    pub fn taste_center(&self) -> Option<Vec<f32>> {
        if self.owned_idx.is_empty() {
            return None;
        }
        let has_rated = self.owned_idx.iter().any(|&i| self.weights.contains_key(&self.rows[i].id));
        let default = if has_rated { 0.0 } else { 1.0 };
        let mut weights: Vec<f64> = self.owned_idx.iter().map(|&i| self.weights.get(&self.rows[i].id).copied().unwrap_or(default)).collect();
        if weights.iter().all(|&w| w <= 0.0) {
            weights = vec![1.0; weights.len()];
        }
        let mut v = vec![0f64; self.dim];
        for (&i, &w) in self.owned_idx.iter().zip(&weights) {
            for (k, x) in self.eff_row(i).iter().enumerate() {
                v[k] += *x as f64 * (w as f32) as f64;
            }
        }
        let norm = v.iter().map(|x| x * x).sum::<f64>().sqrt().max(1e-9);
        Some(v.iter().map(|x| (x / norm) as f32).collect())
    }
}
