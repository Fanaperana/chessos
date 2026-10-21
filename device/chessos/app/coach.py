"""The ChessOS coach: grades moves with engine evaluations, spots tactics, names
openings and picks a line from the phrase bank (Fritz-style commentary).

Phrases without {slots} get pre-rendered Kokoro clips (see static_lines());
phrases with slots are spoken live by Piper on the device.
"""
import math
import random

from .chess import PIECE_WORDS, sq_name, uci

VALUE = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}

# ---- phrase bank -------------------------------------------------------------------
P = {
    "start_white": ["Let's play! You have the white pieces. Good luck!",
                    "New game. You're white, so you move first.",
                    "Here we go. White to move, that's you!"],
    "start_black": ["Let's play! You have the black pieces. I'll start.",
                    "New game. I'm white, so I move first. Ready?",
                    "Here we go. You're black, watch my first move."],
    "best": ["Excellent move!", "That's exactly what I would play.", "Best move. Very nice!",
             "Strong move!", "Perfect. You found the best move.", "Great move!",
             "Precise! That's the top engine choice."],
    "good": ["Good move.", "Solid.", "Nice, that works.", "Reasonable move.", "Fine move.",
             "That's a good idea.", "Okay, keep going."],
    "inaccuracy": ["Hmm, not the most precise move.", "That's a small inaccuracy.",
                   "There was something slightly better.", "Playable, but not the best."],
    "inaccuracy_hint": ["A little imprecise. {best} was a bit stronger.",
                        "Not bad, but {best} was better here."],
    "mistake": ["That's a mistake.", "Hmm, that one costs you.", "Careful, that weakens your position.",
                "Oh no, that's not good."],
    "mistake_hint": ["That's a mistake. {best} was much better.",
                     "Hmm. Better was {best}."],
    "blunder": ["Ouch! That's a blunder.", "Oh no, a big blunder!", "That's a serious mistake.",
                "Whoops! That move loses a lot."],
    "hangs": ["Careful! Your {piece} on {square} is hanging.",
              "That leaves your {piece} on {square} undefended.",
              "Blunder! Now I can take your {piece} on {square}."],
    "allows_mate": ["Watch out! That allows checkmate.", "Oh no, now I have a checkmate!",
                    "Danger! You just allowed a mating attack."],
    "missed_mate": ["You had a checkmate! {best} was mate.", "So close! {best} would have been checkmate."],
    "missed_capture": ["You could have taken my {piece} on {square}.",
                       "Did you see my {piece} on {square} was free?"],
    "fork": ["A fork! Your {piece} attacks two pieces at once.", "Nice fork with the {piece}!",
             "Fork! Two of my pieces are under attack."],
    "check": ["Check!", "Check. My king has to move.", "A check! Let me think."],
    "capture": ["You take my {captured}.", "There goes my {captured}.", "You win my {captured}."],
    "trade": ["A fair trade.", "Pieces come off the board.", "An even exchange."],
    "castle": ["Good, you castled. Your king is safer now.", "Castling. King safety first, nice!",
               "Smart, getting your king to safety."],
    "promote": ["Promotion! A brand new queen.", "Your pawn becomes a queen. Wonderful!"],
    "opening": ["This is the {opening}.", "Ah, the {opening}. A classic.", "We're in the {opening}."],
    "my_capture": ["I take your {captured}.", "I'll grab that {captured}.", "Thank you for the {captured}!"],
    "my_check": ["Check! Your king is under attack.", "Check! How will you get out of this?", "Check!"],
    "threat": ["Watch out, I'm threatening your {piece}.", "Careful, your {piece} on {square} is under attack."],
    "winning": ["You're doing great. You're winning!", "You have a clear advantage now.",
                "Your position looks very good."],
    "losing": ["I'm ahead now. Can you fight back?", "This is getting tough for you. Look for counterplay!",
               "Things look difficult. Stay calm and defend."],
    "equal": ["The position is about equal.", "It's an even game so far.", "Balanced position."],
    "you_won": ["Checkmate! You win! Well played!", "Checkmate! Brilliant game, you beat me!"],
    "you_lost": ["Checkmate. I win this time. Let's play again!", "That's checkmate. Good fight, try again!"],
    "draw": ["It's a draw!", "Draw! A hard-fought game."],
    "hint": ["Try moving your {piece} to {square}.", "Look at your {piece}. What about {square}?",
             "Hint: the {piece} on {from} has a good move."],
    "takeback": ["Okay, let's take that back.", "No problem, try again."],
    "thinking": ["Let me think.", "Hmm, interesting.", "Let me see."],
}

OPENINGS = [  # (SAN sequence, name) - the longest match wins
    ("e4", "King's Pawn Opening"), ("d4", "Queen's Pawn Opening"), ("c4", "English Opening"),
    ("Nf3", "Reti Opening"), ("e4 e5", "Open Game"), ("e4 c5", "Sicilian Defense"),
    ("e4 e6", "French Defense"), ("e4 c6", "Caro-Kann Defense"), ("e4 d5", "Scandinavian Defense"),
    ("e4 d6", "Pirc Defense"), ("e4 Nf6", "Alekhine's Defense"), ("e4 g6", "Modern Defense"),
    ("e4 e5 Nf3 Nc6", "King's Knight Opening"), ("e4 e5 Nf3 Nc6 Bc4", "Italian Game"),
    ("e4 e5 Nf3 Nc6 Bc4 Bc5", "Giuoco Piano"), ("e4 e5 Nf3 Nc6 Bc4 Nf6", "Two Knights Defense"),
    ("e4 e5 Nf3 Nc6 Bb5", "Ruy Lopez"), ("e4 e5 Nf3 Nc6 d4", "Scotch Game"),
    ("e4 e5 Nf3 Nf6", "Petrov's Defense"), ("e4 e5 Nf3 d6", "Philidor Defense"),
    ("e4 e5 f4", "King's Gambit"), ("e4 e5 Nc3", "Vienna Game"), ("e4 e5 Bc4", "Bishop's Opening"),
    ("e4 e5 Qh5", "Wayward Queen Attack"), ("e4 c5 Nf3 d6", "Sicilian Defense"),
    ("e4 c5 Nc3", "Closed Sicilian"), ("e4 c5 c3", "Alapin Sicilian"),
    ("e4 e6 d4 d5", "French Defense"), ("e4 c6 d4 d5", "Caro-Kann Defense"),
    ("d4 d5", "Closed Game"), ("d4 d5 c4", "Queen's Gambit"), ("d4 d5 c4 e6", "Queen's Gambit Declined"),
    ("d4 d5 c4 dxc4", "Queen's Gambit Accepted"), ("d4 d5 c4 c6", "Slav Defense"),
    ("d4 d5 Bf4", "London System"), ("d4 Nf6 Bf4", "London System"), ("d4 Nf6", "Indian Defense"),
    ("d4 Nf6 c4 g6", "King's Indian Defense"), ("d4 Nf6 c4 e6", "Queen's Indian setup"),
    ("d4 Nf6 c4 e6 Nc3 Bb4", "Nimzo-Indian Defense"), ("d4 Nf6 c4 g6 Nc3 d5", "Grunfeld Defense"),
    ("d4 f5", "Dutch Defense"), ("d4 Nf6 c4 c5", "Benoni Defense"), ("c4 e5", "Reversed Sicilian"),
]

TACTIC_PHRASES = ("hangs", "allows_mate", "missed_mate", "missed_capture", "fork", "promote")


def static_lines():
    """Phrases without slots: these get Kokoro clips."""
    out = []
    for lines in P.values():
        out += [l for l in lines if "{" not in l]
    return out


# ---- helpers ---------------------------------------------------------------------------
def win_prob(cp):
    """Expected score (0..1) for an evaluation in centipawns (Lichess formula)."""
    cp = max(-2000, min(2000, cp))
    return 1.0 / (1.0 + math.exp(-0.00368208 * cp))


def move_accuracy(wp_before, wp_after):
    loss = max(0.0, (wp_before - wp_after) * 100)
    return max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * loss) - 3.1669))


def color(p):
    return "w" if p.isupper() else "b"


def attackers(pos, sq, by):
    """Squares of `by` pieces attacking sq (uses the side-to-move independent attack test per piece)."""
    out = []
    for s, p in enumerate(pos.board):
        if p == "." or color(p) != by:
            continue
        b = pos.board[:]
        # place an enemy pawn on sq so pawn captures count, then ask: can p capture it?
        from .chess import Position
        tmp = Position(b, by, "-", None, 0, 1)
        if tmp.board[sq] == "." or color(tmp.board[sq]) == by:
            tmp.board[sq] = "p" if by == "w" else "P"
        for m in tmp.pseudo_moves():
            if m.frm == s and m.to == sq:
                out.append(s)
                break
    return out


def hanging_pieces(pos, side):
    """Pieces of `side` that the opponent can win: undefended and attacked, or
    attacked by a cheaper piece."""
    them = "b" if side == "w" else "w"
    out = []
    for s, p in enumerate(pos.board):
        if p == "." or color(p) != side or p.upper() == "K":
            continue
        atk = attackers(pos, s, them)
        if not atk:
            continue
        cheapest = min(VALUE[pos.board[a].upper()] or 100 for a in atk)
        defended = bool(attackers(pos, s, side))
        if not defended or cheapest < VALUE[p.upper()]:
            out.append((VALUE[p.upper()], s, p))
    out.sort(reverse=True)
    return out


def forked(pos_after, moved_to, side):
    """Enemy pieces (worth at least a knight, or the king) attacked by the piece on moved_to."""
    from .chess import Position
    p = pos_after.board[moved_to]
    tmp = Position(pos_after.board[:], side, "-", None, 0, 1)
    hits = []
    for m in tmp.pseudo_moves():
        if m.frm != moved_to:
            continue
        t = pos_after.board[m.to]
        if t != "." and color(t) != side and (t.upper() == "K" or VALUE[t.upper()] > VALUE[p.upper()]
                                               or (VALUE[t.upper()] >= 3 and not attackers(pos_after, m.to, color(t)))):
            hits.append(m.to)
    return sorted(set(hits))


def opening_name(sans):
    best = None
    seq = " ".join(s.rstrip("+#") for s in sans)
    for line, name in OPENINGS:
        if seq == line or seq.startswith(line + " "):
            if best is None or len(line) > len(best[0]):
                best = (line, name)
    return best[1] if best else None


# ---- the coach ---------------------------------------------------------------------------
class Coach(object):
    def __init__(self, player):
        self.player = player
        self.recent = []
        self.said_opening = None
        self.last_eval_comment = 0
        self.ply = 0
        self.stats = {"best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0}
        self.accuracies = []

    def pick(self, key, **slots):
        lines = P[key]
        fresh = [l for l in lines if l not in self.recent] or lines
        line = random.choice(fresh)
        self.recent = (self.recent + [line])[-12:]
        return line.format(**slots) if slots else line

    def describe(self, pos, m):
        """Short human description of move m in pos, e.g. 'knight to f3'."""
        p = pos.board[m.frm].upper()
        if p == "K" and abs(m.to - m.frm) == 2:
            return "castling"
        return "%s to %s" % (PIECE_WORDS[p], sq_name(m.to))

    def start(self):
        return self.pick("start_white" if self.player == "w" else "start_black")

    def player_move(self, before, m, after, eval_before, eval_after, best_uci, sans, reply_uci=None):
        """Comment on the player's move.
        eval_before/eval_after: centipawns from the PLAYER's point of view
        (mates already folded in as +-10000). reply_uci: the engine's best answer.
        Returns (text, grade)."""
        self.ply += 1
        quiet_ok = self.ply - getattr(self, "last_quiet", -9) >= 2
        wb, wa = win_prob(eval_before), win_prob(eval_after)
        loss = wb - wa
        self.accuracies.append(move_accuracy(wb, wa))
        is_best = best_uci is not None and uci(m) == best_uci
        best_desc = None
        best_move = None
        if best_uci and not is_best:
            try:
                best_move = before.parse_uci(best_uci)
                best_desc = self.describe(before, best_move)
            except ValueError:
                pass

        if is_best or loss < 0.02:
            grade = "best" if is_best else "good"
        elif loss < 0.10:
            grade = "good"
        elif loss < 0.20:
            grade = "inaccuracy"
        elif loss < 0.30:
            grade = "mistake"
        else:
            grade = "blunder"
        self.stats[grade] += 1

        captured = before.board[m.to] if before.board[m.to] != "." else None
        if after.is_checkmate():
            return self.pick("you_won"), grade
        # serious problems first
        if eval_after <= -9000 and eval_before > -9000:
            return self.pick("allows_mate"), grade
        if eval_before >= 9000 and eval_after < 9000 and best_desc:
            return self.pick("missed_mate", best=best_desc), grade
        # the engine's best reply wins a real piece: say so even in lost positions
        if reply_uci and grade != "best":
            try:
                r = after.parse_uci(reply_uci)
                t = after.board[r.to]
                if t != "." and color(t) == self.player and VALUE[t.upper()] >= 3 and                         (r.to in [s for _, s, _ in hanging_pieces(after, self.player)]):
                    return self.pick("hangs", piece=PIECE_WORDS[t.upper()], square=sq_name(r.to)), grade
            except ValueError:
                pass
        if grade in ("blunder", "mistake"):
            hang = hanging_pieces(after, self.player)
            if hang and hang[0][0] >= 3:
                _, s, p = hang[0]
                return self.pick("hangs", piece=PIECE_WORDS[p.upper()], square=sq_name(s)), grade
            if best_move is not None and before.board[best_move.to] != "." and \
                    VALUE[before.board[best_move.to].upper()] >= 3:
                t = before.board[best_move.to]
                return self.pick("missed_capture", piece=PIECE_WORDS[t.upper()], square=sq_name(best_move.to)), grade
            if grade == "blunder":
                return self.pick("blunder"), grade
            return (self.pick("mistake_hint", best=best_desc) if best_desc else self.pick("mistake")), grade
        # nice things
        if m.promo:
            return self.pick("promote"), grade
        fork = forked(after, m.to, self.player) if grade in ("best", "good") else []
        if len(fork) >= 2:
            return self.pick("fork", piece=PIECE_WORDS[after.board[m.to].upper()]), grade
        if before.board[m.frm].upper() == "K" and abs(m.to - m.frm) == 2:
            return self.pick("castle"), grade
        name = opening_name(sans)
        if name and name != self.said_opening and len(sans) <= 10:
            self.said_opening = name
            return self.pick("opening", opening=name), grade
        if grade == "inaccuracy":
            return (self.pick("inaccuracy_hint", best=best_desc) if best_desc and random.random() < 0.5
                    else self.pick("inaccuracy")), grade
        if captured and grade in ("best", "good"):
            if random.random() < 0.6:
                return self.pick("capture", captured=PIECE_WORDS[captured.upper()]), grade
        if after.in_check():
            return self.pick("check"), grade
        if self.ply - self.last_eval_comment >= 7:
            self.last_eval_comment = self.ply
            return self.eval_comment(eval_after), grade
        # routine moves: speak at most every other move, and not always
        if quiet_ok and grade == "best" and random.random() < 0.35:
            self.last_quiet = self.ply
            return self.pick("best"), grade
        if quiet_ok and random.random() < 0.15:
            self.last_quiet = self.ply
            return self.pick("good"), grade
        return None, grade

    def eval_comment(self, ev):
        if ev > 250:
            return self.pick("winning")
        if ev < -250:
            return self.pick("losing")
        return self.pick("equal")

    def engine_move(self, before, m, after):
        """Comment on the coach's own move (only when worth saying)."""
        if after.is_checkmate():
            return self.pick("you_lost")
        captured = before.board[m.to]
        if captured != "." and VALUE[captured.upper()] >= 3:
            return self.pick("my_capture", captured=PIECE_WORDS[captured.upper()])
        if after.in_check():
            return self.pick("my_check")
        hang = hanging_pieces(after, self.player)
        if hang and hang[0][0] >= 3 and random.random() < 0.7:
            _, s, p = hang[0]
            return self.pick("threat", piece=PIECE_WORDS[p.upper()], square=sq_name(s))
        return None

    def hint(self, pos, best_uci):
        try:
            m = pos.parse_uci(best_uci)
        except (ValueError, TypeError):
            return None, None
        p = PIECE_WORDS[pos.board[m.frm].upper()]
        return self.pick("hint", piece=p, square=sq_name(m.to), **{"from": sq_name(m.frm)}), m

    def accuracy(self):
        return sum(self.accuracies) / len(self.accuracies) if self.accuracies else 0.0
