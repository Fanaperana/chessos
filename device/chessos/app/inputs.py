"""Gamepad + keyboard input mapped to ChessOS actions.

Actions: up down left right a b x y l1 r1 l2 r2 start select
R36S (ArkOS) reports a "GO-Super Gamepad"; we use SDL's GameController API with
the bundled gamecontrollerdb.txt and fall back to raw joystick buttons.
"""
import ctypes
import os

import sdl2

DIRS = ("up", "down", "left", "right")

# raw button numbers for the R36S / OGS family (from gamecontrollerdb "GO-Super Gamepad")
RAW_MAP = {1: "a", 0: "b", 2: "x", 3: "y", 4: "l1", 5: "r1", 6: "l2", 7: "r2",
           8: "up", 9: "down", 10: "left", 11: "right", 12: "select", 13: "start"}

CB = {
    sdl2.SDL_CONTROLLER_BUTTON_A: "a", sdl2.SDL_CONTROLLER_BUTTON_B: "b",
    sdl2.SDL_CONTROLLER_BUTTON_X: "x", sdl2.SDL_CONTROLLER_BUTTON_Y: "y",
    sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: "l1", sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: "r1",
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: "up", sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: "down",
    sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: "left", sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: "right",
    sdl2.SDL_CONTROLLER_BUTTON_START: "start", sdl2.SDL_CONTROLLER_BUTTON_BACK: "select",
    sdl2.SDL_CONTROLLER_BUTTON_GUIDE: "select",
}

KEYS = {
    sdl2.SDLK_UP: "up", sdl2.SDLK_DOWN: "down", sdl2.SDLK_LEFT: "left", sdl2.SDLK_RIGHT: "right",
    sdl2.SDLK_z: "a", sdl2.SDLK_RETURN: "a", sdl2.SDLK_SPACE: "a",
    sdl2.SDLK_x: "b", sdl2.SDLK_BACKSPACE: "b",
    sdl2.SDLK_c: "x", sdl2.SDLK_v: "y",
    sdl2.SDLK_q: "l1", sdl2.SDLK_e: "r1", sdl2.SDLK_1: "l2", sdl2.SDLK_3: "r2",
    sdl2.SDLK_s: "start", sdl2.SDLK_TAB: "select", sdl2.SDLK_ESCAPE: "start",
}


class Input(object):
    REPEAT_DELAY = 0.30
    REPEAT_RATE = 0.085

    def __init__(self, base_dir):
        self.held = set()
        self.pressed = []
        self.quit = False
        self.swap_ab = False
        self.controllers = {}
        self.joysticks = {}
        self.hold_t = {}
        self.axis_state = {}
        db = os.path.join(base_dir, "assets", "gamecontrollerdb.txt")
        env_db = os.environ.get("SDL_GAMECONTROLLERCONFIG_FILE")
        for path in (env_db, db):
            if path and os.path.exists(path):
                rw = sdl2.SDL_RWFromFile(path.encode("utf-8"), b"rb")
                if rw:
                    sdl2.SDL_GameControllerAddMappingsFromRW(rw, 1)
        for i in range(sdl2.SDL_NumJoysticks()):
            self._open(i)

    def _open(self, index):
        if sdl2.SDL_IsGameController(index):
            c = sdl2.SDL_GameControllerOpen(index)
            if c:
                joy = sdl2.SDL_GameControllerGetJoystick(c)
                self.controllers[sdl2.SDL_JoystickInstanceID(joy)] = c
                return
        j = sdl2.SDL_JoystickOpen(index)
        if j:
            self.joysticks[sdl2.SDL_JoystickInstanceID(j)] = j

    def _press(self, act):
        if self.swap_ab and act in ("a", "b"):
            act = "b" if act == "a" else "a"
        if act not in self.held:
            self.held.add(act)
            self.pressed.append(act)
            self.hold_t[act] = 0.0
        if "select" in self.held and "start" in self.held:
            self.pressed.append("quit_combo")

    def _release(self, act):
        if self.swap_ab and act in ("a", "b"):
            act = "b" if act == "a" else "a"
        self.held.discard(act)
        self.hold_t.pop(act, None)

    def _axis(self, key, value, neg, pos):
        state = self.axis_state.get(key)
        new = neg if value < -16000 else pos if value > 16000 else None
        if new != state:
            if state:
                self._release(state)
            if new:
                self._press(new)
            self.axis_state[key] = new

    def handle(self, ev):
        t = ev.type
        if t == sdl2.SDL_QUIT:
            self.quit = True
        elif t == sdl2.SDL_KEYDOWN and not ev.key.repeat:
            act = KEYS.get(ev.key.keysym.sym)
            if act:
                self._press(act)
        elif t == sdl2.SDL_KEYUP:
            act = KEYS.get(ev.key.keysym.sym)
            if act:
                self._release(act)
        elif t == sdl2.SDL_CONTROLLERDEVICEADDED:
            idx = ev.cdevice.which
            self._open(idx)
        elif t == sdl2.SDL_JOYDEVICEADDED:
            if not sdl2.SDL_IsGameController(ev.jdevice.which):
                self._open(ev.jdevice.which)
        elif t == sdl2.SDL_CONTROLLERBUTTONDOWN:
            act = CB.get(ev.cbutton.button)
            if act:
                self._press(act)
        elif t == sdl2.SDL_CONTROLLERBUTTONUP:
            act = CB.get(ev.cbutton.button)
            if act:
                self._release(act)
        elif t == sdl2.SDL_CONTROLLERAXISMOTION:
            a = ev.caxis.axis
            if a == sdl2.SDL_CONTROLLER_AXIS_LEFTX:
                self._axis("lx", ev.caxis.value, "left", "right")
            elif a == sdl2.SDL_CONTROLLER_AXIS_LEFTY:
                self._axis("ly", ev.caxis.value, "up", "down")
            elif a == sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                self._axis("tl", ev.caxis.value, None, "l2")
            elif a == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                self._axis("tr", ev.caxis.value, None, "r2")
        elif t in (sdl2.SDL_JOYBUTTONDOWN, sdl2.SDL_JOYBUTTONUP):
            if ev.jbutton.which in self.controllers:
                return
            act = RAW_MAP.get(ev.jbutton.button)
            if act:
                (self._press if t == sdl2.SDL_JOYBUTTONDOWN else self._release)(act)
        elif t == sdl2.SDL_JOYHATMOTION:
            if ev.jhat.which in self.controllers:
                return
            v = ev.jhat.value
            for bit, act in ((1, "up"), (4, "down"), (8, "left"), (2, "right")):
                (self._press if v & bit else self._release)(act)
        elif t == sdl2.SDL_JOYAXISMOTION:
            if ev.jaxis.which in self.controllers:
                return
            if ev.jaxis.axis == 0:
                self._axis("jx", ev.jaxis.value, "left", "right")
            elif ev.jaxis.axis == 1:
                self._axis("jy", ev.jaxis.value, "up", "down")

    def update(self, dt):
        for act in DIRS:
            if act in self.hold_t:
                t0 = self.hold_t[act]
                t1 = t0 + dt
                self.hold_t[act] = t1
                if t1 >= self.REPEAT_DELAY:
                    n0 = int(max(0.0, t0 - self.REPEAT_DELAY) / self.REPEAT_RATE)
                    n1 = int((t1 - self.REPEAT_DELAY) / self.REPEAT_RATE)
                    if t0 < self.REPEAT_DELAY or n1 > n0:
                        self.pressed.append(act)

    def take(self):
        out, self.pressed = self.pressed, []
        return out
