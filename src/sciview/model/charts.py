"""Charts: an Axes object plus series (curve, scatter, bars, histogram, marker, guide) that refer to it."""
from __future__ import annotations

import math

import numpy as np

from ..engine.color import COLORMAPS, apply_colormap
from ..engine.mathexpr import ExpressionError, evaluate
from .base import Prop, SceneObject, parse_array, register
from .objects2d import draw_rotated_text, format_values

G_AX, G_DATA, G_LOOK, G_TXT = "Axes", "Data", "Appearance", "Labels"


def nice_ticks(lo: float, hi: float, n: int) -> tuple[np.ndarray, float]:
    if n <= 0 or not np.isfinite(lo) or not np.isfinite(hi) or hi == lo:
        return np.zeros(0), 1.0
    if hi < lo:
        lo, hi = hi, lo
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    first = math.ceil(lo / step - 1e-9) * step
    ticks = np.arange(first, hi + step * 1e-6, step)
    return ticks, step


def fmt_tick(v: float, step: float) -> str:
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1e5 or a < 1e-3:
        return f"{v:.0e}".replace("e+0", "e").replace("e-0", "e-")
    dec = max(0, -int(math.floor(math.log10(step) + 1e-9)))
    if abs(step * 10 ** dec - round(step * 10 ** dec)) > 1e-6:
        dec += 1
    return f"{v:.{dec}f}"


@register
class Axes(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "axes", "Chart axes", "axes", "Charts"
    DESCRIPTION = "A coordinate frame. Add curves, scatter, bars and markers that point to it."
    HAS_PROGRESS = True
    PROPS = [
        Prop("position", "vec2", [1020, 220], group=G_AX, help="Top-left corner of the plot area"),
        Prop("size", "vec2", [720, 460], group=G_AX),
        Prop("x_range", "vec2", [0, 10], group=G_AX, help="Animate to zoom or pan"),
        Prop("y_range", "vec2", [0, 1], group=G_AX),
        Prop("log_x", "bool", False, group=G_AX),
        Prop("log_y", "bool", False, group=G_AX),
        Prop("x_label", "text", "x", group=G_TXT),
        Prop("y_label", "text", "y", group=G_TXT),
        Prop("title", "text", "", group=G_TXT),
        Prop("x_ticks", "int", 5, min=0, max=30, group=G_TXT, help="About how many ticks (0 = none)"),
        Prop("y_ticks", "int", 4, min=0, max=30, group=G_TXT),
        Prop("tick_labels", "bool", True, group=G_TXT),
        Prop("font_size", "number", 18, min=6, max=60, step=1, group=G_TXT),
        Prop("label_color", "color", "cream", group=G_TXT),
        Prop("frame", "enum", "L", options=("L", "box", "none"), group=G_LOOK),
        Prop("grid", "bool", True, group=G_LOOK),
        Prop("color", "color", "gray", group=G_LOOK),
        Prop("line_width", "number", 1.5, min=0, max=10, step=0.5, group=G_LOOK),
        Prop("grid_opacity", "number", 0.12, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("background_opacity", "number", 0.0, min=0, max=1, step=0.01, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        a = v.opacity * st.opacity
        s = ctx.s
        tr = ctx.axes(self.id)
        if tr is None:
            return None
        ox, oy = st.dx, st.dy
        x0, y0, x1, y1 = tr.x0 + ox, tr.y0 + oy, tr.x0 + tr.w + ox, tr.y0 + tr.h + oy
        p = st.progress
        if v.background_opacity > 0:
            cv.polygon(np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) * s, fill=ctx.color("navy"),
                       fill_alpha=v.background_opacity * a)
        fs = v.font_size
        lc = v.label_color

        def ticks(lo, hi, n, log):
            if log:
                if lo <= 0 or hi <= 0:
                    return np.zeros(0), 1.0
                e0, e1 = math.ceil(math.log10(min(lo, hi)) - 1e-9), math.floor(math.log10(max(lo, hi)) + 1e-9)
                return 10.0 ** np.arange(e0, e1 + 1), 1.0
            return nice_ticks(lo, hi, n)

        xt, xs = ticks(tr.xmin, tr.xmax, int(v.x_ticks), tr.logx)
        yt, ys = ticks(tr.ymin, tr.ymax, int(v.y_ticks), tr.logy)
        X = tr.map_x(xt) + ox
        Y = tr.map_y(yt) + oy
        if v.grid and v.grid_opacity > 0:
            segs = [np.array([[xx, y0], [xx, y0 + (y1 - y0) * p]]) * s for xx in X if x0 + 0.5 < xx < x1 - 0.5]
            segs += [np.array([[x0, yy], [x0 + (x1 - x0) * p, yy]]) * s for yy in Y if y0 + 0.5 < yy < y1 - 0.5]
            cv.lines(segs, v.color, a * v.grid_opacity, 1.0 * s)
        lw = v.line_width * s
        if v.frame != "none":
            cv.polyline(np.array([[x0, y1], [x0 + (x1 - x0) * p, y1]]) * s, v.color, a, lw, 0.3)
            cv.polyline(np.array([[x0, y1], [x0, y1 - (y1 - y0) * p]]) * s, v.color, a, lw, 0.3)
            if v.frame == "box":
                cv.polyline(np.array([[x1, y1], [x1, y1 - (y1 - y0) * p]]) * s, v.color, a, lw, 0.3)
                cv.polyline(np.array([[x0, y0], [x0 + (x1 - x0) * p, y0]]) * s, v.color, a, lw, 0.3)
        ta = a * min(1.0, max(0.0, (p - 0.5) * 2))
        if v.tick_labels and ta > 0:
            for xx, val in zip(X, xt):
                if x0 - 1 <= xx <= x1 + 1:
                    cv.polyline(np.array([[xx, y1], [xx, y1 + 6]]) * s, v.color, ta, lw)
                    txt = fmt_tick(val, xs) if not tr.logx else f"10^{{{int(round(math.log10(val)))}}}"
                    ctx.draw_text(cv, txt, xx, y1 + 10, fs * 0.8, lc, align="center", opacity=ta * 0.75)
            for yy, val in zip(Y, yt):
                if y0 - 1 <= yy <= y1 + 1:
                    cv.polyline(np.array([[x0 - 6, yy], [x0, yy]]) * s, v.color, ta, lw)
                    txt = fmt_tick(val, ys) if not tr.logy else f"10^{{{int(round(math.log10(val)))}}}"
                    ctx.draw_text(cv, txt, x0 - 12, yy, fs * 0.8, lc, align="right", valign="middle", opacity=ta * 0.75)
        if ta > 0:
            if v.x_label:
                ctx.draw_text(cv, v.x_label, (x0 + x1) / 2, y1 + fs * 2.1, fs, lc, align="center", opacity=ta)
            if v.y_label:
                draw_rotated_text(cv, ctx, v.y_label, x0 - fs * 3.4, (y0 + y1) / 2, fs, lc, 90, ta)
            if v.title:
                ctx.draw_text(cv, v.title, x0, y0 - fs * 2.2, fs * 1.15, lc, opacity=ta, weight="medium")
        return (x0 * s - 60 * s, y0 * s - 10 * s, x1 * s + 10 * s, y1 * s + 60 * s)


AXES_REF = Prop("axes", "ref", "", ref="axes", group=G_AX, help="The chart this series is drawn in")
DATA_PROPS = [
    Prop("data", "asset", "", accept="table", group=G_DATA, help="CSV/TSV/NPY/NPZ table"),
    Prop("x_column", "text", "x", group=G_DATA, help="Column name or number"),
    Prop("y_column", "text", "y", group=G_DATA),
    Prop("x_values", "array", "", group=G_DATA, help="Or type numbers: 0, 1, 2, 3"),
    Prop("y_values", "array", "", group=G_DATA),
]


class Series(SceneObject):
    CATEGORY = "Charts"

    def xy_data(self, ctx, v):
        if v.get("data"):
            return ctx.assets.column(v.data, v.x_column), ctx.assets.column(v.data, v.y_column)
        xs, ys = parse_array(v.x_values), parse_array(v.y_values)
        if len(xs) == 0 and len(ys):
            xs = np.arange(len(ys), dtype=np.float64)
        n = min(len(xs), len(ys))
        return xs[:n], ys[:n]

    def axes_or_warn(self, ctx, v):
        tr = ctx.axes(v.axes)
        if tr is None:
            ctx.warn(f"{self.name}: choose a chart in 'Axes' (add a Chart axes object first)")
        return tr

    @staticmethod
    def clip_to(cv, ctx, tr, st, on=True):
        if on:
            s = ctx.s
            cv.push_clip((tr.x0 + st.dx) * s - 2, (tr.y0 + st.dy) * s - 2,
                         (tr.x0 + tr.w + st.dx) * s + 2, (tr.y0 + tr.h + st.dy) * s + 2)
        return on


@register
class Curve(Series):
    TYPE, LABEL, ICON = "curve", "Curve", "curve"
    DESCRIPTION = "A line from an expression like exp(-x/2) (t is time, for moving waves) or from data."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("source", "enum", "expression", options=("expression", "data"), group=G_DATA),
        Prop("expression", "text", "exp(-x/3)", group=G_DATA,
             help="y as a function of x (and time t): sin(x - 2*t), gauss(x, 5, 1), x^2 ..."),
        Prop("domain", "vec2", [0, 0], group=G_DATA, help="x range of the expression (equal values = whole axis)"),
        Prop("samples", "int", 400, min=2, max=20000, group=G_DATA),
        *DATA_PROPS,
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("width", "number", 3.0, min=0, max=30, step=0.5, group=G_LOOK),
        Prop("style", "enum", "solid", options=("solid", "dashed", "dotted"), group=G_LOOK),
        Prop("fill_opacity", "number", 0.0, min=0, max=1, step=0.01, group=G_LOOK, help="Shade under the curve"),
        Prop("glow", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("clip", "bool", True, group=G_LOOK, help="Hide what falls outside the axes"),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        if v.source == "expression":
            lo, hi = float(v.domain[0]), float(v.domain[1])
            if lo == hi:
                lo, hi = tr.xmin, tr.xmax
            if tr.logx and lo > 0 and hi > 0:
                xs = np.logspace(math.log10(lo), math.log10(hi), int(v.samples))
            else:
                xs = np.linspace(lo, hi, int(v.samples))
            try:
                ys = np.broadcast_to(evaluate(v.expression, x=xs, t=ctx.t), xs.shape).astype(np.float64)
            except ExpressionError as exc:
                ctx.warn(f"{self.name}: {exc}")
                return None
        else:
            xs, ys = self.xy_data(ctx, v)
        if len(xs) < 2:
            return None
        X, Y = tr.map(xs, ys)
        pts = np.stack([X + st.dx, Y + st.dy], 1) * ctx.s
        pts = pts[np.isfinite(pts).all(axis=1)]
        if len(pts) < 2:
            return None
        clipped = self.clip_to(cv, ctx, tr, st, bool(v.clip))
        try:
            n = max(2, int(math.ceil(len(pts) * st.progress))) if st.progress < 1 else len(pts)
            shown = pts[:n]
            if v.fill_opacity > 0:
                base = tr.map_y(max(tr.ymin, 0.0) if not tr.logy else tr.ymin) + st.dy
                poly = np.vstack([shown, [[shown[-1, 0], base * ctx.s], [shown[0, 0], base * ctx.s]]])
                cv.polygon(poly, fill=v.color, fill_alpha=v.fill_opacity * a, fill_glow=v.glow * 0.2)
            dash = {"dashed": 14, "dotted": 3}.get(v.style, 0) * ctx.s
            gap = {"dashed": 10, "dotted": 7}.get(v.style, 0) * ctx.s
            cv.polyline(shown, v.color, a, v.width * ctx.s, v.glow, dash=dash, gap=gap)
        finally:
            if clipped:
                cv.pop_clip()
        return (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())


@register
class Scatter(Series):
    TYPE, LABEL, ICON = "scatter", "Scatter", "scatter"
    DESCRIPTION = "Points from a table or typed values. The draw effect makes them appear one by one."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        *DATA_PROPS,
        Prop("color", "color", "ice", group=G_LOOK),
        Prop("color_by", "text", "", group=G_LOOK, help="Column (from the data file) used for colour"),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_LOOK),
        Prop("size", "number", 3.0, min=0.3, max=40, step=0.1, group=G_LOOK, help="Radius in pixels"),
        Prop("style", "enum", "glow", options=("glow", "solid"), group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("clip", "bool", True, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        xs, ys = self.xy_data(ctx, v)
        if len(xs) == 0:
            return None
        cvals = ctx.assets.column(v.data, v.color_by)[: len(xs)] if (v.data and v.color_by) else None
        if st.progress < 1:
            order = np.random.default_rng(11).permutation(len(xs))[: int(round(len(xs) * st.progress))]
            xs, ys = xs[order], ys[order]
            cvals = None if cvals is None else cvals[order]
        X, Y = tr.map(xs, ys)
        pts = np.stack([X + st.dx, Y + st.dy], 1) * ctx.s
        colors = None if cvals is None else apply_colormap(cvals, v.colormap)
        clipped = self.clip_to(cv, ctx, tr, st, bool(v.clip))
        try:
            if v.style == "solid":
                cv.dots(pts, v.size * ctx.s, v.color, a, v.glow, colors)
            else:
                cv.splat(pts, 1.0, v.color, a, max(0.5, v.size * ctx.s * 0.6), gain=1.6, glow=v.glow, colors=colors)
        finally:
            if clipped:
                cv.pop_clip()
        x0, y0, x1, y1 = tr.rect
        return (x0 * ctx.s, y0 * ctx.s, x1 * ctx.s, y1 * ctx.s)


@register
class Bars(Series):
    TYPE, LABEL, ICON = "bars", "Bar chart", "bars"
    DESCRIPTION = "Bars from typed values; the draw effect grows them from the baseline."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("values", "array", "3, 5, 2, 4", group=G_DATA),
        Prop("positions", "array", "", group=G_DATA, help="x of each bar (default 1, 2, 3 ...)"),
        Prop("labels", "text", "", group=G_DATA, help="Comma-separated names under the bars"),
        Prop("baseline", "number", 0.0, group=G_DATA),
        Prop("height_scale", "number", 1.0, min=0, step=0.01, group=G_DATA, help="Animate to change all heights"),
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("colors", "text", "", group=G_LOOK, help="Optional comma-separated colours, one per bar"),
        Prop("bar_width", "number", 0.7, min=0.05, max=1, step=0.05, group=G_LOOK, help="Fraction of the spacing"),
        Prop("fill_opacity", "number", 0.85, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("value_labels", "bool", False, group=G_LOOK),
        Prop("value_format", "text", "{value:.0f}", group=G_LOOK),
        Prop("label_size", "number", 16, min=6, max=60, step=1, group=G_LOOK),
        Prop("glow", "number", 0.4, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        vals = parse_array(v.values)
        if len(vals) == 0:
            return None
        pos = parse_array(v.positions)
        if len(pos) < len(vals):
            pos = np.arange(1, len(vals) + 1, dtype=np.float64)
        spacing = float(np.min(np.diff(np.sort(pos)))) if len(pos) > 1 else 1.0
        bw = spacing * float(v.bar_width)
        names = [x.strip() for x in v.labels.split(",")] if v.labels else []
        cols = [x.strip() for x in v.colors.split(",") if x.strip()] if v.colors else []
        s = ctx.s
        b = float(v.baseline)
        bbox = None
        for i, (x, val) in enumerate(zip(pos, vals)):
            top = b + (val - b) * float(v.height_scale) * st.progress
            X0, Yb = tr.map(x - bw / 2, b)
            X1, Yt = tr.map(x + bw / 2, top)
            c = ctx.color(cols[i % len(cols)]) if cols else v.color
            rect = np.array([[X0, Yt], [X1, Yt], [X1, Yb], [X0, Yb]]) + (st.dx, st.dy)
            cv.polygon(rect * s, fill=c, fill_alpha=v.fill_opacity * a, fill_glow=v.glow * 0.3)
            cv.polyline(np.array([[X0, Yt], [X1, Yt]]) * s + np.array([st.dx, st.dy]) * s, c, a, 2 * s, v.glow)
            cxp = (float(X0) + float(X1)) / 2 + st.dx
            if v.value_labels and st.progress > 0.2:
                ctx.draw_text(cv, format_values(v.value_format, value=float(val) * float(v.height_scale)),
                              cxp, float(min(Yt, Yb)) + st.dy - 8, v.label_size, c, align="center", valign="bottom",
                              opacity=a)
            if i < len(names) and names[i]:
                ctx.draw_text(cv, names[i], cxp, tr.y0 + tr.h + st.dy + 10, v.label_size, ctx.color("cream"),
                              align="center", opacity=a)
            bb = (min(X0, X1) * s, min(Yt, Yb) * s, max(X0, X1) * s, max(Yt, Yb) * s)
            bbox = bb if bbox is None else (min(bbox[0], bb[0]), min(bbox[1], bb[1]), max(bbox[2], bb[2]), max(bbox[3], bb[3]))
        return bbox


@register
class Histogram(Series):
    TYPE, LABEL, ICON = "histogram", "Histogram", "histogram"
    DESCRIPTION = "Histogram of a data column, vertical or along the y axis (for marginal histograms)."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("data", "asset", "", accept="table", group=G_DATA),
        Prop("column", "text", "0", group=G_DATA),
        Prop("values", "array", "", group=G_DATA, help="Or type numbers"),
        Prop("bins", "int", 40, min=1, max=2000, group=G_DATA),
        Prop("range", "vec2", [0, 0], group=G_DATA, help="Bin range (equal values = axis range)"),
        Prop("orientation", "enum", "vertical", options=("vertical", "horizontal"), group=G_DATA,
             help="Horizontal bars grow from the y axis"),
        Prop("normalize", "enum", "max", options=("max", "count", "density"), group=G_DATA,
             help="'max' scales the tallest bar to Height (a fraction of the axis)"),
        Prop("height", "number", 0.9, min=0, max=1, step=0.01, group=G_DATA),
        Prop("color", "color", "blue", group=G_LOOK),
        Prop("fill_opacity", "number", 0.8, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 0.5, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        data = ctx.assets.column(v.data, v.column) if v.data else parse_array(v.values)
        data = data[np.isfinite(data)]
        if len(data) == 0:
            return None
        horiz = v.orientation == "horizontal"
        lo, hi = float(v.range[0]), float(v.range[1])
        if lo == hi:
            lo, hi = (tr.ymin, tr.ymax) if horiz else (tr.xmin, tr.xmax)
        counts, edges = np.histogram(data, bins=int(v.bins), range=(min(lo, hi), max(lo, hi)))
        counts = counts.astype(np.float64)
        span = (tr.xmax - tr.xmin) if horiz else (tr.ymax - tr.ymin)
        base = tr.xmin if horiz else tr.ymin
        if v.normalize == "max":
            h = counts / max(counts.max(), 1) * span * float(v.height)
        elif v.normalize == "density":
            h = counts / max(counts.sum() * (edges[1] - edges[0]), 1e-12)
        else:
            h = counts
        h = h * st.progress
        s = ctx.s
        polys = []
        for e0, e1, hh in zip(edges[:-1], edges[1:], h):
            if hh <= 0:
                continue
            if horiz:
                X0, Y0 = tr.map(base, e0)
                X1, Y1 = tr.map(base + hh, e1)
            else:
                X0, Y0 = tr.map(e0, base)
                X1, Y1 = tr.map(e1, base + hh)
            polys.append(np.array([[X0, Y0], [X1, Y0], [X1, Y1], [X0, Y1]], np.float64) + (st.dx, st.dy))
        for p in polys:
            cv.polygon(p * s, fill=v.color, fill_alpha=v.fill_opacity * a, fill_glow=v.glow)
        x0, y0, x1, y1 = tr.rect
        return (x0 * s, y0 * s, x1 * s, y1 * s)


@register
class Marker(Series):
    TYPE, LABEL, ICON = "marker", "Marker", "marker"
    DESCRIPTION = "A dot at (x, y) in a chart, with guide lines and a live label. Animate x to move it along a curve."
    TEXTUAL = False
    DEFAULT_ENTER = "pop"
    PROPS = [
        AXES_REF,
        Prop("x", "number", 5.0, group=G_DATA),
        Prop("y", "number", 0.5, group=G_DATA),
        Prop("follow", "text", "", group=G_DATA, help="Optional expression: y follows f(x), e.g. exp(-x/3)"),
        Prop("size", "number", 7, min=1, max=60, step=0.5, group=G_LOOK),
        Prop("color", "color", "white", group=G_LOOK),
        Prop("guides", "enum", "both", options=("none", "x", "y", "both"), group=G_LOOK,
             help="Dashed lines down to the x axis and/or across to the y axis"),
        Prop("guide_color", "color", "cream", group=G_LOOK),
        Prop("label", "text", "", group=G_TXT, help="Can show live values: x = {x:.2f}, y = {y:.3f}"),
        Prop("label_size", "number", 18, min=6, max=80, step=1, group=G_TXT),
        Prop("label_offset", "vec2", [14, -14], group=G_TXT),
        Prop("glow", "number", 1.0, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        x = float(v.x)
        y = float(v.y)
        if v.follow.strip():
            try:
                y = float(np.asarray(evaluate(v.follow, x=x, t=ctx.t)).ravel()[0])
            except ExpressionError as exc:
                ctx.warn(f"{self.name}: {exc}")
        X, Y = tr.map(x, y)
        X, Y = float(X) + st.dx, float(Y) + st.dy
        s = ctx.s
        if v.guides in ("x", "both"):
            cv.polyline(np.array([[X, Y], [X, tr.y0 + tr.h + st.dy]]) * s, v.guide_color, a * 0.8, 1.5 * s, 0.3, dash=7 * s)
        if v.guides in ("y", "both"):
            cv.polyline(np.array([[X, Y], [tr.x0 + st.dx, Y]]) * s, v.guide_color, a * 0.8, 1.5 * s, 0.3, dash=7 * s)
        r = v.size * st.scale
        cv.circle(X * s, Y * s, r * s, fill=v.color, fill_alpha=a, fill_glow=v.glow)
        if v.label:
            ctx.draw_text(cv, format_values(v.label, x=x, y=y), X + v.label_offset[0], Y + v.label_offset[1],
                          v.label_size, v.color, valign="bottom" if v.label_offset[1] < 0 else "top",
                          align="left" if v.label_offset[0] >= 0 else "right", opacity=a)
        return ((X - r) * s, (Y - r) * s, (X + r) * s, (Y + r) * s)


@register
class Guide(Series):
    TYPE, LABEL, ICON = "guide", "Threshold line", "guide"
    DESCRIPTION = "A vertical or horizontal line across a chart at a data value (thresholds, references)."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("orientation", "enum", "vertical", options=("vertical", "horizontal"), group=G_DATA),
        Prop("value", "number", 5.0, group=G_DATA, help="Animate it to sweep the threshold"),
        Prop("color", "color", "white", group=G_LOOK),
        Prop("width", "number", 2.5, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("dashed", "bool", False, group=G_LOOK),
        Prop("label", "text", "", group=G_TXT),
        Prop("label_size", "number", 16, min=6, max=60, step=1, group=G_TXT),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        a = v.opacity * st.opacity
        s = ctx.s
        if v.orientation == "vertical":
            X = float(tr.map_x(float(v.value))) + st.dx
            pts = np.array([[X, tr.y0 + tr.h], [X, tr.y0]]) + (0, st.dy)
            lab = (X, tr.y0 + st.dy - 8, "center", "bottom")
        else:
            Y = float(tr.map_y(float(v.value))) + st.dy
            pts = np.array([[tr.x0, Y], [tr.x0 + tr.w, Y]]) + (st.dx, 0)
            lab = (tr.x0 + tr.w + st.dx + 10, Y, "left", "middle")
        cv.polyline(pts * s, v.color, a, v.width * s, v.glow, dash=10 * s if v.dashed else 0, progress=st.progress)
        if v.label:
            ctx.draw_text(cv, v.label, lab[0], lab[1], v.label_size, v.color, align=lab[2], valign=lab[3],
                          opacity=a * min(1.0, st.progress * 2))
        return (pts[:, 0].min() * s - 4, pts[:, 1].min() * s - 4, pts[:, 0].max() * s + 4, pts[:, 1].max() * s + 4)
