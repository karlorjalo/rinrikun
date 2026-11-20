//! Values that the server computes one time and keeps until the data changes.

use std::collections::HashMap;
use std::hash::Hash;
use std::sync::{Arc, Mutex, OnceLock};

/// A value that is computed one time. Callers at the same time wait for the same computation,
/// thus the server does not compute the same value two times in parallel.
///
/// Do not call `get_or_compute` in a rayon closure: a rayon thread that waits can block the work
/// that it waits for.
pub struct Memo<T> {
    cell: OnceLock<T>,
}

impl<T> Default for Memo<T> {
    fn default() -> Self {
        Memo { cell: OnceLock::new() }
    }
}

impl<T: Clone> Memo<T> {
    /// The value. The first caller computes it, and the callers at the same time wait for it.
    pub fn get_or_compute(&self, compute: impl FnOnce() -> T) -> T {
        self.cell.get_or_init(compute).clone()
    }

    /// The value, if it is computed
    #[allow(dead_code)]
    pub fn get(&self) -> Option<T> {
        self.cell.get().cloned()
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
        // The code holds the lock only to take the cell, not during the computation
        let cell = self.cells.lock().unwrap().entry(key.clone()).or_default().clone();
        cell.get_or_init(compute).clone()
    }

    /// The value of a key, if it is computed. A look does not start a computation.
    pub fn get(&self, key: &K) -> Option<V> {
        self.cells.lock().unwrap().get(key).and_then(|cell| cell.get().cloned())
    }

    /// The number of keys with a value or with a computation that runs
    pub fn len(&self) -> usize {
        self.cells.lock().unwrap().len()
    }
}

/// A group of kept values that the owner forgets all at the same time: `reset` puts a new, empty
/// group in place. A new field of the group needs no line in a "clear" function, thus no kept
/// value can stay by mistake after the data changed.
///
/// A computation that started before `reset` fills the old group. No caller reads the old group
/// again: a caller after `reset` never gets a value of the old data.
pub struct Resettable<T> {
    current: Mutex<Arc<T>>,
}

impl<T: Default> Default for Resettable<T> {
    fn default() -> Self {
        Resettable { current: Mutex::new(Arc::new(T::default())) }
    }
}

impl<T: Default> Resettable<T> {
    /// The group of now. The code holds the lock only to take it, not while a caller uses it.
    pub fn get(&self) -> Arc<T> {
        self.current.lock().unwrap().clone()
    }

    /// Forget each value of the group: the data changed
    pub fn reset(&self) {
        *self.current.lock().unwrap() = Arc::new(T::default());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::mpsc;
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
    fn resettable_gives_a_new_group_after_reset() {
        let kept = Resettable::<Memo<i32>>::default();
        let count = AtomicUsize::new(0);
        let compute = || {
            count.fetch_add(1, Ordering::SeqCst);
            5
        };
        assert_eq!(kept.get().get_or_compute(compute), 5);
        assert_eq!(kept.get().get_or_compute(compute), 5);
        assert_eq!(count.load(Ordering::SeqCst), 1);
        kept.reset();
        assert_eq!(kept.get().get(), None);
        assert_eq!(kept.get().get_or_compute(compute), 5);
        assert_eq!(count.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn memo_drops_value_of_old_generation() {
        let kept = Arc::new(Resettable::<Memo<i32>>::default());
        let (started_tx, started_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel::<()>();
        let old = {
            let kept = kept.clone();
            thread::spawn(move || {
                kept.get().get_or_compute(|| {
                    started_tx.send(()).unwrap();
                    release_rx.recv().unwrap();
                    1
                })
            })
        };
        // The old computation runs now. The data changes before it ends.
        started_rx.recv().unwrap();
        kept.reset();
        assert_eq!(kept.get().get_or_compute(|| 2), 2);
        release_tx.send(()).unwrap();
        // The caller of the old computation gets its own value, but the new group keeps the new value
        assert_eq!(old.join().unwrap(), 1);
        assert_eq!(kept.get().get(), Some(2));
    }

    #[test]
    fn memo_map_get_gives_only_a_computed_value() {
        let map = MemoMap::<u8, String>::default();
        assert_eq!(map.get(&1), None);
        map.get_or_compute(&1, || "one".into());
        assert_eq!(map.get(&1), Some("one".to_string()));
        assert_eq!(map.get(&2), None);
        // A look at a key does not make a cell that a later computation would skip
        assert_eq!(map.get_or_compute(&2, || "two".into()), "two");
    }

    #[test]
    fn memo_map_keeps_one_value_per_key() {
        let map = MemoMap::<u8, String>::default();
        assert_eq!(map.get_or_compute(&1, || "one".into()), "one");
        assert_eq!(map.get_or_compute(&2, || "two".into()), "two");
        assert_eq!(map.get_or_compute(&1, || "other".into()), "one");
        assert_eq!(map.len(), 2);
    }
}
