//! Downloads (with progress), xz decompression and big-file copies.
use anyhow::{bail, Context, Result};
use std::fs::File;
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::Path;

const CHUNK: usize = 4 << 20;

/// Download `url` to `dest` unless it is already there with the expected size.
pub fn download(url: &str, dest: &Path, expected: Option<u64>, progress: &dyn Fn(u64, u64)) -> Result<()> {
    if let (Ok(m), Some(sz)) = (std::fs::metadata(dest), expected) {
        if m.len() == sz {
            return Ok(());
        }
    }
    if let Some(dir) = dest.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let resp = ureq::get(url).set("User-Agent", "ChessOS-Studio").call().context("download failed")?;
    let total: u64 = resp.header("Content-Length").and_then(|s| s.parse().ok()).or(expected).unwrap_or(0);
    let part = dest.with_extension("part");
    let mut out = BufWriter::new(File::create(&part)?);
    let mut rd = resp.into_reader();
    let mut buf = vec![0u8; 1 << 20];
    let mut done = 0u64;
    loop {
        let n = rd.read(&mut buf)?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        done += n as u64;
        progress(done, total);
    }
    out.flush()?;
    drop(out);
    if let Some(sz) = expected {
        if done != sz {
            bail!("download incomplete: {} of {} bytes", done, sz);
        }
    }
    std::fs::rename(&part, dest)?;
    Ok(())
}

struct Counting<R> {
    inner: R,
    n: u64,
}
impl<R: Read> Read for Counting<R> {
    fn read(&mut self, b: &mut [u8]) -> std::io::Result<usize> {
        let k = self.inner.read(b)?;
        self.n += k as u64;
        Ok(k)
    }
}

/// Decompress an .xz file (progress counts compressed bytes read).
pub fn unxz(src: &Path, dest: &Path, progress: &dyn Fn(u64, u64)) -> Result<()> {
    let total = std::fs::metadata(src)?.len();
    let f = BufReader::with_capacity(CHUNK, File::open(src)?);
    let mut dec = xz2::read::XzDecoder::new(Counting { inner: f, n: 0 });
    let part = dest.with_extension("part");
    let mut out = BufWriter::with_capacity(CHUNK, File::create(&part)?);
    let mut buf = vec![0u8; CHUNK];
    let mut tick = 0u32;
    loop {
        let n = dec.read(&mut buf)?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        tick += 1;
        if tick % 8 == 0 {
            progress(dec.get_ref().n, total);
        }
    }
    out.flush()?;
    drop(out);
    std::fs::rename(&part, dest)?;
    progress(total, total);
    Ok(())
}

/// Copy a byte range of `src` into `dst` at `dst_off` (dst created/extended as needed).
pub fn copy_range(src: &Path, src_off: u64, len: u64, dst: &Path, dst_off: u64, progress: &dyn Fn(u64, u64)) -> Result<()> {
    use std::io::{Seek, SeekFrom};
    let mut r = File::open(src)?;
    r.seek(SeekFrom::Start(src_off))?;
    let mut w = std::fs::OpenOptions::new().create(true).write(true).open(dst)?;
    w.seek(SeekFrom::Start(dst_off))?;
    let mut buf = vec![0u8; CHUNK];
    let mut done = 0u64;
    while done < len {
        let want = std::cmp::min(CHUNK as u64, len - done) as usize;
        r.read_exact(&mut buf[..want])?;
        w.write_all(&buf[..want])?;
        done += want as u64;
        progress(done, len);
    }
    w.flush()?;
    Ok(())
}

/// Whole-file copy with progress.
pub fn copy_file(src: &Path, dst: &Path, progress: &dyn Fn(u64, u64)) -> Result<()> {
    let len = std::fs::metadata(src)?.len();
    if dst.exists() {
        std::fs::remove_file(dst)?;
    }
    copy_range(src, 0, len, dst, 0, progress)
}
