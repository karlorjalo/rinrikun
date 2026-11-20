//! The similarity of each show to some shows, kept in memory.
//!
//! The match and the lists compare each candidate with each liked show: about 20 000 x 200 dot
//! products of 768 values, which was most of the time of the match. The vectors change only when
//! the engine loads again (the weekly build), but the match is computed again after each change of
//! the user. Thus the engine keeps the similarities: one column for each liked show, with its
//! similarity to each show. After a change, only a show that is new in the liked shows needs a
//! new column.
//!
//! A column has the same bits as the direct computation, thus each result stays the same.

use std::sync::Arc;

use rayon::prelude::*;

use crate::math::dot;
use crate::memo::MemoMap;

/// The similarity columns of an engine. A column is 4 bytes for each show (about 85 KB for
/// 21 000 shows). The engine asks only for the columns of the shows that the user rated, thus
/// the memory stays small: 350 shows are about 30 MB.
#[derive(Default)]
pub struct SimColumns {
    columns: MemoMap<usize, Arc<Vec<f32>>>,
}

impl SimColumns {
    /// The column of each of `rows`, in the same order: `column[j]` is the dot product of the
    /// vector of row j and the vector of the row of the column. `vectors` has `dim` values for
    /// each row. The columns that are not there are computed in parallel.
    ///
    /// Do not call it in a rayon closure (see `Memo`): get the columns before the parallel work.
    pub fn get(&self, vectors: &[f32], dim: usize, rows: &[usize]) -> Vec<Arc<Vec<f32>>> {
        let count = vectors.len() / dim;
        let vector = |i: usize| &vectors[i * dim..(i + 1) * dim];
        let mut missing: Vec<usize> = rows.iter().copied().filter(|r| self.columns.get(r).is_none()).collect();
        missing.sort_unstable();
        missing.dedup();
        let computed: Vec<Arc<Vec<f32>>> =
            missing.par_iter().map(|&r| Arc::new((0..count).into_par_iter().map(|j| dot(vector(j), vector(r))).collect())).collect();
        // A different thread can have the same column at this moment: the first one stays
        for (&r, column) in missing.iter().zip(computed) {
            self.columns.get_or_compute(&r, || column);
        }
        rows.iter().map(|r| self.columns.get(r).expect("each column is there now")).collect()
    }

    /// The number of columns in memory
    pub fn len(&self) -> usize {
        self.columns.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::math::dot;
    use std::sync::Arc;

    const DIM: usize = 11;
    const ROWS: usize = 9;

    /// Some rows of fixed values: no row is equal to a different row
    fn vectors() -> Vec<f32> {
        (0..ROWS * DIM).map(|k| ((k * 37 + 11) % 23) as f32 / 23.0 - 0.4 + (k / DIM) as f32 * 0.01).collect()
    }

    fn row(m: &[f32], i: usize) -> &[f32] {
        &m[i * DIM..(i + 1) * DIM]
    }

    #[test]
    fn a_column_has_the_dot_product_of_each_row() {
        let m = vectors();
        let cache = SimColumns::default();
        let columns = cache.get(&m, DIM, &[2, 7]);
        assert_eq!(columns.len(), 2);
        for (column, &of) in columns.iter().zip(&[2usize, 7]) {
            assert_eq!(column.len(), ROWS);
            for j in 0..ROWS {
                // The same bits as the direct computation: a list with the cache is the list without it
                assert_eq!(column[j].to_bits(), dot(row(&m, j), row(&m, of)).to_bits(), "row {j}, column of {of}");
            }
        }
    }

    #[test]
    fn a_column_is_computed_one_time() {
        let m = vectors();
        let cache = SimColumns::default();
        let first = cache.get(&m, DIM, &[1, 4]);
        assert_eq!(cache.len(), 2);
        let second = cache.get(&m, DIM, &[4, 5, 1]);
        assert_eq!(cache.len(), 3);
        // The same memory, not a new computation
        assert!(Arc::ptr_eq(&first[1], &second[0]));
        assert!(Arc::ptr_eq(&first[0], &second[2]));
    }

    #[test]
    fn the_order_and_the_repeats_of_the_rows_stay() {
        let m = vectors();
        let cache = SimColumns::default();
        let columns = cache.get(&m, DIM, &[3, 0, 3]);
        assert_eq!(columns.len(), 3);
        assert!(Arc::ptr_eq(&columns[0], &columns[2]));
        assert_eq!(columns[1][0].to_bits(), dot(row(&m, 0), row(&m, 0)).to_bits());
        assert_eq!(cache.len(), 2);
        assert!(cache.get(&m, DIM, &[]).is_empty());
    }
}
