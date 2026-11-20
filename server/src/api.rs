//! The answers of the API as JSON. The shapes are the types of web/src/lib/api/types.ts.

use anyhow::Result;
use serde_json::{Map, Value, json};

use crate::engine::{Engine, display_similarity};
use crate::lists::{Random, Recommendation};
use crate::math::round1;
use crate::store::truthy;

/// The options of a list of recommendations
pub struct RecommendOptions<'a> {
    pub k: usize,
    pub seed: Option<&'a str>,
    pub diverse: bool,
    pub new_only: bool,
    pub usual: bool,
    pub links: bool,
}

/// The options of a list without a seed: the key of the list in the cache of the engine
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct ListKey {
    pub k: usize,
    pub diverse: bool,
    pub new_only: bool,
    pub usual: bool,
    pub links: bool,
}

impl ListKey {
    pub fn of(o: &RecommendOptions) -> ListKey {
        ListKey { k: o.k, diverse: o.diverse, new_only: o.new_only, usual: o.usual, links: o.links }
    }

    /// The options of the list of this key
    pub fn options(&self) -> RecommendOptions<'static> {
        RecommendOptions { k: self.k, seed: None, diverse: self.diverse, new_only: self.new_only, usual: self.usual, links: self.links }
    }
}

/// The options of the steps of a list: the key of the steps in the cache of the engine
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct StepsKey {
    pub k: usize,
    pub usual: bool,
    pub links: bool,
    pub new_only: bool,
}

/// The fields of the data of a row that the page never reads: no answer has them
const UNUSED_FIELDS: [&str; 3] = ["recommendations", "provider_ids", "added_at"];
/// The long fields that a card in a list does not show. The answers with all fields:
/// /api/show (the detail window), /api/discover and /api/review-queue (the cards of the decks).
const CARD_LEFT_OUT: [&str; 3] = ["overview", "studios", "tag_ranks"];

fn round_to(x: f64, places: usize) -> f64 {
    format!("{x:.places$}").parse().unwrap_or(x)
}

impl Engine {
    /// `poster_of`: the address of the poster of a row. A library row uses the poster of its
    /// AniList entry, or the address of this server that passes the poster on from Jellyfin.
    pub fn poster_of(&self, j: usize) -> Value {
        let r = &self.rows[j];
        if r.source != "library" {
            return r.data["poster"].clone();
        }
        let source = self.tag_source(j);
        if source != j && truthy(&self.rows[source].data["poster"]) {
            return self.rows[source].data["poster"].clone();
        }
        if truthy(&r.data["poster"]) { Value::from(format!("/api/poster/{}", r.id)) } else { Value::Null }
    }

    /// `other_titles`: the titles of a row that are not its two main titles, for the search
    pub fn other_titles(&self, j: usize) -> Vec<String> {
        let r = &self.rows[j];
        let text = |row: usize, key: &str| self.rows[row].data.get(key).and_then(|v| v.as_str()).map(str::to_string);
        let mut names = vec![text(j, "title_english")];
        if r.source == "library" {
            for &other in &self.counterparts[j] {
                names.extend([text(other, "title"), text(other, "title_english"), text(other, "title_native")]);
            }
        }
        let key = |s: &str| s.trim().to_lowercase();
        let mut seen: Vec<String> = vec![key(&text(j, "title").unwrap_or_default()), key(&text(j, "title_native").unwrap_or_default())];
        let mut out = Vec::new();
        for name in names.into_iter().flatten() {
            let name = name.trim().to_string();
            if !name.is_empty() && !seen.contains(&name.to_lowercase()) {
                seen.push(name.to_lowercase());
                out.push(name);
            }
        }
        out
    }

    /// `public_row`: a copy of a row for the API. A library row gets the AniList id and the
    /// crowd score of its AniList entry. Its own rating moves to `library_score`. The fields that
    /// the page never reads (UNUSED_FIELDS) are not in the copy.
    pub fn public_row(&self, j: usize) -> Map<String, Value> {
        let r = &self.rows[j];
        let mut out = r.data.clone();
        for key in UNUSED_FIELDS {
            out.remove(key);
        }
        out.insert("owned".into(), Value::from(r.owned as i64));
        out.insert("manual_watched".into(), Value::from(r.manual_watched as i64));
        out.insert("tier".into(), r.tier.clone().map(Value::from).unwrap_or(Value::Null));
        out.insert("weight".into(), Value::from(r.weight));
        out.insert("dismissed".into(), Value::from(self.refused(&r.id) as i64));
        out.insert("interest".into(), self.interest.get(&r.id).map(|&v| Value::from(v)).unwrap_or(Value::Null));
        out.insert("poster".into(), self.poster_of(j));
        let source = self.tag_source(j);
        if source != j {
            out.insert("anilist_id".into(), self.rows[source].data["anilist_id"].clone());
            out.insert("library_score".into(), r.data["score"].clone());
            out.insert("score".into(), self.rows[source].data["score"].clone());
        }
        out
    }

    /// `_result`: a row of a list, with its similarity to a seed and the tags that it shares with the seed
    pub fn result(&self, j: usize, similarity: Option<f32>, seed: Option<usize>) -> Map<String, Value> {
        let mut out = self.public_row(j);
        if let Some(s) = similarity {
            out.insert("similarity".into(), Value::from(display_similarity(s)));
        }
        let shared: Vec<String> = match seed {
            Some(s) => {
                let mut tags: Vec<String> = self.rows[s].tags.iter().filter(|t| self.rows[j].tags.contains(t)).cloned().collect();
                tags.sort();
                tags.dedup();
                tags
            }
            None => Vec::new(),
        };
        out.insert("shared_tags".into(), Value::from(shared));
        out
    }

    /// A row of a list of cards: `result` without the long fields that a card does not show
    /// (CARD_LEFT_OUT). The detail window of the page gets the full row from /api/show.
    pub fn card(&self, j: usize, similarity: Option<f32>, seed: Option<usize>) -> Map<String, Value> {
        let mut out = self.result(j, similarity, seed);
        for key in CARD_LEFT_OUT {
            out.remove(key);
        }
        out
    }

    /// `with_match`: add the match, and for a row without a tier the letter of the tier guess
    pub fn with_match(&self, mut results: Vec<Map<String, Value>>) -> Vec<Value> {
        let matches = self.match_percent();
        let guesses = self.tier_guess();
        results
            .iter_mut()
            .map(|r| {
                let j = self.pos[r["id"].as_str().unwrap_or_default()];
                let m = matches[j];
                r.insert("match".into(), if m.is_nan() { Value::Null } else { Value::from(round1(m as f64)) });
                let letter = if r.get("tier").is_none_or(Value::is_null) { Engine::guess_letter(guesses[j]) } else { None };
                r.insert("tier_guess".into(), letter.map(Value::from).unwrap_or(Value::Null));
                Value::Object(std::mem::take(r))
            })
            .collect()
    }

    /// The rows with all their fields, for the cards of the Discover deck and of the Review tab
    fn listed(&self, rows: impl IntoIterator<Item = usize>) -> Vec<Value> {
        self.with_match(rows.into_iter().map(|j| self.result(j, None, None)).collect())
    }

    /// The rows for a list of cards
    fn listed_cards(&self, rows: impl IntoIterator<Item = usize>) -> Vec<Value> {
        self.with_match(rows.into_iter().map(|j| self.card(j, None, None)).collect())
    }

    /// GET /api/profile
    pub fn api_profile(&self) -> Value {
        let mut summary = Map::new();
        for t in ["S", "A", "B", "C", "D", "unrated"] {
            summary.insert(t.into(), Value::from(0));
        }
        for &i in &self.owned_idx {
            let key = match self.rows[i].tier.as_deref() {
                Some(t) if summary.contains_key(t) && t != "unrated" => t.to_string(),
                _ => "unrated".to_string(),
            };
            let count = summary[&key].as_i64().unwrap() + 1;
            summary.insert(key, Value::from(count));
        }
        json!({
            "tier_summary": summary,
            "owned_count": self.owned_idx.len(),
            "library_count": self.owned_idx.iter().filter(|&&i| self.rows[i].source == "library").count(),
            "manual_count": self.manual_count,
            "total_count": self.len(),
        })
    }

    /// GET /api/shows: the titles of all shows, for the search box
    pub fn api_titles(&self) -> Value {
        Value::from(
            (0..self.len())
                .map(|i| {
                    let r = &self.rows[i];
                    json!({
                        "id": r.id, "title": r.data["title"], "title_native": r.data["title_native"], "year": r.data["year"],
                        "poster": self.poster_of(i), "owned": r.owned as i64, "manual_watched": r.manual_watched as i64,
                        "tier": r.tier, "weight": r.weight, "aka": self.other_titles(i),
                    })
                })
                .collect::<Vec<_>>(),
        )
    }

    /// GET /api/show/{id}
    pub fn api_show(&self, id: &str) -> Option<Value> {
        let &j = self.pos.get(id)?;
        self.with_match(vec![self.public_row(j)]).pop()
    }

    /// GET /api/ratings: the rated shows of the user, by tier and then by match
    pub fn api_ratings(&self) -> Value {
        let mut out = self.listed_cards(self.owned_idx.iter().copied().filter(|&i| self.rows[i].tier.is_some()));
        let order = |t: Option<&str>| match t {
            Some("S") => 0,
            Some("A") => 1,
            Some("B") => 2,
            Some("C") => 3,
            Some("D") => 4,
            _ => 99,
        };
        // A stable sort: the highest match first, and -0.0 is equal to 0.0
        out.sort_by(|a, b| {
            let key = |v: &Value| (order(v["tier"].as_str()), v["match"].as_f64().unwrap_or(0.0));
            let (ka, kb) = (key(a), key(b));
            ka.0.cmp(&kb.0).then(kb.1.partial_cmp(&ka.1).unwrap_or(std::cmp::Ordering::Equal))
        });
        Value::from(out)
    }

    /// GET /api/watched: the shows that the user marked as watched by hand
    pub fn api_watched(&self) -> Value {
        Value::from(self.listed_cards((0..self.len()).filter(|&i| self.rows[i].manual_watched && !self.is_duplicate(i))))
    }

    /// GET /api/dismissed: the shows that the user does not want
    pub fn api_dismissed(&self) -> Value {
        Value::from(self.listed_cards(self.refused_ids().iter().map(|id| self.pos[id])))
    }

    /// GET /api/review-queue
    pub fn api_review_queue(&self, unrated_only: bool) -> Value {
        Value::from(self.listed(self.review_queue(unrated_only)))
    }

    /// GET /api/interest: the watch list, the highest match first
    pub fn api_watch_list(&self) -> Value {
        let rows = self.interest.iter().filter(|&(_, &v)| v != 0).map(|(id, _)| self.pos[id]).filter(|&j| !self.rows[j].owned);
        let mut out = self.listed_cards(rows);
        out.sort_by(|a, b| b["match"].as_f64().unwrap_or(0.0).total_cmp(&a["match"].as_f64().unwrap_or(0.0)));
        Value::from(out)
    }

    /// GET /api/interest/results
    pub fn api_interest_results(&self) -> Value {
        let r = self.interest_results();
        json!({
            "answers": r.answers,
            "interested": r.interested,
            "not_interested": r.not_interested,
            "groups": r.groups.iter().map(|g| json!({"low": g.low, "high": g.high, "answers": g.answers, "interested": g.interested})).collect::<Vec<_>>(),
            "model": r.model.map(|(pairs, auc)| json!({"pairs": pairs, "auc": auc})),
            "popular": r.popular.map(|p| p as i64),
        })
    }

    /// GET /api/similar
    pub fn api_similar(&self, id: &str, k: usize) -> Result<Value> {
        let seed = self.pos[id];
        let list = self.similar_to(id, k)?;
        Ok(Value::from(self.with_match(list.iter().map(|&(j, s)| self.card(j, Some(s), Some(seed))).collect())))
    }

    /// GET /api/recommend. The server writes a list without a seed into the log (server.rs). The
    /// engine keeps a list without a seed until the data changes. A list with a seed is fast
    /// (about 6 ms), and it is not kept.
    pub fn api_recommend(&self, o: &RecommendOptions) -> Result<Value> {
        if o.seed.is_some() {
            return self.compute_recommend(o);
        }
        self.cached_list(ListKey::of(o), || self.compute_recommend(o).map_err(|error| format!("{error:#}"))).map_err(anyhow::Error::msg)
    }

    /// The list without the cache (the timing command uses it)
    pub(crate) fn compute_recommend(&self, o: &RecommendOptions) -> Result<Value> {
        let list = self.recommend(o.k, o.seed, o.diverse, o.new_only, o.usual, o.links)?;
        let rows = list
            .iter()
            .map(|rec: &Recommendation| {
                let mut out = self.card(rec.row, rec.similarity, None);
                if let Some(f) = &rec.matched_favorite {
                    out.insert("matched_favorite".into(), Value::from(f.clone()));
                }
                if let Some(f) = &rec.linked_favorite {
                    out.insert("linked_favorite".into(), Value::from(f.clone()));
                }
                out.insert("franchise_owned".into(), Value::from(rec.franchise_owned));
                out
            })
            .collect();
        Ok(Value::from(self.with_match(rows)))
    }

    /// GET /api/recommend/steps. The engine keeps the steps until the data changes.
    pub fn api_steps(&self, k: usize, usual: bool, links: bool, new_only: bool) -> Value {
        self.cached_steps(StepsKey { k, usual, links, new_only }, || self.compute_steps(k, usual, links, new_only))
    }

    /// The steps without the cache (the timing command uses it)
    pub(crate) fn compute_steps(&self, k: usize, usual: bool, links: bool, new_only: bool) -> Value {
        let (info, steps) = self.recommendation_steps(k, usual, links, new_only);
        json!({
            "kinds": if usual { "usual" } else { "all" },
            "links": links,
            "k": k,
            "info": {"shows": info.shows, "franchises": info.franchises, "removed": info.removed,
                     "liked": info.liked, "rated": info.rated, "sources": info.sources},
            "steps": steps.iter().map(|s| json!({"key": s.key, "count": s.count, "points": s.points})).collect::<Vec<_>>(),
        })
    }

    /// GET /api/rec-log: what the user did with the shows that the lists of recommendations gave
    pub fn api_rec_log(&self) -> Value {
        let order = ["S", "A", "B", "C", "D"];
        let mut mine: std::collections::HashMap<usize, Vec<usize>> = std::collections::HashMap::new();
        for &i in &self.owned_idx {
            mine.entry(self.row_fr[i]).or_default().push(i);
        }
        let (mut shown, mut added, mut unrated, mut removed) = (0, 0, 0, 0);
        let mut since: Option<String> = None;
        let mut tiers = [0usize; 5];
        let mut formulas = [[0usize; 3]; 2];
        let mut shows = Vec::new();
        for entry in &self.rec_log {
            let Some(&j) = self.pos.get(&entry.id) else { continue };
            let formula = if entry.kinds.as_deref().unwrap_or("").ends_with("no links") { 1 } else { 0 };
            shown += 1;
            formulas[formula][0] += 1;
            if since.as_ref().is_none_or(|s| entry.first_seen < *s) {
                since = Some(entry.first_seen.clone());
            }
            if let Some(rows) = mine.get(&self.row_fr[j]) {
                added += 1;
                formulas[formula][1] += 1;
                let tier = rows.iter().filter_map(|&i| order.iter().position(|t| Some(*t) == self.rows[i].tier.as_deref())).min();
                match tier {
                    Some(t) => tiers[t] += 1,
                    None => unrated += 1,
                }
                let r = &self.rows[rows[0]];
                shows.push((entry.first_seen.clone(), r.id.clone(), json!({
                    "id": r.id, "title": r.data["title"], "title_native": r.data["title_native"],
                    "tier": tier.map(|t| order[t]), "first_seen": entry.first_seen, "best_rank": entry.best_rank,
                })));
            } else if self.refused(&entry.id) {
                removed += 1;
                formulas[formula][2] += 1;
            }
        }
        shows.sort_by(|a, b| (&b.0, &b.1).cmp(&(&a.0, &a.1)));
        let counts = |f: [usize; 3]| json!({"shown": f[0], "added": f[1], "removed": f[2]});
        json!({
            "since": since, "shown": shown, "added": added, "unrated": unrated, "removed": removed,
            "tiers": order.iter().zip(tiers).map(|(t, n)| (t.to_string(), Value::from(n))).collect::<Map<_, _>>(),
            "shows": shows.into_iter().map(|(_, _, v)| v).collect::<Vec<_>>(),
            "formulas": {"links": counts(formulas[0]), "no links": counts(formulas[1])},
        })
    }

    /// GET /api/vector-map: the fixed part of the map: the points, the areas and the size of a
    /// cell. It has no data of the user, thus it stays the same until the engine loads again. The
    /// engine keeps its answer for that time (`prepared_vector_map`), and the browser keeps it too.
    pub fn api_vector_map(&self) -> Value {
        let mut points = Vec::new();
        for i in self.unique_rows() {
            let r = &self.rows[i];
            let genres: Vec<Value> = r.data["genres"].as_array().map(|g| g.iter().take(2).cloned().collect()).unwrap_or_default();
            let mut point = json!({
                "id": r.id,
                "x": round_to(self.coords[i].0 as f64, 4), "y": round_to(self.coords[i].1 as f64, 4),
                "gx": round_to(self.grid[i].0 as f64, 5), "gy": round_to(self.grid[i].1 as f64, 5),
                "title": r.data["title"], "title_native": r.data["title_native"], "year": r.data["year"],
                "poster": self.poster_of(i), "genres": genres,
                "score": self.rows[self.tag_source(i)].data["score"],
            });
            let aka = self.other_titles(i);
            if !aka.is_empty() {
                point["aka"] = Value::from(aka);
            }
            points.push(point);
        }
        json!({
            "points": points,
            "regions": self.regions,
            "cell": {"w": self.cell.0, "h": self.cell.1},
        })
    }

    /// GET /api/vector-map/user: the part of the user of the map: the points of the shows that
    /// the user has or that have a tier, by the id of the show. Each other point is a catalog
    /// show. The answer is small, and the page asks for it at each load.
    pub fn api_map_user(&self) -> Value {
        let shows: Map<String, Value> = self
            .unique_rows()
            .into_iter()
            .map(|i| &self.rows[i])
            .filter(|r| r.owned || r.tier.is_some())
            .map(|r| (r.id.clone(), json!({"owned": r.owned as i64, "tier": r.tier})))
            .collect();
        json!({"shows": shows})
    }

    /// GET /api/vector-map/match: the match of each point of the map
    pub fn api_map_match(&self) -> Value {
        let matches = self.match_percent();
        Value::from(
            self.unique_rows()
                .into_iter()
                .map(|i| if matches[i].is_nan() { Value::Null } else { Value::from(round1(matches[i] as f64)) })
                .collect::<Vec<_>>(),
        )
    }

    /// GET /api/discover: random cards, and the numbers of the answers
    pub fn api_discover(&self, count: usize, random: &mut Random) -> Value {
        let cards = self.discover(count, random);
        let interested = self.interest.values().filter(|&&v| v != 0).count();
        json!({
            "cards": self.listed(cards.into_iter().map(|(j, _)| j)),
            "counts": {"interested": interested, "not_interested": self.interest.len() - interested},
        })
    }

    /// GET /api/weights: the tiers as the database has them
    pub fn api_weights(&self) -> Value {
        Value::from(
            self.stored_weights
                .iter()
                .map(|(id, tier, weight)| (id.clone(), json!({"tier": tier, "weight": weight})))
                .collect::<Map<_, _>>(),
        )
    }
}

