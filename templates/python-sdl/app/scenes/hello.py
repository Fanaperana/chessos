"""@TITLE@ starter screen: shows input, animation, sound and the Power menu.
Replace this with your own scenes (see app/core.py for the Scene API)."""
from .. import motion
from ..core import Scene
from ..ui import BG, CARD, CARD_HI, BORDER, TEXT, SUB, GREEN, BLUE, RED, button, hint

ITEMS = ["Say hello", "Show the controls", "Power"]


class Hello(Scene):
    def enter(self):
        self.sel = 0
        self.last = "-"
        self.title_s = motion.Value(0).spring(1, "bouncy", delay=0.1)
        self.rows = [motion.Value(0).spring(1, "snappy", delay=0.3 + i * 0.07) for i in range(len(ITEMS))]
        self.wave = -10.0

    def update(self, dt, actions):
        for a in actions:
            self.last = a.upper()
            if a in ("up", "down"):
                self.sel = (self.sel + (1 if a == "down" else -1)) % len(ITEMS)
                self.app.audio.sfx("nav")
            elif a == "a":
                self.activate()
            elif a == "start":
                self.sel = 2
                self.activate()

    def activate(self):
        self.app.audio.sfx("select")
        if self.sel == 0:
            self.wave = motion.now()
            self.app.audio.sfx("correct")
        elif self.sel == 2:
            from .dialog import Dialog
            if self.app.frontend:   # booted as the device's main app
                codes = {1: 10, 2: 11, 3: 0}

                def power(i):
                    if i in codes:
                        self.app.exit_code = codes[i]
                        self.app.quit()
                self.app.push(Dialog(self.app, "Power", "What would you like to do?",
                                     ["CANCEL", "POWER OFF", "RESTART", "ARKOS MENUS"], power, danger=1))
            else:                   # run as a port or on the PC
                self.app.push(Dialog(self.app, "Exit?", "Close @TITLE@?", ["STAY", "EXIT"],
                                     lambda i: i == 1 and self.app.quit(), danger=1))

    def draw(self, g, dt):
        s = self.title_s.get()
        bounce = motion.shake(self.wave, 14, 0.6, 18)
        g.text("@TITLE@", 320 + bounce, 90, 52, GREEN[0], 900, align="c", valign="m", scale=max(0.01, s))
        g.text("Hello from your own handheld app!", 320, 140, 17, SUB, 800, align="c")
        for i, label in enumerate(ITEMS):
            v = self.rows[i].get()
            y = 190 + i * 62
            button(g, 170 + (1 - v) * 60, y, 300, 48, label, GREEN if i == self.sel else BLUE,
                   focused=(i == self.sel), a=max(0.0, min(1.0, v)))
        if self.sel == 1:
            g.rrect(40, 380, 560, 40, 12, CARD)
            g.text("Last button: " + self.last, 320, 400, 16, TEXT, 800, align="c", valign="m")
        hint(g, 320, 448, [("↑↓", "Choose"), ("A", "Select"), ("START", "Power")], align="c")
