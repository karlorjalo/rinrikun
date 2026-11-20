//! Small numeric functions of the engine. They have the rules of the NumPy functions of the first
//! version of the app, with the same names.

use rayon::prelude::*;

/// The dot product of two vectors. Eight sums in parallel let the compiler use vector instructions.
pub fn dot(a: &[f32], b: &[f32]) -> f32 {
    let mut sums = [0f32; 8];
    let chunks = a.len() / 8;
    for c in 0..chunks {
        for l in 0..8 {
            sums[l] += a[c * 8 + l] * b[c * 8 + l];
        }
    }
    let mut total: f32 = sums.iter().sum();
    for i in chunks * 8..a.len() {
        total += a[i] * b[i];
    }
    total
}

/// A sparse vector: the positions of the values that are not 0 (in increasing order), and the values
#[derive(Clone, Debug, Default)]
pub struct Sparse {
    pub index: Vec<usize>,
    pub value: Vec<f32>,
}

impl Sparse {
    pub fn dot_dense(&self, dense: &[f32]) -> f32 {
        self.index.iter().zip(&self.value).map(|(&i, &v)| v * dense[i]).sum()
    }

    pub fn dot_dense64(&self, dense: &[f64]) -> f64 {
        self.index.iter().zip(&self.value).map(|(&i, &v)| v as f64 * dense[i]).sum()
    }

    /// The vector with all values, `size` values long
    pub fn to_dense(&self, size: usize) -> Vec<f32> {
        let mut out = vec![0f32; size];
        for (&i, &v) in self.index.iter().zip(&self.value) {
            out[i] = v;
        }
        out
    }
}

pub fn mean(x: &[f64]) -> f64 {
    if x.is_empty() { f64::NAN } else { x.iter().sum::<f64>() / x.len() as f64 }
}

/// The standard deviation of the values (of all values, not of a sample)
pub fn std(x: &[f64]) -> f64 {
    let m = mean(x);
    (x.iter().map(|v| (v - m) * (v - m)).sum::<f64>() / x.len() as f64).sqrt()
}

/// `_zscore`: the values minus their mean, divided by their standard deviation. 0 if the values are all equal.
pub fn zscore(x: &[f64]) -> Vec<f64> {
    if x.is_empty() {
        return Vec::new();
    }
    let sd = std(x);
    if sd > 1e-9 {
        let m = mean(x);
        x.iter().map(|v| (v - m) / sd).collect()
    } else {
        vec![0.0; x.len()]
    }
}

/// `_scale_like`: the z-scores of x with the mean and the standard deviation of `reference`
pub fn scale_like(reference: &[f64], x: &[f64]) -> Vec<f64> {
    if reference.is_empty() {
        return vec![0.0; x.len()];
    }
    let sd = std(reference);
    if sd <= 1e-9 {
        return vec![0.0; x.len()];
    }
    let m = mean(reference);
    x.iter().map(|v| (v - m) / sd).collect()
}

/// `_ranks`: the rank of each value (0 = lowest). Equal values get the mean of their ranks.
pub fn ranks(x: &[f64]) -> Vec<f64> {
    let mut order: Vec<usize> = (0..x.len()).collect();
    order.sort_by(|&a, &b| x[a].total_cmp(&x[b]));
    let mut out = vec![0.0; x.len()];
    let mut start = 0;
    while start < order.len() {
        let mut end = start;
        while end + 1 < order.len() && x[order[end + 1]] == x[order[start]] {
            end += 1;
        }
        let rank = (start + end) as f64 / 2.0;
        for &i in &order[start..=end] {
            out[i] = rank;
        }
        start = end + 1;
    }
    out
}

/// The positions of the values from the highest value to the lowest. Equal values keep their order.
pub fn argsort_desc(x: &[f64]) -> Vec<usize> {
    let mut order: Vec<usize> = (0..x.len()).collect();
    order.sort_by(|&a, &b| x[b].total_cmp(&x[a]));
    order
}

/// `np.searchsorted(sorted, v, side="left")`: the number of values of `sorted` that are less than v
pub fn count_below(sorted: &[f64], v: f64) -> usize {
    sorted.partition_point(|&r| r < v)
}

/// `bisect_right`: the number of limits that are not more than v
pub fn bisect_right(limits: &[f64], v: f64) -> i64 {
    limits.partition_point(|&l| l <= v) as i64
}

/// The nearest number with one decimal. A value exactly between two numbers goes to the even
/// digit. The text conversion does the rounding, with the exact value of the number.
pub fn round1(x: f64) -> f64 {
    format!("{x:.1}").parse().unwrap_or(x)
}

/// `_knn_score`: score each candidate by the mean weighted similarity to its k nearest liked shows.
/// `sim(c, l)` is the similarity of candidate c to liked show l. Return the scores, and for each
/// candidate the liked show with the highest weighted similarity.
pub fn knn_score<F>(candidates: usize, liked_w: &[f32], sim: F, k: usize) -> (Vec<f64>, Vec<usize>)
where
    F: Fn(usize, usize) -> f32 + Sync,
{
    let k = k.min(liked_w.len()).max(1);
    (0..candidates)
        .into_par_iter()
        .map(|c| {
            let mut weighted: Vec<f32> = liked_w.iter().enumerate().map(|(l, &w)| sim(c, l) * w).collect();
            let mut best = 0;
            for l in 1..weighted.len() {
                if weighted[l] > weighted[best] {
                    best = l;
                }
            }
            weighted.select_nth_unstable_by(k - 1, |a, b| b.total_cmp(a));
            let score = weighted[..k].iter().map(|&v| v as f64).sum::<f64>() / k as f64;
            (score, best)
        })
        .unzip()
}

/// `_knn_score_without`: as the score of `knn_score`, but each candidate ignores the liked shows
/// for which `skip(c, l)` is true
pub fn knn_score_without<F, S>(candidates: usize, liked_w: &[f32], sim: F, skip: S, k: usize) -> Vec<f64>
where
    F: Fn(usize, usize) -> f32 + Sync,
    S: Fn(usize, usize) -> bool + Sync,
{
    let k = k.min(liked_w.len()).max(1);
    (0..candidates)
        .into_par_iter()
        .map(|c| {
            let mut weighted: Vec<f32> = liked_w
                .iter()
                .enumerate()
                .map(|(l, &w)| if skip(c, l) { f32::NEG_INFINITY } else { sim(c, l) * w })
                .collect();
            weighted.select_nth_unstable_by(k - 1, |a, b| b.total_cmp(a));
            let valid: Vec<f64> = weighted[..k].iter().filter(|v| v.is_finite()).map(|&v| v as f64).collect();
            valid.iter().sum::<f64>() / valid.len().max(1) as f64
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round1_goes_to_the_even_digit_and_uses_the_exact_value() {
        // round(0.25, 1) == 0.2, round(0.35, 1) == 0.3 (0.35 is a little less than 0.35),
        // round(99.25, 1) == 99.2, round(2.675, 1) == 2.7
        assert_eq!(round1(0.25), 0.2);
        assert_eq!(round1(0.35), 0.3);
        assert_eq!(round1(99.25), 99.2);
        assert_eq!(round1(99.75), 99.8);
        assert_eq!(round1(2.675), 2.7);
        assert_eq!(round1(-0.04), -0.0);
    }

    #[test]
    fn ranks_give_equal_values_their_mean_rank() {
        assert_eq!(ranks(&[3.0, 1.0, 3.0, 2.0]), vec![2.5, 0.0, 2.5, 1.0]);
    }

    #[test]
    fn zscore_of_equal_values_is_zero() {
        assert_eq!(zscore(&[2.0, 2.0]), vec![0.0, 0.0]);
        let z = zscore(&[1.0, 2.0, 3.0]);
        assert!((z[2] - 1.224744871391589).abs() < 1e-12);
    }

    #[test]
    fn count_below_is_searchsorted_left() {
        let sorted = [1.0, 2.0, 2.0, 3.0];
        assert_eq!(count_below(&sorted, 2.0), 1);
        assert_eq!(count_below(&sorted, 2.5), 3);
        assert_eq!(count_below(&sorted, 9.0), 4);
    }

    #[test]
    fn knn_uses_the_k_best_weighted_similarities() {
        let w = [1.0f32, 2.0, 1.0];
        let sims = [[0.5f32, 0.1, 0.9]];
        let (score, best) = knn_score(1, &w, |c, l| sims[c][l], 2);
        assert!((score[0] - (0.9 + 0.5) / 2.0).abs() < 1e-6);
        assert_eq!(best[0], 2);
        let without = knn_score_without(1, &w, |c, l| sims[c][l], |_, l| l == 2, 5);
        assert!((without[0] - (0.5 + 0.2) / 2.0).abs() < 1e-6);
    }
}
