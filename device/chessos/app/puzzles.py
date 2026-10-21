"""Puzzle packs, the daily puzzle, practice selection and online download.

Folders (inside the chessos folder on the SD card):
  data/puzzles/*.pgn     bundled packs (Lichess puzzle database, CC0)
  puzzles/daily/*.pgn    downloaded daily puzzles, one file per date
  puzzles/custom/*.pgn   drop your own PGN puzzles here (FEN header + moves)
"""
import glob
import json
import os
import random
import threading

from .chess import Position, START_FEN, uci
from .pgn import Puzzle, puzzles_from_pgn, read_games

LESSON_SIZE = 5
BAND = 15


class Puzzles(object):
    def __init__(self, base_dir):
        self.base = base_dir
        self.packs = {}
        self.user_dir = os.path.join(base_dir, "puzzles")
        for sub in ("daily", "custom"):
            try:
                os.makedirs(os.path.join(self.user_dir, sub), exist_ok=True)
            except OSError:
                pass
        self.download_state = None  # None | "running" | "ok" | "fail"
        self.download_msg = ""

    def pack(self, name):
        p = self.packs.get(name)
        if p is None:
            path = os.path.join(self.base, "data", "puzzles", name + ".pgn")
            try:
                with open(path, encoding="utf-8") as f:
                    p = puzzles_from_pgn(f.read(), source=name)
            except IOError:
                p = []
            self.packs[name] = p
        return p

    def custom(self):
        out = []
        for path in sorted(glob.glob(os.path.join(self.user_dir, "custom", "*.pgn"))):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    out += puzzles_from_pgn(f.read(), source=os.path.basename(path))
            except IOError:
                pass
        return out

    # ---- lessons -------------------------------------------------------------------
    def for_lesson(self, lid, crowns, plays):
        pool = sorted(self.pack(lid), key=lambda p: p.rating)
        if not pool:
            return []
        band = min(crowns, max(0, len(pool) // BAND - 1))
        sub = pool[band * BAND:(band + 1) * BAND] or pool
        off = (plays * LESSON_SIZE) % len(sub)
        picked = (sub[off:] + sub[:off])[:LESSON_SIZE]
        picked = [p for p in picked if p.valid()]
        picked.sort(key=lambda p: p.rating)
        return picked

    # ---- daily -----------------------------------------------------------------------
    def daily_path(self, date):
        return os.path.join(self.user_dir, "daily", date.isoformat() + ".pgn")

    def daily(self, date):
        path = self.daily_path(date)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    ps = [p for p in puzzles_from_pgn(f.read(), source="Lichess daily") if p.valid()]
                if ps:
                    ps[0].title = "Lichess daily puzzle"
                    return ps[0], True
            except IOError:
                pass
        pack = self.pack("daily")
        if not pack:
            return None, False
        p = pack[date.toordinal() % len(pack)]
        return p, False

    def download_daily(self, date):
        """Fetch today's Lichess daily puzzle in a background thread, save as PGN."""
        if self.download_state == "running":
            return
        self.download_state = "running"
        t = threading.Thread(target=self._download, args=(date,))
        t.daemon = True
        t.start()

    def _download(self, date):
        try:
            try:
                from urllib.request import Request, urlopen
            except ImportError:
                raise RuntimeError("no urllib")
            req = Request("https://lichess.org/api/puzzle/daily",
                          headers={"Accept": "application/json", "User-Agent": "ChessOS/0.1 (R36S)"})
            data = json.loads(urlopen(req, timeout=8).read().decode("utf-8"))
            puzzle = lichess_to_puzzle(data)
            with open(self.daily_path(date), "w", encoding="utf-8") as f:
                f.write(puzzle.to_pgn())
            self.download_state = "ok"
            self.download_msg = "Downloaded puzzle %s" % puzzle.id
        except Exception as e:
            self.download_state = "fail"
            self.download_msg = "Download failed: %s" % (str(e)[:60])

    # ---- practice --------------------------------------------------------------------------
    def practice_next(self, rating, seen):
        pool = self.pack("practice") + self.custom()
        seen = set(seen)
        cand = [p for p in pool if p.id not in seen] or pool
        if not cand:
            return None
        cand.sort(key=lambda p: abs((p.rating or rating) - rating))
        choice = random.choice(cand[:12])
        return choice if choice.valid() else None


def lichess_to_puzzle(data):
    """Convert Lichess /api/puzzle/daily JSON to a Premove-style Puzzle."""
    game, pz = data["game"], data["puzzle"]
    tokens = []
    for _, toks in read_games(game["pgn"]):
        tokens = toks
    solution = pz["solution"]
    ply = int(pz.get("initialPly", len(tokens) - 1))
    for n in (len(tokens), ply + 1, ply):
        pos = Position.from_fen(START_FEN)
        hist = []
        try:
            for t in tokens[:n]:
                m = pos.parse_san(t)
                hist.append((pos.fen(), uci(m)))
                pos = pos.push(m)
            pos.parse_uci(solution[0])
        except ValueError:
            continue
        if not hist:
            continue
        fen, last = hist[-1]
        return Puzzle(fen, [last] + list(solution), premove=True, rating=pz.get("rating", 0),
                      themes=" ".join(pz.get("themes", [])), pid=pz["id"], title="Lichess daily puzzle",
                      source="https://lichess.org/training/" + pz["id"])
    raise ValueError("could not rebuild puzzle position")
