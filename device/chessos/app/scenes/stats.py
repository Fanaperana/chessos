"""Full-year GitHub-style contribution grid + totals."""
import datetime

from .. import motion
from ..core import Scene
from ..ui import (BG, CARD, CARD_HI, BORDER, TEXT, SUB, WHITE, GOLD, GREEN, BLUE, ORANGE, PURPLE,
                  GRID, grid_level, hint)
from .home import draw_top_stats

WEEKS = 53
CELL = 9
GAP = 2
GX, GY = 44, 222


class Stats(Scene):
    def enter(self):
        p = self.app.progress
        self.today = p.today()
        self.first = self.today - datetime.timedelta(days=(self.today.weekday() + 1) % 7 + 7 * (WEEKS - 1))
        self.cur = (WEEKS - 1, (self.today.weekday() + 1) % 7)
        self.cur_x = motion.Value(0)
        self.cur_y = motion.Value(0)
        self.place(True)
        self.cols = [motion.Value(0).spring(1, "bouncy", delay=motion.stagger(WEEKS - 1 - i, 0.012, 0.15))
                     for i in range(WEEKS)]
        self.tiles = [motion.Value(0).spring(1, "bouncy", delay=0.05 + i * 0.06) for i in range(5)]

    def resume(self):
        pass

    def place(self, instant=False):
        x = GX + self.cur[0] * (CELL + GAP)
        y = GY + self.cur[1] * (CELL + GAP)
        if instant:
            self.cur_x.set(x)
            self.cur_y.set(y)
        else:
            self.cur_x.spring(x, "stiff")
            self.cur_y.spring(y, "stiff")

    def date_at(self, c, r):
        return self.first + datetime.timedelta(days=c * 7 + r)

    def update(self, dt, actions):
        for a in actions:
            c, r = self.cur
            if a == "left":
                c -= 1
            elif a == "right":
                c += 1
            elif a == "up":
                r -= 1
            elif a == "down":
                r += 1
            elif a == "l1":
                c -= 4
            elif a == "r1":
                c += 4
            elif a in ("b", "select", "start", "a"):
                self.app.pop(fade=True)
                return
            c = max(0, min(WEEKS - 1, c))
            r = max(0, min(6, r))
            if self.date_at(c, r) > self.today:
                continue
            if (c, r) != self.cur:
                self.cur = (c, r)
                self.place()
                self.app.audio.sfx("nav")

    def draw(self, g, dt):
        p = self.app.progress
        g.text("Your chess year", 20, 25, 22, TEXT, 900, valign="m")
        draw_top_stats(g, self.app)
        g.rect(0, 48, 640, 2, BORDER)
        tiles = [
            ("flame", "%d" % p.streak(), "Day streak", ORANGE[0]),
            ("flame", "%d" % p.longest_streak(), "Longest", ORANGE[1]),
            ("gem", "%d" % p.total_xp(), "Total XP", BLUE[0]),
            ("crown", "%d" % p.data.get("lessons_done", 0), "Lessons", GOLD[0]),
            ("check", "%d" % p.data.get("puzzles_solved", 0), "Puzzles", GREEN[0]),
        ]
        for i, (icon, val, label, col) in enumerate(tiles):
            v = self.tiles[i].get()
            x = 20 + i * 122
            y = 64 + (1 - v) * 30
            a = max(0.0, min(1.0, v))
            g.rrect(x - 2, y - 2, 114, 74, 14, BORDER, a)
            g.rrect(x, y, 110, 70, 12, CARD, a)
            if icon == "check":
                g.circle(x + 22, y + 24, 12, col, a)
                g.draw_sprite("check", x + 22, y + 24, 15, a=a)
            else:
                g.draw_sprite(icon, x + 22, y + 24, 24, a=a)
            g.text(val, x + 40, y + 24, 22, col, 900, valign="m", a=a)
            g.text(label, x + 12, y + 46, 13, SUB, 800, a=a)
        # grid card
        g.rrect(16, 160, 608, 204, 14, CARD)
        days_active = sum(1 for k, v in p.data["xp_by_day"].items() if v > 0)
        g.text("%d active day%s in the last year" % (days_active, "" if days_active == 1 else "s"), 30, 172, 15, TEXT, 900)
        # month labels
        last_month = None
        for c in range(WEEKS):
            d = self.date_at(c, 0)
            if d.month != last_month and d.day <= 7:
                g.text(d.strftime("%b"), GX + c * (CELL + GAP), GY - 18, 11, SUB, 800)
                last_month = d.month
        for r, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
            g.text(lab, GX - 6, GY + r * (CELL + GAP) + CELL / 2.0, 10, SUB, 800, align="r", valign="m")
        goal = p.goal()
        for c in range(WEEKS):
            v = self.cols[c].get()
            if v <= 0.02:
                continue
            s = CELL * min(1.2, v)
            for r in range(7):
                d = self.date_at(c, r)
                if d > self.today:
                    continue
                lvl = grid_level(p.xp_on(d), goal)
                cx = GX + c * (CELL + GAP) + CELL / 2.0
                cy = GY + r * (CELL + GAP) + CELL / 2.0
                g.rect(cx - s / 2, cy - s / 2, s, s, GRID[lvl])
        # cursor
        cx, cy = self.cur_x.get(), self.cur_y.get()
        g.rrect(cx - 3, cy - 3, CELL + 6, CELL + 6, 4, WHITE, 0.9)
        d = self.date_at(*self.cur)
        lvl = grid_level(p.xp_on(d), goal)
        g.rrect(cx - 1, cy - 1, CELL + 2, CELL + 2, 2, GRID[lvl])
        # legend + detail
        g.text("Less", 470, 304, 11, SUB, 800)
        for i in range(5):
            g.rrect(498 + i * 15, 305, 11, 11, 2, GRID[i])
        g.text("More", 576, 304, 11, SUB, 800)
        xp = p.xp_on(d)
        detail = "%s  ·  %s" % (d.strftime("%a, %b %d %Y"), ("%d XP" % xp) if xp else "No activity")
        g.text(detail, 30, 330, 15, GREEN[0] if xp else SUB, 900)
        if p.data["daily_done"].get(d.isoformat()):
            g.text("Daily puzzle solved", 610, 332, 13, GOLD[0], 900, align="r")
        hint(g, 20, 448, [("D-pad", "Browse days"), ("L1/R1", "Month"), ("B", "Back")])
