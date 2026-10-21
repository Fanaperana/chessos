"""Save data: XP per day (for the GitHub-style grid), streaks, lessons, settings.

The R36S has no real-time-clock battery, so the system date can be wrong after
a reboot. We keep a user-adjustable day offset and the last date seen.
"""
import datetime
import json
import os

DEFAULT = {
    "version": 1,
    "xp_by_day": {},          # "YYYY-MM-DD": xp
    "lessons": {},            # lesson_id: {"crowns": n, "plays": n}
    "daily_done": {},         # "YYYY-MM-DD": puzzle id
    "puzzles_solved": 0,
    "lessons_done": 0,
    "practice_rating": 900,
    "practice_seen": [],
    "day_offset": 0,
    "last_seen": "",
    "settings": {"voice": True, "sfx": True, "goal": 20, "board": "green", "swap_ab": False, "fps": False},
}

MAX_CROWNS = 3


def parse_date(s):
    """YYYY-MM-DD -> date (works on Python 3.6, unlike date.fromisoformat)."""
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


def build_date():
    """The day this ChessOS build was made (data/build.json). A clock earlier
    than that is certainly wrong - the R36S boots with the ArkOS image's date."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "build.json")
    try:
        with open(path) as f:
            return parse_date(json.load(f)["date"])
    except Exception:
        return datetime.date(2025, 1, 1)


class Progress(object):
    def __init__(self, path):
        self.path = path
        self.data = json.loads(json.dumps(DEFAULT))
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k == "settings":
                    self.data["settings"].update(v)
                else:
                    self.data[k] = v
        except Exception:
            pass

    def save(self):
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1)
        os.replace(tmp, self.path)

    # ---- dates -------------------------------------------------------------------
    def today(self):
        return datetime.date.today() + datetime.timedelta(days=self.data.get("day_offset", 0))

    def clock_suspicious(self):
        """True if the device clock looks wrong (no RTC on the R36S)."""
        t = self.today()
        if t.year < 2025 or t < build_date():
            return True
        last = self.data.get("last_seen")
        if last:
            try:
                if t < parse_date(last):
                    return True
            except ValueError:
                pass
        return False

    def set_today(self, date):
        self.data["day_offset"] = (date - datetime.date.today()).days
        self.mark_seen()

    def mark_seen(self):
        self.data["last_seen"] = self.today().isoformat()
        self.save()

    # ---- xp & streaks ------------------------------------------------------------
    def xp_on(self, date):
        return self.data["xp_by_day"].get(date.isoformat(), 0)

    def xp_today(self):
        return self.xp_on(self.today())

    def total_xp(self):
        return sum(self.data["xp_by_day"].values())

    def add_xp(self, xp):
        """Add XP for today. Returns True if this extended the streak (first XP today)."""
        key = self.today().isoformat()
        first = self.data["xp_by_day"].get(key, 0) == 0
        self.data["xp_by_day"][key] = self.data["xp_by_day"].get(key, 0) + int(xp)
        self.save()
        return first

    def streak(self):
        d = self.today()
        if self.xp_on(d) == 0:
            d -= datetime.timedelta(days=1)
        n = 0
        while self.xp_on(d) > 0:
            n += 1
            d -= datetime.timedelta(days=1)
        return n

    def longest_streak(self):
        days = sorted(parse_date(k) for k, v in self.data["xp_by_day"].items() if v > 0)
        best = cur = 0
        prev = None
        for d in days:
            cur = cur + 1 if prev and (d - prev).days == 1 else 1
            best = max(best, cur)
            prev = d
        return best

    def goal(self):
        return self.data["settings"].get("goal", 20)

    # ---- lessons -----------------------------------------------------------------
    def crowns(self, lid):
        return self.data["lessons"].get(lid, {}).get("crowns", 0)

    def plays(self, lid):
        return self.data["lessons"].get(lid, {}).get("plays", 0)

    def complete_lesson(self, lid):
        rec = self.data["lessons"].setdefault(lid, {"crowns": 0, "plays": 0})
        rec["plays"] = rec.get("plays", 0) + 1
        rec["crowns"] = min(MAX_CROWNS, rec.get("crowns", 0) + 1)
        self.data["lessons_done"] += 1
        self.save()

    def setting(self, key):
        return self.data["settings"].get(key, DEFAULT["settings"].get(key))

    def set_setting(self, key, value):
        self.data["settings"][key] = value
        self.save()

    def reset(self):
        keep = dict(self.data["settings"])
        self.data = json.loads(json.dumps(DEFAULT))
        self.data["settings"] = keep
        self.save()
