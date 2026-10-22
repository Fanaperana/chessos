//! Edits on the FAT boot partition inside an image file: screen file (device
//! tree), boot logo. Uses the fatfs crate (lookups are case-insensitive, which
//! FAT needs: names are often stored 8.3 upper case like EXTLINUX.CONF).
use crate::parts::Part;
use anyhow::{Context, Result};
use serde::Serialize;
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::path::Path;

type Fs = fatfs::FileSystem<fscommon::BufStream<fscommon::StreamSlice<std::fs::File>>>;

fn open(img: &Path, p: &Part) -> Result<Fs> {
    let f = OpenOptions::new().read(true).write(true).open(img)?;
    let slice = fscommon::StreamSlice::new(f, p.start, p.start + p.size)?;
    Ok(fatfs::FileSystem::new(fscommon::BufStream::new(slice), fatfs::FsOptions::new())
        .context("boot partition is not a readable FAT filesystem")?)
}

#[derive(Serialize, Clone, Debug)]
pub struct BootInfo {
    pub dtbs: Vec<String>,    // "rf3536k4ka.dtb", "ScreenFiles/Panel 5/rf3536k3ka.dtb", ...
    pub current_dtb: Option<String>,
    pub has_logo: bool,
    pub files: Vec<String>,
}

fn read_text(fs: &Fs, path: &str) -> Option<String> {
    let mut f = fs.root_dir().open_file(path).ok()?;
    let mut s = String::new();
    f.read_to_string(&mut s).ok()?;
    Some(s)
}

pub fn inspect(img: &Path, p: &Part) -> Result<BootInfo> {
    let fs = open(img, p)?;
    let root = fs.root_dir();
    let mut dtbs = Vec::new();
    let mut files = Vec::new();
    let mut has_logo = false;
    for e in root.iter().flatten() {
        let name = e.file_name();
        if e.is_dir() {
            files.push(format!("{}/", name));
            if name.eq_ignore_ascii_case("ScreenFiles") {
                for panel in e.to_dir().iter().flatten().filter(|x| x.is_dir() && x.file_name() != "." && x.file_name() != "..") {
                    for f in panel.to_dir().iter().flatten() {
                        if f.file_name().to_lowercase().ends_with(".dtb") {
                            dtbs.push(format!("ScreenFiles/{}/{}", panel.file_name(), f.file_name()));
                        }
                    }
                }
            }
        } else {
            files.push(name.clone());
            if name.to_lowercase().ends_with(".dtb") {
                dtbs.insert(0, name.clone());
            }
            if name.eq_ignore_ascii_case("logo.bmp") {
                has_logo = true;
            }
        }
    }
    let current_dtb = read_text(&fs, "extlinux/extlinux.conf").and_then(|c| {
        c.lines().find(|l| l.trim_start().starts_with("FDT ")).map(|l| l.trim().trim_start_matches("FDT").trim().trim_start_matches('/').to_string())
    });
    Ok(BootInfo { dtbs, current_dtb, has_logo, files })
}

fn write_file(fs: &Fs, path: &str, data: &[u8]) -> Result<()> {
    let mut f = fs.root_dir().create_file(path)?;
    f.truncate()?;
    f.write_all(data)?;
    f.flush()?;
    Ok(())
}

/// Use `dtb` (a root file or a ScreenFiles/... path) as the screen file.
pub fn set_dtb(img: &Path, p: &Part, dtb: &str) -> Result<()> {
    let fs = open(img, p)?;
    let name = dtb.rsplit('/').next().unwrap().to_string();
    if dtb.contains('/') {
        let mut data = Vec::new();
        fs.root_dir().open_file(dtb)?.read_to_end(&mut data)?;
        write_file(&fs, &name, &data)?;
    }
    let conf = read_text(&fs, "extlinux/extlinux.conf").context("no extlinux/extlinux.conf on the boot partition")?;
    let new: Vec<String> = conf
        .lines()
        .map(|l| if l.trim_start().starts_with("FDT ") { format!("  FDT /{}", name) } else { l.to_string() })
        .collect();
    write_file(&fs, "extlinux/extlinux.conf", (new.join("\n") + "\n").as_bytes())?;
    fs.unmount()?;
    Ok(())
}

/// Install the boot logo (keeps the original as logo_orig.bmp once).
pub fn set_logo(img: &Path, p: &Part, bmp: &[u8]) -> Result<()> {
    let fs = open(img, p)?;
    if let Ok(mut f) = fs.root_dir().open_file("logo.bmp") {
        if fs.root_dir().open_file("logo_orig.bmp").is_err() {
            let mut old = Vec::new();
            f.read_to_end(&mut old)?;
            drop(f);
            write_file(&fs, "logo_orig.bmp", &old)?;
        }
    }
    write_file(&fs, "logo.bmp", bmp)?;
    write_file(&fs, "logo_kernel.bmp", bmp)?;
    fs.unmount()?;
    Ok(())
}
