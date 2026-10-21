"""Write a demo save (two months of activity) for README screenshots."""
import datetime
import json
import random
import sys

out = sys.argv[1]
rnd = random.Random(36)
today = datetime.date.today()
xp = {}
for i in range(1, 121):
    d = today - datetime.timedelta(days=i)
    if i < 24 or rnd.random() < 0.55:
        xp[d.isoformat()] = rnd.choice([10, 15, 20, 25, 30, 45, 60])
lessons = {l: {"crowns": c, "plays": c} for l, c in
           [("rook", 3), ("bishop", 2), ("queen", 2), ("king", 1), ("knight", 1), ("pawn", 1), ("check", 1)]}
data = {
    "version": 1, "xp_by_day": xp, "lessons": lessons,
    "daily_done": {(today - datetime.timedelta(days=i)).isoformat(): "x" for i in range(1, 9)},
    "puzzles_solved": 214, "lessons_done": 19, "practice_rating": 1184, "practice_seen": [],
    "day_offset": 0, "last_seen": today.isoformat(),
    "settings": {"voice": True, "sfx": True, "goal": 20, "board": "ice", "swap_ab": False, "fps": False,
                 "theme": "midnight", "pieces": "soft"},
}
with open(out, "w") as f:
    json.dump(data, f)
print("demo save:", len(xp), "active days")
