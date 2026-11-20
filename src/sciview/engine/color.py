"""Colours: named palette, parsing and colormaps.

Every colour in a project is either a hex string (``"#4fd1c5"``) or the name of
a palette entry (``"teal"``). Names are resolved through the project palette at
render time, so editing the palette recolours the whole film.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Union

import numpy as np

ColorLike = Union[str, Sequence[float], np.ndarray]

#: Default palette, sampled from neon-on-navy explainer films.
DEFAULT_PALETTE: dict[str, str] = {
    "teal": "#4fd1c5",
    "gold": "#ffcf4a",
    "amber": "#f5a23c",
    "blue": "#6cb4fc",
    "ice": "#a5e4fc",
    "cream": "#f3ead8",
    "red": "#ff6b6b",
    "violet": "#c38cff",
    "green": "#7ee08a",
    "white": "#ffffff",
    "gray": "#8b95a7",
    "navy": "#10182a",
}

#: Light palette for white-background figures (papers, posters).
LIGHT_PALETTE: dict[str, str] = {
    "teal": "#0f8f84",
    "gold": "#c98a00",
    "amber": "#d9730d",
    "blue": "#2563eb",
    "ice": "#0891b2",
    "cream": "#1f2937",
    "red": "#dc2626",
    "violet": "#7c3aed",
    "green": "#16a34a",
    "white": "#111827",
    "gray": "#6b7280",
    "navy": "#e5e7eb",
}


def hex_to_rgb(value: str) -> np.ndarray:
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def rgb_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = (int(round(float(np.clip(c, 0, 1)) * 255)) for c in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_color(value: ColorLike, palette: Mapping[str, str] | None = None) -> np.ndarray:
    """Return an RGB float32 array in 0..1 for a hex string, palette name or sequence."""
    if isinstance(value, np.ndarray):
        return value.astype(np.float32)[:3]
    if isinstance(value, (list, tuple)):
        arr = np.asarray(value, np.float32)[:3]
        return arr / 255.0 if arr.max() > 1.0 else arr
    if not isinstance(value, str):
        raise ValueError(f"cannot read colour {value!r}")
    v = value.strip()
    pal = palette if palette is not None else DEFAULT_PALETTE
    if v.lower() in pal:
        return hex_to_rgb(pal[v.lower()])
    if v.lower() in DEFAULT_PALETTE:
        return hex_to_rgb(DEFAULT_PALETTE[v.lower()])
    if v.startswith("#") or len(v) in (3, 6):
        return hex_to_rgb(v)
    raise ValueError(f"unknown colour {value!r}: use #rrggbb or a palette name")


# --------------------------------------------------------------------------- colormaps
# Control points (position, hex). Scientific maps sampled from matplotlib (BSD/CC0).
_CMAPS: dict[str, list[tuple[float, str]]] = {
    "gray": [(0, "#000000"), (1, "#ffffff")],
    "gold": [(0, "#000000"), (0.35, "#5a2c00"), (0.65, "#d9820f"), (0.85, "#ffcf4a"), (1, "#fff6d8")],
    "ice": [(0, "#000000"), (0.35, "#0b2a5c"), (0.65, "#2f7de1"), (0.85, "#8fd3ff"), (1, "#f2fbff")],
    "teal": [(0, "#000000"), (0.4, "#0c3f42"), (0.75, "#2fb3a8"), (1, "#e6fffb")],
    "viridis": [(0, "#440154"), (0.125, "#472d7b"), (0.25, "#3b528b"), (0.375, "#2c728e"),
                (0.5, "#21918c"), (0.625, "#28ae80"), (0.75, "#5ec962"), (0.875, "#addc30"), (1, "#fde725")],
    "magma": [(0, "#000004"), (0.125, "#1c1044"), (0.25, "#4f127b"), (0.375, "#812581"),
              (0.5, "#b5367a"), (0.625, "#e55064"), (0.75, "#fb8761"), (0.875, "#fec287"), (1, "#fcfdbf")],
    "inferno": [(0, "#000004"), (0.125, "#1f0c48"), (0.25, "#550f6d"), (0.375, "#88226a"),
                (0.5, "#ba3655"), (0.625, "#e35933"), (0.75, "#f98e09"), (0.875, "#f9cb35"), (1, "#fcffa4")],
    "plasma": [(0, "#0d0887"), (0.125, "#4c02a1"), (0.25, "#7e03a8"), (0.375, "#a92395"),
               (0.5, "#cc4778"), (0.625, "#e56b5d"), (0.75, "#f89540"), (0.875, "#fdc527"), (1, "#f0f921")],
    "cividis": [(0, "#00224e"), (0.25, "#3d4d6a"), (0.5, "#7c7b78"), (0.75, "#bcaf6f"), (1, "#fee838")],
    "coolwarm": [(0, "#3b4cc0"), (0.25, "#8db0fe"), (0.5, "#dddddd"), (0.75, "#f49a7b"), (1, "#b40426")],
}

COLORMAPS = tuple(_CMAPS)


@lru_cache(maxsize=64)
def colormap_lut(name: str) -> np.ndarray:
    """256x3 float32 lookup table for a colormap name (built-in, or any matplotlib name)."""
    if name in _CMAPS:
        pts = _CMAPS[name]
        xs = np.array([p for p, _ in pts], np.float32)
        cs = np.stack([hex_to_rgb(c) for _, c in pts])
        u = np.linspace(0, 1, 256, dtype=np.float32)
        return np.stack([np.interp(u, xs, cs[:, k]) for k in range(3)], axis=1).astype(np.float32)
    try:  # optional: any matplotlib colormap
        import matplotlib  # noqa: F401
        from matplotlib import colormaps

        cmap = colormaps[name]
        return cmap(np.linspace(0, 1, 256))[:, :3].astype(np.float32)
    except Exception:
        return colormap_lut("gray")


def apply_colormap(values: np.ndarray, name: str, vmin: float | None = None,
                   vmax: float | None = None, gamma: float = 1.0) -> np.ndarray:
    """Map a 2D array to RGB with a colormap. vmin/vmax default to the data range."""
    v = np.asarray(values, np.float32)
    lo = float(np.nanmin(v)) if vmin is None else float(vmin)
    hi = float(np.nanmax(v)) if vmax is None else float(vmax)
    if hi <= lo:
        hi = lo + 1e-6
    u = np.clip((v - lo) / (hi - lo), 0, 1)
    if gamma != 1.0:
        u = u ** (1.0 / max(gamma, 1e-3))
    u = np.nan_to_num(u, nan=0.0)
    return colormap_lut(name)[(u * 255).astype(np.int32)]
