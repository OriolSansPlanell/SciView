"""Molecules from PDB and XYZ files: ball-and-stick, space-filling, sticks, wire and backbone ribbons."""
from __future__ import annotations

import math

import numpy as np

from ..engine.camera import rotation_matrix
from ..engine.color import hex_to_rgb
from .base import Prop, register
from .objects3d import Object3D, _bbox, _project

G_MOL, G_GEO, G_LOOK = "Molecule", "Geometry", "Appearance"

# Jmol-like element colours, slightly softened for dark backgrounds
ELEMENT_COLORS = {
    "H": "#f2f2f2", "C": "#9aa3b2", "N": "#5b7cfa", "O": "#ff5a5a", "S": "#ffd93d", "P": "#ff9a3c",
    "F": "#90e050", "Cl": "#3fd17a", "Br": "#c0603a", "I": "#a463d9", "Fe": "#e0824a", "Na": "#ab5cf2",
    "Mg": "#8aff00", "K": "#8f40d4", "Ca": "#7dd3c0", "Zn": "#7d80b0", "Cu": "#c88033", "Si": "#f0c8a0",
    "B": "#ffb5b5", "Se": "#ffa100", "Li": "#cc80ff", "Al": "#bfa6a6", "Ti": "#bfc2c7", "Mn": "#9c7ac7",
    "Co": "#f090a0", "Ni": "#50d050", "Au": "#ffd123", "Ag": "#c0c0c0", "Pt": "#d0d0e0", "U": "#008fff",
}
VDW_RADIUS = {"H": 1.10, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80, "F": 1.47, "Cl": 1.75,
              "Br": 1.85, "I": 1.98, "Na": 2.27, "Mg": 1.73, "K": 2.75, "Ca": 2.31, "Fe": 1.94, "Zn": 1.39,
              "Cu": 1.40, "Si": 2.10, "Se": 1.90}
CHAIN_COLORS = ["#4fd1c5", "#ffcf4a", "#6cb4fc", "#ff6b6b", "#c38cff", "#7ee08a", "#f5a23c", "#a5e4fc"]


RAINBOW = ["#6cb4fc", "#4fd1c5", "#7ee08a", "#ffcf4a", "#f5a23c", "#ff6b6b"]


def _rainbow(u: np.ndarray) -> np.ndarray:
    """Blue (start of a chain) to red (end), through the palette's teal, green and gold."""
    stops = np.stack([hex_to_rgb(c) for c in RAINBOW])
    x = np.linspace(0, 1, len(stops))
    u = np.clip(np.asarray(u, np.float64), 0, 1)
    return np.stack([np.interp(u, x, stops[:, k]) for k in range(3)], axis=1).astype(np.float32)


def _catmull(points: np.ndarray, per: int) -> np.ndarray:
    """Smooth curve through points (Catmull-Rom, ``per`` samples per segment)."""
    p = np.vstack([points[:1], points, points[-1:]])
    out = []
    t = np.linspace(0, 1, per, endpoint=False)[:, None]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(points[-1:])
    return np.vstack(out)


def _tube(curve: np.ndarray, r: float, colors: np.ndarray, sides: int = 8):
    """A tube mesh around a curve: vertices, outward normals, triangles and one colour per triangle."""
    n = len(curve)
    T = np.gradient(curve, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    # parallel transport of a normal along the curve (no twisting)
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = np.zeros_like(curve)
    N[0] = np.cross(T[0], ref)
    N[0] /= np.linalg.norm(N[0])
    for i in range(1, n):
        v = N[i - 1] - (N[i - 1] @ T[i]) * T[i]
        nv = np.linalg.norm(v)
        N[i] = v / nv if nv > 1e-9 else N[i - 1]
    B = np.cross(T, N)
    th = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = np.cos(th)[None, :, None] * N[:, None, :] + np.sin(th)[None, :, None] * B[:, None, :]
    verts = (curve[:, None, :] + r * ring).reshape(-1, 3)
    normals = ring.reshape(-1, 3)
    faces, fcol = [], []
    for i in range(n - 1):
        for k in range(sides):
            a, b = i * sides + k, i * sides + (k + 1) % sides
            c, d = a + sides, b + sides
            faces += [(a, b, d), (a, d, c)]
            fcol += [colors[i], colors[i]]
    return verts, normals, np.asarray(faces, np.int64), np.asarray(fcol, np.float32)


@register
class Molecule(Object3D):
    TYPE, LABEL, ICON = "molecule", "Molecule", "molecule"
    DESCRIPTION = ("Atoms and bonds from a PDB or XYZ file, as ball-and-stick, space-filling, sticks, wire, or a "
                   "ribbon along a protein's backbone with its ligands. The draw effect builds it atom by atom.")
    HAS_PROGRESS = True
    PROPS = [
        Prop("model", "asset", "", accept="molecule", group=G_MOL, help="PDB or XYZ file"),
        Prop("style", "enum", "ball_and_stick", options=("ball_and_stick", "spacefill", "sticks", "wire", "ribbon"),
             group=G_MOL, help="ribbon: a smooth tube through the backbone, with ligands as ball-and-stick"),
        Prop("color_by", "enum", "element", options=("element", "chain", "rainbow", "single"), group=G_MOL,
             help="rainbow runs along each chain from start to end"),
        Prop("color", "color", "teal", group=G_MOL, help="Used when colouring by single"),
        Prop("hydrogens", "bool", True, group=G_MOL),
        Prop("center", "vec3", [0, 0, 0], group=G_GEO, help="Where the molecule's centre goes"),
        Prop("scale", "number", 2.0, min=0.01, step=0.1, group=G_GEO, help="Scene units per ångström"),
        Prop("rotation", "vec3", [0, 0, 0], group=G_GEO, help="Animate it to turn the molecule"),
        Prop("atom_scale", "number", 0.3, min=0.05, max=1.5, step=0.05, group=G_LOOK,
             help="Ball size as a fraction of the van der Waals radius (ball-and-stick)"),
        Prop("bond_radius", "number", 0.16, min=0.02, max=1, step=0.01, group=G_LOOK, help="In ångström"),
        Prop("ribbon_radius", "number", 0.5, min=0.05, max=3, step=0.05, group=G_LOOK, help="In ångström"),
        Prop("glow", "number", 0.15, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def _mol(self, ctx, v):
        return ctx.assets.molecule(v.model)

    def _world(self, mol, v) -> np.ndarray:
        R = rotation_matrix(*v.rotation)
        c = mol.xyz.mean(axis=0)
        return (mol.xyz - c) * float(v.scale) @ R.T + np.asarray(v.center, np.float64)

    def label_anchor(self, ctx, v):
        try:
            p = self._world(self._mol(ctx, v), v)
            return np.array([p.min(0), p.max(0)])
        except Exception:
            return None

    def _atom_colors(self, mol, v) -> np.ndarray:
        n = len(mol)
        if v.color_by == "single":
            return np.tile(np.asarray(v.color, np.float32), (n, 1))
        if v.color_by == "chain":
            chains = {c: i for i, c in enumerate(dict.fromkeys(mol.chains))}
            return np.stack([hex_to_rgb(CHAIN_COLORS[chains[c] % len(CHAIN_COLORS)]) for c in mol.chains])
        if v.color_by == "rainbow":
            out = np.zeros((n, 3), np.float32)
            for ch in dict.fromkeys(mol.chains):
                idx = np.array([i for i, c in enumerate(mol.chains) if c == ch])
                out[idx] = _rainbow(np.linspace(0, 1, len(idx)))
            return out
        return np.stack([hex_to_rgb(ELEMENT_COLORS.get(e, "#ff80c0")) for e in mol.elements])

    def draw(self, cv, ctx, v, st):
        if not v.model:
            return None
        try:
            mol = self._mol(ctx, v)
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "model")
            return None
        a = v.opacity * st.opacity
        cam = ctx.camera
        pts = self._world(mol, v)
        if st.scale != 1:
            c0 = np.asarray(v.center, np.float64)
            pts = c0 + (pts - c0) * st.scale
        xy, z = _project(ctx, pts, st)
        n = len(mol)
        shown = np.ones(n, bool)
        if not v.hydrogens:
            shown &= np.array([e != "H" for e in mol.elements])
        if st.progress < 1:
            shown &= np.arange(n) < int(math.ceil(n * st.progress))
        shown &= z > cam.near
        if not shown.any():
            return None
        colors = self._atom_colors(mol, v)
        sc = float(v.scale) * st.scale
        style = v.style
        ribbon = style == "ribbon"
        atom_on = shown.copy()
        if ribbon:
            atom_on &= np.array(mol.hetero) & np.array([r not in ("HOH", "WAT", "DOD") for r in mol.resnames])
        if style == "spacefill":
            rad = np.array([VDW_RADIUS.get(e, 1.8) for e in mol.elements]) * sc
        elif style in ("sticks", "wire"):
            rad = np.full(n, float(v.bond_radius) * sc)
        else:
            rad = np.array([VDW_RADIUS.get(e, 1.8) for e in mol.elements]) * sc * float(v.atom_scale)
        rpx = cam.focal * rad / np.maximum(z, cam.near)
        bpx = cam.focal * float(v.bond_radius) * sc / np.maximum(z, cam.near) * 2
        prims = []        # (depth, kind, data)
        if style != "spacefill":
            for i, j in mol.bonds:
                if not (atom_on[i] and atom_on[j]):
                    continue
                mid = (xy[i] + xy[j]) / 2
                zm = (z[i] + z[j]) / 2
                for k, other in ((i, j), (j, i)):
                    prims.append(((z[k] + zm) / 2 + 1e-4, 1, (xy[k], mid, (bpx[k] + bpx[other]) / 2, colors[k])))
        if style != "wire":
            for i in np.flatnonzero(atom_on):
                prims.append((z[i], 0, (xy[i], rpx[i], colors[i])))
        if ribbon:
            rr = float(v.ribbon_radius) * sc
            lightdir = -cam.forward + 0.6 * cam.upv - 0.4 * cam.right
            lightdir /= np.linalg.norm(lightdir)
            for ch_i, (_ch, idx) in enumerate(mol.backbone()):
                idx = idx[shown[idx]]
                if len(idx) < 2:
                    continue
                curve = _catmull(pts[idx], 6)
                if v.color_by in ("element", "rainbow"):
                    ccol = _rainbow(np.linspace(0, 1, len(curve)))
                elif v.color_by == "chain":
                    ccol = np.tile(hex_to_rgb(CHAIN_COLORS[ch_i % len(CHAIN_COLORS)]), (len(curve), 1))
                else:
                    ccol = np.tile(np.asarray(v.color, np.float32), (len(curve), 1))
                verts, normals, faces, fcol = _tube(curve, rr, ccol, sides=8)
                vxy, vz = _project(ctx, verts, st)
                fz = vz[faces].mean(1)
                fn = normals[faces].mean(1)
                fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
                shade = 0.3 + 0.7 * np.clip(fn @ lightdir, 0, 1)
                spec = np.clip(fn @ ((lightdir - cam.forward) / np.linalg.norm(lightdir - cam.forward)), 0, 1) ** 20
                face_col = fcol * shade[:, None] + 0.3 * spec[:, None]
                front = (fn @ -cam.forward) > -0.2
                for f, zz, c in zip(faces[front], fz[front], face_col[front]):
                    if (vz[f] > cam.near).all():
                        prims.append((zz, 3, (vxy[f], c)))
        if not prims:
            return None
        allxy = xy[shown]
        pad = float(np.max(rpx[shown])) + 4 if shown.any() else 4
        pt = cv.painter(allxy, pad)
        if pt is None:
            return None
        light = np.array([-0.35, -0.45])
        for _, kind, d in sorted(prims, key=lambda p: -p[0]):
            if kind == 0:
                (x, y), r, c = d
                if r < 0.6:
                    continue
                c = np.asarray(c, np.float32)
                pt.circle(x, y, r, c * 0.45)
                pt.circle(x + light[0] * r * 0.12, y + light[1] * r * 0.12, r * 0.86, c * 0.72)
                pt.circle(x + light[0] * r * 0.25, y + light[1] * r * 0.25, r * 0.6, c * 0.95)
                pt.circle(x + light[0] * r * 0.42, y + light[1] * r * 0.42, r * 0.22, np.minimum(c * 1.1 + 0.35, 1.3))
            elif kind == 3:
                tri, c = d
                pt.polygon(tri, np.minimum(c, 1.3))
            else:
                p0, p1, w, c = d
                c = np.asarray(c, np.float32)
                if kind == 1 and style == "wire":
                    pt.line(p0, p1, max(1.5, 2.0 * ctx.s), c)
                    continue
                w = max(w, 1.0)
                pt.line(p0, p1, w, c * 0.5)
                pt.line(p0, p1, max(1.0, w * 0.55), c * 0.9)
                if w > 4:
                    off = np.array([light[0], light[1]]) * w * 0.18
                    pt.line(np.asarray(p0) + off, np.asarray(p1) + off, max(1.0, w * 0.18), np.minimum(c * 1.1 + 0.25, 1.2))
        pt.done(a, v.glow)
        r = float(np.max(rpx[shown]))
        b = _bbox(allxy)
        return (b[0] - r, b[1] - r, b[2] + r, b[3] + r) if b else None
