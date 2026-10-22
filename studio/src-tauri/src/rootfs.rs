//! Installing the app into the ext4 root filesystem of an ArkOS image, using
//! e2fsprogs' debugfs (Linux/macOS natively, Windows through WSL). Root-free:
//! works on a file holding the partition, never mounts anything.
//!
//! Hard-won rules (see docs/APPLIANCE-GUIDE.md, Part 4):
//!  - repair first (e2fsck -fy): debugfs does not replay a journal left by a power cut
//!  - debugfs "mkdir" on an existing directory leaves an orphaned inode -> stat first
//!  - remove every other appliance drop-in so exactly one app boots
//!  - make the EASYROMS mounts nofail so a failed format can't freeze the boot
use crate::bundle::{render, AppInfo, BOOT_SH, DROPIN};
use anyhow::{bail, Context, Result};
use serde::Serialize;
use std::path::{Path, PathBuf};
use std::process::Command;

pub struct Debugfs {
    pub via_wsl: bool,
}

#[derive(Serialize, Clone, Debug)]
pub struct ToolStatus {
    pub ok: bool,
    pub how: String,
    pub hint: String,
}

fn no_window(c: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x08000000);
    }
    c
}

pub fn to_wsl(p: &Path) -> String {
    let s = p.to_string_lossy().replace('\\', "/");
    if s.len() > 2 && &s[1..2] == ":" {
        format!("/mnt/{}{}", s[0..1].to_lowercase(), &s[2..])
    } else {
        s
    }
}

impl Debugfs {
    pub fn check() -> ToolStatus {
        if cfg!(windows) {
            let out = no_window(Command::new("wsl.exe").args(["-e", "sh", "-c", "test -x /usr/sbin/debugfs && test -x /sbin/e2fsck && echo OK"])).output();
            match out {
                Ok(o) if String::from_utf8_lossy(&o.stdout).contains("OK") => ToolStatus { ok: true, how: "WSL".into(), hint: String::new() },
                Ok(_) => ToolStatus {
                    ok: false,
                    how: "WSL".into(),
                    hint: "WSL is installed, but e2fsprogs is missing. Run: wsl -- sudo apt install -y e2fsprogs".into(),
                },
                Err(_) => ToolStatus {
                    ok: false,
                    how: "WSL".into(),
                    hint: "Install WSL (run 'wsl --install' in an admin terminal, reboot), then: wsl -- sudo apt install -y e2fsprogs".into(),
                },
            }
        } else {
            let ok = Path::new("/usr/sbin/debugfs").exists() || Path::new("/sbin/debugfs").exists() || which("debugfs").is_some();
            ToolStatus {
                ok,
                how: "native".into(),
                hint: if ok { String::new() } else { "Install e2fsprogs (apt install e2fsprogs / brew install e2fsprogs)".into() },
            }
        }
    }

    pub fn new() -> Self {
        Debugfs { via_wsl: cfg!(windows) }
    }

    fn p(&self, path: &Path) -> String {
        if self.via_wsl { to_wsl(path) } else { path.to_string_lossy().to_string() }
    }

    fn run(&self, tool: &str, args: &[String]) -> Result<std::process::Output> {
        let out = if self.via_wsl {
            let exe = if tool == "debugfs" { "/usr/sbin/debugfs".to_string() } else { format!("/sbin/{}", tool) };
            no_window(Command::new("wsl.exe").arg("-e").arg(exe).args(args)).output()
        } else {
            let exe = which(tool).unwrap_or_else(|| PathBuf::from(format!("/sbin/{}", tool)));
            Command::new(exe).args(args).output()
        };
        out.with_context(|| format!("could not run {}", tool))
    }

    /// Read-only request, e.g. "cat /etc/passwd".
    pub fn request(&self, img: &Path, req: &str) -> Result<String> {
        let o = self.run("debugfs", &["-R".into(), req.into(), self.p(img)])?;
        Ok(String::from_utf8_lossy(&o.stdout).to_string())
    }

    /// Run a command file; returns stdout+stderr.
    pub fn script(&self, img: &Path, script: &Path, write: bool) -> Result<String> {
        let mut args: Vec<String> = Vec::new();
        if write {
            args.push("-w".into());
        }
        args.push("-f".into());
        args.push(self.p(script));
        args.push(self.p(img));
        let o = self.run("debugfs", &args)?;
        Ok(format!("{}{}", String::from_utf8_lossy(&o.stdout), String::from_utf8_lossy(&o.stderr)))
    }

    /// e2fsck: fix=true repairs (-fy), else checks only (-fn). Returns (clean, last line).
    pub fn fsck(&self, img: &Path, fix: bool) -> Result<(bool, String)> {
        let o = self.run("e2fsck", &[if fix { "-fy".into() } else { "-fn".into() }, self.p(img)])?;
        // stderr first: it only holds the version banner; the summary is the last stdout line
        let text = format!("{}{}", String::from_utf8_lossy(&o.stderr), String::from_utf8_lossy(&o.stdout));
        let last = text.lines().filter(|l| !l.trim().is_empty()).last().unwrap_or("").to_string();
        let code = o.status.code().unwrap_or(8);
        Ok((if fix { code <= 2 } else { code == 0 }, if fix && text.contains("Fix? yes") { format!("repaired: {}", last) } else { last }))
    }
}

fn which(name: &str) -> Option<PathBuf> {
    std::env::var_os("PATH").and_then(|paths| std::env::split_paths(&paths).map(|d| d.join(name)).find(|p| p.is_file()))
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct RootInfo {
    pub service_found: bool,
    pub service_path: String,
    pub user: String,
    pub uid: u32,
    pub gid: u32,
    pub os: String,
    pub python: String,
    pub installed_apps: Vec<String>,
}

/// Look inside a root filesystem: front-end service, its user, OS, installed appliance apps.
pub fn inspect(dbg: &Debugfs, rootfs: &Path, service: &str) -> Result<RootInfo> {
    let mut info = RootInfo::default();
    for dir in ["/etc/systemd/system", "/lib/systemd/system"] {
        let unit = dbg.request(rootfs, &format!("cat {}/{}", dir, service))?;
        if unit.contains("[Service]") {
            info.service_found = true;
            info.service_path = format!("{}/{}", dir, service);
            info.user = unit.lines().find_map(|l| l.trim().strip_prefix("User=")).unwrap_or("root").trim().to_string();
            break;
        }
    }
    if info.user.is_empty() {
        info.user = "root".into();
    }
    let passwd = dbg.request(rootfs, "cat /etc/passwd")?;
    for l in passwd.lines() {
        let f: Vec<&str> = l.split(':').collect();
        if f.len() > 3 && f[0] == info.user {
            info.uid = f[2].parse().unwrap_or(0);
            info.gid = f[3].parse().unwrap_or(0);
        }
    }
    let osr = dbg.request(rootfs, "cat /usr/lib/os-release")?;
    info.os = osr.lines().find_map(|l| l.strip_prefix("PRETTY_NAME=")).unwrap_or("").trim_matches('"').to_string();
    let py = dbg.request(rootfs, "stat /usr/bin/python3")?;
    info.python = py.lines().find_map(|l| l.split("Fast link dest: ").nth(1)).unwrap_or("").trim_matches('"').to_string();
    let drop = dbg.request(rootfs, &format!("ls {}.d", info.service_path))?;
    for name in drop.split_whitespace().filter(|n| n.starts_with("10-") && n.ends_with(".conf")) {
        let c = dbg.request(rootfs, &format!("cat {}.d/{}", info.service_path, name))?;
        if let Some(l) = c.lines().find(|l| l.starts_with("ExecStart=/opt/")) {
            info.installed_apps.push(l.trim_start_matches("ExecStart=/opt/").trim_end_matches("/boot.sh").to_string());
        }
    }
    Ok(info)
}

fn patch_fstab(text: &str) -> String {
    text.lines()
        .map(|l| {
            let f: Vec<&str> = l.split_whitespace().collect();
            if f.len() >= 4 && !l.trim_start().starts_with('#') {
                let mut opts = f[3].to_string();
                let want = if f[1] == "/roms" && f[2] == "exfat" {
                    ",nofail,x-systemd.device-timeout=10s"
                } else if (f[2] == "none" && opts.contains("bind")) || (f[1] == "/boot" && f[2] == "vfat") {
                    ",nofail"
                } else {
                    ""
                };
                if !want.is_empty() && !opts.contains("nofail") {
                    opts.push_str(want);
                    let mut g: Vec<String> = f.iter().map(|s| s.to_string()).collect();
                    g[3] = opts;
                    return g.join(" ");
                }
            }
            l.to_string()
        })
        .collect::<Vec<_>>()
        .join("\n")
        + "\n"
}

/// Install `staged` (a prepared app folder) as /opt/<app> and make it the boot program.
pub fn install(dbg: &Debugfs, rootfs: &Path, staged: &Path, a: &AppInfo, service: &str, tmp: &Path, log: &dyn Fn(String)) -> Result<String> {
    std::fs::create_dir_all(tmp)?;
    let (_, rep) = dbg.fsck(rootfs, true)?;
    if rep.starts_with("repaired") {
        log("repaired the filesystem first (unclean shutdown)".into());
    }
    let info = inspect(dbg, rootfs, service)?;
    if !info.service_found {
        bail!("front-end service {} not found in this image - check the device profile", service);
    }
    log(format!("{} · front end {} runs as {} (uid {})", info.os, info.service_path, info.user, info.uid));
    let (uid, gid) = (info.uid, info.gid);
    let opt = format!("/opt/{}", a.app);

    // which directories exist already (one read-only debugfs run)
    let mut dirs = vec![opt.clone()];
    let mut files: Vec<(PathBuf, String)> = Vec::new();
    fn walk(base: &Path, rel: &Path, dirs: &mut Vec<String>, files: &mut Vec<(PathBuf, String)>, opt: &str) {
        if let Ok(rd) = std::fs::read_dir(base.join(rel)) {
            let mut ents: Vec<_> = rd.flatten().collect();
            ents.sort_by_key(|e| e.file_name());
            for e in ents {
                let r = rel.join(e.file_name());
                let target = format!("{}/{}", opt, r.to_string_lossy().replace('\\', "/"));
                if e.path().is_dir() {
                    dirs.push(target);
                    walk(base, &r, dirs, files, opt);
                } else {
                    files.push((e.path(), target));
                }
            }
        }
    }
    walk(staged, Path::new(""), &mut dirs, &mut files, &opt);
    let stat_script = tmp.join("stat.debugfs");
    std::fs::write(&stat_script, dirs.iter().map(|d| format!("stat \"{}\"\n", d)).collect::<String>())?;
    let out = dbg.script(rootfs, &stat_script, false)?;
    let mut existing = std::collections::HashSet::new();
    for chunk in out.split("debugfs: stat ").skip(1) {
        let name = chunk.lines().next().unwrap_or("").trim().trim_matches('"').to_string();
        if chunk.contains("Type: directory") {
            existing.insert(name);
        }
    }

    let mut s = String::new();
    let own = |s: &mut String, p: &str| s.push_str(&format!("sif \"{p}\" uid {uid}\nsif \"{p}\" gid {gid}\n"));
    for d in &dirs {
        if !existing.contains(d) {
            s.push_str(&format!("mkdir \"{}\"\n", d));
        }
        own(&mut s, d);
    }
    for (src, dst) in &files {
        s.push_str(&format!("rm \"{dst}\"\nwrite \"{}\" \"{dst}\"\n", dbg.p(src)));
        own(&mut s, dst);
        if dst.ends_with(".sh") || dst.ends_with("/start") || dst.contains("/bin/") {
            s.push_str(&format!("sif \"{dst}\" mode 0100755\n"));
        }
    }
    // boot session + systemd drop-in
    let boot = tmp.join("boot.sh");
    std::fs::write(&boot, render(BOOT_SH, a))?;
    s.push_str(&format!("rm {opt}/boot.sh\nwrite \"{}\" {opt}/boot.sh\nsif {opt}/boot.sh mode 0100755\n", dbg.p(&boot)));
    own(&mut s, &format!("{opt}/boot.sh"));
    let dropdir = format!("{}.d", info.service_path);
    let dropname = format!("10-{}.conf", a.app);
    let dropin = tmp.join(&dropname);
    std::fs::write(&dropin, render(DROPIN, a))?;
    if !dbg.request(rootfs, &format!("stat {}", dropdir))?.contains("Type: directory") {
        s.push_str(&format!("mkdir {}\n", dropdir));
    }
    for name in dbg.request(rootfs, &format!("ls {}", dropdir))?.split_whitespace().filter(|n| n.starts_with("10-") && n.ends_with(".conf")) {
        if name != dropname && dbg.request(rootfs, &format!("cat {}/{}", dropdir, name))?.contains("ExecStart=/opt/") {
            log(format!("removing the previous app's boot entry {}", name));
            s.push_str(&format!("rm {}/{}\n", dropdir, name));
        }
    }
    s.push_str(&format!("rm {dropdir}/{dropname}\nwrite \"{}\" {dropdir}/{dropname}\n", dbg.p(&dropin)));
    // fstab: optional EASYROMS mounts (first-boot template and the live one)
    for (i, path) in [format!("/home/{}/fstab", info.user), "/etc/fstab".to_string()].iter().enumerate() {
        let cur = dbg.request(rootfs, &format!("cat {}", path))?;
        if cur.trim().is_empty() {
            continue;
        }
        let new = patch_fstab(&cur);
        if new.trim() != cur.trim() {
            let f = tmp.join(format!("fstab{}", i));
            std::fs::write(&f, &new)?;
            s.push_str(&format!("rm {path}\nwrite \"{}\" {path}\nsif {path} mode 0100644\n", dbg.p(&f)));
            log(format!("{}: EASYROMS mounts made optional (nofail)", path));
        }
    }
    let script = tmp.join("install.debugfs");
    std::fs::write(&script, &s)?;
    log(format!("writing {} files into {}", files.len() + 2, opt));
    let out = dbg.script(rootfs, &script, true)?;
    let bad: Vec<&str> = out
        .lines()
        .filter(|l| !l.starts_with("debugfs"))
        .filter(|l| !l.contains("File not found by ext2_lookup") && !l.contains("already exists") && !l.starts_with("Allocated inode"))
        .filter(|l| {
            let x = l.to_lowercase();
            x.contains("error") || x.contains("could not") || x.contains("failed") || x.contains("not found")
        })
        .collect();
    if !bad.is_empty() {
        bail!("debugfs reported problems:\n{}", bad.join("\n"));
    }
    let (clean, last) = dbg.fsck(rootfs, false)?;
    if !clean {
        bail!("filesystem check failed after installing: {}", last);
    }
    Ok(last)
}
