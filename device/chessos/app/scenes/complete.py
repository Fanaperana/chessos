"""Lesson complete + streak celebration screens."""
import datetime
import math

from .. import motion
from ..core import Scene
from ..ui import (BG, CARD, BORDER, TEXT, SUB, WHITE, GOLD, GREEN, BLUE, ORANGE, Confetti, button, hint)


class Complete(Scene):
    def __init__(self, app, title, xp, accuracy, elapsed, extended, goal_hit, lesson_id, color):
        Scene.__init__(self, app)
        self.title, self.xp, self.acc, self.elapsed = title, xp, accuracy, elapsed
        self.extended, self.goal_hit, self.lesson_id, self.color = extended, goal_hit, lesson_id, color
        self.confetti = Confetti()

    def enter(self):
        self.t0 = motion.now()
        self.mascot = motion.Value(0).spring(1, "bouncy", delay=0.1)
        self.title_s = motion.Value(0).spring(1, "bouncy", delay=0.3)
        self.tiles = [motion.Value(0).spring(1, "bouncy", delay=0.6 + i * 0.12) for i in range(3)]
        self.count = motion.Value(0).tween(1, 1.0, "easeOut", delay=0.8)
        self.confetti.rain(90)
        self.confetti.burst(320, 160, 50, 300, 420)
        self.app.audio.sfx("complete")
        self.app.audio.speak(self.title)

    def update(self, dt, actions):
        if "a" in actions and motion.now() - self.t0 > 0.6:
            self.app.audio.sfx("select")
            if self.extended:
                self.app.replace(Streak(self.app, self.lesson_id, self.goal_hit))
            else:
                from .home import Home
                self.app.reset(Home(self.app, focus_lesson=self.lesson_id, celebrate=self.lesson_id))

    def draw(self, g, dt):
        jump = abs(math.sin((motion.now() - self.t0) * 4)) * 12 * max(0, 1 - (motion.now() - self.t0) / 2.5)
        g.draw_sprite("mascot", 320, 120 - jump, 150 * self.mascot.get())
        s = self.title_s.get()
        g.text(self.title, 320, 222, 32, GOLD[0], 900, align="c", valign="m", scale=max(0.01, s))
        tiles = [("TOTAL XP", "+%d" % int(round(self.xp * self.count.get())), GOLD),
                 ("ACCURACY", "%d%%" % int(round(self.acc * self.count.get())), GREEN),
                 ("TIME", "%d:%02d" % (int(self.elapsed) // 60, int(self.elapsed) % 60), BLUE)]
        for i, (label, val, cols) in enumerate(tiles):
            v = self.tiles[i].get()
            x = 92 + i * 160
            y = 270 + (1 - v) * 40
            a = max(0.0, min(1.0, v))
            g.rrect(x, y, 136, 92, 16, cols[0], a)
            g.text(label, x + 68, y + 8, 12, WHITE, 900, align="c", a=a)
            g.rrect(x + 3, y + 28, 130, 61, 13, BG, a)
            g.text(val, x + 68, y + 58, 26, cols[0], 900, align="c", valign="m", a=a)
        if self.goal_hit:
            g.text("Daily goal reached!", 320, 380, 16, ORANGE[0], 900, align="c")
        button(g, 200, 404, 240, 48, "CONTINUE", GREEN)
        self.confetti.draw(g, dt)


class Streak(Scene):
    def __init__(self, app, lesson_id, goal_hit):
        Scene.__init__(self, app)
        self.lesson_id = lesson_id
        self.goal_hit = goal_hit

    def enter(self):
        p = self.app.progress
        self.n = p.streak()
        self.t0 = motion.now()
        self.flame = motion.Value(0).spring(1, "wobbly", delay=0.15)
        self.roll = motion.Value(0).spring(1, "bouncy", delay=0.7)
        self.days = [motion.Value(0).spring(1, "bouncy", delay=1.0 + i * 0.07) for i in range(7)]
        self.confetti = Confetti()
        self.app.audio.sfx("streak")
        line = "%d day streak!" % self.n
        self.app.audio.speak(line if self.app.audio.has_clip(line) else "You extended your streak!")
        self.burst = False

    def update(self, dt, actions):
        if not self.burst and motion.now() - self.t0 > 0.8:
            self.burst = True
            self.confetti.burst(320, 170, 40, 220, 360)
        if "a" in actions and motion.now() - self.t0 > 0.6:
            from .home import Home
            self.app.reset(Home(self.app, focus_lesson=self.lesson_id, celebrate=self.lesson_id))

    def draw(self, g, dt):
        f = self.flame.get()
        flick = 1 + 0.04 * math.sin(motion.now() * 9)
        g.circle(320, 160, 90 * f, ORANGE[0], 0.12)
        g.draw_sprite("flame", 320, 150, 150 * f * flick)
        r = self.roll.get()
        old, new = self.n - 1, self.n
        # number rolls up from the previous streak value
        g.clip((200, 236, 240, 70))
        g.text(str(old), 320, 270 - r * 64, 56, ORANGE[0], 900, align="c", valign="m", a=1 - min(1, r))
        g.text(str(new), 320, 270 + (1 - r) * 64, 56, ORANGE[0], 900, align="c", valign="m")
        g.clip(None)
        g.text("day streak!", 320, 318, 24, ORANGE[0], 900, align="c", valign="m")
        # this week
        p = self.app.progress
        today = p.today()
        start = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
        g.rrect(110, 346, 420, 64, 16, CARD)
        for i in range(7):
            d = start + datetime.timedelta(days=i)
            x = 110 + 30 + i * 60
            v = self.days[i].get()
            g.text("SMTWTFS"[i], x, 354, 12, ORANGE[0] if d == today else SUB, 900, align="c")
            done = p.xp_on(d) > 0
            g.circle(x, 388, 13 * v, ORANGE[0] if done else BORDER)
            if done:
                g.draw_sprite("check", x, 388, 16 * v)
        if self.goal_hit:
            g.text("Daily goal reached!", 320, 420, 14, GOLD[0], 900, align="c")
        button(g, 200, 432, 240, 40, "CONTINUE", GREEN, size=15)
        self.confetti.draw(g, dt)
