"""Render ChessOS sprites with Pillow into a tiny raw format the device loads
without SDL_image:  b"CSPR" + uint16 w + uint16 h + zlib(RGBA bytes).
Also writes a PNG preview sheet to build/sprites_preview.png.
"""
import math
import os
import struct
import zlib

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "device", "chessos", "assets", "sprites")
FONT = os.path.join(ROOT, "device", "chessos", "assets", "fonts", "DejaVuSans.ttf")
SS = 4  # supersampling


def save(name, img):
    img = img.convert("RGBA")
    data = zlib.compress(img.tobytes(), 9)
    with open(os.path.join(OUT, name + ".spr"), "wb") as f:
        f.write(b"CSPR" + struct.pack("<HH", img.width, img.height) + data)
    return img


def canvas(size):
    return Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))


def down(img, size):
    return img.resize((size, size), Image.LANCZOS)


# ---- chess pieces ------------------------------------------------------------
def piece(letter, size=96):
    white = letter.isupper()
    idx = "KQRBNP".index(letter.upper())
    filled = chr(0x265A + idx)
    hollow = chr(0x2654 + idx)
    S = size * SS
    font = ImageFont.truetype(FONT, int(S * 0.92))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), filled, font=font)
    x = (S - (bb[2] - bb[0])) / 2 - bb[0]
    y = (S - (bb[3] - bb[1])) / 2 - bb[1] + S * 0.01
    sw = max(1, int(S * 0.018))
    if white:
        d.text((x, y), filled, font=font, fill=(255, 255, 255, 255), stroke_width=sw, stroke_fill=(40, 40, 40, 255))
        d.text((x, y), hollow, font=font, fill=(40, 40, 40, 255))
    else:
        d.text((x, y), filled, font=font, fill=(52, 52, 56, 255), stroke_width=sw, stroke_fill=(20, 20, 22, 255))
        # light inner detail lines so black pieces read well on dark squares
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).text((x, y), hollow, font=font, fill=255)
        fillmask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(fillmask).text((x, y), filled, font=font, fill=255)
        inner = Image.new("L", (S, S), 0)
        inner.paste(mask, (0, 0), fillmask.point(lambda v: 255 - v))
    # soft drop shadow
    alpha = img.split()[3]
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh.putalpha(alpha.point(lambda v: v * 0.35).filter(ImageFilter.GaussianBlur(S * 0.02)))
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    base.alpha_composite(sh, (0, int(S * 0.025)))
    base.alpha_composite(img)
    return base.resize((size, size), Image.LANCZOS)


# ---- shapes ------------------------------------------------------------------
def circle(size=128):
    img = canvas(size)
    ImageDraw.Draw(img).ellipse((0, 0, size * SS - 1, size * SS - 1), fill=(255, 255, 255, 255))
    return down(img, size)


def star_points(cx, cy, ro, ri, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = ro if i % 2 == 0 else ri
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def star(size=64, color=(255, 255, 255, 255)):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    d.polygon(star_points(S / 2, S * 0.53, S * 0.48, S * 0.22), fill=color)
    return down(img.filter(ImageFilter.GaussianBlur(SS * 0.6)), size)


def flame(size=64, outer=(255, 150, 0, 255), inner=(255, 200, 0, 255)):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)

    def drop(cx, cy, r, h, col):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
        d.polygon([(cx - r * 0.98, cy - r * 0.2), (cx + r * 0.25, cy - h), (cx + r * 0.98, cy - r * 0.15)], fill=col)
        d.polygon([(cx - r * 0.95, cy - r * 0.35), (cx - r * 0.75, cy - h * 0.62), (cx - r * 0.2, cy - r * 0.6)], fill=col)

    drop(S * 0.5, S * 0.64, S * 0.33, S * 0.62, outer)
    drop(S * 0.52, S * 0.72, S * 0.19, S * 0.30, inner)
    return down(img.filter(ImageFilter.GaussianBlur(SS * 0.8)), size)


def heart(size=64, color=(255, 75, 75, 255)):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    r = S * 0.25
    d.ellipse((S * 0.06, S * 0.12, S * 0.06 + 2 * r, S * 0.12 + 2 * r), fill=color)
    d.ellipse((S * 0.94 - 2 * r, S * 0.12, S * 0.94, S * 0.12 + 2 * r), fill=color)
    d.polygon([(S * 0.08, S * 0.45), (S * 0.5, S * 0.92), (S * 0.92, S * 0.45), (S * 0.5, S * 0.3)], fill=color)
    d.ellipse((S * 0.2, S * 0.24, S * 0.34, S * 0.34), fill=(255, 255, 255, 110))
    return down(img.filter(ImageFilter.GaussianBlur(SS * 0.5)), size)


def gem(size=64):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    top = [(S * 0.2, S * 0.18), (S * 0.8, S * 0.18), (S * 0.97, S * 0.4), (S * 0.03, S * 0.4)]
    d.polygon(top, fill=(132, 216, 255, 255))
    d.polygon([(S * 0.03, S * 0.4), (S * 0.97, S * 0.4), (S * 0.5, S * 0.95)], fill=(28, 176, 246, 255))
    d.polygon([(S * 0.3, S * 0.4), (S * 0.7, S * 0.4), (S * 0.5, S * 0.95)], fill=(73, 192, 248, 255))
    d.polygon([(S * 0.35, S * 0.18), (S * 0.65, S * 0.18), (S * 0.7, S * 0.4), (S * 0.3, S * 0.4)], fill=(190, 236, 255, 255))
    return down(img, size)


def crown(size=64, color=(255, 200, 0, 255)):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    d.polygon([(S * 0.08, S * 0.3), (S * 0.3, S * 0.52), (S * 0.5, S * 0.18), (S * 0.7, S * 0.52),
               (S * 0.92, S * 0.3), (S * 0.84, S * 0.8), (S * 0.16, S * 0.8)], fill=color)
    for cx, cy in ((0.08, 0.3), (0.5, 0.18), (0.92, 0.3)):
        d.ellipse((S * cx - S * 0.07, S * cy - S * 0.07, S * cx + S * 0.07, S * cy + S * 0.07), fill=color)
    d.rectangle((S * 0.16, S * 0.72, S * 0.84, S * 0.8), fill=(229, 164, 0, 255))
    return down(img.filter(ImageFilter.GaussianBlur(SS * 0.5)), size)


def lock(size=64):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    w = int(S * 0.1)
    d.arc((S * 0.27, S * 0.1, S * 0.73, S * 0.62), 180, 360, fill=(255, 255, 255, 255), width=w)
    d.line((S * 0.27 + w / 2, S * 0.36, S * 0.27 + w / 2, S * 0.5), fill=(255, 255, 255, 255), width=w)
    d.line((S * 0.73 - w / 2, S * 0.36, S * 0.73 - w / 2, S * 0.5), fill=(255, 255, 255, 255), width=w)
    d.rounded_rectangle((S * 0.16, S * 0.44, S * 0.84, S * 0.92), radius=S * 0.1, fill=(255, 255, 255, 255))
    d.ellipse((S * 0.44, S * 0.58, S * 0.56, S * 0.7), fill=(0, 0, 0, 0))
    return down(img, size)


def checkmark(size=64):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    d.line([(S * 0.18, S * 0.52), (S * 0.42, S * 0.75), (S * 0.84, S * 0.27)], fill=(255, 255, 255, 255),
           width=int(S * 0.14), joint="curve")
    for x, y in ((0.18, 0.52), (0.84, 0.27)):
        r = S * 0.07
        d.ellipse((S * x - r, S * y - r, S * x + r, S * y + r), fill=(255, 255, 255, 255))
    return down(img, size)


def speaker(size=64):
    img = canvas(size)
    S = size * SS
    d = ImageDraw.Draw(img)
    d.polygon([(S * 0.1, S * 0.38), (S * 0.3, S * 0.38), (S * 0.52, S * 0.16), (S * 0.52, S * 0.84),
               (S * 0.3, S * 0.62), (S * 0.1, S * 0.62)], fill=(255, 255, 255, 255))
    w = int(S * 0.07)
    d.arc((S * 0.42, S * 0.3, S * 0.72, S * 0.7), -50, 50, fill=(255, 255, 255, 255), width=w)
    d.arc((S * 0.42, S * 0.14, S * 0.9, S * 0.86), -50, 50, fill=(255, 255, 255, 255), width=w)
    return down(img, size)


def mascot(size=160):
    """'Rook-y' style mascot: a friendly green knight with a big eye."""
    S = size * SS
    font = ImageFont.truetype(FONT, int(S * 0.95))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = chr(0x265E)
    bb = d.textbbox((0, 0), g, font=font)
    x = (S - (bb[2] - bb[0])) / 2 - bb[0]
    y = (S - (bb[3] - bb[1])) / 2 - bb[1]
    sw = int(S * 0.025)
    d.text((x, y), g, font=font, fill=(88, 204, 2, 255), stroke_width=sw, stroke_fill=(70, 163, 2, 255))
    # fill the glyph's interior detail holes so it reads as a solid character
    solid = img.split()[3].filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    body = Image.new("RGBA", (S, S), (88, 204, 2, 255))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(body, (0, 0), solid)
    out.alpha_composite(img)
    d = ImageDraw.Draw(out)
    # belly highlight and eye
    ex, ey, er = S * 0.47, S * 0.3, S * 0.085
    d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=(255, 255, 255, 255), outline=(60, 60, 60, 255), width=SS * 2)
    pr = er * 0.5
    d.ellipse((ex - pr + er * 0.25, ey - pr, ex + pr + er * 0.25, ey + pr), fill=(40, 40, 40, 255))
    d.ellipse((ex + er * 0.25, ey - pr * 0.7, ex + er * 0.25 + pr * 0.6, ey - pr * 0.1), fill=(255, 255, 255, 255))
    return out.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    sheet = []
    for p in "KQRBNPkqrbnp":
        name = ("w" if p.isupper() else "b") + p.upper()
        sheet.append(save("piece_" + name, piece(p)))
    sheet.append(save("circle", circle()))
    sheet.append(save("star", star()))
    sheet.append(save("flame", flame()))
    sheet.append(save("flame_gray", flame(outer=(90, 110, 120, 255), inner=(130, 150, 160, 255))))
    sheet.append(save("heart", heart()))
    sheet.append(save("gem", gem()))
    sheet.append(save("crown", crown()))
    sheet.append(save("lock", lock()))
    sheet.append(save("check", checkmark()))
    sheet.append(save("speaker", speaker()))
    sheet.append(save("mascot", mascot()))
    # preview
    W = 12 * 100
    prev = Image.new("RGBA", (W, 400), (19, 31, 36, 255))
    x, y = 0, 0
    for im in sheet:
        if x + im.width > W:
            x, y = 0, y + 170
        if im.width < 100:
            prev.alpha_composite(Image.new("RGBA", im.size, (119, 149, 86, 255) if (x // 100) % 2 else (235, 236, 208, 255)), (x, y))
        prev.alpha_composite(im, (x, y))
        x += max(100, im.width + 4)
    prev.save(os.path.join(ROOT, "build", "sprites_preview.png"))
    print("sprites:", len(sheet))


if __name__ == "__main__":
    main()
