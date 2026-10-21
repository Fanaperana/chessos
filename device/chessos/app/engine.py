"""Stockfish over UCI, non-blocking (a reader thread updates the current search).

    eng = Engine.find(base_dir)       # None if no binary is available
    s = eng.search(fen, movetime=800)  # returns immediately
    ... every frame: if s.done: s.bestmove, s.cp, s.mate, s.depth
"""
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time

MATE_CP = 10000


class Search(object):
    __slots__ = ("fen", "done", "bestmove", "cp", "mate", "depth", "pv", "started", "kind")

    def __init__(self, fen, kind=""):
        self.fen = fen
        self.kind = kind
        self.done = False
        self.bestmove = None
        self.cp = None      # centipawns, from the side to move's point of view
        self.mate = None    # mate in N (positive: side to move mates)
        self.depth = 0
        self.pv = []
        self.started = time.time()

    def score(self):
        """Single number for the side to move: mates become +-(10000 - N)."""
        if self.mate is not None:
            return (MATE_CP - abs(self.mate)) * (1 if self.mate > 0 else -1)
        return self.cp if self.cp is not None else 0


class Engine(object):
    def __init__(self, path, threads=2, hash_mb=32):
        self.path = path
        flags = 0
        if sys.platform == "win32":
            flags = 0x08000000  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, universal_newlines=True, bufsize=1,
                                     cwd=os.path.dirname(path) or None, creationflags=flags)
        self.lines = queue.Queue()
        self.current = None
        self.name = "engine"
        self.skill = None
        self._ready = threading.Event()
        self._uciok = threading.Event()
        t = threading.Thread(target=self._reader)
        t.daemon = True
        t.start()
        self._send("uci")
        if not self._uciok.wait(15):
            raise RuntimeError("engine did not answer 'uci'")
        self._send("setoption name Threads value %d" % threads)
        self._send("setoption name Hash value %d" % hash_mb)
        self.sync()

    @classmethod
    def find(cls, base_dir, **kw):
        """Locate a bundled or installed Stockfish; returns None if there is none."""
        cands = [os.environ.get("CHESSOS_STOCKFISH")]
        mach = platform.machine().lower()
        if sys.platform == "win32":
            cands.append(os.path.join(base_dir, "bin", "windows", "stockfish.exe"))
        elif mach in ("aarch64", "arm64"):
            cands.append(os.path.join(base_dir, "bin", "linux-aarch64", "stockfish"))
        cands += [shutil.which("stockfish"), "/usr/games/stockfish"]
        for c in cands:
            if c and os.path.exists(c):
                try:
                    if not os.access(c, os.X_OK):
                        os.chmod(c, 0o755)
                    return cls(c, **kw)
                except Exception as e:
                    print("engine: %s failed: %s" % (c, e))
        return None

    # ---- protocol ----------------------------------------------------------------
    def _send(self, line):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line.startswith("id name "):
                self.name = line[8:]
            elif line == "uciok":
                self._uciok.set()
            elif line == "readyok":
                self._ready.set()
            elif line.startswith("info ") and self.current is not None:
                self._info(self.current, line.split())
            elif line.startswith("bestmove") and self.current is not None:
                parts = line.split()
                s = self.current
                s.bestmove = parts[1] if len(parts) > 1 and parts[1] != "(none)" else None
                s.done = True

    @staticmethod
    def _info(s, t):
        if "multipv" in t and t[t.index("multipv") + 1] != "1":
            return
        if "score" not in t or "pv" not in t:
            return
        i = t.index("score")
        kind, val = t[i + 1], int(t[i + 2])
        if "upperbound" in t or "lowerbound" in t:
            return
        if kind == "cp":
            s.cp, s.mate = val, None
        elif kind == "mate":
            s.mate, s.cp = val, None
        if "depth" in t:
            s.depth = int(t[t.index("depth") + 1])
        s.pv = t[t.index("pv") + 1:]

    def sync(self, timeout=10):
        self._ready.clear()
        self._send("isready")
        return self._ready.wait(timeout)

    # ---- API -------------------------------------------------------------------------
    def busy(self):
        return self.current is not None and not self.current.done

    def stop(self, wait=2.0):
        if self.busy():
            self._send("stop")
            end = time.time() + wait
            while self.busy() and time.time() < end:
                time.sleep(0.005)

    def set_skill(self, skill):
        """0-20, None = full strength."""
        level = 20 if skill is None else int(skill)
        if level != self.skill:
            self._send("setoption name Skill Level value %d" % level)
            self.skill = level

    def search(self, fen, movetime=800, depth=None, skill=None, kind=""):
        self.stop()
        self.set_skill(skill)
        s = Search(fen, kind)
        self.current = s
        self._send("position fen " + fen)
        if depth:
            self._send("go depth %d" % depth)
        else:
            self._send("go movetime %d" % movetime)
        return s

    def new_game(self):
        self.stop()
        self._send("ucinewgame")
        self.sync()

    def quit(self):
        try:
            self.stop(0.5)
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
