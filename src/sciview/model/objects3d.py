"""3D objects: drawn with the scene camera and sorted back to front."""
from __future__ import annotations

import math

import numpy as np

from ..engine.camera import rotation_matrix
from ..engine.color import COLORMAPS, apply_colormap
from ..engine.surface import arrow_head, truncate_path
from . import data as seqdata
from .base import Prop, SceneObject, State, Values, parse_array, register

G_GEO, G_LOOK, G_IMG, G_DATA, G_MOTION = "Geometry", "Appearance", "Image", "Data", "Particles"


def _bbox(xy: np.ndarray):
    xy = np.asarray(xy).reshape(-1, 2)
    xy = xy[np.isfinite(xy).all(axis=1)]
    if len(xy) == 0:
        return None
    return (float(xy[:, 0].min()), float(xy[:, 1].min()), float(xy[:, 0].max()), float(xy[:, 1].max()))


def _project(ctx, pts, st: State, about=None):
    """Project world points; apply pop scale about ``about`` and slide offsets."""
    pts = np.asarray(pts, np.float64).reshape(-1, 3)
    if st.scale != 1 and about is not None:
        pts = about + (pts - about) * st.scale
    xy, z = ctx.camera.project(pts)
    xy = xy + np.array([st.dx, st.dy]) * ctx.s
    return xy, z


def _split_runs(mask: np.ndarray) -> list[tuple[int, int, bool]]:
    """Contiguous runs of a boolean array as (start, end_exclusive, value)."""
    if len(mask) == 0:
        return []
    edges = np.flatnonzero(np.diff(mask.astype(np.int8))) + 1
    bounds = np.concatenate([[0], edges, [len(mask)]])
    return [(int(a), int(b), bool(mask[a])) for a, b in zip(bounds[:-1], bounds[1:])]


def _draw_depth_line(cv, xy, front, color, alpha, width, glow, back_alpha=0.4, progress=1.0):
    """Polyline whose back-facing part is dimmer (spheres, cylinder rings)."""
    if progress < 1:
        n = max(2, int(math.ceil(len(xy) * progress)))
        xy, front = xy[:n], front[:n]
    for a, b, f in _split_runs(front):
        seg = xy[max(0, a - 1):b + 1] if a > 0 else xy[a:b + 1]
        cv.polyline(seg, color, alpha * (1.0 if f else back_alpha), width, glow * (1.0 if f else 0.3))


BOX_EDGES = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
BOX_FACES = [(0, 2, 6, 4), (1, 3, 7, 5), (0, 1, 5, 4), (2, 3, 7, 6), (0, 1, 3, 2), (4, 5, 7, 6)]


def box_corners(center, size, rotation) -> np.ndarray:
    sgn = np.array([[(i & 1) * 2 - 1, ((i >> 1) & 1) * 2 - 1, ((i >> 2) & 1) * 2 - 1] for i in range(8)], np.float64)
    local = sgn * (np.asarray(size, np.float64) / 2)
    return local @ rotation_matrix(*rotation).T + np.asarray(center, np.float64)


def draw_box(cv, ctx, corners, st, about, fill, fill_alpha, edge, edge_alpha, width, glow, progress=1.0):
    xy, z = _project(ctx, corners, st, about)
    if (z <= ctx.camera.near).any():
        return None
    if fill_alpha > 0:
        order = sorted(BOX_FACES, key=lambda f: -float(z[list(f)].mean()))
        for f in order:
            cv.polygon(xy[list(f)], fill=fill, fill_alpha=fill_alpha)
    if edge_alpha > 0 and width > 0:
        if progress >= 1:
            cv.lines([xy[[a, b]] for a, b in BOX_EDGES], edge, edge_alpha, width, glow)
        else:
            cv.lines([truncate_path(xy[[a, b]], progress) for a, b in BOX_EDGES], edge, edge_alpha, width, glow)
    return _bbox(xy)


class Object3D(SceneObject):
    IS_3D = True
    CATEGORY = "3D scene"

    def center_of(self, v: Values) -> np.ndarray:
        return np.asarray(v.get("center", (0, 0, 0)), np.float64)

    def depth(self, ctx, v):
        return ctx.camera.depth(self.center_of(v))


@register
class Box(Object3D):
    TYPE, LABEL, ICON = "box", "Box", "cube"
    DESCRIPTION = "Wireframe box with see-through faces: sources, detectors, instruments."
    HAS_PROGRESS = True
    PROPS = [
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("size", "vec3", [10, 10, 10], group=G_GEO),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO, help="Degrees about x, y and z"),
        Prop("edge_color", "color", "teal", group=G_LOOK),
        Prop("edge_width", "number", 2.0, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("fill_color", "color", "teal", group=G_LOOK),
        Prop("fill_opacity", "number", 0.08, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def corners(self, v):
        return box_corners(v.center, v.size, v.rotation)

    def label_anchor(self, ctx, v):
        return self.corners(v)

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        return draw_box(cv, ctx, self.corners(v), st, v.center, v.fill_color, v.fill_opacity * a,
                        v.edge_color, a, v.edge_width * ctx.s, v.glow, st.progress)


@register
class Cylinder(Object3D):
    TYPE, LABEL, ICON = "cylinder", "Cylinder", "cylinder"
    DESCRIPTION = "Wireframe cylinder: samples, tubes, vessels, pipes."
    HAS_PROGRESS = True
    PROPS = [
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("radius", "number", 5.0, min=0, step=0.1, group=G_GEO),
        Prop("height", "number", 12.0, min=0, step=0.1, group=G_GEO),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO, help="Degrees; the axis is z before rotation"),
        Prop("rings", "int", 2, min=2, max=40, group=G_GEO, help="Circles along the height"),
        Prop("lines", "int", 0, min=0, max=64, group=G_GEO, help="Extra lines along the length"),
        Prop("edge_color", "color", "cream", group=G_LOOK),
        Prop("edge_width", "number", 1.5, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("fill_color", "color", "cream", group=G_LOOK),
        Prop("fill_opacity", "number", 0.06, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def _frame(self, v):
        R = rotation_matrix(*v.rotation)
        return R @ np.array([0, 0, 1.0]), R @ np.array([1.0, 0, 0]), R @ np.array([0, 1.0, 0])

    def label_anchor(self, ctx, v):
        ax, u, w = self._frame(v)
        c, r, h = v.center, v.radius, v.height / 2
        return np.array([c + s1 * ax * h + s2 * u * r + s3 * w * r for s1 in (-1, 1) for s2 in (-1, 1) for s3 in (-1, 1)])

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        ax, u, w = self._frame(v)
        c = v.center
        r, H = float(v.radius), float(v.height)
        ang = np.radians(np.linspace(0, 360, 97))
        circ = np.cos(ang)[:, None] * u + np.sin(ang)[:, None] * w
        d = ctx.camera.eye - c
        dp = d - (d @ ax) * ax
        dpn = dp / (np.linalg.norm(dp) or 1.0)
        front = (circ @ dpn) > -1e-9
        heights = np.linspace(-H / 2, H / 2, max(2, int(v.rings)))
        rings_xy = []
        bbox_pts = []
        for h in heights:
            pts = c + ax * h + circ * r
            xy, z = _project(ctx, pts, st, c)
            if (z <= ctx.camera.near).any():
                return None
            rings_xy.append(xy)
            bbox_pts.append(xy)
        allxy = np.vstack(bbox_pts)
        if v.fill_opacity > 0:
            import cv2
            hull = cv2.convexHull(allxy.astype(np.float32)).reshape(-1, 2)
            cv.polygon(hull, fill=v.fill_color, fill_alpha=v.fill_opacity * a)
        width = v.edge_width * ctx.s
        for xy in rings_xy:
            _draw_depth_line(cv, xy, front, v.edge_color, a, width, v.glow, progress=st.progress)
        phi = math.atan2(float(dp @ w), float(dp @ u))
        angles = [phi + math.pi / 2, phi - math.pi / 2]
        n = int(v.lines)
        angles += [phi + math.pi / 2 + 2 * math.pi * (k + 0.5) / n for k in range(n)] if n else []
        segs = []
        for k, an in enumerate(angles):
            p = math.cos(an) * u + math.sin(an) * w
            ends = np.array([c - ax * H / 2 + p * r, c + ax * H / 2 + p * r])
            xy, _ = _project(ctx, ends, st, c)
            segs.append((truncate_path(xy, st.progress), k < 2 or float(p @ dpn) >= 0))
        cv.lines([s for s, f in segs if f], v.edge_color, a, width, v.glow)
        cv.lines([s for s, f in segs if not f], v.edge_color, a * 0.4, width, v.glow * 0.3)
        return _bbox(allxy)


@register
class Sphere(Object3D):
    TYPE, LABEL, ICON = "sphere", "Sphere", "sphere"
    DESCRIPTION = "Wireframe sphere: atoms, nuclei, droplets, planets."
    HAS_PROGRESS = True
    PROPS = [
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("radius", "number", 6.0, min=0, step=0.1, group=G_GEO),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO),
        Prop("meridians", "int", 6, min=0, max=48, group=G_GEO),
        Prop("parallels", "int", 5, min=0, max=48, group=G_GEO),
        Prop("edge_color", "color", "blue", group=G_LOOK),
        Prop("edge_width", "number", 1.2, min=0, max=20, step=0.1, group=G_LOOK),
        Prop("fill_color", "color", "blue", group=G_LOOK),
        Prop("fill_opacity", "number", 0.12, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def label_anchor(self, ctx, v):
        r = v.radius
        return v.center + np.array([[sx * r, sy * r, sz * r] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        c = v.center
        r = float(v.radius) * st.scale
        cam = ctx.camera
        z = cam.depth(c)
        if z <= r:
            return None
        (cxy,), _ = _project(ctx, c[None], st)
        rp = cam.focal * r / math.sqrt(max(z * z - r * r, 1e-9))
        cv.circle(cxy[0], cxy[1], rp, fill=v.fill_color, fill_alpha=v.fill_opacity * a,
                  stroke=v.edge_color, stroke_alpha=a, width=v.edge_width * ctx.s, glow=v.glow)
        R = rotation_matrix(*v.rotation)
        view = (cam.eye - c) / np.linalg.norm(cam.eye - c)
        t = np.radians(np.linspace(0, 360, 97))
        width = v.edge_width * ctx.s
        for k in range(int(v.meridians)):
            ph = math.pi * k / max(1, int(v.meridians))
            loc = np.stack([np.cos(t) * math.cos(ph), np.cos(t) * math.sin(ph), np.sin(t)], 1)
            pts = c + (loc @ R.T) * r
            xy, _ = _project(ctx, pts, State(dx=st.dx, dy=st.dy))
            _draw_depth_line(cv, xy, ((pts - c) @ view) >= 0, v.edge_color, a * 0.9, width, v.glow * 0.7,
                             back_alpha=0.25, progress=st.progress)
        for k in range(int(v.parallels)):
            th = math.pi * (k + 1) / (int(v.parallels) + 1) - math.pi / 2
            loc = np.stack([np.cos(t) * math.cos(th), np.sin(t) * math.cos(th), np.full_like(t, math.sin(th))], 1)
            pts = c + (loc @ R.T) * r
            xy, _ = _project(ctx, pts, State(dx=st.dx, dy=st.dy))
            _draw_depth_line(cv, xy, ((pts - c) @ view) >= 0, v.edge_color, a * 0.9, width, v.glow * 0.7,
                             back_alpha=0.25, progress=st.progress)
        return (cxy[0] - rp, cxy[1] - rp, cxy[0] + rp, cxy[1] + rp)


def prepare_image(ctx, v, key_extra=(), max_side=640):
    """Colour image (h,w,3) for an image property group, with optional neutron-by-neutron build-up.
    A file pattern shows the file of the current step."""
    rel = seqdata.current_file(ctx, v, "image")
    img = ctx.assets.image_resized(rel, max_side)
    vmin = None if v.vmin == v.vmax else float(v.vmin)
    vmax = None if v.vmin == v.vmax else float(v.vmax)
    counts = float(v.get("counts", 0))
    buildup = float(np.clip(v.get("buildup", 1.0), 0, 1))
    if img.ndim == 3 and img.shape[2] == 4:
        rgb, alpha = img[..., :3], img[..., 3]
    elif img.ndim == 3:
        rgb, alpha = img[..., :3], None
    else:
        rgb, alpha = None, None
    if counts > 0 and buildup < 1.0 + 1e-9:
        gray = img if img.ndim == 2 else img[..., :3].mean(axis=2)
        key = ("buildup", rel, ctx.assets.stamp(rel), img.shape, counts, vmin, vmax, int(v.get("seed", 0)))

        def make():
            lo = float(np.nanmin(gray)) if vmin is None else vmin
            hi = float(np.nanmax(gray)) if vmax is None else vmax
            norm = np.clip((gray - lo) / ((hi - lo) or 1e-9), 0, 1)
            rng = np.random.default_rng(1234 + int(v.get("seed", 0)))
            C = rng.poisson(norm * counts).astype(np.float32)
            return norm.astype(np.float32), C, rng.random(norm.shape).astype(np.float32)
        norm, C, r = ctx.assets.memo(key, make)
        shown = np.floor(C * buildup + r) / counts
        if rgb is None:
            col = apply_colormap(shown, v.colormap, 0.0, 1.0, float(v.get("gamma", 1.0)))
        else:
            col = rgb * np.clip(shown / np.maximum(norm, 1e-3), 0, 1.5)[..., None]
        return col.astype(np.float32), alpha
    if rgb is None:
        key = ("cmap", rel, ctx.assets.stamp(rel), img.shape, v.colormap, vmin, vmax, float(v.get("gamma", 1.0)))
        col = ctx.assets.memo(key, lambda: apply_colormap(img, v.colormap, vmin, vmax, float(v.get("gamma", 1.0))))
    else:
        col = rgb
    if buildup < 1:
        col = col * buildup
    return col.astype(np.float32), alpha


IMAGE_PROPS = [
    Prop("image", "asset", "", accept="image", group=G_IMG, help="PNG, JPG, TIFF (16-bit is fine) or .npy array"),
    Prop("colormap", "enum", "gray", options=COLORMAPS, group=G_IMG, help="Used for single-channel images"),
    Prop("vmin", "number", 0.0, group=G_IMG, help="Data value shown black. vmin = vmax uses the data range"),
    Prop("vmax", "number", 0.0, group=G_IMG),
    Prop("gamma", "number", 1.0, min=0.1, max=5, step=0.05, group=G_IMG),
    Prop("buildup", "number", 1.0, label="Build-up", min=0, max=1, step=0.01, group=G_IMG,
         help="Animate from 0 to 1 to build the image up count by count"),
    Prop("counts", "number", 0.0, min=0, step=1, group=G_IMG,
         help="Counts per bright pixel for the build-up noise. 0 = smooth fade"),
    Prop("pixelated", "bool", False, group=G_IMG, help="Show pixels as sharp squares"),
    *seqdata.seq_props(G_IMG),
]


@register
class Screen(Object3D):
    TYPE, LABEL, ICON = "screen", "Screen / detector", "screen"
    DESCRIPTION = "A flat panel that can show an image: detectors, scintillators, samples, slides."
    PROPS = [
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("size", "vec2", [20, 20], group=G_GEO, help="Width and height"),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO, help="Degrees. At 0 the panel faces along x"),
        Prop("thickness", "number", 0.0, min=0, step=0.1, group=G_GEO, help="Depth of a housing behind the panel"),
        Prop("frame_color", "color", "teal", group=G_LOOK),
        Prop("frame_width", "number", 2.0, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("fill_color", "color", "navy", group=G_LOOK),
        Prop("fill_opacity", "number", 0.35, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("image_opacity", "number", 1.0, min=0, max=1, step=0.01, group=G_IMG),
        *IMAGE_PROPS,
        Prop("image_glow", "number", 0.35, min=0, max=3, step=0.05, group=G_IMG),
        Prop("flip", "bool", False, group=G_IMG, help="Mirror the image left-right"),
    ]

    def depends_on_time(self) -> bool:
        return super().depends_on_time() or seqdata.plays_by_itself(self, "image")

    def _axes(self, v):
        R = rotation_matrix(*v.rotation)
        return R @ np.array([1.0, 0, 0]), R @ np.array([0, 1.0, 0]), R @ np.array([0, 0, 1.0])

    def face(self, v):
        n, u, w = self._axes(v)
        c = v.center - n * float(v.thickness) / 2
        hw, hh = float(v.size[0]) / 2, float(v.size[1]) / 2
        # corners tl, tr, br, bl as seen from the side the panel faces (-normal, where the beam comes from)
        return np.array([c + u * hw + w * hh, c - u * hw + w * hh, c - u * hw - w * hh, c + u * hw - w * hh])

    def label_anchor(self, ctx, v):
        n, _, _ = self._axes(v)
        f = self.face(v)
        return np.vstack([f, f + n * float(v.thickness)])

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        n, u, w = self._axes(v)
        quad3 = self.face(v)
        if v.thickness > 0:
            size = [float(v.thickness), float(v.size[0]), float(v.size[1])]
            corners = box_corners(v.center, size, v.rotation)
            draw_box(cv, ctx, corners, st, v.center, v.fill_color, v.fill_opacity * a * 0.5,
                     v.frame_color, a * 0.55, v.frame_width * ctx.s * 0.75, v.glow * 0.5)
        xy, z = _project(ctx, quad3, st, v.center)
        if (z <= ctx.camera.near).any():
            return None
        cv.polygon(xy, fill=v.fill_color, fill_alpha=v.fill_opacity * a)
        if v.image:
            try:
                col, alpha = prepare_image(ctx, v)
                if v.flip:
                    col = col[:, ::-1]
                    alpha = None if alpha is None else alpha[:, ::-1]
                cv.warp(col, xy, a * v.image_opacity, v.image_glow, alpha, nearest=bool(v.pixelated))
            except Exception as exc:  # missing file etc.
                ctx.warn(f"{self.name}: {exc}", "image")
        if v.frame_width > 0:
            cv.polygon(xy, stroke=v.frame_color, stroke_alpha=a, width=v.frame_width * ctx.s, glow=v.glow)
        return _bbox(xy)


@register
class Beam(Object3D):
    TYPE, LABEL, ICON = "beam", "Particle beam", "beam"
    TIME_DEPENDENT = True
    DESCRIPTION = "Particles streaking from a source to a target, with optional scattering on the way."
    DEFAULT_ENTER = "none"
    PROPS = [
        Prop("source", "vec3", [-60, 0, 0], group=G_GEO),
        Prop("target", "vec3", [0, 0, 0], group=G_GEO),
        Prop("source_radius", "number", 1.5, min=0, step=0.1, group=G_GEO, help="Beam radius at the source"),
        Prop("target_radius", "number", 4.0, min=0, step=0.1, group=G_GEO, help="Beam radius at the target (cone)"),
        Prop("rate", "number", 220.0, min=0, max=5000, step=10, group=G_MOTION, animatable=False,
             help="Particles per second"),
        Prop("speed", "number", 30.0, min=0.01, step=1, group=G_MOTION, animatable=False,
             help="Scene units per second"),
        Prop("streak", "number", 4.0, min=0, step=0.1, group=G_MOTION, help="Streak length in scene units"),
        Prop("color", "color", "gold", group=G_LOOK),
        Prop("brightness", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("size", "number", 1.1, min=0.3, max=8, step=0.1, group=G_LOOK, help="Streak softness in pixels"),
        Prop("glow", "number", 1.2, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("scatter_fraction", "number", 0.0, min=0, max=1, step=0.01, group="Scattering",
             help="Share of particles that scatter"),
        Prop("scatter_at", "number", 0.5, min=0, max=1, step=0.01, group="Scattering",
             help="Where along the path they scatter (0 = source, 1 = target)"),
        Prop("scatter_range", "number", 25.0, min=0, step=1, group="Scattering",
             help="How far scattered particles travel"),
        Prop("scatter_color", "color", "amber", group="Scattering"),
        Prop("seed", "int", 1, min=0, max=100000, group=G_MOTION, animatable=False),
    ]

    def center_of(self, v):
        return (np.asarray(v.source) + np.asarray(v.target)) / 2

    def label_anchor(self, ctx, v):
        return np.array([v.source, v.target])

    def _table(self, ctx, v, n: int):
        key = ("beam", int(v.seed), n)

        def make():
            rng = np.random.default_rng(int(v.seed) * 7919 + 17)
            def disk(m):
                r = np.sqrt(rng.random(m))
                a = rng.random(m) * 2 * np.pi
                return np.stack([r * np.cos(a), r * np.sin(a)], 1)
            sd = rng.normal(size=(n, 3))
            sd /= np.linalg.norm(sd, axis=1, keepdims=True)
            return dict(jit=rng.random(n), d0=disk(n), d1=disk(n), u=rng.random(n), sdir=sd,
                        b=0.6 + 0.4 * rng.random(n))
        return ctx.assets.memo(key, make)

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        rate, speed = max(float(v.rate), 0.0), max(float(v.speed), 1e-6)
        if rate <= 0:
            return None
        S, T = np.asarray(v.source, np.float64), np.asarray(v.target, np.float64)
        axis = T - S
        L0 = float(np.linalg.norm(axis))
        if L0 < 1e-9:
            return None
        ah = axis / L0
        tmp = np.array([0, 0, 1.0]) if abs(ah[2]) < 0.9 else np.array([1.0, 0, 0])
        e1 = np.cross(ah, tmp)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(ah, e1)
        frac, sat = float(v.scatter_fraction), float(np.clip(v.scatter_at, 0, 1))
        travel_max = L0 * 1.3 + (float(v.scatter_range) if frac > 0 else 0) + float(v.streak)
        tl = st.local_t
        lo = max(0, int(math.floor((tl - travel_max / speed) * rate)) - 1)
        hi = int(math.floor(tl * rate)) + 1
        if hi <= lo:
            return None
        cap = int((ctx.duration + travel_max / speed + 2) * rate) + 64
        tab = self._table(ctx, v, max(cap, hi + 1))
        idx = np.arange(lo, min(hi, len(tab["jit"])))
        ti = (idx + tab["jit"][idx]) / rate
        d = (tl - ti) * speed
        S_i = S + (tab["d0"][idx, :1] * e1 + tab["d0"][idx, 1:] * e2) * float(v.source_radius)
        T_i = T + (tab["d1"][idx, :1] * e1 + tab["d1"][idx, 1:] * e2) * float(v.target_radius)
        dirv = T_i - S_i
        L = np.linalg.norm(dirv, axis=1)
        dirv = dirv / np.maximum(L, 1e-9)[:, None]
        scat = tab["u"][idx] < frac
        Ls = L * sat
        reach = np.where(scat, Ls + float(v.scatter_range), L)
        alive = (d >= 0) & (d - float(v.streak) <= reach)
        if not alive.any():
            return None
        d, S_i, dirv, L, Ls, scat = d[alive], S_i[alive], dirv[alive], L[alive], Ls[alive], scat[alive]
        sdir, bright = tab["sdir"][idx][alive], tab["b"][idx][alive]
        sigma = max(0.45, float(v.size) * ctx.s)
        streak_px = ctx.camera.pixel_size(self.center_of(v), max(float(v.streak), 1e-6))
        K = int(np.clip(streak_px / (sigma * 0.9), 4, 40))
        ks = np.linspace(0, 1, K)
        dk = d[:, None] - ks[None, :] * float(v.streak)                     # (N,K) distance travelled
        w = (1 - ks[None, :]) ** 1.4 * bright[:, None] * float(v.brightness) * (7.0 / K) ** 0.5
        w = np.where(dk >= 0, w, 0.0)
        limit = np.where(scat, Ls + float(v.scatter_range), L)[:, None]
        w = np.where(dk <= limit, w, 0.0)
        before = (~scat[:, None]) | (dk <= Ls[:, None])
        dk_in = np.where(before, np.minimum(dk, L[:, None]), Ls[:, None])
        pos = S_i[:, None, :] + dirv[:, None, :] * dk_in[..., None]
        after = ~before
        pos = np.where(after[..., None], pos + sdir[:, None, :] * (dk - Ls[:, None])[..., None], pos)
        # scattered particles fade out over their range
        fade = np.where(after, np.clip(1 - (dk - Ls[:, None]) / max(float(v.scatter_range), 1e-6), 0, 1), 1.0)
        w = w * fade
        pts = pos.reshape(-1, 3)
        wf = w.reshape(-1)
        xy, z = _project(ctx, pts, st)
        wf = np.where(z > ctx.camera.near, wf, 0.0)
        col = np.where(after.reshape(-1, 1), v.scatter_color[None, :], v.color[None, :]).astype(np.float32)
        if frac > 0:
            cv.splat(xy, wf, v.color, a, sigma, gain=1.4, glow=v.glow, colors=col)
        else:
            cv.splat(xy, wf, v.color, a, sigma, gain=1.4, glow=v.glow)
        ends, _ = _project(ctx, np.array([S, T]), st)
        return _bbox(ends)


@register
class Arrow3D(Object3D):
    TYPE, LABEL, ICON = "arrow3d", "3D arrow / line", "arrow3d"
    DESCRIPTION = "A straight line or arrow between two points in the scene: axes, vectors, rays."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        Prop("tail", "vec3", [0, 0, 0], group=G_GEO),
        Prop("tip", "vec3", [20, 0, 0], group=G_GEO),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("width", "number", 2.0, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("head_size", "number", 14.0, min=0, max=80, step=1, group=G_LOOK, help="Pixels; 0 for a plain line"),
        Prop("dashed", "bool", False, group=G_LOOK),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def center_of(self, v):
        return (np.asarray(v.tail) + np.asarray(v.tip)) / 2

    def label_anchor(self, ctx, v):
        return np.array([v.tip])

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        n = 24
        pts = np.asarray(v.tail) + (np.asarray(v.tip) - np.asarray(v.tail)) * np.linspace(0, 1, n)[:, None]
        xy, z = _project(ctx, pts, st)
        if (z <= ctx.camera.near).any():
            return None
        xy = truncate_path(xy, st.progress)
        cv.polyline(xy, v.color, a, v.width * ctx.s, v.glow, dash=12 * ctx.s if v.dashed else 0)
        if v.head_size > 0 and len(xy) >= 2:
            tip = xy[-1]
            head = arrow_head(tip, tip - xy[-2], v.head_size * ctx.s)
            if len(head):
                cv.polygon(head, fill=v.color, fill_alpha=a, fill_glow=v.glow)
        return _bbox(xy)


@register
class Grid3D(Object3D):
    TYPE, LABEL, ICON = "grid3d", "Floor grid", "grid"
    DESCRIPTION = "A grid in a horizontal plane that gives the scene a floor."
    PROPS = [
        Prop("center", "vec3", [0, 0, -15], group=G_GEO),
        Prop("size", "vec2", [160, 100], group=G_GEO),
        Prop("divisions", "int", 16, min=1, max=200, group=G_GEO),
        Prop("color", "color", "blue", group=G_LOOK),
        Prop("line_opacity", "number", 0.18, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("width", "number", 1.0, min=0, max=10, step=0.1, group=G_LOOK),
        Prop("fade_edges", "bool", True, group=G_LOOK),
    ]

    def depth(self, ctx, v):
        return 1e9  # always behind everything else

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity * v.line_opacity
        c = np.asarray(v.center)
        sx, sy = float(v.size[0]) / 2, float(v.size[1]) / 2
        n = int(v.divisions)
        m = 16
        levels: dict[int, list] = {}
        allxy = []
        for k in range(n + 1):
            f = k / n
            fade = 1 - abs(2 * f - 1) ** 2 if v.fade_edges else 1.0
            for p0, p1 in (((-sx + 2 * sx * f, -sy), (-sx + 2 * sx * f, sy)), ((-sx, -sy + 2 * sy * f), (sx, -sy + 2 * sy * f))):
                pts = c + np.stack([np.linspace(p0[0], p1[0], m), np.linspace(p0[1], p1[1], m), np.zeros(m)], 1)
                xy, z = _project(ctx, pts, st)
                if (z <= ctx.camera.near).any():
                    continue
                allxy.append(xy)
                if v.fade_edges:
                    along = np.abs(np.linspace(-1, 1, m))
                    for j in range(m - 1):
                        lvl = int(round(8 * fade * (1 - along[j] ** 2)))
                        if lvl > 0:
                            levels.setdefault(lvl, []).append(xy[j:j + 2])
                else:
                    levels.setdefault(8, []).append(xy)
        cv.lines_levels(levels, v.color, a, v.width * ctx.s)
        return _bbox(np.vstack(allxy)) if allxy else None


@register
class PointCloud(Object3D):
    TYPE, LABEL, ICON = "pointcloud", "Point cloud", "points"
    DESCRIPTION = "3D points from a table (x, y, z columns): atoms, simulation particles, scans."
    HAS_PROGRESS = True
    PROPS = [
        Prop("data", "asset", "", accept="table", group=G_DATA, help="CSV/TSV/NPY/NPZ with x, y, z columns"),
        Prop("x_column", "text", "x", group=G_DATA),
        Prop("y_column", "text", "y", group=G_DATA),
        Prop("z_column", "text", "z", group=G_DATA),
        Prop("x_values", "array", "", group=G_DATA, help="Or type numbers: 1, 2, 3"),
        Prop("y_values", "array", "", group=G_DATA),
        Prop("z_values", "array", "", group=G_DATA),
        *seqdata.seq_props(G_DATA),
        Prop("center", "vec3", [0, 0, 0], group=G_GEO, help="Where the data origin goes"),
        Prop("scale", "number", 1.0, min=0, step=0.1, group=G_GEO),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO),
        Prop("color", "color", "ice", group=G_LOOK),
        Prop("color_by", "text", "", group=G_LOOK, help="Column used for colour (with a colormap)"),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_LOOK),
        Prop("size", "number", 3.0, min=0.3, max=40, step=0.1, group=G_LOOK, help="Point radius in pixels"),
        Prop("style", "enum", "glow", options=("glow", "solid"), group=G_LOOK),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def depends_on_time(self) -> bool:
        return super().depends_on_time() or seqdata.plays_by_itself(self, "data")

    def _data(self, ctx, v):
        if v.data:
            xs = seqdata.column(ctx, v, v.x_column)
            ys = seqdata.column(ctx, v, v.y_column)
            zs = seqdata.column(ctx, v, v.z_column)
            cvals = seqdata.column(ctx, v, v.color_by) if v.color_by else None
        else:
            xs, ys, zs = parse_array(v.x_values), parse_array(v.y_values), parse_array(v.z_values)
            cvals = None
        n = min(len(xs), len(ys), len(zs))
        p = np.stack([xs[:n], ys[:n], zs[:n]], 1)
        R = rotation_matrix(*v.rotation)
        return (p * float(v.scale)) @ R.T + np.asarray(v.center), (None if cvals is None else cvals[:n])

    def label_anchor(self, ctx, v):
        try:
            p, _ = self._data(ctx, v)
            return np.array([p.min(0), p.max(0)]) if len(p) else None
        except Exception:
            return None

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        p, cvals = self._data(ctx, v)
        if len(p) == 0:
            return None
        if st.progress < 1:
            order = np.random.default_rng(3).permutation(len(p))
            keep = order[: int(round(len(p) * st.progress))]
            p = p[keep]
            cvals = None if cvals is None else cvals[keep]
        xy, z = _project(ctx, p, st, np.asarray(v.center))
        ok = z > ctx.camera.near
        xy = xy[ok]
        colors = None
        if cvals is not None:
            colors = apply_colormap(cvals[ok], v.colormap)
        if v.style == "solid":
            order = np.argsort(-z[ok])
            cv.dots(xy[order], v.size * ctx.s, v.color, a, v.glow, None if colors is None else colors[order])
        else:
            cv.splat(xy, 1.0, v.color, a, max(0.5, v.size * ctx.s * 0.6), gain=1.6, glow=v.glow, colors=colors)
        return _bbox(xy)


@register
class Mesh(Object3D):
    TYPE, LABEL, ICON = "mesh", "3D model (STL/OBJ)", "mesh"
    DESCRIPTION = "Import an STL or OBJ model of an instrument or sample, drawn as wireframe or solid."
    PROPS = [
        Prop("model", "asset", "", accept="mesh", group=G_GEO, help="STL or OBJ file"),
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("scale", "number", 1.0, min=0, step=0.01, group=G_GEO),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO),
        Prop("style", "enum", "solid+edges", options=("wire", "solid", "solid+edges", "edges"), group=G_LOOK,
             help="'edges' shows only sharp creases, which reads well for CAD parts"),
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("fill_opacity", "number", 0.35, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("edge_color", "color", "teal", group=G_LOOK),
        Prop("edge_width", "number", 1.2, min=0, max=10, step=0.1, group=G_LOOK),
        Prop("feature_angle", "number", 30.0, min=0, max=180, step=1, group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def _geometry(self, ctx, v):
        verts, faces = ctx.assets.mesh(v.model)
        R = rotation_matrix(*v.rotation)
        return (verts * float(v.scale)) @ R.T + np.asarray(v.center), faces

    def _edges(self, ctx, v, verts, faces):
        key = ("mesh_edges", v.model, ctx.assets.stamp(v.model), float(v.feature_angle), faces.shape)

        def make():
            e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
            fid = np.tile(np.arange(len(faces)), 3)
            n = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            order = np.lexsort((e[:, 1], e[:, 0]))
            e, fid = e[order], fid[order]
            uniq, start, counts = np.unique(e, axis=0, return_index=True, return_counts=True)
            sharp = []
            cosmax = math.cos(math.radians(float(v.feature_angle)))
            for (i, j), s0, c in zip(uniq, start, counts):
                if c == 1:
                    sharp.append((i, j))
                elif c >= 2 and float(n[fid[s0]] @ n[fid[s0 + 1]]) < cosmax:
                    sharp.append((i, j))
            return uniq, np.array(sharp, np.int64).reshape(-1, 2)
        return ctx.assets.memo(key, make)

    def label_anchor(self, ctx, v):
        try:
            verts, _ = self._geometry(ctx, v)
            return np.array([verts.min(0), verts.max(0)])
        except Exception:
            return None

    def draw(self, cv, ctx, v, st):
        if not v.model:
            return None
        a = v.opacity * st.opacity
        verts, faces = self._geometry(ctx, v)
        if len(faces) == 0:
            return None
        xy, z = _project(ctx, verts, st, np.asarray(v.center))
        if (z <= ctx.camera.near).any():
            return None
        style = v.style
        if style in ("solid", "solid+edges") and v.fill_opacity > 0:
            fz = z[faces].mean(1)
            n = np.cross(verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]])
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
            light = np.array([0.4, -0.5, 0.75])
            light /= np.linalg.norm(light)
            shade = 0.35 + 0.65 * np.abs(n @ light)
            order = np.argsort(-fz)
            if len(order) > 20000:
                order = order[:: int(math.ceil(len(order) / 20000))]
            for fi in order:
                cv.polygon(xy[faces[fi]], fill=v.color * shade[fi], fill_alpha=v.fill_opacity * a)
        if style in ("wire", "solid+edges", "edges"):
            allE, sharp = self._edges(ctx, v, verts, faces)
            E = allE if style == "wire" else sharp
            if len(E):
                cv.lines([xy[e] for e in E], v.edge_color, a, v.edge_width * ctx.s, v.glow)
        return _bbox(xy)


@register
class Label3D(Object3D):
    TYPE, LABEL, ICON = "label3d", "3D label", "pin"
    DESCRIPTION = "Text pinned to a point in the scene, with an optional leader line."
    HAS_LABEL = False
    TEXTUAL = True
    PROPS = [
        Prop("point", "vec3", [0, 0, 0], group=G_GEO),
        Prop("text", "text", "Label", group="Text"),
        Prop("size", "number", 20, min=6, max=160, step=1, group="Text"),
        Prop("color", "color", "cream", group="Text"),
        Prop("weight", "enum", "regular", options=("light", "regular", "medium", "bold"), group="Text"),
        Prop("offset", "vec2", [30, -40], group=G_GEO, help="Text position relative to the point, in pixels"),
        Prop("leader", "bool", True, group=G_LOOK, help="Line from the point to the text"),
        Prop("dot", "bool", True, group=G_LOOK),
        Prop("line_color", "color", "gray", group=G_LOOK),
        Prop("glow", "number", 0.3, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def center_of(self, v):
        return np.asarray(v.point)

    def depth(self, ctx, v):
        return -1e9  # labels on top of the 3D scene

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        (p,), z = _project(ctx, np.asarray(v.point)[None], st)
        if z[0] <= ctx.camera.near:
            return None
        off = np.asarray(v.offset) * ctx.s
        tx, ty = p + off
        if v.leader and (abs(off[0]) + abs(off[1])) > 1:
            cv.polyline(np.array([p, p + off * 0.92]), v.line_color, a * 0.8, 1.2 * ctx.s)
        if v.dot:
            cv.circle(p[0], p[1], 3.2 * ctx.s, fill=v.color, fill_alpha=a, fill_glow=v.glow)
        align = "left" if off[0] >= 0 else "right"
        valign = "bottom" if off[1] < 0 else "top"
        b = ctx.draw_text(cv, v.text, tx / ctx.s, ty / ctx.s, v.size, v.color, align=align, valign=valign,
                          opacity=a, glow=v.glow, weight=v.weight, progress=st.progress)
        if b is None:
            return (p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4)
        return (min(b[0], p[0]), min(b[1], p[1]), max(b[2], p[0]), max(b[3], p[1]))
