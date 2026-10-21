"""Animated chess board widget driven by the D-pad."""
import math

from . import motion
from .chess import sq_name, FILES
from .ui import WHITE, GOLD, RED

THEMES = {
    "green": ((235, 236, 208), (119, 149, 86)),
    "brown": ((240, 217, 181), (181, 136, 99)),
    "blue": ((222, 227, 230), (140, 162, 173)),
}
HIGHLIGHT = (255, 255, 51)


def piece_sprite(p):
    return "piece_" + ("w" if p.isupper() else "b") + p.upper()


class Sprite(object):
    __slots__ = ("piece", "x", "y", "scale", "alpha", "z")

    def __init__(self, piece, x, y):
        self.piece = piece
        self.x = motion.Value(x)
        self.y = motion.Value(y)
        self.scale = motion.Value(1)
        self.alpha = motion.Value(1)
        self.z = 0


class Board(object):
    def __init__(self, app, x, y, sq):
        self.app = app
        self.x, self.y, self.sq = x, y, sq
        self.flip = False
        self.pos = None
        self.sprites = {}
        self.dying = []
        self.cc, self.cr = 4, 6
        self.cur_x = motion.Value(0)
        self.cur_y = motion.Value(0)
        self.selected = None
        self.targets = []
        self.last = None
        self.stars = {}       # square -> {"scale": Value, "collected": bool, "t": time}
        self.hint_sq = None
        self.hint_to = None
        self.shake_t = -10.0
        self.show_cursor = True
        self.interactive = True
        self._place_cursor(True)

    # ---- geometry -------------------------------------------------------------------
    def sq_to_cr(self, s):
        f, r = s % 8, s // 8
        if self.flip:
            return 7 - f, r
        return f, 7 - r

    def cr_to_sq(self, c, r):
        if self.flip:
            return (7 - c) + r * 8
        return c + (7 - r) * 8

    def sq_xy(self, s):
        c, r = self.sq_to_cr(s)
        return self.x + c * self.sq, self.y + r * self.sq

    def cursor_sq(self):
        return self.cr_to_sq(self.cc, self.cr)

    def _place_cursor(self, instant=False):
        tx, ty = self.x + self.cc * self.sq, self.y + self.cr * self.sq
        if instant:
            self.cur_x.set(tx)
            self.cur_y.set(ty)
        else:
            self.cur_x.spring(tx, "stiff")
            self.cur_y.spring(ty, "stiff")

    def set_cursor(self, s, instant=False):
        self.cc, self.cr = self.sq_to_cr(s)
        self._place_cursor(instant)

    # ---- position --------------------------------------------------------------------
    def set_position(self, pos, pop=True, delay=0.0):
        self.pos = pos
        self.sprites = {}
        self.dying = []
        self.selected = None
        self.targets = []
        self.last = None
        self.hint_sq = self.hint_to = None
        for s, p in enumerate(pos.board):
            if p == ".":
                continue
            x, y = self.sq_xy(s)
            sp = Sprite(p, x, y)
            if pop:
                c, r = self.sq_to_cr(s)
                d = math.hypot(c - 3.5, r - 3.5)
                sp.scale.set(0).spring(1, "bouncy", delay=delay + motion.stagger(d, 0.035))
            self.sprites[s] = sp

    def set_stars(self, squares, delay=0.0):
        self.stars = {}
        for i, s in enumerate(squares):
            v = motion.Value(0).spring(1, "bouncy", delay=delay + 0.3 + i * 0.08)
            self.stars[s] = {"scale": v, "collected": False, "t": 0}

    def collect_star(self, s):
        st = self.stars.get(s)
        if st and not st["collected"]:
            st["collected"] = True
            st["t"] = motion.now()
            st["scale"].tween(2.2, 0.35, "easeOut")
            return True
        return False

    def stars_left(self):
        return sum(1 for s in self.stars.values() if not s["collected"])

    def apply_move(self, before, m, after, sound=True, duration=0.2):
        """Animate move m from `before` to `after`."""
        cap_sq = m.to
        moving = before.board[m.frm]
        if moving.upper() == "P" and m.to == before.ep and before.board[m.to] == ".":
            cap_sq = m.to - 8 if moving == "P" else m.to + 8
        captured = self.sprites.pop(cap_sq, None)
        if captured:
            captured.alpha.tween(0, 0.25, "easeOut", delay=duration * 0.6)
            captured.scale.tween(0.4, 0.3, "easeIn", delay=duration * 0.6)
            captured.z = -1
            self.dying.append((captured, motion.now() + 0.6))
        sp = self.sprites.pop(m.frm, None)
        if sp is None:
            x, y = self.sq_xy(m.frm)
            sp = Sprite(moving, x, y)
        tx, ty = self.sq_xy(m.to)
        sp.x.tween(tx, duration, "easeOut")
        sp.y.tween(ty, duration, "easeOut")
        sp.z = 2
        sp.piece = after.board[m.to] if after.board[m.to] != "." else sp.piece
        if m.promo:
            sp.scale.set(1)
            sp.scale.spring(1, "bouncy", velocity=8)
        self.sprites[m.to] = sp
        if moving.upper() == "K" and abs(m.to - m.frm) == 2:
            rf, rt = {6: (7, 5), 2: (0, 3), 62: (63, 61), 58: (56, 59)}[m.to]
            rs = self.sprites.pop(rf, None)
            if rs:
                x, y = self.sq_xy(rt)
                rs.x.tween(x, duration * 1.2, "easeOut", delay=0.05)
                rs.y.tween(y, duration * 1.2, "easeOut", delay=0.05)
                self.sprites[rt] = rs
        self.pos = after
        self.last = (m.frm, m.to)
        self.selected = None
        self.targets = []
        if sound:
            self.app.audio.sfx("capture" if captured else "move")

    def shake(self):
        self.shake_t = motion.now()

    # ---- input --------------------------------------------------------------------------
    def move_cursor(self, act):
        dc, dr = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[act]
        self.cc = max(0, min(7, self.cc + dc))
        self.cr = max(0, min(7, self.cr + dr))
        self._place_cursor()

    def handle(self, act, side):
        """D-pad + A/B selection. Returns a Move when the player commits one."""
        if not self.interactive or self.pos is None:
            return None
        if act in ("up", "down", "left", "right"):
            self.move_cursor(act)
            return None
        s = self.cursor_sq()
        if act == "a":
            if self.selected is not None:
                for m in self.targets:
                    if m.to == s:
                        return m
                if s == self.selected:
                    self.selected, self.targets = None, []
                    return None
            p = self.pos.board[s]
            if p != "." and (p.isupper() == (side == "w")):
                mv = self.pos.moves_from(s)
                if mv:
                    self.selected = s
                    self.targets = mv
                    self.app.audio.sfx("select")
                    sp = self.sprites.get(s)
                    if sp:
                        sp.scale.set(1).spring(1, "bouncy", velocity=5)
                else:
                    self.shake()
                    self.app.audio.sfx("nav")
        elif act == "b":
            self.selected, self.targets = None, []
        return None

    # ---- drawing ---------------------------------------------------------------------------
    def draw(self, g, theme="green"):
        light, dark = THEMES.get(theme, THEMES["green"])
        sq = self.sq
        ox = motion.shake(self.shake_t, 8, 0.35)
        bx, by = self.x + ox, self.y
        g.rrect(bx - 4, by - 4, sq * 8 + 8, sq * 8 + 8, 10, (14, 22, 26))

        def squares(gg, x0=0, y0=0):
            for r in range(8):
                for c in range(8):
                    col = light if (r + c) % 2 == 0 else dark
                    gg.rect(x0 + c * sq, y0 + r * sq, sq, sq, col)
            for i in range(8):
                f = FILES[7 - i] if self.flip else FILES[i]
                rank = str(i + 1) if self.flip else str(8 - i)
                col_f = dark if (7 + i) % 2 == 0 else light
                col_r = dark if i % 2 == 0 else light
                gg.text(f, x0 + i * sq + sq - 3, y0 + 8 * sq - 2, 11, col_f, 900, align="r", valign="b")
                gg.text(rank, x0 + 3, y0 + i * sq + 1, 11, col_r, 900)

        layer = g.layer(("board", theme, sq, self.flip), sq * 8, sq * 8, squares)
        if layer is not None:
            g.blit(layer, bx, by)
        else:
            squares(g, bx, by)
        # last move & selection
        if self.last:
            for s in self.last:
                x, y = self.sq_xy(s)
                g.rect(x + ox, y, sq, sq, HIGHLIGHT, 0.38)
        if self.selected is not None:
            x, y = self.sq_xy(self.selected)
            g.rect(x + ox, y, sq, sq, HIGHLIGHT, 0.55)
        if self.hint_sq is not None:
            x, y = self.sq_xy(self.hint_sq)
            g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * (0.45 + 0.05 * motion.pulse(3)), (28, 176, 246), 0.55)
        if self.hint_to is not None:
            x, y = self.sq_xy(self.hint_to)
            g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * 0.3, (28, 176, 246), 0.45)
        # check glow
        if self.pos is not None and self.pos.in_check():
            k = self.pos.king_sq(self.pos.turn)
            if k is not None:
                x, y = self.sq_xy(k)
                g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * 0.62, RED[0], 0.35 + 0.2 * motion.pulse(2.5))
                g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * 0.45, RED[1], 0.55)
        # stars
        for s, st in self.stars.items():
            x, y = self.sq_xy(s)
            sc = st["scale"].get()
            if st["collected"]:
                a = max(0.0, 1 - (motion.now() - st["t"]) / 0.35)
                if a <= 0:
                    continue
            else:
                a = 1.0
                sc *= 1 + 0.06 * motion.pulse(2.2, phase=s)
            bob = 0 if st["collected"] else 2 * math.sin(motion.now() * 3 + s)
            g.draw_sprite("star", x + ox + sq / 2.0, y + sq / 2.0 + bob, sq * 0.62 * sc, a=a, color=GOLD[0])
        # pieces (dying, normal, moving on top)
        now = motion.now()
        self.dying = [(sp, t) for sp, t in self.dying if t > now]
        items = [sp for sp, _ in self.dying] + sorted(self.sprites.values(), key=lambda sp: sp.z)
        for sp in items:
            sc = sp.scale.get()
            a = sp.alpha.get()
            if sc <= 0.01 or a <= 0.01:
                continue
            g.draw_sprite(piece_sprite(sp.piece), sp.x.get() + ox + sq / 2.0, sp.y.get() + sq / 2.0,
                          sq * 1.08 * sc, a=a)
            if not sp.x.animating:
                sp.z = 0
        # legal move dots
        for m in self.targets:
            x, y = self.sq_xy(m.to)
            if self.pos.board[m.to] != ".":
                g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * 0.48, (0, 0, 0), 0.18)
            else:
                g.circle(x + ox + sq / 2.0, y + sq / 2.0, sq * 0.16, (0, 0, 0), 0.22)
        # cursor
        if self.show_cursor and self.interactive:
            cx, cy = self.cur_x.get() + ox, self.cur_y.get()
            t = 3
            col = WHITE
            p = 0.75 + 0.25 * motion.pulse(2.4)
            g.rect(cx, cy, sq, t, col, p)
            g.rect(cx, cy + sq - t, sq, t, col, p)
            g.rect(cx, cy + t, t, sq - 2 * t, col, p)
            g.rect(cx + sq - t, cy + t, t, sq - 2 * t, col, p)
            g.rect(cx - 1, cy - 1, sq + 2, 1, (0, 0, 0), 0.4 * p)
            g.rect(cx - 1, cy + sq, sq + 2, 1, (0, 0, 0), 0.4 * p)



def draw_mini(g, pos, x, y, sq, theme="green", flip=False):
    """Small static preview of a position (for cards)."""
    light, dark = THEMES.get(theme, THEMES["green"])
    for r in range(8):
        for c in range(8):
            g.rect(x + c * sq, y + r * sq, sq, sq, light if (r + c) % 2 == 0 else dark)
    for s, p in enumerate(pos.board):
        if p != ".":
            c, r = s % 8, 7 - s // 8
            if flip:
                c, r = 7 - c, 7 - r
            g.draw_sprite(piece_sprite(p), x + c * sq + sq / 2.0, y + r * sq + sq / 2.0, sq * 1.05)
