"""Make the ChessOS boot logo for the R36S BOOT partition.

Writes dist/BOOT/logo.bmp and logo_kernel.bmp: 640x480, 8-bit palette,
RLE8-compressed - the same format as the stock ArkOS R36S logos.
"""
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from build_assets import mascot  # noqa: E402

FONTS = os.path.join(ROOT, "device", "chessos", "assets", "fonts")


def render():
    W, H = 640, 480
    img = Image.new("RGB", (W, H), (19, 31, 36))
    d = ImageDraw.Draw(img)
    d.ellipse((320 - 105, 175 - 105, 320 + 105, 175 + 105), fill=(30, 52, 40))
    m = mascot(190)
    img.paste(m, (320 - 95, 175 - 102), m)
    big = ImageFont.truetype(os.path.join(FONTS, "Nunito-900.ttf"), 64)
    small = ImageFont.truetype(os.path.join(FONTS, "Nunito-800.ttf"), 20)
    w1 = d.textlength("Chess", font=big)
    w2 = d.textlength("OS", font=big)
    x = (W - w1 - w2) / 2
    d.text((x, 300), "Chess", font=big, fill=(88, 204, 2))
    d.text((x + w1, 300), "OS", font=big, fill=(241, 247, 251))
    t = "Learn chess, one day at a time."
    d.text(((W - d.textlength(t, font=small)) / 2, 392), t, font=small, fill=(130, 155, 166))
    return img


def rle8(indices, w, h):
    out = bytearray()
    for y in range(h - 1, -1, -1):  # BMP rows are bottom-up
        row = indices[y * w:(y + 1) * w]
        i = 0
        while i < w:
            v = row[i]
            n = 1
            while i + n < w and n < 255 and row[i + n] == v:
                n += 1
            out += bytes((n, v))
            i += n
        out += b"\x00\x00"  # end of line
    out += b"\x00\x01"      # end of bitmap
    return bytes(out)


def write_bmp(img, path):
    q = img.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
    pal = q.getpalette()[:256 * 3]
    pal += [0] * (256 * 3 - len(pal))
    w, h = q.size
    data = rle8(list(q.getdata()), w, h)
    palette = b"".join(struct.pack("<BBBB", pal[i * 3 + 2], pal[i * 3 + 1], pal[i * 3], 0) for i in range(256))
    offset = 14 + 40 + len(palette)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 1, len(data), 3779, 3779, 256, 256)
    head = struct.pack("<2sIHHI", b"BM", offset + len(data), 0, 0, offset)
    with open(path, "wb") as f:
        f.write(head + info + palette + data)


def main():
    out = os.path.join(ROOT, "dist", "BOOT")
    os.makedirs(out, exist_ok=True)
    img = render()
    for name in ("logo.bmp", "logo_kernel.bmp"):
        write_bmp(img, os.path.join(out, name))
    img.save(os.path.join(ROOT, "build", "bootlogo_preview.png"))
    chk = Image.open(os.path.join(out, "logo.bmp"))
    chk.load()
    print("boot logo:", chk.size, chk.mode, os.path.getsize(os.path.join(out, "logo.bmp")), "bytes")


if __name__ == "__main__":
    main()
