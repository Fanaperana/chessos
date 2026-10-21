"""Build ChessOS puzzle packs (PGN) from the Lichess puzzle database (CC0).

Input : build/puzzles_part.csv  (decompressed part of lichess_db_puzzle.csv.zst)
Output: device/chessos/data/puzzles/<lesson>.pgn, daily.pgn, practice.pgn
"""
import csv
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "device", "chessos"))

from app.content import PUZZLE_RULES  # noqa: E402
from app.pgn import Puzzle  # noqa: E402

SRC = os.path.join(ROOT, "build", "puzzles_part.csv")
OUT = os.path.join(ROOT, "device", "chessos", "data", "puzzles")
PER_LESSON = 45
DAILY = 400
PRACTICE = 1500


def good(r, min_pop=85):
    return int(r["Popularity"]) >= min_pop and int(r["NbPlays"]) >= 300 and int(r["RatingDeviation"]) <= 90


def to_puzzle(r):
    return Puzzle(r["FEN"], r["Moves"].split(), premove=True, rating=int(r["Rating"]),
                  themes=r["Themes"], pid=r["PuzzleId"], title="Lichess puzzle " + r["PuzzleId"],
                  source="https://lichess.org/training/" + r["PuzzleId"])


def spread(rows, n):
    rows = sorted(rows, key=lambda r: int(r["Rating"]))
    if len(rows) <= n:
        return rows
    step = len(rows) / float(n)
    return [rows[int(i * step)] for i in range(n)]


def write(name, rows):
    texts = []
    for r in rows:
        try:
            texts.append(to_puzzle(r).to_pgn())
        except Exception as e:
            print("skip", r["PuzzleId"], e)
    with open(os.path.join(OUT, name + ".pgn"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(texts))
    return len(texts)


DB_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"


def fetch(nbytes=12000000):
    """Download the start of the Lichess puzzle DB (CC0) and decompress what we got."""
    import urllib.request
    import zstandard
    print("downloading the first %d MB of %s" % (nbytes // 1000000, DB_URL))
    req = urllib.request.Request(DB_URL, headers={"Range": "bytes=0-%d" % nbytes, "User-Agent": "ChessOS-build"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    reader = zstandard.ZstdDecompressor().stream_reader(__import__("io").BytesIO(raw))
    out = b""
    try:
        while True:
            chunk = reader.read(1 << 20)
            if not chunk:
                break
            out += chunk
    except zstandard.ZstdError:
        pass  # the download stops mid-frame on purpose
    lines = out.decode("utf-8", "ignore").split("\n")[:-1]  # drop the partial last line
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("puzzles in sample:", len(lines) - 1)


def main():
    if not os.path.exists(SRC):
        fetch()
    os.makedirs(OUT, exist_ok=True)
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    print("rows", len(rows))
    used = set()
    for lid, rule in PUZZLE_RULES.items():
        lo, hi = rule["rating"]
        cand = []
        for r in rows:
            th = set(r["Themes"].split())
            if not good(r) or r["PuzzleId"] in used:
                continue
            if not lo <= int(r["Rating"]) <= hi:
                continue
            if not all(t in th for t in rule.get("all", [])):
                continue
            if rule.get("any") and not any(t in th for t in rule["any"]):
                continue
            if len(r["Moves"].split()) > 8:
                continue
            cand.append(r)
        pick = spread(cand, PER_LESSON)
        used.update(r["PuzzleId"] for r in pick)
        print(lid, len(cand), "->", write(lid, pick))

    daily = [r for r in rows if r.get("DailyDate")]
    daily.sort(key=lambda r: int(r["DailyDate"]))
    rnd = random.Random(2026)
    pool = [r for r in rows if good(r, 90) and 1200 <= int(r["Rating"]) <= 1900
            and len(r["Moves"].split()) <= 6 and r["PuzzleId"] not in used and not r.get("DailyDate")]
    rnd.shuffle(pool)
    daily += pool[:DAILY - len(daily)]
    used.update(r["PuzzleId"] for r in daily)
    print("daily ->", write("daily", daily))

    pool = [r for r in rows if good(r) and 500 <= int(r["Rating"]) <= 2300
            and len(r["Moves"].split()) <= 8 and r["PuzzleId"] not in used]
    rnd.shuffle(pool)
    print("practice ->", write("practice", spread(pool[:20000], PRACTICE)))


if __name__ == "__main__":
    main()
