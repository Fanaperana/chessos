"""SDL2 drawing layer for ChessOS (PySDL2, no SDL_image/SDL_gfx needed)."""
import ctypes
import os
import struct
import zlib
from collections import OrderedDict

import sdl2
import sdl2.sdlttf as ttf

W, H = 640, 480
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "assets")

FONT_FILES = {
    700: "Nunito-700.ttf",
    800: "Nunito-800.ttf",
    900: "Nunito-900.ttf",
    "sym": "DejaVuSans.ttf",
}


class Texture(object):
    __slots__ = ("tex", "w", "h")

    def __init__(self, tex, w, h):
        self.tex, self.w, self.h = tex, w, h

    def destroy(self):
        if self.tex:
            sdl2.SDL_DestroyTexture(self.tex)
            self.tex = None


class Gfx(object):
    def __init__(self, device=False, scale=2):
        sdl2.SDL_SetHint(b"SDL_RENDER_SCALE_QUALITY", b"1")
        sdl2.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
        if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER |
                         sdl2.SDL_INIT_EVENTS | sdl2.SDL_INIT_TIMER) != 0:
            raise RuntimeError("SDL_Init: %s" % sdl2.SDL_GetError())
        if device:
            flags = sdl2.SDL_WINDOW_FULLSCREEN | sdl2.SDL_WINDOW_SHOWN
            ww, wh = W, H
            dm = sdl2.SDL_DisplayMode()
            if sdl2.SDL_GetCurrentDisplayMode(0, ctypes.byref(dm)) == 0 and dm.w > 0:
                ww, wh = dm.w, dm.h
        else:
            flags = sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE
            ww, wh = W * scale, H * scale
        self.window = sdl2.SDL_CreateWindow(b"ChessOS", sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
                                            ww, wh, flags)
        if not self.window:
            raise RuntimeError("SDL_CreateWindow: %s" % sdl2.SDL_GetError())
        self.ren = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_ACCELERATED |
                                           sdl2.SDL_RENDERER_PRESENTVSYNC | sdl2.SDL_RENDERER_TARGETTEXTURE)
        if not self.ren:
            self.ren = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_SOFTWARE)
        sdl2.SDL_RenderSetLogicalSize(self.ren, W, H)
        sdl2.SDL_SetRenderDrawBlendMode(self.ren, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_ShowCursor(0 if device else 1)
        if ttf.TTF_Init() != 0:
            raise RuntimeError("TTF_Init failed")
        self.fonts = {}
        self.text_cache = OrderedDict()
        self.sprites = {}
        self.alpha = 1.0  # global opacity multiplier
        self.ox, self.oy = 0.0, 0.0  # global offset (for screen shake / slides)
        self._has_f = True
        try:
            r = sdl2.SDL_FRect(0, 0, 1, 1)
            sdl2.SDL_RenderFillRectF(self.ren, ctypes.byref(r))
        except Exception:
            self._has_f = False
        self.circle_tex = self.sprite("circle")

    # ---- frame -----------------------------------------------------------------
    def clear(self, color):
        sdl2.SDL_SetRenderDrawColor(self.ren, color[0], color[1], color[2], 255)
        sdl2.SDL_RenderClear(self.ren)

    def present(self):
        sdl2.SDL_RenderPresent(self.ren)

    def clip(self, rect=None):
        if rect is None:
            sdl2.SDL_RenderSetClipRect(self.ren, None)
        else:
            x, y, w, h = [int(v) for v in rect]
            sdl2.SDL_RenderSetClipRect(self.ren, ctypes.byref(sdl2.SDL_Rect(x, y, w, h)))

    # ---- primitives ------------------------------------------------------------------
    def _a(self, a):
        return int(max(0, min(255, 255 * a * self.alpha)))

    def rect(self, x, y, w, h, color, a=1.0):
        if w <= 0 or h <= 0:
            return
        al = self._a(a)
        if al <= 0:
            return
        sdl2.SDL_SetRenderDrawColor(self.ren, color[0], color[1], color[2], al)
        if self._has_f:
            sdl2.SDL_RenderFillRectF(self.ren, ctypes.byref(sdl2.SDL_FRect(x + self.ox, y + self.oy, w, h)))
        else:
            sdl2.SDL_RenderFillRect(self.ren, ctypes.byref(sdl2.SDL_Rect(int(x + self.ox), int(y + self.oy), int(w), int(h))))

    def _copy(self, tex, src, x, y, w, h, angle=0.0, flip=0):
        if self._has_f:
            dst = sdl2.SDL_FRect(x + self.ox, y + self.oy, w, h)
            if angle or flip:
                sdl2.SDL_RenderCopyExF(self.ren, tex, src, ctypes.byref(dst), angle, None, flip)
            else:
                sdl2.SDL_RenderCopyF(self.ren, tex, src, ctypes.byref(dst))
        else:
            dst = sdl2.SDL_Rect(int(x + self.ox), int(y + self.oy), int(round(w)), int(round(h)))
            if angle or flip:
                sdl2.SDL_RenderCopyEx(self.ren, tex, src, ctypes.byref(dst), angle, None, flip)
            else:
                sdl2.SDL_RenderCopy(self.ren, tex, src, ctypes.byref(dst))

    def _mod(self, t, color, a):
        c = color or (255, 255, 255)
        sdl2.SDL_SetTextureColorMod(t.tex, c[0], c[1], c[2])
        sdl2.SDL_SetTextureAlphaMod(t.tex, self._a(a))

    def circle(self, cx, cy, r, color, a=1.0):
        if r <= 0:
            return
        t = self.circle_tex
        self._mod(t, color, a)
        self._copy(t.tex, None, cx - r, cy - r, r * 2, r * 2)

    def rrect(self, x, y, w, h, r, color, a=1.0):
        if w <= 0 or h <= 0:
            return
        r = max(0.0, min(r, w / 2.0, h / 2.0))
        if r < 1:
            return self.rect(x, y, w, h, color, a)
        t = self.circle_tex
        self._mod(t, color, a)
        hw = t.w // 2
        q = [sdl2.SDL_Rect(0, 0, hw, hw), sdl2.SDL_Rect(hw, 0, hw, hw),
             sdl2.SDL_Rect(0, hw, hw, hw), sdl2.SDL_Rect(hw, hw, hw, hw)]
        self._copy(t.tex, ctypes.byref(q[0]), x, y, r, r)
        self._copy(t.tex, ctypes.byref(q[1]), x + w - r, y, r, r)
        self._copy(t.tex, ctypes.byref(q[2]), x, y + h - r, r, r)
        self._copy(t.tex, ctypes.byref(q[3]), x + w - r, y + h - r, r, r)
        self.rect(x + r, y, w - 2 * r, h, color, a)
        self.rect(x, y + r, r, h - 2 * r, color, a)
        self.rect(x + w - r, y + r, r, h - 2 * r, color, a)

    def rrect_outline(self, x, y, w, h, r, color, bg, thick=2, a=1.0):
        self.rrect(x, y, w, h, r, color, a)
        self.rrect(x + thick, y + thick, w - 2 * thick, h - 2 * thick, max(0, r - thick), bg, a)

    def button3d(self, x, y, w, h, color, shade, r=14, depth=4, pressed=False, a=1.0):
        """Duolingo-style chunky button. Returns y of the face."""
        d = 0 if pressed else depth
        self.rrect(x, y + depth, w, h, r, shade, a)
        fy = y + (depth - d)
        self.rrect(x, fy, w, h, r, color, a)
        return fy

    # ---- sprites -----------------------------------------------------------------------
    def texture_from_rgba(self, data, w, h):
        buf = ctypes.create_string_buffer(data, len(data))
        surf = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(buf, w, h, 32, w * 4, sdl2.SDL_PIXELFORMAT_ABGR8888)
        tex = sdl2.SDL_CreateTextureFromSurface(self.ren, surf)
        sdl2.SDL_FreeSurface(surf)
        sdl2.SDL_SetTextureBlendMode(tex, sdl2.SDL_BLENDMODE_BLEND)
        return Texture(tex, w, h)

    def sprite(self, name):
        t = self.sprites.get(name)
        if t is None:
            path = os.path.join(ASSETS, "sprites", name + ".spr")
            with open(path, "rb") as f:
                raw = f.read()
            w, h = struct.unpack("<HH", raw[4:8])
            t = self.texture_from_rgba(zlib.decompress(raw[8:]), w, h)
            self.sprites[name] = t
        return t

    def draw_sprite(self, name, cx, cy, w, h=None, a=1.0, color=None, angle=0.0, flip=0):
        """Draw a sprite centred on (cx, cy)."""
        t = self.sprite(name) if isinstance(name, str) else name
        h = w if h is None else h
        if w <= 0 or h <= 0:
            return
        self._mod(t, color, a)
        self._copy(t.tex, None, cx - w / 2.0, cy - h / 2.0, w, h, angle, flip)

    # ---- text -----------------------------------------------------------------------------
    def font(self, size, weight=800):
        key = (size, weight)
        f = self.fonts.get(key)
        if f is None:
            path = os.path.join(ASSETS, "fonts", FONT_FILES[weight])
            f = ttf.TTF_OpenFont(path.encode("utf-8"), int(size))
            if not f:
                raise RuntimeError("font %s" % path)
            self.fonts[key] = f
        return f

    def _text_tex(self, s, size, weight):
        key = (s, size, weight)
        t = self.text_cache.get(key)
        if t is not None:
            self.text_cache.move_to_end(key)
            return t
        surf = ttf.TTF_RenderUTF8_Blended(self.font(size, weight), s.encode("utf-8"), sdl2.SDL_Color(255, 255, 255, 255))
        if not surf:
            t = Texture(None, 0, 0)
        else:
            tex = sdl2.SDL_CreateTextureFromSurface(self.ren, surf)
            t = Texture(tex, surf.contents.w, surf.contents.h)
            sdl2.SDL_FreeSurface(surf)
        self.text_cache[key] = t
        if len(self.text_cache) > 500:
            _, old = self.text_cache.popitem(last=False)
            old.destroy()
        return t

    def text_size(self, s, size=18, weight=800):
        if not s:
            return 0, 0
        t = self._text_tex(s, size, weight)
        return t.w, t.h

    def text(self, s, x, y, size=18, color=(255, 255, 255), weight=800, align="l", a=1.0, scale=1.0, valign="t"):
        if not s:
            return 0
        t = self._text_tex(s, size, weight)
        if not t.tex:
            return 0
        w, h = t.w * scale, t.h * scale
        if align == "c":
            x -= w / 2.0
        elif align == "r":
            x -= w
        if valign == "m":
            y -= h / 2.0
        elif valign == "b":
            y -= h
        self._mod(t, color, a)
        self._copy(t.tex, None, x, y, w, h)
        return w

    def wrap(self, s, width, size=16, weight=700):
        lines = []
        for para in s.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = word if not cur else cur + " " + word
                if self.text_size(trial, size, weight)[0] <= width or not cur:
                    cur = trial
                else:
                    lines.append(cur)
                    cur = word
            lines.append(cur)
        return lines

    def text_block(self, s, x, y, width, size=16, color=(255, 255, 255), weight=700, line_h=None, align="l", a=1.0):
        line_h = line_h or int(size * 1.3)
        lines = self.wrap(s, width, size, weight)
        for i, ln in enumerate(lines):
            xx = x + width / 2.0 if align == "c" else x
            self.text(ln, xx, y + i * line_h, size, color, weight, align=align, a=a)
        return len(lines) * line_h

    # ---- render targets ------------------------------------------------------------------
    def target(self, w, h):
        tex = sdl2.SDL_CreateTexture(self.ren, sdl2.SDL_PIXELFORMAT_ARGB8888, sdl2.SDL_TEXTUREACCESS_TARGET, w, h)
        if tex:
            sdl2.SDL_SetTextureBlendMode(tex, sdl2.SDL_BLENDMODE_BLEND)
        return Texture(tex, w, h)

    def set_target(self, t):
        sdl2.SDL_SetRenderTarget(self.ren, t.tex if t else None)
        if t is None:
            sdl2.SDL_RenderSetLogicalSize(self.ren, W, H)

    def layer(self, key, w, h, draw_fn):
        """Render draw_fn(g) once into a cached texture (static backgrounds).
        Returns None if render targets are unsupported (caller draws directly)."""
        if not hasattr(self, "layers"):
            self.layers = {}
        t = self.layers.get(key)
        if t is None:
            if getattr(self, "_no_targets", False):
                return None
            t = self.target(w, h)
            if not t.tex or sdl2.SDL_SetRenderTarget(self.ren, t.tex) != 0:
                self._no_targets = True
                return None
            sdl2.SDL_SetRenderDrawColor(self.ren, 0, 0, 0, 0)
            sdl2.SDL_RenderClear(self.ren)
            ox, oy, al = self.ox, self.oy, self.alpha
            self.ox = self.oy = 0.0
            self.alpha = 1.0
            draw_fn(self)
            self.ox, self.oy, self.alpha = ox, oy, al
            self.set_target(None)
            if len(self.layers) > 12:
                for k in list(self.layers)[:4]:
                    self.layers.pop(k).destroy()
            self.layers[key] = t
        return t

    def blit(self, t, x, y, a=1.0, w=None, h=None):
        if not t or not t.tex:
            return
        self._mod(t, None, a)
        self._copy(t.tex, None, x, y, w or t.w, h or t.h)

    def quit(self):
        for t in list(self.text_cache.values()) + list(self.sprites.values()):
            t.destroy()
        for f in self.fonts.values():
            ttf.TTF_CloseFont(f)
        ttf.TTF_Quit()
        sdl2.SDL_DestroyRenderer(self.ren)
        sdl2.SDL_DestroyWindow(self.window)
        sdl2.SDL_Quit()
