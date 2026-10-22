//! The app to boot: check a folder, stage a clean copy for the card, and
//! render the device-side scripts from the same templates the PowerShell
//! pipeline uses (device/system/*.in, compiled in).
use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const BOOT_SH: &str = include_str!("../../../device/system/boot.sh.in");
pub const DROPIN: &str = include_str!("../../../device/system/dropin.conf.in");
pub const PORT_SH: &str = include_str!("../../../device/system/port.sh.in");
pub const PORT_BOOTMODE_SH: &str = include_str!("../../../device/system/port-bootmode.sh.in");
pub const AUTOBOOT_SH: &str = include_str!("../../../device/system/autoboot.sh.in");
pub const BOOT_RUN_SH: &str = include_str!("../../../device/system/boot_run.sh.in");

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AppInfo {
    pub path: String,
    pub app: String,
    pub title: String,
    pub env: String,
    pub tagline: String,
    pub kind: String,     // "python" or "native"
    pub size_mb: f64,
    pub has_build_hook: bool,
    pub repo_root: Option<String>,
}

#[derive(Deserialize, Default)]
struct AppJson {
    title: Option<String>,
    env: Option<String>,
    tagline: Option<String>,
}

fn dir_size(p: &Path) -> u64 {
    let mut n = 0;
    if let Ok(rd) = std::fs::read_dir(p) {
        for e in rd.flatten() {
            let path = e.path();
            if path.is_dir() {
                if e.file_name() != "windows" && e.file_name() != "__pycache__" {
                    n += dir_size(&path);
                }
            } else if let Ok(m) = e.metadata() {
                n += m.len();
            }
        }
    }
    n
}

pub fn sanitize(name: &str) -> String {
    let s: String = name.to_lowercase().chars().map(|c| if c.is_ascii_alphanumeric() || c == '-' || c == '_' { c } else { '-' }).collect();
    s.trim_matches('-').to_string()
}

pub fn inspect(dir: &Path) -> Result<AppInfo> {
    let kind = if dir.join("start").is_file() {
        "native"
    } else if dir.join("main.py").is_file() {
        "python"
    } else {
        bail!("This folder has no main.py (Python app) and no 'start' launcher (native app).");
    };
    let folder = dir.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_else(|| "app".into());
    let app = sanitize(&folder);
    let meta: AppJson = std::fs::read_to_string(dir.join("app.json")).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
    let title = meta.title.unwrap_or_else(|| folder.clone());
    let env = meta.env.unwrap_or_else(|| app.to_uppercase().replace('-', "_"));
    // a repo checkout (setup.ps1 + appliance.json two levels up) can run the app's build hook
    let repo = dir.parent().and_then(|p| p.parent()).filter(|r| r.join("setup.ps1").is_file() && r.join("appliance.json").is_file());
    Ok(AppInfo {
        path: dir.to_string_lossy().to_string(),
        app,
        title,
        env,
        tagline: meta.tagline.unwrap_or_default(),
        kind: kind.into(),
        size_mb: dir_size(dir) as f64 / 1e6,
        has_build_hook: dir.join("build.ps1").is_file(),
        repo_root: repo.map(|r| r.to_string_lossy().to_string()),
    })
}

pub fn render(tpl: &str, a: &AppInfo) -> String {
    tpl.replace("\r\n", "\n")
        .replace("@APP@", &a.app)
        .replace("@TITLE@", &a.title)
        .replace("@ENV@", &a.env)
        .replace("@TAGLINE@", &a.tagline)
}

const SKIP_DIRS: &[&str] = &["__pycache__", "save", "shots", "test", ".git"];
const SKIP_FILES: &[&str] = &["crash.log", "log.txt", "boot_log.txt", "build.ps1"];
const LF_EXT: &[&str] = &["sh", "py", "txt", "pgn", "json", "conf"];

fn copy_tree(src: &Path, dst: &Path, rel: &Path) -> Result<()> {
    std::fs::create_dir_all(dst.join(rel))?;
    for e in std::fs::read_dir(src.join(rel))?.flatten() {
        let name = e.file_name().to_string_lossy().to_string();
        let r = rel.join(&name);
        if e.path().is_dir() {
            let in_bin = rel.file_name().map(|n| n == "bin").unwrap_or(false);
            if SKIP_DIRS.contains(&name.as_str()) || (in_bin && name == "windows") || (rel == Path::new("puzzles") && name == "daily") {
                continue;
            }
            copy_tree(src, dst, &r)?;
        } else {
            if SKIP_FILES.contains(&name.as_str()) || name.ends_with(".pyc") {
                continue;
            }
            let in_bin = r.components().any(|c| c.as_os_str() == "bin");
            let ext = Path::new(&name).extension().map(|x| x.to_string_lossy().to_string()).unwrap_or_default();
            if LF_EXT.contains(&ext.as_str()) && !in_bin {
                let data = std::fs::read(e.path())?;
                let text = String::from_utf8_lossy(&data).replace("\r\n", "\n");
                std::fs::write(dst.join(&r), if std::str::from_utf8(&data).is_ok() { text.into_bytes() } else { data })?;
            } else {
                std::fs::copy(e.path(), dst.join(&r))?;
            }
        }
    }
    Ok(())
}

/// Stage `a` into `work/stage/<app>` (+ data/build.json). Returns the staged folder.
pub fn stage(a: &AppInfo, work: &Path) -> Result<PathBuf> {
    let out = work.join("stage").join(&a.app);
    if out.exists() {
        std::fs::remove_dir_all(&out)?;
    }
    copy_tree(Path::new(&a.path), &out, Path::new(""))?;
    std::fs::create_dir_all(out.join("data"))?;
    let today = crate::today();
    std::fs::write(
        out.join("data").join("build.json"),
        serde_json::json!({"date": today, "app": a.app, "title": a.title}).to_string(),
    )?;
    if out.join("puzzles").is_dir() {
        std::fs::create_dir_all(out.join("puzzles").join("daily"))?;
    }
    std::fs::create_dir_all(out.join("tools"))?;
    std::fs::write(out.join("tools").join("autoboot.sh"), render(AUTOBOOT_SH, a))?;
    std::fs::write(out.join("tools").join("boot_run.sh"), render(BOOT_RUN_SH, a))?;
    Ok(out)
}

/// "App only" install: copy the staged app + port launchers into an ArkOS card's ports folder.
pub fn install_to_ports(a: &AppInfo, staged: &Path, ports: &Path, progress: &dyn Fn(String)) -> Result<()> {
    if !ports.is_dir() {
        bail!("{} not found - is this the EASYROMS drive?", ports.display());
    }
    let dst = ports.join(&a.app);
    if dst.exists() {
        progress(format!("replacing {}", dst.display()));
        std::fs::remove_dir_all(&dst)?;
    }
    copy_tree(staged, &dst, Path::new(""))?;
    std::fs::write(ports.join(format!("{}.sh", a.title)), render(PORT_SH, a))?;
    std::fs::write(ports.join(format!("{} Boot Mode.sh", a.title)), render(PORT_BOOTMODE_SH, a))?;
    progress(format!("copied {} to {}", a.title, ports.display()));
    Ok(())
}
