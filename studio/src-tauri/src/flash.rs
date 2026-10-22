//! The elevated helper: the same executable relaunched as administrator with
//! `--helper job.json`. It flashes an image or updates the app on a card and
//! reports progress by appending lines to a log file the UI watches:
//!   P <done> <total> <label>  |  L <message>  |  OK <message>  |  E <message>
use crate::bundle::AppInfo;
use crate::disks;
use crate::rootfs::Debugfs;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const CHUNK: usize = 4 << 20;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct HelperJob {
    pub mode: String, // "flash" | "update"
    pub disk: u32,
    pub size: u64,
    pub log: String,
    pub work: String,
    pub image: Option<String>,
    pub app: Option<AppInfo>,
    pub staged: Option<String>,
    pub service: Option<String>,
}

struct Log(File);
impl Log {
    fn line(&mut self, s: &str) {
        let _ = writeln!(self.0, "{}", s.replace('\n', " | "));
        let _ = self.0.flush();
    }
}

fn disk_path(n: u32) -> String {
    format!(r"\\.\PhysicalDrive{}", n)
}

/// Same checks as tools/card_write.ps1, done again as administrator right before writing.
fn check_disk(job: &HelperJob) -> Result<()> {
    let d = disks::get(job.disk)?;
    if d.boot || d.system {
        bail!("disk {} is a system disk - nothing written", job.disk);
    }
    if !["USB", "SD", "MMC"].contains(&d.bus.as_str()) {
        bail!("disk {} is {} - not a USB/SD card, nothing written", job.disk, d.bus);
    }
    if d.size != job.size {
        bail!("disk {} changed size ({} bytes) since you picked it - nothing written", job.disk, d.size);
    }
    Ok(())
}

fn flash(job: &HelperJob, log: &mut Log) -> Result<()> {
    let img = PathBuf::from(job.image.as_ref().context("no image")?);
    let total = std::fs::metadata(&img)?.len();
    if total > job.size {
        bail!("the image ({} bytes) is bigger than the card", total);
    }
    let d = disks::get(job.disk)?;
    if d.style != "RAW" {
        log.line("L erasing the old partition table");
        disks::powershell(&format!("Clear-Disk -Number {} -RemoveData -RemoveOEM -Confirm:$false", job.disk))?;
    }
    // removable cards can't be taken offline on Windows: write everything after the
    // first MiB, then the partition tables last, so nothing gets mounted midway
    let head_len = 1 << 20;
    let mut src = File::open(&img)?;
    let mut dev = OpenOptions::new().read(true).write(true).open(disk_path(job.disk)).context("open disk (administrator?)")?;
    let mut head = vec![0u8; head_len];
    src.read_exact(&mut head)?;
    let mut hasher = Sha256::new();
    hasher.update(&head);
    dev.seek(SeekFrom::Start(head_len as u64))?;
    let mut buf = vec![0u8; CHUNK];
    let mut done = head_len as u64;
    let mut tick = 0;
    while done < total {
        let want = std::cmp::min(CHUNK as u64, total - done) as usize;
        src.read_exact(&mut buf[..want])?;
        let mut n = want;
        if n % 512 != 0 {
            let pad = 512 - n % 512;
            buf[n..n + pad].fill(0);
            n += pad;
        }
        hasher.update(&buf[..n]);
        dev.write_all(&buf[..n])?;
        done += want as u64;
        tick += 1;
        if tick % 4 == 0 {
            log.line(&format!("P {} {} writing", done, total));
        }
    }
    dev.seek(SeekFrom::Start(0))?;
    dev.write_all(&head)?;
    dev.flush()?;
    let want_hash = hasher.finalize();
    log.line("L verifying - reading everything back");
    let mut h2 = Sha256::new();
    dev.seek(SeekFrom::Start(0))?;
    let mut done = 0u64;
    let padded = total.div_ceil(512) * 512;
    while done < padded {
        let n = std::cmp::min(CHUNK as u64, padded - done) as usize;
        dev.read_exact(&mut buf[..n])?;
        h2.update(&buf[..n]);
        done += n as u64;
        tick += 1;
        if tick % 4 == 0 {
            log.line(&format!("P {} {} verifying", done, padded));
        }
    }
    if h2.finalize() != want_hash {
        bail!("VERIFY FAILED: the card does not match the image");
    }
    log.line(&format!("OK written and verified ({:.2} GB)", total as f64 / 1e9));
    Ok(())
}

fn update(job: &HelperJob, log: &mut Log) -> Result<()> {
    let app = job.app.as_ref().context("no app")?;
    let staged = PathBuf::from(job.staged.as_ref().context("no staged app")?);
    let service = job.service.clone().unwrap_or_else(|| "emulationstation.service".into());
    let work = PathBuf::from(&job.work);
    let mut dev = OpenOptions::new().read(true).write(true).open(disk_path(job.disk)).context("open disk (administrator?)")?;
    let layout = crate::parts::layout(&mut dev, job.size)?;
    let root = layout.root().context("no ext4 system partition on this card - was it made with 'Whole OS'?")?.clone();
    log.line(&format!("L system partition: {:.2} GB at {}", root.size as f64 / 1e9, root.start));
    let old = work.join("card_root.ext4");
    let new = work.join("card_root_new.ext4");
    {
        let mut out = File::create(&old)?;
        dev.seek(SeekFrom::Start(root.start))?;
        let mut buf = vec![0u8; CHUNK];
        let mut done = 0u64;
        while done < root.size {
            let n = std::cmp::min(CHUNK as u64, root.size - done) as usize;
            dev.read_exact(&mut buf[..n])?;
            out.write_all(&buf[..n])?;
            done += n as u64;
            if (done / CHUNK as u64) % 4 == 0 {
                log.line(&format!("P {} {} reading the card", done, root.size));
            }
        }
    }
    std::fs::copy(&old, &new)?;
    log.line(&format!("L installing {} into a copy", app.title));
    let dbg = Debugfs::new();
    let msgs = std::cell::RefCell::new(Vec::<String>::new());
    let res = crate::rootfs::install(&dbg, &new, &staged, app, &service, &work.join("tmp"), &|m| msgs.borrow_mut().push(m));
    for m in msgs.borrow().iter() {
        log.line(&format!("L {}", m));
    }
    let last = res?;
    log.line(&format!("L filesystem check: {}", last));
    // write back only the 4 MiB chunks that changed, each read back to verify
    let mut a = File::open(&old)?;
    let mut b = File::open(&new)?;
    let (mut x, mut y, mut back) = (vec![0u8; CHUNK], vec![0u8; CHUNK], vec![0u8; CHUNK]);
    let mut off = 0u64;
    let mut changed = 0;
    while off < root.size {
        let n = std::cmp::min(CHUNK as u64, root.size - off) as usize;
        a.read_exact(&mut x[..n])?;
        b.read_exact(&mut y[..n])?;
        if x[..n] != y[..n] {
            dev.seek(SeekFrom::Start(root.start + off))?;
            dev.write_all(&y[..n])?;
            dev.seek(SeekFrom::Start(root.start + off))?;
            dev.read_exact(&mut back[..n])?;
            if back[..n] != y[..n] {
                bail!("verify failed at offset {}", off);
            }
            changed += 1;
        }
        off += n as u64;
        if (off / CHUNK as u64) % 16 == 0 {
            log.line(&format!("P {} {} writing changes", off, root.size));
        }
    }
    let _ = std::fs::remove_file(&old);
    let _ = std::fs::remove_file(&new);
    log.line(&format!("OK {} updated: {} block(s) of 4 MiB written and verified", app.title, changed));
    Ok(())
}

/// Entry point for `--helper job.json` (runs elevated).
pub fn run_helper(job_path: &Path) -> i32 {
    let job: HelperJob = match std::fs::read_to_string(job_path).ok().and_then(|t| serde_json::from_str(&t).ok()) {
        Some(j) => j,
        None => return 2,
    };
    let mut log = match OpenOptions::new().create(true).append(true).open(&job.log) {
        Ok(f) => Log(f),
        Err(_) => return 3,
    };
    let res = check_disk(&job).and_then(|_| match job.mode.as_str() {
        "flash" => flash(&job, &mut log),
        "update" => update(&job, &mut log),
        m => Err(anyhow::anyhow!("unknown mode {}", m)),
    });
    match res {
        Ok(()) => 0,
        Err(e) => {
            log.line(&format!("E {:#}", e));
            1
        }
    }
}

/// Start the helper elevated (UAC prompt). Returns immediately.
pub fn launch_elevated(job_file: &Path) -> Result<()> {
    let exe = std::env::current_exe()?;
    let ps = format!(
        "Start-Process -FilePath '{}' -ArgumentList @('--helper', '\"{}\"') -Verb RunAs",
        exe.display().to_string().replace('\'', "''"),
        job_file.display().to_string().replace('\'', "''")
    );
    let mut c = std::process::Command::new("powershell.exe");
    c.args(["-NoProfile", "-NonInteractive", "-Command", &ps]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x08000000);
    }
    let o = c.output()?;
    if !o.status.success() {
        let err = String::from_utf8_lossy(&o.stderr);
        if err.to_lowercase().contains("cancel") {
            bail!("The administrator prompt was declined - nothing was written.");
        }
        bail!("could not start the elevated helper: {}", err.lines().next().unwrap_or(""));
    }
    Ok(())
}
