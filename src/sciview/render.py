"""Turning a project into pixels. ``Renderer.frame(t)`` is a pure function of time."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from .engine.assets import AssetStore
from .engine.surface import Canvas, make_background
from .model.context import RenderContext

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project


@dataclass
class FrameInfo:
    """Extra information about a rendered frame (used by the editor)."""

    boxes: list[dict] = field(default_factory=list)   # {"id", "x0", "y0", "x1", "y1"} in design px
    warnings: list[str] = field(default_factory=list)
    ms: float = 0.0


def out_size(project: Project, scale: float) -> tuple[int, int]:
    """Output size for a scale factor, rounded to even numbers (needed by H.264)."""
    w, h = project.size
    W = max(2, int(round(w * scale / 2)) * 2)
    H = max(2, int(round(h * scale / 2)) * 2)
    return W, H


class Renderer:
    """Renders frames of a project. Keeps caches (text, images, particles) between frames."""

    def __init__(self, project: Project, base_dir=None):
        self.project = project
        self.assets = AssetStore(base_dir or project.base_dir)
        self._bg: dict[tuple, np.ndarray] = {}

    def background(self, W: int, H: int, scale: float, ctx: RenderContext) -> np.ndarray:
        s = self.project.settings
        key = (W, H, s["background"], s["background2"], s["background_style"], round(float(s["stars"]), 3),
               tuple(sorted(self.project.palette.items())))
        bg = self._bg.get(key)
        if bg is None:
            bg = make_background(W, H, scale, ctx.color(s["background"]), ctx.color(s["background2"]),
                                 s["background_style"], float(s["stars"]))
            if len(self._bg) > 6:
                self._bg.clear()
            self._bg[key] = bg
        return bg

    def frame(self, t: float, scale: float = 1.0, info: FrameInfo | None = None) -> np.ndarray:
        t0 = time.perf_counter()
        proj = self.project
        self.assets.base_dir = proj.base_dir
        W, H = out_size(proj, scale)
        s = W / proj.size[0]
        cam = proj.camera_at(t, W, H, s)
        ctx = RenderContext(proj, self.assets, t, s, W, H, cam)
        cv = Canvas(W, H, s, self.background(W, H, s, ctx))
        dur = proj.duration

        items3d, items2d = [], []
        for obj in proj.objects:
            st = obj.state(t, dur)
            if st is None:
                continue
            try:
                v = obj.resolve(t, ctx)
            except Exception as exc:  # pragma: no cover - defensive
                ctx.warn(f"{obj.name}: {exc}")
                continue
            if obj.IS_3D:
                try:
                    d = obj.depth(ctx, v)
                except Exception:
                    d = 0.0
                items3d.append((d, obj, v, st))
            else:
                items2d.append((obj, v, st))

        boxes = []

        def run(obj, v, st):
            try:
                b = obj.draw(cv, ctx, v, st)
            except Exception as exc:
                msg = str(exc) or type(exc).__name__
                ctx.warn(f"{obj.name}: {msg}")
                return None
            if b is not None:
                boxes.append({"id": obj.id, "x0": b[0] / s, "y0": b[1] / s, "x1": b[2] / s, "y1": b[3] / s})
            return b

        items3d.sort(key=lambda it: -it[0])
        drawn3d = []
        for _d, obj, v, st in items3d:
            b = run(obj, v, st)
            drawn3d.append((obj, v, st, b))
        for obj, v, st, _b in drawn3d:  # labels on top of all 3D geometry
            if obj.HAS_LABEL and v.get("label"):
                try:
                    self._label(cv, ctx, obj, v, st)
                except Exception as exc:
                    ctx.warn(f"{obj.name} label: {exc}")
        for obj, v, st in items2d:
            run(obj, v, st)

        img = cv.finish(float(proj.settings["bloom"]), float(proj.settings["vignette"]),
                        ctx.color(proj.settings["background"]) * 0.5)
        if info is not None:
            info.boxes = boxes
            info.warnings = ctx.warnings
            info.ms = (time.perf_counter() - t0) * 1000
        return img

    @staticmethod
    def _label(cv, ctx, obj, v, st):
        pts = obj.label_anchor(ctx, v)
        if pts is None or len(pts) == 0:
            return
        xy, z = ctx.camera.project(np.asarray(pts, np.float64).reshape(-1, 3))
        if (z <= ctx.camera.near).all():
            return
        xy = xy[z > ctx.camera.near] / ctx.s + (st.dx, st.dy)
        x0, y0 = xy.min(0)
        x1, y1 = xy.max(0)
        gap = 10.0
        pos = v.label_position
        if pos == "below":
            x, y, al, va = (x0 + x1) / 2, y1 + gap, "center", "top"
        elif pos == "left":
            x, y, al, va = x0 - gap, (y0 + y1) / 2, "right", "middle"
        elif pos == "right":
            x, y, al, va = x1 + gap, (y0 + y1) / 2, "left", "middle"
        elif pos == "center":
            x, y, al, va = (x0 + x1) / 2, (y0 + y1) / 2, "center", "middle"
        else:
            x, y, al, va = (x0 + x1) / 2, y0 - gap, "center", "bottom"
        x += float(v.label_offset[0])
        y += float(v.label_offset[1])
        ctx.draw_text(cv, v.label, x, y, v.label_size, v.label_color, align=al, valign=va,
                      opacity=v.opacity * st.opacity, glow=0.15)


def render_frame(project: Project, t: float, scale: float = 1.0) -> np.ndarray:
    return Renderer(project).frame(t, scale)


def describe_error(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()
