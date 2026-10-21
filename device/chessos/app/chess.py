"""Small, dependency-free chess rules engine for ChessOS.

Board squares are 0..63 with a1 = 0, h1 = 7, a8 = 56.
Pieces are FEN letters ('P','n',...) and '.' for empty.
Positions are immutable: push() returns a new Position.
"""
from collections import namedtuple

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

Move = namedtuple("Move", "frm to promo")
Move.__new__.__defaults__ = (None,)


def sq_name(s):
    return FILES[s % 8] + str(s // 8 + 1)


def parse_sq(name):
    return FILES.index(name[0]) + (int(name[1]) - 1) * 8


def uci(m):
    return sq_name(m.frm) + sq_name(m.to) + (m.promo.lower() if m.promo else "")


def color_of(p):
    if p == ".":
        return None
    return "w" if p.isupper() else "b"


# ---- precomputed attack tables -------------------------------------------
def _steps(deltas):
    table = []
    for s in range(64):
        f, r = s % 8, s // 8
        out = []
        for df, dr in deltas:
            nf, nr = f + df, r + dr
            if 0 <= nf < 8 and 0 <= nr < 8:
                out.append(nr * 8 + nf)
        table.append(out)
    return table


def _rays(dirs):
    table = []
    for s in range(64):
        f, r = s % 8, s // 8
        rays = []
        for df, dr in dirs:
            ray = []
            nf, nr = f + df, r + dr
            while 0 <= nf < 8 and 0 <= nr < 8:
                ray.append(nr * 8 + nf)
                nf += df
                nr += dr
            rays.append(ray)
        table.append(rays)
    return table


KNIGHT = _steps([(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)])
KING = _steps([(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)])
DIAG = _rays([(1, 1), (1, -1), (-1, 1), (-1, -1)])
ORTH = _rays([(1, 0), (-1, 0), (0, 1), (0, -1)])


class Position(object):
    __slots__ = ("board", "turn", "castling", "ep", "halfmove", "fullmove", "_legal")

    def __init__(self, board, turn="w", castling="-", ep=None, halfmove=0, fullmove=1):
        self.board = board
        self.turn = turn
        self.castling = castling or "-"
        self.ep = ep
        self.halfmove = halfmove
        self.fullmove = fullmove
        self._legal = None

    # ---- FEN ---------------------------------------------------------------
    @classmethod
    def from_fen(cls, fen=START_FEN):
        parts = fen.strip().split()
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError("bad FEN: " + fen)
        board = ["."] * 64
        for i, row in enumerate(rows):
            r = 7 - i
            f = 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    board[r * 8 + f] = ch
                    f += 1
        turn = parts[1] if len(parts) > 1 else "w"
        castling = parts[2] if len(parts) > 2 else "-"
        ep = parse_sq(parts[3]) if len(parts) > 3 and parts[3] != "-" else None
        half = int(parts[4]) if len(parts) > 4 else 0
        full = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, turn, castling, ep, half, full)

    def fen(self):
        rows = []
        for r in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.board[r * 8 + f]
                if p == ".":
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p
            if empty:
                row += str(empty)
            rows.append(row)
        ep = sq_name(self.ep) if self.ep is not None else "-"
        return "%s %s %s %s %d %d" % ("/".join(rows), self.turn, self.castling, ep, self.halfmove, self.fullmove)

    # ---- queries -----------------------------------------------------------
    def king_sq(self, color):
        k = "K" if color == "w" else "k"
        try:
            return self.board.index(k)
        except ValueError:
            return None

    def attacked(self, sq, by):
        """Is square `sq` attacked by side `by`?"""
        b = self.board
        if by == "w":
            n, k, p, bq, rq = "N", "K", "P", ("B", "Q"), ("R", "Q")
        else:
            n, k, p, bq, rq = "n", "k", "p", ("b", "q"), ("r", "q")
        for t in KNIGHT[sq]:
            if b[t] == n:
                return True
        for t in KING[sq]:
            if b[t] == k:
                return True
        f = sq % 8
        if by == "w":
            if sq >= 8:
                if f > 0 and b[sq - 9] == p:
                    return True
                if f < 7 and b[sq - 7] == p:
                    return True
        else:
            if sq < 56:
                if f > 0 and b[sq + 7] == p:
                    return True
                if f < 7 and b[sq + 9] == p:
                    return True
        for ray in DIAG[sq]:
            for t in ray:
                q = b[t]
                if q != ".":
                    if q in bq:
                        return True
                    break
        for ray in ORTH[sq]:
            for t in ray:
                q = b[t]
                if q != ".":
                    if q in rq:
                        return True
                    break
        return False

    def in_check(self, color=None):
        color = color or self.turn
        k = self.king_sq(color)
        if k is None:
            return False
        return self.attacked(k, "b" if color == "w" else "w")

    # ---- move generation ---------------------------------------------------
    def pseudo_moves(self):
        b = self.board
        me = self.turn
        them = "b" if me == "w" else "w"
        moves = []
        add = moves.append
        for s in range(64):
            p = b[s]
            if p == "." or color_of(p) != me:
                continue
            u = p.upper()
            if u == "P":
                fwd = 8 if me == "w" else -8
                start_rank = 1 if me == "w" else 6
                last_rank = 7 if me == "w" else 0
                t = s + fwd
                if 0 <= t < 64 and b[t] == ".":
                    if t // 8 == last_rank:
                        for pr in "QRBN":
                            add(Move(s, t, pr))
                    else:
                        add(Move(s, t))
                        t2 = t + fwd
                        if s // 8 == start_rank and b[t2] == ".":
                            add(Move(s, t2))
                f = s % 8
                for df in (-1, 1):
                    if not 0 <= f + df < 8:
                        continue
                    t = s + fwd + df
                    if not 0 <= t < 64:
                        continue
                    if color_of(b[t]) == them or t == self.ep:
                        if t // 8 == last_rank:
                            for pr in "QRBN":
                                add(Move(s, t, pr))
                        else:
                            add(Move(s, t))
            elif u == "N" or u == "K":
                for t in (KNIGHT if u == "N" else KING)[s]:
                    if color_of(b[t]) != me:
                        add(Move(s, t))
            else:
                rays = []
                if u in "BQ":
                    rays += DIAG[s]
                if u in "RQ":
                    rays += ORTH[s]
                for ray in rays:
                    for t in ray:
                        q = b[t]
                        if q == ".":
                            add(Move(s, t))
                        else:
                            if color_of(q) == them:
                                add(Move(s, t))
                            break
        # castling
        c = self.castling
        if c != "-":
            if me == "w" and b[4] == "K":
                if "K" in c and b[7] == "R" and b[5] == "." and b[6] == "." and not self.attacked(4, them) \
                        and not self.attacked(5, them) and not self.attacked(6, them):
                    add(Move(4, 6))
                if "Q" in c and b[0] == "R" and b[1] == "." and b[2] == "." and b[3] == "." \
                        and not self.attacked(4, them) and not self.attacked(3, them) and not self.attacked(2, them):
                    add(Move(4, 2))
            elif me == "b" and b[60] == "k":
                if "k" in c and b[63] == "r" and b[61] == "." and b[62] == "." and not self.attacked(60, them) \
                        and not self.attacked(61, them) and not self.attacked(62, them):
                    add(Move(60, 62))
                if "q" in c and b[56] == "r" and b[57] == "." and b[58] == "." and b[59] == "." \
                        and not self.attacked(60, them) and not self.attacked(59, them) and not self.attacked(58, them):
                    add(Move(60, 58))
        return moves

    def legal_moves(self):
        if self._legal is None:
            me = self.turn
            out = []
            for m in self.pseudo_moves():
                nxt = self.push(m)
                if not nxt.in_check(me):
                    out.append(m)
            self._legal = out
        return self._legal

    def moves_from(self, sq):
        return [m for m in self.legal_moves() if m.frm == sq]

    def is_checkmate(self):
        return self.in_check() and not self.legal_moves()

    def is_stalemate(self):
        return not self.in_check() and not self.legal_moves()

    # ---- making moves --------------------------------------------------------
    def push(self, m):
        b = self.board[:]
        p = b[m.frm]
        captured = b[m.to]
        b[m.to] = p
        b[m.frm] = "."
        u = p.upper()
        ep = None
        if u == "P":
            if m.to == self.ep and captured == ".":
                b[m.to - 8 if p == "P" else m.to + 8] = "."
                captured = "p" if p == "P" else "P"
            if abs(m.to - m.frm) == 16:
                ep = (m.to + m.frm) // 2
            if m.promo:
                b[m.to] = m.promo.upper() if p == "P" else m.promo.lower()
        elif u == "K" and abs(m.to - m.frm) == 2:
            if m.to == 6:
                b[5], b[7] = "R", "."
            elif m.to == 2:
                b[3], b[0] = "R", "."
            elif m.to == 62:
                b[61], b[63] = "r", "."
            elif m.to == 58:
                b[59], b[56] = "r", "."
        c = self.castling
        if c != "-":
            for sq, flag in ((4, "KQ"), (60, "kq"), (0, "Q"), (7, "K"), (56, "q"), (63, "k")):
                if m.frm == sq or m.to == sq:
                    for ch in flag:
                        c = c.replace(ch, "")
            if not c:
                c = "-"
        half = 0 if (u == "P" or captured != ".") else self.halfmove + 1
        full = self.fullmove + (1 if self.turn == "b" else 0)
        return Position(b, "b" if self.turn == "w" else "w", c, ep, half, full)

    def is_capture(self, m):
        return self.board[m.to] != "." or (self.board[m.frm].upper() == "P" and m.to == self.ep)

    # ---- SAN -----------------------------------------------------------------
    def san(self, m):
        p = self.board[m.frm]
        u = p.upper()
        if u == "K" and abs(m.to - m.frm) == 2:
            s = "O-O" if m.to % 8 == 6 else "O-O-O"
        else:
            cap = self.is_capture(m)
            if u == "P":
                s = (FILES[m.frm % 8] + "x" if cap else "") + sq_name(m.to)
                if m.promo:
                    s += "=" + m.promo.upper()
            else:
                s = u
                others = [o for o in self.legal_moves()
                          if o.to == m.to and o.frm != m.frm and self.board[o.frm] == p]
                if others:
                    same_file = any(o.frm % 8 == m.frm % 8 for o in others)
                    same_rank = any(o.frm // 8 == m.frm // 8 for o in others)
                    if not same_file:
                        s += FILES[m.frm % 8]
                    elif not same_rank:
                        s += str(m.frm // 8 + 1)
                    else:
                        s += sq_name(m.frm)
                s += ("x" if cap else "") + sq_name(m.to)
        nxt = self.push(m)
        if nxt.in_check():
            s += "#" if not nxt.legal_moves() else "+"
        return s

    def parse_san(self, text):
        t = text.strip().replace("0", "O").rstrip("+#!?")
        t = t.replace("x", "").replace("=", "").replace("-", "") if not t.startswith("O") else t.replace("-", "")
        for m in self.legal_moves():
            s = self.san(m).rstrip("+#")
            if s.startswith("O"):
                s2 = s.replace("-", "")
            else:
                s2 = s.replace("x", "").replace("=", "")
            if s2 == t:
                return m
        # lenient: pawn promotion without piece, e.g. "e8" -> queen
        for m in self.legal_moves():
            if m.promo == "Q" and sq_name(m.to) == t[-2:] and self.board[m.frm].upper() == "P" \
                    and (len(t) == 2 or t[0] == FILES[m.frm % 8]):
                return m
        raise ValueError("illegal SAN %r in %s" % (text, self.fen()))

    def parse_uci(self, text):
        frm, to = parse_sq(text[0:2]), parse_sq(text[2:4])
        promo = text[4].upper() if len(text) > 4 else None
        for m in self.legal_moves():
            if m.frm == frm and m.to == to and (m.promo or None) == promo:
                return m
        raise ValueError("illegal UCI %r in %s" % (text, self.fen()))


PIECE_WORDS = {"P": "pawn", "N": "knight", "B": "bishop", "R": "rook", "Q": "queen", "K": "king"}


def spoken(pos, m):
    """Words for the voice system, e.g. ['knight', 'takes', 'e5', 'check']."""
    p = pos.board[m.frm].upper()
    words = []
    if p == "K" and abs(m.to - m.frm) == 2:
        words.append("castles kingside" if m.to % 8 == 6 else "castles queenside")
    else:
        words.append(PIECE_WORDS[p])
        if pos.is_capture(m):
            words.append("takes")
        words.append(sq_name(m.to))
        if m.promo:
            words += ["promotes to", PIECE_WORDS[m.promo.upper()]]
    nxt = pos.push(m)
    if nxt.in_check():
        words.append("checkmate" if not nxt.legal_moves() else "check")
    return words


def perft(pos, depth):
    if depth == 0:
        return 1
    n = 0
    for m in pos.legal_moves():
        n += perft(pos.push(m), depth - 1)
    return n
