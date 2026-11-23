"""Per-frame render context shared by all objects."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from ..engine.assets import AssetStore
from ..engine.camera import Camera
from ..engine.color import parse_color
from ..engine.surface import Canvas
from ..engine.text import TextImage, parse_markup, render_text

if TYPE_CHECKING:  # pragma: no cover
    from .project import Project


@dataclass
class AxesTransform:
    """Maps data coordinates of a chart to design pixels."""

    x0: float
    y0: float
    w: float
    h: float
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    logx: bool = False
    logy: bool = False

    def _u(self, x, lo, hi, log):
        x = np.asarray(x, np.float64)
        if log:
            lo, hi = math.log10(max(lo, 1e-300)), math.log10(max(hi, 1e-300))
            with np.errstate(all="ignore"):
                x = np.log10(np.where(x > 0, x, np.nan))
        return (x - lo) / ((hi - lo) or 1e-12)

    def map(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        X = self.x0 + self._u(x, self.xmin, self.xmax, self.logx) * self.w
        Y = self.y0 + self.h - self._u(y, self.ymin, self.ymax, self.logy) * self.h
        return X, Y

    def map_x(self, x):
        return self.x0 + self._u(x, self.xmin, self.xmax, self.logx) * self.w

    def map_y(self, y):
        return self.y0 + self.h - self._u(y, self.ymin, self.ymax, self.logy) * self.h

    def scale_x(self, dx: float) -> float:
        return dx / ((self.xmax - self.xmin) or 1e-12) * self.w

    def scale_y(self, dy: float) -> float:
        return dy / ((self.ymax - self.ymin) or 1e-12) * self.h

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return self.x0, self.y0, self.x0 + self.w, self.y0 + self.h


def truncate_markup(text: str, frac: float) -> str:
    """First ``frac`` of the visible characters of marked-up text, markup preserved."""
    if frac >= 1:
        return text
    lines = parse_markup(text)
    total = sum(len(r.text) for line in lines for r in line)
    keep = int(round(total * max(0.0, frac)))
    out_lines = []
    for line in lines:
        parts = []
        for r in line:
            if keep <= 0:
                break
            s = r.text[:keep]
            keep -= len(s)
            esc = "".join("\\" + c if c in "_^*\\{}" else c for c in s)
            if r.level == -1:
                esc = "_{" + esc + "}"
            elif r.level == 1:
                esc = "^{" + esc + "}"
            if r.bold:
                esc = "**" + esc + "**"
            parts.append(esc)
        out_lines.append("".join(parts))
        if keep <= 0:
            break
    return "\n".join(out_lines)


class RenderContext:
    """Everything an object needs while drawing one frame."""

    def __init__(self, project: Project, assets: AssetStore, t: float, scale: float,
                 width: int, height: int, camera: Camera):
        self.project = project
        self.settings = project.settings
        self.palette = project.palette
        self.assets = assets
        self.t = float(t)
        self.s = float(scale)
        self.W, self.H = width, height
        self.camera = camera
        self.duration = project.duration
        self.font = self.settings.get("font", "Poppins")
        self.warnings: list[str] = []
        self.issues: list[dict] = []          # {"id", "prop", "message"} for the editor
        self.current: str | None = None       # id of the object being drawn
        self._axes: dict[str, Any] = {}
        self._color_cache: dict[Any, np.ndarray] = {}

    # ------------------------------------------------------------------ helpers
    def warn(self, msg: str, prop: str | None = None) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)
            self.issues.append({"id": self.current, "prop": prop, "message": msg})

    def derive(self, s: float | None = None, camera: Camera | None = None, current: str | None = None) -> RenderContext:
        """A copy for one object (inside a group): its own scale/camera, shared caches and warnings."""
        c = copy.copy(self)
        if s is not None:
            c.s = float(s)
        if camera is not None:
            c.camera = camera
        c.current = current
        return c

    def color(self, value) -> np.ndarray:
        if isinstance(value, (list, tuple, np.ndarray)):
            return parse_color(value)
        c = self._color_cache.get(value)
        if c is None:
            try:
                c = parse_color(value, self.palette)
            except ValueError as exc:
                self.warn(str(exc))
                c = np.array([0.55, 0.58, 0.65], np.float32)
            self._color_cache[value] = c
        return c

    def px(self, v: float) -> float:
        return float(v) * self.s

    def xy(self, p) -> np.ndarray:
        return np.asarray(p, np.float64) * self.s

    # ------------------------------------------------------------------ text
    def text_image(self, text: str, size: float, weight: str = "regular", align: str = "left",
                   line_spacing: float = 1.25, max_width: float = 0.0, family: str | None = None) -> TextImage:
        return render_text(text, round(size * self.s, 2), family or self.font, weight, align,
                           line_spacing, round(max_width * self.s, 1))

    def draw_text(self, cv: Canvas, text: str, x: float, y: float, size: float, color, *,
                  align: str = "left", valign: str = "top", opacity: float = 1.0, glow: float = 0.0,
                  weight: str = "regular", line_spacing: float = 1.25, max_width: float = 0.0,
                  progress: float = 1.0, scale: float = 1.0, family: str | None = None,
                  background=None, background_alpha: float = 0.0, background_pad: float = 10.0):
        """Draw marked-up text anchored at design point (x, y). Returns bbox in output px."""
        if not text or opacity <= 0:
            return None
        if progress < 1:
            text = truncate_markup(text, progress)
            if not text:
                return None
        img = self.text_image(text, size * scale, weight, align, line_spacing, max_width * scale, family)
        if img.width <= 0:
            return None
        left, top, w_in, h_in = self._place(img, x, y, align, valign)
        pad = img.pad
        if background is not None and background_alpha > 0:
            from ..engine.surface import rounded_rect
            bp = background_pad * self.s
            rr = rounded_rect(left - bp, top - bp * 0.6, w_in + 2 * bp, h_in + 1.2 * bp, (h_in + 1.2 * bp) / 2)
            cv.polygon(rr, fill=background, fill_alpha=background_alpha * opacity)
        cv.blit(img.mask, left - pad, top - pad, color=color, alpha=opacity, glow=glow)
        return (left, top, left + w_in, top + h_in)

    def text_bounds(self, text: str, x: float, y: float, size: float, *, align: str = "left", valign: str = "top",
                    weight: str = "regular", line_spacing: float = 1.25, max_width: float = 0.0,
                    scale: float = 1.0, family: str | None = None):
        """Where :meth:`draw_text` would put the text (bbox in output px), without drawing it."""
        if not text:
            return None
        img = self.text_image(text, size * scale, weight, align, line_spacing, max_width * scale, family)
        if img.width <= 0:
            return None
        left, top, w_in, h_in = self._place(img, x, y, align, valign)
        return (left, top, left + w_in, top + h_in)

    def _place(self, img, x: float, y: float, align: str, valign: str):
        X, Y = x * self.s, y * self.s
        pad = img.pad
        w_in, h_in = img.width - 2 * pad, img.height - 2 * pad
        if align == "center":
            left = X - w_in / 2
        elif align == "right":
            left = X - w_in
        else:
            left = X
        if valign == "middle":
            top = Y - h_in / 2
        elif valign == "bottom":
            top = Y - h_in
        elif valign == "baseline":
            top = Y - (img.baseline - pad)
        else:
            top = Y
        return left, top, w_in, h_in

    # ------------------------------------------------------------------ charts
    def axes(self, ref: str) -> AxesTransform | None:
        if not ref:
            return None
        if ref in self._axes:
            return self._axes[ref]
        obj = self.project.find(ref)
        tr = None
        if obj is not None and obj.TYPE == "axes":
            v = obj.resolve(self.t, self)
            xr, yr = v["x_range"], v["y_range"]
            tr = AxesTransform(float(v.position[0]), float(v.position[1]), float(v.size[0]), float(v.size[1]),
                               float(xr[0]), float(xr[1]), float(yr[0]), float(yr[1]),
                               bool(v.log_x), bool(v.log_y))
        self._axes[ref] = tr
        return tr
