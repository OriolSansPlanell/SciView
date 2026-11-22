"""Imaging objects: volumes (slices, projections, isosurfaces), tomography and scale bars."""
from __future__ import annotations

import math

import cv2
import numpy as np

from ..engine.camera import rotation_matrix
from ..engine.color import COLORMAPS, apply_colormap
from ..engine.units import nice_length, parse_si, si
from ..science import tomo
from . import data as seqdata
from .base import Prop, SceneObject, register
from .objects3d import BOX_EDGES, Object3D, _bbox, _project, box_corners

G_VOL, G_GEO, G_SLICE, G_COL, G_ISO, G_LOOK = "Volume", "Geometry", "Slices", "Colour", "Isosurface", "Appearance"
G_TOMO, G_POS, G_BAR = "Tomography", "Position", "Scale bar"
IMAGING = "Imaging"


def _percentile_range(arr: np.ndarray, lo: float = 1.0, hi: float = 99.5) -> tuple[float, float]:
    a = np.asarray(arr, np.float32)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return 0.0, 1.0
    if a.size > 2_000_000:
        a = a[:: int(math.ceil(a.size / 2_000_000))]
    p0, p1 = (float(x) for x in np.percentile(a, [lo, hi]))
    if p1 <= p0:
        p0, p1 = float(a.min()), float(a.max())
    return p0, (p1 if p1 > p0 else p0 + 1e-6)


# --------------------------------------------------------------------------- volume
@register
class Volume(Object3D):
    TYPE, LABEL, ICON = "volume", "Volume (3D image)", "volume"
    DESCRIPTION = ("A 3D image from tomography, MRI or a simulation, shown as sweeping slice planes, a "
                   "maximum-intensity projection, a radiograph-like projection or an isosurface.")
    HAS_PROGRESS = True
    PROPS = [
        Prop("data", "asset", "", accept="volume", group=G_VOL,
             help=".npy array (z, y, x), multi-page TIFF, HDF5 (.h5), or a pattern of slices such as slices/*.png"),
        Prop("dataset", "text", "", group=G_VOL, help="HDF5 only: the dataset inside the file (empty = the first 3D one)"),
        Prop("mode", "enum", "slices", options=("slices", "mip", "projection", "isosurface"), group=G_VOL,
             help="slices: up to three planes; mip: brightest value along each line of sight; "
                  "projection: the average, like a radiograph; isosurface: the surface at Threshold"),
        Prop("max_size", "int", 192, min=16, max=1024, group=G_VOL,
             help="Voxels along the longest side used for drawing: larger is sharper and slower"),
        Prop("samples", "int", 128, min=8, max=512, group=G_VOL, help="Planes sampled for mip and projection"),
        Prop("center", "vec3", [0, 0, 0], group=G_GEO),
        Prop("size", "number", 40.0, min=0.01, step=1, group=G_GEO, help="Length of the longest side, in scene units"),
        Prop("spacing", "vec3", [1, 1, 1], group=G_GEO, help="Voxel size along x, y and z, for scans with thicker slices"),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO),
        Prop("slice_x", "number", 0.5, min=0, max=1, step=0.01, group=G_SLICE,
             help="Where the slice across x sits (0 to 1). Animate it to sweep through the sample"),
        Prop("slice_y", "number", 0.5, min=0, max=1, step=0.01, group=G_SLICE),
        Prop("slice_z", "number", 0.5, min=0, max=1, step=0.01, group=G_SLICE),
        Prop("show_x", "bool", True, group=G_SLICE),
        Prop("show_y", "bool", True, group=G_SLICE),
        Prop("show_z", "bool", True, group=G_SLICE),
        Prop("slice_opacity", "number", 1.0, min=0, max=1, step=0.01, group=G_SLICE),
        Prop("colormap", "enum", "gray", options=COLORMAPS, group=G_COL),
        Prop("vmin", "number", 0.0, group=G_COL, help="Value shown darkest; vmin = vmax uses the 1st to 99.5th percentile"),
        Prop("vmax", "number", 0.0, group=G_COL),
        Prop("gamma", "number", 1.0, min=0.1, max=5, step=0.05, group=G_COL),
        Prop("clear_below", "number", 0.0, min=0, max=1, step=0.01, group=G_COL,
             help="Values below this fraction of the range become see-through (air around a sample)"),
        Prop("threshold", "number", 0.5, min=0, max=1, step=0.01, group=G_ISO,
             help="Isosurface level as a fraction of vmin..vmax. Animate it to peel layers away"),
        Prop("iso_color", "color", "teal", group=G_ISO),
        Prop("iso_opacity", "number", 0.95, min=0, max=1, step=0.01, group=G_ISO),
        Prop("smoothness", "int", 1, min=1, max=6, group=G_ISO,
             help="Marching-cubes step: larger gives fewer, smoother triangles"),
        Prop("outline", "bool", True, group=G_LOOK),
        Prop("outline_color", "color", "teal", group=G_LOOK),
        Prop("outline_width", "number", 1.5, min=0, max=10, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.3, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    # ------------------------------------------------------------------ data
    def _volume(self, ctx, v) -> np.ndarray:
        return ctx.assets.volume_reduced(v.data, v.dataset, int(v.max_size))

    def color_range(self, ctx, v) -> tuple[float, float]:
        if float(v.vmin) != float(v.vmax):
            return float(v.vmin), float(v.vmax)
        key = ("vol_range", v.data, v.dataset, ctx.assets.stamp(v.data), int(v.max_size))
        return ctx.assets.memo(key, lambda: _percentile_range(self._volume(ctx, v)))

    def _frame(self, v, shape):
        """Local half-extents (x, y, z) and the local-to-world rotation."""
        nz, ny, nx = shape
        sp = np.abs(np.asarray(v.spacing, np.float64)) + 1e-12
        ext = np.array([nx * sp[0], ny * sp[1], nz * sp[2]])
        ext = ext * (float(v.size) / max(ext.max(), 1e-12))
        return ext, rotation_matrix(*v.rotation)

    def _world(self, v, ext, R, f):
        """Fractional coordinates (..., 3) in 0..1 (x, y, z) to world points."""
        return (np.asarray(f, np.float64) - 0.5) * ext @ R.T + np.asarray(v.center, np.float64)

    def label_anchor(self, ctx, v):
        try:
            ext, R = self._frame(v, self._volume(ctx, v).shape)
        except Exception:
            ext = np.full(3, float(v.size))
        return box_corners(v.center, ext, v.rotation)

    # ------------------------------------------------------------------ drawing
    def draw(self, cv, ctx, v, st):
        if not v.data:
            return None
        a = v.opacity * st.opacity
        try:
            vol = self._volume(ctx, v)
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "data")
            return None
        ext, R = self._frame(v, vol.shape)
        corners = box_corners(v.center, ext * max(st.scale, 1e-3), v.rotation)
        xy, z = _project(ctx, corners, st)
        if (z <= ctx.camera.near).any():
            return None
        lo, hi = self.color_range(ctx, v)
        fade = a * min(1.0, st.progress * 1.5)
        mode = v.mode
        if mode == "slices":
            self._draw_slices(cv, ctx, v, st, vol, ext, R, lo, hi, fade)
        elif mode in ("mip", "projection"):
            self._draw_projection(cv, ctx, v, st, vol, ext, R, lo, hi, fade, xy)
        elif mode == "isosurface":
            self._draw_iso(cv, ctx, v, st, vol, ext, R, lo, hi, fade)
        if v.outline and v.outline_width > 0:
            from ..engine.surface import truncate_path
            segs = [xy[[i, j]] for i, j in BOX_EDGES]
            if st.progress < 1:
                segs = [truncate_path(sg, st.progress) for sg in segs]
            cv.lines(segs, v.outline_color, a * 0.8, v.outline_width * ctx.s, v.glow)
        return _bbox(xy)

    def _colored(self, img, v, lo, hi):
        u = np.clip((np.asarray(img, np.float32) - lo) / ((hi - lo) or 1e-9), 0, 1)
        col = apply_colormap(u, v.colormap, 0.0, 1.0, float(v.gamma))
        cb = float(v.clear_below)
        mask = None
        if cb > 0:
            mask = np.clip((u - cb) / max(0.08 * (1 - cb), 1e-3), 0, 1).astype(np.float32)
        return col, mask

    def _slice(self, vol, axis: int, f: float) -> np.ndarray:
        """Slice through the volume at fractional position f along local axis (0 = x, 1 = y, 2 = z),
        interpolated between the two nearest voxel planes, oriented for the quads below."""
        n = vol.shape[2 - axis]
        pos = min(max(f * n - 0.5, 0.0), n - 1.0)
        i0 = int(math.floor(pos))
        i1 = min(i0 + 1, n - 1)
        w = pos - i0

        def plane(i):
            if axis == 0:
                return vol[::-1, :, i]          # rows z (top = high), cols y
            if axis == 1:
                return vol[::-1, i, :]          # rows z, cols x
            return vol[i, ::-1, :]              # rows y (top = high), cols x
        p = plane(i0)
        return p if w < 1e-6 else p * (1 - w) + plane(i1) * w

    def _draw_slices(self, cv, ctx, v, st, vol, ext, R, lo, hi, a):
        if v.slice_opacity <= 0:
            return
        shape = {0: vol.shape[2], 1: vol.shape[1], 2: vol.shape[0]}           # voxels along x, y, z
        on = {k: bool(v[f"show_{'xyz'[k]}"]) for k in range(3)}
        pos = {k: min(max(float(v[f"slice_{'xyz'[k]}"]), 0.0), 1.0) for k in range(3)}
        # split each plane where the other shown planes cut it, so the pieces sort correctly by depth
        snapped = {k: round(pos[k] * shape[k]) / shape[k] for k in range(3)}
        pieces = []
        for k in range(3):
            if not on[k]:
                continue
            img = self._slice(vol, k, pos[k])
            col, mask = self._colored(img, v, lo, hi)
            u_axis, w_axis = [(1, 2), (0, 2), (0, 1)][k]          # image columns, image rows (flipped)
            us = [0.0] + ([snapped[u_axis]] if on[u_axis] else []) + [1.0]
            ws = [0.0] + ([snapped[w_axis]] if on[w_axis] else []) + [1.0]
            nu, nw = shape[u_axis], shape[w_axis]
            for u0, u1 in zip(us, us[1:]):
                for w0, w1 in zip(ws, ws[1:]):
                    c0, c1 = round(u0 * nu), round(u1 * nu)
                    r0, r1 = round((1 - w1) * nw), round((1 - w0) * nw)
                    if c1 <= c0 or r1 <= r0:
                        continue
                    f = np.zeros((4, 3))
                    f[:, k] = pos[k]
                    f[:, u_axis] = [u0, u1, u1, u0]
                    f[:, w_axis] = [w1, w1, w0, w0]
                    pts = self._world(v, ext * max(st.scale, 1e-3), R, f)
                    depth = float(ctx.camera.to_camera(pts.mean(0, keepdims=True))[0, 2])
                    sub_mask = None if mask is None else mask[r0:r1, c0:c1]
                    pieces.append((depth, pts, col[r0:r1, c0:c1], sub_mask))
        for _, pts, col, mask in sorted(pieces, key=lambda p: -p[0]):
            qxy, qz = _project(ctx, pts, st)
            if (qz <= ctx.camera.near).any():
                continue
            cv.warp(np.ascontiguousarray(col), qxy, a * v.slice_opacity, v.glow * 0.3,
                    None if mask is None else np.ascontiguousarray(mask))

    def _draw_projection(self, cv, ctx, v, st, vol, ext, R, lo, hi, a, box_xy):
        cam = ctx.camera
        center = np.asarray(v.center, np.float64)
        view_local = R.T @ (center - cam.eye)
        k = int(np.argmax(np.abs(view_local) / np.maximum(ext, 1e-9) * ext))   # dominant axis
        n = vol.shape[2 - k]
        S = int(min(max(int(v.samples), 2), n))
        pts_box = cv._t(box_xy)
        roi = cv._roi(pts_box, 2)
        if roi is None:
            return
        x0, y0, x1, y1 = roi
        W, H = x1 - x0, y1 - y0
        acc = np.zeros((H, W), np.float32)
        cnt = np.zeros((H, W), np.float32) if v.mode == "projection" else None
        u_axis, w_axis = [(1, 2), (0, 2), (0, 1)][k]
        sc = ext * max(st.scale, 1e-3)
        for j in range(S):
            f = (j + 0.5) / S
            img = np.clip((self._slice(vol, k, f) - lo) / ((hi - lo) or 1e-9), 0, 1).astype(np.float32)
            q = np.zeros((4, 3))
            q[:, k] = f
            q[:, u_axis] = [0, 1, 1, 0]
            q[:, w_axis] = [1, 1, 0, 0]
            qxy, qz = _project(ctx, self._world(v, sc, R, q), st)
            if (qz <= cam.near).any():
                continue
            h, w = img.shape
            src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
            dst = np.float32(cv._t(qxy) - (x0, y0))
            try:
                M = cv2.getPerspectiveTransform(src, dst)
            except cv2.error:
                continue
            warped = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            if cnt is None:
                np.maximum(acc, warped, out=acc)
            else:
                acc += warped
                cnt += cv2.warpPerspective(np.ones_like(img), M, (W, H), flags=cv2.INTER_LINEAR,
                                           borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        if cnt is not None:
            acc = acc / np.maximum(cnt, 1e-3)
            hi2 = float(np.percentile(acc[cnt > 0.5], 99.5)) if (cnt > 0.5).any() else 1.0
            acc = np.clip(acc / max(hi2, 1e-6), 0, 1)
        hull = cv2.convexHull(np.round((pts_box - (x0, y0)) * 16).astype(np.int32))
        cover = np.zeros((H, W), np.uint8)
        cv2.fillConvexPoly(cover, hull, 255, cv2.LINE_AA, 4)
        mask = cover.astype(np.float32) / 255
        col = apply_colormap(acc, v.colormap, 0.0, 1.0, float(v.gamma))
        cb = float(v.clear_below)
        if cb > 0:
            mask *= np.clip((acc - cb) / max(0.08 * (1 - cb), 1e-3), 0, 1)
        cv.composite_rgb(roi, col, mask, a * v.slice_opacity, v.glow * 0.3)

    def _draw_iso(self, cv, ctx, v, st, vol, ext, R, lo, hi, a):
        level = lo + float(np.clip(v.threshold, 0, 1)) * (hi - lo)
        step = int(v.smoothness)
        key = ("iso", v.data, v.dataset, ctx.assets.stamp(v.data), int(v.max_size), round(level, 6), step)

        def make():
            try:
                from skimage.measure import marching_cubes
            except ImportError:
                return None
            if not (float(np.nanmin(vol)) < level < float(np.nanmax(vol))):
                return np.zeros((0, 3)), np.zeros((0, 3), np.int64), np.zeros((0, 3))
            work = np.nan_to_num(vol, nan=float(np.nanmin(vol)))
            try:                      # a light blur: noise in scans otherwise shows as speckled facets
                from scipy.ndimage import gaussian_filter
                work = gaussian_filter(work, 0.6 + 0.3 * (step - 1))
            except ImportError:
                pass
            # pad with "outside" so surfaces touching the edge of the volume are closed
            outside = min(float(work.min()), level) - 1e-3 - 0.1 * abs(level)
            work = np.pad(work, 1, constant_values=outside)
            verts, faces, normals, _ = marching_cubes(work, level, step_size=step, allow_degenerate=False)
            return verts - 1.0, faces, normals
        mesh = ctx.assets.memo(key, make)
        if mesh is None:
            ctx.warn(f"{self.name}: isosurfaces need scikit-image (pip install scikit-image)", "mode")
            return
        verts, faces, normals = mesh
        if len(faces) == 0:
            return
        shape = np.array(vol.shape[::-1], np.float64)                      # x, y, z voxels
        f = (verts[:, ::-1] + 0.5) / shape
        pts = self._world(v, ext * max(st.scale, 1e-3), R, f)
        cam = ctx.camera
        xy, z = _project(ctx, pts, st)
        if (z <= cam.near).any():
            return
        # normals: gradient in voxel index space -> world (scale by 1/voxel size, then rotate)
        vox = ext / shape
        nl = normals[:, ::-1] / vox
        nw = nl @ R.T
        nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-12)
        fn = nw[faces].mean(1)
        fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
        light = -cam.forward + 0.6 * cam.upv - 0.3 * cam.right
        light /= np.linalg.norm(light)
        diff = np.abs(fn @ light)
        view = -cam.forward
        half = (light + view) / np.linalg.norm(light + view)
        spec = np.abs(fn @ half) ** 24
        base = np.asarray(v.iso_color, np.float32)
        colors = base[None, :] * (0.22 + 0.78 * diff[:, None]) + 0.35 * spec[:, None]
        order = np.argsort(-z[faces].mean(1))
        if st.progress < 1:
            keep = order[int(len(order) * (1 - st.progress)):]
            order = keep
        cv.triangles(xy, faces[order], np.clip(colors[order], 0, 1.2), a * v.iso_opacity, v.glow * 0.2)


# --------------------------------------------------------------------------- tomography
class _Tomo(SceneObject):
    CATEGORY = IMAGING
    HAS_PROGRESS = False

    def _rect(self, v, st, s):
        cx, cy = (v.position[0] + st.dx) * s, (v.position[1] + st.dy) * s
        W, H = v.size[0] * s * st.scale, v.size[1] * s * st.scale
        return cx - W / 2, cy - H / 2, W, H

    def _blit(self, cv, ctx, v, st, img_rgb, a, nearest=False):
        x0, y0, W, H = self._rect(v, st, ctx.s)
        quad = np.array([[x0, y0], [x0 + W, y0], [x0 + W, y0 + H], [x0, y0 + H]])
        cv.warp(np.ascontiguousarray(img_rgb), quad, a, v.get("glow", 0.2), nearest=nearest)
        if v.get("border_width", 0) > 0:
            cv.polygon(quad, stroke=v.border_color, stroke_alpha=a * 0.8, width=v.border_width * ctx.s, glow=0.3)
        return x0, y0, W, H


def _source_image(ctx, obj, v) -> np.ndarray:
    n = int(v.resolution)
    if v.source == "image" and v.image:
        key = ("tomo_src", seqdata.current_file(ctx, v, "image"), ctx.assets.stamp(v.image), n)
        return ctx.assets.memo(key, lambda: tomo.square(ctx.assets.image(seqdata.current_file(ctx, v, "image")), n))
    return ctx.assets.memo(("phantom", n), lambda: tomo.phantom(n))


def _sinogram(ctx, obj, v):
    img = _source_image(ctx, obj, v)
    ang = tomo.angles(int(v.angles), float(v.angle_range))
    key = ("sino", v.source, v.image if v.source == "image" else "", ctx.assets.stamp(v.image) if v.image else 0,
           int(v.resolution), int(v.angles), float(v.angle_range))
    return ctx.assets.memo(key, lambda: tomo.radon(img, ang)), ang


TOMO_SOURCE = [
    Prop("source", "enum", "phantom", options=("phantom", "image"), group=G_TOMO,
         help="phantom: the Shepp-Logan test head; image: your own slice (made square)"),
    Prop("image", "asset", "", accept="image", group=G_TOMO, help="The slice to scan when Source is image"),
    Prop("resolution", "int", 192, min=32, max=512, group=G_TOMO, help="Pixels across the slice"),
    Prop("angles", "int", 180, min=2, max=720, group=G_TOMO, help="Number of projections in the scan"),
    Prop("angle_range", "number", 180.0, min=1, max=360, step=1, group=G_TOMO, help="Degrees covered by the scan"),
]


@register
class Sinogram(_Tomo):
    TYPE, LABEL, ICON = "sinogram", "Sinogram", "sinogram"
    DESCRIPTION = ("A tomography scan recorded projection by projection: animate Progress from 0 to 1 while "
                   "the sample turns. Pair it with Back-projection to rebuild the slice.")
    PROPS = [
        *TOMO_SOURCE,
        Prop("progress", "number", 1.0, min=0, max=1, step=0.01, group=G_TOMO,
             help="Fraction of the scan recorded so far. Animate it from 0 to 1"),
        Prop("position", "vec2", [1300, 540], group=G_POS, help="Centre"),
        Prop("size", "vec2", [420, 420], group=G_POS, help="Width (detector) and height (angle)"),
        Prop("colormap", "enum", "gray", options=COLORMAPS, group=G_LOOK),
        Prop("show_current", "bool", True, group=G_LOOK, help="Highlight the projection being recorded"),
        Prop("current_color", "color", "gold", group=G_LOOK),
        Prop("profile", "bool", False, group=G_LOOK, help="Plot the current projection above the sinogram"),
        Prop("labels", "bool", True, group=G_LOOK, help="Name the axes: detector position and angle"),
        Prop("label_size", "number", 18, min=6, max=60, step=1, group=G_LOOK),
        Prop("label_color", "color", "cream", group=G_LOOK),
        Prop("border_color", "color", "teal", group=G_LOOK),
        Prop("border_width", "number", 1.5, min=0, max=10, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.2, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def current_angle(self, v) -> float:
        return float(np.clip(v.progress, 0, 1)) * float(v.angle_range)

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        try:
            sino, ang = _sinogram(ctx, self, v)
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "image")
            return None
        nA = len(ang)
        p = float(np.clip(v.progress, 0, 1))
        rows = int(math.floor(p * nA + 1e-9))
        hi = float(sino.max()) or 1.0
        col = apply_colormap(sino / hi, v.colormap, 0.0, 1.0)
        shown = np.zeros_like(col)
        shown[:rows] = col[:rows]
        x0, y0, W, H = self._blit(cv, ctx, v, st, shown, a)
        s = ctx.s
        if v.show_current and 0 < p < 1:
            yy = y0 + H * min(rows, nA - 1) / nA
            cv.polyline(np.array([[x0, yy], [x0 + W, yy]]), v.current_color, a, 2 * s, 1.0)
        if v.profile and rows > 0:
            prof = sino[min(rows, nA) - 1] / hi
            xs = np.linspace(x0, x0 + W, len(prof))
            base = y0 - 10 * s
            pts = np.stack([xs, base - prof * H * 0.28], 1)
            cv.polyline(pts, v.current_color, a, 2 * s, 0.8)
        if v.labels:
            fs = v.label_size
            ctx.draw_text(cv, "detector position", (x0 + W / 2) / s, (y0 + H) / s + 8, fs, v.label_color,
                          align="center", opacity=a * 0.85)
            from .objects2d import draw_rotated_text
            draw_rotated_text(cv, ctx, f"angle 0–{float(v.angle_range):g}°", x0 / s - fs * 1.2, (y0 + H / 2) / s, fs,
                              v.label_color, 90, a * 0.85)
        top = y0 - (H * 0.3 + 10 * s if v.profile else 0)
        return (x0, top, x0 + W, y0 + H)


@register
class Backprojection(_Tomo):
    TYPE, LABEL, ICON = "backprojection", "Back-projection", "backprojection"
    REQUIRED_REFS = ("sinogram",)
    DESCRIPTION = ("The slice rebuilt from a sinogram, one projection at a time (filtered back-projection). "
                   "Choose no filter to show why the filter is needed.")
    PROPS = [
        Prop("sinogram", "ref", "", ref="sinogram", group=G_TOMO, help="The scan to rebuild"),
        Prop("follow", "bool", True, group=G_TOMO, help="Rebuild as far as the sinogram has recorded"),
        Prop("progress", "number", 1.0, min=0, max=1, step=0.01, group=G_TOMO,
             help="Fraction of the projections used, when not following the sinogram"),
        Prop("filter", "enum", "ramp", options=("ramp", "shepp-logan", "cosine", "hann", "none"), group=G_TOMO,
             help="'none' gives the blurred plain back-projection"),
        Prop("position", "vec2", [1300, 540], group=G_POS, help="Centre"),
        Prop("size", "vec2", [420, 420], group=G_POS),
        Prop("colormap", "enum", "gray", options=COLORMAPS, group=G_LOOK),
        Prop("show_angle", "bool", True, group=G_LOOK, help="Draw the direction of the latest projection"),
        Prop("angle_color", "color", "gold", group=G_LOOK),
        Prop("border_color", "color", "teal", group=G_LOOK),
        Prop("border_width", "number", 1.5, min=0, max=10, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.2, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        src = ctx.project.find(v.sinogram) if v.sinogram else None
        if src is None or src.TYPE != "sinogram":
            ctx.warn(f"{self.name}: choose a Sinogram to rebuild", "sinogram")
            return None
        sv = src.resolve(ctx.t, ctx)
        try:
            sino, ang = _sinogram(ctx, src, sv)
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "sinogram")
            return None
        p = float(np.clip(sv.progress if v.follow else v.progress, 0, 1))
        key = ("fbp", src.id, sv.source, sv.image, ctx.assets.stamp(sv.image) if sv.image else 0,
               int(sv.resolution), int(sv.angles), float(sv.angle_range), v.filter)
        stack = ctx.assets.memo(key, lambda: tomo.fbp(sino, ang, v.filter, cumulative=True))
        k = int(math.floor(p * len(ang) + 1e-9))
        x0, y0, W, H = self._rect(v, st, ctx.s)
        if k <= 0:
            img = np.zeros(stack.shape[1:], np.float32)
        else:
            img = stack[min(k, len(ang)) - 1]
        final = stack[-1]
        lo, hi = 0.0, float(np.percentile(final, 99.5)) or 1.0
        col = apply_colormap(np.clip(img, lo, None), v.colormap, lo, hi)
        self._blit(cv, ctx, v, st, col, a)
        if v.show_angle and 0 < k < len(ang):
            th = math.radians(float(ang[k - 1]))
            cx, cy = x0 + W / 2, y0 + H / 2
            dx, dy = -math.sin(th), -math.cos(th)          # the rays of that projection, in the slice's frame
            L = min(W, H) * 0.5
            cv.polyline(np.array([[cx - dx * L, cy - dy * L], [cx + dx * L, cy + dy * L]]), v.angle_color, a * 0.8,
                        1.5 * ctx.s, 0.8)
        return (x0, y0, x0 + W, y0 + H)


# --------------------------------------------------------------------------- scale bars
def _length_from(text: str) -> tuple[float | None, str]:
    text = (text or "").strip()
    if not text:
        return None, ""
    return parse_si(text)


@register
class ScaleBar(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "scalebar", "Scale bar", "scalebar", IMAGING
    REQUIRED_REFS = ("reference",)
    DESCRIPTION = ("A bar of known length for an image (from its pixel size) or a chart (from its data units), "
                   "labelled with SI prefixes: 100 µm, 2.5 mm.")
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        Prop("reference", "ref", "", group=G_BAR, help="The image or chart the bar measures"),
        Prop("pixel_size", "text", "1 µm", group=G_BAR,
             help="Image: the size of one image pixel (0.65 µm). Chart: what one data unit is (1 mm)"),
        Prop("length", "text", "", group=G_BAR, help="Bar length such as 100 µm (empty = a round length near 20% of the width)"),
        Prop("position", "vec2", [1700, 960], group=G_POS, help="Centre of the bar"),
        Prop("thickness", "number", 6, min=1, max=40, step=0.5, group=G_LOOK),
        Prop("color", "color", "white", group=G_LOOK),
        Prop("label_size", "number", 22, min=6, max=80, step=1, group=G_LOOK),
        Prop("label_position", "enum", "above", options=("above", "below", "none"), group=G_LOOK),
        Prop("digits", "int", 3, min=1, max=6, group=G_LOOK, help="Significant digits of the label"),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def physical_per_design_px(self, ctx, v) -> tuple[float, str, float] | None:
        """(physical size of one design pixel, unit, width of the reference in design px)."""
        ref = ctx.project.find(v.reference) if v.reference else None
        if ref is None:
            ctx.warn(f"{self.name}: choose the image or chart the bar measures", "reference")
            return None
        try:
            size, unit = parse_si(v.pixel_size)
        except ValueError as exc:
            ctx.warn(f"{self.name}: {exc}", "pixel_size")
            return None
        rv = ref.resolve(ctx.t, ctx)
        if ref.TYPE == "image":
            try:
                img = ctx.assets.image(seqdata.current_file(ctx, rv, "image"))
            except Exception as exc:
                ctx.warn(f"{self.name}: {exc}", "reference")
                return None
            w_px = img.shape[1]
            return size * w_px / max(float(rv.width), 1e-9), unit, float(rv.width)
        if ref.TYPE == "axes":
            xr = rv.x_range
            return size * abs(float(xr[1]) - float(xr[0])) / max(float(rv.size[0]), 1e-9), unit, float(rv.size[0])
        ctx.warn(f"{self.name}: the reference must be an image or a chart", "reference")
        return None

    def draw(self, cv, ctx, v, st):
        got = self.physical_per_design_px(ctx, v)
        if got is None:
            return None
        per_px, unit, ref_w = got
        try:
            L, lunit = _length_from(v.length)
        except ValueError as exc:
            ctx.warn(f"{self.name}: {exc}", "length")
            return None
        if lunit and unit and lunit != unit:
            ctx.warn(f"{self.name}: the length is in {lunit} but the pixel size in {unit}", "length")
        if L is None:
            L = nice_length(0.2 * ref_w * per_px)
        length_px = L / max(per_px, 1e-300)
        a = v.opacity * st.opacity
        s = ctx.s
        cx, cy = v.position[0] + st.dx, v.position[1] + st.dy
        half = length_px / 2
        th = float(v.thickness)
        bar = np.array([[cx - half, cy - th / 2], [cx - half + length_px * st.progress, cy - th / 2],
                        [cx - half + length_px * st.progress, cy + th / 2], [cx - half, cy + th / 2]])
        cv.polygon(bar * s, fill=v.color, fill_alpha=a, fill_glow=v.glow)
        label = si(L, unit or lunit, int(v.digits))
        box = [cx - half, cy - th / 2, cx + half, cy + th / 2]
        if v.label_position != "none" and st.progress > 0.3:
            ta = a * min(1.0, (st.progress - 0.3) / 0.4)
            if v.label_position == "above":
                b = ctx.draw_text(cv, label, cx, cy - th / 2 - 8, v.label_size, v.color, align="center", valign="bottom",
                                  opacity=ta, glow=v.glow * 0.3)
            else:
                b = ctx.draw_text(cv, label, cx, cy + th / 2 + 8, v.label_size, v.color, align="center", opacity=ta,
                                  glow=v.glow * 0.3)
            if b:
                box = [min(box[0], b[0] / s), min(box[1], b[1] / s), max(box[2], b[2] / s), max(box[3], b[3] / s)]
        return (box[0] * s, box[1] * s, box[2] * s, box[3] * s)


@register
class ScaleBar3D(Object3D):
    TYPE, LABEL, ICON = "scalebar3d", "3D scale bar", "scalebar"
    DESCRIPTION = "A ruler in the 3D scene with end ticks and a label in real units (one scene unit = Unit)."
    HAS_PROGRESS = True
    HAS_LABEL = False
    DEFAULT_ENTER = "draw"
    PROPS = [
        Prop("origin", "vec3", [-20, -20, 0], group=G_GEO, help="Where the bar starts"),
        Prop("direction", "vec3", [1, 0, 0], group=G_GEO, help="Direction of the bar (normalised)"),
        Prop("length", "number", 10, min=0, step=1, group=G_GEO, help="In scene units"),
        Prop("unit", "text", "1 mm", group=G_BAR, help="What one scene unit is in reality, such as 1 mm or 0.1 nm"),
        Prop("color", "color", "white", group=G_LOOK),
        Prop("width", "number", 3, min=0.5, max=20, step=0.5, group=G_LOOK),
        Prop("tick_size", "number", 2, min=0, step=0.5, group=G_LOOK, help="End ticks, in scene units"),
        Prop("label_size", "number", 20, min=6, max=80, step=1, group=G_LOOK),
        Prop("digits", "int", 3, min=1, max=6, group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def center_of(self, v):
        d = np.asarray(v.direction, np.float64)
        d = d / (np.linalg.norm(d) or 1.0)
        return np.asarray(v.origin, np.float64) + d * float(v.length) / 2

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        d = np.asarray(v.direction, np.float64)
        n = np.linalg.norm(d)
        if n < 1e-12:
            return None
        d = d / n
        p0 = np.asarray(v.origin, np.float64)
        p1 = p0 + d * float(v.length) * st.progress
        cam = ctx.camera
        side = np.cross(d, cam.forward)
        if np.linalg.norm(side) < 1e-6:
            side = cam.upv
        side = side / np.linalg.norm(side) * float(v.tick_size) / 2
        pts = np.array([p0, p1, p0 - side, p0 + side, p1 - side, p1 + side])
        xy, z = _project(ctx, pts, st)
        if (z <= cam.near).any():
            return None
        w = v.width * ctx.s
        cv.polyline(xy[:2], v.color, a, w, v.glow)
        cv.polyline(xy[2:4], v.color, a, w, v.glow)
        if st.progress >= 0.999:
            cv.polyline(xy[4:6], v.color, a, w, v.glow)
        try:
            unit_len, unit = parse_si(v.unit)
        except ValueError as exc:
            ctx.warn(f"{self.name}: {exc}", "unit")
            unit_len, unit = 1.0, ""
        mid = (xy[0] + xy[1]) / 2 / ctx.s
        nrm = np.array([-(xy[1] - xy[0])[1], (xy[1] - xy[0])[0]])
        nrm = nrm / (np.linalg.norm(nrm) or 1)
        if nrm[1] > 0:
            nrm = -nrm
        lab = mid + nrm * (v.label_size * 0.9)
        if st.progress > 0.5:
            ctx.draw_text(cv, si(float(v.length) * unit_len, unit, int(v.digits)), lab[0], lab[1], v.label_size, v.color,
                          align="center", valign="middle", opacity=a * min(1, (st.progress - 0.5) * 2), glow=v.glow * 0.3)
        return _bbox(xy)


# --------------------------------------------------------------------------- morph
G_SRC, G_TGT, G_MOVE = "From", "To", "Motion"


@register
class Morph(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "morph", "Points into a chart", "morph", IMAGING
    REQUIRED_REFS = ("source", "axes")
    DESCRIPTION = ("Points that fly from an image's pixels (or a scatter plot) into a chart: a scatter of two "
                   "images' values, a joint histogram, or a stack of histogram bins. Animate Progress.")
    PROPS = [
        Prop("source", "ref", "", group=G_SRC,
             help="An image (its pixels) or a scatter plot (its points) already in the film"),
        Prop("image_b", "asset", "", accept="image", group=G_SRC,
             help="A second image of the same size: its values give y in a joint scatter"),
        Prop("max_points", "int", 3000, min=10, max=200000, group=G_SRC, help="Pixels are sampled on a grid"),
        Prop("axes", "ref", "", ref="axes", group=G_TGT, help="The chart the points land in"),
        Prop("target", "enum", "joint", options=("joint", "histogram"), group=G_TGT,
             help="joint: x = value in the image, y = value in Image b (or the scatter's own points); "
                  "histogram: points stack up in bins of their value"),
        Prop("value", "enum", "x", options=("x", "y"), group=G_TGT, help="For a scatter source: which value to bin"),
        Prop("bins", "int", 30, min=1, max=400, group=G_TGT),
        Prop("height", "number", 0.9, min=0.05, max=1, step=0.05, group=G_TGT, help="Tallest bin, as a fraction of the chart"),
        Prop("progress", "number", 0.0, min=0, max=1, step=0.01, group=G_MOVE,
             help="0 = on the source, 1 = in the chart. Animate it from 0 to 1"),
        Prop("stagger", "number", 0.5, min=0, max=0.95, step=0.05, group=G_MOVE,
             help="How spread out the departures are (0 = all together)"),
        Prop("order", "enum", "random", options=("random", "left_to_right", "top_to_bottom", "by_value"),
             group=G_MOVE, help="Which points leave first"),
        Prop("arc", "number", 0.0, step=10, group=G_MOVE, help="Bend of the flight path, in pixels"),
        Prop("color_mode", "enum", "value", options=("value", "single", "image"), group=G_LOOK,
             help="value: colormap of the source value; image: the pixel's own colour"),
        Prop("color", "color", "ice", group=G_LOOK),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_LOOK),
        Prop("size", "number", 2.5, min=0.3, max=30, step=0.1, group=G_LOOK, help="Point radius in pixels"),
        Prop("style", "enum", "solid", options=("solid", "glow"), group=G_LOOK),
        Prop("glow", "number", 0.4, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def _points(self, ctx, v):
        """Source positions (N,2) in design px, values a (N,), b (N,) or None, colours (N,3) or None."""
        src = ctx.project.find(v.source) if v.source else None
        if src is None:
            raise ValueError("choose a source image or scatter plot")
        sv = src.resolve(ctx.t, ctx)
        if src.TYPE == "image":
            rel = seqdata.current_file(ctx, sv, "image")
            img = ctx.assets.image(rel)
            h, w = img.shape[:2]
            step = max(1, int(round(math.sqrt(h * w / max(int(v.max_points), 1)))))
            iy, ix = np.mgrid[step // 2:h:step, step // 2:w:step]
            iy, ix = iy.ravel(), ix.ravel()
            gray = img if img.ndim == 2 else img[..., :3].mean(axis=2)
            a = gray[iy, ix].astype(np.float64)
            rgb = img[iy, ix, :3].astype(np.float32) if img.ndim == 3 else None
            b = None
            if v.image_b:
                ib = ctx.assets.image(v.image_b)
                if ib.shape[:2] != (h, w):
                    raise ValueError(f"Image b is {ib.shape[1]}×{ib.shape[0]} px but the source is {w}×{h}")
                gb = ib if ib.ndim == 2 else ib[..., :3].mean(axis=2)
                b = gb[iy, ix].astype(np.float64)
            W = float(sv.width)
            H = W * h / max(w, 1)
            px = (ix + 0.5) / w * W - W / 2
            py = (iy + 0.5) / h * H - H / 2
            rot = math.radians(float(sv.get("rotation", 0.0)))
            c, sn = math.cos(rot), math.sin(rot)
            pos = np.stack([px * c - py * sn + sv.position[0], px * sn + py * c + sv.position[1]], 1)
            return pos, a, b, rgb
        if src.TYPE == "scatter":
            tr = ctx.axes(sv.axes)
            if tr is None:
                raise ValueError("the source scatter has no chart")
            xs, ys = src.xy_data(ctx, sv)
            ok = np.isfinite(xs) & np.isfinite(ys)
            xs, ys = xs[ok], ys[ok]
            if len(xs) > int(v.max_points):
                keep = np.random.default_rng(5).choice(len(xs), int(v.max_points), replace=False)
                xs, ys = xs[np.sort(keep)], ys[np.sort(keep)]
            X, Y = tr.map(xs, ys)
            a = xs if v.value == "x" else ys
            return np.stack([X, Y], 1), a.astype(np.float64), (ys if v.value == "x" else xs).astype(np.float64), None
        raise ValueError(f"the source must be an image or a scatter plot, not a {src.LABEL.lower()}")

    def _targets(self, ctx, v, tr, a, b, src_is_scatter):
        if v.target == "joint":
            if b is None:
                raise ValueError("a joint scatter needs Image b (the second value of each pixel)")
            if src_is_scatter:
                X, Y = tr.map(a if v.value == "x" else b, b if v.value == "x" else a)
            else:
                X, Y = tr.map(a, b)
            return np.stack([X, Y], 1)
        # histogram: dots stacked in columns inside each bin
        nb = int(v.bins)
        lo, hi = tr.xmin, tr.xmax
        edges = np.linspace(lo, hi, nb + 1)
        idx = np.clip(np.searchsorted(edges, a, side="right") - 1, 0, nb - 1)
        inside = (a >= lo) & (a <= hi)
        bin_px = abs(tr.scale_x(edges[1] - edges[0]))
        dot = 2 * float(v.size) + 1.0
        m = max(1, int(bin_px * 0.85 // dot))
        counts = np.bincount(idx[inside], minlength=nb)
        rank = np.zeros(len(a), np.int64)
        order = np.argsort(idx, kind="stable")
        starts = np.concatenate([[0], np.cumsum(np.bincount(idx, minlength=nb))[:-1]])
        rank[order] = np.arange(len(a)) - starts[idx[order]]
        rows_max = max(1, int(math.ceil(counts.max() / m))) if counts.size else 1
        col, row = rank % m, rank // m
        cx = (edges[idx] + edges[idx + 1]) / 2
        X = tr.map_x(cx) + (col - (m - 1) / 2) * dot
        Y = tr.y0 + tr.h - (row + 0.5) * (tr.h * float(v.height) / rows_max)
        out = np.stack([X, Y], 1)
        out[~inside] = np.nan
        return out

    def draw(self, cv, ctx, v, st):
        tr = ctx.axes(v.axes)
        if tr is None:
            ctx.warn(f"{self.name}: choose the chart the points land in", "axes")
            return None
        try:
            src_obj = ctx.project.find(v.source) if v.source else None
            pos0, a, b, rgb = self._points(ctx, v)
            dst = self._targets(ctx, v, tr, a, b, src_obj is not None and src_obj.TYPE == "scatter")
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "source")
            return None
        n = len(pos0)
        if n == 0:
            return None
        rng = np.random.default_rng(17)
        if v.order == "left_to_right":
            rank = np.argsort(np.argsort(pos0[:, 0] + rng.random(n) * 1e-3))
        elif v.order == "top_to_bottom":
            rank = np.argsort(np.argsort(pos0[:, 1] + rng.random(n) * 1e-3))
        elif v.order == "by_value":
            rank = np.argsort(np.argsort(a + rng.random(n) * 1e-9))
        else:
            rank = rng.permutation(n)
        stag = float(v.stagger)
        delay = rank / max(n - 1, 1) * stag
        u = np.clip((float(v.progress) - delay) / max(1 - stag, 1e-6), 0, 1)
        e = u * u * (3 - 2 * u)
        moving = np.isfinite(dst).all(axis=1)
        pos = pos0.copy()
        d = dst[moving] - pos0[moving]
        pos[moving] = pos0[moving] + d * e[moving, None]
        if v.arc:
            perp = np.stack([-d[:, 1], d[:, 0]], 1) / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
            pos[moving] += perp * float(v.arc) * np.sin(np.pi * e[moving])[:, None]
        # points that have no place in the chart (outside its range) fade away as they would leave
        alpha_pt = np.where(moving, 1.0, 1.0 - e)
        keep = alpha_pt > 0.02
        pos = pos[keep]
        colors = None
        if v.color_mode == "image" and rgb is not None:
            colors = rgb[keep]
        elif v.color_mode == "value":
            colors = apply_colormap(a[keep][:, None], v.colormap)[:, 0]
        pts = (pos + (st.dx, st.dy)) * ctx.s
        alpha = v.opacity * st.opacity
        if v.style == "solid":
            cv.dots(pts, v.size * ctx.s, v.color, alpha, v.glow, colors)
        else:
            cv.splat(pts, 1.0, v.color, alpha, max(0.5, v.size * ctx.s * 0.6), gain=1.6, glow=v.glow, colors=colors)
        return _bbox(pts)

