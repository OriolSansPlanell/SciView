"""The drawing surface.

A :class:`Canvas` holds two float buffers at output resolution:

* ``rgb``  - the composited picture (values 0..1, may exceed 1 before tone mapping)
* ``emit`` - light that should glow; it is blurred at several scales in
  :meth:`Canvas.finish` and added back, which gives the neon look.

All drawing happens inside a small region of interest around each primitive, so
cost scales with what is drawn, not with the frame size. Coordinates given to
the drawing methods are output pixels; objects convert from design pixels with
``canvas.s``.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import cv2
import numpy as np

_SHIFT = 4
_ONE = 1 << _SHIFT


# --------------------------------------------------------------------------- path helpers
def path_length(pts: np.ndarray) -> np.ndarray:
    """Cumulative arc length along a polyline (N,2) -> (N,)."""
    if len(pts) < 2:
        return np.zeros(len(pts))
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)])


def truncate_path(pts: np.ndarray, progress: float) -> np.ndarray:
    """Keep the first ``progress`` (0..1) of a polyline, interpolating the last point."""
    pts = np.asarray(pts, np.float64)
    if progress >= 1 or len(pts) < 2:
        return pts
    if progress <= 0:
        return pts[:1]
    cum = path_length(pts)
    target = cum[-1] * progress
    i = int(np.searchsorted(cum, target, side="right"))
    i = max(1, min(i, len(pts) - 1))
    span = cum[i] - cum[i - 1]
    f = 0.0 if span <= 0 else (target - cum[i - 1]) / span
    end = pts[i - 1] + (pts[i] - pts[i - 1]) * f
    return np.vstack([pts[:i], end[None]])


def dash_path(pts: np.ndarray, on: float, off: float) -> list[np.ndarray]:
    """Split a polyline into dashes of length ``on`` separated by ``off`` (pixels)."""
    pts = np.asarray(pts, np.float64)
    cum = path_length(pts)
    total = cum[-1] if len(cum) else 0
    if total <= 0 or on <= 0:
        return [pts]
    out = []
    period = on + off
    s = 0.0
    while s < total:
        e = min(s + on, total)
        ts = np.concatenate([[s], cum[(cum > s) & (cum < e)], [e]])
        xs = np.interp(ts, cum, pts[:, 0])
        ys = np.interp(ts, cum, pts[:, 1])
        out.append(np.stack([xs, ys], axis=1))
        s += period
    return out


def rounded_rect(x: float, y: float, w: float, h: float, r: float, n: int = 8) -> np.ndarray:
    r = max(0.0, min(r, w / 2, h / 2))
    if r < 0.5:
        return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float64)
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0),
                       (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(pts, np.float64)


def ellipse_points(cx: float, cy: float, rx: float, ry: float, n: int = 96,
                   a0: float = -90.0, a1: float = 270.0) -> np.ndarray:
    a = np.radians(np.linspace(a0, a1, n))
    return np.stack([cx + rx * np.cos(a), cy + ry * np.sin(a)], axis=1)


def arrow_head(tip: np.ndarray, direction: np.ndarray, size: float, width_ratio: float = 0.55) -> np.ndarray:
    d = np.asarray(direction, np.float64)
    n = float(np.linalg.norm(d))
    if n < 1e-9:
        return np.zeros((0, 2))
    d = d / n
    p = np.array([-d[1], d[0]])
    base = tip - d * size
    return np.array([tip, base + p * size * width_ratio, base - p * size * width_ratio])


# --------------------------------------------------------------------------- canvas
class Painter:
    """Opaque shapes drawn in order into a scratch RGBA buffer, then blended into a canvas once."""

    def __init__(self, canvas: Canvas, roi):
        self.canvas = canvas
        self.roi = roi
        x0, y0, x1, y1 = roi
        self.buf = np.zeros((y1 - y0, x1 - x0, 4), np.float32)

    def ipts(self, pts) -> np.ndarray:
        return Canvas._ipts(self.canvas._t(pts), self.roi)

    def circle(self, x: float, y: float, r: float, color) -> None:
        p = self.ipts(np.array([[x, y]], np.float64))[0]
        c = np.asarray(color, np.float32)
        cv2.circle(self.buf, (int(p[0]), int(p[1])), max(1, int(round(r * _ONE))),
                   (float(c[0]), float(c[1]), float(c[2]), 1.0), -1, cv2.LINE_8, _SHIFT)

    def line(self, p0, p1, width: float, color) -> None:
        ip = self.ipts(np.array([p0, p1], np.float64))
        c = np.asarray(color, np.float32)
        cv2.line(self.buf, (int(ip[0, 0]), int(ip[0, 1])), (int(ip[1, 0]), int(ip[1, 1])),
                 (float(c[0]), float(c[1]), float(c[2]), 1.0), max(1, int(round(width))), cv2.LINE_8, _SHIFT)

    def polygon(self, pts, color) -> None:
        ip = self.ipts(np.asarray(pts, np.float64))
        c = np.asarray(color, np.float32)
        cv2.fillPoly(self.buf, [ip], (float(c[0]), float(c[1]), float(c[2]), 1.0), cv2.LINE_8, _SHIFT)

    def done(self, alpha: float = 1.0, glow: float = 0.0) -> None:
        mask = self.buf[..., 3]
        rgb = self.buf[..., :3]
        # half a pixel of anti-aliasing on the outline: blur the coverage, spread colour into the fringe
        soft = cv2.blur(mask, (3, 3))
        fringe = (soft > 0) & (mask < 1)
        if fringe.any():
            grown = cv2.dilate(rgb, np.ones((3, 3), np.uint8))
            rgb[fringe] = grown[fringe]
        self.canvas.composite_rgb(self.roi, rgb, soft, alpha, glow)


class Canvas:
    """Float RGB canvas with a glow buffer, clip rectangles and anti-aliased primitives.

    Two modes:

    * normal: ``rgb`` holds the picture and primitives blend straight into it;
    * layer (``layer=True``): nothing is known about what lies underneath, so the canvas
      records an affine map ``F -> F * T + P`` per pixel (transmission ``T``, premultiplied
      light ``P``). :meth:`paste` applies a layer to another canvas and gives exactly the
      picture that drawing the same primitives directly would have given. The renderer
      caches layers of objects that do not change between frames.

    ``set_offset`` shifts everything drawn afterwards by a number of output pixels (used
    for groups).
    """

    def __init__(self, width: int, height: int, scale: float = 1.0, background: np.ndarray | None = None,
                 layer: bool = False):
        self.w, self.h, self.s = int(width), int(height), float(scale)
        self.layer = bool(layer)
        if self.layer:
            self.rgb = np.zeros((self.h, self.w, 3), np.float32)      # P
            self.trans = np.ones((self.h, self.w), np.float32)        # T
        elif background is not None:
            self.rgb = background.astype(np.float32, copy=True)
        else:
            self.rgb = np.zeros((self.h, self.w, 3), np.float32)
        self.emit = np.zeros((self.h, self.w, 3), np.float32)
        self._clips: list[tuple[int, int, int, int]] = [(0, 0, self.w, self.h)]
        self._emit_used = False
        self._ebox: list[int] | None = None      # union of regions that received glow
        self._touched: list[int] | None = None   # union of regions drawn (layer mode)
        self.ox = 0.0
        self.oy = 0.0

    # ------------------------------------------------------------------ offset and clipping
    def set_offset(self, ox: float = 0.0, oy: float = 0.0) -> None:
        self.ox, self.oy = float(ox), float(oy)

    def _t(self, pts) -> np.ndarray:
        p = np.asarray(pts, np.float64).reshape(-1, 2)
        if self.ox or self.oy:
            p = p + (self.ox, self.oy)
        return p

    @property
    def clip(self) -> tuple[int, int, int, int]:
        return self._clips[-1]

    def push_clip(self, x0: float, y0: float, x1: float, y1: float) -> None:
        cx0, cy0, cx1, cy1 = self.clip
        x0, x1, y0, y1 = x0 + self.ox, x1 + self.ox, y0 + self.oy, y1 + self.oy
        self._clips.append((max(cx0, int(math.floor(x0))), max(cy0, int(math.floor(y0))),
                            min(cx1, int(math.ceil(x1))), min(cy1, int(math.ceil(y1)))))

    def pop_clip(self) -> None:
        if len(self._clips) > 1:
            self._clips.pop()

    def _roi(self, pts: np.ndarray, pad: float):
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        pts = pts[np.isfinite(pts).all(axis=1)]
        if len(pts) == 0:
            return None
        cx0, cy0, cx1, cy1 = self.clip
        x0 = max(cx0, int(math.floor(pts[:, 0].min() - pad)))
        y0 = max(cy0, int(math.floor(pts[:, 1].min() - pad)))
        x1 = min(cx1, int(math.ceil(pts[:, 0].max() + pad)) + 1)
        y1 = min(cy1, int(math.ceil(pts[:, 1].max() + pad)) + 1)
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1, y1

    @staticmethod
    def _ipts(pts: np.ndarray, roi) -> np.ndarray:
        p = (np.asarray(pts, np.float64) - (roi[0], roi[1])) * _ONE
        return np.round(np.clip(p, -1e6, 1e6)).astype(np.int32)

    @staticmethod
    def _grow(box: list[int] | None, roi) -> list[int]:
        if box is None:
            return list(roi)
        return [min(box[0], roi[0]), min(box[1], roi[1]), max(box[2], roi[2]), max(box[3], roi[3])]

    # ------------------------------------------------------------------ compositing
    def _blend(self, roi, m3: np.ndarray, colour: np.ndarray, additive: bool) -> None:
        x0, y0, x1, y1 = roi
        sub = self.rgb[y0:y1, x0:x1]
        if self.layer:
            self._touched = self._grow(self._touched, roi)
            if additive:
                sub += colour * m3
            else:
                keep = 1.0 - m3
                sub *= keep
                sub += colour * m3
                self.trans[y0:y1, x0:x1] *= keep[..., 0]
        elif additive:
            sub += colour * m3
        else:
            sub += (colour - sub) * m3

    def _glow(self, roi, m3: np.ndarray, colour: np.ndarray, glow: float) -> None:
        if glow > 0:
            x0, y0, x1, y1 = roi
            self.emit[y0:y1, x0:x1] += colour * (m3 * glow)
            self._emit_used = True
            self._ebox = self._grow(self._ebox, roi)
            if self.layer:
                self._touched = self._grow(self._touched, roi)

    def composite(self, roi, mask: np.ndarray, color, alpha: float = 1.0, glow: float = 0.0,
                  additive: bool = False) -> None:
        """Blend ``color`` through ``mask`` (float 0..1 or uint8, ROI-sized) into the canvas."""
        if alpha <= 0 or roi is None:
            return
        if mask.dtype == np.uint8:
            m = mask.astype(np.float32) * (alpha / 255.0)
        else:
            m = mask.astype(np.float32, copy=False) * alpha
        m3 = m[..., None]
        col = np.asarray(color, np.float32).reshape(1, 1, 3)
        self._blend(roi, m3, col, additive)
        self._glow(roi, m3, col, glow)

    def composite_rgb(self, roi, rgb: np.ndarray, mask: np.ndarray, alpha: float = 1.0,
                      glow: float = 0.0, additive: bool = False) -> None:
        """Blend a per-pixel colour image (ROI-sized) through a float mask."""
        if alpha <= 0 or roi is None:
            return
        m3 = (mask.astype(np.float32, copy=False) * alpha)[..., None]
        rgb = rgb.astype(np.float32, copy=False)
        self._blend(roi, m3, rgb, additive)
        self._glow(roi, m3, rgb, glow)

    # ------------------------------------------------------------------ layers
    def extract(self, tile: int = 64) -> Layer | None:
        """The drawn part of a layer canvas as tiles; empty tiles (nothing drawn) are dropped."""
        if not self.layer or self._touched is None:
            return None
        x0, y0, x1, y1 = self._touched
        tiles = []
        for ty in range(y0, y1, tile):
            for tx in range(x0, x1, tile):
                ex, ey = min(tx + tile, x1), min(ty + tile, y1)
                T = self.trans[ty:ey, tx:ex]
                P = self.rgb[ty:ey, tx:ex]
                E = self.emit[ty:ey, tx:ex] if self._emit_used else None
                if T.min() >= 1.0 and not P.any() and (E is None or not E.any()):
                    continue
                tiles.append((tx, ty, P.copy(), np.repeat(T[..., None], 3, axis=2),
                              E.copy() if E is not None and E.any() else None))
        return Layer(tiles)

    def paste(self, lay: Layer | None) -> None:
        """Apply a cached layer: F = F * T + P, glow added."""
        if lay is None:
            return
        for x0, y0, P, T3, E in lay.tiles:
            h, w = P.shape[:2]
            roi = (x0, y0, x0 + w, y0 + h)
            sub = self.rgb[y0:y0 + h, x0:x0 + w]
            sub *= T3
            sub += P
            if self.layer:
                self._touched = self._grow(self._touched, roi)
                self.trans[y0:y0 + h, x0:x0 + w] *= T3[..., 0]
            if E is not None:
                self.emit[y0:y0 + h, x0:x0 + w] += E
                self._emit_used = True
                self._ebox = self._grow(self._ebox, roi)

    # ------------------------------------------------------------------ primitives
    def polygon(self, pts, fill=None, fill_alpha: float = 1.0, stroke=None, stroke_alpha: float = 1.0,
                width: float = 1.0, glow: float = 0.0, fill_glow: float = 0.0, dash: float = 0.0) -> None:
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if len(pts) < 3 or not np.isfinite(pts).all():
            return
        if fill is not None and fill_alpha > 0:
            tp = self._t(pts)
            roi = self._roi(tp, 2)
            if roi is not None:
                mask = np.zeros((roi[3] - roi[1], roi[2] - roi[0]), np.uint8)
                cv2.fillPoly(mask, [self._ipts(tp, roi)], 255, cv2.LINE_AA, _SHIFT)
                self.composite(roi, mask, fill, fill_alpha, fill_glow)
        if stroke is not None and stroke_alpha > 0 and width > 0:
            self.polyline(np.vstack([pts, pts[:1]]), stroke, stroke_alpha, width, glow, dash=dash)

    def polyline(self, pts, color, alpha: float = 1.0, width: float = 1.0, glow: float = 0.0,
                 dash: float = 0.0, gap: float | None = None, progress: float = 1.0,
                 additive: bool = False) -> None:
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if progress < 1:
            pts = truncate_path(pts, progress)
        if len(pts) < 2 or alpha <= 0:
            return
        paths = dash_path(pts, dash, gap if gap is not None else dash * 0.8) if dash > 0 else [pts]
        self.lines(paths, color, alpha, width, glow, additive=additive)

    def lines(self, paths: Iterable[np.ndarray], color, alpha: float = 1.0, width: float = 1.0,
              glow: float = 0.0, additive: bool = False) -> None:
        """Draw many open polylines with one style in a single pass (fast wireframes)."""
        self.lines_levels({8: list(paths)}, color, alpha, width, glow, additive)

    def lines_levels(self, groups: dict, color, alpha: float = 1.0, width: float = 1.0,
                     glow: float = 0.0, additive: bool = False, levels: int = 8) -> None:
        """Polylines at several opacities (``{level: [paths]}``, level 1..levels) in ONE composite.

        Used for grids whose lines fade out: one mask instead of one pass per opacity.
        """
        thick = max(1, int(round(width)))
        a = alpha * min(1.0, width) if width < 1 else alpha
        if a <= 0:
            return
        clean: dict[int, list[np.ndarray]] = {}
        allpts = []
        for lvl, paths in groups.items():
            ps = [self._t(p) for p in paths]
            ps = [p for p in ps if len(p) >= 2 and np.isfinite(p).all()]
            if ps and lvl > 0:
                clean[int(lvl)] = ps
                allpts.extend(ps)
        if not allpts:
            return
        roi = self._roi(np.vstack(allpts), thick + 2)
        if roi is None:
            return
        mask = np.zeros((roi[3] - roi[1], roi[2] - roi[0]), np.uint8)
        for lvl in sorted(clean):
            value = int(round(255 * min(lvl, levels) / levels))
            cv2.polylines(mask, [self._ipts(p, roi) for p in clean[lvl]], False, value, thick, cv2.LINE_AA, _SHIFT)
        self.composite(roi, mask, color, a, glow, additive)

    def circle(self, cx: float, cy: float, r: float, fill=None, fill_alpha: float = 1.0, stroke=None,
               stroke_alpha: float = 1.0, width: float = 1.0, glow: float = 0.0, fill_glow: float = 0.0) -> None:
        n = int(min(256, max(24, r * 1.5)))
        pts = ellipse_points(cx, cy, r, r, n, 0, 360)[:-1]
        self.polygon(pts, fill, fill_alpha, stroke, stroke_alpha, width, glow, fill_glow)

    def dots(self, xy: np.ndarray, radius: float, color, alpha: float = 1.0, glow: float = 0.0,
             colors: np.ndarray | None = None) -> None:
        """Crisp filled discs (one colour, or per-dot ``colors`` (N,3))."""
        xy = self._t(xy)
        ok = np.isfinite(xy).all(axis=1)
        xy = xy[ok]
        if colors is not None:
            colors = np.asarray(colors, np.float32)[ok]
        if len(xy) == 0:
            return
        roi = self._roi(xy, radius + 2)
        if roi is None:
            return
        h, w = roi[3] - roi[1], roi[2] - roi[0]
        ip = self._ipts(xy, roi)
        rr = max(1, int(round(radius * _ONE)))
        if colors is None:
            mask = np.zeros((h, w), np.uint8)
            for p in ip:
                cv2.circle(mask, (int(p[0]), int(p[1])), rr, 255, -1, cv2.LINE_AA, _SHIFT)
            self.composite(roi, mask, color, alpha, glow)
        else:
            img = np.zeros((h, w, 3), np.float32)
            mask = np.zeros((h, w), np.float32)
            for p, c in zip(ip, colors):
                cv2.circle(img, (int(p[0]), int(p[1])), rr, tuple(float(v) for v in c), -1, cv2.LINE_8, _SHIFT)
                cv2.circle(mask, (int(p[0]), int(p[1])), rr, 1.0, -1, cv2.LINE_8, _SHIFT)
            self.composite_rgb(roi, img, mask, alpha, glow)

    def splat(self, xy: np.ndarray, weights, color, alpha: float = 1.0, sigma: float = 1.0,
              gain: float = 1.4, glow: float = 0.0, additive: bool = True, colors: np.ndarray | None = None) -> None:
        """Accumulate soft points, blur, and compress with 1 - exp(-x).

        Crowded points glow instead of clipping to white (the particle-streak look).
        ``weights`` is a scalar or an (N,) array. ``colors`` (N,3) gives per-point colours.
        """
        xy = self._t(xy)
        w = np.broadcast_to(np.asarray(weights, np.float64), (len(xy),)).copy()
        ok = np.isfinite(xy).all(axis=1) & (w > 0)
        xy, w = xy[ok], w[ok]
        if colors is not None:
            colors = np.asarray(colors, np.float32)[ok]
        if len(xy) == 0:
            return
        pad = 3 * sigma + 2
        cx0, cy0, cx1, cy1 = self.clip
        inside = (xy[:, 0] > cx0 - pad) & (xy[:, 0] < cx1 + pad) & (xy[:, 1] > cy0 - pad) & (xy[:, 1] < cy1 + pad)
        xy, w = xy[inside], w[inside]
        if colors is not None:
            colors = colors[inside]
        roi = self._roi(xy, pad)
        if roi is None:
            return
        x0, y0, x1, y1 = roi
        rw, rh = x1 - x0, y1 - y0
        px = xy[:, 0] - x0 - 0.5
        py = xy[:, 1] - y0 - 0.5
        ix, iy = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
        fx, fy = px - ix, py - iy
        acc = np.zeros(rw * rh, np.float64)
        accc = np.zeros((rw * rh, 3), np.float64) if colors is not None else None
        for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
            xx, yy = ix + dx, iy + dy
            good = (xx >= 0) & (xx < rw) & (yy >= 0) & (yy < rh)
            idx = (yy * rw + xx)[good]
            ww = (w * wt)[good]
            acc += np.bincount(idx, ww, minlength=rw * rh)
            if accc is not None:
                for k in range(3):
                    accc[:, k] += np.bincount(idx, ww * colors[good, k], minlength=rw * rh)
        acc = acc.reshape(rh, rw).astype(np.float32)
        if sigma > 0.3:
            acc = cv2.GaussianBlur(acc, (0, 0), sigma) * (2 * math.pi * sigma * sigma)
        val = 1.0 - np.exp(-acc * gain)
        if accc is None:
            self.composite(roi, val, color, alpha, glow, additive)
        else:
            cimg = accc.reshape(rh, rw, 3).astype(np.float32)
            if sigma > 0.3:
                cimg = cv2.GaussianBlur(cimg, (0, 0), sigma) * (2 * math.pi * sigma * sigma)
            cimg = cimg / np.maximum(acc, 1e-6)[..., None]
            self.composite_rgb(roi, np.clip(cimg, 0, 1.5), val, alpha, glow, additive)

    def blit(self, mask: np.ndarray, x: float, y: float, color=None, rgb: np.ndarray | None = None,
             alpha: float = 1.0, glow: float = 0.0, additive: bool = False) -> tuple[int, int, int, int] | None:
        """Paste a float alpha ``mask`` (h,w) with its top-left at (x, y), coloured by ``color`` or ``rgb``."""
        h, w = mask.shape[:2]
        X, Y = int(round(x + self.ox)), int(round(y + self.oy))
        cx0, cy0, cx1, cy1 = self.clip
        x0, y0 = max(cx0, X), max(cy0, Y)
        x1, y1 = min(cx1, X + w), min(cy1, Y + h)
        if x1 <= x0 or y1 <= y0:
            return None
        roi = (x0, y0, x1, y1)
        m = mask[y0 - Y:y1 - Y, x0 - X:x1 - X]
        if rgb is not None:
            self.composite_rgb(roi, rgb[y0 - Y:y1 - Y, x0 - X:x1 - X], m, alpha, glow, additive)
        else:
            self.composite(roi, m, color, alpha, glow, additive)
        return roi

    def triangles(self, xy: np.ndarray, tris: np.ndarray, colors: np.ndarray, alpha: float = 1.0,
                  glow: float = 0.0) -> None:
        """Opaque shaded triangles (indices ``tris`` into points ``xy``), painted in the given order
        (sort them back to front), then blended into the canvas once with ``alpha``.

        Used for isosurfaces and ribbons: one composite instead of one per face.
        """
        tris = np.asarray(tris, np.int64).reshape(-1, 3)
        if len(tris) == 0 or alpha <= 0:
            return
        pt = self.painter(np.asarray(xy)[np.unique(tris)], 2)
        if pt is None:
            return
        ip = pt.ipts(xy)
        cols = np.asarray(colors, np.float32).reshape(-1, 3)
        for tri, c in zip(ip[tris], cols):
            cv2.fillConvexPoly(pt.buf, tri, (float(c[0]), float(c[1]), float(c[2]), 1.0), cv2.LINE_8, _SHIFT)
        pt.done(alpha, glow)

    def painter(self, pts: np.ndarray, pad: float) -> Painter | None:
        """An opaque scratch layer over the area of ``pts`` (output px) for painter's-algorithm drawing;
        call its ``done`` to blend it into the canvas in one step (molecules, meshes)."""
        roi = self._roi(self._t(pts), pad)
        if roi is None:
            return None
        return Painter(self, roi)

    def warp(self, img: np.ndarray, quad: np.ndarray, alpha: float = 1.0, glow: float = 0.0,
             mask: np.ndarray | None = None, nearest: bool = False) -> None:
        """Map an RGB image (h,w,3) onto a quadrilateral (tl, tr, br, bl) in output pixels."""
        quad = self._t(quad).reshape(4, 2)
        roi = self._roi(quad, 2)
        if roi is None or alpha <= 0:
            return
        x0, y0, x1, y1 = roi
        h, w = img.shape[:2]
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32(quad - (x0, y0))
        try:
            M = cv2.getPerspectiveTransform(src, dst)
        except cv2.error:
            return
        size = (x1 - x0, y1 - y0)
        flag = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
        warped = cv2.warpPerspective(img.astype(np.float32, copy=False), M, size, flags=flag,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
        src_mask = np.ones((h, w), np.float32) if mask is None else mask.astype(np.float32)
        # pad the mask by one pixel so the warped edge is anti-aliased
        src_mask = cv2.copyMakeBorder(src_mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        T = np.array([[1, 0, -1], [0, 1, -1], [0, 0, 1]], np.float64)
        cov = cv2.warpPerspective(src_mask, M @ T, size, flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        if warped.ndim == 2:
            warped = np.repeat(warped[..., None], 3, axis=2)
        self.composite_rgb(roi, warped, np.clip(cov, 0, 1), alpha, glow)

    # ------------------------------------------------------------------ finishing
    def finish(self, bloom: float = 0.6, vignette: float = 0.0, vignette_color=(0, 0, 0)) -> np.ndarray:
        """Add bloom, apply vignette and a soft highlight shoulder; return uint8 RGB.

        The canvas is consumed: its buffers are modified in place.
        """
        out = self.rgb
        self._add_bloom(out, bloom)
        if vignette > 0:
            vm3, vadd = _vignette_terms(self.w, self.h, vignette, tuple(float(c) for c in vignette_color))
            cv2.multiply(out, vm3, dst=out)
            cv2.add(out, vadd, dst=out)
        _shoulder(out)
        return cv2.convertScaleAbs(out, alpha=255.0)

    def finish_rgba(self, bloom: float = 0.6) -> np.ndarray:
        """Like :meth:`finish` for a canvas drawn without background (``layer=True``): uint8 RGBA with
        straight alpha. Coverage gives the alpha; glow adds light and as much opacity as it is bright."""
        if not self.layer:
            raise ValueError("finish_rgba needs a canvas made with layer=True")
        P = self.rgb
        A = 1.0 - self.trans
        glow_alpha = np.zeros_like(A)
        self._add_bloom(P, bloom, glow_alpha)
        A = 1.0 - (1.0 - A) * (1.0 - np.clip(glow_alpha, 0.0, 1.0))
        _shoulder(P)
        a = np.maximum(A, 1e-6)[..., None]
        rgb = np.where(A[..., None] > 1e-4, np.clip(P / a, 0.0, 1.0), 0.0)
        out = np.empty((self.h, self.w, 4), np.uint8)
        out[..., :3] = cv2.convertScaleAbs(rgb.astype(np.float32), alpha=255.0)
        out[..., 3] = cv2.convertScaleAbs(np.clip(A, 0, 1).astype(np.float32), alpha=255.0)
        return out

    def _add_bloom(self, out: np.ndarray, bloom: float, glow_alpha: np.ndarray | None = None) -> None:
        if bloom > 0 and self._emit_used and self._ebox is not None:
            s = self.s
            margin = int(math.ceil(3 * 40.0 * s)) + 16          # 3 sigma of the widest blur
            bx0, by0, bx1, by1 = self._ebox
            # crop on the global 8-pixel grid (padding past the frame with zeros), so the
            # result does not depend on how large the glowing region happens to be
            X0, Y0 = max(0, (bx0 - margin) // 8 * 8), max(0, (by0 - margin) // 8 * 8)
            X1, Y1 = -(-(bx1 + margin) // 8) * 8, -(-(by1 + margin) // 8) * 8
            fx1, fy1 = min(self.w, X1), min(self.h, Y1)
            if X1 <= self.w and Y1 <= self.h:
                e = self.emit[Y0:Y1, X0:X1]
            else:
                e = np.zeros((Y1 - Y0, X1 - X0, 3), np.float32)
                e[:fy1 - Y0, :fx1 - X0] = self.emit[Y0:fy1, X0:fx1]
            h, w = e.shape[:2]
            h2, w2, h8, w8 = h // 2, w // 2, h // 8, w // 8
            half = cv2.resize(e, (w2, h2), interpolation=cv2.INTER_AREA)
            eighth = cv2.resize(half, (w8, h8), interpolation=cv2.INTER_AREA)
            g1 = cv2.GaussianBlur(half, (0, 0), max(0.6, 3.0 * s / 2))
            g2 = cv2.GaussianBlur(eighth, (0, 0), max(0.6, 14.0 * s / 8))
            g3 = cv2.GaussianBlur(eighth, (0, 0), max(0.8, 40.0 * s / 8))
            wide = cv2.addWeighted(g2, 0.55, g3, 0.35, 0.0)
            glow_half = cv2.addWeighted(g1, 0.9, cv2.resize(wide, (w2, h2), interpolation=cv2.INTER_LINEAR), 1.0, 0.0)
            glow = cv2.resize(glow_half, (w, h), interpolation=cv2.INTER_LINEAR)
            region = out[Y0:fy1, X0:fx1]
            g = glow[:fy1 - Y0, :fx1 - X0] * float(bloom)
            region += g
            if glow_alpha is not None:
                glow_alpha[Y0:fy1, X0:fx1] = np.maximum(glow_alpha[Y0:fy1, X0:fx1], g.max(axis=2))


def _shoulder(out: np.ndarray, knee: float = 0.85) -> None:
    """Soft shoulder above ``knee`` instead of a hard clip (in place)."""
    if float(out.max()) > knee:
        over = out > knee
        v = out[over]
        out[over] = knee + (1 - knee) * (1 - np.exp(-(v - knee) / (1 - knee)))


@dataclass
class Layer:
    """A cached drawing: tiles of (x, y, premultiplied light P, transmission T, glow E or None)."""

    tiles: list

    @property
    def nbytes(self) -> int:
        n = 0
        for _x, _y, P, T3, E in self.tiles:
            n += P.nbytes + T3.nbytes + (E.nbytes if E is not None else 0)
        return n + 64


_vterm_cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _vignette_terms(w: int, h: int, strength: float, colour: tuple) -> tuple[np.ndarray, np.ndarray]:
    key = (w, h, round(strength, 3), tuple(round(c, 4) for c in colour))
    terms = _vterm_cache.get(key)
    if terms is None:
        vm = vignette_mask(w, h, strength)
        vm3 = np.repeat(vm[..., None], 3, axis=2).astype(np.float32)
        vadd = ((1 - vm3) * np.asarray(colour, np.float32)).astype(np.float32)
        if len(_vterm_cache) > 6:
            _vterm_cache.clear()
        terms = _vterm_cache[key] = (vm3, vadd)
    return terms


_vig_cache: dict[tuple[int, int, float], np.ndarray] = {}


def vignette_mask(w: int, h: int, strength: float) -> np.ndarray:
    key = (w, h, round(strength, 3))
    m = _vig_cache.get(key)
    if m is None:
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
        m = (1 - strength * np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6).astype(np.float32)
        if len(_vig_cache) > 8:
            _vig_cache.clear()
        _vig_cache[key] = m
    return m


def make_background(w: int, h: int, scale: float, color1, color2, style: str = "radial",
                    stars: float = 0.0, seed: int = 7) -> np.ndarray:
    """Solid, vertical or radial gradient background with an optional starfield."""
    c1 = np.asarray(color1, np.float32)
    c2 = np.asarray(color2, np.float32)
    if style == "solid":
        bg = np.empty((h, w, 3), np.float32)
        bg[:] = c1
    else:
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        if style == "vertical":
            u = y / max(h - 1, 1)
        else:  # radial: color2 in the centre, color1 at the edges
            u = 1 - np.clip(np.sqrt(((x - w / 2) / (w * 0.62)) ** 2 + ((y - h / 2) / (h * 0.62)) ** 2), 0, 1)
            u = u * u * (3 - 2 * u)
        bg = c1 + (c2 - c1) * u[..., None]
    if stars > 0:
        rng = np.random.default_rng(seed)
        n = int(stars * 900)
        sx = rng.uniform(0, w, n)
        sy = rng.uniform(0, h, n)
        b = rng.power(3.0, n) * 0.55 + 0.05
        tint = np.stack([np.full(n, 0.8), np.full(n, 0.88), np.ones(n)], axis=1) * b[:, None]
        cv = Canvas(w, h, scale, bg)
        sig = max(0.45, 0.7 * scale)
        cv.splat(np.stack([sx, sy], 1), b, (1, 1, 1), 1.0, sig, gain=1.2, colors=tint / np.maximum(b[:, None], 1e-6))
        bg = cv.rgb
    return bg.astype(np.float32)
