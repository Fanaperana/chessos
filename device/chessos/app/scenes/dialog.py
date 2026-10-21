"""Modal dialog that springs in over the current scene."""
from .. import motion
from ..core import Scene
from ..ui import CARD, BORDER, TEXT, SUB, GREEN, RED, BLUE, button


class Dialog(Scene):
    opaque = False

    def __init__(self, app, title, message, options, on_choose, danger=None):
        """options: list of labels; on_choose(index or None for cancel)."""
        Scene.__init__(self, app)
        self.title, self.message, self.options = title, message, options
        self.on_choose = on_choose
        self.danger = danger if danger is not None else -1
        self.sel = 0
        self.s = motion.Value(0)
        self.bg = motion.Value(0)

    def enter(self):
        self.s.set(0.85).spring(1, "bouncy")
        self.bg.tween(0.7, 0.2)
        self.app.audio.sfx("select")

    def close(self, idx):
        self.app.pop()
        self.on_choose(idx)

    def update(self, dt, actions):
        for a in actions:
            if a in ("up", "left"):
                self.sel = (self.sel - 1) % len(self.options)
                self.app.audio.sfx("nav")
            elif a in ("down", "right"):
                self.sel = (self.sel + 1) % len(self.options)
                self.app.audio.sfx("nav")
            elif a == "a":
                self.close(self.sel)
                return
            elif a in ("b", "start"):
                self.close(None)
                return

    def draw(self, g, dt):
        g.rect(0, 0, 640, 480, (0, 0, 0), self.bg.get())
        s = self.s.get()
        w, h = 380 * s, (150 + 56 * len(self.options)) * s
        x, y = 320 - w / 2, 240 - h / 2
        g.rrect(x - 2, y - 2, w + 4, h + 4, 22, BORDER)
        g.rrect(x, y, w, h, 20, CARD)
        if s < 0.95:
            return
        g.text(self.title, 320, y + 26, 22, TEXT, 900, align="c")
        g.text_block(self.message, x + 30, y + 64, w - 60, 15, SUB, 700, align="c")
        for i, label in enumerate(self.options):
            cols = RED if i == self.danger else (GREEN if i == 0 else BLUE)
            button(g, x + 30, y + 130 + i * 56, w - 60, 44, label, cols, focused=(i == self.sel), size=16)
