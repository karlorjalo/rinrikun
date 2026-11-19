//! The rinrikun server in Rust. It reads the database of the Python server and computes the same
//! results. With --write it also changes the data of the user, as the Python server does.
//!
//!   rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--write]   the HTTP server
//!   rinrikun reference <database> <out.json>   write the results of the engine as JSON

mod anilist;
mod api;
mod changes;
mod engine;
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
        _ => {
            eprintln!("usage: rinrikun serve <database> [--listen address]... [--root folder] [--web address] [--write]
       rinrikun reference <database> <out.json>");
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}
