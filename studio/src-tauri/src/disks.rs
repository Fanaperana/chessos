//! Listing disks/volumes (Windows: PowerShell Storage cmdlets).
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::process::Command;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Disk {
    pub number: u32,
    pub name: String,
    pub bus: String,
    pub size: u64,
    pub boot: bool,
    pub system: bool,
    pub style: String,
    #[serde(default)]
    pub volumes: Vec<String>, // "G:EASYROMS"
    #[serde(default)]
    pub removable: bool,
}

pub fn powershell(script: &str) -> Result<String> {
    let mut c = Command::new("powershell.exe");
    c.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x08000000);
    }
    let o = c.output().context("powershell")?;
    Ok(String::from_utf8_lossy(&o.stdout).to_string())
}

const LIST: &str = r#"
$d = Get-Disk | ForEach-Object {
  $n = $_.Number
  $vols = @(Get-Partition -DiskNumber $n -ErrorAction SilentlyContinue | Get-Volume -ErrorAction SilentlyContinue |
            Where-Object { $_.DriveLetter } | ForEach-Object { "$($_.DriveLetter):$($_.FileSystemLabel)" })
  [pscustomobject]@{ number = [uint32]$n; name = [string]$_.FriendlyName; bus = [string]$_.BusType; size = [uint64]$_.Size;
                     boot = [bool]$_.IsBoot; system = [bool]$_.IsSystem; style = [string]$_.PartitionStyle; volumes = $vols }
}
ConvertTo-Json -InputObject @($d) -Depth 3 -Compress
"#;

pub fn list() -> Result<Vec<Disk>> {
    if !cfg!(windows) {
        anyhow::bail!("disk listing is implemented for Windows only so far");
    }
    let out = powershell(LIST)?;
    let mut disks: Vec<Disk> = serde_json::from_str(out.trim()).context("could not read the disk list")?;
    for d in disks.iter_mut() {
        // size 0 = a card reader with no card in it
        d.removable = !d.boot && !d.system && d.size > 0 && ["USB", "SD", "MMC"].contains(&d.bus.as_str());
    }
    Ok(disks)
}

pub fn get(number: u32) -> Result<Disk> {
    list()?.into_iter().find(|d| d.number == number).context("disk not found")
}
