"""Chess piece sets for ChessOS (all original artwork, drawn with Pillow).

  soft   puffy rounded pieces with smooth shading (pale ice / slate)
  pixel  12x12 pixel art for the retro-handheld look
  (classic = the DejaVu glyph pieces made in build_assets.py)

Each set is saved as sprites piece_<set>_<w|b><K|Q|R|B|N|P>.
"""
from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 4

SOFT = {
    # base, darker side, deep rim, highlight, ground shadow
    "w": {"base": (226, 235, 243), "side": (196, 211, 225), "rim": (160, 180, 199), "light": (255, 255, 255),
          "shadow": (120, 140, 160)},
    "b": {"base": (92, 98, 108), "side": (72, 77, 86), "rim": (46, 50, 58), "light": (150, 158, 170),
          "shadow": (40, 46, 56)},
}


# ---- soft -------------------------------------------------------------------------
def _soft_mask(kind, S):
    """Silhouette: simple shapes, then heavily rounded (blur + threshold)."""
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    U = lambda *v: [x * S for x in v]  # noqa: E731
    P = lambda pts: [(x * S, y * S) for x, y in pts]  # noqa: E731

    def bell(top, half_top, half_bot=0.27, bottom=0.88):
        """The shared rounded 'bell' body every piece stands on."""
        d.polygon(P([(0.5 - half_top, top), (0.5 + half_top, top), (0.5 + half_bot, bottom - 0.05),
                     (0.5 - half_bot, bottom - 0.05)]), fill=255)
        d.rounded_rectangle(U(0.5 - half_bot - 0.02, bottom - 0.13, 0.5 + half_bot + 0.02, bottom), radius=0.07 * S, fill=255)

    if kind == "P":
        d.ellipse(U(0.30, 0.27, 0.70, 0.65), fill=255)          # big round head, sitting low
        bell(0.60, 0.15, 0.27)
    elif kind == "R":
        d.rounded_rectangle(U(0.27, 0.16, 0.73, 0.40), radius=0.06 * S, fill=255)
        bell(0.36, 0.17, 0.27)
        for x0 in (0.375, 0.535):                                 # two notches -> three merlons
            d.rounded_rectangle(U(x0, 0.10, x0 + 0.09, 0.25), radius=0.03 * S, fill=0)
    elif kind == "B":
        d.ellipse(U(0.445, 0.08, 0.555, 0.19), fill=255)          # little top ball
        d.ellipse(U(0.32, 0.15, 0.68, 0.58), fill=255)            # mitre
        bell(0.52, 0.10, 0.25)
        d.line(P([(0.60, 0.25), (0.50, 0.37)]), fill=0, width=int(0.04 * S))  # the slit
    elif kind == "Q":
        pts = [(0.25, 0.20), (0.375, 0.13), (0.5, 0.10), (0.625, 0.13), (0.75, 0.20)]
        d.polygon(P([(0.25, 0.20), (0.36, 0.34), (0.375, 0.13), (0.45, 0.31), (0.5, 0.10), (0.55, 0.31),
                     (0.625, 0.13), (0.64, 0.34), (0.75, 0.20), (0.69, 0.50), (0.31, 0.50)]), fill=255)
        for x, y in pts:
            d.ellipse(U(x - 0.04, y - 0.04, x + 0.04, y + 0.04), fill=255)
        bell(0.46, 0.17, 0.28)
    elif kind == "K":
        d.rounded_rectangle(U(0.465, 0.05, 0.535, 0.22), radius=0.03 * S, fill=255)   # cross
        d.rounded_rectangle(U(0.42, 0.095, 0.58, 0.16), radius=0.03 * S, fill=255)
        d.rounded_rectangle(U(0.24, 0.26, 0.76, 0.52), radius=0.10 * S, fill=255)     # wide crown
        for x in (0.32, 0.5, 0.68):
            d.ellipse(U(x - 0.06, 0.20, x + 0.06, 0.32), fill=255)                    # crown bumps
        bell(0.46, 0.18, 0.28)
    elif kind == "N":
        d.polygon(P([(0.30, 0.80), (0.34, 0.62), (0.25, 0.57), (0.17, 0.49), (0.18, 0.40), (0.28, 0.32),
                     (0.37, 0.25), (0.40, 0.11), (0.48, 0.19), (0.56, 0.12), (0.64, 0.21), (0.74, 0.35),
                     (0.78, 0.52), (0.74, 0.80)]), fill=255)
        d.rounded_rectangle(U(0.21, 0.73, 0.79, 0.88), radius=0.07 * S, fill=255)
    r = S * 0.022
    return m.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v > 128 else 0)


def _shift(m, dx, dy):
    out = Image.new("L", m.size, 0)
    out.paste(m, (dx, dy))
    return out


def _paint(img, color, alpha_mask):
    img.paste(Image.new("RGBA", img.size, color + (255,)), (0, 0), alpha_mask)


def soft_piece(letter, size=96):
    kind = letter.upper()
    c = SOFT["w" if letter.isupper() else "b"]
    S = size * SS
    m = _soft_mask(kind, S)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _paint(img, c["base"], m)
    # smooth diagonal light: lighter top-left, darker bottom-right
    grad = Image.linear_gradient("L").resize((S, S)).rotate(-45, resample=Image.BICUBIC, fillcolor=255)
    side = ImageChops.multiply(m, grad.point(lambda v: int(max(0, v - 90) * 0.75)))
    _paint(img, c["side"], side)
    # soft inner rim on the shadow side (bottom-right edges)
    blur = m.filter(ImageFilter.GaussianBlur(S * 0.035))
    k = int(S * 0.03)
    rim = ImageChops.subtract(m, _shift(blur, -k, -k)).point(lambda v: int(v * 0.85))
    _paint(img, c["rim"], rim)
    # soft glow on the lit side (top-left edges)
    glow = ImageChops.subtract(m, _shift(blur, k, k)).point(lambda v: int(v * 0.55))
    _paint(img, c["light"], glow)
    # specular highlight on the head
    spot = Image.new("L", (S, S), 0)
    hx, hy = {"P": (0.42, 0.29), "R": (0.36, 0.22), "B": (0.42, 0.27), "Q": (0.40, 0.25),
              "K": (0.38, 0.27), "N": (0.33, 0.37)}[kind]
    ImageDraw.Draw(spot).ellipse((S * (hx - 0.05), S * (hy - 0.035), S * (hx + 0.05), S * (hy + 0.035)), fill=150)
    spot = ImageChops.multiply(spot.filter(ImageFilter.GaussianBlur(S * 0.018)), m)
    _paint(img, c["light"], spot)
    if kind == "N":  # eye
        ImageDraw.Draw(img).ellipse((S * 0.43, S * 0.29, S * 0.48, S * 0.34), fill=c["rim"] + (255,))
    # soft ground shadow, slightly to the right
    sh = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sh).ellipse((S * 0.24, S * 0.84, S * 0.86, S * 0.96), fill=70)
    sh = sh.filter(ImageFilter.GaussianBlur(S * 0.025))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _paint(out, c["shadow"], sh)
    out.alpha_composite(img)
    return out.resize((size, size), Image.LANCZOS)


# ---- pixel ------------------------------------------------------------------------
PIXEL = {
    "P": ["............", "............", ".....##.....", "....####....", "....####....", ".....##.....",
          "....####....", "....####....", "...######...", "..########..", "..########..", "............"],
    "R": ["............", "..##.##.##..", "..########..", "...######...", "...######...", "...######...",
          "...######...", "...######...", "..########..", ".##########.", ".##########.", "............"],
    "B": ["............", ".....##.....", "....###.....", "...###.#....", "...##.###...", "...######...",
          "....####....", ".....##.....", "...######...", "..########..", "..########..", "............"],
    "N": ["............", "....##.#....", "...######...", "..#######...", ".####.###...", ".##..####...",
          ".....####...", "....#####...", "...######...", "..########..", "..########..", "............"],
    "Q": ["............", ".#...##...#.", ".##.####.##.", ".##########.", "..########..", "...######...",
          "....####....", "....####....", "...######...", "..########..", "..########..", "............"],
    "K": [".....##.....", "....####....", ".....##.....", "...######...", "..########..", "..########..",
          "...######...", "....####....", "...######...", "..########..", "..########..", "............"],
}
PIX_COL = {"w": ((244, 244, 238), (22, 22, 28), (200, 200, 192)), "b": ((70, 70, 84), (10, 10, 14), (110, 110, 128))}


def pixel_piece(letter, size=96):
    rows = PIXEL[letter.upper()]
    fill, line, shade = PIX_COL["w" if letter.isupper() else "b"]
    n = len(rows)
    filled = {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "#"}
    small = Image.new("RGBA", (n + 2, n + 2), (0, 0, 0, 0))
    px = small.load()
    for (x, y) in filled:  # outline: every empty neighbour of a filled pixel
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in filled:
                px[q[0] + 1, q[1] + 1] = line + (255,)
    for (x, y) in filled:
        right_edge = (x + 1, y) not in filled or (x, y + 1) not in filled
        px[x + 1, y + 1] = (shade if right_edge else fill) + (255,)
    return small.resize((size, size), Image.NEAREST)


def build(save):
    """save(name, image) -> image. Returns the images for the preview sheet."""
    out = []
    for p in "RNBQKPrnbqkp":
        name = ("w" if p.isupper() else "b") + p.upper()
        out.append(save("piece_soft_" + name, soft_piece(p)))
    for p in "RNBQKPrnbqkp":
        name = ("w" if p.isupper() else "b") + p.upper()
        out.append(save("piece_pixel_" + name, pixel_piece(p)))
    return out
