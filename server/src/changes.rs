//! The changes of the data of the user: tiers, shows marked as watched, removed shows, answers of
//! the Discover deck, and the log of the lists. Each function writes the database, and then it
//! changes the state of the engine in memory.

use anyhow::{Result, bail};
use serde_json::{Value, json};

use crate::engine::Engine;
use crate::store::Store;

/// The weight of each tier. Another tier has the weight 1.
fn tier_weight(tier: &str) -> f64 {
    match tier {
        "S" => 2.0,
        "A" => 1.5,
        "B" => 1.0,
        "C" => 0.3,
        "D" => 0.0,
        _ => 1.0,
    }
}

/// A change that the user cannot make: the answer is 400 with this text
#[derive(Debug)]
pub struct Refused(pub String);

impl std::fmt::Display for Refused {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Refused {}

impl Engine {
    fn index(&self, id: &str) -> Result<usize> {
        match self.pos.get(id) {
            Some(&i) => Ok(i),
            None => bail!("unknown show id {id}"),
        }
    }

    /// The data of the user changed: the lists and the parts that come from the database again
    fn after_change(&mut self, store: &Store) -> Result<()> {
        self.owned_idx = (0..self.len()).filter(|&i| self.rows[i].owned && !self.is_duplicate(i)).collect();
        self.weights = self.rows.iter().filter(|r| r.tier.is_some()).map(|r| (r.id.clone(), r.weight)).collect();
        // The order of the tiers in the table changes with INSERT OR REPLACE: read them again
        self.stored_weights = store.weights()?;
        self.manual_count = store.manual_watched_ids().len();
        self.clear_cache();
        Ok(())
    }

    /// `set_show_tier`: give a show and its counterparts a tier, or take it away (None)
    pub fn set_show_tier(&mut self, store: &mut Store, id: &str, tier: Option<&str>) -> Result<Value> {
        let i = self.index(id)?;
        let tier = tier.filter(|t| !t.is_empty()).map(str::to_uppercase);
        let weight = tier.as_deref().map(tier_weight).unwrap_or(1.0);
        let mut changed = vec![i];
        changed.extend(self.counterparts[i].iter().copied());
        for &j in &changed {
            let row_id = self.rows[j].id.clone();
            match &tier {
                Some(t) => store.set_weight(&row_id, t, weight)?,
                None => store.delete_weight(&row_id)?,
            }
            self.rows[j].tier = tier.clone();
            self.rows[j].weight = weight;
        }
        self.after_change(store)?;
        let ids: Vec<&str> = changed.iter().map(|&j| self.rows[j].id.as_str()).collect();
        Ok(json!({"id": id, "tier": self.rows[i].tier, "weight": self.rows[i].weight, "ids": ids}))
    }

    /// `set_watched`: mark a show as watched by hand, or take the mark away. Return the new "owned".
    pub fn set_watched(&mut self, store: &mut Store, id: &str, watched: bool) -> Result<i64> {
        let i = self.index(id)?;
        store.set_manual_watched(id, watched)?;
        let row = &mut self.rows[i];
        row.manual_watched = watched;
        if row.source != "library" {
            row.owned = watched;
        }
        let owned = row.owned as i64;
        self.after_change(store)?;
        Ok(owned)
    }

    /// `_drop_interest`: delete the answer of a show
    fn drop_interest(&mut self, store: &mut Store, id: &str) -> Result<()> {
        if self.interest.contains_key(id) {
            store.set_interest(id, None, None, "")?;
            self.interest.remove(id);
            self.interest_source.remove(id);
        }
        Ok(())
    }

    /// `set_dismissed`: remove a show from the recommendations, or put it back. A removed show has
    /// no answer: to remove a show replaces its answer, and to put it back deletes "not interested".
    pub fn set_dismissed(&mut self, store: &mut Store, id: &str, dismissed: bool) -> Result<()> {
        self.index(id)?;
        store.set_dismissed(id, dismissed)?;
        if dismissed {
            self.dismissed.insert(id.to_string());
        } else {
            self.dismissed.remove(id);
        }
        if dismissed || self.interest.get(id) == Some(&0) {
            self.drop_interest(store, id)?;
        }
        self.after_change(store)
    }

    /// `set_interest`: record the answer of the user for a show that the user does not have. None
    /// deletes the answer. The database keeps the match that the deck showed for the card, or the
    /// match of now for an answer from a page.
    pub fn set_interest(&mut self, store: &mut Store, id: &str, value: Option<bool>, source: &str) -> Result<()> {
        let i = self.index(id)?;
        match value {
            None => self.drop_interest(store, id)?,
            Some(value) => {
                if self.rows[i].owned {
                    return Err(Refused("the user has this show: it gets a tier, not an answer".into()).into());
                }
                let shown = self.deck_match.lock().unwrap().remove(id);
                let matched = shown.unwrap_or_else(|| self.match_percent()[i]);
                let matched = (!matched.is_nan()).then_some(matched as f64);
                store.set_interest(id, Some(value as i64), matched, source)?;
                self.interest.insert(id.to_string(), value as i64);
                self.interest_source.insert(id.to_string(), Some(source.to_string()));
                if value && self.dismissed.contains(id) {
                    // "Interested" puts a removed show back
                    store.set_dismissed(id, false)?;
                    self.dismissed.remove(id);
                }
            }
        }
        self.after_change(store)
    }

    /// The numbers of the answers, for the answer of POST /api/interest
    pub fn interest_counts(&self) -> Value {
        let interested = self.interest.values().filter(|&&v| v != 0).count();
        json!({"interested": interested, "not_interested": self.interest.len() - interested})
    }

    /// Record the shows of a list of recommendations without a seed: the shows of new franchises,
    /// with their places. `kinds` is the formula, with ", no links" for a list without the crowd links.
    pub fn log_list(&mut self, store: &mut Store, list: &Value, kinds: &str) -> Result<()> {
        let items: Vec<(String, usize)> = list
            .as_array()
            .map(|rows| {
                rows.iter()
                    .enumerate()
                    .filter(|(_, r)| !r["franchise_owned"].as_bool().unwrap_or(false))
                    .filter_map(|(place, r)| Some((r["id"].as_str()?.to_string(), place)))
                    .collect()
            })
            .unwrap_or_default();
        let today = chrono::Local::now().date_naive().format("%Y-%m-%d").to_string();
        store.log_recommendations(&items, kinds, &today)?;
        self.rec_log = store.rec_log();
        Ok(())
    }
}
