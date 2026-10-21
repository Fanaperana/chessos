"""ChessOS main loop and scene manager."""
import ctypes
import os
import time

import sdl2

from . import motion
from .audio import Audio
from .gfx import Gfx
from .inputs import Input
from .progress import Progress
from .puzzles import Puzzles
from .ui import BG


class Scene(object):
    opaque = True

    def __init__(self, app):
        self.app = app
        self.g = app.g

    def enter(self):
        pass

    def update(self, dt, actions):
        pass

    def draw(self, g, dt):
        pass

    def resume(self):
        """Called when the scene above this one is closed."""
        pass


class App(object):
    def __init__(self, base, device=False):
        self.base = base
        self.device = device
        print("ChessOS: SDL video")
        self.g = Gfx(device=device, scale=int(os.environ.get("CHESSOS_SCALE", "2")))
        print("ChessOS: input")
        self.input = Input(base)
        print("ChessOS: audio")
        self.audio = Audio(base)
        print("ChessOS: data")
        self.progress = Progress(os.environ.get("CHESSOS_SAVE") or os.path.join(base, "save", "save.json"))
        self.puzzles = Puzzles(base)
        self.stack = []
        self.fade = motion.Value(0)
        self.pending = None
        self.running = True
        self.exit_code = 0
        self.frontend = os.environ.get("CHESSOS_FRONTEND") == "1"
        self.fps = 0.0
        self.show_fps = os.environ.get("CHESSOS_FPS") == "1"
        # test autopilot: CHESSOS_AUTOPILOT="2|shot:home|down|a|0.5|shot:pop|quit"
        ap = os.environ.get("CHESSOS_AUTOPILOT")
        self.autopilot = [s.strip() for s in ap.split("|") if s.strip()] if ap else None
        self.ap_next = 0.0
        self.shot_dir = os.environ.get("CHESSOS_SHOTS", os.path.join(base, "shots"))
        self.apply_settings()

    def apply_settings(self):
        p = self.progress
        self.audio.voice_on = p.setting("voice")
        self.audio.sfx_on = p.setting("sfx")
        self.input.swap_ab = p.setting("swap_ab")
        self.show_fps = bool(p.setting("fps")) or os.environ.get("CHESSOS_FPS") == "1"

    # ---- scenes --------------------------------------------------------------------
    def _do(self, op, scene):
        if op == "push":
            self.stack.append(scene)
        elif op == "replace":
            if self.stack:
                self.stack.pop()
            self.stack.append(scene)
        elif op == "pop":
            if len(self.stack) > 1:
                self.stack.pop()
                self.stack[-1].resume()
        elif op == "reset":
            self.stack = [scene]
        if scene is not None:
            scene.enter()

    def go(self, op, scene=None, fade=True):
        if not fade:
            self._do(op, scene)
            return
        self.pending = (op, scene)
        self.fade.tween(1, 0.16, "easeIn")

    def push(self, scene, fade=False):
        self.go("push", scene, fade)

    def pop(self, fade=False):
        self.go("pop", None, fade)

    def replace(self, scene, fade=True):
        self.go("replace", scene, fade)

    def reset(self, scene, fade=True):
        self.go("reset", scene, fade)

    def quit(self):
        self.running = False

    def autopilot_step(self, t):
        if t < self.ap_next or not self.autopilot:
            return []
        if self.pending:
            return []
        step = self.autopilot.pop(0)
        self.ap_next = t + 0.12
        try:
            self.ap_next = t + float(step)
            return []
        except ValueError:
            pass
        if step.startswith("shot:"):
            self.want_shot = step[5:]
            return []
        if step == "quit":
            self.running = False
            return []
        if step.startswith("eval:"):
            exec(step[5:], {"app": self})
            return []
        return [step]

    def screenshot(self, name):
        os.makedirs(self.shot_dir, exist_ok=True)
        w, h = ctypes.c_int(), ctypes.c_int()
        sdl2.SDL_GetRendererOutputSize(self.g.ren, ctypes.byref(w), ctypes.byref(h))
        surf = sdl2.SDL_CreateRGBSurfaceWithFormat(0, w.value, h.value, 32, sdl2.SDL_PIXELFORMAT_ARGB8888)
        sdl2.SDL_RenderReadPixels(self.g.ren, None, sdl2.SDL_PIXELFORMAT_ARGB8888, surf.contents.pixels, surf.contents.pitch)
        sdl2.SDL_SaveBMP(surf, os.path.join(self.shot_dir, name + ".bmp").encode("utf-8"))
        sdl2.SDL_FreeSurface(surf)

    # ---- loop ------------------------------------------------------------------------
    def run(self, first):
        motion.tick(time.perf_counter())
        self._do("reset", first)
        ev = sdl2.SDL_Event()
        last = time.perf_counter()
        frame = 1.0 / 60
        while self.running:
            t = time.perf_counter()
            dt = min(0.05, t - last)
            last = t
            if dt > 0:
                self.fps = self.fps * 0.95 + (1.0 / dt) * 0.05
            motion.tick(t)
            while sdl2.SDL_PollEvent(ctypes.byref(ev)):
                self.input.handle(ev)
            self.input.update(dt)
            actions = self.input.take()
            if self.autopilot is not None:
                actions += self.autopilot_step(t)
            if self.input.quit or "quit_combo" in actions:
                break
            if self.pending:
                actions = []
                if not self.fade.animating and self.fade.get() >= 0.99:
                    op, scene = self.pending
                    self.pending = None
                    self._do(op, scene)
                    self.fade.tween(0, 0.22, "easeOut")
            if self.stack:
                self.stack[-1].update(dt, actions)
            self.audio.update()
            self.draw(dt)
            spent = time.perf_counter() - t
            if spent < frame:
                sdl2.SDL_Delay(int((frame - spent) * 1000))
        self.progress.save()
        self.audio.quit()
        self.g.quit()

    def draw(self, dt):
        g = self.g
        g.clear(BG)
        start = 0
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].opaque:
                start = i
                break
        for s in self.stack[start:]:
            s.draw(g, dt)
        f = self.fade.get()
        if f > 0.001:
            g.rect(0, 0, 640, 480, BG, f)
        if self.show_fps:
            g.text("%d fps" % self.fps, 636, 462, 12, (255, 255, 0), 800, align="r")
        shot = getattr(self, "want_shot", None)
        if shot:
            self.want_shot = None
            self.screenshot(shot)
        g.present()
        if not getattr(self, "_first_frame", False):
            self._first_frame = True
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
            print("ChessOS: first frame shown")
