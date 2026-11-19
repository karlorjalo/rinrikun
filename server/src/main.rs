//! The rinrikun server in Rust. In this phase it reads the database of the Python server and
//! computes the same results; the Python server stays the live server.
//!
//!   rinrikun reference <database> <out.json>   write the results of the engine as JSON

mod engine;
mod math;
mod reference;
mod store;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("reference") => reference::run(&args[1..]),
        _ => {
            eprintln!("usage: rinrikun reference <database> <out.json>");
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}
