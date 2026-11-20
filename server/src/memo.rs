//! Values that the server computes one time and keeps until the data changes.

use std::collections::HashMap;
use std::hash::Hash;
use std::sync::{Arc, Mutex, OnceLock};

/// A value that is computed one time. Callers at the same time wait for the same computation,
/// thus the server does not compute the same value two times in parallel.
///
/// `clear` forgets the value. A computation that started before `clear` fills a cell that no
/// caller reads again: a caller after `clear` never gets a value of the old data.
///
/// Do not call `get_or_compute` in a rayon closure: a rayon thread that waits can block the work
/// that it waits for.
pub struct Memo<T> {
    cell: Mutex<Arc<OnceLock<T>>>,
}

impl<T> Default for Memo<T> {
    fn default() -> Self {
        Memo { cell: Mutex::new(Arc::new(OnceLock::new())) }
    }
}

impl<T: Clone> Memo<T> {
    /// The value. The first caller computes it, and the callers at the same time wait for it.
    pub fn get_or_compute(&self, compute: impl FnOnce() -> T) -> T {
        // The lock is held only to take the cell, not during the computation
        let cell = self.cell.lock().unwrap().clone();
        cell.get_or_init(compute).clone()
    }

    /// The value, if it is computed
    #[allow(dead_code)]
    pub fn get(&self) -> Option<T> {
        self.cell.lock().unwrap().get().cloned()
    }

    /// Forget the value: the data changed
    pub fn clear(&self) {
        *self.cell.lock().unwrap() = Arc::new(OnceLock::new());
    }
}

/// One `Memo` for each key
pub struct MemoMap<K, V> {
    cells: Mutex<HashMap<K, Arc<OnceLock<V>>>>,
}

impl<K, V> Default for MemoMap<K, V> {
    fn default() -> Self {
        MemoMap { cells: Mutex::new(HashMap::new()) }
    }
}

impl<K: Eq + Hash + Clone, V: Clone> MemoMap<K, V> {
    /// The value of a key. The first caller computes it, and the callers at the same time wait for it.
    pub fn get_or_compute(&self, key: &K, compute: impl FnOnce() -> V) -> V {
        let cell = self.cells.lock().unwrap().entry(key.clone()).or_default().clone();
        cell.get_or_init(compute).clone()
    }

    /// Forget all values: the data changed
    pub fn clear(&self) {
        *self.cells.lock().unwrap() = HashMap::new();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::thread;
    use std::time::Duration;

    #[test]
    fn memo_computes_once_for_parallel_callers() {
        let memo = Arc::new(Memo::<i32>::default());
        let count = Arc::new(AtomicUsize::new(0));
        let threads: Vec<_> = (0..4)
            .map(|_| {
                let (memo, count) = (memo.clone(), count.clone());
                thread::spawn(move || {
                    memo.get_or_compute(|| {
                        thread::sleep(Duration::from_millis(50));
                        count.fetch_add(1, Ordering::SeqCst);
                        7
                    })
                })
            })
            .collect();
        let values: Vec<i32> = threads.into_iter().map(|t| t.join().unwrap()).collect();
        assert_eq!(count.load(Ordering::SeqCst), 1);
        assert_eq!(values, vec![7, 7, 7, 7]);
    }

    #[test]
    fn memo_computes_again_after_clear() {
        let memo = Memo::<i32>::default();
        let count = AtomicUsize::new(0);
        let compute = || {
            count.fetch_add(1, Ordering::SeqCst);
            5
        };
        assert_eq!(memo.get_or_compute(compute), 5);
        assert_eq!(memo.get_or_compute(compute), 5);
        assert_eq!(count.load(Ordering::SeqCst), 1);
        memo.clear();
        assert_eq!(memo.get(), None);
        assert_eq!(memo.get_or_compute(compute), 5);
        assert_eq!(count.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn memo_drops_value_of_old_generation() {
        let memo = Arc::new(Memo::<i32>::default());
        let old = {
            let memo = memo.clone();
            thread::spawn(move || {
                memo.get_or_compute(|| {
                    thread::sleep(Duration::from_millis(100));
                    1
                })
            })
        };
        thread::sleep(Duration::from_millis(20));
        memo.clear();
        assert_eq!(memo.get_or_compute(|| 2), 2);
        // The caller of the old computation gets its own value, but the memo keeps the new value
        assert_eq!(old.join().unwrap(), 1);
        assert_eq!(memo.get(), Some(2));
    }

    #[test]
    fn memo_map_keeps_one_value_per_key() {
        let map = MemoMap::<u8, String>::default();
        assert_eq!(map.get_or_compute(&1, || "one".into()), "one");
        assert_eq!(map.get_or_compute(&2, || "two".into()), "two");
        assert_eq!(map.get_or_compute(&1, || "other".into()), "one");
        map.clear();
        assert_eq!(map.get_or_compute(&1, || "new".into()), "new");
        assert_eq!(map.get_or_compute(&2, || "new two".into()), "new two");
    }
}
