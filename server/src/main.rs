//! rinrikun: a personal anime recommender. This program is the server of the app and its tools.
//!
//!   rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--read-only]
//!       the HTTP server: the API, and the page through the page server (web/)
//!   rinrikun build [--root folder] [--db file] [--refresh-anilist] [--pool-only]
//!       the weekly rebuild of the catalog: Jellyfin, AniList, embeddings, map
//!   rinrikun build-check <database> [--embed N] [--tsne]
//!       check the text hashes, the embeddings and the map of a database (reads only)
//!   rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]
//!       the offline test of the recommendations: the hidden franchise test (reads only)

mod anilist;
mod api;
mod build;
mod changes;
mod engine;
mod evaluate;
mod frames;
mod lists;
mod math;
mod server;
mod store;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("serve") => server::run(&args[1..]),
        Some("build") => build::run(&args[1..]),
        Some("build-check") => build::check(&args[1..]),
        Some("evaluate") => evaluate::run(&args[1..]),
        _ => {
            eprintln!(
                "usage: rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--read-only]
       rinrikun build [--root folder] [--db file] [--refresh-anilist] [--pool-only]
       rinrikun build-check <database> [--embed N] [--tsne]
       rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]"
            );
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}
