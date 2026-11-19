//! The map of the shows, with the rules of anime_vec/layout.py and of `_build_layout` and
//! `_build_regions` in anime_vec/engine.py: the 2D positions (t-SNE), the grid of the close view,
//! and the named areas of the map.

use std::collections::{HashMap, HashSet};

use serde_json::Value;

use super::tsne;
use crate::engine::Engine;
use crate::lists::Random;

/// The method of the layout. It is part of the signature: a change makes the kept layouts old.
pub const VERSION: &str = "tsne-v3-grid";
/// t-SNE needs more rows than its perplexity. Smaller indexes use PCA.
const TSNE_MIN_ROWS: usize = 100;
const REGION_MIN_ROWS: usize = 200;
const REGION_COUNT: usize = 24;
const REGION_MIN_SIZE: usize = 15;
const REGION_PART_SIZES: [f64; 2] = [230.0, 60.0];
const REGION_MIN_PART: usize = 12;
const REGION_PART_SUPPORT: [f64; 2] = [0.15, 0.2];
const CELL_ASPECT: f64 = 1.4;
const GRID_FILL: f64 = 0.5;

/// `fit_unit_square`: the points in the square from 0 to 1, with the same scale on the two axes
pub fn fit_unit_square(points: &[[f32; 2]]) -> Vec<[f32; 2]> {
    if points.is_empty() {
        return Vec::new();
    }
    let p: Vec<[f64; 2]> = points.iter().map(|q| [q[0] as f64, q[1] as f64]).collect();
    let mut lo = [f64::INFINITY; 2];
    let mut hi = [f64::NEG_INFINITY; 2];
    for q in &p {
        for ax in 0..2 {
            lo[ax] = lo[ax].min(q[ax]);
            hi[ax] = hi[ax].max(q[ax]);
        }
    }
    let span = (hi[0] - lo[0]).max(hi[1] - lo[1]).max(1e-9);
    let scaled: Vec<[f64; 2]> = p.iter().map(|q| [(q[0] - lo[0]) / span, (q[1] - lo[1]) / span]).collect();
    // The shorter axis goes to the middle of the square
    let mut top = [f64::NEG_INFINITY; 2];
    for q in &scaled {
        for ax in 0..2 {
            top[ax] = top[ax].max(q[ax]);
        }
    }
    let shift = [(1.0 - top[0]) / 2.0, (1.0 - top[1]) / 2.0];
    scaled.iter().map(|q| [(q[0] + shift[0]) as f32, (q[1] + shift[1]) as f32]).collect()
}

/// `_cell_offsets`: the cells around a cell, the nearest first
fn cell_offsets(radius: i64, dx: f64, dy: f64) -> Vec<(i64, i64)> {
    let mut offsets: Vec<(i64, i64)> = (-radius..=radius).flat_map(|ox| (-radius..=radius).map(move |oy| (ox, oy))).collect();
    // A stable sort, as list.sort of Python
    offsets.sort_by(|a, b| {
        let da = (a.0 as f64 * dx).powi(2) + (a.1 as f64 * dy).powi(2);
        let db = (b.0 as f64 * dx).powi(2) + (b.1 as f64 * dy).powi(2);
        da.total_cmp(&db)
    });
    offsets
}

/// `round()` of Python for a float: the nearest whole number, and the even number for a half
fn round_half_even(x: f64) -> i64 {
    let r = x.round();
    if (x - x.trunc()).abs() == 0.5 { (2.0 * (x / 2.0).round()) as i64 } else { r as i64 }
}

/// `grid_layout`: give each point its own cell of a grid, near its position on the map. Return
/// the centers of the cells, and the width and the height of a cell. `order` gives the points
/// that select their cell first.
pub fn grid_layout(points: &[[f32; 2]], order: &[usize]) -> (Vec<[f32; 2]>, f64, f64) {
    let n = points.len();
    if n == 0 {
        return (Vec::new(), 1.0, CELL_ASPECT);
    }
    let dx = (GRID_FILL / (CELL_ASPECT * n as f64)).sqrt();
    let dy = dx * CELL_ASPECT;
    let u: Vec<[f64; 2]> = points.iter().map(|p| [p[0] as f64 / dx, p[1] as f64 / dy]).collect();
    let mut taken: HashMap<(i64, i64), usize> = HashMap::new();
    let mut place = vec![(0i64, 0i64); n];
    let mut radius = 16;
    let mut offsets = cell_offsets(radius, dx, dy);
    for &i in order {
        let (cx, cy) = (round_half_even(u[i][0]), round_half_even(u[i][1]));
        let key = loop {
            if let Some(&(ox, oy)) = offsets.iter().find(|&&(ox, oy)| !taken.contains_key(&(cx + ox, cy + oy))) {
                break (cx + ox, cy + oy);
            }
            // All cells of the search area are taken: search a larger area
            radius *= 2;
            offsets = cell_offsets(radius, dx, dy);
        };
        taken.insert(key, i);
        place[i] = key;
    }
    let cost = |i: usize, c: (i64, i64)| ((u[i][0] - c.0 as f64) * dx).powi(2) + ((u[i][1] - c.1 as f64) * dy).powi(2);
    // A point changes its cell with a point in an adjacent cell, or moves to an adjacent free
    // cell, if that makes the sum of the movements smaller
    let adjacent: Vec<(i64, i64)> = [-1, 0, 1].iter().flat_map(|&ox| [-1, 0, 1].iter().map(move |&oy| (ox, oy))).filter(|&o| o != (0, 0)).collect();
    for _ in 0..6 {
        let mut changed = false;
        for i in 0..n {
            let mut a = place[i];
            for &(ox, oy) in &adjacent {
                let b = (a.0 + ox, a.1 + oy);
                match taken.get(&b).copied() {
                    None => {
                        if cost(i, b) < cost(i, a) - 1e-12 {
                            taken.remove(&a);
                            taken.insert(b, i);
                            place[i] = b;
                            a = b;
                            changed = true;
                        }
                    }
                    Some(j) => {
                        if cost(i, b) + cost(j, a) < cost(i, a) + cost(j, b) - 1e-12 {
                            taken.insert(a, j);
                            taken.insert(b, i);
                            place[i] = b;
                            place[j] = a;
                            a = b;
                            changed = true;
                        }
                    }
                }
            }
        }
        if !changed {
            break;
        }
    }
    let cells = place.iter().map(|&(x, y)| [(x as f64 * dx) as f32, (y as f64 * dy) as f32]).collect();
    (cells, dx, dy)
}

/// `kmeans`: divide the points into k groups with k-means++ and Lloyd steps. Return the group of
/// each point. The random generator is not the generator of NumPy: the groups of the two builds
/// can differ.
pub fn kmeans(points: &[[f64; 2]], k: usize, seed: u64) -> Vec<usize> {
    let n = points.len();
    let k = k.min(n).max(1);
    let mut random = Random::new(seed);
    let dist2 = |a: [f64; 2], b: [f64; 2]| (a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2);
    let mut centers = vec![points[random.below(n)]];
    while centers.len() < k {
        let d: Vec<f64> = points.iter().map(|&p| centers.iter().map(|&c| dist2(p, c)).fold(f64::INFINITY, f64::min)).collect();
        let total: f64 = d.iter().sum();
        let pick = if total > 0.0 {
            let mut target = random.unit() * total;
            let mut pick = n - 1;
            for (i, &v) in d.iter().enumerate() {
                if target < v {
                    pick = i;
                    break;
                }
                target -= v;
            }
            pick
        } else {
            random.below(n)
        };
        centers.push(points[pick]);
    }
    let mut labels = vec![usize::MAX; n];
    for _ in 0..50 {
        let new_labels: Vec<usize> = points
            .iter()
            .map(|&p| {
                let mut best = 0;
                for c in 1..k {
                    if dist2(p, centers[c]) < dist2(p, centers[best]) {
                        best = c;
                    }
                }
                best
            })
            .collect();
        if new_labels == labels {
            break;
        }
        labels = new_labels;
        for (c, center) in centers.iter_mut().enumerate() {
            let members: Vec<[f64; 2]> = points.iter().zip(&labels).filter(|&(_, &l)| l == c).map(|(p, _)| *p).collect();
            if !members.is_empty() {
                *center = [members.iter().map(|p| p[0]).sum::<f64>() / members.len() as f64, members.iter().map(|p| p[1]).sum::<f64>() / members.len() as f64];
            }
        }
    }
    labels
}

/// `round(x, 4)` of Python
fn round4(x: f64) -> f64 {
    format!("{x:.4}").parse().unwrap_or(x)
}

/// One named area of the map
pub struct Region {
    pub x: f64,
    pub y: f64,
    pub gx: f64,
    pub gy: f64,
    pub label: String,
    pub count: usize,
    pub level: usize,
}

impl Region {
    /// The text of the area as `json.dumps` of the dict of Python
    pub fn json(&self) -> String {
        use super::pyjson::{dumps, float_repr};
        format!(
            "{{\"x\": {}, \"y\": {}, \"gx\": {}, \"gy\": {}, \"label\": {}, \"count\": {}, \"level\": {}}}",
            float_repr(self.x),
            float_repr(self.y),
            float_repr(self.gx),
            float_repr(self.gy),
            dumps(&Value::String(self.label.clone())),
            self.count,
            self.level
        )
    }
}

/// The data of the rows of the map for `regions`: the positions, the cells and the tag vectors
struct MapRows<'a> {
    points: &'a [[f32; 2]],
    cells: &'a [[f32; 2]],
    /// The dense tag vector of each row (the TF-IDF values)
    tags: Vec<Vec<f32>>,
    names: &'a [String],
}

impl MapRows<'_> {
    /// The mean of the tag values of the members, and the part of the members with each tag
    fn means(&self, members: &[usize]) -> (Vec<f64>, Vec<f64>) {
        let size = self.names.len();
        let mut mean = vec![0f64; size];
        let mut share = vec![0f64; size];
        for &m in members {
            for (c, &v) in self.tags[m].iter().enumerate() {
                mean[c] += v as f64;
                if v > 0.0 {
                    share[c] += 1.0;
                }
            }
        }
        let n = members.len().max(1) as f64;
        mean.iter_mut().for_each(|v| *v /= n);
        share.iter_mut().for_each(|v| *v /= n);
        (mean, share)
    }

    /// `typical_tags`: the tags that are more frequent in the members than in `base`
    fn typical_tags(&self, members: &[usize], base: &[f64], exclude: &HashSet<String>, support: f64, count: usize) -> Vec<String> {
        let (mean, share) = self.means(members);
        let lift: Vec<f64> = mean.iter().zip(base).map(|(m, b)| m - b).collect();
        let mut order: Vec<usize> = (0..lift.len()).collect();
        order.sort_by(|&a, &b| lift[b].total_cmp(&lift[a]));
        let mut out = Vec::new();
        for j in order {
            if lift[j] <= 0.0 || out.len() >= count {
                break;
            }
            if share[j] >= support && !exclude.contains(&self.names[j]) {
                out.push(self.names[j].clone());
            }
        }
        out
    }

    fn region(&self, members: &[usize], level: usize, tags: &[String]) -> Region {
        let n = members.len() as f64;
        let mean = |values: &[[f32; 2]], ax: usize| members.iter().map(|&m| values[m][ax] as f64).sum::<f64>() / n;
        Region {
            x: round4(mean(self.points, 0)),
            y: round4(mean(self.points, 1)),
            gx: round4(mean(self.cells, 0)),
            gy: round4(mean(self.cells, 1)),
            label: tags.join(" · "),
            count: members.len(),
            level,
        }
    }

    fn divide(&self, members: &[usize], level: usize, exclude: &HashSet<String>, corpus: &[f64], out: &mut Vec<Region>) {
        let parts = round_half_even(members.len() as f64 / REGION_PART_SIZES[level - 1]).max(0) as usize;
        if parts < 2 {
            return;
        }
        let points: Vec<[f64; 2]> = members.iter().map(|&m| [self.points[m][0] as f64, self.points[m][1] as f64]).collect();
        let labels = kmeans(&points, parts, 0);
        let (base, _) = self.means(members);
        let support = REGION_PART_SUPPORT[level - 1];
        for c in 0..parts {
            let part: Vec<usize> = members.iter().zip(&labels).filter(|&(_, &l)| l == c).map(|(&m, _)| m).collect();
            if part.len() < REGION_MIN_PART {
                continue;
            }
            let mut tags = self.typical_tags(&part, &base, exclude, support, 2);
            if tags.is_empty() {
                tags = self.typical_tags(&part, corpus, exclude, support, 2);
            }
            if !tags.is_empty() {
                out.push(self.region(&part, level, &tags));
            }
            if level < REGION_PART_SIZES.len() {
                let mut deeper = exclude.clone();
                deeper.extend(tags);
                self.divide(&part, level + 1, &deeper, corpus, out);
            }
        }
    }
}

/// `_build_regions`: divide the map into areas on three levels and name each area after its most
/// typical tags. `points`, `cells` and `tags` are for the rows of the map (the unique rows).
pub fn regions(points: &[[f32; 2]], cells: &[[f32; 2]], tags: Vec<Vec<f32>>, names: &[String]) -> Vec<Region> {
    if points.len() < REGION_MIN_ROWS || names.is_empty() {
        return Vec::new();
    }
    let rows = MapRows { points, cells, tags, names };
    let all: Vec<usize> = (0..points.len()).collect();
    let (corpus, _) = rows.means(&all);
    let p64: Vec<[f64; 2]> = points.iter().map(|p| [p[0] as f64, p[1] as f64]).collect();
    let labels = kmeans(&p64, REGION_COUNT, 0);
    let groups = labels.iter().copied().max().map_or(0, |m| m + 1);
    let mut areas: Vec<Vec<usize>> = (0..groups).map(|c| all.iter().copied().filter(|&i| labels[i] == c).collect()).collect();
    // The largest areas first; a stable sort, as sorted() of Python
    areas.sort_by_key(|a| std::cmp::Reverse(a.len()));
    let mut out = Vec::new();
    let mut used: HashSet<String> = HashSet::new();
    for members in areas {
        if members.len() < REGION_MIN_SIZE {
            continue;
        }
        let tags = rows.typical_tags(&members, &corpus, &HashSet::new(), 0.0, 6);
        if tags.is_empty() {
            continue;
        }
        // Two large areas must not have the same label: the second area gets its next typical tag
        let mut label: Vec<String> = tags.iter().take(2).cloned().collect();
        for other in tags.iter().skip(2) {
            if !used.contains(&label.join(" · ")) {
                break;
            }
            label = vec![tags[0].clone(), other.clone()];
        }
        used.insert(label.join(" · "));
        out.push(rows.region(&members, 0, &label));
        rows.divide(&members, 1, &label.iter().cloned().collect(), &corpus, &mut out);
    }
    out.sort_by(|a, b| a.level.cmp(&b.level).then(b.count.cmp(&a.count)));
    out
}

/// The layout of the map, as the build keeps it in the database
pub struct Layout {
    pub signature: Option<String>,
    /// (id, position, cell) of each unique row
    pub rows: Vec<(String, [f32; 2], [f32; 2])>,
    pub cell: (f64, f64),
    pub regions: Vec<Region>,
}

/// The signature of a layout: the method, the ids of the rows of the map, and the bytes of the
/// stored embedding that each row uses on the map (a library row uses the embedding of its first
/// AniList row). anime_vec/engine.py computes the same value. Both programs read these bytes from
/// the database, thus the value does not depend on the arithmetic of the program.
pub fn signature(ids: &[&str], vectors: &[&[f32]]) -> String {
    let mut hash = sha1_smol::Sha1::new();
    hash.update(b"layout v2\n");
    hash.update(VERSION.as_bytes());
    hash.update(ids.join("\n").as_bytes());
    for v in vectors {
        for x in *v {
            hash.update(&x.to_le_bytes());
        }
    }
    hash.digest().to_string()
}

/// The kept layout of the database: the position and the cell of each row, by its id
pub type Kept = HashMap<String, ([f32; 2], [f32; 2])>;

/// `_build_layout` and `_build_regions` for the engine. `raw` gives the stored embedding of each row.
/// `kept` is the layout in the database, if its signature is the signature of now.
pub fn compute(engine: &Engine, raw: &HashMap<String, Vec<f32>>, kept: Option<Kept>, kept_cell: Option<(f64, f64)>) -> Layout {
    let unique = engine.unique_rows();
    let ids: Vec<&str> = unique.iter().map(|&i| engine.rows[i].id.as_str()).collect();
    let n = unique.len();
    if n < 2 {
        return Layout { signature: None, rows: Vec::new(), cell: (1.0, CELL_ASPECT), regions: Vec::new() };
    }
    // The shows of the user select their cell first (by tier), then the catalog by score
    let tier_rank = |t: Option<&str>| match t {
        Some("S") => 0,
        Some("A") => 1,
        Some("B") => 2,
        Some("C") => 3,
        Some("D") => 4,
        _ => 5,
    };
    let mut order: Vec<usize> = (0..n).collect();
    let key = |k: usize| {
        let r = &engine.rows[unique[k]];
        let score = engine.rows[engine.tag_source(unique[k])].score.unwrap_or(0.0);
        (if r.owned { 0 } else { 1 }, tier_rank(r.tier.as_deref()), -score, k)
    };
    order.sort_by(|&a, &b| {
        let (ka, kb) = (key(a), key(b));
        ka.0.cmp(&kb.0).then(ka.1.cmp(&kb.1)).then(ka.2.total_cmp(&kb.2)).then(ka.3.cmp(&kb.3))
    });
    let x: Vec<f32> = unique.iter().flat_map(|&i| engine.eff_row(i).iter().copied()).collect();
    let (points, cells, cell, signature) = if n >= TSNE_MIN_ROWS {
        let vectors: Vec<&[f32]> = unique.iter().map(|&i| raw[&engine.rows[engine.tag_source(i)].id].as_slice()).collect();
        let signature = signature(&ids, &vectors);
        let reuse = kept.zip(kept_cell).filter(|(k, _)| ids.iter().all(|id| k.contains_key(*id)));
        match reuse {
            Some((kept, cell)) => {
                println!("the map layout of the database is still correct");
                let points = ids.iter().map(|id| kept[*id].0).collect::<Vec<_>>();
                let cells = ids.iter().map(|id| kept[*id].1).collect::<Vec<_>>();
                (points, cells, cell, Some(signature))
            }
            None => {
                let started = std::time::Instant::now();
                let points = fit_unit_square(&tsne::tsne(&x, n, engine.dim));
                println!("t-SNE of {n} shows in {:.1?}", started.elapsed());
                let (cells, w, h) = grid_layout(&points, &order);
                (points, cells, (w, h), Some(signature))
            }
        }
    } else {
        let start = tsne::pca_2d(&x, n, engine.dim);
        let points = fit_unit_square(&start.iter().map(|p| [p[0] as f32, p[1] as f32]).collect::<Vec<_>>());
        let (cells, w, h) = grid_layout(&points, &order);
        (points, cells, (w, h), None)
    };
    let size = engine.tag_names.len();
    let tags: Vec<Vec<f32>> = unique.iter().map(|&i| engine.tags[i].to_dense(size)).collect();
    let regions = if signature.is_some() { regions(&points, &cells, tags, &engine.tag_names) } else { Vec::new() };
    let rows = ids.iter().zip(points.iter().zip(&cells)).map(|(id, (p, c))| (id.to_string(), *p, *c)).collect();
    Layout { signature, rows, cell, regions }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_unit_square_keeps_the_aspect() {
        let p = fit_unit_square(&[[0.0, 0.0], [2.0, 1.0], [1.0, 0.5]]);
        assert_eq!(p, vec![[0.0, 0.25], [1.0, 0.75], [0.5, 0.5]]);
    }

    #[test]
    fn each_point_gets_its_own_cell() {
        let points: Vec<[f32; 2]> = (0..300).map(|i| [0.5 + (i % 7) as f32 * 1e-4, 0.5 + (i % 5) as f32 * 1e-4]).collect();
        let order: Vec<usize> = (0..points.len()).collect();
        let (cells, dx, dy) = grid_layout(&points, &order);
        let keys: HashSet<(i64, i64)> = cells.iter().map(|c| ((c[0] as f64 / dx).round() as i64, (c[1] as f64 / dy).round() as i64)).collect();
        assert_eq!(keys.len(), points.len());
        assert!((dy / dx - CELL_ASPECT).abs() < 1e-12);
    }

    #[test]
    fn round_is_the_round_of_python() {
        assert_eq!(round_half_even(2.5), 2);
        assert_eq!(round_half_even(3.5), 4);
        assert_eq!(round_half_even(-2.5), -2);
        assert_eq!(round_half_even(2.6), 3);
    }

    #[test]
    fn kmeans_finds_two_far_groups() {
        let mut points: Vec<[f64; 2]> = (0..20).map(|i| [i as f64 * 0.01, 0.0]).collect();
        points.extend((0..20).map(|i| [10.0 + i as f64 * 0.01, 0.0]));
        let labels = kmeans(&points, 2, 0);
        assert!(labels[..20].iter().all(|&l| l == labels[0]));
        assert!(labels[20..].iter().all(|&l| l == labels[20]));
        assert_ne!(labels[0], labels[20]);
    }
}
