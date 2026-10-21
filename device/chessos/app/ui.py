"""Shared look & widgets (Duolingo-like dark theme)."""
import math
import random

from . import motion
from .content import COLORS

BG = (19, 31, 36)
CARD = (32, 47, 54)
CARD_HI = (44, 62, 71)
BORDER = (55, 70, 79)
TEXT = (241, 247, 251)
SUB = (130, 155, 166)
LOCK = (55, 70, 79)
LOCK_SHADE = (38, 52, 59)
WHITE = (255, 255, 255)
GOLD = COLORS["gold"]
GREEN = COLORS["green"]
RED = COLORS["red"]
BLUE = COLORS["blue"]
ORANGE = COLORS["orange"]
PURPLE = COLORS["purple"]

# GitHub contribution colours (dark mode)
GRID = [(22, 27, 34), (14, 68, 41), (0, 109, 50), (38, 166, 65), (57, 211, 83)]


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
        g.rect(0, y, 640, 480 - y + 4, (24, 40, 46))
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
