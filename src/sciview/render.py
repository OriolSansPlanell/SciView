"""Turning a project into pixels. ``Renderer.frame(t)`` is a pure function of time.

Two things make frames cheaper without changing a single pixel:

* objects that look the same as in the previous frames (no keyframes, no running effect,
  no dependence on time, camera still for 3D) are drawn once into a cached layer; runs of
  such objects in the drawing order share one layer (see :class:`~sciview.engine.surface.Canvas`);
* the glow is only computed around what glows.

Groups add a transform per member: 2D members are drawn with a scaled context and a canvas
offset, 3D members with a camera moved into the group's coordinates.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from .engine.assets import AssetStore
from .engine.camera import Camera, rotation_matrix
from .engine.surface import Canvas, make_background
from .model.context import RenderContext

if TYPE_CHECKING:  # pragma: no cover
    from .model.base import SceneObject, State, Values
    from .model.project import Project


@dataclass
class FrameInfo:
    """Extra information about a rendered frame (used by the editor)."""

    boxes: list[dict] = field(default_factory=list)   # {"id", "x0", "y0", "x1", "y1"} in design px
    warnings: list[str] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)  # {"id", "prop", "message"}
    ms: float = 0.0
    cached: int = 0                                     # objects taken from the layer cache


def out_size(project: Project, scale: float) -> tuple[int, int]:
    """Output size for a scale factor, rounded to even numbers (needed by H.264)."""
    w, h = project.size
    W = max(2, int(round(w * scale / 2)) * 2)
    H = max(2, int(round(h * scale / 2)) * 2)
    return W, H


# --------------------------------------------------------------------------- group transforms
@dataclass
class Xform:
    """Accumulated transform of an object's groups, applied when it is drawn."""

    a: float = 1.0                     # 2D: design point p -> a * p + b
    b: tuple[float, float] = (0.0, 0.0)
    A: np.ndarray | None = None        # 3D: world = A @ local + c (None = identity)
    c: np.ndarray | None = None
    sig: float = 1.0                   # 3D uniform scale (product)
    screen: tuple[float, float] = (0.0, 0.0)   # 3D members: shift on screen, design px
    opacity: float = 1.0
    static: bool = True                # no group in the chain changes over time here
    key: tuple = ()

    @property
    def identity(self) -> bool:
        return not self.key


IDENTITY = Xform()


@dataclass
class Item:
    obj: SceneObject
    v: Values
    st: State
    xf: Xform
    kind: str                          # "geom" | "label" | "2d"
    static: bool = False
    key: Any = None
    depth: float = 0.0


class Renderer:
    """Renders frames of a project. Keeps caches (text, images, particles, layers) between frames."""

    LAYER_BUDGET = 256 * 1024 * 1024   # bytes of cached layers per renderer

    def __init__(self, project: Project, base_dir=None, cache: bool = True):
        self.project = project
        self.assets = AssetStore(base_dir or project.base_dir)
        self.cache_enabled = cache
        self._bg: dict[tuple, np.ndarray] = {}
        self._layers: OrderedDict[tuple, dict] = OrderedDict()
        self._layer_bytes = 0
        self.stats = {"hits": 0, "misses": 0}

    # ------------------------------------------------------------------ background
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

    # ------------------------------------------------------------------ groups
    def _group_xforms(self, t: float, ctx: RenderContext) -> dict[str, Xform | None]:
        """Transform of every group (None = the group is hidden at t)."""
        proj = self.project
        dur = proj.duration
        out: dict[str, Xform | None] = {}
        groups = {o.id: o for o in proj.objects if o.IS_GROUP}

        def solve(gid: str, stack: tuple = ()) -> Xform | None:
            if gid in out:
                return out[gid]
            g = groups.get(gid)
            if g is None or gid in stack:
                return IDENTITY
            st = g.state(t, dur)
            if st is None:
                out[gid] = None
                return None
            parent = solve(g.parent, stack + (gid,)) if g.parent else IDENTITY
            if parent is None:
                out[gid] = None
                return None
            v = g.resolve(t, ctx)
            sig = float(v.scale) * st.scale
            pv = np.asarray(v.pivot, np.float64)
            off = np.asarray(v.offset, np.float64) + (st.dx, st.dy)
            # this group's own map, then the parent's (outer) map
            a_g = sig
            b_g = pv * (1 - sig) + off
            a = parent.a * a_g
            b = tuple(parent.a * b_g + np.asarray(parent.b))
            R = rotation_matrix(*v.rotation) * sig
            p3 = np.asarray(v.pivot3d, np.float64)
            c_g = p3 - R @ p3 + np.asarray(v.position, np.float64)
            A_par = parent.A if parent.A is not None else np.eye(3)
            c_par = parent.c if parent.c is not None else np.zeros(3)
            A = A_par @ R
            c = A_par @ c_g + c_par
            screen = (parent.screen[0] + off[0], parent.screen[1] + off[1])
            opacity = parent.opacity * float(v.opacity) * st.opacity
            static = parent.static and (not g.keys or g.held(t)) and g.steady(t, dur)
            key = parent.key + ((gid, round(a, 6), round(b[0], 4), round(b[1], 4),
                                 tuple(np.round(A, 6).ravel()), tuple(np.round(c, 4)),
                                 round(screen[0], 4), round(screen[1], 4), round(opacity, 5)),)
            xf = Xform(a, b, A, c, parent.sig * sig, screen, opacity, static, key)
            out[gid] = xf
            return xf

        for gid in groups:
            solve(gid)
        return out

    @staticmethod
    def _local_camera(cam: Camera, xf: Xform) -> Camera:
        if xf.A is None:
            return cam
        try:
            Ainv = np.linalg.inv(xf.A)
        except np.linalg.LinAlgError:
            return cam
        eye = Ainv @ (cam.eye - xf.c)
        target = Ainv @ (cam.target - xf.c)
        up = Ainv @ np.asarray(cam.up, np.float64)
        n = float(np.linalg.norm(up))
        up = up / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])
        return Camera(eye=eye, target=target, width=cam.width, height=cam.height, fov=cam.fov,
                      offset=cam.offset, up=up, near=cam.near / max(xf.sig, 1e-9))

    # ------------------------------------------------------------------ cache keys
    def _fingerprint(self, obj: SceneObject, t: float) -> str:
        parts = [obj.TYPE, json.dumps(obj.props, sort_keys=True, default=str)]
        if obj.keys:
            parts.append(json.dumps(obj.keyed_values(t), sort_keys=True, default=str))
        for p in obj.all_props():
            if p.kind == "asset" and obj.props.get(p.name):
                try:
                    parts.append(str(os.stat(self.assets.resolve(obj.props[p.name])).st_mtime_ns))
                except OSError:
                    parts.append("missing")
        return "|".join(parts)

    def _static(self, obj: SceneObject, t: float, xf: Xform, cam_animated: bool) -> bool:
        if not self.cache_enabled or not xf.static or obj.depends_on_time():
            return False
        if obj.keys and not obj.held(t):
            return False
        if not obj.steady(t, self.project.duration):
            return False
        if obj.IS_3D and cam_animated:
            return False
        for ref in obj.refs():
            r = self.project.find(ref)
            if r is not None and ((r.keys and not r.held(t)) or not r.steady(t, self.project.duration)):
                return False
        return True

    # ------------------------------------------------------------------ frame
    def frame(self, t: float, scale: float = 1.0, info: FrameInfo | None = None) -> np.ndarray:
        t0 = time.perf_counter()
        proj = self.project
        self.assets.base_dir = proj.base_dir
        W, H = out_size(proj, scale)
        s = W / proj.size[0]
        cam = proj.camera_at(t, W, H, s)
        cam_animated = bool(proj.camera.keys)
        ctx = RenderContext(proj, self.assets, t, s, W, H, cam)
        cv = Canvas(W, H, s, self.background(W, H, s, ctx))
        dur = proj.duration
        gx = self._group_xforms(t, ctx)
        cam_key = (tuple(np.round(cam.eye, 5)), tuple(np.round(cam.target, 5)), round(cam.fov, 4),
                   tuple(round(o, 3) for o in cam.offset))

        items3d: list[Item] = []
        items2d: list[Item] = []
        for obj in proj.objects:
            if obj.IS_GROUP:
                continue
            xf = IDENTITY
            if obj.parent:
                xf = gx.get(obj.parent, IDENTITY)
                if xf is None:
                    continue
            st = obj.state(t, dur)
            if st is None:
                continue
            if xf.opacity != 1.0:
                st.opacity *= xf.opacity
                if st.opacity <= 1e-4:
                    continue
            try:
                v = obj.resolve(t, ctx)
            except Exception as exc:  # pragma: no cover - defensive
                ctx.current = obj.id
                ctx.warn(f"{obj.name}: {exc}")
                continue
            static = self._static(obj, t, xf, cam_animated)
            key = None
            if static:
                key = (obj.id, self._fingerprint(obj, t), _st_key(st), xf.key)
                if obj.IS_3D:
                    key += (cam_key,)
                for ref in obj.refs():
                    r = proj.find(ref)
                    if r is not None:
                        key += (self._fingerprint(r, t),)
            it = Item(obj, v, st, xf, "geom" if obj.IS_3D else "2d", static, key)
            if obj.IS_3D:
                try:
                    lctx = ctx.derive(camera=self._local_camera(cam, xf), current=obj.id)
                    it.depth = obj.depth(lctx, v) * xf.sig
                except Exception:
                    it.depth = 0.0
                items3d.append(it)
            else:
                items2d.append(it)

        items3d.sort(key=lambda it: -it.depth)
        labels = [Item(it.obj, it.v, it.st, it.xf, "label", it.static, (it.key, "label") if it.static else None)
                  for it in items3d if it.obj.HAS_LABEL and it.v.get("label")]
        order = items3d + labels + items2d

        boxes: list[dict] = []
        cached_objects = 0
        i = 0
        palette_key = (tuple(sorted(proj.palette.items())), ctx.font, W, H, round(s, 6))
        while i < len(order):
            if not order[i].static:
                self._draw_item(cv, ctx, cam, order[i], boxes)
                i += 1
                continue
            j = i
            while j < len(order) and order[j].static:
                j += 1
            run = order[i:j]
            rkey = (palette_key, tuple(it.key for it in run))
            entry = self._layers.get(rkey)
            if entry is None:
                self.stats["misses"] += 1
                t_draw = time.perf_counter()
                layer_cv = Canvas(W, H, s, layer=True)
                run_boxes: list[dict] = []
                n_warn = len(ctx.issues)
                for it in run:
                    self._draw_item(layer_cv, ctx, cam, it, run_boxes)
                lay = layer_cv.extract()
                entry = {"layer": lay, "boxes": run_boxes, "issues": ctx.issues[n_warn:],
                         "draw": time.perf_counter() - t_draw, "paste": None, "use": True}
                self._store(rkey, entry)
                cv.paste(lay)
                boxes.extend(run_boxes)
            elif entry["use"]:
                self.stats["hits"] += 1
                self._layers.move_to_end(rkey)
                for iss in entry["issues"]:
                    ctx.current = iss["id"]
                    ctx.warn(iss["message"], iss["prop"])
                t_paste = time.perf_counter()
                cv.paste(entry["layer"])
                if entry["paste"] is None:
                    entry["paste"] = time.perf_counter() - t_paste
                    # a layer that costs as much to paste as to draw is not worth keeping
                    if entry["paste"] > 0.8 * entry["draw"]:
                        entry["use"] = False
                boxes.extend(entry["boxes"])
                cached_objects += len(run)
            else:
                self._layers.move_to_end(rkey)
                for it in run:
                    self._draw_item(cv, ctx, cam, it, boxes)
            i = j

        cv.set_offset(0, 0)
        # bounding boxes of groups = union of their members
        group_boxes: dict[str, list[float]] = {}
        for b in boxes:
            o = proj.find(b["id"])
            if o is None:
                continue
            for g in proj.ancestors(o):
                gb = group_boxes.get(g.id)
                group_boxes[g.id] = [b["x0"], b["y0"], b["x1"], b["y1"]] if gb is None else [
                    min(gb[0], b["x0"]), min(gb[1], b["y0"]), max(gb[2], b["x1"]), max(gb[3], b["y1"])]
        boxes = [{"id": k, "x0": v[0], "y0": v[1], "x1": v[2], "y1": v[3], "group": True}
                 for k, v in group_boxes.items()] + boxes

        img = cv.finish(float(proj.settings["bloom"]), float(proj.settings["vignette"]),
                        ctx.color(proj.settings["background"]) * 0.5)
        if info is not None:
            info.boxes = boxes
            info.warnings = ctx.warnings
            info.issues = ctx.issues
            info.cached = cached_objects
            info.ms = (time.perf_counter() - t0) * 1000
        return img

    def _store(self, key: tuple, entry: dict) -> None:
        lay = entry["layer"]
        size = lay.nbytes if lay is not None else 64
        while self._layers and self._layer_bytes + size > self.LAYER_BUDGET:
            _, old = self._layers.popitem(last=False)
            self._layer_bytes -= old["layer"].nbytes if old["layer"] is not None else 64
        if size <= self.LAYER_BUDGET:
            self._layers[key] = entry
            self._layer_bytes += size

    def clear_cache(self) -> None:
        self._layers.clear()
        self._layer_bytes = 0

    def _draw_item(self, cv: Canvas, ctx: RenderContext, cam: Camera, it: Item, boxes: list[dict]) -> None:
        obj, xf, s = it.obj, it.xf, ctx.s
        if obj.IS_3D:
            octx = ctx.derive(camera=self._local_camera(cam, xf), current=obj.id)
            ox, oy = xf.screen[0] * s, xf.screen[1] * s
        else:
            octx = ctx.derive(s=s * xf.a, current=obj.id)
            ox, oy = xf.b[0] * s, xf.b[1] * s
        cv.set_offset(ox, oy)
        try:
            if it.kind == "label":
                self._label(cv, octx, obj, it.v, it.st)
                return
            b = obj.draw(cv, octx, it.v, it.st)
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            octx.warn(f"{obj.name}{' label' if it.kind == 'label' else ''}: {msg}", _guess_prop(obj, msg))
            return
        finally:
            cv.set_offset(0, 0)
        if b is not None:
            boxes.append({"id": obj.id, "x0": (b[0] + ox) / s, "y0": (b[1] + oy) / s,
                          "x1": (b[2] + ox) / s, "y1": (b[3] + oy) / s})

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


def _st_key(st) -> tuple:
    return (round(st.opacity, 5), round(st.dx, 3), round(st.dy, 3), round(st.scale, 5), round(st.progress, 5))


def _guess_prop(obj: SceneObject, msg: str) -> str | None:
    """Which property a drawing error is about, for the editor (missing file, unknown column ...)."""
    for p in obj.all_props():
        val = obj.props.get(p.name)
        if not isinstance(val, str) or not val:
            continue
        if p.kind == "asset" and val in msg:
            return p.name
    for p in obj.all_props():
        val = obj.props.get(p.name)
        if p.kind == "text" and isinstance(val, str) and val and f"'{val}'" in msg and "column" in msg:
            return p.name
    return None


def render_frame(project: Project, t: float, scale: float = 1.0) -> np.ndarray:
    return Renderer(project).frame(t, scale)


def describe_error(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()
