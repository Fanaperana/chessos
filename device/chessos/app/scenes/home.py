"""Home: Duolingo-style lesson path + daily puzzle, practice and activity cards."""
import datetime
import os
import math

from .. import motion
from ..board import draw_mini
from ..content import UNITS, COLORS
from ..core import Scene
from ..progress import MAX_CROWNS
from ..ui import (BG, CARD, CARD_HI, BORDER, TEXT, SUB, LOCK, LOCK_SHADE, WHITE, GOLD, GREEN, BLUE,
                  ORANGE, GRID, grid_level, progress_bar, bubble, hint)

TOP = 50
PATH_W = 404
SIDE_X = 414
SIDE_W = 214
OFFSETS = [0, -48, -70, -48, 0, 48, 70, 48]
NODE_R = 30
SPACING = 88
HEADER_H = 118
PIECE_GLYPH = {"K": u"♚", "Q": u"♛", "R": u"♜", "B": u"♝", "N": u"♞", "P": u"♟"}


class Node(object):
    def __init__(self, unit, uidx, lesson, lidx, gidx, cx, cy):
        self.unit, self.uidx, self.lesson, self.lidx, self.gidx = unit, uidx, lesson, lidx, gidx
        self.cx, self.cy = cx, cy
        self.pop = motion.Value(0)
        self.scale = motion.Value(1)


def draw_top_stats(g, app, right=630):
    """Streak flame, crowns and XP in the top bar (right aligned)."""
    p = app.progress
    streak = p.streak()
    lit = p.xp_today() > 0
    items = [
        ("flame" if lit else "flame_gray", str(streak), ORANGE[0] if lit else SUB),
        ("crown", str(sum(p.crowns(l["id"]) for u in UNITS for l in u["lessons"])), GOLD[0]),
        ("gem", str(p.total_xp()), BLUE[0]),
    ]
    x = right
    for icon, num, col in reversed(items):
        w = g.text_size(num, 18, 900)[0]
        x -= w
        g.text(num, x, 25, 18, col, 900, valign="m")
        x -= 26
        wob = 1 + (0.06 * motion.pulse(3) if icon == "flame" and lit else 0)
        g.draw_sprite(icon, x + 11, 25, 24 * wob)
        x -= 16


class Home(Scene):
    def __init__(self, app, focus_lesson=None, celebrate=None):
        Scene.__init__(self, app)
        self.focus_lesson = focus_lesson
        self.celebrate = celebrate  # lesson id that just earned a crown

    def enter(self):
        p = self.app.progress
        self.nodes = []
        self.headers = []
        y = 16
        gidx = 0
        self.current = None
        for ui_, u in enumerate(UNITS):
            self.headers.append((u, ui_, y))
            y += HEADER_H
            for li, l in enumerate(u["lessons"]):
                cx = PATH_W / 2.0 + OFFSETS[li % len(OFFSETS)]
                n = Node(u, ui_, l, li, gidx, cx, y + NODE_R + 6)
                n.crowns = p.crowns(l["id"])
                self.nodes.append(n)
                if self.current is None and n.crowns == 0:
                    self.current = n
                y += SPACING
                gidx += 1
            y += 20
        self.content_h = y
        unlocked = True
        test_unlock = os.environ.get("CHESSOS_UNLOCK") == "1"
        for n in self.nodes:
            n.unlocked = unlocked or test_unlock
            if n.crowns == 0:
                unlocked = False
        sel = self.current or self.nodes[-1]
        if self.focus_lesson:
            for n in self.nodes:
                if n.lesson["id"] == self.focus_lesson:
                    sel = n
        self.sel = sel.gidx
        self.cam = motion.Value(self.cam_target())
        self.cam.set(self.cam_target() + 60).spring(self.cam_target(), "gentle")
        for n in self.nodes:
            d = abs(n.gidx - self.sel)
            n.pop.set(0).spring(1, "bouncy", delay=motion.stagger(min(d, 8), 0.05, 0.05))
        self.nodes[self.sel].scale.set(1).spring(1.12, "bouncy")
        self.focus = "path"
        self.side = 0
        self.side_pop = [motion.Value(0).spring(1, "bouncy", delay=0.15 + i * 0.08) for i in range(3)]
        self.side_focus = motion.Value(0)
        self.popover = None
        self.pop_s = motion.Value(0)
        today = p.today()
        self.daily, self.daily_live = self.app.puzzles.daily(today)
        self.daily_done = today.isoformat() in p.data["daily_done"]
        self.daily_pos = self.daily.start() if self.daily else None
        if self.daily and self.daily.premove:
            try:
                self.daily_pos = self.daily_pos.push(self.daily_pos.parse_uci(self.daily.moves[0]))
            except Exception:
                pass
        self.grid_pop = motion.Value(0).tween(1, 0.9, "easeOut", delay=0.3)
        if self.celebrate:
            for n in self.nodes:
                if n.lesson["id"] == self.celebrate:
                    n.pop.set(1)
                    n.scale.set(1.6).spring(1.12 if n.gidx == self.sel else 1, "wobbly")

    def cam_target(self):
        n = self.nodes[self.sel]
        t = n.cy - 200
        return max(0, min(t, self.content_h - (480 - TOP)))

    # ---- input --------------------------------------------------------------------------
    def select(self, idx):
        idx = max(0, min(len(self.nodes) - 1, idx))
        if idx == self.sel:
            return
        self.nodes[self.sel].scale.spring(1, "snappy")
        self.sel = idx
        self.nodes[idx].scale.spring(1.12, "bouncy")
        self.cam.spring(self.cam_target(), "gentle")
        self.app.audio.sfx("nav")

    def update(self, dt, actions):
        st = self.app.puzzles.download_state
        if st in ("ok", "fail"):
            self.app.puzzles.download_state = None
            if st == "ok":
                self.app.audio.speak("Daily puzzle downloaded.")
                self.enter_keep_focus()
            else:
                self.app.audio.speak("No internet connection. Using the offline puzzle.")
            self.toast = (self.app.puzzles.download_msg, motion.now())
        for a in actions:
            if self.popover is not None:
                self.popover_input(a)
                continue
            if a == "start":
                from .settings import Settings
                self.app.push(Settings(self.app), fade=True)
                return
            if a == "select":
                from .stats import Stats
                self.app.push(Stats(self.app), fade=True)
                return
            if self.focus == "path":
                if a == "up":
                    self.select(self.sel - 1)
                elif a == "down":
                    self.select(self.sel + 1)
                elif a == "l1":
                    self.jump_unit(-1)
                elif a == "r1":
                    self.jump_unit(1)
                elif a == "right":
                    self.focus = "side"
                    self.side_focus.spring(1, "snappy")
                    self.app.audio.sfx("nav")
                elif a == "a":
                    self.open_popover()
            else:
                if a == "up":
                    self.side = max(0, self.side - 1)
                    self.app.audio.sfx("nav")
                elif a == "down":
                    self.side = min(2, self.side + 1)
                    self.app.audio.sfx("nav")
                elif a in ("left", "b"):
                    self.focus = "path"
                    self.side_focus.spring(0, "snappy")
                    self.app.audio.sfx("nav")
                elif a == "x" and self.side == 0:
                    self.app.puzzles.download_daily(self.app.progress.today())
                    self.app.audio.sfx("select")
                elif a == "a":
                    self.open_side()

    def resume(self):
        self.enter_keep_focus()

    def enter_keep_focus(self):
        focus, side = self.focus, self.side
        self.focus_lesson = self.nodes[self.sel].lesson["id"]
        self.enter()
        self.focus, self.side = focus, side
        if focus == "side":
            self.side_focus.set(1)

    def jump_unit(self, d):
        u = self.nodes[self.sel].uidx + d
        for n in self.nodes:
            if n.uidx == u:
                self.select(n.gidx)
                return

    def open_popover(self):
        self.popover = self.nodes[self.sel]
        self.pop_s.set(0.6).spring(1, "bouncy")
        self.app.audio.sfx("select")
        self.app.audio.speak(self.popover.lesson["title"])

    def popover_input(self, a):
        n = self.popover
        if a == "b":
            self.popover = None
            self.app.audio.sfx("nav")
        elif a == "a":
            if n.unlocked:
                from .lesson import Lesson
                self.popover = None
                self.app.audio.sfx("select")
                self.app.push(Lesson(self.app, "lesson", unit=n.unit, lesson=n.lesson), fade=True)
            else:
                self.nodes[self.sel].scale.set(1.12).spring(1.12, "bouncy", velocity=-6)
                self.app.audio.sfx("wrong")
        elif a in ("up", "down"):
            self.popover = None
            self.update(0, [a])

    def open_side(self):
        from .lesson import Lesson
        self.app.audio.sfx("select")
        if self.side == 0 and self.daily:
            self.app.push(Lesson(self.app, "daily", puzzle=self.daily), fade=True)
        elif self.side == 1:
            self.app.push(Lesson(self.app, "practice"), fade=True)
        elif self.side == 2:
            from .stats import Stats
            self.app.push(Stats(self.app), fade=True)

    # ---- drawing -----------------------------------------------------------------------------
    def draw(self, g, dt):
        cam = self.cam.get()
        g.clip((0, TOP, PATH_W + 6, 480 - TOP))
        oy = TOP - cam
        for u, ui_, y in self.headers:
            self.draw_header(g, u, ui_, y + oy)
        # path dots between nodes
        for i in range(len(self.nodes) - 1):
            a, b = self.nodes[i], self.nodes[i + 1]
            if a.uidx != b.uidx:
                continue
            for k in range(1, 4):
                t = k / 4.0
                x = a.cx + (b.cx - a.cx) * t
                y = a.cy + (b.cy - a.cy) * t + oy
                if TOP - 10 < y < 490:
                    g.circle(x, y, 3, BORDER if not b.unlocked else COLORS[b.unit["color"]][1], 0.8)
        for n in self.nodes:
            y = n.cy + oy
            if -60 < y < 540:
                self.draw_node(g, n, y)
        # mascot cheering next to the current lesson
        cur = self.current
        if cur is not None:
            side = -1 if OFFSETS[cur.lidx % 8] >= 0 else 1
            mx = cur.cx + side * 118
            my = cur.cy + oy + 4 * math.sin(motion.now() * 2.4)
            g.draw_sprite("mascot", mx, my, 78, flip=1 if side > 0 else 0)
        if self.popover is not None:
            self.draw_popover(g, self.popover, self.popover.cy + oy)
        g.clip(None)
        self.draw_side(g)
        # top bar
        g.rect(0, 0, 640, TOP, BG)
        g.rect(0, TOP - 2, 640, 2, BORDER)
        g.draw_sprite("mascot", 26, 25, 36)
        g.text("Chess", 48, 25, 22, GREEN[0], 900, valign="m")
        g.text("OS", 48 + g.text_size("Chess", 22, 900)[0], 25, 22, TEXT, 900, valign="m")
        draw_top_stats(g, self.app)
        toast = getattr(self, "toast", None)
        if toast and motion.now() - toast[1] < 3.5:
            a = min(1.0, (3.5 - (motion.now() - toast[1])) * 2)
            w = g.text_size(toast[0], 14, 800)[0] + 30
            g.rrect(320 - w / 2, 440, w, 30, 15, CARD_HI, a)
            g.text(toast[0], 320, 455, 14, TEXT, 800, align="c", valign="m", a=a)

    def draw_header(self, g, u, ui_, y):
        if y > 490 or y < -100:
            return
        main, shade, light = COLORS[u["color"]]
        g.button3d(14, y, PATH_W - 28, 76, main, shade, r=16, depth=4)
        g.text("UNIT %d" % (ui_ + 1), 30, y + 12, 13, light, 900)
        g.text(u["title"], 30, y + 29, 21, WHITE, 900)
        g.text(u["blurb"], 30, y + 54, 13, light, 800)
        done = sum(1 for l in u["lessons"] if self.app.progress.crowns(l["id"]) > 0)
        g.text("%d/%d" % (done, len(u["lessons"])), PATH_W - 32, y + 14, 14, WHITE, 900, align="r")

    def draw_node(self, g, n, y):
        s = n.pop.get() * n.scale.get()
        if s <= 0.02:
            return
        main, shade, light = COLORS[n.unit["color"]]
        if n.crowns >= MAX_CROWNS:
            main, shade = GOLD[0], GOLD[1]
        if not n.unlocked:
            main, shade = LOCK, LOCK_SHADE
        r = NODE_R * s
        selected = n.gidx == self.sel and self.focus == "path"
        if n is self.current:
            halo = r + 8 + 3 * motion.pulse(2)
            g.circle(n.cx, y + 2, halo, main, 0.22)
        if selected:
            g.circle(n.cx, y + 3, r + 6, WHITE, 0.9)
            g.circle(n.cx, y + 3, r + 3, BG)
        g.circle(n.cx, y + 6, r, shade)
        g.circle(n.cx, y, r, main)
        if n.unlocked:
            g.circle(n.cx - r * 0.25, y - r * 0.35, r * 0.28, WHITE, 0.18)
        icon = n.lesson["icon"]
        if not n.unlocked:
            g.draw_sprite("lock", n.cx, y, r * 0.95, color=(90, 110, 120))
        elif icon == "check":
            g.draw_sprite("check", n.cx, y, r * 1.1)
        elif icon in PIECE_GLYPH:
            g.text(PIECE_GLYPH[icon], n.cx, y + 1, int(30), WHITE, "sym", align="c", valign="m", scale=s)
        if n.crowns > 0:
            g.circle(n.cx + r * 0.78, y + r * 0.7, 12, GOLD[1])
            g.draw_sprite("crown", n.cx + r * 0.78, y + r * 0.66, 16)
            g.text(str(n.crowns), n.cx + r * 0.78, y + r * 0.7 + 4, 9, (90, 60, 0), 900, align="c", valign="m")
        if selected and self.popover is None:
            label = "START" if n is self.current else ("REVIEW" if n.unlocked else "LOCKED")
            bob = 3 * math.sin(motion.now() * 4)
            w = g.text_size(label, 14, 900)[0] + 26
            bx, by = n.cx - w / 2.0, y - r - 44 + bob
            col = main if n.unlocked else SUB
            g.rrect(bx - 2, by - 2, w + 4, 32, 10, BORDER)
            g.rrect(bx, by, w, 28, 9, CARD_HI)
            for i in range(6):
                g.rect(n.cx - (6 - i), by + 28 + i, (6 - i) * 2, 1, CARD_HI)
            g.text(label, n.cx, by + 14, 14, col, 900, align="c", valign="m")

    def draw_popover(self, g, n, y):
        s = self.pop_s.get()
        main, shade, light = COLORS[n.unit["color"]]
        if not n.unlocked:
            main, shade = CARD_HI, BORDER
        w, h = 300 * s, 124 * s
        x = max(8, min(PATH_W - 8 - w, n.cx - w / 2.0))
        py = y + NODE_R + 18
        if py + h > 470:
            py = y - NODE_R - 18 - h
        g.rrect(x, py, w, h, 16, main)
        if s < 0.9:
            return
        l = n.lesson
        g.text(l["title"], x + 18, py + 14, 20, WHITE, 900)
        if n.unlocked:
            lvl = min(n.crowns + 1, MAX_CROWNS)
            sub = "Level %d of %d" % (lvl, MAX_CROWNS) if n.crowns < MAX_CROWNS else "Legendary! Practice again"
            g.text(sub, x + 18, py + 42, 14, light, 800)
            for i in range(MAX_CROWNS):
                g.draw_sprite("crown", x + w - 30 - i * 22, py + 24, 20, a=1.0 if i < n.crowns else 0.25)
            fy = g.button3d(x + 16, py + 70, w - 32, 40, WHITE, light, r=12, depth=4)
            xp = 10 if l["kind"] != "puzzles" else 15
            g.text("START  +%d XP" % xp, x + w / 2.0, fy + 20, 16, main, 900, align="c", valign="m")
        else:
            g.text_block("Complete all lessons above to unlock this one!", x + 18, py + 44, w - 36, 14, SUB, 800)
            fy = g.button3d(x + 16, py + 76, w - 32, 36, BORDER, LOCK_SHADE, r=12, depth=4)
            g.text("LOCKED", x + w / 2.0, fy + 18, 15, SUB, 900, align="c", valign="m")

    def card(self, g, i, x, y, w, h):
        s = self.side_pop[i].get()
        focused = self.focus == "side" and self.side == i
        if focused:
            g.rrect(x - 3, y - 3, w + 6, h + 6, 17, GREEN[0])
        else:
            g.rrect(x - 2, y - 2, w + 4, h + 4, 16, BORDER)
        g.rrect(x, y, w, h, 14, CARD)
        return s

    def draw_side(self, g):
        x, w = SIDE_X, SIDE_W
        p = self.app.progress
        # --- daily puzzle card
        y = TOP + 10
        dx = (1 - self.side_pop[0].get()) * 60
        self.card(g, 0, x + dx, y, w, 150)
        g.text("Daily Puzzle", x + dx + 12, y + 10, 17, TEXT, 900)
        g.text(p.today().strftime("%a, %b %d"), x + dx + w - 12, y + 13, 12, SUB, 800, align="r")
        if self.daily_pos is not None:
            draw_mini(g, self.daily_pos, x + dx + 12, y + 38, 11, p.setting("board"),
                      flip=self.daily.solver() == "b")
        tx = x + dx + 112
        if self.daily_done:
            g.circle(tx + 14, y + 56, 13, GREEN[0])
            g.draw_sprite("check", tx + 14, y + 56, 16)
            g.text("Solved!", tx + 32, y + 48, 15, GREEN[0], 900)
        else:
            g.text("+15 XP", tx, y + 46, 16, GOLD[0], 900)
        if self.daily:
            g.text("Rating %d" % self.daily.rating if self.daily.rating else "Custom", tx, y + 76, 13, SUB, 800)
            g.text("To move:", tx, y + 94, 13, SUB, 800)
            side = self.daily.solver()
            g.circle(tx + 64, y + 103, 8, SUB)
            g.circle(tx + 64, y + 103, 6.5, WHITE if side == "w" else (30, 30, 30))
            g.text("LIVE" if self.daily_live else "OFFLINE", tx, y + 114, 11, BLUE[0] if self.daily_live else SUB, 900)
        if self.app.puzzles.download_state == "running":
            g.text("Downloading...", x + dx + 12, y + 132, 11, BLUE[0], 900)
        elif self.focus == "side" and self.side == 0:
            g.text("A play · X download", x + dx + 12, y + 132, 11, SUB, 800)
        # --- practice card
        y = TOP + 172
        dx = (1 - self.side_pop[1].get()) * 60
        self.card(g, 1, x + dx, y, w, 52)
        g.circle(x + dx + 28, y + 26, 18, BLUE[1])
        g.text(PIECE_GLYPH["N"], x + dx + 28, y + 27, 22, WHITE, "sym", align="c", valign="m")
        g.text("Practice", x + dx + 54, y + 8, 16, TEXT, 900)
        g.text("Puzzle rating %d" % p.data.get("practice_rating", 900), x + dx + 54, y + 28, 12, SUB, 800)
        # --- activity card (GitHub-style grid)
        y = TOP + 236
        dx = (1 - self.side_pop[2].get()) * 60
        self.card(g, 2, x + dx, y, w, 166)
        g.text("Activity", x + dx + 12, y + 8, 16, TEXT, 900)
        goal = p.goal()
        xp = p.xp_today()
        g.text("%d/%d XP" % (min(xp, 999), goal), x + dx + w - 12, y + 11, 12, GOLD[0] if xp >= goal else SUB, 900, align="r")
        progress_bar(g, x + dx + 12, y + 34, w - 24, 10, xp / float(goal), GOLD[0] if xp >= goal else ORANGE[0])
        self.draw_grid(g, x + dx + 12, y + 54, weeks=15)
        g.text("Less", x + dx + 12, y + 146, 10, SUB, 800)
        for i in range(5):
            g.rrect(x + dx + 40 + i * 13, y + 147, 10, 10, 2, GRID[i])
        g.text("More", x + dx + 108, y + 146, 10, SUB, 800)
        # footer hints
        hint(g, SIDE_X + 2, 457, [("START", "Menu"), ("SELECT", "Stats")], align="l")

    def draw_grid(self, g, x, y, weeks=15, cell=11, gap=2):
        p = self.app.progress
        today = p.today()
        # week columns start on Sunday like GitHub
        first = today - datetime.timedelta(days=(today.weekday() + 1) % 7 + 7 * (weeks - 1))
        goal = p.goal()
        pop = self.grid_pop.get()
        for wk in range(weeks):
            colt = max(0.0, min(1.0, pop * weeks * 1.3 - wk * 0.9))
            if colt <= 0:
                continue
            for dow in range(7):
                d = first + datetime.timedelta(days=wk * 7 + dow)
                if d > today:
                    continue
                lvl = grid_level(p.xp_on(d), goal)
                s = cell * colt
                cx = x + wk * (cell + gap) + cell / 2.0
                cy = y + dow * (cell + gap) + cell / 2.0
                g.rect(cx - s / 2, cy - s / 2, s, s, GRID[lvl])
                if d == today:
                    a = 0.5 + 0.5 * motion.pulse(2)
                    g.rect(cx - cell / 2 - 1, cy - cell / 2 - 1, cell + 2, 1, WHITE, a)
                    g.rect(cx - cell / 2 - 1, cy + cell / 2, cell + 2, 1, WHITE, a)
                    g.rect(cx - cell / 2 - 1, cy - cell / 2, 1, cell, WHITE, a)
                    g.rect(cx + cell / 2, cy - cell / 2, 1, cell, WHITE, a)
