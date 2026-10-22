// Prevents an extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<String> = std::env::args().collect();
    // elevated helper mode: `chessos-studio --helper job.json` (flash / update a card)
    if args.len() >= 3 && args[1] == "--helper" {
        std::process::exit(studio_lib::run_helper(std::path::Path::new(&args[2])));
    }
    studio_lib::run()
}
