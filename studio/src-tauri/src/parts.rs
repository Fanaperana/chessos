//! Partition tables (GPT and MBR) and filesystem detection on images and disks.
use anyhow::{bail, Result};
use serde::Serialize;
use std::io::{Read, Seek, SeekFrom};

#[derive(Serialize, Clone, Debug)]
pub struct Part {
    pub index: u32,
    pub start: u64,
    pub size: u64,
    pub fs: String, // "fat", "ext4", "exfat", "unknown"
    pub name: String,
}

#[derive(Serialize, Clone, Debug)]
pub struct Layout {
    pub table: String, // "gpt" / "mbr"
    pub parts: Vec<Part>,
}

impl Layout {
    pub fn boot(&self) -> Option<&Part> {
        self.parts.iter().find(|p| p.fs == "fat")
    }
    pub fn root(&self) -> Option<&Part> {
        self.parts.iter().filter(|p| p.fs == "ext4").max_by_key(|p| p.size)
    }
}

fn u16le(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
fn u32le(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn u64le(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}

fn read_at<R: Read + Seek>(r: &mut R, off: u64, n: usize) -> Result<Vec<u8>> {
    r.seek(SeekFrom::Start(off))?;
    let mut b = vec![0u8; n];
    r.read_exact(&mut b)?;
    Ok(b)
}

fn detect_fs<R: Read + Seek>(r: &mut R, start: u64) -> String {
    let b = match read_at(r, start, 2048) {
        Ok(b) => b,
        Err(_) => return "unknown".into(),
    };
    if u16le(&b, 1024 + 56) == 0xEF53 {
        return "ext4".into();
    }
    if &b[3..11] == b"EXFAT   " {
        return "exfat".into();
    }
    if b[510] == 0x55 && b[511] == 0xAA && (&b[0x36..0x39] == b"FAT" || &b[0x52..0x55] == b"FAT") {
        return "fat".into();
    }
    "unknown".into()
}

/// Read the partition layout. `total` = image/disk size in bytes (for the backup GPT).
pub fn layout<R: Read + Seek>(r: &mut R, total: u64) -> Result<Layout> {
    let mbr = read_at(r, 0, 512)?;
    let gpt_protective = (0..4).any(|i| mbr[446 + i * 16 + 4] == 0xEE);
    if gpt_protective {
        // primary header; ArkOS images sometimes ship a primary GPT whose header
        // CRC is stale, so the signature + entries are trusted and the backup
        // header is used only when the primary signature is missing
        let mut hdr = read_at(r, 512, 512)?;
        if &hdr[0..8] != b"EFI PART" {
            let last = total / 512 - 1;
            hdr = read_at(r, last * 512, 512)?;
            if &hdr[0..8] != b"EFI PART" {
                bail!("GPT disk without a readable header");
            }
        }
        let entries_lba = u64le(&hdr, 72);
        let n = u32le(&hdr, 80).min(256) as usize;
        let esz = u32le(&hdr, 84) as usize;
        let ents = read_at(r, entries_lba * 512, n * esz)?;
        let mut parts = Vec::new();
        for i in 0..n {
            let e = &ents[i * esz..(i + 1) * esz];
            if e[0..16].iter().all(|&x| x == 0) {
                continue;
            }
            let first = u64le(e, 32);
            let last = u64le(e, 40);
            let name: String = String::from_utf16_lossy(
                &e[56..128].chunks(2).map(|c| u16::from_le_bytes([c[0], c[1]])).take_while(|&c| c != 0).collect::<Vec<_>>(),
            );
            let start = first * 512;
            let size = (last - first + 1) * 512;
            if start >= total {
                continue; // e.g. EASYROMS of the original card, beyond a cut-down image
            }
            let fs = detect_fs(r, start);
            parts.push(Part { index: i as u32 + 1, start, size, fs, name });
        }
        return Ok(Layout { table: "gpt".into(), parts });
    }
    if mbr[510] != 0x55 || mbr[511] != 0xAA {
        bail!("no partition table found");
    }
    let mut parts = Vec::new();
    for i in 0..4 {
        let e = &mbr[446 + i * 16..446 + (i + 1) * 16];
        let typ = e[4];
        if typ == 0 || typ == 0x05 || typ == 0x0F {
            continue;
        }
        let start = u32le(e, 8) as u64 * 512;
        let size = u32le(e, 12) as u64 * 512;
        if start >= total {
            continue;
        }
        let fs = detect_fs(r, start);
        parts.push(Part { index: i as u32 + 1, start, size, fs, name: String::new() });
    }
    Ok(Layout { table: "mbr".into(), parts })
}

pub fn layout_of_file(path: &std::path::Path) -> Result<Layout> {
    let mut f = std::fs::File::open(path)?;
    let total = f.metadata()?.len();
    layout(&mut f, total)
}
