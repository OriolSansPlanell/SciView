"""Transitions between two finished frames: crossfades, dips, wipes, pushes and zooms.

Frames are float32 arrays in 0..1, (h, w, 3) RGB or (h, w, 4) premultiplied RGBA. ``p`` runs from 0
(only the outgoing scene) to 1 (only the incoming one) and is eased here.
"""
from __future__ import annotations

import cv2
import numpy as np

TRANSITIONS: dict[str, str] = {
    "cut": "Cut",
    "crossfade": "Crossfade",
    "dip": "Dip to background",
    "wipe_left": "Wipe to the left",
    "wipe_right": "Wipe to the right",
    "wipe_up": "Wipe upwards",
    "wipe_down": "Wipe downwards",
    "push_left": "Push to the left",
    "push_right": "Push to the right",
    "push_up": "Push upwards",
    "push_down": "Push downwards",
    "zoom": "Zoom through",
}


def ease(p: float) -> float:
    p = min(1.0, max(0.0, float(p)))
    return p * p * (3 - 2 * p)


def _wipe_mask(h: int, w: int, kind: str, p: float) -> np.ndarray:
    """1 where the incoming frame shows. The edge is soft (3% of the frame) and travels with p."""
    horizontal = kind in ("wipe_left", "wipe_right")
    n = w if horizontal else h
    soft = max(2.0, 0.03 * n)
    pos = -soft + p * (n + 2 * soft)                   # edge position measured from where it starts
    u = np.arange(n, dtype=np.float32)
    if kind in ("wipe_left", "wipe_up"):               # the edge moves left/up: B is revealed from the far side
        u = (n - 1) - u
    m = np.clip((pos - u) / soft + 0.5, 0.0, 1.0)
    return m[None, :, None] if horizontal else m[:, None, None]


def _shift(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _zoom(img: np.ndarray, z: float) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 0.0, z)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def blend(a: np.ndarray, b: np.ndarray, kind: str, p: float, background: np.ndarray | None = None) -> np.ndarray:
    """Frame ``p`` of the way through a transition from ``a`` to ``b``.

    ``background`` (h, w, c) is what a dip passes through; it defaults to black (transparent with alpha).
    """
    q = ease(p)
    if kind == "cut" or a is None:
        return b if q >= 0.5 or a is None else a
    if kind == "crossfade":
        return a * (1 - q) + b * q
    if kind == "dip":
        bg = background if background is not None else np.zeros_like(a)
        if q < 0.5:
            u = ease(q * 2)
            return a * (1 - u) + bg * u
        u = ease(q * 2 - 1)
        return bg * (1 - u) + b * u
    h, w = a.shape[:2]
    if kind.startswith("wipe_"):
        m = _wipe_mask(h, w, kind, q)
        return a * (1 - m) + b * m
    if kind.startswith("push_"):
        # the outgoing frame slides away and the incoming one follows it in from the other side
        sign = -1.0 if kind in ("push_left", "push_up") else 1.0
        span = w if kind in ("push_left", "push_right") else h
        da = sign * span * q
        db = da - sign * span
        if kind in ("push_left", "push_right"):
            out, bb = _shift(a, da, 0.0), _shift(b, db, 0.0)
            cover = _shift(np.ones((h, w), np.float32), db, 0.0)
        else:
            out, bb = _shift(a, 0.0, da), _shift(b, 0.0, db)
            cover = _shift(np.ones((h, w), np.float32), 0.0, db)
        return out * (1 - cover[..., None]) + bb
    if kind == "zoom":
        za = _zoom(a, 1 + 0.18 * q)
        zb = _zoom(b, 0.9 + 0.1 * q)
        f = ease((q - 0.2) / 0.6)
        return za * (1 - f) + zb * f
    raise ValueError(f"unknown transition {kind!r}. Transitions: {', '.join(TRANSITIONS)}")


def describe(kind: str, seconds: float) -> str:
    if kind == "cut" or seconds <= 0:
        return "cut"
    return f"{TRANSITIONS.get(kind, kind).lower()}, {seconds:g} s"

