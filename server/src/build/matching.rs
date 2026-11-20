//! The connection of the AniList rows to the library rows. The title match uses the ratio of
//! `difflib.SequenceMatcher` of Python: `ratio` below has the same algorithm.

use std::collections::{HashMap, HashSet};

use unicode_normalization::UnicodeNormalization;

use super::ShowRow;
use super::idmap::IdMap;

/// `normalize_title`: NFKC, lower case, only digits, Latin letters, kana and kanji, without "the" at the start
pub fn normalize_title(t: &str) -> Vec<char> {
    if t.is_empty() {
        return Vec::new();
    }
    let lower: String = t.nfkc().collect::<String>().to_lowercase();
    let kept: Vec<char> = lower
        .chars()
        .filter(|&c| {
            c.is_ascii_digit()
                || c.is_ascii_lowercase()
                || ('\u{3040}'..='\u{30ff}').contains(&c)
                || ('\u{4e00}'..='\u{9fff}').contains(&c)
                || ('\u{3400}'..='\u{4dbf}').contains(&c)
                || ('\u{ff66}'..='\u{ff9f}').contains(&c)
        })
        .collect();
    if kept.starts_with(&['t', 'h', 'e']) { kept[3..].to_vec() } else { kept }
}

/// `SequenceMatcher(None, a, b).ratio()`: 2 M / T, where M is the number of the matched
/// characters of the matching blocks and T is the number of characters of the two texts
pub fn ratio(a: &[char], b: &[char]) -> f64 {
    let total = a.len() + b.len();
    if total == 0 {
        return 1.0;
    }
    let matches: usize = matching_blocks(a, b).iter().map(|&(_, _, k)| k).sum();
    2.0 * matches as f64 / total as f64
}

/// `get_matching_blocks`, without the sort and the merge of the blocks: the sum of the sizes is the same
fn matching_blocks(a: &[char], b: &[char]) -> Vec<(usize, usize, usize)> {
    // `__chain_b`: the positions of each character of b. With autojunk, a character that is in
    // more than 1% of a long b (200 characters or more) is "popular": it is not in the index.
    let mut b2j: HashMap<char, Vec<usize>> = HashMap::new();
    for (j, &c) in b.iter().enumerate() {
        b2j.entry(c).or_default().push(j);
    }
    if b.len() >= 200 {
        let ntest = b.len() / 100 + 1;
        b2j.retain(|_, positions| positions.len() <= ntest);
    }
    let mut blocks = Vec::new();
    let mut queue = vec![(0, a.len(), 0, b.len())];
    while let Some((alo, ahi, blo, bhi)) = queue.pop() {
        let (i, j, k) = longest_match(a, b, &b2j, alo, ahi, blo, bhi);
        if k > 0 {
            blocks.push((i, j, k));
            if alo < i && blo < j {
                queue.push((alo, i, blo, j));
            }
            if i + k < ahi && j + k < bhi {
                queue.push((i + k, ahi, j + k, bhi));
            }
        }
    }
    blocks
}

/// `find_longest_match` without junk: the longest block of a[alo..ahi] in b[blo..bhi]. Of the
/// longest blocks it gives the block that starts first in a, then first in b.
fn longest_match(a: &[char], b: &[char], b2j: &HashMap<char, Vec<usize>>, alo: usize, ahi: usize, blo: usize, bhi: usize) -> (usize, usize, usize) {
    let (mut besti, mut bestj, mut bestsize) = (alo, blo, 0usize);
    let mut j2len: HashMap<usize, usize> = HashMap::new();
    for i in alo..ahi {
        let mut new_j2len: HashMap<usize, usize> = HashMap::new();
        if let Some(positions) = b2j.get(&a[i]) {
            for &j in positions {
                if j < blo {
                    continue;
                }
                if j >= bhi {
                    break;
                }
                let k = if j > 0 { j2len.get(&(j - 1)).copied().unwrap_or(0) } else { 0 } + 1;
                new_j2len.insert(j, k);
                if k > bestsize {
                    besti = i + 1 - k;
                    bestj = j + 1 - k;
                    bestsize = k;
                }
            }
        }
        j2len = new_j2len;
    }
    // Extend the block with equal characters on each end. Without junk the characters that are
    // not in the index ("popular") can also extend it.
    while besti > alo && bestj > blo && a[besti - 1] == b[bestj - 1] {
        besti -= 1;
        bestj -= 1;
        bestsize += 1;
    }
    while besti + bestsize < ahi && bestj + bestsize < bhi && a[besti + bestsize] == b[bestj + bestsize] {
        bestsize += 1;
    }
    (besti, bestj, bestsize)
}

/// `OwnershipMatcher`: the nearest title of the library rows
pub struct OwnershipMatcher {
    by_key: HashMap<Vec<char>, String>,
    normed: Vec<(Vec<char>, String)>,
}

impl OwnershipMatcher {
    const THRESHOLD: f64 = 0.92;

    /// `owned`: (id, native title, title) of each row
    pub fn new(owned: &[(&str, &str, &str)]) -> OwnershipMatcher {
        let mut by_key = HashMap::new();
        let mut normed = Vec::new();
        for &(id, native, english) in owned {
            for t in [native, english] {
                let n = normalize_title(t);
                if n.is_empty() {
                    continue;
                }
                by_key.entry(n.clone()).or_insert_with(|| id.to_string());
                normed.push((n, id.to_string()));
            }
        }
        OwnershipMatcher { by_key, normed }
    }

    /// `best`: the id of the nearest title and the ratio of the match (1 = the same title)
    pub fn best(&self, titles: &[&str]) -> (Option<String>, f64) {
        let (mut best_id, mut best_ratio) = (None, 0.0);
        for t in titles {
            let n = normalize_title(t);
            if n.is_empty() {
                continue;
            }
            if let Some(hit) = self.by_key.get(&n).filter(|h| !h.is_empty()) {
                return (Some(hit.clone()), 1.0);
            }
            for (other, id) in &self.normed {
                let length_ratio = 2.0 * n.len().min(other.len()) as f64 / (n.len() + other.len()) as f64;
                if length_ratio < Self::THRESHOLD {
                    continue;
                }
                let r = ratio(&n, other);
                if r > best_ratio {
                    best_id = Some(id.clone());
                    best_ratio = r;
                }
            }
        }
        if best_ratio >= Self::THRESHOLD { (best_id, best_ratio) } else { (None, 0.0) }
    }
}

/// `title_similarity`: how near the titles of a library row and of a pool row are, from 0 to 1
pub fn title_similarity(lib: &ShowRow, pool: &ShowRow) -> f64 {
    let mut best = 0.0f64;
    for a in [&lib.title, &lib.title_native] {
        for b in [&pool.title, &pool.title_native] {
            let (na, nb) = (normalize_title(a), normalize_title(b));
            if !na.is_empty() && !nb.is_empty() {
                best = best.max(ratio(&na, &nb));
            }
        }
    }
    best
}

/// The numbers of `link_library`, for the log of the build
pub struct Links {
    pub by_id: usize,
    pub by_title: usize,
    pub missing_ids: usize,
    pub unlinked_library_rows: usize,
}

/// `link_library`: connect each pool row that the library has to its library row. A connected
/// pool row gets owned = 1 and the id of the library row in `library_id`.
///
/// The id map is the first method. If it gives one AniList entry to two library rows, the library
/// row with the nearest title gets it. The title match is the second method, only for the library
/// rows that the id map did not connect.
pub fn link_library(lib_rows: &[ShowRow], pool: &mut [ShowRow], idmap: Option<&IdMap>) -> Links {
    // The last row with an AniList id wins
    let by_anilist: HashMap<i64, usize> = pool.iter().enumerate().filter_map(|(k, r)| Some((r.anilist_id?, k))).collect();
    for r in pool.iter_mut() {
        r.library_id = None;
    }
    // The claims in the order of the first claim: AniList id → library rows
    let mut claims: Vec<(i64, Vec<usize>)> = Vec::new();
    let mut claim_at: HashMap<i64, usize> = HashMap::new();
    let mut missing: HashSet<i64> = HashSet::new();
    if let Some(idmap) = idmap {
        for (l, lib) in lib_rows.iter().enumerate() {
            let mut ids: Vec<i64> = idmap.anilist_ids(lib.provider_ids.as_ref(), lib.format.as_deref() == Some("movie"), &lib.seasons).into_iter().collect();
            ids.sort();
            for i in ids {
                if by_anilist.contains_key(&i) {
                    let at = *claim_at.entry(i).or_insert_with(|| {
                        claims.push((i, Vec::new()));
                        claims.len() - 1
                    });
                    claims[at].1.push(l);
                } else {
                    missing.insert(i);
                }
            }
        }
    }
    let mut by_id = 0;
    for (i, libs) in &claims {
        let p = by_anilist[i];
        let winner = if libs.len() == 1 {
            libs[0]
        } else {
            // The first row with the largest value
            let mut best = libs[0];
            let mut best_value = title_similarity(&lib_rows[best], &pool[p]);
            for &l in &libs[1..] {
                let value = title_similarity(&lib_rows[l], &pool[p]);
                if value > best_value {
                    best = l;
                    best_value = value;
                }
            }
            best
        };
        pool[p].owned = 1;
        pool[p].library_id = Some(lib_rows[winner].id.clone());
        by_id += 1;
    }
    let linked: HashSet<String> = pool.iter().filter_map(|r| r.library_id.clone()).collect();
    let unlinked: Vec<(&str, &str, &str)> =
        lib_rows.iter().filter(|r| !linked.contains(&r.id)).map(|r| (r.id.as_str(), r.title_native.as_str(), r.title.as_str())).collect();
    let matcher = OwnershipMatcher::new(&unlinked);
    let mut found: Vec<(String, Vec<(f64, usize)>)> = Vec::new();
    let mut found_at: HashMap<String, usize> = HashMap::new();
    for (k, r) in pool.iter().enumerate() {
        if r.library_id.is_some() {
            continue;
        }
        if let (Some(hit), ratio) = matcher.best(&[&r.title, &r.title_native]) {
            let at = *found_at.entry(hit.clone()).or_insert_with(|| {
                found.push((hit, Vec::new()));
                found.len() - 1
            });
            found[at].1.push((ratio, k));
        }
    }
    let mut by_title = 0;
    for (lib_id, hits) in &found {
        // A title that is almost the same is frequently a different entry ("Title 3" for "Title").
        // Thus a near match counts only if no pool row has the same title, and then only the nearest.
        let same: Vec<usize> = hits.iter().filter(|(ratio, _)| *ratio >= 1.0).map(|&(_, k)| k).collect();
        let chosen = if same.is_empty() {
            let mut best = hits[0];
            for &hit in &hits[1..] {
                if hit.0 > best.0 {
                    best = hit;
                }
            }
            vec![best.1]
        } else {
            same
        };
        for k in chosen {
            pool[k].owned = 1;
            pool[k].library_id = Some(lib_id.clone());
            by_title += 1;
        }
    }
    let linked: HashSet<String> = pool.iter().filter_map(|r| r.library_id.clone()).collect();
    Links { by_id, by_title, missing_ids: missing.len(), unlinked_library_rows: lib_rows.iter().filter(|r| !linked.contains(&r.id)).count() }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn chars(s: &str) -> Vec<char> {
        s.chars().collect()
    }

    #[test]
    fn the_ratio_is_the_ratio_of_difflib() {
        // The values of difflib.SequenceMatcher(None, a, b).ratio() in Python 3.13
        let cases = [
            ("abcd", "bcde", 0.75),
            ("shingekinokyojin", "shingekinokyojin2", 0.9696969696969697),
            ("", "", 1.0),
            ("abc", "", 0.0),
            ("qabxcd", "abycdf", 0.6666666666666666),
            ("aaaaaaaa", "aaaa", 0.6666666666666666),
        ];
        for (a, b, expected) in cases {
            assert!((ratio(&chars(a), &chars(b)) - expected).abs() < 1e-12, "{a} {b}");
        }
        // A long b (200 characters or more): its frequent characters are "popular" (autojunk)
        let (a, b) = ("ab".repeat(150) + "xyz", "ba".repeat(160) + "xy");
        assert!((ratio(&chars(&a), &chars(&b)) - 0.0064).abs() < 1e-12);
    }

    #[test]
    fn normalize_keeps_letters_digits_kana_and_kanji() {
        assert_eq!(normalize_title("The Melancholy of Haruhi!"), chars("melancholyofharuhi"));
        assert_eq!(normalize_title("ＳＰＹ×ＦＡＭＩＬＹ"), chars("spyfamily"));
        assert_eq!(normalize_title("進撃の巨人 Season 2"), chars("進撃の巨人season2"));
        assert_eq!(normalize_title("Théâtre"), chars("thtre"));
        assert_eq!(normalize_title("The"), chars(""));
    }

    #[test]
    fn the_matcher_finds_the_same_title_and_a_near_title() {
        let m = OwnershipMatcher::new(&[("jf:1", "進撃の巨人", "Attack on Titan"), ("jf:2", "", "Some Long Title Here")]);
        assert_eq!(m.best(&["attack on titan!"]), (Some("jf:1".into()), 1.0));
        let (hit, r) = m.best(&["Some Long Title Here 2"]);
        assert_eq!(hit.as_deref(), Some("jf:2"));
        assert!(r > 0.92 && r < 1.0);
        assert_eq!(m.best(&["Other"]), (None, 0.0));
    }
}
