"""Shared look & widgets (Duolingo-like dark theme)."""
import math
import random

from . import motion
from .content import COLORS

# Colour tokens are lists so apply_theme() can recolour the whole UI in place
# (every screen imported the same list objects).
BG = [19, 31, 36]
CARD = [32, 47, 54]
CARD_HI = [44, 62, 71]
BORDER = [55, 70, 79]
TEXT = [241, 247, 251]
SUB = [130, 155, 166]
LOCK = [55, 70, 79]
LOCK_SHADE = [38, 52, 59]
FRAME = [14, 22, 26]        # behind the board
PANEL = [24, 40, 46]        # feedback banner
WHITE = (255, 255, 255)
GOLD = COLORS["gold"]
GREEN = COLORS["green"]     # the theme's main colour (buttons, focus, unit 1)
RED = COLORS["red"]
BLUE = COLORS["blue"]
ORANGE = COLORS["orange"]
PURPLE = COLORS["purple"]

GRID = [[22, 27, 34], [14, 68, 41], [0, 109, 50], [38, 166, 65], [57, 211, 83]]

THEMES = {
    # name: surfaces, main colour (main, shade, light), activity grid, light?
    "midnight": {"bg": (19, 31, 36), "card": (32, 47, 54), "card_hi": (44, 62, 71), "border": (55, 70, 79),
                 "text": (241, 247, 251), "sub": (130, 155, 166), "lock": (55, 70, 79), "lock_shade": (38, 52, 59),
                 "frame": (14, 22, 26), "panel": (24, 40, 46),
                 "main": ((88, 204, 2), (70, 163, 2), (215, 255, 184)),
                 "grid": ((22, 27, 34), (14, 68, 41), (0, 109, 50), (38, 166, 65), (57, 211, 83))},
    "ice": {"bg": (243, 247, 251), "card": (255, 255, 255), "card_hi": (230, 238, 246), "border": (214, 224, 234),
            "text": (30, 45, 60), "sub": (98, 116, 134), "lock": (220, 228, 236), "lock_shade": (192, 204, 216),
            "frame": (206, 216, 226), "panel": (255, 255, 255),
            "main": ((30, 144, 235), (20, 110, 190), (214, 236, 255)),
            "grid": ((228, 234, 240), (178, 214, 245), (110, 176, 236), (52, 136, 220), (20, 96, 180))},
    "ocean": {"bg": (12, 21, 37), "card": (21, 34, 57), "card_hi": (30, 47, 77), "border": (44, 63, 96),
              "text": (236, 243, 255), "sub": (128, 150, 186), "lock": (44, 63, 96), "lock_shade": (29, 43, 69),
              "frame": (7, 13, 24), "panel": (18, 30, 52),
              "main": ((34, 202, 232), (16, 150, 182), (210, 246, 252)),
              "grid": ((20, 30, 48), (14, 62, 86), (10, 112, 140), (24, 166, 196), (64, 222, 240))},
    "plum": {"bg": (27, 19, 39), "card": (41, 30, 59), "card_hi": (55, 41, 79), "border": (72, 56, 100),
             "text": (247, 241, 255), "sub": (162, 146, 192), "lock": (72, 56, 100), "lock_shade": (50, 38, 72),
             "frame": (17, 11, 26), "panel": (36, 26, 52),
             "main": ((255, 112, 122), (214, 74, 92), (255, 224, 228)),
             "grid": ((36, 26, 50), (92, 40, 66), (150, 56, 86), (214, 84, 106), (255, 122, 132))},
    "forest": {"bg": (15, 23, 17), "card": (25, 37, 28), "card_hi": (35, 51, 39), "border": (50, 70, 54),
               "text": (238, 246, 236), "sub": (140, 162, 142), "lock": (50, 70, 54), "lock_shade": (34, 49, 37),
               "frame": (8, 14, 10), "panel": (22, 34, 25),
               "main": ((255, 184, 40), (212, 144, 10), (255, 240, 204)),
               "grid": ((24, 34, 26), (74, 70, 24), (138, 116, 20), (206, 158, 24), (255, 196, 48))},
}
THEME_NAMES = ["midnight", "ice", "ocean", "plum", "forest"]


def apply_theme(name):
    t = THEMES.get(name, THEMES["midnight"])
    for token, key in ((BG, "bg"), (CARD, "card"), (CARD_HI, "card_hi"), (BORDER, "border"), (TEXT, "text"),
                       (SUB, "sub"), (LOCK, "lock"), (LOCK_SHADE, "lock_shade"), (FRAME, "frame"), (PANEL, "panel")):
        token[:] = t[key]
    for i in range(3):
        GREEN[i][:] = t["main"][i]
    for i in range(5):
        GRID[i][:] = t["grid"][i]


def grid_level(xp, goal):
    if xp <= 0:
        return 0
    if xp < goal * 0.5:
        return 1
    if xp < goal:
        return 2
    if xp < goal * 2:
        return 3
    return 4


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def progress_bar(g, x, y, w, h, frac, color=GREEN[0], bg=BORDER):
    g.rrect(x, y, w, h, h / 2.0, bg)
    fw = max(0.0, min(1.0, frac)) * w
    if fw > 1:
        fw = max(fw, h)
        g.rrect(x, y, fw, h, h / 2.0, color)
        # glossy highlight like Duolingo
        if fw > h:
            g.rrect(x + h / 2.0, y + h * 0.22, fw - h, h * 0.24, h * 0.12, WHITE, 0.28)


def button(g, x, y, w, h, label, colors=GREEN, focused=True, pressed=False, size=17, a=1.0):
    main, shade, _ = colors
    if not focused:
        main, shade = BORDER, LOCK_SHADE
    fy = g.button3d(x, y, w, h, main, shade, r=13, depth=4, pressed=pressed, a=a)
    g.text(label, x + w / 2.0, fy + h / 2.0, size, WHITE if focused else SUB, 900, align="c", valign="m", a=a)


def hint(g, x, y, items, align="l", a=1.0):
    """Controller hints like [('A', 'Select'), ('B', 'Back')]."""
    parts = []
    total = 0
    for key, label in items:
        kf = "sym" if any(ord(ch) > 127 for ch in key) else 900
        kw = max(20, g.text_size(key, 12, kf)[0] + 10)
        lw = g.text_size(label, 13, 800)[0]
        parts.append((key, label, kw, lw, kf))
        total += kw + 5 + lw + 12
    cx = x - total if align == "r" else (x - total / 2.0 if align == "c" else x)
    for key, label, kw, lw, kf in parts:
        g.rrect(cx, y, kw, 20, 10, BORDER, a)
        g.text(key, cx + kw / 2.0, y + 10, 12, TEXT, kf, align="c", valign="m", a=a)
        g.text(label, cx + kw + 5, y + 10, 13, SUB, 800, valign="m", a=a)
        cx += kw + 5 + lw + 12


def bubble(g, x, y, w, h, tail_x=None, tail_side="left", color=CARD, border=BORDER):
    """Speech bubble with a little tail pointing to the mascot."""
    g.rrect(x - 2, y - 2, w + 4, h + 4, 16, border)
    g.rrect(x, y, w, h, 14, color)
    if tail_side == "left":
        ty = y + (tail_x if tail_x is not None else h / 2.0)
        for i in range(9):
            g.rect(x - 9 + i, ty - (9 - i), 1, (9 - i) * 2, border)
        for i in range(7):
            g.rect(x - 6 + i, ty - (7 - i), 2, (7 - i) * 2, color)
    elif tail_side == "bottom":
        tx = x + (tail_x if tail_x is not None else w / 2.0)
        for i in range(9):
            g.rect(tx - (9 - i), y + h + 9 - i, (9 - i) * 2, 1, border)
        for i in range(7):
            g.rect(tx - (7 - i), y + h + 6 - i, (7 - i) * 2, 2, color)


class Confetti(object):
    COLORS = [GREEN[0], BLUE[0], GOLD[0], RED[0], PURPLE[0], ORANGE[0]]

    def __init__(self):
        self.p = []

    def burst(self, x, y, n=60, spread=260, up=380):
        rnd = random.random
        for _ in range(n):
            self.p.append([x, y, (rnd() - 0.5) * spread * 2, -up * (0.4 + rnd() * 0.8),
                           rnd() * 360, (rnd() - 0.5) * 720, random.choice(self.COLORS),
                           2.2 + rnd() * 1.2, 3 + rnd() * 4])

    def rain(self, n=70, w=640):
        rnd = random.random
        for _ in range(n):
            self.p.append([rnd() * w, -20 - rnd() * 200, (rnd() - 0.5) * 60, 60 + rnd() * 120,
                           rnd() * 360, (rnd() - 0.5) * 500, random.choice(self.COLORS),
                           3.5 + rnd() * 1.5, 3 + rnd() * 4])

    def draw(self, g, dt):
        alive = []
        for q in self.p:
            q[3] += 520 * dt
            q[2] *= (1 - 0.8 * dt)
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] += q[5] * dt
            q[7] -= dt
            if q[7] > 0 and q[1] < 520:
                alive.append(q)
                s = q[8]
                wob = abs(math.cos(math.radians(q[4])))
                g.rect(q[0], q[1], s * 1.6 * (0.3 + 0.7 * wob), s, q[6], min(1.0, q[7] * 2))
        self.p = alive


class Banner(object):
    """Bottom feedback panel that springs up (correct / wrong / info)."""
    H = 112

    def __init__(self):
        self.y = motion.Value(480)
        self.kind = None
        self.title = ""
        self.sub = ""
        self.button = "CONTINUE"
        self.visible = False

    def show(self, kind, title, sub="", button="CONTINUE"):
        self.kind, self.title, self.sub, self.button = kind, title, sub, button
        self.visible = True
        self.t0 = motion.now()
        self.y.set(480).spring(480 - self.H, "snappy")

    def hide(self):
        self.visible = False
        self.y.spring(480 + 6, "stiff")

    def draw(self, g):
        y = self.y.get()
        if y >= 480:
            return
        cols = {"good": GREEN, "bad": RED, "info": BLUE, "gold": GOLD}[self.kind or "info"]
        main, shade, light = cols
        g.rect(0, y, 640, 480 - y + 4, PANEL)
        g.rect(0, y, 640, 3, main)
        # icon badge
        pop = motion.Keyframes([0, 1.25, 1], 0.35, delay=0.05)
        pop.t0 = self.t0 + 0.05
        s = pop.get()
        g.circle(44, y + 40, 22 * s, main)
        if self.kind == "good" or self.kind == "gold":
            g.draw_sprite("check", 44, y + 40, 26 * s)
        elif self.kind == "bad":
            g.text("✕", 44, y + 40, int(22), WHITE, "sym", align="c", valign="m", scale=s)
        else:
            g.text("i", 44, y + 41, 24, WHITE, 900, align="c", valign="m", scale=s)
        g.text(self.title, 78, y + 18, 24, main, 900)
        if self.sub:
            g.text(self.sub, 78, y + 50, 15, TEXT, 800)
        bw = 176
        button(g, 640 - bw - 20, y + self.H - 58, bw, 42, self.button + "  (A)", cols, size=15)
