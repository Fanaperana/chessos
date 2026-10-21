"""Animated ChessOS logo intro + "what day is it?" picker."""
import datetime
import math

from .. import motion
from ..core import Scene
from ..progress import parse_date
from ..ui import BG, GREEN, TEXT, SUB, BORDER, CARD, button, hint


class Splash(Scene):
    def enter(self):
        self.t0 = motion.now()
        self.logo = motion.Value(0).spring(1, "bouncy", delay=0.1)
        self.rot = motion.Value(-25).spring(0, "wobbly", delay=0.1)
        self.letters = [motion.Value(0).spring(1, "bouncy", delay=motion.stagger(i, 0.05, 0.45))
                        for i in range(len("ChessOS"))]
        self.tag = motion.Value(0).tween(1, 0.5, "easeOut", delay=0.9)
        self.done = False
        self.app.audio.speak("Welcome to ChessOS!")
        # warm up the packs we need soon (fast, lazy parse)
        self.app.puzzles.pack("daily")

    def next(self):
        if self.done:
            return
        self.done = True
        from .home import Home
        if self.app.progress.clock_suspicious():
            self.app.replace(DatePick(self.app, then_home=True))
        else:
            self.app.progress.mark_seen()
            self.app.replace(Home(self.app))

    def update(self, dt, actions):
        if actions or motion.now() - self.t0 > 2.6:
            self.next()

    def draw(self, g, dt):
        s = self.logo.get()
        cx, cy = 320, 190
        g.circle(cx, cy + 8, 92 * s, GREEN[1], 0.35)
        g.circle(cx, cy, 86 * s, (30, 52, 40))
        g.draw_sprite("mascot", cx, cy - 6 + 4 * math.sin(motion.now() * 3), 150 * s, angle=self.rot.get())
        word = "ChessOS"
        x = 320 - g.text_size(word, 48, 900)[0] / 2.0
        for i, ch in enumerate(word):
            v = self.letters[i].get()
            w = g.text_size(ch, 48, 900)[0]
            col = GREEN[0] if i < 5 else TEXT
            g.text(ch, x + w / 2.0, 330 - (1 - v) * 40, 48, col, 900, align="c", valign="m", a=max(0.0, min(1.0, v)))
            x += w
        g.text("Learn chess, one day at a time.", 320, 372, 17, SUB, 800, align="c", a=self.tag.get())


class DatePick(Scene):
    """The R36S forgets the date without Wi-Fi. Ask the player once per launch if it looks wrong."""

    def __init__(self, app, then_home=False):
        Scene.__init__(self, app)
        self.then_home = then_home
        p = app.progress
        last = p.data.get("last_seen")
        base = p.today()
        if last:
            try:
                d = parse_date(last)
                if base < d or base.year < 2025:
                    base = d
            except ValueError:
                pass
        self.date = base
        self.pop = motion.Value(0)

    def enter(self):
        self.pop.set(0).spring(1, "bouncy")
        self.bump = motion.Value(1)
        self.app.audio.speak("What day is it today?")

    def update(self, dt, actions):
        for a in actions:
            delta = {"left": -1, "right": 1, "up": 7, "down": -7, "l1": -30, "r1": 30}.get(a)
            if delta:
                self.date += datetime.timedelta(days=delta)
                self.bump.set(1).spring(1, "bouncy", velocity=6)
                self.app.audio.sfx("nav")
            elif a == "a":
                self.app.progress.set_today(self.date)
                self.app.audio.sfx("select")
                from .home import Home
                if self.then_home:
                    self.app.replace(Home(self.app))
                else:
                    self.app.pop(fade=True)
            elif a == "b" and not self.then_home:
                self.app.pop(fade=True)

    def draw(self, g, dt):
        s = self.pop.get()
        g.draw_sprite("mascot", 320, 92, 110 * s)
        g.text("What day is it today?", 320, 160, 28, TEXT, 900, align="c", a=min(1, s))
        g.text("Your R36S has no clock battery, so ChessOS asks to keep your streak right.",
               320, 198, 14, SUB, 700, align="c")
        b = self.bump.get()
        g.rrect(150, 236, 340, 96, 20, BORDER)
        g.rrect(152, 238, 336, 92, 18, CARD)
        g.text(self.date.strftime("%A"), 320, 254, 18, GREEN[0], 900, align="c")
        g.text(self.date.strftime("%B %d, %Y"), 320, 290, int(30), TEXT, 900, align="c", valign="m", scale=b)
        g.text("◀", 128, 284, 26, SUB, "sym", align="c", valign="m")
        g.text("▶", 512, 284, 26, SUB, "sym", align="c", valign="m")
        button(g, 220, 360, 200, 46, "THAT'S TODAY")
        hint(g, 320, 440, [("←→", "Day"), ("↑↓", "Week"), ("L1/R1", "Month"), ("A", "OK")], align="c")
