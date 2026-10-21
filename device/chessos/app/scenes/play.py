"""Play vs Coach: a game against Stockfish with Fritz-style live commentary."""
import random
import time

from .. import motion
from ..board import Board, piece_sprite
from ..chess import Position, START_FEN, uci, spoken
from ..coach import Coach, win_prob, static_lines
from ..core import Scene
from ..engine import Engine
from ..ui import (BG, CARD, CARD_HI, BORDER, TEXT, SUB, WHITE, GOLD, GREEN, RED, BLUE, ORANGE, PURPLE,
                  bubble, button, hint, Confetti)

BOARD_X, BOARD_Y, SQ = 14, 54, 52
PANEL_X, PANEL_W = 448, 182
PROMO = "QRBN"

LEVELS = [
    # name, description, engine settings for the coach's own moves
    ("Beginner", "Just learned the moves", {"skill": 0, "depth": 1}),
    ("Casual", "Plays for fun, makes mistakes", {"skill": 3, "depth": 3}),
    ("Club", "A solid club player", {"skill": 8, "movetime": 300}),
    ("Strong", "A tough opponent", {"skill": 14, "movetime": 600}),
    ("Master", "Full strength. Good luck!", {"skill": None, "movetime": 900}),
]
SIDES = ["White", "Black", "Random"]
GRADE_COLORS = {"best": GREEN[0], "good": BLUE[0], "inaccuracy": GOLD[0], "mistake": ORANGE[0], "blunder": RED[0]}


class PlaySetup(Scene):
    def enter(self):
        p = self.app.progress
        self.level = p.data.get("play_level", 1)
        self.side = p.data.get("play_side", 0)
        self.row = 0
        self.pop = [motion.Value(0).spring(1, "bouncy", delay=i * 0.06) for i in range(3)]
        self.app.audio.speak("Let's play!")

    def update(self, dt, actions):
        for a in actions:
            if a in ("up", "down"):
                self.row = (self.row + (1 if a == "down" else -1)) % 3
                self.app.audio.sfx("nav")
            elif a in ("left", "right"):
                d = 1 if a == "right" else -1
                if self.row == 0:
                    self.level = max(0, min(len(LEVELS) - 1, self.level + d))
                elif self.row == 1:
                    self.side = (self.side + d) % len(SIDES)
                self.app.audio.sfx("nav")
            elif a == "a":
                if True:  # A starts the game from any row
                    p = self.app.progress
                    p.data["play_level"], p.data["play_side"] = self.level, self.side
                    p.save()
                    side = SIDES[self.side]
                    color = "w" if side == "White" else "b" if side == "Black" else random.choice("wb")
                    self.app.audio.sfx("select")
                    self.app.replace(Play(self.app, self.level, color))
                    return
            elif a in ("b", "start"):
                self.app.pop(fade=True)
                return

    def draw(self, g, dt):
        g.text("Play vs Coach", 20, 25, 22, TEXT, 900, valign="m")
        g.rect(0, 48, 640, 2, BORDER)
        g.draw_sprite("mascot", 92, 160 + 4 * motion.pulse(1.4), 120)
        bubble(g, 170, 92, 440, 70, tail_x=35)
        g.text_block("Play a full game against me. I'll comment on every move and help you get better!",
                     188, 104, 410, 16, TEXT, 800)
        rows = [("Strength", LEVELS[self.level][0], LEVELS[self.level][1]),
                ("You play", SIDES[self.side], "White moves first" if SIDES[self.side] == "White" else
                 ("The coach moves first" if SIDES[self.side] == "Black" else "Let fate decide"))]
        for i, (label, value, sub) in enumerate(rows):
            v = self.pop[i].get()
            y = 200 + i * 86
            x = 60 + (1 - v) * 40
            sel = self.row == i
            g.rrect(x - 3, y - 3, 526, 76, 18, GREEN[0] if sel else BORDER)
            g.rrect(x, y, 520, 70, 16, CARD)
            g.text(label.upper(), x + 20, y + 12, 12, SUB, 900)
            g.text(value, x + 20, y + 30, 24, TEXT, 900)
            g.text(sub, x + 500, y + 40, 13, SUB, 800, align="r", valign="m")
            if i == 0:
                for k in range(len(LEVELS)):
                    g.circle(x + 380 + k * 22, y + 22, 7, GREEN[0] if k <= self.level else BORDER)
            g.text("◀", x + 210, y + 46, 14, SUB if sel else BORDER, "sym", valign="m")
            g.text("▶", x + 236, y + 46, 14, SUB if sel else BORDER, "sym", valign="m")
        button(g, 220, 384, 200, 48, "START GAME", GREEN, focused=True)
        hint(g, 320, 448, [("↑↓", "Choose"), ("←→", "Change"), ("A", "Start"), ("B", "Back")], align="c")


class Play(Scene):
    def __init__(self, app, level, color):
        Scene.__init__(self, app)
        self.level = level
        self.player = color
        self.coach = Coach(color)
        self.board = Board(app, BOARD_X, BOARD_Y, SQ)
        self.board.flip = color == "b"
        self.pos = Position.from_fen(START_FEN)
        self.history = []          # list of (pos_before, move, san)
        self.seen = {}
        self.state = "init"
        self.comment = ""
        self.comment_t = 0.0
        self.grade = None
        self.grade_t = -10.0
        self.eval_white = motion.Value(0)
        self.ana = None
        self.job = None
        self.wait_until = 0.0
        self.result = None
        self.promo_moves = None
        self.promo_sel = 0
        self.confetti = Confetti()
        self.res_s = motion.Value(0)
        dev = app.device
        self.ana_time = 700 if dev else 300
        self.grade_time = 700 if dev else 300

    # ---- lifecycle -------------------------------------------------------------------
    def enter(self):
        self.engine = Engine.find(self.app.base, threads=2 if self.app.device else 4, hash_mb=32)
        self.app.audio.start_piper()
        self.board.set_position(self.pos)
        if self.engine is None:
            self.state = "noengine"
            self.say("I can't find my chess engine. Please reinstall ChessOS.", speak=False)
            return
        self.engine.new_game()
        self.say(self.coach.start())
        if self.player == "w":
            self.begin_player()
        else:
            self.start_reply(time.time() + 1.2)

    def close(self):
        if getattr(self, "engine", None):
            self.engine.quit()
            self.engine = None
        self.app.audio.stop_piper()

    def leave_home(self):
        self.close()
        self.app.pop(fade=True)

    # ---- helpers ---------------------------------------------------------------------
    def say(self, text, speak=True, interrupt=False, append=False):
        if not text:
            return
        if append and self.comment and motion.now() - self.comment_t < 4:
            self.comment = self.comment + " " + text   # keep the explanation of your move visible
        else:
            self.comment = text
            self.comment_t = motion.now()
        if speak:
            self.app.audio.speak(text, interrupt=interrupt)

    def key(self, pos):
        return " ".join(pos.fen().split()[:4])

    def sans(self):
        return [h[2] for h in self.history]

    def game_over(self):
        p = self.pos
        if p.is_checkmate():
            return "win" if p.turn != self.player else "loss"
        if p.is_stalemate():
            return "draw"
        if p.halfmove >= 100 or self.seen.get(self.key(p), 0) >= 3:
            return "draw"
        pieces = [c for c in p.board if c not in ".kK"]
        if not pieces or (len(pieces) == 1 and pieces[0].upper() in "NB"):
            return "draw"
        return None

    def push(self, m, sound=True):
        before = self.pos
        san = before.san(m)
        after = before.push(m)
        self.board.apply_move(before, m, after, sound=sound, duration=0.22)
        self.history.append((before, m, san))
        self.pos = after
        k = self.key(after)
        self.seen[k] = self.seen.get(k, 0) + 1
        return before, after, san

    def set_eval(self, cp_white):
        self.eval_white.spring(max(-1.0, min(1.0, (win_prob(cp_white) - 0.5) * 2)), "gentle")

    # ---- flow ------------------------------------------------------------------------
    def begin_player(self):
        self.state = "player"
        self.board.interactive = True
        self.board.hint_sq = self.board.hint_to = None
        self.ana = self.engine.search(self.pos.fen(), movetime=self.ana_time + 500, kind="ana")
        if self.history:
            self.board.set_cursor(self.history[-1][1].to)
        else:
            self.board.set_cursor(12 if self.player == "w" else 52)

    def start_reply(self, not_before):
        """Coach's move: weakened search (or reuse the grading search at full strength)."""
        self.state = "reply"
        self.board.interactive = False
        cfg = LEVELS[self.level][2]
        self.job = self.engine.search(self.pos.fen(), movetime=cfg.get("movetime", 300), depth=cfg.get("depth"),
                                      skill=cfg.get("skill"), kind="reply")
        self.wait_until = not_before

    def player_moved(self, m):
        ana = self.ana
        self.engine.stop()
        e_before = ana.score() if ana is not None and ana.depth >= 1 else None
        best = ana.bestmove or (ana.pv[0] if ana and ana.pv else None) if ana else None
        before, after, san = self.push(m)
        self.pending = (before, m, after, e_before, best)
        self.board.interactive = False
        self.board.hint_sq = self.board.hint_to = None
        over = self.game_over()
        if over:
            self.finish(over)
            return
        self.state = "grading"
        self.job = self.engine.search(after.fen(), movetime=self.grade_time, kind="grade")
        self.wait_until = time.time() + 0.15

    def on_graded(self, s):
        before, m, after, e_before, best = self.pending
        e_after = -s.score()
        if e_before is None:
            e_before = e_after
        text, grade = self.coach.player_move(before, m, after, e_before, e_after, best, self.sans(), s.bestmove)
        self.grade, self.grade_t = grade, motion.now()
        self.set_eval(e_after if self.player == "w" else -e_after)
        if text:
            self.say(text, interrupt=True)
        cfg = LEVELS[self.level][2]
        if cfg.get("skill") is None and s.bestmove:
            self.reply_move = s.bestmove
            self.state = "reply_ready"
            self.wait_until = time.time() + 0.35
        else:
            self.start_reply(time.time() + 0.35)

    def play_reply(self, best):
        try:
            m = self.pos.parse_uci(best)
        except (ValueError, TypeError):
            m = random.choice(self.pos.legal_moves())
        before, after, san = self.push(m)
        self.app.audio.speak_words(spoken(before, m), interrupt=False)
        text = self.coach.engine_move(before, m, after)
        over = self.game_over()
        if text and not over:
            self.say(text, append=True)
        if over:
            self.finish(over)
            return
        self.begin_player()

    def finish(self, result):
        self.state = "over"
        self.result = result
        self.board.interactive = False
        if self.engine:
            self.engine.stop()
        lines = {"win": "you_won", "loss": "you_lost", "draw": "draw"}
        self.say(self.coach.pick(lines[result]), interrupt=False)
        self.app.audio.sfx("complete" if result == "win" else "correct" if result == "draw" else "wrong")
        if result == "win":
            self.confetti.rain(90)
        plies = len([h for h in self.history if h[0].turn == self.player])
        self.xp = 0
        if plies >= 5:
            self.xp = {"win": 25, "draw": 15, "loss": 10}[result]
            self.app.progress.data["games_played"] = self.app.progress.data.get("games_played", 0) + 1
            if result == "win":
                self.app.progress.data["games_won"] = self.app.progress.data.get("games_won", 0) + 1
            self.app.progress.add_xp(self.xp)
        self.res_s.set(0).spring(1, "bouncy", delay=0.8)

    def takeback(self):
        # undo the player's last move and the coach's reply
        n = 0
        while self.history and n < 2:
            before, m, san = self.history.pop()
            k = self.key(self.pos)
            self.seen[k] = max(0, self.seen.get(k, 1) - 1)
            self.pos = before
            n += 1
            if before.turn == self.player:
                break
        if n:
            self.board.set_position(self.pos, pop=False)
            if self.history:
                self.board.last = (self.history[-1][1].frm, self.history[-1][1].to)
            self.say(self.coach.pick("takeback"))
            self.begin_player()

    # ---- update ----------------------------------------------------------------------
    def update(self, dt, actions):
        st = self.state
        now = time.time()
        if st == "grading" and self.job.done and now >= self.wait_until:
            self.on_graded(self.job)
        elif st == "reply" and self.job.done and now >= self.wait_until:
            self.play_reply(self.job.bestmove)
        elif st == "reply_ready" and now >= self.wait_until:
            self.play_reply(self.reply_move)
        elif st == "player" and self.ana is not None and self.ana.depth >= 1:
            sc = self.ana.score()
            self.set_eval(sc if self.player == "w" else -sc)
        for a in actions:
            if self.state == "over":
                if a == "a" and self.res_s.get() > 0.9:
                    self.close()
                    self.app.replace(PlaySetup(self.app))
                    return
                if a in ("b", "start"):
                    self.leave_home()
                    return
                continue
            if self.state == "noengine":
                if a in ("a", "b", "start"):
                    self.leave_home()
                return
            if a == "start":
                self.menu()
                return
            if a == "x":
                if self.comment:
                    self.app.audio.speak(self.comment)
                continue
            if self.state == "promo":
                self.promo_input(a)
                continue
            if self.state != "player":
                continue
            if a == "y":
                self.show_hint()
            elif a == "l1":
                self.takeback()
            else:
                m = self.board.handle(a, self.player)
                if m is not None:
                    if m.promo:
                        self.promo_moves = [mm for mm in self.board.targets if mm.to == m.to]
                        self.promo_sel = 0
                        self.state = "promo"
                    else:
                        self.player_moved(m)

    def promo_input(self, a):
        if a in ("left", "up"):
            self.promo_sel = (self.promo_sel - 1) % 4
        elif a in ("right", "down"):
            self.promo_sel = (self.promo_sel + 1) % 4
        elif a == "a":
            m = [mm for mm in self.promo_moves if mm.promo == PROMO[self.promo_sel]][0]
            self.state = "player"
            self.player_moved(m)
        elif a == "b":
            self.state = "player"
            self.board.selected, self.board.targets = None, []

    def show_hint(self):
        ana = self.ana
        best = ana.bestmove or (ana.pv[0] if ana.pv else None) if ana else None
        if not best:
            self.say(self.coach.pick("thinking"))
            return
        text, m = self.coach.hint(self.pos, best)
        if m is not None:
            self.board.hint_sq, self.board.hint_to = m.frm, m.to
            self.say(text, interrupt=True)

    def menu(self):
        from .dialog import Dialog

        def chosen(i):
            if i == 1 and self.state != "over":
                self.finish("loss")
            elif i == 2:
                self.leave_home()
        self.app.push(Dialog(self.app, "Game menu", "Resigning counts as a loss.",
                             ["KEEP PLAYING", "RESIGN", "QUIT TO HOME"], chosen, danger=1))

    # ---- drawing ---------------------------------------------------------------------
    def draw(self, g, dt):
        lv = LEVELS[self.level][0]
        g.text("Play vs Coach", 20, 25, 20, TEXT, 900, valign="m")
        g.text(lv, 20 + g.text_size("Play vs Coach", 20, 900)[0] + 12, 26, 14, GREEN[0], 900, valign="m")
        g.text("You: " + ("White" if self.player == "w" else "Black"), 626, 26, 14, SUB, 800, align="r", valign="m")
        self.board.draw(g, self.app.progress.setting("board"))
        self.draw_eval(g)
        self.draw_panel(g)
        if self.state == "promo":
            self.draw_promo(g)
        self.confetti.draw(g, dt)
        if self.state == "over":
            self.draw_result(g)

    def draw_eval(g_self, g):
        x, y, h = BOARD_X + SQ * 8 + 6, BOARD_Y, SQ * 8
        v = g_self.eval_white.get()  # -1..1, white's share
        g.rrect(x, y, 10, h, 5, (40, 40, 44))
        white_h = h * (0.5 + v / 2.0)
        if g_self.board.flip:
            g.rrect(x, y, 10, max(4, white_h), 5, (235, 235, 235))
        else:
            g.rrect(x, y + h - white_h, 10, max(4, white_h), 5, (235, 235, 235))

    def draw_panel(self, g):
        x, w = PANEL_X, PANEL_W
        # coach header
        g.draw_sprite("mascot", x + 22, 76 + 2 * motion.pulse(1.6), 46)
        g.text("Coach", x + 50, 60, 17, TEXT, 900)
        live = "voice ready" if self.app.audio.live_ready() else "no live voice"
        g.text(live, x + 50, 82, 11, SUB, 800)
        # speech bubble
        text = self.comment or "..."
        lines = g.wrap(text, w - 22, 15, 800)[:6]
        bh = max(46, len(lines) * 20 + 20)
        bubble(g, x, 108, w, bh, tail_x=24, tail_side="left")
        a = min(1.0, (motion.now() - self.comment_t) * 4)
        for i, ln in enumerate(lines):
            g.text(ln, x + 11, 118 + i * 20, 15, TEXT, 800, a=a)
        y = 108 + bh + 10
        # grade badge
        if self.grade and motion.now() - self.grade_t < 6:
            col = GRADE_COLORS.get(self.grade, SUB)
            label = self.grade.upper()
            tw = g.text_size(label, 12, 900)[0] + 18
            g.rrect(x, y, tw, 22, 11, col)
            g.text(label, x + tw / 2.0, y + 11, 12, WHITE, 900, align="c", valign="m")
        y += 32
        # move list (last 5 moves)
        g.rrect(x, y, w, 120, 12, CARD)
        sans = self.sans()
        start_white = self.history[0][0].turn == "w" if self.history else True
        rows = []
        i = 0
        num = 1
        if not start_white and sans:
            rows.append("%d. ...  %s" % (num, sans[0]))
            i, num = 1, 2
        while i < len(sans):
            rows.append("%d. %-6s %s" % (num, sans[i], sans[i + 1] if i + 1 < len(sans) else ""))
            i += 2
            num += 1
        for k, r in enumerate(rows[-5:]):
            g.text(r, x + 12, y + 10 + k * 21, 14, TEXT if k == len(rows[-5:]) - 1 else SUB, 800)
        if not rows:
            g.text("No moves yet", x + 12, y + 10, 14, SUB, 800)
        y += 130
        # status
        st = {"player": "Your move", "grading": "Coach is looking...", "reply": "Coach is thinking...",
              "reply_ready": "Coach is thinking...", "promo": "Choose a piece", "over": "Game over",
              "init": "", "noengine": "No chess engine"}.get(self.state, "")
        dots = "." * (1 + int(motion.now() * 3) % 3) if "thinking" in st or "looking" in st else ""
        g.text(st.rstrip(".") + dots, x + 2, y, 15, GREEN[0] if self.state == "player" else SUB, 900)
        hint(g, x, 410, [("Y", "Hint"), ("X", "Repeat")])
        hint(g, x, 436, [("L1", "Undo"), ("START", "Menu")])

    def draw_promo(self, g):
        g.rect(BOARD_X, BOARD_Y, SQ * 8, SQ * 8, (0, 0, 0), 0.55)
        w = 4 * 74 + 20
        x = BOARD_X + SQ * 4 - w / 2.0
        y = BOARD_Y + SQ * 4 - 60
        g.rrect(x, y, w, 120, 18, CARD)
        g.text("Promote to", BOARD_X + SQ * 4, y + 10, 16, TEXT, 900, align="c")
        for i, pc in enumerate(PROMO):
            cx = x + 47 + i * 74
            if i == self.promo_sel:
                g.rrect(cx - 33, y + 36, 66, 72, 14, GREEN[0])
            g.rrect(cx - 30, y + 39, 60, 66, 12, CARD_HI)
            g.draw_sprite(piece_sprite(pc if self.player == "w" else pc.lower()), cx, y + 72, 56)

    def draw_result(self, g):
        s = self.res_s.get()
        if s <= 0.02:
            return
        g.rect(0, 0, 640, 480, (0, 0, 0), 0.55 * min(1, s))
        w, h = 440 * s, 300 * s
        x, y = 320 - w / 2, 240 - h / 2
        g.rrect(x - 2, y - 2, w + 4, h + 4, 22, BORDER)
        g.rrect(x, y, w, h, 20, CARD)
        if s < 0.9:
            return
        title, col = {"win": ("You won!", GOLD[0]), "loss": ("The coach won", RED[0]),
                      "draw": ("Draw", BLUE[0])}[self.result]
        g.text(title, 320, y + 22, 30, col, 900, align="c")
        acc = self.coach.accuracy()
        g.text("Accuracy %d%%" % round(acc), 320, y + 66, 20, TEXT, 900, align="c")
        st = self.coach.stats
        items = [("Best", st["best"], GREEN[0]), ("Good", st["good"], BLUE[0]), ("Inaccuracies", st["inaccuracy"], GOLD[0]),
                 ("Mistakes", st["mistake"], ORANGE[0]), ("Blunders", st["blunder"], RED[0])]
        for i, (label, n, c) in enumerate(items):
            cx = x + 44 + i * 88
            g.text(str(n), cx, y + 112, 26, c, 900, align="c")
            g.text(label, cx, y + 146, 11, SUB, 800, align="c")
        if self.xp:
            g.text("+%d XP" % self.xp, 320, y + 176, 18, GOLD[0], 900, align="c")
        button(g, x + 30, y + h - 70, w / 2 - 40, 46, "PLAY AGAIN", GREEN, size=15)
        button(g, x + w / 2 + 10, y + h - 70, w / 2 - 40, 46, "HOME (B)", BLUE, size=15)
