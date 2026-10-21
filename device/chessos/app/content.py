"""ChessOS course content: units, lessons and spoken phrases.

Lesson kinds:
  stars   - move one piece around to collect stars (and capture targets)
  check   - find any move that gives check
  puzzles - solve puzzles from data/puzzles/<id>.pgn (built by tools/build_puzzles.py)

Every string in `intro`, `PHRASES` etc. gets a pre-rendered voice clip.
"""

UNITS = [
    {
        "id": "u1", "title": "Meet the pieces", "color": "green",
        "blurb": "Learn how every piece moves",
        "lessons": [
            {"id": "rook", "title": "The Rook", "icon": "R", "kind": "stars",
             "intro": "The rook moves in straight lines. Up, down, left and right, as far as it likes. Collect all the stars!",
             "levels": [
                 {"piece": "R", "at": "d2", "stars": ["d6"]},
                 {"piece": "R", "at": "a1", "stars": ["a6", "f6"]},
                 {"piece": "R", "at": "h1", "stars": ["h5", "c5", "c8", "g8"]},
                 {"piece": "R", "at": "e4", "stars": ["b4", "b7", "g7", "g2"], "targets": {"e7": "p"}},
             ]},
            {"id": "bishop", "title": "The Bishop", "icon": "B", "kind": "stars",
             "intro": "The bishop moves diagonally, as far as it likes. It always stays on the same colour. Collect all the stars!",
             "levels": [
                 {"piece": "B", "at": "c1", "stars": ["g5"]},
                 {"piece": "B", "at": "f1", "stars": ["b5", "e8"]},
                 {"piece": "B", "at": "a1", "stars": ["d4", "g1", "h2"]},
                 {"piece": "B", "at": "e3", "stars": ["h6", "f8", "a3"], "targets": {"c5": "n"}},
             ]},
            {"id": "queen", "title": "The Queen", "icon": "Q", "kind": "stars",
             "intro": "The queen is the strongest piece. She moves like a rook and a bishop together. Collect all the stars!",
             "levels": [
                 {"piece": "Q", "at": "d1", "stars": ["d6", "h6"]},
                 {"piece": "Q", "at": "a8", "stars": ["h1", "h8", "a1"]},
                 {"piece": "Q", "at": "e4", "stars": ["b7", "g7", "c3", "c8"], "targets": {"g2": "r"}},
             ]},
            {"id": "king", "title": "The King", "icon": "K", "kind": "stars",
             "intro": "The king is slow. He moves just one square in any direction. Keep him safe! Collect all the stars.",
             "levels": [
                 {"piece": "K", "at": "e1", "stars": ["e2", "e3"]},
                 {"piece": "K", "at": "d4", "stars": ["e5", "e6", "d7", "c6"]},
                 {"piece": "K", "at": "a1", "stars": ["b2", "c3", "c2"], "targets": {"d3": "p"}},
             ]},
            {"id": "knight", "title": "The Knight", "icon": "N", "kind": "stars",
             "intro": "The knight jumps in an L shape. Two squares one way, then one square to the side. It can jump over pieces! Collect all the stars.",
             "levels": [
                 {"piece": "N", "at": "b1", "stars": ["c3"]},
                 {"piece": "N", "at": "g1", "stars": ["f3", "e5", "c6"]},
                 {"piece": "N", "at": "a1", "stars": ["b3", "c5", "d7", "f8"]},
                 {"piece": "N", "at": "e4", "stars": ["g5", "e6", "c7"], "targets": {"d5": "p", "f5": "p"}},
             ]},
            {"id": "pawn", "title": "The Pawn", "icon": "P", "kind": "stars",
             "intro": "Pawns march forward one square. On their first move they can jump two. They capture diagonally. Reach the last row to promote!",
             "levels": [
                 {"piece": "P", "at": "e2", "stars": ["e4", "e5"]},
                 {"piece": "P", "at": "d2", "stars": ["d4"], "targets": {"e5": "p", "f6": "n"}},
                 {"piece": "P", "at": "c6", "stars": ["c8"]},
                 {"piece": "P", "at": "a5", "stars": [], "targets": {"b6": "p", "a7": "n", "b8": "r"}},
             ]},
        ],
    },
    {
        "id": "u2", "title": "Check and mate", "color": "blue",
        "blurb": "Attack the king and win the game",
        "lessons": [
            {"id": "check", "title": "Give check", "icon": "check", "kind": "check",
             "intro": "A check is an attack on the king. Find a move that puts the black king in check!",
             "positions": [
                 "4k3/8/8/8/8/8/8/R3K3 w - - 0 1",
                 "6k1/8/8/8/8/8/8/1B4K1 w - - 0 1",
                 "4k3/8/8/3N4/8/8/8/4K3 w - - 0 1",
                 "2k5/8/8/8/8/8/8/3QK3 w - - 0 1",
                 "r3k3/ppp5/8/8/8/8/5PPP/3R2K1 w - - 0 1",
             ]},
            {"id": "mate1", "title": "Mate in one", "icon": "K", "kind": "puzzles",
             "intro": "Checkmate wins the game. The king is in check and cannot escape. Find the checkmate in one move!"},
            {"id": "backrank", "title": "Back rank mate", "icon": "R", "kind": "puzzles",
             "intro": "A king trapped behind its own pawns is in danger. Strike on the back rank!"},
            {"id": "mate1b", "title": "Mate in one II", "icon": "Q", "kind": "puzzles",
             "intro": "More checkmates in one. Look at every check before you move!"},
        ],
    },
    {
        "id": "u3", "title": "Tactics", "color": "purple",
        "blurb": "Win material with clever tricks",
        "lessons": [
            {"id": "hanging", "title": "Free pieces", "icon": "P", "kind": "puzzles",
             "intro": "Sometimes your opponent leaves a piece unprotected. Find it and take it!"},
            {"id": "fork", "title": "Forks", "icon": "N", "kind": "puzzles",
             "intro": "A fork attacks two pieces at once. Your opponent can only save one!"},
            {"id": "pin", "title": "Pins", "icon": "B", "kind": "puzzles",
             "intro": "A pinned piece cannot move without exposing something more valuable behind it."},
            {"id": "skewer", "title": "Skewers", "icon": "R", "kind": "puzzles",
             "intro": "A skewer attacks a valuable piece. When it moves away, you win the piece behind it."},
            {"id": "discovered", "title": "Discovered attacks", "icon": "Q", "kind": "puzzles",
             "intro": "Move one piece out of the way to unleash an attack from another!"},
        ],
    },
    {
        "id": "u4", "title": "Attack!", "color": "orange",
        "blurb": "Combinations and sacrifices",
        "lessons": [
            {"id": "mate2", "title": "Mate in two", "icon": "K", "kind": "puzzles",
             "intro": "Find a checkmate in two moves. Think about what your opponent will do."},
            {"id": "sacrifice", "title": "Sacrifices", "icon": "Q", "kind": "puzzles",
             "intro": "Sometimes you must give something up to win something bigger. Be brave!"},
            {"id": "deflection", "title": "Deflection", "icon": "B", "kind": "puzzles",
             "intro": "Lure a defender away from its job, then strike."},
            {"id": "promotion", "title": "Promotion", "icon": "P", "kind": "puzzles",
             "intro": "Push your pawn to the last row and turn it into a queen!"},
        ],
    },
    {
        "id": "u5", "title": "Endgames", "color": "red",
        "blurb": "Finish the game like a master",
        "lessons": [
            {"id": "pawnend", "title": "Pawn endgames", "icon": "P", "kind": "puzzles",
             "intro": "In pawn endgames every tempo counts. Find the winning plan."},
            {"id": "rookend", "title": "Rook endgames", "icon": "R", "kind": "puzzles",
             "intro": "Rook endgames are the most common endgames. Activate your rook!"},
            {"id": "mate3", "title": "Mate in three", "icon": "K", "kind": "puzzles",
             "intro": "A checkmate in three moves. Calculate carefully!"},
            {"id": "zugzwang", "title": "Zugzwang", "icon": "K", "kind": "puzzles",
             "intro": "Zugzwang means your opponent must move, and every move makes things worse."},
        ],
    },
]

# Puzzle selection rules used by tools/build_puzzles.py
PUZZLE_RULES = {
    "mate1":      {"all": ["mateIn1"], "rating": (400, 1100)},
    "backrank":   {"all": ["backRankMate"], "any": ["mateIn1", "mateIn2"], "rating": (500, 1500)},
    "mate1b":     {"all": ["mateIn1"], "rating": (1100, 1700)},
    "hanging":    {"all": ["hangingPiece"], "any": ["oneMove", "short"], "rating": (500, 1400)},
    "fork":       {"all": ["fork"], "any": ["short", "oneMove"], "rating": (600, 1600)},
    "pin":        {"all": ["pin"], "any": ["short", "oneMove"], "rating": (700, 1700)},
    "skewer":     {"all": ["skewer"], "rating": (700, 1700)},
    "discovered": {"all": ["discoveredAttack"], "any": ["short", "oneMove"], "rating": (800, 1800)},
    "mate2":      {"all": ["mateIn2"], "rating": (700, 1700)},
    "sacrifice":  {"all": ["sacrifice"], "any": ["short", "mate"], "rating": (900, 1900)},
    "deflection": {"all": ["deflection"], "rating": (900, 1900)},
    "promotion":  {"all": ["promotion"], "rating": (700, 1700)},
    "pawnend":    {"all": ["pawnEndgame"], "rating": (700, 1800)},
    "rookend":    {"all": ["rookEndgame"], "any": ["short", "oneMove"], "rating": (800, 1800)},
    "mate3":      {"all": ["mateIn3"], "rating": (900, 2000)},
    "zugzwang":   {"all": ["zugzwang"], "rating": (900, 2000)},
}

COLORS = {
    # name: (main, shade, light)
    "green": ((88, 204, 2), (70, 163, 2), (215, 255, 184)),
    "blue": ((28, 176, 246), (24, 153, 214), (221, 244, 255)),
    "purple": ((206, 130, 255), (165, 104, 204), (243, 224, 255)),
    "orange": ((255, 150, 0), (204, 121, 0), (255, 236, 205)),
    "red": ((255, 75, 75), (234, 43, 43), (255, 223, 224)),
    "gold": ((255, 200, 0), (229, 164, 0), (255, 243, 199)),
}

CORRECT = ["Excellent!", "Great job!", "Nicely done!", "Brilliant!", "You got it!", "Amazing!", "Perfect!"]
WRONG = ["Not quite.", "Try again.", "Oops, not that one.", "Almost! Try another move."]

PHRASES = [
    "Welcome to ChessOS!", "Let's learn chess!",
    "Lesson complete!", "Daily puzzle solved!", "Puzzle solved!",
    "Out of hearts. Let's try again later.",
    "Your move.", "White to move.", "Black to move.",
    "Find the best move for white.", "Find the best move for black.",
    "Collect all the stars!", "Star collected!", "Capture the piece!",
    "Here is a hint.", "The solution was", "Keep going!", "Promote your pawn!",
    "Choose a piece for promotion.",
    "Day streak!", "You extended your streak!", "Daily goal reached!",
    "Daily puzzle downloaded.", "No internet connection. Using the offline puzzle.",
    "Practice mode.", "Goodbye!", "What day is it today?", "Let's play!",
]

WORDS = ["pawn", "knight", "bishop", "rook", "queen", "king", "takes", "check", "checkmate",
         "castles kingside", "castles queenside", "promotes to"]


def all_lessons():
    for u in UNITS:
        for l in u["lessons"]:
            yield u, l


def lesson_by_id(lid):
    for u, l in all_lessons():
        if l["id"] == lid:
            return u, l
    return None, None


def spoken_lines():
    """Every line that gets a pre-rendered voice clip."""
    lines = []
    for u, l in all_lessons():
        lines.append(l["intro"])
        lines.append(l["title"])
    for u in UNITS:
        lines.append(u["title"])
    lines += CORRECT + WRONG + PHRASES + WORDS
    from .coach import static_lines  # the coach's slot-free phrases
    lines += static_lines()
    for f in "abcdefgh":
        for r in "12345678":
            lines.append(f + r)
    for n in range(1, 31):
        lines.append("%d day streak!" % n)
    seen, out = set(), []
    for s in lines:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
