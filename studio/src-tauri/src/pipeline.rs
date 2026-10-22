//! The build: base image -> copy -> boot partition edits -> app into the root
//! filesystem -> ready-to-flash image.
use crate::bundle::{self, AppInfo};
use crate::{bootfs, fetch, parts, profiles::BaseImage, rootfs, splash};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Serialize, Clone, Debug)]
pub struct Progress {
    pub stage: String,
    pub msg: String,
    pub done: u64,
    pub total: u64,
}

pub type Report<'a> = &'a dyn Fn(Progress);

fn say(r: Report, stage: &str, msg: impl Into<String>) {
    r(Progress { stage: stage.into(), msg: msg.into(), done: 0, total: 0 });
}

fn bar<'a>(r: Report<'a>, stage: &'a str, label: &'a str) -> impl Fn(u64, u64) + 'a {
    let last = std::cell::Cell::new(0u64);
    move |d, t| {
        // throttle: about every 1%
        if t == 0 || d == t || d.saturating_sub(last.get()) * 100 >= t {
            last.set(d);
            r(Progress { stage: stage.into(), msg: label.into(), done: d, total: t });
        }
    }
}

/// Make sure the base image is downloaded and decompressed; returns the .img path.
pub fn prepare_base(work: &Path, base: Option<&BaseImage>, local: Option<&str>, r: Report) -> Result<PathBuf> {
    let src: PathBuf = if let Some(p) = local {
        PathBuf::from(p)
    } else {
        let b = base.context("no base image chosen")?;
        let dest = work.join("downloads").join(&b.file);
        let url = b.url.as_ref().context("this base image has no download link")?;
        say(r, "base", format!("{} ({})", b.name, url));
        fetch::download(url, &dest, b.size, &bar(r, "base", "downloading the base OS"))?;
        dest
    };
    if !src.exists() {
        bail!("{} not found", src.display());
    }
    let is_xz = src.extension().map(|e| e == "xz").unwrap_or(false);
    if !is_xz {
        return Ok(src);
    }
    let name = src.file_stem().unwrap().to_string_lossy().to_string();
    let img = work.join("base").join(&name);
    if img.exists() {
        say(r, "base", format!("using the cached {}", name));
        return Ok(img);
    }
    std::fs::create_dir_all(img.parent().unwrap())?;
    fetch::unxz(&src, &img, &bar(r, "base", "decompressing"))?;
    Ok(img)
}

#[derive(Serialize, Clone, Debug)]
pub struct ImageInfo {
    pub path: String,
    pub size: u64,
    pub layout: parts::Layout,
    pub boot: Option<bootfs::BootInfo>,
    pub root: Option<rootfs::RootInfo>,
}

/// Look inside an image: partitions, boot files (screen files, logo), the system.
pub fn inspect_image(img: &Path, service: &str, work: &Path) -> Result<ImageInfo> {
    let size = std::fs::metadata(img)?.len();
    let layout = parts::layout_of_file(img)?;
    let boot = match layout.boot() {
        Some(p) => bootfs::inspect(img, p).ok(),
        None => None,
    };
    let mut root = None;
    if let Some(p) = layout.root() {
        if rootfs::Debugfs::check().ok {
            // the root filesystem must be a file of its own for debugfs
            let tmp = work.join("inspect_root.ext4");
            fetch::copy_range(img, p.start, p.size, &tmp, 0, &|_, _| {})?;
            root = rootfs::inspect(&rootfs::Debugfs::new(), &tmp, service).ok();
            let _ = std::fs::remove_file(&tmp);
        }
    }
    Ok(ImageInfo { path: img.to_string_lossy().to_string(), size, layout, boot, root })
}

#[derive(Deserialize, Clone, Debug)]
pub struct BuildJob {
    pub base_img: String,
    pub out_name: String,
    pub app_path: Option<String>,
    pub dtb: Option<String>,
    pub splash_path: Option<String>,
    pub splash_fit: Option<String>,
    pub screen: (u32, u32),
    pub service: String,
}

/// Build the flashable image. Returns its path.
pub fn build_image(work: &Path, job: &BuildJob, r: Report) -> Result<PathBuf> {
    let base = PathBuf::from(&job.base_img);
    let out_dir = work.join("out");
    std::fs::create_dir_all(&out_dir)?;
    let out = out_dir.join(format!("{}.img", bundle::sanitize(&job.out_name)));
    say(r, "copy", format!("copying the base image to {}", out.display()));
    fetch::copy_file(&base, &out, &bar(r, "copy", "copying the base image"))?;
    let layout = parts::layout_of_file(&out)?;
    say(r, "inspect", format!("{} partition table: {}", layout.table.to_uppercase(),
        layout.parts.iter().map(|p| format!("#{} {} {:.1} GB", p.index, p.fs, p.size as f64 / 1e9)).collect::<Vec<_>>().join(", ")));
    let boot = layout.boot().context("no FAT boot partition found in the base image")?.clone();
    if let Some(dtb) = &job.dtb {
        say(r, "boot", format!("screen file: {}", dtb));
        bootfs::set_dtb(&out, &boot, dtb)?;
    }
    if let Some(sp) = &job.splash_path {
        say(r, "boot", "boot logo");
        let s = splash::make(Path::new(sp), job.screen.0, job.screen.1, job.splash_fit.as_deref().unwrap_or("contain"), [19, 31, 36])?;
        bootfs::set_logo(&out, &boot, &s.bmp)?;
    }
    if let Some(app_path) = &job.app_path {
        let app: AppInfo = bundle::inspect(Path::new(app_path))?;
        let root = layout.root().context("no ext4 system partition found in the base image")?.clone();
        say(r, "app", format!("staging {} ({:.1} MB)", app.title, app.size_mb));
        let staged = bundle::stage(&app, work)?;
        let rootfile = work.join("root.ext4");
        fetch::copy_range(&out, root.start, root.size, &rootfile, 0, &bar(r, "app", "extracting the system partition"))?;
        let dbg = rootfs::Debugfs::new();
        let last = rootfs::install(&dbg, &rootfile, &staged, &app, &job.service, &work.join("tmp"), &|m| say(r, "app", m))?;
        say(r, "app", format!("filesystem check: {}", last));
        fetch::copy_range(&rootfile, 0, root.size, &out, root.start, &bar(r, "app", "writing the system partition back"))?;
        let _ = std::fs::remove_file(&rootfile);
    } else {
        say(r, "app", "no app: the image boots the stock OS");
    }
    Ok(out)
}
