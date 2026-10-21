"""Tiny animation library modelled on motion.dev (https://motion.dev).

motion.dev itself is JavaScript for browsers, which the R36S can't run, so
this ports its core ideas to Python:

  * Value     - like a MotionValue: v.get(), v.set(x)
  * springs   - same physical model as motion's spring() (stiffness, damping,
                mass, velocity), solved analytically so it is frame-rate
                independent and cheap on the RK3326
  * tweens    - duration + easing, incl. motion's cubic-bezier presets
                (easeIn, easeOut, easeInOut, backOut, circOut, anticipate)
  * stagger() - delay helper, same idea as motion's stagger()

All values read a shared clock (set once per frame with tick()), so nothing
needs to be updated manually.
"""
import math

_now = [0.0]


def tick(t):
    _now[0] = t


def now():
    return _now[0]


# ---- easing --------------------------------------------------------------------
def cubic_bezier(x1, y1, x2, y2):
    def sample(t, a1, a2):
        return ((1 - 3 * a2 + 3 * a1) * t + (3 * a2 - 6 * a1)) * t * t + 3 * a1 * t

    def ease(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        lo, hi, t = 0.0, 1.0, x
        for _ in range(14):  # binary subdivision, like motion's implementation
            t = (lo + hi) / 2
            if sample(t, x1, x2) < x:
                lo = t
            else:
                hi = t
        return sample(t, y1, y2)
    return ease


def _back_out(t):
    s = 1.70158
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def _anticipate(t):
    t *= 2
    if t < 1:
        s = 1.70158 * 1.525
        return 0.5 * (t * t * ((s + 1) * t - s))
    return 0.5 * (2 - 2 ** (-10 * (t - 1)))


EASE = {
    "linear": lambda t: t,
    "easeIn": cubic_bezier(0.42, 0, 1, 1),
    "easeOut": cubic_bezier(0, 0, 0.58, 1),
    "easeInOut": cubic_bezier(0.42, 0, 0.58, 1),
    "circOut": lambda t: math.sqrt(max(0.0, 1 - (t - 1) ** 2)),
    "backOut": _back_out,
    "anticipate": _anticipate,
}

# spring presets (stiffness, damping, mass)
SPRINGS = {
    "default": (100, 10, 1),    # motion.dev default spring
    "bouncy": (400, 15, 1),
    "snappy": (500, 32, 1),
    "gentle": (120, 14, 1),
    "wobbly": (180, 9, 1),
    "stiff": (700, 40, 1),
}


def stagger(index, each=0.05, start=0.0):
    return start + index * each


# ---- spring solver --------------------------------------------------------------
class _Spring(object):
    def __init__(self, frm, to, velocity, stiffness, damping, mass, t0, delay):
        self.frm, self.to, self.t0, self.delay = frm, to, t0, delay
        self.k, self.c, self.m = float(stiffness), float(damping), float(mass)
        self.x0 = frm - to
        self.v0 = velocity
        self.w0 = math.sqrt(self.k / self.m)
        self.zeta = self.c / (2 * math.sqrt(self.k * self.m))

    def disp(self, t):
        x0, v0, w0, z = self.x0, self.v0, self.w0, self.zeta
        if z < 1:
            wd = w0 * math.sqrt(1 - z * z)
            e = math.exp(-z * w0 * t)
            return e * (x0 * math.cos(wd * t) + (v0 + z * w0 * x0) / wd * math.sin(wd * t))
        if z == 1:
            return math.exp(-w0 * t) * (x0 + (v0 + w0 * x0) * t)
        s = math.sqrt(z * z - 1)
        r1, r2 = -w0 * (z - s), -w0 * (z + s)
        b = (v0 - r1 * x0) / (r2 - r1)
        a = x0 - b
        return a * math.exp(r1 * t) + b * math.exp(r2 * t)

    def value(self, t):
        t = t - self.t0 - self.delay
        if t <= 0:
            return self.frm, False
        d = self.disp(t)
        if t > 0.05 and abs(d) < 0.0005 * max(1.0, abs(self.x0)) and abs(self.velocity_at(t)) < 0.01 * max(1.0, abs(self.x0)):
            return self.to, True
        if t > 12:
            return self.to, True
        return self.to + d, False

    def velocity_at(self, t):
        h = 0.001
        return (self.disp(t + h) - self.disp(t)) / h


class _Tween(object):
    def __init__(self, frm, to, duration, ease, t0, delay):
        self.frm, self.to, self.dur, self.t0, self.delay = frm, to, max(1e-4, duration), t0, delay
        self.ease = EASE[ease] if isinstance(ease, str) else ease

    def value(self, t):
        p = (t - self.t0 - self.delay) / self.dur
        if p <= 0:
            return self.frm, False
        if p >= 1:
            return self.to, True
        return self.frm + (self.to - self.frm) * self.ease(p), False


class Value(object):
    """A number that can be animated. Read it with get()."""
    __slots__ = ("_v", "_anim", "_vel_hint")

    def __init__(self, v=0.0):
        self._v = float(v)
        self._anim = None

    def get(self):
        a = self._anim
        if a is None:
            return self._v
        v, done = a.value(_now[0])
        if done:
            self._v = v
            self._anim = None
        return v

    __float__ = get

    @property
    def target(self):
        return self._anim.to if self._anim else self._v

    @property
    def animating(self):
        self.get()
        return self._anim is not None

    def set(self, v):
        self._v = float(v)
        self._anim = None
        return self

    def velocity(self):
        a = self._anim
        if isinstance(a, _Spring):
            t = _now[0] - a.t0 - a.delay
            if t > 0:
                return a.velocity_at(t)
        return 0.0

    def spring(self, to, preset="snappy", stiffness=None, damping=None, mass=None, delay=0.0, velocity=None):
        k, c, m = SPRINGS.get(preset, SPRINGS["snappy"])
        vel = self.velocity() if velocity is None else velocity
        self._anim = _Spring(self.get(), float(to), vel, stiffness or k, damping or c, mass or m, _now[0], delay)
        return self

    def tween(self, to, duration=0.3, ease="easeOut", delay=0.0, frm=None):
        start = self.get() if frm is None else float(frm)
        self._anim = _Tween(start, float(to), duration, ease, _now[0], delay)
        return self


class Keyframes(object):
    """Play a list of (value) keyframes over a duration, like motion's [0, 1.2, 1]."""

    def __init__(self, frames, duration=0.4, ease="easeOut", delay=0.0):
        self.frames = [float(f) for f in frames]
        self.dur = duration
        self.ease = EASE[ease] if isinstance(ease, str) else ease
        self.t0 = _now[0] + delay

    def get(self):
        p = (_now[0] - self.t0) / self.dur
        if p <= 0:
            return self.frames[0]
        if p >= 1:
            return self.frames[-1]
        seg = len(self.frames) - 1
        x = p * seg
        i = min(seg - 1, int(x))
        f = self.ease(x - i)
        return self.frames[i] + (self.frames[i + 1] - self.frames[i]) * f

    @property
    def done(self):
        return _now[0] - self.t0 >= self.dur


def shake(t0, amount=10.0, duration=0.4, freq=28.0):
    """Horizontal shake offset (wrong-answer wiggle)."""
    t = _now[0] - t0
    if t < 0 or t > duration:
        return 0.0
    return amount * math.sin(t * freq) * (1 - t / duration)


def pulse(speed=2.0, lo=0.0, hi=1.0, phase=0.0):
    """Endless 0..1 breathing wave, for idle 'alive' animations."""
    s = (math.sin(_now[0] * speed * math.pi + phase) + 1) / 2
    return lo + (hi - lo) * s
