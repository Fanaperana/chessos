"""Settings menu."""
import os
import subprocess

from .. import motion
from ..core import Scene
from ..ui import BG, CARD, CARD_HI, BORDER, TEXT, SUB, WHITE, GREEN, RED, BLUE, GOLD, hint
from .home import draw_top_stats

GOALS = [10, 20, 30, 50]
BOARDS = ["green", "brown", "blue"]


class Settings(Scene):
    def enter(self):
        self.sel = 0
        self.items = self.build()
        self.pops = [motion.Value(0).spring(1, "snappy", delay=i * 0.03) for i in range(len(self.items))]
        self.sel_y = motion.Value(self.row_y(0))
        self.msg = None

    def resume(self):
        self.items = self.build()

    def build(self):
        p = self.app.progress
        on = lambda k: "On" if p.setting(k) else "Off"
        items = [
            ("Voice", on("voice"), "voice"),
            ("Sound effects", on("sfx"), "sfx"),
            ("Daily goal", "%d XP" % p.goal(), "goal"),
            ("Board colours", p.setting("board").title(), "board"),
            ("Swap A / B buttons", on("swap_ab"), "swap_ab"),
            ("Show FPS (beta)", on("fps"), "fps"),
            ("Today's date", p.today().strftime("%b %d, %Y"), "date"),
            ("Download daily puzzle", "Wi-Fi", "download"),
            ("Reset progress", "", "reset"),
            ("Power" if self.app.frontend else "Exit ChessOS", "", "exit"),
        ]
        return items

    def row_y(self, i):
        return 60 + i * 38

    def update(self, dt, actions):
        st = self.app.puzzles.download_state
        if st in ("ok", "fail"):
            self.msg = (self.app.puzzles.download_msg, motion.now())
            self.app.puzzles.download_state = None
        for a in actions:
            if a == "up":
                self.sel = (self.sel - 1) % len(self.items)
            elif a == "down":
                self.sel = (self.sel + 1) % len(self.items)
            elif a in ("b", "start"):
                self.app.pop(fade=True)
                return
            elif a in ("left", "right", "a"):
                self.change(self.items[self.sel][2], -1 if a == "left" else 1, a == "a")
                self.items = self.build()
                continue
            else:
                continue
            self.sel_y.spring(self.row_y(self.sel), "stiff")
            self.app.audio.sfx("nav")

    def change(self, key, d, pressed):
        p = self.app.progress
        au = self.app.audio
        if key in ("voice", "sfx", "swap_ab", "fps"):
            p.set_setting(key, not p.setting(key))
            self.app.apply_settings()
            au.sfx("select")
            if key == "voice" and p.setting("voice"):
                au.speak("Let's learn chess!")
        elif key == "goal":
            i = GOALS.index(p.goal()) if p.goal() in GOALS else 1
            p.set_setting("goal", GOALS[(i + d) % len(GOALS)])
            au.sfx("select")
        elif key == "board":
            i = BOARDS.index(p.setting("board")) if p.setting("board") in BOARDS else 0
            p.set_setting("board", BOARDS[(i + d) % len(BOARDS)])
            au.sfx("select")
        elif key == "date" and pressed:
            from .splash import DatePick
            self.app.push(DatePick(self.app), fade=True)
        elif key == "download" and pressed:
            self.app.puzzles.download_daily(p.today())
            self.msg = ("Downloading from lichess.org ...", motion.now())
            au.sfx("select")
        elif key == "reset" and pressed:
            from .dialog import Dialog

            def done(i):
                if i == 1:
                    p.reset()
                    self.msg = ("Progress reset.", motion.now())
            self.app.push(Dialog(self.app, "Reset progress?", "This deletes your XP, streak and crowns.",
                                 ["CANCEL", "RESET"], done, danger=1))
        elif key == "exit" and pressed:
            from .dialog import Dialog

            if self.app.frontend:
                # exit codes are read by boot.sh: 10 = power off, 11 = restart, 0 = ArkOS menus
                codes = {1: 10, 2: 11, 3: 0}

                def power(i):
                    if i in codes:
                        au.speak("Goodbye!")
                        self.app.exit_code = codes[i]
                        self.app.quit()
                self.app.push(Dialog(self.app, "Power", "See you tomorrow! Keep your streak alive.",
                                     ["CANCEL", "POWER OFF", "RESTART", "ARKOS MENUS (WI-FI)"], power, danger=1))
                return

            def bye(i):
                if i == 1:
                    au.speak("Goodbye!")
                    self.app.quit()
            self.app.push(Dialog(self.app, "Exit ChessOS?", "See you tomorrow! Keep your streak alive.",
                                 ["STAY", "EXIT"], bye, danger=1))

    def draw(self, g, dt):
        g.text("Settings", 20, 25, 22, TEXT, 900, valign="m")
        draw_top_stats(g, self.app)
        g.rect(0, 48, 640, 2, BORDER)
        sy = self.sel_y.get()
        g.rrect(16, sy - 3, 608, 40, 12, GREEN[0])
        for i, (label, value, key) in enumerate(self.items):
            v = self.pops[i].get()
            y = self.row_y(i)
            x = 20 + (1 - v) * 40
            g.rrect(x, y, 600, 32, 10, CARD_HI if i == self.sel else CARD, max(0.0, min(1.0, v)))
            col = RED[0] if key in ("reset", "exit") else TEXT
            g.text(label, x + 16, y + 16, 16, col, 900, valign="m")
            if value:
                vc = GREEN[0] if value == "On" else (SUB if value == "Off" else BLUE[0])
                if key in ("goal", "board", "date"):
                    vw = g.text_size(value, 15, 900)[0]
                    g.text("▶", x + 588, y + 16, 11, SUB, "sym", align="r", valign="m")
                    g.text(value, x + 570, y + 16, 15, vc, 900, align="r", valign="m")
                    g.text("◀", x + 562 - vw, y + 16, 11, SUB, "sym", align="r", valign="m")
                else:
                    g.text(value, x + 584, y + 16, 15, vc, 900, align="r", valign="m")
        if self.msg and motion.now() - self.msg[1] < 4:
            g.text(self.msg[0], 320, 448, 14, BLUE[0], 800, align="c")
        else:
            hint(g, 20, 448, [("A", "Change"), ("←→", "Adjust"), ("B", "Back")])
            g.text("ChessOS 0.1 beta", 620, 458, 12, SUB, 800, align="r", valign="m")
