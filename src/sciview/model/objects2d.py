"""2D overlay objects, positioned in design pixels (1920 x 1080 by default, origin top-left)."""
from __future__ import annotations

import math
import re

import cv2
import numpy as np

from ..engine.surface import arrow_head, ellipse_points, rounded_rect, truncate_path
from ..engine.text import MATH_ERRORS, render_math
from ..engine.units import format_number
from . import data as seqdata
from .base import Prop, SceneObject, register
from .objects3d import IMAGE_PROPS, prepare_image

G_POS, G_TEXT, G_LOOK = "Position", "Text", "Appearance"
WEIGHTS = ("light", "regular", "medium", "bold")
ALIGN = ("left", "center", "right")
VALIGN = ("top", "middle", "bottom", "baseline")

_FMT = re.compile(r"\{(value|x|y|t)(?::([^{}]*))?\}")


def format_values(text: str, **values) -> str:
    """Replace ``{value}``, ``{value:.1f}``, ``{x}``, ``{y}`` ... without touching markup braces."""
    def rep(m):
        name, spec = m.group(1), m.group(2)
        if name not in values:
            return m.group(0)
        try:
            return format_number(values[name], spec)
        except (ValueError, TypeError):
            return str(values[name])
    return _FMT.sub(rep, text)


def _scaled_rect(x, y, w, h, st, s):
    """Rect in output px after slide and pop (scaled about its centre)."""
    cx, cy = (x + w / 2 + st.dx) * s, (y + h / 2 + st.dy) * s
    W, H = w * s * st.scale, h * s * st.scale
    return cx - W / 2, cy - H / 2, W, H


class Object2D(SceneObject):
    CATEGORY = "Shapes & media"

    def to_px_points(self, ctx, pts, st, axes_ref: str = "", about=None):
        """Design points (or data points if ``axes_ref``) to output px, with slide/pop applied."""
        pts = np.asarray(pts, np.float64).reshape(-1, 2)
        if axes_ref:
            tr = ctx.axes(axes_ref)
            if tr is not None:
                X, Y = tr.map(pts[:, 0], pts[:, 1])
                pts = np.stack([X, Y], 1)
        if st.scale != 1:
            c = pts.mean(0) if about is None else np.asarray(about, np.float64)
            pts = c + (pts - c) * st.scale
        return (pts + (st.dx, st.dy)) * ctx.s


# --------------------------------------------------------------------------- text
@register
class Title(Object2D):
    TYPE, LABEL, ICON, CATEGORY = "title", "Title", "title", "Text"
    DESCRIPTION = "Section title with an optional subtitle, top-left."
    TEXTUAL = True
    DEFAULT_ENTER = "slide_up"
    PROPS = [
        Prop("text", "text", "Title", group=G_TEXT),
        Prop("subtitle", "text", "", group=G_TEXT),
        Prop("position", "vec2", [80, 60], group=G_POS),
        Prop("title_size", "number", 46, min=8, max=200, step=1, group=G_LOOK),
        Prop("subtitle_size", "number", 22, min=6, max=120, step=1, group=G_LOOK),
        Prop("title_color", "color", "gold", group=G_LOOK),
        Prop("subtitle_color", "color", "cream", group=G_LOOK),
        Prop("weight", "enum", "bold", options=WEIGHTS, group=G_LOOK),
        Prop("align", "enum", "left", options=ALIGN, group=G_POS),
        Prop("glow", "number", 0.15, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        x, y = v.position[0] + st.dx, v.position[1] + st.dy
        b1 = ctx.draw_text(cv, v.text, x, y, v.title_size, v.title_color, align=v.align, opacity=a,
                           glow=v.glow, weight=v.weight, progress=st.progress, scale=st.scale)
        b2 = None
        if v.subtitle:
            y2 = y + v.title_size * st.scale * 1.22
            b2 = ctx.draw_text(cv, v.subtitle, x, y2, v.subtitle_size, v.subtitle_color, align=v.align,
                               opacity=a * 0.9, scale=st.scale, progress=st.progress)
        boxes = [b for b in (b1, b2) if b]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


CAPTION_STYLES = ("plain", "box", "band", "outline", "shadow")


@register
class Caption(Object2D):
    TYPE, LABEL, ICON, CATEGORY = "caption", "Caption", "caption", "Text"
    DESCRIPTION = "Narration line at the bottom of the frame. Also exported as subtitles (.srt)."
    TEXTUAL = True
    DEFAULT_DURATION = 4.0
    PROPS = [
        Prop("text", "longtext", "A caption explains what is happening.", group=G_TEXT),
        Prop("position", "vec2", [960, 1000], group=G_POS, help="Centre of the text"),
        Prop("size", "number", 30, min=8, max=120, step=1, group=G_LOOK),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("weight", "enum", "regular", options=WEIGHTS, group=G_LOOK),
        Prop("max_width", "number", 1500, min=0, step=10, group=G_POS, help="Wrap width in pixels (0 = no wrap)"),
        Prop("style", "enum", "plain", options=CAPTION_STYLES, group=G_LOOK,
             help="plain, box (a panel behind the text), band (across the frame), outline or shadow: "
                  "box, band and outline stay readable over busy pictures"),
        Prop("background_color", "color", "navy", group=G_LOOK, help="Colour of the box or band"),
        Prop("background_opacity", "number", 0.0, min=0, max=1, step=0.01, group=G_LOOK,
             help="0 with the box or band style means 0.8"),
        Prop("glow", "number", 0.0, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def backing(self, v) -> tuple[str, float] | None:
        """The panel the text sits on, (colour, opacity), if its style has one."""
        style = v.get("style", "plain")
        op = float(v.background_opacity)
        if style in ("box", "band"):
            return v.background_color, op if op > 0 else 0.8
        return (v.background_color, op) if op > 0 else None

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        x, y = v.position[0] + st.dx, v.position[1] + st.dy
        style = v.get("style", "plain")
        back = self.backing(v)
        kw = dict(align="center", valign="middle", weight=v.weight, max_width=v.max_width, progress=st.progress,
                  scale=st.scale)
        if style == "band":
            # measure the text, then a band across the whole frame at its height
            box = ctx.text_bounds(v.text, x, y, v.size, align="center", valign="middle", weight=v.weight,
                                  max_width=v.max_width, scale=st.scale)
            if box is not None and a > 0:
                pad = 0.45 * v.size * ctx.s
                W = ctx.project.size[0] * ctx.s
                band = np.array([[0, box[1] - pad], [W, box[1] - pad], [W, box[3] + pad], [0, box[3] + pad]])
                cv.polygon(band, fill=ctx.color(back[0]), fill_alpha=back[1] * a)
        elif style in ("outline", "shadow"):
            d = max(1.0, v.size * (0.06 if style == "outline" else 0.08))
            offsets = ([(dx * d, dy * d) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
                       if style == "outline" else [(d, d)])
            dark = ctx.color("#000000")
            for ox, oy in offsets:
                ctx.draw_text(cv, v.text, x + ox, y + oy, v.size, dark,
                              opacity=a * (0.85 if style == "outline" else 0.65), **kw)
        box_kw = {} if style == "band" or back is None else {"background": back[0], "background_alpha": back[1]}
        return ctx.draw_text(cv, v.text, x, y, v.size, v.color, opacity=a, glow=v.glow, **kw, **box_kw)


@register
class Text(Object2D):
    TYPE, LABEL, ICON, CATEGORY = "text", "Text", "text", "Text"
    DESCRIPTION = "Free text. Use {value} or {value:.1f} to show an animated number (counters)."
    TEXTUAL = True
    PROPS = [
        Prop("text", "longtext", "Text", group=G_TEXT,
             help="Markup: H_2O, ^6Li, x_{max}, \\alpha, **bold**. {value:.2f} shows the Value below, "
                  "{value:si:m} with an SI prefix (2.5 mm), {t:.1f} the film time"),
        Prop("value", "number", 0.0, group=G_TEXT, help="Animate it to make a counter"),
        Prop("position", "vec2", [960, 540], group=G_POS),
        Prop("size", "number", 36, min=4, max=300, step=1, group=G_LOOK),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("weight", "enum", "regular", options=WEIGHTS, group=G_LOOK),
        Prop("align", "enum", "left", options=ALIGN, group=G_POS),
        Prop("valign", "enum", "top", options=VALIGN, group=G_POS),
        Prop("line_spacing", "number", 1.25, min=0.6, max=3, step=0.05, group=G_LOOK),
        Prop("max_width", "number", 0, min=0, step=10, group=G_POS, help="Wrap width in pixels (0 = no wrap)"),
        Prop("rotation", "number", 0.0, min=-360, max=360, step=1, group=G_POS, help="Degrees"),
        Prop("background_color", "color", "navy", group=G_LOOK),
        Prop("background_opacity", "number", 0.0, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 0.0, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        text = format_values(v.text, value=float(v.value), t=ctx.t)
        if abs(float(v.rotation)) < 0.01:
            return ctx.draw_text(cv, text, v.position[0] + st.dx, v.position[1] + st.dy, v.size, v.color,
                                 align=v.align, valign=v.valign, opacity=a, glow=v.glow, weight=v.weight,
                                 line_spacing=v.line_spacing, max_width=v.max_width, progress=st.progress,
                                 scale=st.scale, background=v.background_color,
                                 background_alpha=v.background_opacity)
        return draw_rotated_text(cv, ctx, text, v.position[0] + st.dx, v.position[1] + st.dy, v.size * st.scale,
                                 v.color, float(v.rotation), a, v.glow, v.weight, v.align)


def draw_rotated_text(cv, ctx, text, x, y, size, color, angle, alpha, glow=0.0, weight="regular", align="center"):
    """Text rotated about its anchor (x, y) in design px; returns bbox in output px."""
    img = ctx.text_image(text, size, weight, align)
    m = img.mask
    h, w = m.shape
    if abs((angle % 360) - 90) < 0.01 or abs((angle % 360) - 270) < 0.01:
        rm = np.rot90(m, 1 if abs((angle % 360) - 90) < 0.01 else 3)
    else:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        nw, nh = int(h * sin + w * cos) + 2, int(h * cos + w * sin) + 2
        M[0, 2] += nw / 2 - w / 2
        M[1, 2] += nh / 2 - h / 2
        rm = cv2.warpAffine(m, M, (nw, nh), flags=cv2.INTER_LINEAR)
    rh, rw = rm.shape
    X, Y = x * ctx.s, y * ctx.s
    left, top = X - rw / 2, Y - rh / 2
    cv.blit(np.ascontiguousarray(rm), left, top, color=color, alpha=alpha, glow=glow)
    return (left, top, left + rw, top + rh)


@register
class Equation(Object2D):
    TYPE, LABEL, ICON, CATEGORY = "equation", "Equation (LaTeX)", "equation", "Text"
    DESCRIPTION = "A formula in LaTeX syntax, rendered with matplotlib's mathtext (no LaTeX install needed)."
    PROPS = [
        Prop("tex", "longtext", r"\mu = -\frac{\ln T}{d}", group=G_TEXT, help="LaTeX math, e.g. E = mc^2 or \\frac{a}{b}"),
        Prop("position", "vec2", [960, 540], group=G_POS),
        Prop("size", "number", 44, min=6, max=300, step=1, group=G_LOOK),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("align", "enum", "center", options=ALIGN, group=G_POS),
        Prop("valign", "enum", "middle", options=("top", "middle", "bottom"), group=G_POS),
        Prop("font", "enum", "dejavusans", options=("dejavusans", "cm", "stix", "stixsans", "dejavuserif"), group=G_LOOK),
        Prop("glow", "number", 0.1, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        size = round(v.size * ctx.s * st.scale, 2)
        img = render_math(v.tex, size, v.font)
        if img is None:
            why = MATH_ERRORS.get((v.tex, round(float(size), 2), v.font), "unknown error")
            ctx.warn(f"{self.name}: could not render the formula ({why}); showing it as text", "tex")
            return ctx.draw_text(cv, v.tex, v.position[0] + st.dx, v.position[1] + st.dy, v.size, v.color,
                                 align=v.align, valign=v.valign, opacity=a)
        w, h = img.width - 2 * img.pad, img.height - 2 * img.pad
        X, Y = (v.position[0] + st.dx) * ctx.s, (v.position[1] + st.dy) * ctx.s
        left = {"center": X - w / 2, "right": X - w}.get(v.align, X)
        top = {"middle": Y - h / 2, "bottom": Y - h}.get(v.valign, Y)
        cv.blit(img.mask, left - img.pad, top - img.pad, color=v.color, alpha=a, glow=v.glow)
        return (left, top, left + w, top + h)


@register
class Legend(Object2D):
    TYPE, LABEL, ICON, CATEGORY = "legend", "Legend", "legend", "Text"
    DESCRIPTION = "Colour key. One entry per line: colour | label."
    TEXTUAL = True
    PROPS = [
        Prop("entries", "longtext", "teal | Plastic (polyethylene)\ngray | Aluminium\nred | Lead\nviolet | Hydride (ZrH_2)",
             group=G_TEXT, help="One per line: colour | label"),
        Prop("position", "vec2", [1500, 300], group=G_POS),
        Prop("size", "number", 18, min=6, max=80, step=1, group=G_LOOK),
        Prop("text_color", "color", "cream", group=G_LOOK),
        Prop("swatch", "enum", "square", options=("square", "circle", "line"), group=G_LOOK),
        Prop("spacing", "number", 1.6, min=1, max=4, step=0.05, group=G_LOOK),
        Prop("glow", "number", 0.3, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        rows = [r for r in v.entries.splitlines() if r.strip()]
        if st.progress < 1:
            rows = rows[: int(math.ceil(len(rows) * st.progress))]
        x0, y0 = v.position[0] + st.dx, v.position[1] + st.dy
        s = ctx.s
        sz = v.size * st.scale
        boxes = []
        for i, row in enumerate(rows):
            col, _, label = row.partition("|")
            if not _:
                col, label = "cream", row
            c = ctx.color(col.strip())
            y = y0 + i * sz * v.spacing
            cy = (y + sz * 0.62) * s
            if v.swatch == "circle":
                cv.circle((x0 + sz * 0.35) * s, cy, sz * 0.32 * s, fill=c, fill_alpha=a, fill_glow=v.glow)
            elif v.swatch == "line":
                cv.polyline(np.array([[x0 * s, cy], [(x0 + sz * 0.9) * s, cy]]), c, a, 3 * s, v.glow)
            else:
                q = sz * 0.6 * s
                cv.polygon(rounded_rect(x0 * s, cy - q / 2, q, q, 2 * s), fill=c, fill_alpha=a, fill_glow=v.glow)
            b = ctx.draw_text(cv, label.strip(), x0 + sz * 1.25, y, sz, v.text_color, opacity=a)
            if b:
                boxes.append(b)
        if not boxes:
            return None
        return (x0 * s, y0 * s, max(b[2] for b in boxes), max(b[3] for b in boxes))


# --------------------------------------------------------------------------- shapes
@register
class Panel(Object2D):
    TYPE, LABEL, ICON = "panel", "Panel / card", "panel"
    DESCRIPTION = "Rounded card with a header and a numbered badge, for step-by-step explanations."
    PROPS = [
        Prop("position", "vec2", [100, 160], group=G_POS, help="Top-left corner"),
        Prop("size", "vec2", [520, 640], group=G_POS),
        Prop("radius", "number", 16, min=0, max=200, step=1, group=G_LOOK),
        Prop("fill_color", "color", "navy", group=G_LOOK),
        Prop("fill_opacity", "number", 0.55, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("border_color", "color", "gray", group=G_LOOK),
        Prop("border_opacity", "number", 0.35, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("border_width", "number", 1.5, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("title", "text", "", group=G_TEXT),
        Prop("title_size", "number", 22, min=6, max=100, step=1, group=G_TEXT),
        Prop("title_color", "color", "cream", group=G_TEXT),
        Prop("badge", "int", 0, min=0, max=99, group=G_TEXT, help="Number in a circle before the title (0 = none)"),
        Prop("accent", "color", "cream", group=G_TEXT, help="Badge colour"),
        Prop("glow", "number", 0.0, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        x, y, w, h = _scaled_rect(v.position[0], v.position[1], v.size[0], v.size[1], st, s)
        rr = rounded_rect(x, y, w, h, v.radius * s * st.scale)
        cv.polygon(rr, fill=v.fill_color, fill_alpha=v.fill_opacity * a)
        if v.border_width > 0:
            cv.polygon(rr, stroke=v.border_color, stroke_alpha=v.border_opacity * a,
                       width=v.border_width * s, glow=v.glow)
        tx = x / s + 22 * st.scale
        ty = y / s + 20 * st.scale
        if v.badge > 0:
            r = v.title_size * 0.55 * st.scale
            cx, cy = tx + r, ty + v.title_size * 0.62 * st.scale
            cv.circle(cx * s, cy * s, r * s, stroke=v.accent, stroke_alpha=a, width=1.6 * s, glow=v.glow)
            ctx.draw_text(cv, str(v.badge), cx, cy, v.title_size * 0.7 * st.scale, v.accent,
                          align="center", valign="middle", opacity=a, weight="medium")
            tx += 2 * r + 10 * st.scale
        if v.title:
            ctx.draw_text(cv, v.title, tx, ty, v.title_size * st.scale, v.title_color, opacity=a, weight="medium")
        return (x, y, x + w, y + h)


SHAPE_COMMON = [
    Prop("fill_color", "color", "teal", group=G_LOOK),
    Prop("fill_opacity", "number", 0.0, min=0, max=1, step=0.01, group=G_LOOK),
    Prop("stroke_color", "color", "cream", group=G_LOOK),
    Prop("stroke_width", "number", 2.0, min=0, max=40, step=0.5, group=G_LOOK),
    Prop("dashed", "bool", False, group=G_LOOK),
    Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    Prop("axes", "ref", "", ref="axes", group=G_POS, help="Pick a chart to place the shape in data coordinates"),
]


def _stroke(cv, ctx, pts, v, a, progress):
    if v.stroke_width > 0:
        cv.polyline(pts, v.stroke_color, a, v.stroke_width * ctx.s, v.glow,
                    dash=10 * ctx.s if v.dashed else 0, progress=progress)


@register
class Rect(Object2D):
    TYPE, LABEL, ICON = "rect", "Rectangle", "rect"
    DESCRIPTION = "Rectangle or rounded box: highlights, regions, frames."
    HAS_PROGRESS = True
    PROPS = [
        Prop("position", "vec2", [760, 400], group=G_POS, help="Top-left corner"),
        Prop("size", "vec2", [400, 280], group=G_POS),
        Prop("radius", "number", 0, min=0, max=500, step=1, group=G_LOOK),
        *SHAPE_COMMON,
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        x, y = v.position
        w, h = v.size
        if v.axes:
            corners = self.to_px_points(ctx, [[x, y], [x + w, y + h]], st, v.axes)
            x0, y0 = corners.min(0)
            x1, y1 = corners.max(0)
            rx, ry, rw, rh = x0, y0, x1 - x0, y1 - y0
        else:
            rx, ry, rw, rh = _scaled_rect(x, y, w, h, st, ctx.s)
        rr = rounded_rect(rx, ry, rw, rh, v.radius * ctx.s)
        if v.fill_opacity > 0:
            cv.polygon(rr, fill=v.fill_color, fill_alpha=v.fill_opacity * a * (st.progress if st.progress < 1 else 1))
        _stroke(cv, ctx, np.vstack([rr, rr[:1]]), v, a, st.progress)
        return (rx, ry, rx + rw, ry + rh)


@register
class Ellipse(Object2D):
    TYPE, LABEL, ICON = "ellipse", "Circle / ellipse", "ellipse"
    DESCRIPTION = "Circle or ellipse: highlight a cluster, a region of interest, a spot."
    HAS_PROGRESS = True
    PROPS = [
        Prop("center", "vec2", [960, 540], group=G_POS),
        Prop("radii", "vec2", [120, 80], group=G_POS),
        Prop("rotation", "number", 0.0, min=-360, max=360, step=1, group=G_POS, help="Degrees"),
        *SHAPE_COMMON,
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        pts = ellipse_points(0, 0, v.radii[0], v.radii[1], 128)
        if v.rotation:
            r = math.radians(v.rotation)
            pts = pts @ np.array([[math.cos(r), math.sin(r)], [-math.sin(r), math.cos(r)]])
        if v.axes:
            tr = ctx.axes(v.axes)
            if tr is not None:
                cx, cy = tr.map(v.center[0], v.center[1])
                pts = np.stack([cx + tr.scale_x(1) * pts[:, 0], cy + tr.scale_y(1) * pts[:, 1]], 1)
                pxy = (pts + (st.dx, st.dy)) * ctx.s
            else:
                pxy = self.to_px_points(ctx, pts + v.center, st, about=v.center)
        else:
            pxy = self.to_px_points(ctx, pts + v.center, st, about=v.center)
        if v.fill_opacity > 0:
            cv.polygon(pxy, fill=v.fill_color, fill_alpha=v.fill_opacity * a)
        _stroke(cv, ctx, pxy, v, a, st.progress)
        return (pxy[:, 0].min(), pxy[:, 1].min(), pxy[:, 0].max(), pxy[:, 1].max())


@register
class Arrow(Object2D):
    TYPE, LABEL, ICON = "arrow", "Arrow", "arrow"
    DESCRIPTION = "Straight or curved arrow pointing at something."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        Prop("tail", "vec2", [760, 540], group=G_POS),
        Prop("tip", "vec2", [1160, 540], group=G_POS),
        Prop("bend", "number", 0.0, min=-800, max=800, step=1, group=G_POS, help="Curvature in pixels"),
        Prop("color", "color", "cream", group=G_LOOK),
        Prop("width", "number", 3.0, min=0, max=40, step=0.5, group=G_LOOK),
        Prop("heads", "enum", "end", options=("end", "start", "both", "none"), group=G_LOOK),
        Prop("head_size", "number", 18, min=0, max=120, step=1, group=G_LOOK),
        Prop("dashed", "bool", False, group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("axes", "ref", "", ref="axes", group=G_POS, help="Pick a chart to place the arrow in data coordinates"),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        p0p1 = self.to_px_points(ctx, [v.tail, v.tip], st, v.axes)
        p0, p1 = p0p1[0], p0p1[1]
        n = 64
        u = np.linspace(0, 1, n)[:, None]
        d = p1 - p0
        perp = np.array([-d[1], d[0]]) / (np.linalg.norm(d) or 1)
        ctrl = (p0 + p1) / 2 + perp * v.bend * ctx.s
        pts = (1 - u) ** 2 * p0 + 2 * (1 - u) * u * ctrl + u ** 2 * p1
        pts = truncate_path(pts, st.progress)
        if len(pts) < 2:
            return None
        hs = v.head_size * ctx.s
        cv.polyline(pts, v.color, a, v.width * ctx.s, v.glow, dash=12 * ctx.s if v.dashed else 0)
        if hs > 0 and v.heads in ("end", "both"):
            k = max(0, len(pts) - 4)
            cv.polygon(arrow_head(pts[-1], pts[-1] - pts[k], hs), fill=v.color, fill_alpha=a, fill_glow=v.glow)
        if hs > 0 and v.heads in ("start", "both") and st.progress > 0.05:
            cv.polygon(arrow_head(pts[0], pts[0] - pts[min(3, len(pts) - 1)], hs), fill=v.color, fill_alpha=a, fill_glow=v.glow)
        return (pts[:, 0].min() - hs, pts[:, 1].min() - hs, pts[:, 0].max() + hs, pts[:, 1].max() + hs)


@register
class Image2D(Object2D):
    TYPE, LABEL, ICON = "image", "Image", "image"
    DESCRIPTION = "A picture or data array (radiograph, slice, micrograph, logo) placed in the frame."
    PROPS = [
        *IMAGE_PROPS,
        Prop("position", "vec2", [960, 540], group=G_POS, help="Centre of the image"),
        Prop("width", "number", 420, min=1, step=1, group=G_POS, help="Pixels; height follows the aspect ratio"),
        Prop("rotation", "number", 0.0, step=1, group=G_POS, help="Degrees, clockwise (a sample turning on its stage)"),
        Prop("mask", "enum", "none", options=("none", "circle", "rounded"), group=G_LOOK),
        Prop("border_color", "color", "cream", group=G_LOOK),
        Prop("border_width", "number", 0.0, min=0, max=30, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.3, min=0, max=3, step=0.05, group=G_LOOK, help="Glow of the image itself"),
    ]

    def depends_on_time(self) -> bool:
        return super().depends_on_time() or seqdata.plays_by_itself(self, "image")

    def draw(self, cv, ctx, v, st):
        if not v.image:
            return None
        a = v.opacity * st.opacity
        col, alpha = prepare_image(ctx, v, max_side=1600)
        h, w = col.shape[:2]
        W = v.width * ctx.s * st.scale
        H = W * h / max(w, 1)
        cx, cy = (v.position[0] + st.dx) * ctx.s, (v.position[1] + st.dy) * ctx.s
        x0, y0 = cx - W / 2, cy - H / 2
        quad = np.array([[x0, y0], [x0 + W, y0], [x0 + W, y0 + H], [x0, y0 + H]])
        rot = float(v.get("rotation", 0.0))
        if rot:
            c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            d = quad - (cx, cy)
            quad = np.stack([d[:, 0] * c - d[:, 1] * sn, d[:, 0] * sn + d[:, 1] * c], 1) + (cx, cy)
        mask = alpha
        if v.mask == "circle":
            yy, xx = np.mgrid[0:h, 0:w]
            r = min(h, w) / 2
            circ = np.clip(r - np.hypot(xx + 0.5 - w / 2, yy + 0.5 - h / 2), 0, 1).astype(np.float32)
            mask = circ if mask is None else mask * circ
        elif v.mask == "rounded":
            m = np.zeros((h, w), np.uint8)
            cv2.fillPoly(m, [np.round(rounded_rect(0, 0, w, h, min(w, h) * 0.08) * 16).astype(np.int32)], 255, cv2.LINE_AA, 4)
            mm = m.astype(np.float32) / 255
            mask = mm if mask is None else mask * mm
        cv.warp(col, quad, a, v.glow, mask, nearest=bool(v.pixelated))
        if v.border_width > 0:
            if v.mask == "circle":
                cv.circle(cx, cy, min(W, H) / 2, stroke=v.border_color, stroke_alpha=a, width=v.border_width * ctx.s, glow=0.5)
            elif rot:
                cv.polygon(quad, stroke=v.border_color, stroke_alpha=a, width=v.border_width * ctx.s, glow=0.5)
            else:
                rad = min(W, H) * 0.08 if v.mask == "rounded" else 0
                cv.polygon(rounded_rect(x0, y0, W, H, rad), stroke=v.border_color, stroke_alpha=a,
                           width=v.border_width * ctx.s, glow=0.5)
        return (float(quad[:, 0].min()), float(quad[:, 1].min()), float(quad[:, 0].max()), float(quad[:, 1].max()))
