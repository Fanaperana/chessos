"""Lesson / puzzle player: stars, check drills, puzzle lessons, daily puzzle, practice."""
import random
import time

from .. import motion
from ..board import Board, piece_sprite
from ..chess import Position, Move, parse_sq, uci, spoken
from ..content import CORRECT, WRONG, COLORS
from ..core import Scene
from ..ui import (BG, CARD, CARD_HI, BORDER, TEXT, SUB, WHITE, GOLD, GREEN, RED, BLUE, ORANGE,
                  progress_bar, bubble, hint, Banner, Confetti)

BOARD_X, BOARD_Y, SQ = 14, 54, 52
PANEL_X = 446
PANEL_W = 184
MAX_HEARTS = 5
PROMO = "QRBN"


def star_position(level):
    board = ["."] * 64
    board[parse_sq(level["at"])] = level["piece"]
    for s, p in level.get("targets", {}).items():
        board[parse_sq(s)] = p
    return Position(board, "w", "-", None, 0, 1)


class Lesson(Scene):
    def __init__(self, app, mode, unit=None, lesson=None, puzzle=None):
        Scene.__init__(self, app)
        self.mode = mode
        self.unit, self.lesson = unit, lesson
        self.color = COLORS[unit["color"]] if unit else (GOLD if mode == "daily" else BLUE)
        self.exercises = []
        p = app.progress
        if mode == "lesson":
            kind = lesson["kind"]
            if kind == "stars":
                self.exercises = [{"type": "stars", "level": lv} for lv in lesson["levels"]]
            elif kind == "check":
                self.exercises = [{"type": "check", "fen": f} for f in lesson["positions"]]
            else:
                ps = app.puzzles.for_lesson(lesson["id"], p.crowns(lesson["id"]), p.plays(lesson["id"]))
                self.exercises = [{"type": "puzzle", "puzzle": z} for z in ps]
        elif mode == "daily":
            self.exercises = [{"type": "puzzle", "puzzle": puzzle}]
        self.hearts = MAX_HEARTS if mode == "lesson" else None
        self.idx = 0
        self.done_count = 0
        self.mistakes_total = 0
        self.perfect = 0
        self.practice_streak = 0
        self.start_time = time.time()
        self.board = Board(app, BOARD_X, BOARD_Y, SQ)
        self.banner = Banner()
        self.confetti = Confetti()
        self.prog = motion.Value(0)
        self.heart_shake = -10.0
        self.heart_pop = motion.Value(1)
        self.state = "intro" if mode == "lesson" else "setup"
        self.timer = 0.0
        self.prompt = ""
        self.flash = None
        self.mascot_jump = motion.Value(0)
        self.intro_s = motion.Value(0)
        self.promo_moves = None
        self.promo_sel = 0
        self.after_wrong = None
        self.finished = False

    def enter(self):
        if self.state == "intro":
            self.intro_s.set(0).spring(1, "bouncy")
            self.app.audio.speak(self.lesson["intro"])
        else:
            self.setup()

    # ---- exercises --------------------------------------------------------------------
    def current(self):
        if self.mode == "practice":
            return getattr(self, "practice_ex", None)
        if not self.exercises:
            return None
        return self.exercises[min(self.idx, len(self.exercises) - 1)]

    def setup(self):
        if self.mode == "practice":
            pz = self.app.puzzles.practice_next(self.app.progress.data.get("practice_rating", 900),
                                                self.app.progress.data.get("practice_seen", [])[-300:])
            if pz is None:
                self.app.pop(fade=True)
                return
            self.practice_ex = {"type": "puzzle", "puzzle": pz}
        elif not self.exercises:
            self.app.pop(fade=True)
            return
        ex = self.current()
        self.ex_mistakes = 0
        self.used_hint = False
        self.ply = 0
        self.board.hint_sq = self.board.hint_to = None
        self.board.stars = {}
        t = ex["type"]
        if t == "puzzle":
            pz = ex["puzzle"]
            self.line = pz.moves
            pos = pz.start()
            self.side = pz.solver()
            self.board.flip = self.side == "b"
            self.board.set_position(pos)
            self.prompt = self.puzzle_prompt(pz)
            if pz.premove:
                self.state, self.timer = "reply", 0.9
            else:
                self.begin_play()
            self.app.audio.speak("Find the best move for white." if self.side == "w" else "Find the best move for black.")
        elif t == "stars":
            lv = ex["level"]
            pos = star_position(lv)
            self.side = "w"
            self.board.flip = False
            self.board.set_position(pos)
            self.board.set_stars([parse_sq(s) for s in lv["stars"]])
            self.prompt = "Collect all the stars!" if lv["stars"] else "Capture all the black pieces!"
            if lv.get("targets") and lv["stars"]:
                self.prompt = "Collect the stars and capture the black pieces!"
            self.moves_made = 0
            self.begin_play()
            self.app.audio.speak("Collect all the stars!" if lv["stars"] else "Capture the piece!")
        elif t == "check":
            pos = Position.from_fen(ex["fen"])
            self.side = pos.turn
            self.board.flip = False
            self.board.set_position(pos)
            self.prompt = "Find a move that puts the black king in check!"
            self.begin_play()
            self.app.audio.speak("Your move.")

    def puzzle_prompt(self, pz):
        th = pz.themes.split()
        who = "White" if pz.solver() == "w" else "Black"
        if "mateIn1" in th:
            return "%s to move. Find the checkmate in one!" % who
        if "mateIn2" in th:
            return "%s to move. Find mate in two!" % who
        if "mateIn3" in th:
            return "%s to move. Find mate in three!" % who
        if self.mode == "daily":
            return "%s to move. Find the best move!" % who
        return "%s to move. Find the best move!" % who

    def begin_play(self):
        self.state = "play"
        self.board.interactive = True
        piece_sq = None
        for s, p in enumerate(self.board.pos.board):
            if p != "." and (p.isupper() == (self.side == "w")):
                if self.current()["type"] == "stars" or piece_sq is None:
                    piece_sq = s
        if self.current()["type"] == "stars" and piece_sq is not None:
            self.board.set_cursor(piece_sq)
        elif self.board.last:
            self.board.set_cursor(self.board.last[1])
        elif piece_sq is not None:
            self.board.set_cursor(piece_sq)

    # ---- update -----------------------------------------------------------------------------
    def update(self, dt, actions):
        if self.timer > 0:
            self.timer -= dt
            if self.timer <= 0:
                self.on_timer()
        for a in actions:
            if a == "start" and self.state not in ("finish",):
                self.pause()
                return
            if self.state == "intro":
                if a == "a":
                    self.app.audio.sfx("select")
                    self.app.audio.stop_voice()
                    self.state = "setup"
                    self.setup()
                elif a == "b":
                    self.app.pop(fade=True)
                elif a == "x":
                    self.app.audio.speak(self.lesson["intro"])
            elif self.state == "play":
                self.play_input(a)
            elif self.state == "promo":
                self.promo_input(a)
            elif self.state in ("solved", "failed", "reveal"):
                if a == "a":
                    self.next_exercise()
            elif self.state == "dead":
                if a == "a":
                    self.app.pop(fade=True)

    def pause(self):
        from .dialog import Dialog

        def chosen(i):
            if i == 1:
                self.app.audio.stop_voice()
                self.app.pop(fade=True)
        msg = "Your progress in this lesson will be lost." if self.mode == "lesson" else "You can come back any time."
        self.app.push(Dialog(self.app, "Quit?", msg, ["KEEP LEARNING", "QUIT"], chosen, danger=1))

    def play_input(self, a):
        if a == "y":
            self.give_hint()
            return
        if a == "x":
            self.app.audio.speak(self.prompt if self.app.audio.has_clip(self.prompt) else
                                 ("Find the best move for white." if self.side == "w" else "Find the best move for black."))
            return
        if a == "b" and self.board.selected is None and self.mode != "lesson":
            self.pause()
            return
        m = self.board.handle(a, self.side)
        if m is None:
            return
        if m.promo:
            self.promo_moves = [mm for mm in self.board.targets if mm.to == m.to]
            self.promo_sel = 0
            self.state = "promo"
            self.app.audio.speak("Choose a piece for promotion.")
            return
        self.commit(m)

    def promo_input(self, a):
        if a in ("left", "up"):
            self.promo_sel = (self.promo_sel - 1) % 4
            self.app.audio.sfx("nav")
        elif a in ("right", "down"):
            self.promo_sel = (self.promo_sel + 1) % 4
            self.app.audio.sfx("nav")
        elif a == "a":
            want = PROMO[self.promo_sel]
            m = [mm for mm in self.promo_moves if mm.promo == want][0]
            self.state = "play"
            self.commit(m)
        elif a == "b":
            self.state = "play"
            self.board.selected, self.board.targets = None, []

    # ---- move logic ---------------------------------------------------------------------------
    def commit(self, m):
        ex = self.current()
        before = self.board.pos
        after = before.push(m)
        t = ex["type"]
        if t == "stars":
            after = Position(after.board, "w", "-", None, 0, 1)
            self.board.apply_move(before, m, after)
            self.moves_made += 1
            self.board.interactive = True
            if self.board.collect_star(m.to):
                self.app.audio.sfx("star")
                self.confetti.burst(*self.sq_center(m.to), n=18, spread=120, up=220)
            black_left = any(p != "." and p.islower() for p in after.board)
            if self.board.stars_left() == 0 and not black_left:
                self.solved()
            else:
                self.board.set_cursor(m.to)
            return
        if t == "check":
            ok = after.in_check()
            if ok:
                self.board.apply_move(before, m, after)
                self.app.audio.speak_words(spoken(before, m), interrupt=True)
                self.solved()
            else:
                self.wrong(before, m, after)
            return
        # puzzle
        expected = self.line[self.ply]
        last = self.ply == len(self.line) - 1
        if uci(m) == expected or (last and after.is_checkmate()):
            self.board.apply_move(before, m, after)
            self.app.audio.speak_words(spoken(before, m), interrupt=True)
            self.ply += 1
            self.board.hint_sq = self.board.hint_to = None
            if self.ply >= len(self.line):
                self.solved()
            else:
                self.state, self.timer = "reply", 0.55
                self.board.interactive = False
                self.flash = ("Keep going!", GREEN[0], motion.now())
        else:
            self.wrong(before, m, after)

    def on_timer(self):
        if self.state == "reply":
            before = self.board.pos
            m = before.parse_uci(self.line[self.ply])
            after = before.push(m)
            self.board.apply_move(before, m, after, duration=0.32)
            self.ply += 1
            if self.ply >= len(self.line):
                self.solved()
            else:
                self.begin_play()
        elif self.state == "undo":
            before, last = self.after_wrong
            self.board.set_position(before, pop=False)
            self.board.last = last
            self.after_wrong = None
            if self.hearts is not None and self.hearts <= 0:
                self.out_of_hearts()
            elif self.ex_mistakes >= 3 and self.current()["type"] == "puzzle":
                self.reveal()
            else:
                self.begin_play()
                if self.ex_mistakes >= 2:
                    self.give_hint(free=True)

    def wrong(self, before, m, after):
        last = self.board.last
        self.board.apply_move(before, m, after)
        self.board.interactive = False
        self.board.shake()
        self.app.audio.sfx("wrong")
        self.app.audio.speak(random.choice(WRONG))
        self.ex_mistakes += 1
        self.mistakes_total += 1
        self.flash = (random.choice(WRONG), RED[0], motion.now())
        if self.hearts is not None:
            self.hearts -= 1
            self.heart_shake = motion.now()
            self.heart_pop.set(1.5).spring(1, "bouncy")
            self.app.audio.sfx("heart")
        self.after_wrong = (before, last)
        self.state, self.timer = "undo", 0.8

    def give_hint(self, free=False):
        ex = self.current()
        if ex["type"] == "puzzle" and self.ply < len(self.line):
            m = self.board.pos.parse_uci(self.line[self.ply])
            if self.board.hint_sq == m.frm:
                self.board.hint_to = m.to
            self.board.hint_sq = m.frm
        elif ex["type"] == "check":
            for m in self.board.pos.legal_moves():
                if self.board.pos.push(m).in_check():
                    self.board.hint_sq = m.frm
                    break
        elif ex["type"] == "stars":
            left = [s for s, st in self.board.stars.items() if not st["collected"]]
            if left:
                self.board.hint_to = left[0]
        if not free:
            self.used_hint = True
        self.app.audio.speak("Here is a hint.")

    def reveal(self):
        before = self.board.pos
        m = before.parse_uci(self.line[self.ply])
        san = before.san(m)
        self.board.apply_move(before, m, before.push(m))
        self.board.interactive = False
        self.state = "reveal"
        self.banner.show("bad", "Solution: " + san, "No worries, you'll see it again soon.")
        self.app.audio.speak_words(["The solution was"] + spoken(before, m))
        if self.mode == "practice":
            self.practice_update(False)

    def out_of_hearts(self):
        self.state = "dead"
        self.board.interactive = False
        self.banner.show("bad", "Out of hearts!", "Take a break and try this lesson again.", "BACK HOME")
        self.app.audio.speak("Out of hearts. Let's try again later.")

    def solved(self):
        self.state = "solved"
        self.board.interactive = False
        perfect = self.ex_mistakes == 0 and not self.used_hint
        if perfect:
            self.perfect += 1
        self.done_count += 1
        phrase = random.choice(CORRECT)
        self.app.audio.sfx("correct")
        self.app.audio.speak(phrase, interrupt=False)
        self.mascot_jump.set(0).spring(0, "wobbly", velocity=-260)
        ex = self.current()
        sub = ""
        if ex["type"] == "puzzle":
            pz = ex["puzzle"]
            if pz.rating:
                sub = "Puzzle rating %d" % pz.rating
            if self.mode == "practice":
                self.practice_update(perfect)
                sub = "Rating %d   ·   +5 XP" % self.app.progress.data["practice_rating"]
        elif ex["type"] == "stars":
            sub = "Moves: %d" % self.moves_made
        self.banner.show("good", phrase, sub)
        self.prog.spring(self.done_count / float(max(1, len(self.exercises))), "bouncy")
        cx, cy = BOARD_X + SQ * 4, BOARD_Y + SQ * 4
        self.confetti.burst(cx, cy, n=36, spread=200, up=320)

    def practice_update(self, ok):
        p = self.app.progress
        r = p.data.get("practice_rating", 900)
        pz = self.current()["puzzle"]
        pr = pz.rating or r
        exp = 1.0 / (1 + 10 ** ((pr - r) / 400.0))
        r = int(round(r + 32 * ((1 if ok else 0) - exp)))
        p.data["practice_rating"] = max(400, min(3000, r))
        seen = p.data.setdefault("practice_seen", [])
        seen.append(pz.id)
        del seen[:-400]
        if ok:
            p.data["puzzles_solved"] += 1
            self.practice_streak += 1
            p.add_xp(5)
        else:
            self.practice_streak = 0
            p.save()

    def next_exercise(self):
        self.banner.hide()
        self.app.audio.sfx("select")
        if self.mode == "practice":
            self.setup()
            return
        if self.state in ("solved", "reveal"):
            if self.state == "reveal":
                self.done_count += 1
                self.prog.spring(self.done_count / float(max(1, len(self.exercises))), "bouncy")
            self.idx += 1
        if self.idx >= len(self.exercises):
            self.finish()
        else:
            self.setup()

    def finish(self):
        if self.finished:
            return
        self.finished = True
        self.state = "finish"
        p = self.app.progress
        elapsed = time.time() - self.start_time
        n = max(1, len(self.exercises))
        acc = int(round(100.0 * self.perfect / n))
        if self.mode == "lesson":
            xp = (10 if self.lesson["kind"] != "puzzles" else 15) + (5 if self.perfect == n else 0)
            p.complete_lesson(self.lesson["id"])
            if self.lesson["kind"] == "puzzles":
                p.data["puzzles_solved"] += self.done_count
            title = "Lesson complete!"
            lid = self.lesson["id"]
        else:
            xp = 15 + (5 if self.mistakes_total == 0 else 0)
            p.data["daily_done"][p.today().isoformat()] = self.exercises[0]["puzzle"].id
            p.data["puzzles_solved"] += 1
            title = "Daily puzzle solved!"
            lid = None
        before_goal = p.xp_today() >= p.goal()
        extended = p.add_xp(xp)
        goal_hit = not before_goal and p.xp_today() >= p.goal()
        from .complete import Complete
        self.app.replace(Complete(self.app, title, xp, acc, elapsed, extended, goal_hit, lid, self.color))

    # ---- drawing ----------------------------------------------------------------------------------
    def sq_center(self, s):
        x, y = self.board.sq_xy(s)
        return x + SQ / 2.0, y + SQ / 2.0

    def draw(self, g, dt):
        p = self.app.progress
        # top bar
        g.text("✕", 28, 25, 22, SUB, "sym", align="c", valign="m")
        g.text("START", 28, 42, 8, SUB, 900, align="c")
        if self.mode == "lesson":
            progress_bar(g, 56, 17, 470, 16, self.prog.get(), self.color[0])
        else:
            title = "Daily Puzzle" if self.mode == "daily" else "Practice"
            g.text(title, 56, 25, 20, self.color[0], 900, valign="m")
            sub = p.today().strftime("%A, %B %d") if self.mode == "daily" else \
                "Rating %d  ·  Streak %d" % (p.data.get("practice_rating", 900), self.practice_streak)
            g.text(sub, 56 + g.text_size(title, 20, 900)[0] + 14, 26, 14, SUB, 800, valign="m")
        if self.hearts is not None:
            hx = 586 + motion.shake(self.heart_shake, 6, 0.4)
            g.draw_sprite("heart", hx, 25, 26 * self.heart_pop.get(), a=1 if self.hearts > 0 else 0.35)
            g.text(str(max(0, self.hearts)), hx + 18, 25, 18, RED[0], 900, valign="m")
        if self.state == "intro":
            self.draw_intro(g)
            return
        self.board.draw(g, p.setting("board"))
        self.draw_panel(g)
        if self.state == "promo":
            self.draw_promo(g)
        self.confetti.draw(g, dt)
        self.banner.draw(g)

    def draw_intro(self, g):
        s = self.intro_s.get()
        l = self.lesson
        g.text(self.unit["title"].upper(), 320, 70, 14, self.color[0], 900, align="c", a=min(1, s))
        g.text(l["title"], 320, 88, 30, TEXT, 900, align="c", a=min(1, s))
        g.draw_sprite("mascot", 120, 270 + 5 * motion.pulse(1.5), 150 * s)
        bx, by, bw = 220, 170, 390
        lines = g.wrap(l["intro"], bw - 36, 18, 800)
        bh = len(lines) * 25 + 32
        if s > 0.5:
            bubble(g, bx, by, bw, bh, tail_x=bh / 2.0)
            for i, ln in enumerate(lines):
                g.text(ln, bx + 18, by + 16 + i * 25, 18, TEXT, 800)
            g.draw_sprite("speaker", bx + bw - 20, by + bh - 18, 18, color=BLUE[0])
        from ..ui import button
        button(g, 220, 400, 200, 48, "LET'S GO!", self.color)
        hint(g, 320, 456, [("A", "Start"), ("X", "Listen"), ("B", "Back")], align="c")

    def draw_panel(self, g):
        x, w = PANEL_X, PANEL_W
        # mascot + bubble
        lines = g.wrap(self.prompt, w - 24, 15, 800)
        bh = len(lines) * 20 + 22
        bubble(g, x, 58, w, bh, tail_x=w / 2.0, tail_side="bottom")
        for i, ln in enumerate(lines):
            g.text(ln, x + 12, 69 + i * 20, 15, TEXT, 800)
        my = 58 + bh + 58 + self.mascot_jump.get() * 0.25 + 3 * motion.pulse(1.6)
        g.draw_sprite("mascot", x + w / 2.0, my, 90)
        y = 58 + bh + 112
        # side to move
        side = getattr(self, "side", "w")
        g.rrect(x, y, w, 34, 12, CARD)
        g.circle(x + 20, y + 17, 9, WHITE if side == "w" else (30, 30, 30))
        g.circle(x + 20, y + 17, 9 if side == "b" else 0, (30, 30, 30))
        g.text("White to move" if side == "w" else "Black to move", x + 38, y + 17, 15, TEXT, 800, valign="m")
        y += 44
        ex = self.current()
        if ex and ex["type"] == "puzzle":
            pz = ex["puzzle"]
            info = "Rating %d" % pz.rating if pz.rating else (pz.source or "Custom puzzle")
            g.text(info, x + 4, y, 13, SUB, 800)
            if self.state in ("solved", "reveal"):
                tags = [t for t in pz.themes.split() if t not in ("short", "long", "veryLong", "oneMove",
                                                                 "middlegame", "endgame", "opening", "crushing",
                                                                 "advantage", "master", "masterVsMaster")]
                g.text_block(" · ".join(tags[:4]), x + 4, y + 18, w - 8, 12, BLUE[0], 800)
        elif ex and ex["type"] == "stars":
            g.text("Stars left: %d" % self.board.stars_left(), x + 4, y, 13, GOLD[0], 900)
        if self.mode == "lesson":
            g.text("Exercise %d of %d" % (min(self.idx + 1, len(self.exercises)), len(self.exercises)),
                   x + 4, y + 52, 12, SUB, 800)
        # flash text (feedback)
        if self.flash and motion.now() - self.flash[2] < 1.2:
            age = motion.now() - self.flash[2]
            a = min(1.0, (1.2 - age) * 3)
            g.text(self.flash[0], x + w / 2.0, 58 + bh + 8 - age * 12, 15, self.flash[1], 900, align="c", a=a)
        hint(g, x, 410, [("A", "Move"), ("B", "Cancel")])
        hint(g, x, 436, [("Y", "Hint"), ("X", "Speak")])

    def draw_promo(self, g):
        g.rect(BOARD_X, BOARD_Y, SQ * 8, SQ * 8, (0, 0, 0), 0.55)
        w = 4 * 74 + 20
        x = BOARD_X + SQ * 4 - w / 2.0
        y = BOARD_Y + SQ * 4 - 60
        g.rrect(x, y, w, 120, 18, CARD)
        g.text("Promote to", BOARD_X + SQ * 4, y + 10, 16, TEXT, 900, align="c")
        for i, pc in enumerate(PROMO):
            cx = x + 10 + 37 + i * 74
            sel = i == self.promo_sel
            if sel:
                g.rrect(cx - 33, y + 36, 66, 72, 14, GREEN[0])
            g.rrect(cx - 30, y + 39, 60, 66, 12, CARD_HI)
            letter = pc if self.side == "w" else pc.lower()
            g.draw_sprite(piece_sprite(letter), cx, y + 72, 56 * (1.08 if sel else 1))
