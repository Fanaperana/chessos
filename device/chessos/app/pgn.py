"""PGN reading/writing for puzzles.

A puzzle PGN is a normal PGN game with a [FEN] header. The side to move in
the FEN solves the puzzle, unless the header [Premove "1"] is present: then
the first move is the opponent's move that sets the puzzle up (Lichess style)
and is auto-played. After every solver move the opponent reply is played.
"""
import re

from .chess import Position, START_FEN, uci

_HEADER = re.compile(r'^\s*\[(\w+)\s+"(.*)"\s*\]\s*$')
_RESULT = ("1-0", "0-1", "1/2-1/2", "*")


def _strip_movetext(text):
    out, depth, i = [], 0, 0
    while i < len(text):
        c = text[i]
        if c == "{":
            j = text.find("}", i)
            i = len(text) if j < 0 else j + 1
            continue
        if c == ";":
            j = text.find("\n", i)
            i = len(text) if j < 0 else j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(c)
        i += 1
    tokens = []
    for tok in "".join(out).split():
        tok = re.sub(r"^\d+\.(\.\.)?", "", tok)
        if not tok or tok.startswith("$") or tok in _RESULT or re.match(r"^\d+\.*$", tok):
            continue
        tokens.append(tok)
    return tokens


def read_games(text):
    """Yield (headers, san_tokens) for each game in PGN text."""
    headers, moves, in_moves = {}, [], False
    for line in text.splitlines():
        m = _HEADER.match(line)
        if m:
            if in_moves:
                yield headers, _strip_movetext(" ".join(moves))
                headers, moves, in_moves = {}, [], False
            headers[m.group(1)] = m.group(2)
        elif line.strip():
            in_moves = True
            moves.append(line)
    if headers or moves:
        yield headers, _strip_movetext(" ".join(moves))


class Puzzle(object):
    def __init__(self, fen, moves, premove=False, rating=0, themes="", pid="", title="", source="", sans=None):
        self.fen = fen
        self._moves = moves  # list of uci strings, full line incl. premove
        self._sans = sans    # SAN tokens, converted on first use (fast loading)
        self.premove = premove
        self.rating = rating
        self.themes = themes
        self.id = pid
        self.title = title
        self.source = source

    @property
    def moves(self):
        if self._moves is None:
            pos = self.start()
            out = []
            for t in self._sans:
                m = pos.parse_san(t)
                out.append(uci(m))
                pos = pos.push(m)
            self._moves = out
        return self._moves

    def valid(self):
        try:
            return len(self.moves) > 0
        except Exception as e:
            print("bad puzzle", self.id, e)
            return False

    def start(self):
        return Position.from_fen(self.fen)

    def solver(self):
        side = self.start().turn
        if self.premove:
            side = "b" if side == "w" else "w"
        return side

    def to_pgn(self):
        pos = self.start()
        sans = []
        for u in self.moves:
            m = pos.parse_uci(u)
            num = pos.fullmove
            if pos.turn == "w":
                sans.append("%d. %s" % (num, pos.san(m)))
            elif not sans:
                sans.append("%d... %s" % (num, pos.san(m)))
            else:
                sans.append(pos.san(m))
            pos = pos.push(m)
        h = [("Event", self.title or "Puzzle"), ("Site", self.source or "?"), ("FEN", self.fen), ("SetUp", "1")]
        if self.premove:
            h.append(("Premove", "1"))
        if self.rating:
            h.append(("Rating", str(self.rating)))
        if self.themes:
            h.append(("Themes", self.themes))
        if self.id:
            h.append(("PuzzleId", self.id))
        return "\n".join('[%s "%s"]' % kv for kv in h) + "\n\n" + " ".join(sans) + " *\n"


def puzzles_from_pgn(text, source="", lazy=True):
    """Parse puzzles. With lazy=True moves are only checked when a puzzle is played."""
    out = []
    for headers, tokens in read_games(text):
        try:
            fen = headers.get("FEN", START_FEN)
            if not tokens:
                continue
            p = Puzzle(
                fen, None, sans=tokens,
                premove=headers.get("Premove", "0") == "1",
                rating=int(headers.get("Rating", "0") or 0),
                themes=headers.get("Themes", ""),
                pid=headers.get("PuzzleId", headers.get("Site", "")),
                title=headers.get("Event", ""),
                source=source or headers.get("Site", ""),
            )
            if lazy or p.valid():
                out.append(p)
        except Exception as e:  # skip broken games, keep the rest
            print("PGN skip:", e)
    return out
