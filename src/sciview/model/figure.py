"""A matplotlib figure placed in the film, redrawn per frame by a Python function."""
from __future__ import annotations

import numpy as np

from .. import figures
from .base import Prop, SceneObject, register

G_FIG, G_POS, G_LOOK = "Figure", "Position", "Appearance"


@register
class Figure(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "figure", "Matplotlib figure", "figure", "Charts"
    DESCRIPTION = ("A matplotlib figure drawn by your Python function at every frame (film.add_figure in a "
                   "script). The editor shows the snapshot saved with the project.")
    PROPS = [
        Prop("callback", "text", "", group=G_FIG, help="Name of the Python function (set by film.add_figure)"),
        Prop("snapshot", "asset", "", accept="image", group=G_FIG,
             help="Picture shown where the function is not available (saved automatically)"),
        Prop("still", "bool", False, group=G_FIG, help="The figure does not change with time: draw it once"),
        Prop("style", "enum", "sciview", options=("sciview", "matplotlib"), group=G_FIG,
             help="sciview: transparent background and light text; matplotlib: your own style"),
        Prop("position", "vec2", [960, 540], group=G_POS, help="Centre"),
        Prop("size", "vec2", [800, 500], group=G_POS, help="Width and height in pixels"),
        Prop("dpi", "number", 100, min=20, max=600, step=10, group=G_POS,
             help="Pixels per inch at full size: larger makes text and lines smaller"),
        Prop("glow", "number", 0.0, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def depends_on_time(self) -> bool:
        return (bool(figures.get(self.props.get("callback", ""))) and not self.props.get("still", False)) \
            or super().depends_on_time()

    def rgba(self, ctx, v, scale: float | None = None):
        func = figures.get(v.callback)
        s = ctx.s if scale is None else scale
        W, H = int(round(float(v.size[0]) * s)), int(round(float(v.size[1]) * s))
        if func is not None:
            return figures.render(func, ctx.t, W, H, float(v.dpi) * s, v.style)
        return None

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        cx, cy = (v.position[0] + st.dx) * s, (v.position[1] + st.dy) * s
        W, H = float(v.size[0]) * s * st.scale, float(v.size[1]) * s * st.scale
        quad = np.array([[cx - W / 2, cy - H / 2], [cx + W / 2, cy - H / 2], [cx + W / 2, cy + H / 2],
                         [cx - W / 2, cy + H / 2]])
        try:
            buf = self.rgba(ctx, v)
        except Exception as exc:  # errors in the user's function
            ctx.warn(f"{self.name}: the figure function failed: {exc}", "callback")
            buf = None
        if buf is None and v.snapshot:
            try:
                img = ctx.assets.image(v.snapshot)
                buf = img if img.ndim == 3 and img.shape[2] == 4 else None
                if buf is None:
                    rgb = img if img.ndim == 3 else np.repeat(img[..., None], 3, axis=2)
                    buf = np.concatenate([rgb[..., :3], np.ones(rgb.shape[:2] + (1,), np.float32)], axis=2)
            except Exception as exc:
                ctx.warn(f"{self.name}: {exc}", "snapshot")
        if buf is None:
            if not figures.get(v.callback):
                ctx.warn(f"{self.name}: drawn by a Python script (film.add_figure); run the script to see it",
                         "callback")
            cv.polygon(quad, stroke=ctx.color("gray"), stroke_alpha=a * 0.6, width=1.5 * s)
            ctx.draw_text(cv, "Matplotlib figure", cx / s, cy / s, 22, ctx.color("gray"), align="center",
                          valign="middle", opacity=a * 0.7)
            return (quad[0, 0], quad[0, 1], quad[2, 0], quad[2, 1])
        rgb = np.ascontiguousarray(buf[..., :3])
        mask = np.ascontiguousarray(buf[..., 3])
        cv.warp(rgb, quad, a, v.glow, mask)
        return (quad[0, 0], quad[0, 1], quad[2, 0], quad[2, 1])
