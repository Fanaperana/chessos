//! Any picture -> boot logo: an 8-bit palette, RLE8-compressed BMP (the
//! format the ArkOS bootloader shows), plus a PNG preview of the result.
use anyhow::Result;
use image::{imageops::FilterType, Rgb, RgbImage};
use std::path::Path;

pub struct Splash {
    pub bmp: Vec<u8>,
    pub preview_png: Vec<u8>,
}

/// fit: "cover" (fill, crop edges) or "contain" (whole picture, background bars)
pub fn make(src: &Path, w: u32, h: u32, fit: &str, bg: [u8; 3]) -> Result<Splash> {
    let img = image::open(src)?.to_rgb8();
    let (iw, ih) = img.dimensions();
    let s = if fit == "cover" {
        (w as f32 / iw as f32).max(h as f32 / ih as f32)
    } else {
        (w as f32 / iw as f32).min(h as f32 / ih as f32)
    };
    let (nw, nh) = (((iw as f32 * s).round() as u32).max(1), ((ih as f32 * s).round() as u32).max(1));
    let scaled = image::imageops::resize(&img, nw, nh, FilterType::Lanczos3);
    let mut canvas = RgbImage::from_pixel(w, h, Rgb(bg));
    let ox = (w as i64 - nw as i64) / 2;
    let oy = (h as i64 - nh as i64) / 2;
    image::imageops::overlay(&mut canvas, &scaled, ox, oy);
    encode(&canvas)
}

fn encode(img: &RgbImage) -> Result<Splash> {
    let (w, h) = img.dimensions();
    let rgba: Vec<u8> = img.pixels().flat_map(|p| [p[0], p[1], p[2], 255]).collect();
    let nq = color_quant::NeuQuant::new(10, 256, &rgba);
    let pal = nq.color_map_rgb();
    let idx: Vec<u8> = rgba.chunks(4).map(|c| nq.index_of(c) as u8).collect();
    // preview of the quantized result
    let prev = RgbImage::from_fn(w, h, |x, y| {
        let i = idx[(y * w + x) as usize] as usize * 3;
        Rgb([pal[i], pal[i + 1], pal[i + 2]])
    });
    let mut png = Vec::new();
    prev.write_to(&mut std::io::Cursor::new(&mut png), image::ImageFormat::Png)?;
    Ok(Splash { bmp: rle8_bmp(&idx, &pal, w, h), preview_png: png })
}

fn rle8_bmp(idx: &[u8], pal: &[u8], w: u32, h: u32) -> Vec<u8> {
    let mut data = Vec::new();
    for y in (0..h).rev() {
        // BMP rows are bottom-up
        let row = &idx[(y * w) as usize..((y + 1) * w) as usize];
        let mut i = 0;
        while i < row.len() {
            let v = row[i];
            let mut n = 1;
            while i + n < row.len() && n < 255 && row[i + n] == v {
                n += 1;
            }
            data.push(n as u8);
            data.push(v);
            i += n;
        }
        data.extend_from_slice(&[0, 0]); // end of line
    }
    data.extend_from_slice(&[0, 1]); // end of bitmap
    let mut palette = Vec::with_capacity(1024);
    for i in 0..256 {
        let (r, g, b) = if i * 3 + 2 < pal.len() { (pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2]) } else { (0, 0, 0) };
        palette.extend_from_slice(&[b, g, r, 0]);
    }
    let offset = 14 + 40 + palette.len() as u32;
    let mut out = Vec::new();
    out.extend_from_slice(b"BM");
    out.extend_from_slice(&(offset + data.len() as u32).to_le_bytes());
    out.extend_from_slice(&[0, 0, 0, 0]);
    out.extend_from_slice(&offset.to_le_bytes());
    for v in [40u32, w, h] {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&8u16.to_le_bytes());
    for v in [1u32, data.len() as u32, 3779, 3779, 256, 256] {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out.extend_from_slice(&palette);
    out.extend_from_slice(&data);
    out
}
