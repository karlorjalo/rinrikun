//! t-SNE with the Barnes-Hut approximation, with the steps of sklearn.manifold.TSNE that
//! anime_vec/layout.py uses: perplexity 30, the cosine distance, the PCA start, the learning rate
//! "auto", 250 steps with early exaggeration 12, then the steps up to 1000 with momentum 0.8.
//!
//! The result is not equal to the result of sklearn to the last digit: sklearn adds the forces of
//! the points in more than one thread, in an order that changes. The two maps keep the same
//! neighbours: see the comparison in the README of the server.

use nalgebra::{DMatrix, SymmetricEigen};
use rayon::prelude::*;

pub const PERPLEXITY: f64 = 30.0;
const EARLY_EXAGGERATION: f64 = 12.0;
const EXPLORATION_ITER: usize = 250;
const MAX_ITER: usize = 1000;
const N_ITER_CHECK: usize = 50;
const ANGLE: f32 = 0.5;
const MIN_GAIN: f32 = 0.01;
const MIN_GRAD_NORM: f64 = 1e-7;
const PERPLEXITY_TOLERANCE: f64 = 1e-5;
const EPSILON_DBL: f64 = 1e-8;
const MACHINE_EPSILON: f64 = f64::EPSILON;
const FLOAT32_TINY: f32 = f32::MIN_POSITIVE;
/// Two points nearer than this are the same point in the quad tree
const DUPLICATE: f32 = 1e-6;

/// The rows of `x` (n rows of `dim` values) on their two principal components, with the sign of
/// sklearn: the largest value of each component is positive. Return (n × 2) and nothing else.
pub fn pca_2d(x: &[f32], n: usize, dim: usize) -> Vec<[f64; 2]> {
    if n < 2 || dim < 1 {
        return vec![[0.0, 0.0]; n];
    }
    let mut mean = vec![0f64; dim];
    for row in x.chunks_exact(dim) {
        for (m, v) in mean.iter_mut().zip(row) {
            *m += *v as f64;
        }
    }
    mean.iter_mut().for_each(|m| *m /= n as f64);
    // The centered rows as the columns of a matrix (dim × n)
    let centered = DMatrix::<f64>::from_iterator(dim, n, x.chunks_exact(dim).flat_map(|row| row.iter().zip(&mean).map(|(v, m)| *v as f64 - m)));
    let covariance = &centered * centered.transpose();
    let eigen = SymmetricEigen::new(covariance);
    let mut order: Vec<usize> = (0..dim).collect();
    order.sort_by(|&a, &b| eigen.eigenvalues[b].total_cmp(&eigen.eigenvalues[a]));
    let mut out = vec![[0.0; 2]; n];
    for (axis, &k) in order.iter().take(2).enumerate() {
        let mut v: Vec<f64> = eigen.eigenvectors.column(k).iter().copied().collect();
        let largest = v.iter().copied().fold(0.0f64, |best, x| if x.abs() > best.abs() { x } else { best });
        if largest < 0.0 {
            v.iter_mut().for_each(|x| *x = -*x);
        }
        for (i, column) in centered.column_iter().enumerate() {
            out[i][axis] = column.iter().zip(&v).map(|(a, b)| a * b).sum();
        }
    }
    out
}

/// The k nearest neighbours of each row by the cosine distance, without the row itself:
/// (index, distance) in the order of the distance. `squared_neighbours` gives the squares of the
/// distances, as the t-SNE of sklearn uses them.
fn nearest(x: &[f32], n: usize, dim: usize, k: usize) -> Vec<Vec<(usize, f32)>> {
    // Unit rows: the cosine distance is 1 - the dot product
    let unit: Vec<f32> = x
        .chunks_exact(dim)
        .flat_map(|row| {
            let norm = row.iter().map(|v| (*v as f64) * (*v as f64)).sum::<f64>().sqrt().max(1e-12);
            row.iter().map(move |v| (*v as f64 / norm) as f32)
        })
        .collect();
    let all = DMatrix::<f32>::from_column_slice(dim, n, &unit);
    const BLOCK: usize = 128;
    (0..n.div_ceil(BLOCK))
        .into_par_iter()
        .flat_map_iter(|b| {
            let start = b * BLOCK;
            let size = BLOCK.min(n - start);
            let dots = all.columns(start, size).transpose() * &all;
            (0..size).map(move |r| {
                let i = start + r;
                let mut d: Vec<(usize, f32)> = (0..n).filter(|&j| j != i).map(|j| (j, (1.0 - dots[(r, j)]).clamp(0.0, 2.0))).collect();
                let key = |a: &(usize, f32), b: &(usize, f32)| a.1.total_cmp(&b.1).then(a.0.cmp(&b.0));
                if d.len() > k {
                    d.select_nth_unstable_by(k - 1, key);
                    d.truncate(k);
                }
                d.sort_by(key);
                d
            })
        })
        .collect()
}

/// The neighbours with the squares of their distances. sklearn squares the distances of the
/// neighbours for each metric ("knn return the euclidean distance but we need it squared"), the
/// cosine distance too.
fn squared_neighbours(x: &[f32], n: usize, dim: usize, k: usize) -> Vec<Vec<(usize, f32)>> {
    let mut neighbours = nearest(x, n, dim, k);
    for row in neighbours.iter_mut() {
        row.iter_mut().for_each(|(_, d)| *d *= *d);
    }
    neighbours
}

/// `_binary_search_perplexity`: the conditional probabilities of the neighbours of one row, with
/// the perplexity PERPLEXITY
fn conditional(distances: &[f32]) -> Vec<f64> {
    let desired_entropy = PERPLEXITY.ln();
    let (mut beta, mut beta_min, mut beta_max) = (1.0f64, f64::NEG_INFINITY, f64::INFINITY);
    let mut p = vec![0f64; distances.len()];
    for _ in 0..100 {
        let mut sum_p = 0.0;
        for (pj, &d) in p.iter_mut().zip(distances) {
            *pj = (-(d as f64) * beta).exp();
            sum_p += *pj;
        }
        if sum_p == 0.0 {
            sum_p = EPSILON_DBL;
        }
        let mut sum_disti_pi = 0.0;
        for (pj, &d) in p.iter_mut().zip(distances) {
            *pj /= sum_p;
            sum_disti_pi += d as f64 * *pj;
        }
        let entropy_diff = sum_p.ln() + beta * sum_disti_pi - desired_entropy;
        if entropy_diff.abs() <= PERPLEXITY_TOLERANCE {
            break;
        }
        if entropy_diff > 0.0 {
            beta_min = beta;
            beta = if beta_max == f64::INFINITY { beta * 2.0 } else { (beta + beta_max) / 2.0 };
        } else {
            beta_max = beta;
            beta = if beta_min == f64::NEG_INFINITY { beta / 2.0 } else { (beta + beta_min) / 2.0 };
        }
    }
    p
}

/// The joint probabilities P (symmetric, sum 1) as rows of (column, value), with the columns in order
fn joint_probabilities(neighbours: &[Vec<(usize, f32)>]) -> Vec<Vec<(usize, f64)>> {
    let n = neighbours.len();
    let conditional: Vec<Vec<f64>> = neighbours.par_iter().map(|row| conditional(&row.iter().map(|&(_, d)| d).collect::<Vec<_>>())).collect();
    let mut rows: Vec<Vec<(usize, f64)>> = vec![Vec::new(); n];
    for (i, row) in neighbours.iter().enumerate() {
        for (&(j, _), &p) in row.iter().zip(&conditional[i]) {
            rows[i].push((j, p));
            rows[j].push((i, p));
        }
    }
    let mut total = 0.0;
    for row in rows.iter_mut() {
        row.sort_by_key(|&(j, _)| j);
        let mut merged: Vec<(usize, f64)> = Vec::with_capacity(row.len());
        for &(j, p) in row.iter() {
            match merged.last_mut() {
                Some(last) if last.0 == j => last.1 += p,
                _ => merged.push((j, p)),
            }
        }
        total += merged.iter().map(|&(_, p)| p).sum::<f64>();
        *row = merged;
    }
    let total = total.max(MACHINE_EPSILON);
    for row in rows.iter_mut() {
        row.iter_mut().for_each(|(_, p)| *p /= total);
    }
    rows
}

/// One cell of the quad tree of `_QuadTree` in sklearn
#[derive(Clone)]
struct Cell {
    min: [f32; 2],
    max: [f32; 2],
    center: [f32; 2],
    squared_max_width: f32,
    barycenter: [f32; 2],
    size: u32,
    leaf: bool,
    children: [i32; 4],
}

impl Cell {
    fn new(min: [f32; 2], max: [f32; 2]) -> Cell {
        let center = [(min[0] + max[0]) / 2.0, (min[1] + max[1]) / 2.0];
        let w = [max[0] - min[0], max[1] - min[1]];
        Cell { min, max, center, squared_max_width: (w[0] * w[0]).max(w[1] * w[1]), barycenter: [0.0; 2], size: 0, leaf: true, children: [-1; 4] }
    }
}

struct QuadTree {
    cells: Vec<Cell>,
}

impl QuadTree {
    /// `build_tree`: insert the points one after the other
    fn build(points: &[[f32; 2]]) -> QuadTree {
        let mut min = [f32::INFINITY; 2];
        let mut max = [f32::NEG_INFINITY; 2];
        for p in points {
            for ax in 0..2 {
                min[ax] = min[ax].min(p[ax]);
                max[ax] = max[ax].max(p[ax]);
            }
        }
        // As sklearn: a small offset, so that the largest value is inside the root cell
        for ax in 0..2 {
            max[ax] = (max[ax] * (1.0 + 1e-3 * max[ax].signum())).max(max[ax] + 1e-3);
        }
        let mut tree = QuadTree { cells: vec![Cell::new(min, max)] };
        for p in points {
            tree.insert(*p, 0);
        }
        tree
    }

    fn child_slot(cell: &Cell, point: [f32; 2]) -> usize {
        let mut slot = 0;
        for ax in 0..2 {
            slot *= 2;
            if point[ax] >= cell.center[ax] {
                slot += 1;
            }
        }
        slot
    }

    /// `_insert_point_in_new_child`: a new leaf below `parent` with `size` points at `point`
    fn new_child(&mut self, parent: usize, point: [f32; 2], size: u32) {
        let cell = &self.cells[parent];
        let mut min = [0.0; 2];
        let mut max = [0.0; 2];
        for ax in 0..2 {
            if point[ax] >= cell.center[ax] {
                min[ax] = cell.center[ax];
                max[ax] = cell.max[ax];
            } else {
                min[ax] = cell.min[ax];
                max[ax] = cell.center[ax];
            }
        }
        let slot = Self::child_slot(cell, point);
        let mut child = Cell::new(min, max);
        child.barycenter = point;
        child.size = size;
        let id = self.cells.len();
        self.cells.push(child);
        let parent = &mut self.cells[parent];
        parent.leaf = false;
        parent.children[slot] = id as i32;
    }

    /// `insert_point`
    fn insert(&mut self, point: [f32; 2], cell_id: usize) {
        let mut cell_id = cell_id;
        loop {
            let cell = &mut self.cells[cell_id];
            let n = cell.size as f32;
            if cell.size == 0 {
                cell.size = 1;
                cell.barycenter = point;
                return;
            }
            if !cell.leaf {
                for ax in 0..2 {
                    cell.barycenter[ax] = (n * cell.barycenter[ax] + point[ax]) / (n + 1.0);
                }
                cell.size += 1;
                let child = cell.children[Self::child_slot(cell, point)];
                if child == -1 {
                    self.new_child(cell_id, point, 1);
                    return;
                }
                cell_id = child as usize;
                continue;
            }
            if (0..2).all(|ax| (point[ax] - cell.barycenter[ax]).abs() <= DUPLICATE) {
                cell.size += 1;
                return;
            }
            // A leaf with one point (or duplicates): move its points to a child, then insert again
            let (barycenter, size) = (cell.barycenter, cell.size);
            self.new_child(cell_id, barycenter, size);
        }
    }

    /// `summarize` and the negative force of `compute_gradient_negative` for one point: the sum
    /// of q·size and the force without the division by the sum of q
    fn negative(&self, point: [f32; 2], squared_theta: f32) -> (f64, [f64; 2]) {
        let mut sum_q = 0f64;
        let mut force = [0f64; 2];
        let mut stack = vec![0usize];
        while let Some(id) = stack.pop() {
            let cell = &self.cells[id];
            let d = [point[0] - cell.barycenter[0], point[1] - cell.barycenter[1]];
            let dist2 = d[0] * d[0] + d[1] * d[1];
            let duplicate = d[0].abs() <= DUPLICATE && d[1].abs() <= DUPLICATE;
            // No force of a point on itself
            if duplicate && cell.leaf {
                continue;
            }
            if cell.leaf || cell.squared_max_width / dist2 < squared_theta {
                let q = 1.0 / (1.0 + dist2 as f64);
                let size = cell.size as f64;
                sum_q += size * q;
                let mult = size * q * q;
                force[0] += mult * d[0] as f64;
                force[1] += mult * d[1] as f64;
            } else {
                // The children in the reverse order on the stack: the first child comes first
                for &child in cell.children.iter().rev() {
                    if child != -1 {
                        stack.push(child as usize);
                    }
                }
            }
        }
        (sum_q, force)
    }
}

/// `_kl_divergence_bh`: the gradient (with the factor 4 of one degree of freedom) and, if
/// `with_error`, the KL divergence
fn gradient(p: &[Vec<(usize, f32)>], points: &[[f32; 2]], with_error: bool) -> (f64, Vec<f32>) {
    let tree = QuadTree::build(points);
    let negative: Vec<(f64, [f64; 2])> = points.par_iter().map(|&pt| tree.negative(pt, ANGLE * ANGLE)).collect();
    // As sklearn: at least the machine epsilon, so that the division below is possible
    let sum_q: f64 = negative.iter().map(|n| n.0).sum::<f64>().max(MACHINE_EPSILON);
    let parts: Vec<([f32; 2], f64)> = (0..points.len())
        .into_par_iter()
        .map(|i| {
            let mut force = [0f32; 2];
            let mut error = 0f64;
            for &(j, pij) in &p[i] {
                let b = [points[i][0] - points[j][0], points[i][1] - points[j][1]];
                let dij = b[0] * b[0] + b[1] * b[1];
                let qij = 1.0 / (1.0 + dij);
                if with_error {
                    let q = (qij as f64 / sum_q) as f32;
                    error += pij as f64 * ((pij.max(FLOAT32_TINY) / q.max(FLOAT32_TINY)) as f64).ln();
                }
                let m = pij * qij;
                force[0] += m * b[0];
                force[1] += m * b[1];
            }
            (force, error)
        })
        .collect();
    let mut grad = vec![0f32; points.len() * 2];
    let mut error = 0f64;
    for (i, (positive, e)) in parts.into_iter().enumerate() {
        error += e;
        for ax in 0..2 {
            let g = positive[ax] as f64 - negative[i].1[ax] / sum_q;
            grad[i * 2 + ax] = (g as f32) * 4.0;
        }
    }
    (error, grad)
}

/// `_gradient_descent`: steps from `start` to `max_iter`. Return the last step.
#[allow(clippy::too_many_arguments)]
fn descend(p: &[Vec<(usize, f32)>], params: &mut [f32], update: &mut [f64], gains: &mut [f32], start: usize, max_iter: usize, momentum: f64, learning_rate: f64, without_progress: usize) -> usize {
    let mut best_error = f64::MAX;
    let mut best_iter = start;
    let mut i = start;
    for step in start..max_iter {
        i = step;
        let check = (step + 1) % N_ITER_CHECK == 0;
        let points: Vec<[f32; 2]> = params.chunks_exact(2).map(|c| [c[0], c[1]]).collect();
        let (error, mut grad) = gradient(p, &points, check || step == max_iter - 1);
        for k in 0..params.len() {
            if update[k] * grad[k] as f64 >= 0.0 {
                gains[k] *= 0.8;
            } else {
                gains[k] += 0.2;
            }
            gains[k] = gains[k].max(MIN_GAIN);
            grad[k] *= gains[k];
            update[k] = momentum * update[k] - learning_rate * grad[k] as f64;
            params[k] = (params[k] as f64 + update[k]) as f32;
        }
        if check {
            let grad_norm = grad.iter().map(|g| (*g as f64) * (*g as f64)).sum::<f64>().sqrt();
            if error < best_error {
                best_error = error;
                best_iter = step;
            } else if step - best_iter > without_progress {
                break;
            }
            if grad_norm <= MIN_GRAD_NORM {
                break;
            }
        }
    }
    i
}

/// The t-SNE map of the rows of `x` (n rows of `dim` values): n points in 2D
pub fn tsne(x: &[f32], n: usize, dim: usize) -> Vec<[f32; 2]> {
    let k = (n - 1).min((3.0 * PERPLEXITY + 1.0) as usize);
    let neighbours = squared_neighbours(x, n, dim, k);
    let joint = joint_probabilities(&neighbours);
    // The PCA start: the first component has the standard deviation 1e-4
    let start = pca_2d(x, n, dim);
    let first: Vec<f32> = start.iter().map(|p| p[0] as f32).collect();
    let mean = first.iter().map(|v| *v as f64).sum::<f64>() / n as f64;
    let std = (first.iter().map(|v| (*v as f64 - mean).powi(2)).sum::<f64>() / n as f64).sqrt();
    let mut params: Vec<f32> = start.iter().flat_map(|p| [(p[0] as f32 as f64 / std * 1e-4) as f32, (p[1] as f32 as f64 / std * 1e-4) as f32]).collect();
    let learning_rate = (n as f64 / EARLY_EXAGGERATION / 4.0).max(50.0);
    let mut update = vec![0f64; n * 2];
    let mut gains = vec![1f32; n * 2];
    let exaggerated: Vec<Vec<(usize, f32)>> = joint.iter().map(|row| row.iter().map(|&(j, p)| (j, (p * EARLY_EXAGGERATION) as f32)).collect()).collect();
    let it = descend(&exaggerated, &mut params, &mut update, &mut gains, 0, EXPLORATION_ITER, 0.5, learning_rate, EXPLORATION_ITER);
    let normal: Vec<Vec<(usize, f32)>> = joint.iter().map(|row| row.iter().map(|&(j, p)| (j, p as f32)).collect()).collect();
    descend(&normal, &mut params, &mut update, &mut gains, it + 1, MAX_ITER, 0.8, learning_rate, 300);
    params.chunks_exact(2).map(|c| [c[0], c[1]]).collect()
}

/// The part of the k nearest neighbours of each row in the embedding space that are also among
/// the k nearest neighbours of the row on the map: a measure of the quality of a map
pub fn neighbour_overlap(x: &[f32], n: usize, dim: usize, map: &[[f32; 2]], k: usize) -> f64 {
    let high = nearest(x, n, dim, k);
    let flat: Vec<f32> = map.iter().flat_map(|p| [p[0], p[1]]).collect();
    let low: Vec<Vec<usize>> = (0..n)
        .into_par_iter()
        .map(|i| {
            let mut d: Vec<(usize, f32)> = (0..n).filter(|&j| j != i).map(|j| (j, (flat[2 * i] - flat[2 * j]).powi(2) + (flat[2 * i + 1] - flat[2 * j + 1]).powi(2))).collect();
            d.select_nth_unstable_by(k - 1, |a, b| a.1.total_cmp(&b.1));
            d.truncate(k);
            d.into_iter().map(|(j, _)| j).collect()
        })
        .collect();
    let shared: usize = (0..n).map(|i| high[i].iter().filter(|(j, _)| low[i].contains(j)).count()).sum();
    shared as f64 / (n * k) as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_perplexity_search_gives_the_wanted_entropy() {
        let d: Vec<f32> = (0..91).map(|j| 0.2 + j as f32 * 0.005).collect();
        let p = conditional(&d);
        let entropy: f64 = -p.iter().filter(|&&v| v > 0.0).map(|v| v * v.ln()).sum::<f64>();
        assert!((entropy - PERPLEXITY.ln()).abs() < 1e-4, "{entropy}");
        assert!((p.iter().sum::<f64>() - 1.0).abs() < 1e-9);
    }

    #[test]
    fn the_map_keeps_two_groups_apart() {
        // Two groups of points around two different directions
        let (n, dim) = (200, 8);
        let mut x = vec![0f32; n * dim];
        let mut seed = 7u64;
        let mut random = || {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            ((seed >> 33) as f64 / (1u64 << 31) as f64) as f32 - 0.5
        };
        for i in 0..n {
            for d in 0..dim {
                x[i * dim + d] = random() * 0.3 + if (i < n / 2) == (d < dim / 2) { 1.0 } else { 0.0 };
            }
        }
        let map = tsne(&x, n, dim);
        let center = |range: std::ops::Range<usize>| {
            let c = range.clone().fold([0f64; 2], |acc, i| [acc[0] + map[i][0] as f64, acc[1] + map[i][1] as f64]);
            [c[0] / range.len() as f64, c[1] / range.len() as f64]
        };
        let (a, b) = (center(0..n / 2), center(n / 2..n));
        let spread = (0..n / 2).map(|i| ((map[i][0] as f64 - a[0]).powi(2) + (map[i][1] as f64 - a[1]).powi(2)).sqrt()).sum::<f64>() / (n / 2) as f64;
        let gap = ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt();
        assert!(gap > 2.0 * spread, "gap {gap}, spread {spread}");
        assert!(neighbour_overlap(&x, n, dim, &map, 10) > 0.3);
    }

    #[test]
    fn the_quad_tree_counts_each_point_and_merges_duplicates() {
        let points = vec![[0.0, 0.0], [1.0, 1.0], [1.0, 1.0], [0.5, 0.25], [-1.0, 0.5]];
        let tree = QuadTree::build(&points);
        assert_eq!(tree.cells[0].size, 5);
        let mean = [(0.0 + 1.0 + 1.0 + 0.5 - 1.0) / 5.0, (0.0 + 1.0 + 1.0 + 0.25 + 0.5) / 5.0];
        assert!((tree.cells[0].barycenter[0] - mean[0]).abs() < 1e-6 && (tree.cells[0].barycenter[1] - mean[1]).abs() < 1e-6);
    }
}
