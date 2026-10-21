"""Headless coach test: a scripted 'player' (mostly good moves, some deliberate
blunders) plays Stockfish; prints every grade and comment.
usage: python tools/coach_selftest.py [plies]
"""
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "device", "chessos")
sys.path.insert(0, BASE)

from app.chess import Position, START_FEN, uci  # noqa: E402
from app.coach import Coach, VALUE  # noqa: E402
from app.engine import Engine  # noqa: E402


def wait(s):
    while not s.done:
        time.sleep(0.005)
    return s


def main(plies=40):
    random.seed(7)
    eng = Engine.find(BASE, threads=4)
    coach = Coach("w")
    pos = Position.from_fen(START_FEN)
    sans = []
    print("engine:", eng.name)
    print("COACH:", coach.start())
    for ply in range(plies):
        if pos.is_checkmate() or pos.is_stalemate():
            break
        if pos.turn == "w":
            ana = wait(eng.search(pos.fen(), movetime=200))
            moves = pos.legal_moves()
            if ply % 7 == 5:   # deliberate blunder: hang the most valuable piece we can
                def badness(m):
                    nxt = pos.push(m)
                    return -VALUE[nxt.board[m.to].upper()] if nxt.attacked(m.to, "b") else 0
                m = min(moves, key=badness)
                tag = "(blunder try)"
            else:
                m = pos.parse_uci(ana.bestmove) if random.random() < 0.7 else random.choice(moves)
                tag = ""
            before = pos
            san = pos.san(m)
            pos = pos.push(m)
            sans.append(san)
            g = wait(eng.search(pos.fen(), movetime=200))
            text, grade = coach.player_move(before, m, pos, ana.score(), -g.score(), ana.bestmove, sans, g.bestmove)
            print("%2d. you %-7s %-10s %-11s eval %+5d -> %+5d  %s" % (ply // 2 + 1, san, tag, grade,
                  ana.score(), -g.score(), text or ""))
        else:
            r = wait(eng.search(pos.fen(), movetime=100, skill=5))
            m = pos.parse_uci(r.bestmove)
            before = pos
            san = pos.san(m)
            pos = pos.push(m)
            sans.append(san)
            text = coach.engine_move(before, m, pos)
            print("            coach %-7s %s" % (san, text or ""))
    print("accuracy %.0f%%  stats %s" % (coach.accuracy(), coach.stats))
    eng.quit()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
