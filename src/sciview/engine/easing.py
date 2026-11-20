"""Easing curves. Each maps u in [0, 1] to [0, 1] (overshoot may leave the range)."""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def clamp01(u: float) -> float:
    return 0.0 if u <= 0 else 1.0 if u >= 1 else float(u)


def _back(u: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


EASINGS: dict[str, Callable[[float], float]] = {
    "linear": lambda u: u,
    "smooth": lambda u: u * u * (3 - 2 * u),
    "smoother": lambda u: u * u * u * (u * (u * 6 - 15) + 10),
    "in": lambda u: u ** 3,
    "out": lambda u: 1 - (1 - u) ** 3,
    "in_out": lambda u: 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2,
    "overshoot": _back,
    "sine": lambda u: 0.5 - 0.5 * math.cos(math.pi * u),
    "hold": lambda u: 0.0 if u < 1 else 1.0,
}

EASING_NAMES = tuple(EASINGS) + ("bezier",)


def cubic_bezier(x1: float, y1: float, x2: float, y2: float, u: float) -> float:
    """CSS-style cubic-bezier(x1, y1, x2, y2) evaluated at progress u in [0, 1].

    The curve runs from (0, 0) to (1, 1); x is time, y is progress. y1 and y2 may leave
    [0, 1] for overshoot. x1 and x2 are clamped to [0, 1] so time never runs backwards.
    """
    u = clamp01(u)
    if u in (0.0, 1.0):
        return u
    x1, x2 = min(max(float(x1), 0.0), 1.0), min(max(float(x2), 0.0), 1.0)
    cx = 3 * x1
    bx = 3 * (x2 - x1) - cx
    ax = 1 - cx - bx
    cy = 3 * float(y1)
    by = 3 * (float(y2) - float(y1)) - cy
    ay = 1 - cy - by

    def fx(s: float) -> float:
        return ((ax * s + bx) * s + cx) * s

    s = u
    for _ in range(8):  # Newton
        d = (3 * ax * s + 2 * bx) * s + cx
        err = fx(s) - u
        if abs(err) < 1e-7:
            break
        if abs(d) < 1e-6:
            break
        s -= err / d
    if not (0.0 <= s <= 1.0) or abs(fx(s) - u) > 1e-5:  # bisection fallback
        lo, hi = 0.0, 1.0
        s = u
        for _ in range(40):
            if fx(s) < u:
                lo = s
            else:
                hi = s
            s = (lo + hi) / 2
    return ((ay * s + by) * s + cy) * s


BEZIER_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease_in": (0.42, 0.0, 1.0, 1.0),
    "ease_out": (0.0, 0.0, 0.58, 1.0),
    "ease_in_out": (0.42, 0.0, 0.58, 1.0),
    "back": (0.34, 1.56, 0.64, 1.0),
}


def ease(name: str, u: float, bez=None) -> float:
    """Apply easing ``name`` to u (clamped to 0..1 first). ``name="bezier"`` uses ``bez`` = (x1, y1, x2, y2)."""
    if name == "bezier":
        if bez is not None and len(bez) == 4:
            return cubic_bezier(*bez, u)
        return EASINGS["smooth"](clamp01(u))
    return EASINGS.get(name, EASINGS["smooth"])(clamp01(u))


def smooth(t: float, a: float, b: float) -> float:
    """Ease from 0 to 1 between times a and b (smoothstep), as in the original films."""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return EASINGS["smooth"](clamp01((t - a) / (b - a)))


def smooth_array(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)
