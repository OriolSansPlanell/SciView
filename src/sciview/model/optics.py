"""2D optics: lenses, mirrors, ray bundles traced through them, and wavefronts."""
from __future__ import annotations

import math

import numpy as np

from ..engine.surface import truncate_path
from .base import Prop, SceneObject, register

OPTICS, G_GEO, G_LOOK, G_RAYS, G_WAVE = "Optics", "Geometry", "Appearance", "Rays", "Waves"
EPS = 1e-6


def _dir(deg: float) -> np.ndarray:
    """Unit vector at ``deg`` degrees anticlockwise from +x, in screen coordinates (y down)."""
    a = math.radians(deg)
    return np.array([math.cos(a), -math.sin(a)])


def _box(pts: np.ndarray, s: float):
    pts = np.asarray(pts).reshape(-1, 2)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) == 0:
        return None
    return (pts[:, 0].min() * s, pts[:, 1].min() * s, pts[:, 0].max() * s, pts[:, 1].max() * s)


class _Element(SceneObject):
    CATEGORY = OPTICS

    def frame(self, v):
        """Centre, axis normal n (the way light travels through / the side it faces) and tangent t."""
        c = np.asarray(v.position, np.float64)
        n = _dir(float(v.angle))
        t = np.array([-n[1], n[0]])
        return c, n, t


@register
class Lens(_Element):
    TYPE, LABEL, ICON = "lens", "Lens", "lens"
    DESCRIPTION = "A thin lens. Rays objects bend through it: positive focal length converges, negative diverges."
    PROPS = [
        Prop("position", "vec2", [960, 540], group=G_GEO, help="Centre of the lens"),
        Prop("height", "number", 300, min=10, step=5, group=G_GEO, help="Aperture in pixels"),
        Prop("angle", "number", 0.0, step=1, group=G_GEO, help="Direction of the optical axis (0 = left to right)"),
        Prop("focal", "number", 250, step=5, group=G_GEO, help="Focal length in pixels; negative for a diverging lens"),
        Prop("color", "color", "ice", group=G_LOOK),
        Prop("fill_opacity", "number", 0.18, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("width", "number", 2.0, min=0, max=10, step=0.5, group=G_LOOK),
        Prop("show_focus", "bool", True, group=G_LOOK, help="Mark both focal points on the axis"),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def outline(self, v, k: float = 1.0) -> np.ndarray:
        c, n, t = self.frame(v)
        h = float(v.height) * k
        w = np.linspace(-h / 2, h / 2, 41)
        u = (w / (h / 2)) ** 2
        if float(v.focal) >= 0:
            th = min(0.18 * h, 0.06 * h + 0.25 * h * h / max(abs(float(v.focal)), 1.0) / 4)
            right = th / 2 * (1 - u)
            left = -right
        else:
            th = 0.12 * h
            right = 0.03 * h + th / 2 * u
            left = -right
        pts_r = c + np.outer(right, n) + np.outer(w, t)
        pts_l = c + np.outer(left, n) + np.outer(w, t)
        return np.vstack([pts_r, pts_l[::-1]])

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        poly = self.outline(v, st.scale) + (st.dx, st.dy)
        cv.polygon(poly * s, fill=v.color, fill_alpha=v.fill_opacity * a, stroke=v.color, stroke_alpha=a,
                   width=v.width * s, glow=v.glow)
        if v.show_focus and float(v.focal) != 0:
            c, n, _ = self.frame(v)
            f = abs(float(v.focal))
            for sgn in (-1, 1):
                p = (c + n * f * sgn + (st.dx, st.dy)) * s
                cv.circle(p[0], p[1], 4 * s, fill=v.color, fill_alpha=a * 0.9, fill_glow=0.5)
                ctx.draw_text(cv, "F", p[0] / s, p[1] / s + 8, 16, v.color, align="center", opacity=a * 0.8)
        return _box(poly, s)


@register
class Mirror(_Element):
    TYPE, LABEL, ICON = "mirror", "Mirror", "mirror"
    DESCRIPTION = ("A flat or curved mirror (or a beam splitter, or an absorbing screen) that Rays objects "
                   "reflect from or stop at.")
    PROPS = [
        Prop("position", "vec2", [1300, 540], group=G_GEO, help="Centre of the mirror surface"),
        Prop("height", "number", 300, min=10, step=5, group=G_GEO),
        Prop("angle", "number", 180.0, step=1, group=G_GEO,
             help="The way the mirror faces (180 = facing left, towards light coming from the left)"),
        Prop("radius", "number", 0.0, step=10, group=G_GEO,
             help="Radius of curvature in pixels: 0 = flat, positive = concave (focuses), negative = convex"),
        Prop("kind", "enum", "mirror", options=("mirror", "splitter", "absorber"), group=G_GEO,
             help="splitter: half reflected, half passes; absorber: rays stop here (a detector or screen)"),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("width", "number", 4.0, min=0.5, max=20, step=0.5, group=G_LOOK),
        Prop("hatch", "bool", True, group=G_LOOK, help="Short lines on the back of a mirror"),
        Prop("glow", "number", 0.4, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def surface(self, v, k: float = 1.0) -> np.ndarray:
        c, n, t = self.frame(v)
        h = float(v.height) * k
        R = float(v.radius)
        w = np.linspace(-h / 2, h / 2, 41)
        if abs(R) < h / 2 + EPS:
            return c + np.outer(w, t)
        # vertex at c; centre of curvature at c + n*R (in front for concave)
        sag = R - np.sign(R) * np.sqrt(np.maximum(R * R - w * w, 0))
        return c + np.outer(sag, n) + np.outer(w, t)

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        pts = self.surface(v, st.scale) + (st.dx, st.dy)
        c, n, t = self.frame(v)
        if v.kind == "splitter":
            cv.polyline(pts * s, v.color, a * 0.85, v.width * 0.6 * s, v.glow, dash=8 * s)
        else:
            cv.polyline(pts * s, v.color, a, v.width * s, v.glow)
        if v.hatch and v.kind == "mirror":
            segs = [np.array([p, p - n * 10 - t * 7]) * s for p in pts[::4]]
            cv.lines(segs, v.color, a * 0.5, 1.2 * s)
        return _box(np.vstack([pts, pts - n * 12]), s)

    # ------------------------------------------------------------------ geometry for tracing
    def hit(self, v, o: np.ndarray, d: np.ndarray):
        """Nearest intersection (distance, point, normal) of a ray with this element, or None."""
        c, n, t = self.frame(v)
        h = float(v.height)
        R = float(v.radius)
        if abs(R) < h / 2 + EPS:
            return _hit_segment(c, t, h, o, d, n)
        C = c + n * R
        oc = o - C
        b = float(oc @ d)
        disc = b * b - (float(oc @ oc) - R * R)
        if disc < 0:
            return None
        best = None
        for tt in (-b - math.sqrt(disc), -b + math.sqrt(disc)):
            if tt <= EPS:
                continue
            p = o + d * tt
            if abs(float((p - c) @ t)) <= h / 2 and float((p - C) @ n) * math.copysign(1, R) < 0:
                best = tt
                break
        if best is None:
            return None
        p = o + d * best
        normal = (p - C) / abs(R)
        return best, p, normal


def _hit_segment(c, t, h, o, d, n):
    """Ray o + s·d against the segment c ± t·h/2; returns (s, point, normal)."""
    M = np.array([[d[0], -t[0]], [d[1], -t[1]]])
    det = np.linalg.det(M)
    if abs(det) < 1e-12:
        return None
    sol = np.linalg.solve(M, c - o)
    s_, w = float(sol[0]), float(sol[1])
    if s_ <= EPS or abs(w) > h / 2:
        return None
    return s_, o + d * s_, n


def _lens_hit(lens: Lens, v, o, d):
    c, n, t = lens.frame(v)
    return _hit_segment(c, t, float(v.height), o, d, n)


@register
class Rays(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "rays", "Light rays", "rays", OPTICS
    DESCRIPTION = ("A bundle of rays from a point or a parallel beam, traced through every lens and mirror in the "
                   "film. The draw effect (or Travel) sends the light on its way.")
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        Prop("source", "vec2", [300, 540], group=G_RAYS, help="Where the light starts"),
        Prop("angle", "number", 0.0, step=1, group=G_RAYS, help="Direction of travel (0 = to the right)"),
        Prop("kind", "enum", "parallel", options=("parallel", "point"), group=G_RAYS,
             help="parallel: a beam of width Spread; point: a cone of Spread degrees"),
        Prop("spread", "number", 200, min=0, step=5, group=G_RAYS, help="Beam width in pixels, or cone angle in degrees"),
        Prop("count", "int", 7, min=1, max=200, group=G_RAYS),
        Prop("length", "number", 2400, min=10, step=50, group=G_RAYS, help="Longest path of a ray, in pixels"),
        Prop("bounces", "int", 8, min=0, max=50, group=G_RAYS, help="Most reflections and refractions per ray"),
        Prop("travel", "number", 1.0, min=0, max=1, step=0.01, group=G_RAYS,
             help="How far the light has got along its path. Animate it from 0 to 1"),
        Prop("color", "color", "gold", group=G_LOOK),
        Prop("width", "number", 2.0, min=0.3, max=12, step=0.1, group=G_LOOK),
        Prop("glow", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def starts(self, v) -> list[tuple[np.ndarray, np.ndarray]]:
        o = np.asarray(v.source, np.float64)
        d = _dir(float(v.angle))
        n = max(1, int(v.count))
        perp = np.array([-d[1], d[0]])
        if v.kind == "point":
            half = float(v.spread) / 2
            angs = [float(v.angle)] if n == 1 else list(np.linspace(float(v.angle) - half, float(v.angle) + half, n))
            return [(o.copy(), _dir(a)) for a in angs]
        offs = [0.0] if n == 1 else list(np.linspace(-float(v.spread) / 2, float(v.spread) / 2, n))
        return [(o + perp * k, d.copy()) for k in offs]

    def trace(self, ctx, v) -> list[tuple[np.ndarray, float]]:
        """Paths (polyline, intensity) of all rays, splitting at beam splitters."""
        elements = []
        for obj in ctx.project.objects:
            if obj.TYPE in ("lens", "mirror") and obj.state(ctx.t, ctx.duration) is not None:
                elements.append((obj, obj.resolve(ctx.t, ctx)))
        W, H = ctx.project.size
        margin = 400.0
        stack = [(o, d, [o], 1.0, int(v.bounces), float(v.length)) for o, d in self.starts(v)]
        out = []
        while stack:
            o, d, path, inten, left, budget = stack.pop()
            if len(out) > 2000:
                break
            nearest = None
            for obj, ov in elements:
                h = _lens_hit(obj, ov, o, d) if obj.TYPE == "lens" else obj.hit(ov, o, d)
                if h is not None and h[0] <= budget and (nearest is None or h[0] < nearest[0][0]):
                    nearest = (h, obj, ov)
            if nearest is None or left < 0:
                # run out to the edge of the frame (with a margin) or the length budget
                tt = budget
                for k in range(2):
                    if abs(d[k]) > 1e-9:
                        lo, hi = -margin, (W if k == 0 else H) + margin
                        lim = ((hi - o[k]) if d[k] > 0 else (lo - o[k])) / d[k]
                        tt = min(tt, max(lim, 0.0))
                out.append((np.array(path + [o + d * tt]), inten))
                continue
            (dist, p, normal), obj, ov = nearest
            path = path + [p]
            budget -= dist
            if obj.TYPE == "lens":
                c, n_l, t_l = obj.frame(ov)
                if float(d @ n_l) < 0:
                    n_l = -n_l
                f = float(ov.focal)
                hgt = float((p - c) @ t_l)
                m = float(d @ t_l) / max(float(d @ n_l), 1e-9)
                m2 = m - (hgt / f if f != 0 else 0.0)
                nd = n_l + m2 * t_l
                stack.append((p + nd / np.linalg.norm(nd) * 1e-3, nd / np.linalg.norm(nd), path, inten, left - 1, budget))
            elif ov.kind == "absorber":
                out.append((np.array(path), inten))
            else:
                r = d - 2 * float(d @ normal) * normal
                if ov.kind == "splitter":
                    stack.append((p + d * 1e-3, d, list(path), inten * 0.5, left - 1, budget))
                    stack.append((p + r * 1e-3, r, list(path), inten * 0.5, left - 1, budget))
                else:
                    stack.append((p + r * 1e-3, r, path, inten, left - 1, budget))
        return out

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        paths = self.trace(ctx, v)
        frac = st.progress * float(np.clip(v.travel, 0, 1))
        if frac <= 0 or not paths:
            return None
        # every ray travels at the same speed: cut all paths at the same distance
        lengths = [float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) for p, _ in paths]
        reach = max(lengths) * frac
        allpts = []
        by_intensity: dict[float, list] = {}
        for (p, inten), L in zip(paths, lengths):
            q = p if reach >= L else truncate_path(p, reach / max(L, 1e-9))
            if len(q) < 2:
                continue
            q = (q + (st.dx, st.dy)) * s
            by_intensity.setdefault(round(inten, 3), []).append(q)
            allpts.append(q)
        for inten, qs in by_intensity.items():
            cv.lines(qs, v.color, a * inten, v.width * s, v.glow, additive=True)
        return _box(np.vstack(allpts), 1.0) if allpts else None


@register
class Wavefront(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "wavefront", "Wavefronts", "wavefront", OPTICS
    DESCRIPTION = "Circular or plane wave crests moving out from a source at a set wavelength and speed."
    TIME_DEPENDENT = True
    PROPS = [
        Prop("source", "vec2", [500, 540], group=G_WAVE, help="Point source, or a point on the first plane crest"),
        Prop("kind", "enum", "circular", options=("circular", "plane"), group=G_WAVE),
        Prop("angle", "number", 0.0, step=1, group=G_WAVE, help="Direction of travel (plane), or the centre of the arc"),
        Prop("arc", "number", 360, min=1, max=360, step=1, group=G_WAVE, help="Circular waves: the opening angle"),
        Prop("wavelength", "number", 60, min=2, step=1, group=G_WAVE, help="Crest spacing in pixels"),
        Prop("speed", "number", 120, step=5, group=G_WAVE, help="Pixels per second (0 = frozen)"),
        Prop("extent", "number", 700, min=10, step=10, group=G_WAVE,
             help="Farthest crest from the source (circular) or crest length (plane)"),
        Prop("range", "number", 900, min=10, step=10, group=G_WAVE, help="Plane waves: how far they travel"),
        Prop("color", "color", "blue", group=G_LOOK),
        Prop("width", "number", 2.0, min=0.3, max=12, step=0.1, group=G_LOOK),
        Prop("fade", "bool", True, group=G_LOOK, help="Crests fade with distance"),
        Prop("glow", "number", 0.7, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        lam = max(float(v.wavelength), 1e-3)
        phase = (float(v.speed) * st.local_t) % lam
        o = np.asarray(v.source, np.float64) + (st.dx, st.dy)
        boxes = []
        if v.kind == "circular":
            R = float(v.extent)
            half = float(v.arc) / 2
            th = np.radians(np.linspace(float(v.angle) - half, float(v.angle) + half, max(16, int(v.arc) // 2)))
            r = phase if phase > 1e-6 else lam
            while r <= R:
                pts = o + r * np.stack([np.cos(th), -np.sin(th)], 1)
                k = (1 - r / R) if v.fade else 1.0
                cv.polyline(pts * s, v.color, a * max(k, 0) ** 0.7, v.width * s, v.glow)
                boxes.append(pts)
                r += lam
        else:
            d = _dir(float(v.angle))
            t = np.array([-d[1], d[0]])
            L = float(v.extent)
            D = float(v.range)
            x = phase
            while x <= D:
                c = o + d * x
                pts = np.array([c - t * L / 2, c + t * L / 2])
                k = (1 - x / D) if v.fade else 1.0
                cv.polyline(pts * s, v.color, a * max(k, 0) ** 0.7, v.width * s, v.glow)
                boxes.append(pts)
                x += lam
        return _box(np.vstack(boxes), s) if boxes else None
