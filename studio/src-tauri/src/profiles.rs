//! Device profiles: which handheld, which base OS images, screen size,
//! default screen file (device tree) and the front-end service to replace.
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct BaseImage {
    pub id: String,
    pub name: String,
    pub url: Option<String>,
    /// file name in the download cache (or an absolute path for local images)
    pub file: String,
    /// expected size of the downloaded file, if known
    pub size: Option<u64>,
    #[serde(default)]
    pub notes: String,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Profile {
    pub id: String,
    pub name: String,
    pub maker: String,
    pub verified: bool,
    pub screen: (u32, u32),
    pub default_dtb: Option<String>,
    pub frontend_service: String,
    #[serde(default)]
    pub notes: String,
    pub base_images: Vec<BaseImage>,
}

const BUILTIN: &str = include_str!("../profiles.json");

/// Built-in profiles followed by the user's own (profiles/*.json in the data dir).
pub fn all(data_dir: &Path) -> Vec<Profile> {
    let mut out: Vec<Profile> = serde_json::from_str(BUILTIN).expect("profiles.json");
    let dir = data_dir.join("profiles");
    if let Ok(rd) = std::fs::read_dir(&dir) {
        for e in rd.flatten() {
            if e.path().extension().map(|x| x == "json").unwrap_or(false) {
                if let Ok(txt) = std::fs::read_to_string(e.path()) {
                    if let Ok(p) = serde_json::from_str::<Profile>(&txt) {
                        out.retain(|q| q.id != p.id);
                        out.push(p);
                    }
                }
            }
        }
    }
    out
}

pub fn save(data_dir: &Path, p: &Profile) -> anyhow::Result<()> {
    let dir = data_dir.join("profiles");
    std::fs::create_dir_all(&dir)?;
    std::fs::write(dir.join(format!("{}.json", p.id)), serde_json::to_string_pretty(p)?)?;
    Ok(())
}
