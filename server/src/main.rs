//! The rinrikun server in Rust. It reads the database of the Python server and computes the same
//! results. With --write it also changes the data of the user, as the Python server does. The
//! command `build` is the weekly rebuild of the catalog (build.py).
//!
//!   rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--write]   the HTTP server
//!   rinrikun build [--root folder] [--db file] [--refresh-anilist] [--pool-only]   the rebuild of the catalog
//!   rinrikun build-check <database>   compare the text hashes and show the layout signature (reads only)
//!   rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]   the offline test of the recommendations (reads only)
//!   rinrikun reference <database> <out.json>   write the results of the engine as JSON

mod anilist;
mod api;
mod build;
mod changes;
mod engine;
mod evaluate;
mod frames;
mod lists;
mod math;
mod reference;
mod server;
mod store;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("reference") => reference::run(&args[1..]),
        Some("serve") => server::run(&args[1..]),
        Some("build") => build::run(&args[1..]),
        Some("build-check") => build::check(&args[1..]),
        Some("evaluate") => evaluate::run(&args[1..]),
        _ => {
            eprintln!(
                "usage: rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--write]
       rinrikun build [--root folder] [--db file] [--refresh-anilist] [--pool-only]
       rinrikun build-check <database>
       rinrikun evaluate [--db file] [--tiers] [--recent N] [--benchmark label]
       rinrikun reference <database> <out.json>"
            );
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}
