"""Easing curves. Each maps u in [0, 1] to [0, 1] (overshoot may leave the range)."""
from __future__ import annotations

import math
from typing import Callable

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

EASING_NAMES = tuple(EASINGS)


def ease(name: str, u: float) -> float:
    """Apply easing ``name`` to u (clamped to 0..1 first)."""
    return EASINGS.get(name, EASINGS["smooth"])(clamp01(u))


def smooth(t: float, a: float, b: float) -> float:
    """Ease from 0 to 1 between times a and b (smoothstep), as in the original films."""
    if b <= a:
        return 1.0 if t >= b else 0.0
    return EASINGS["smooth"](clamp01((t - a) / (b - a)))


def smooth_array(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)
