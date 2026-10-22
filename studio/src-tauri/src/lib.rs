//! ChessOS Studio: build and flash single-app handheld OS images.
mod bootfs;
mod bundle;
mod disks;
mod fetch;
mod flash;
mod parts;
mod pipeline;
mod profiles;
mod rootfs;
mod splash;

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

pub use flash::run_helper;

/// Today's date (UTC) as YYYY-MM-DD without extra crates.
pub fn today() -> String {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let z = (secs / 86400) as i64 + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = yoe + era * 400 + if m <= 2 { 1 } else { 0 };
    format!("{:04}-{:02}-{:02}", y, m, d)
}

#[derive(Serialize, Deserialize, Clone)]
struct Settings {
    work_dir: String,
}

struct AppState {
    data_dir: PathBuf,
    settings: Mutex<Settings>,
}

impl AppState {
    fn work(&self) -> PathBuf {
        PathBuf::from(&self.settings.lock().unwrap().work_dir)
    }
}

#[derive(Serialize, Clone)]
struct JobEvent {
    id: String,
    kind: String, // progress | done | error
    stage: String,
    msg: String,
    done: u64,
    total: u64,
    result: Option<serde_json::Value>,
}

fn emit(app: &AppHandle, id: &str, kind: &str, stage: &str, msg: String, done: u64, total: u64, result: Option<serde_json::Value>) {
    let _ = app.emit("job", JobEvent { id: id.into(), kind: kind.into(), stage: stage.into(), msg, done, total, result });
}

/// Run `f` on a worker thread, streaming its progress as "job" events.
fn spawn_job<F>(app: AppHandle, id: &str, f: F)
where
    F: FnOnce(&dyn Fn(pipeline::Progress)) -> anyhow::Result<serde_json::Value> + Send + 'static,
{
    let id = id.to_string();
    std::thread::spawn(move || {
        let a2 = app.clone();
        let id2 = id.clone();
        let report = move |p: pipeline::Progress| emit(&a2, &id2, "progress", &p.stage, p.msg, p.done, p.total, None);
        match f(&report) {
            Ok(v) => emit(&app, &id, "done", "", "done".into(), 0, 0, Some(v)),
            Err(e) => emit(&app, &id, "error", "", format!("{:#}", e), 0, 0, None),
        }
    });
}

fn err(e: anyhow::Error) -> String {
    format!("{:#}", e)
}

// ---- commands -------------------------------------------------------------------
#[derive(Serialize)]
struct StudioState {
    data_dir: String,
    work_dir: String,
    free_gb: Option<f64>,
    profiles: Vec<profiles::Profile>,
    tools: rootfs::ToolStatus,
    platform: String,
}

fn free_space_gb(p: &Path) -> Option<f64> {
    if !cfg!(windows) {
        return None;
    }
    let drive = p.to_string_lossy().chars().next()?;
    let out = disks::powershell(&format!("(Get-Volume -DriveLetter {}).SizeRemaining", drive)).ok()?;
    out.trim().parse::<f64>().ok().map(|b| b / 1e9)
}

#[tauri::command]
fn get_state(st: State<AppState>) -> StudioState {
    let work = st.work();
    StudioState {
        data_dir: st.data_dir.to_string_lossy().to_string(),
        work_dir: work.to_string_lossy().to_string(),
        free_gb: free_space_gb(&work),
        profiles: profiles::all(&st.data_dir),
        tools: rootfs::Debugfs::check(),
        platform: std::env::consts::OS.into(),
    }
}

#[tauri::command]
fn set_work_dir(st: State<AppState>, path: String) -> Result<(), String> {
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    let mut s = st.settings.lock().unwrap();
    s.work_dir = path;
    std::fs::write(st.data_dir.join("settings.json"), serde_json::to_string_pretty(&*s).unwrap()).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn save_profile(st: State<AppState>, profile: profiles::Profile) -> Result<(), String> {
    profiles::save(&st.data_dir, &profile).map_err(err)
}

#[tauri::command]
fn inspect_app(path: String) -> Result<bundle::AppInfo, String> {
    bundle::inspect(Path::new(&path)).map_err(err)
}

#[tauri::command]
fn make_splash(path: String, w: u32, h: u32, fit: String) -> Result<String, String> {
    let s = splash::make(Path::new(&path), w, h, &fit, [19, 31, 36]).map_err(err)?;
    Ok(format!("data:image/png;base64,{}", base64_encode(&s.preview_png)))
}

fn base64_encode(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len() * 4 / 3 + 4);
    for c in data.chunks(3) {
        let b = [c[0], *c.get(1).unwrap_or(&0), *c.get(2).unwrap_or(&0)];
        let n = (b[0] as u32) << 16 | (b[1] as u32) << 8 | b[2] as u32;
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if c.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if c.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}

#[tauri::command]
fn list_disks() -> Result<Vec<disks::Disk>, String> {
    disks::list().map_err(err)
}

/// Download/decompress the base image and inspect it (job events, result = ImageInfo).
#[tauri::command]
fn prepare_base(app: AppHandle, st: State<AppState>, profile_id: String, base_id: Option<String>, local_path: Option<String>, service: String) {
    let work = st.work();
    let profs = profiles::all(&st.data_dir);
    spawn_job(app, "base", move |r| {
        let base = profs.iter().find(|p| p.id == profile_id).and_then(|p| p.base_images.iter().find(|b| Some(&b.id) == base_id.as_ref())).cloned();
        let img = pipeline::prepare_base(&work, base.as_ref(), local_path.as_deref(), r)?;
        r(pipeline::Progress { stage: "inspect".into(), msg: "looking inside the image".into(), done: 0, total: 0 });
        let info = pipeline::inspect_image(&img, &service, &work)?;
        Ok(serde_json::to_value(info)?)
    });
}

#[tauri::command]
fn start_build(app: AppHandle, st: State<AppState>, job: pipeline::BuildJob) {
    let work = st.work();
    spawn_job(app, "build", move |r| {
        let out = pipeline::build_image(&work, &job, r)?;
        let size = std::fs::metadata(&out)?.len();
        Ok(serde_json::json!({"image": out.to_string_lossy(), "size": size}))
    });
}

/// "App only": copy the app into an ArkOS card's Ports menu (no admin needed).
#[tauri::command]
fn install_ports(app: AppHandle, st: State<AppState>, app_path: String, drive: String) {
    let work = st.work();
    spawn_job(app, "ports", move |r| {
        let a = bundle::inspect(Path::new(&app_path))?;
        let staged = bundle::stage(&a, &work)?;
        let ports = PathBuf::from(format!("{}:\\ports", drive.trim_end_matches(':')));
        bundle::install_to_ports(&a, &staged, &ports, &|m| r(pipeline::Progress { stage: "ports".into(), msg: m, done: 0, total: 0 }))?;
        Ok(serde_json::json!({"ports": ports.to_string_lossy()}))
    });
}

/// Flash an image, or update the app on a card, through the elevated helper.
#[tauri::command]
fn start_card_job(app: AppHandle, st: State<AppState>, mode: String, disk: u32, image: Option<String>, app_path: Option<String>, service: Option<String>) -> Result<(), String> {
    let work = st.work();
    let d = disks::get(disk).map_err(err)?;
    if !d.removable {
        return Err(format!("Disk {} is not a removable USB/SD card.", disk));
    }
    let (appinfo, staged) = match (&mode[..], &app_path) {
        ("update", Some(p)) => {
            let a = bundle::inspect(Path::new(p)).map_err(err)?;
            let s = bundle::stage(&a, &work).map_err(err)?;
            (Some(a), Some(s.to_string_lossy().to_string()))
        }
        _ => (None, None),
    };
    let log = work.join(format!("{}.log", mode));
    let _ = std::fs::remove_file(&log);
    let job = flash::HelperJob {
        mode: mode.clone(),
        disk,
        size: d.size,
        log: log.to_string_lossy().to_string(),
        work: work.to_string_lossy().to_string(),
        image,
        app: appinfo,
        staged,
        service,
    };
    let job_file = work.join(format!("{}-job.json", mode));
    std::fs::write(&job_file, serde_json::to_string_pretty(&job).unwrap()).map_err(|e| e.to_string())?;
    flash::launch_elevated(&job_file).map_err(err)?;
    // follow the helper's log
    let id = mode.clone();
    std::thread::spawn(move || {
        let mut seen = 0usize;
        let started = std::time::Instant::now();
        loop {
            std::thread::sleep(std::time::Duration::from_millis(400));
            let text = std::fs::read_to_string(&log).unwrap_or_default();
            let lines: Vec<&str> = text.lines().collect();
            if lines.is_empty() && started.elapsed().as_secs() > 180 {
                emit(&app, &id, "error", "", "The helper did not start (was the administrator prompt answered?)".into(), 0, 0, None);
                return;
            }
            for l in &lines[seen..] {
                let (tag, rest) = l.split_once(' ').unwrap_or((l, ""));
                match tag {
                    "P" => {
                        let f: Vec<&str> = rest.splitn(3, ' ').collect();
                        let done = f.first().and_then(|x| x.parse().ok()).unwrap_or(0);
                        let total = f.get(1).and_then(|x| x.parse().ok()).unwrap_or(0);
                        emit(&app, &id, "progress", "card", f.get(2).unwrap_or(&"").to_string(), done, total, None);
                    }
                    "L" => emit(&app, &id, "progress", "card", rest.into(), 0, 0, None),
                    "OK" => {
                        emit(&app, &id, "done", "card", rest.into(), 0, 0, Some(serde_json::json!({"message": rest})));
                        return;
                    }
                    "E" => {
                        emit(&app, &id, "error", "card", rest.into(), 0, 0, None);
                        return;
                    }
                    _ => {}
                }
            }
            seen = lines.len();
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    //! Run against a real image:  set STUDIO_TEST_IMG=...arkos.img  STUDIO_TEST_APP=...device\chessos
    //!   cargo test -- --ignored --nocapture
    use super::*;

    fn env(k: &str) -> Option<PathBuf> {
        std::env::var(k).ok().map(PathBuf::from)
    }

    #[test]
    fn date_format() {
        assert_eq!(today().len(), 10);
    }

    #[test]
    #[ignore]
    fn inspect_real_image() {
        let img = env("STUDIO_TEST_IMG").expect("STUDIO_TEST_IMG");
        let work = std::env::temp_dir().join("studio-test");
        std::fs::create_dir_all(&work).unwrap();
        let info = pipeline::inspect_image(&img, "emulationstation.service", &work).unwrap();
        println!("{}", serde_json::to_string_pretty(&info).unwrap());
        assert!(info.layout.boot().is_some() && info.layout.root().is_some());
    }

    #[test]
    #[ignore]
    fn build_real_image() {
        let img = env("STUDIO_TEST_IMG").expect("STUDIO_TEST_IMG");
        let app = env("STUDIO_TEST_APP").expect("STUDIO_TEST_APP");
        let work = env("STUDIO_TEST_WORK").unwrap_or_else(|| std::env::temp_dir().join("studio-test"));
        std::fs::create_dir_all(&work).unwrap();
        let job = pipeline::BuildJob {
            base_img: img.to_string_lossy().to_string(),
            out_name: "studio-test".into(),
            app_path: Some(app.to_string_lossy().to_string()),
            dtb: None,
            splash_path: env("STUDIO_TEST_SPLASH").map(|p| p.to_string_lossy().to_string()),
            splash_fit: Some("contain".into()),
            screen: (640, 480),
            service: "emulationstation.service".into(),
        };
        let out = pipeline::build_image(&work, &job, &|p| {
            if p.total == 0 || p.done == p.total {
                println!("[{}] {}", p.stage, p.msg)
            }
        })
        .unwrap();
        let info = pipeline::inspect_image(&out, "emulationstation.service", &work).unwrap();
        println!("installed apps: {:?}", info.root.as_ref().map(|r| &r.installed_apps));
        assert_eq!(info.root.unwrap().installed_apps, vec![bundle::sanitize(&app.file_name().unwrap().to_string_lossy())]);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            let settings: Settings = std::fs::read_to_string(data_dir.join("settings.json"))
                .ok()
                .and_then(|t| serde_json::from_str(&t).ok())
                .unwrap_or(Settings { work_dir: data_dir.join("work").to_string_lossy().to_string() });
            std::fs::create_dir_all(&settings.work_dir)?;
            app.manage(AppState { data_dir, settings: Mutex::new(settings) });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_state, set_work_dir, save_profile, inspect_app, make_splash, list_disks,
            prepare_base, start_build, install_ports, start_card_job
        ])
        .run(tauri::generate_context!())
        .expect("error while running ChessOS Studio");
}
