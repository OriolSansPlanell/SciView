"""More chart series: heatmaps and colour bars, error bars, uncertainty bands, fitted curves, spectra
with labelled peaks, 2D histograms, vector fields and streamlines."""
from __future__ import annotations

import math

import numpy as np

from ..engine.color import COLORMAPS, apply_colormap
from ..engine.mathexpr import ExpressionError, evaluate, uses_time
from ..engine.surface import arrow_head
from ..engine.units import si
from . import data as seqdata
from .base import Prop, SceneObject, parse_array, register
from .charts import AXES_REF, DATA_PROPS, G_DATA, G_LOOK, G_TXT, Series, fmt_tick, nice_ticks
from .objects2d import draw_rotated_text, format_values

G_COL = "Colour"


def _eval(expr: str, **vars):
    out = evaluate(expr, **vars)
    shape = np.broadcast(*[np.asarray(v) for v in vars.values()]).shape
    return np.broadcast_to(np.asarray(out, np.float64), shape).astype(np.float64)


def _auto_range(values: np.ndarray, vmin: float, vmax: float, log: bool = False) -> tuple[float, float]:
    if vmin != vmax:
        return float(vmin), float(vmax)
    a = np.asarray(values, np.float64)
    a = a[np.isfinite(a)]
    if log:
        a = a[a > 0]
    if a.size == 0:
        return (1.0, 10.0) if log else (0.0, 1.0)
    lo, hi = float(a.min()), float(a.max())
    return (lo, hi if hi > lo else lo + 1e-9)


def _cmap(values, name, lo, hi, log=False):
    v = np.asarray(values, np.float64)
    if log:
        lo_l, hi_l = math.log10(max(lo, 1e-300)), math.log10(max(hi, lo * 10, 1e-300))
        with np.errstate(all="ignore"):
            u = (np.log10(np.where(v > 0, v, np.nan)) - lo_l) / ((hi_l - lo_l) or 1e-12)
    else:
        u = (v - lo) / ((hi - lo) or 1e-12)
    return apply_colormap(np.nan_to_num(np.clip(u, 0, 1), nan=0.0), name, 0.0, 1.0), np.isfinite(u)


# --------------------------------------------------------------------------- heatmap
@register
class Heatmap(Series):
    TYPE, LABEL, ICON = "heatmap", "Heatmap", "heatmap"
    DESCRIPTION = "A map of values on a chart, from an expression z(x, y, t) or a 2D array, image or CSV grid."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("source", "enum", "expression", options=("expression", "data"), group=G_DATA),
        Prop("expression", "text", "exp(-((x-5)^2 + (y-0.5)^2*100)/6)", group=G_DATA, expr="x,y,t",
             help="z as a function of x, y (and time t)"),
        Prop("data", "asset", "", accept="image", group=G_DATA,
             help="2D .npy array, image or CSV grid; the top row is the highest y"),
        *seqdata.seq_props(G_DATA),
        Prop("x_extent", "vec2", [0, 0], group=G_DATA, help="x range the data covers (equal values = the chart's)"),
        Prop("y_extent", "vec2", [0, 0], group=G_DATA),
        Prop("resolution", "int", 160, min=8, max=1200, group=G_DATA, help="Samples across, for an expression"),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_COL),
        Prop("vmin", "number", 0.0, group=G_COL, help="Equal vmin and vmax use the data range"),
        Prop("vmax", "number", 0.0, group=G_COL),
        Prop("log_color", "bool", False, group=G_COL),
        Prop("clear_below", "number", 0.0, min=0, max=1, step=0.01, group=G_COL,
             help="Values below this fraction of the range are see-through"),
        Prop("smooth", "bool", True, group=G_LOOK, help="Blend between cells (off = sharp cells)"),
        Prop("glow", "number", 0.2, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def depends_on_time(self):
        if self.props.get("source") == "expression" and uses_time(self.props.get("expression", "")):
            return True
        return super().depends_on_time()

    def _extent(self, tr, v):
        xe, ye = [float(x) for x in v.x_extent], [float(y) for y in v.y_extent]
        if xe[0] == xe[1]:
            xe = [tr.xmin, tr.xmax]
        if ye[0] == ye[1]:
            ye = [tr.ymin, tr.ymax]
        return xe, ye

    def grid(self, ctx, v, tr) -> np.ndarray:
        """The values, (rows, cols) with row 0 at the top (highest y)."""
        if v.source == "data":
            if not v.data:
                raise ValueError("choose a data file")
            return grid_from_file(ctx, seqdata.current_file(ctx, v, "data"))
        xe, ye = self._extent(tr, v)
        n = int(v.resolution)
        aspect = abs(tr.h / max(tr.w, 1e-9))
        m = max(2, int(round(n * aspect)))
        xs = np.linspace(xe[0], xe[1], n)
        ys = np.linspace(ye[1], ye[0], m)
        X, Y = np.meshgrid(xs, ys)
        return _eval(v.expression, x=X, y=Y, t=ctx.t)

    def color_range(self, ctx, v):
        tr = ctx.axes(v.axes)
        if tr is None:
            return float(v.vmin), float(v.vmax)
        try:
            return _auto_range(self.grid(ctx, v, tr), float(v.vmin), float(v.vmax), bool(v.log_color))
        except Exception:
            return 0.0, 1.0

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            z = self.grid(ctx, v, tr)
        except (ExpressionError, ValueError, OSError) as exc:
            ctx.warn(f"{self.name}: {exc}", "expression" if v.source == "expression" else "data")
            return None
        lo, hi = _auto_range(z, float(v.vmin), float(v.vmax), bool(v.log_color))
        col, ok = _cmap(z, v.colormap, lo, hi, bool(v.log_color))
        mask = ok.astype(np.float32)
        cb = float(v.clear_below)
        if cb > 0:
            u = np.clip((np.nan_to_num(z, nan=lo) - lo) / ((hi - lo) or 1e-12), 0, 1)
            mask *= np.clip((u - cb) / max(0.05, 0.1 * (1 - cb)), 0, 1)
        if st.progress < 1:
            mask[:, int(round(mask.shape[1] * st.progress)):] = 0
        xe, ye = self._extent(tr, v)
        X0, Y0 = tr.map(xe[0], ye[1])
        X1, Y1 = tr.map(xe[1], ye[0])
        s = ctx.s
        quad = np.array([[X0, Y0], [X1, Y0], [X1, Y1], [X0, Y1]], np.float64) + (st.dx, st.dy)
        self.clip_to(cv, ctx, tr, st)
        try:
            cv.warp(np.ascontiguousarray(col), quad * s, v.opacity * st.opacity, v.glow, mask, nearest=not v.smooth)
        finally:
            cv.pop_clip()
        box = (quad[:, 0].min() * s, quad[:, 1].min() * s, quad[:, 0].max() * s, quad[:, 1].max() * s)
        return self.clip_box(box, ctx, tr, st)


def grid_from_file(ctx, rel: str) -> np.ndarray:
    from ..engine.assets import asset_kind
    if asset_kind(rel) == "table" and not rel.lower().endswith((".npy", ".npz")):
        tab = ctx.assets.table(rel)
        return np.stack(list(tab.values()), axis=1).astype(np.float64)
    img = ctx.assets.image(rel)
    return (img if img.ndim == 2 else img[..., :3].mean(axis=2)).astype(np.float64)


# --------------------------------------------------------------------------- colour bar
@register
class Colorbar(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "colorbar", "Colour bar", "colorbar", "Charts"
    DESCRIPTION = "The key to a colormap. Point it at a heatmap, image, volume or 2D histogram to follow its range."
    HAS_PROGRESS = True
    PROPS = [
        Prop("source", "ref", "", group=G_COL, help="Copy colormap and range from this object"),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_COL, help="Used without a source"),
        Prop("vmin", "number", 0.0, group=G_COL),
        Prop("vmax", "number", 1.0, group=G_COL),
        Prop("label", "text", "", group=G_TXT),
        Prop("unit", "text", "", group=G_TXT, help="With a unit, tick labels use SI prefixes: 2 mm, 500 µm"),
        Prop("position", "vec2", [1780, 260], group="Position", help="Top-left corner"),
        Prop("size", "vec2", [26, 420], group="Position", help="Thickness and length"),
        Prop("orientation", "enum", "vertical", options=("vertical", "horizontal"), group="Position"),
        Prop("ticks", "int", 5, min=0, max=20, group=G_TXT),
        Prop("font_size", "number", 18, min=6, max=60, step=1, group=G_TXT),
        Prop("label_color", "color", "cream", group=G_TXT),
        Prop("border_color", "color", "gray", group=G_LOOK),
        Prop("glow", "number", 0.2, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def _mapping(self, ctx, v):
        src = ctx.project.find(v.source) if v.source else None
        if src is None:
            return v.colormap, float(v.vmin), float(v.vmax), False
        sv = src.resolve(ctx.t, ctx)
        cmap = sv.get("colormap", v.colormap)
        log = bool(sv.get("log_color", False))
        if hasattr(src, "color_range"):
            lo, hi = src.color_range(ctx, sv)
        elif src.TYPE in ("image", "screen") and sv.get("image"):
            if float(sv.vmin) != float(sv.vmax):
                lo, hi = float(sv.vmin), float(sv.vmax)
            else:
                img = ctx.assets.image(seqdata.current_file(ctx, sv, "image"))
                lo, hi = float(np.nanmin(img)), float(np.nanmax(img))
        else:
            lo, hi = float(sv.get("vmin", v.vmin)), float(sv.get("vmax", v.vmax))
        return cmap, lo, hi, log

    def draw(self, cv, ctx, v, st):
        try:
            cmap, lo, hi, log = self._mapping(ctx, v)
        except Exception as exc:
            ctx.warn(f"{self.name}: {exc}", "source")
            return None
        a = v.opacity * st.opacity
        s = ctx.s
        x, y = v.position[0] + st.dx, v.position[1] + st.dy
        th, ln = float(v.size[0]), float(v.size[1])
        vert = v.orientation == "vertical"
        n = 256
        ramp = np.linspace(1, 0, n)[:, None] if vert else np.linspace(0, 1, n)[None, :]
        col = apply_colormap(ramp, cmap, 0.0, 1.0)
        w, h = (th, ln) if vert else (ln, th)
        mask = np.ones(col.shape[:2], np.float32)
        p = st.progress
        if p < 1:
            if vert:
                mask[: int(round(n * (1 - p)))] = 0
            else:
                mask[:, int(round(n * p)):] = 0
        quad = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
        cv.warp(np.ascontiguousarray(col), quad * s, a, v.glow, mask)
        cv.polygon(quad * s, stroke=v.border_color, stroke_alpha=a * 0.8, width=1.2 * s)
        fs = float(v.font_size)
        box = [x, y, x + w, y + h]
        if int(v.ticks) > 0 and hi != lo:
            if log and lo > 0:
                ticks = 10.0 ** np.arange(math.ceil(math.log10(lo) - 1e-9), math.floor(math.log10(hi) + 1e-9) + 1)
                frac = (np.log10(ticks) - math.log10(lo)) / ((math.log10(hi) - math.log10(lo)) or 1)
                step = 1.0
            else:
                ticks, step = nice_ticks(lo, hi, int(v.ticks))
                frac = (ticks - lo) / (hi - lo)
            for tv, f in zip(ticks, frac):
                if not (-1e-6 <= f <= 1 + 1e-6):
                    continue
                txt = si(tv, v.unit) if v.unit else (f"10^{{{int(round(math.log10(tv)))}}}" if log else fmt_tick(tv, step))
                if vert:
                    yy = y + h * (1 - f)
                    cv.polyline(np.array([[x + w, yy], [x + w + 6, yy]]) * s, v.border_color, a, 1.2 * s)
                    b = ctx.draw_text(cv, txt, x + w + 10, yy, fs * 0.85, v.label_color, valign="middle", opacity=a * p)
                else:
                    xx = x + w * f
                    cv.polyline(np.array([[xx, y + h], [xx, y + h + 6]]) * s, v.border_color, a, 1.2 * s)
                    b = ctx.draw_text(cv, txt, xx, y + h + 10, fs * 0.85, v.label_color, align="center", opacity=a * p)
                if b:
                    box = [min(box[0], b[0] / s), min(box[1], b[1] / s), max(box[2], b[2] / s), max(box[3], b[3] / s)]
        if v.label:
            if vert:
                draw_rotated_text(cv, ctx, v.label, box[2] + fs * 0.9, y + h / 2, fs, v.label_color, 270, a * p)
                box[2] += fs * 1.6
            else:
                ctx.draw_text(cv, v.label, x + w / 2, box[3] + 6, fs, v.label_color, align="center", opacity=a * p)
                box[3] += fs * 1.6
        return (box[0] * s, box[1] * s, box[2] * s, box[3] * s)


# --------------------------------------------------------------------------- error bars and bands
@register
class ErrorBars(Series):
    TYPE, LABEL, ICON = "errorbars", "Error bars", "errorbars"
    DESCRIPTION = "Data points with vertical (and optionally horizontal) error bars from columns or typed values."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        *DATA_PROPS,
        Prop("y_error", "text", "", group=G_DATA, help="Column with the y uncertainty, or one number for all points"),
        Prop("y_error_values", "array", "", group=G_DATA, help="Or type them: 0.1, 0.2, 0.15"),
        Prop("x_error", "text", "", group=G_DATA, help="Optional x uncertainty: a column or one number"),
        Prop("color", "color", "gold", group=G_LOOK),
        Prop("width", "number", 2.0, min=0.3, max=12, step=0.1, group=G_LOOK),
        Prop("cap", "number", 8, min=0, max=40, step=1, group=G_LOOK, help="Cap width in pixels"),
        Prop("points", "bool", True, group=G_LOOK, help="Draw the data points"),
        Prop("point_size", "number", 5, min=0.5, max=30, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.5, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def _err(self, ctx, v, name, values_name, n):
        spec = str(v.get(name, "")).strip()
        if values_name and len(parse_array(v.get(values_name, ""))):
            e = parse_array(v[values_name])
        elif not spec:
            return np.zeros(n)
        else:
            try:
                e = np.full(n, float(spec))
            except ValueError:
                if not v.data:
                    raise ValueError(f"{spec!r} names a column but there is no data file") from None
                e = seqdata.column(ctx, v, spec)
        e = np.abs(np.asarray(e, np.float64))
        return np.resize(e, n) if len(e) else np.zeros(n)

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            xs, ys = self.xy_data(ctx, v)
            ey = self._err(ctx, v, "y_error", "y_error_values", len(xs))
            ex = self._err(ctx, v, "x_error", "", len(xs))
        except (ValueError, OSError) as exc:
            ctx.warn(f"{self.name}: {exc}", "y_error")
            return None
        if len(xs) == 0:
            return None
        a = v.opacity * st.opacity
        s = ctx.s
        p = st.progress
        off = np.array([st.dx, st.dy])
        segs = []
        cap = float(v.cap) / 2
        for x, y, dy, dx in zip(xs, ys, ey, ex):
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            X, Y = (float(c) for c in tr.map(x, y))
            if dy > 0:
                _, Yt = tr.map(x, y + dy * p)
                _, Yb = tr.map(x, y - dy * p)
                Yt, Yb = float(Yt), float(Yb)
                segs.append(np.array([[X, Yt], [X, Yb]]))
                if cap > 0 and p > 0.6:
                    segs += [np.array([[X - cap, Yt], [X + cap, Yt]]), np.array([[X - cap, Yb], [X + cap, Yb]])]
            if dx > 0:
                Xl, _ = tr.map(x - dx * p, y)
                Xr, _ = tr.map(x + dx * p, y)
                Xl, Xr = float(Xl), float(Xr)
                segs.append(np.array([[Xl, Y], [Xr, Y]]))
                if cap > 0 and p > 0.6:
                    segs += [np.array([[Xl, Y - cap], [Xl, Y + cap]]), np.array([[Xr, Y - cap], [Xr, Y + cap]])]
        if segs:
            cv.lines([(sg + off) * s for sg in segs], v.color, a, v.width * s, v.glow)
        if v.points:
            X, Y = tr.map(xs, ys)
            pts = (np.stack([X, Y], 1) + off) * s
            cv.dots(pts, v.point_size * s * min(1.0, p * 1.5), v.color, a, v.glow)
        X, Y = tr.map(xs, ys)
        return ((np.nanmin(X) - 10) * s, (np.nanmin(Y) - 10) * s, (np.nanmax(X) + 10) * s, (np.nanmax(Y) + 10) * s)


@register
class Band(Series):
    TYPE, LABEL, ICON = "band", "Uncertainty band", "band"
    DESCRIPTION = "A shaded band around a curve: centre ± spread from expressions, or lower and upper columns."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("source", "enum", "expression", options=("expression", "data"), group=G_DATA),
        Prop("center", "text", "exp(-x/3)", group=G_DATA, expr=True, help="Centre as a function of x (and t)"),
        Prop("spread", "text", "0.05 + 0.02*x", group=G_DATA, expr=True,
             help="Half-width of the band, a function of x (and t)"),
        Prop("domain", "vec2", [0, 0], group=G_DATA, help="x range (equal values = the whole chart)"),
        Prop("data", "asset", "", accept="table", group=G_DATA),
        Prop("x_column", "text", "x", group=G_DATA),
        Prop("lower_column", "text", "lower", group=G_DATA),
        Prop("upper_column", "text", "upper", group=G_DATA),
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("fill_opacity", "number", 0.25, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("center_line", "bool", True, group=G_LOOK, help="Draw the centre (expression) or mid line (data)"),
        Prop("edges", "bool", False, group=G_LOOK, help="Thin lines along the band's edges"),
        Prop("width", "number", 2.5, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def depends_on_time(self):
        if self.props.get("source") == "expression" and (uses_time(self.props.get("center", "")) or
                                                         uses_time(self.props.get("spread", ""))):
            return True
        return super().depends_on_time()

    def _xs_lo_hi(self, ctx, v, tr):
        if v.source == "data":
            if not v.data:
                raise ValueError("choose a data file")
            xs = ctx.assets.column(v.data, v.x_column)
            lo, hi = ctx.assets.column(v.data, v.lower_column), ctx.assets.column(v.data, v.upper_column)
            order = np.argsort(xs)
            xs, lo, hi = xs[order], lo[order], hi[order]
            return xs, lo, hi, (lo + hi) / 2
        d0, d1 = float(v.domain[0]), float(v.domain[1])
        if d0 == d1:
            d0, d1 = tr.xmin, tr.xmax
        xs = np.linspace(d0, d1, 300)
        c = _eval(v.center, x=xs, t=ctx.t)
        sp = np.abs(_eval(v.spread, x=xs, t=ctx.t))
        return xs, c - sp, c + sp, c

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            xs, lo, hi, mid = self._xs_lo_hi(ctx, v, tr)
        except (ExpressionError, ValueError, OSError) as exc:
            ctx.warn(f"{self.name}: {exc}", "center" if v.source == "expression" else "data")
            return None
        ok = np.isfinite(xs) & np.isfinite(lo) & np.isfinite(hi)
        xs, lo, hi, mid = xs[ok], lo[ok], hi[ok], mid[ok]
        if len(xs) < 2:
            return None
        n = max(2, int(math.ceil(len(xs) * st.progress)))
        xs, lo, hi, mid = xs[:n], lo[:n], hi[:n], mid[:n]
        a = v.opacity * st.opacity
        s = ctx.s
        off = np.array([st.dx, st.dy])
        X, Ylo = tr.map(xs, lo)
        _, Yhi = tr.map(xs, hi)
        poly = np.concatenate([np.stack([X, Yhi], 1), np.stack([X, Ylo], 1)[::-1]])
        self.clip_to(cv, ctx, tr, st)
        try:
            cv.polygon((poly + off) * s, fill=v.color, fill_alpha=v.fill_opacity * a, fill_glow=v.glow * 0.2)
            if v.edges:
                for Y in (Ylo, Yhi):
                    cv.polyline((np.stack([X, Y], 1) + off) * s, v.color, a * 0.6, 1.2 * s, v.glow * 0.3)
            if v.center_line and v.width > 0:
                _, Ym = tr.map(xs, mid)
                cv.polyline((np.stack([X, Ym], 1) + off) * s, v.color, a, v.width * s, v.glow)
        finally:
            cv.pop_clip()
        box = ((poly[:, 0].min() + st.dx) * s, (poly[:, 1].min() + st.dy) * s,
               (poly[:, 0].max() + st.dx) * s, (poly[:, 1].max() + st.dy) * s)
        return self.clip_box(box, ctx, tr, st)


# --------------------------------------------------------------------------- fits
FIT_MODELS = ("linear", "quadratic", "cubic", "exponential", "gaussian", "power", "logistic")
FIT_FORMULAS = {
    "linear": "a·x + b", "quadratic": "a·x² + b·x + c", "cubic": "a·x³ + b·x² + c·x + d",
    "exponential": "a·e^{b·x}", "gaussian": "a·e^{−(x−b)²/2c²}", "power": "a·x^{b}",
    "logistic": "a / (1 + e^{−b·(x−c)})",
}


def _model(name):
    return {
        "exponential": lambda x, a, b: a * np.exp(b * x),
        "gaussian": lambda x, a, b, c: a * np.exp(-((x - b) ** 2) / (2 * c * c)),
        "power": lambda x, a, b: a * np.power(np.abs(x), b),
        "logistic": lambda x, a, b, c: a / (1 + np.exp(-b * (x - c))),
    }[name]


def fit_curve(x: np.ndarray, y: np.ndarray, model: str) -> tuple[list[float], float]:
    """Least-squares fit; returns the parameters (a, b, c ...) and R²."""
    x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    deg = {"linear": 1, "quadratic": 2, "cubic": 3}.get(model)
    if deg is not None:
        if len(x) <= deg:
            raise ValueError(f"a {model} fit needs at least {deg + 1} points")
        p = [float(c) for c in np.polyfit(x, y, deg)]
        yhat = np.polyval(p, x)
    else:
        # starting values from linearised fits, then non-linear least squares when SciPy is there
        if model == "exponential":
            pos = y > 0
            if pos.sum() < 2:
                raise ValueError("an exponential fit needs positive y values")
            b, la = np.polyfit(x[pos], np.log(y[pos]), 1)
            p0 = [math.exp(la), b]
        elif model == "power":
            pos = (y > 0) & (x > 0)
            if pos.sum() < 2:
                raise ValueError("a power fit needs positive x and y values")
            b, la = np.polyfit(np.log(x[pos]), np.log(y[pos]), 1)
            p0 = [math.exp(la), b]
        elif model == "gaussian":
            i = int(np.argmax(y))
            w = math.sqrt(max(float(np.sum(np.clip(y, 0, None) * (x - x[i]) ** 2) / max(np.sum(np.clip(y, 0, None)), 1e-12)), 1e-12))
            p0 = [float(y[i]), float(x[i]), w]
        elif model == "logistic":
            p0 = [float(np.max(y)), 4.0 / max(float(np.ptp(x)), 1e-9), float(np.median(x))]
        else:
            raise ValueError(f"unknown model {model!r}: {', '.join(FIT_MODELS)}")
        f = _model(model)
        p = list(p0)
        try:
            from scipy.optimize import curve_fit
            with np.errstate(all="ignore"):
                p, _ = curve_fit(f, x, y, p0=p0, maxfev=20000)
            p = [float(c) for c in p]
        except ImportError:
            pass
        except (RuntimeError, ValueError):
            pass
        with np.errstate(all="ignore"):
            yhat = f(x, *p)
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-300
    return p, 1.0 - ss_res / ss_tot


def eval_fit(model: str, p, x):
    if model in ("linear", "quadratic", "cubic"):
        return np.polyval(p, x)
    with np.errstate(all="ignore"):
        return _model(model)(np.asarray(x, np.float64), *p)


@register
class Fit(Series):
    TYPE, LABEL, ICON = "fit", "Fitted curve", "fitcurve"
    DESCRIPTION = ("A model fitted to data (linear, polynomial, exponential, Gaussian, power, logistic), with an "
                   "optional label showing the fitted parameters and R².")
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        *DATA_PROPS,
        Prop("model", "enum", "linear", options=FIT_MODELS, group=G_DATA),
        Prop("extend", "bool", False, group=G_DATA, help="Draw across the whole chart, not just the data's x range"),
        Prop("color", "color", "red", group=G_LOOK),
        Prop("width", "number", 2.5, min=0.3, max=20, step=0.5, group=G_LOOK),
        Prop("style", "enum", "dashed", options=("solid", "dashed", "dotted"), group=G_LOOK),
        Prop("glow", "number", 0.6, min=0, max=4, step=0.05, group=G_LOOK),
        Prop("label", "text", "", group=G_TXT,
             help="Shows the fit: {formula}, {a:.3g}, {b:.3g}, {c:.3g}, {d:.3g}, {r2:.4f}"),
        Prop("label_at", "vec2", [0.04, 0.06], group=G_TXT, help="Where the label goes, as fractions of the chart"),
        Prop("label_size", "number", 18, min=6, max=60, step=1, group=G_TXT),
    ]

    def fitted(self, ctx, v):
        xs, ys = self.xy_data(ctx, v)
        key = ("fit", v.model, hash(xs.tobytes()), hash(ys.tobytes()))
        p, r2 = ctx.assets.memo(key, lambda: fit_curve(xs, ys, v.model))
        return xs, p, r2

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            xs, p, r2 = self.fitted(ctx, v)
        except (ValueError, OSError, np.linalg.LinAlgError) as exc:
            ctx.warn(f"{self.name}: {exc}", "model")
            return None
        if v.extend or len(xs) == 0:
            lo, hi = tr.xmin, tr.xmax
        else:
            lo, hi = float(np.nanmin(xs)), float(np.nanmax(xs))
        X = np.linspace(lo, hi, 300)
        Y = eval_fit(v.model, p, X)
        Xp, Yp = tr.map(X, Y)
        pts = np.stack([Xp, Yp], 1) + (st.dx, st.dy)
        pts = pts[np.isfinite(pts).all(axis=1)]
        a = v.opacity * st.opacity
        s = ctx.s
        self.clip_to(cv, ctx, tr, st)
        try:
            dash = {"dashed": 14, "dotted": 3}.get(v.style, 0) * s
            gap = {"dashed": 10, "dotted": 7}.get(v.style, 0) * s
            cv.polyline(pts * s, v.color, a, v.width * s, v.glow, dash=dash, gap=gap, progress=st.progress)
        finally:
            cv.pop_clip()
        if v.label and st.progress > 0.5:
            names = dict(zip("abcd", p))
            names.update(r2=r2)
            text = v.label.replace("{formula}", FIT_FORMULAS.get(v.model, ""))
            text = _format_named(text, names)
            lx = tr.x0 + tr.w * float(v.label_at[0]) + st.dx
            ly = tr.y0 + tr.h * float(v.label_at[1]) + st.dy
            ctx.draw_text(cv, text, lx, ly, v.label_size, v.color, opacity=a * min(1, (st.progress - 0.5) * 2))
        if len(pts) == 0:
            return None
        return self.clip_box((pts[:, 0].min() * s, pts[:, 1].min() * s, pts[:, 0].max() * s, pts[:, 1].max() * s),
                             ctx, tr, st)


def _format_named(text: str, values: dict) -> str:
    import re

    from ..engine.units import format_number

    def rep(m):
        name, spec = m.group(1), m.group(2)
        if name not in values:
            return m.group(0)
        try:
            return format_number(values[name], spec or ".4g")
        except (ValueError, TypeError):
            return str(values[name])
    return re.sub(r"\{(a|b|c|d|r2)(?::([^{}]*))?\}", rep, text)


# --------------------------------------------------------------------------- spectrum
def find_peaks(x: np.ndarray, y: np.ndarray, prominence: float, max_peaks: int = 12) -> np.ndarray:
    """Indices of peaks at least ``prominence`` (fraction of the y range) above their surroundings."""
    y = np.asarray(y, np.float64)
    rng = float(np.nanmax(y) - np.nanmin(y)) or 1.0
    try:
        from scipy.signal import find_peaks as fp
        idx, props = fp(np.nan_to_num(y, nan=float(np.nanmin(y))), prominence=prominence * rng)
        order = np.argsort(-props["prominences"])[:max_peaks]
        return np.sort(idx[order])
    except ImportError:
        pass
    n = len(y)
    w = max(1, n // 200)
    cand = [i for i in range(w, n - w) if y[i] == np.max(y[i - w:i + w + 1]) and y[i] > y[i - 1]]
    out = []
    for i in cand:
        left = y[: i + 1][::-1]
        right = y[i:]
        lmin = np.minimum.accumulate(left)[np.argmax(left > y[i])] if (left > y[i]).any() else left.min()
        rmin = np.minimum.accumulate(right)[np.argmax(right > y[i])] if (right > y[i]).any() else right.min()
        prom = y[i] - max(lmin, rmin)
        if prom >= prominence * rng:
            out.append((prom, i))
    out.sort(reverse=True)
    return np.sort(np.array([i for _, i in out[:max_peaks]], np.int64))


@register
class Spectrum(Series):
    TYPE, LABEL, ICON = "spectrum", "Spectrum", "spectrum"
    DESCRIPTION = "A spectrum (data or expression) with its peaks found automatically or listed, each with a label."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        Prop("source", "enum", "data", options=("data", "expression"), group=G_DATA),
        Prop("expression", "text", "gauss(x, 3, 0.2) + 0.6*gauss(x, 6.4, 0.3) + 0.3*gauss(x, 7.1, 0.25)",
             group=G_DATA, expr=True, help="Intensity as a function of x"),
        *DATA_PROPS,
        Prop("peaks", "array", "", group="Peaks", help="x of the peaks to label (empty = found automatically)"),
        Prop("prominence", "number", 0.1, min=0.001, max=1, step=0.01, group="Peaks",
             help="Automatic peaks must stand this fraction of the y range above their surroundings"),
        Prop("max_peaks", "int", 8, min=0, max=50, group="Peaks"),
        Prop("peak_labels", "text", "", group="Peaks", help="Comma-separated names, one per peak (else the x value)"),
        Prop("label_format", "text", "{x:.3g}", group="Peaks", help="Label of peaks without a name"),
        Prop("label_size", "number", 16, min=6, max=60, step=1, group="Peaks"),
        Prop("label_color", "color", "cream", group="Peaks"),
        Prop("marker_color", "color", "gold", group="Peaks"),
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("width", "number", 2.0, min=0, max=20, step=0.5, group=G_LOOK),
        Prop("fill_opacity", "number", 0.15, min=0, max=1, step=0.01, group=G_LOOK),
        Prop("glow", "number", 0.8, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def depends_on_time(self):
        if self.props.get("source") == "expression" and uses_time(self.props.get("expression", "")):
            return True
        return super().depends_on_time()

    def _xy(self, ctx, v, tr):
        if v.source == "expression":
            xs = np.linspace(tr.xmin, tr.xmax, 800)
            return xs, _eval(v.expression, x=xs, t=ctx.t)
        xs, ys = self.xy_data(ctx, v)
        order = np.argsort(xs)
        return xs[order], ys[order]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            xs, ys = self._xy(ctx, v, tr)
        except (ExpressionError, ValueError, OSError) as exc:
            ctx.warn(f"{self.name}: {exc}", "expression" if v.source == "expression" else "data")
            return None
        ok = np.isfinite(xs) & np.isfinite(ys)
        xs, ys = xs[ok], ys[ok]
        if len(xs) < 2:
            return None
        a = v.opacity * st.opacity
        s = ctx.s
        off = np.array([st.dx, st.dy])
        X, Y = tr.map(xs, ys)
        pts = np.stack([X, Y], 1) + off
        n = max(2, int(math.ceil(len(pts) * st.progress)))
        x_reached = xs[n - 1]
        self.clip_to(cv, ctx, tr, st)
        try:
            if v.fill_opacity > 0:
                base = tr.y0 + tr.h + st.dy
                poly = np.vstack([pts[:n], [[pts[n - 1, 0], base], [pts[0, 0], base]]])
                cv.polygon(poly * s, fill=v.color, fill_alpha=v.fill_opacity * a)
            cv.polyline(pts[:n] * s, v.color, a, v.width * s, v.glow)
        finally:
            cv.pop_clip()
        listed = parse_array(v.peaks)
        if len(listed):
            idx = np.array([int(np.argmin(np.abs(xs - px))) for px in listed])
        else:
            idx = find_peaks(xs, ys, float(v.prominence), int(v.max_peaks)) if int(v.max_peaks) > 0 else np.zeros(0, int)
        names = [t.strip() for t in v.peak_labels.split(",")] if v.peak_labels.strip() else []
        fs = float(v.label_size)
        for k, i in enumerate(idx):
            if xs[i] > x_reached:
                continue
            px, py = pts[i]
            top = max(tr.y0 + st.dy + fs * 1.4, py - 36)
            cv.polyline(np.array([[px, py - 4], [px, top + fs * 0.3]]) * s, v.marker_color, a * 0.8, 1.2 * s, 0.4)
            cv.circle(px * s, py * s, 3.5 * s, fill=v.marker_color, fill_alpha=a, fill_glow=0.6)
            name = names[k] if k < len(names) and names[k] else format_values(v.label_format, x=float(xs[i]), y=float(ys[i]))
            ctx.draw_text(cv, name, px, top, fs, v.label_color, align="center", valign="bottom", opacity=a)
        x0, y0, x1, y1 = tr.rect
        return (x0 * s, y0 * s, x1 * s, y1 * s)


# --------------------------------------------------------------------------- 2D histogram
@register
class Hist2D(Series):
    TYPE, LABEL, ICON = "hist2d", "2D histogram", "hist2d"
    DESCRIPTION = "Counts of (x, y) pairs in a grid of bins, coloured by a colormap: joint histograms, density maps."
    HAS_PROGRESS = True
    PROPS = [
        AXES_REF,
        *DATA_PROPS,
        Prop("bins", "vec2", [60, 60], group=G_DATA, help="Bins along x and y; the range is the chart's"),
        Prop("colormap", "enum", "magma", options=COLORMAPS, group=G_COL),
        Prop("log_color", "bool", True, group=G_COL, help="Colour by log(count): faint populations stay visible"),
        Prop("clear_empty", "bool", True, group=G_COL, help="Empty bins are see-through"),
        Prop("smooth", "bool", False, group=G_LOOK),
        Prop("glow", "number", 0.3, min=0, max=3, step=0.05, group=G_LOOK),
    ]

    def counts(self, ctx, v, tr):
        xs, ys = self.xy_data(ctx, v)
        nx, ny = max(1, int(v.bins[0])), max(1, int(v.bins[1]))
        H, _, _ = np.histogram2d(xs, ys, bins=(nx, ny), range=((min(tr.xmin, tr.xmax), max(tr.xmin, tr.xmax)),
                                                               (min(tr.ymin, tr.ymax), max(tr.ymin, tr.ymax))))
        return H.T[::-1]                     # rows top (high y) to bottom

    def color_range(self, ctx, v):
        tr = ctx.axes(v.axes)
        if tr is None:
            return 1.0, 10.0
        H = self.counts(ctx, v, tr)
        return (1.0, max(float(H.max()), 10.0)) if v.log_color else (0.0, max(float(H.max()), 1.0))

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            H = self.counts(ctx, v, tr)
        except (ValueError, OSError) as exc:
            ctx.warn(f"{self.name}: {exc}", "data")
            return None
        lo, hi = self.color_range(ctx, v)
        col, ok = _cmap(H, v.colormap, lo, hi, bool(v.log_color))
        mask = np.ones(H.shape, np.float32) if not v.clear_empty else (H > 0).astype(np.float32)
        mask *= min(1.0, st.progress * 1.2) if st.progress < 1 else 1.0
        x0, y0, x1, y1 = tr.rect
        quad = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64) + (st.dx, st.dy)
        cv.warp(np.ascontiguousarray(col), quad * ctx.s, v.opacity * st.opacity, v.glow, mask, nearest=not v.smooth)
        return (quad[:, 0].min() * ctx.s, quad[:, 1].min() * ctx.s, quad[:, 0].max() * ctx.s, quad[:, 1].max() * ctx.s)


# --------------------------------------------------------------------------- fields
FIELD_PROPS = [
    Prop("u", "text", "-y + 0.5", group=G_DATA, expr="x,y,t", help="x component of the field, a function of x, y (and t)"),
    Prop("v", "text", "x - 5", group=G_DATA, expr="x,y,t", help="y component"),
]


class _Field(Series):
    def depends_on_time(self):
        return uses_time(self.props.get("u", "")) or uses_time(self.props.get("v", "")) or super().depends_on_time()

    def field(self, ctx, v, x, y):
        return _eval(v.u, x=x, y=y, t=ctx.t), _eval(v.v, x=x, y=y, t=ctx.t)


@register
class VectorField(_Field):
    TYPE, LABEL, ICON = "vectorfield", "Vector field", "vectorfield"
    DESCRIPTION = "Arrows on a grid showing a field u(x, y), v(x, y): flows, forces, gradients. Animate with t."
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        *FIELD_PROPS,
        Prop("grid", "vec2", [18, 12], group=G_DATA, help="Arrows across and up"),
        Prop("length", "number", 0.9, min=0.05, max=5, step=0.05, group=G_LOOK,
             help="Longest arrow as a fraction of the grid spacing"),
        Prop("normalize", "bool", False, group=G_LOOK, help="All arrows the same length; colour shows the strength"),
        Prop("color", "color", "ice", group=G_LOOK),
        Prop("color_by_strength", "bool", True, group=G_LOOK),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_LOOK),
        Prop("width", "number", 2.0, min=0.3, max=10, step=0.1, group=G_LOOK),
        Prop("head_size", "number", 8, min=0, max=40, step=1, group=G_LOOK),
        Prop("glow", "number", 0.5, min=0, max=4, step=0.05, group=G_LOOK),
    ]

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        nx, ny = max(1, int(v.grid[0])), max(1, int(v.grid[1]))
        xs = tr.xmin + (np.arange(nx) + 0.5) / nx * (tr.xmax - tr.xmin)
        ys = tr.ymin + (np.arange(ny) + 0.5) / ny * (tr.ymax - tr.ymin)
        X, Y = np.meshgrid(xs, ys)
        try:
            U, V = self.field(ctx, v, X, Y)
        except ExpressionError as exc:
            ctx.warn(f"{self.name}: {exc}", "u")
            return None
        # directions in screen pixels (y down), so arrows look right whatever the axis ranges
        du = U * tr.w / ((tr.xmax - tr.xmin) or 1e-12)
        dv = -V * tr.h / ((tr.ymax - tr.ymin) or 1e-12)
        mag = np.hypot(du, dv)
        strength = np.hypot(U, V)
        cell = min(tr.w / nx, tr.h / ny)
        mmax = float(np.nanmax(mag)) if np.isfinite(mag).any() else 0.0
        if mmax <= 0:
            return None
        scale = np.where(mag > 0, cell * float(v.length) / mag, 0.0) if v.normalize else cell * float(v.length) / mmax
        L = st.progress
        PX, PY = tr.map(X, Y)
        a = v.opacity * st.opacity
        s = ctx.s
        cols = None
        if v.color_by_strength:
            cols = apply_colormap(strength.ravel()[:, None], v.colormap)[:, 0]
        segs, heads, colors = [], [], []
        for k, (px, py, ddu, ddv) in enumerate(zip(PX.ravel(), PY.ravel(), (du * scale).ravel(), (dv * scale).ravel())):
            if not (np.isfinite(ddu) and np.isfinite(ddv)) or (ddu == 0 and ddv == 0):
                continue
            tail = np.array([px - ddu * L / 2, py - ddv * L / 2]) + (st.dx, st.dy)
            tip = np.array([px + ddu * L / 2, py + ddv * L / 2]) + (st.dx, st.dy)
            segs.append(np.array([tail, tip]))
            hs = min(float(v.head_size), 0.5 * math.hypot(ddu, ddv) * L)
            heads.append(arrow_head(tip, tip - tail, hs))
            colors.append(None if cols is None else cols[k])
        self.clip_to(cv, ctx, tr, st)
        try:
            if cols is None:
                cv.lines([sg * s for sg in segs], v.color, a, v.width * s, v.glow)
                for h in heads:
                    if len(h):
                        cv.polygon(h * s, fill=v.color, fill_alpha=a, fill_glow=v.glow * 0.5)
            else:
                for sg, h, c in zip(segs, heads, colors):
                    cv.polyline(sg * s, c, a, v.width * s, v.glow)
                    if len(h):
                        cv.polygon(h * s, fill=c, fill_alpha=a, fill_glow=v.glow * 0.5)
        finally:
            cv.pop_clip()
        x0, y0, x1, y1 = tr.rect
        return (x0 * s, y0 * s, x1 * s, y1 * s)


@register
class Streamlines(_Field):
    TYPE, LABEL, ICON = "streamlines", "Streamlines", "streamlines"
    DESCRIPTION = ("Lines that follow a field u(x, y), v(x, y), drawn on with the draw effect; Flow speed moves "
                   "dashes along them like tracer particles.")
    HAS_PROGRESS = True
    DEFAULT_ENTER = "draw"
    PROPS = [
        AXES_REF,
        *FIELD_PROPS,
        Prop("seeds", "int", 40, min=1, max=1000, group=G_DATA, help="Number of lines, started on a jittered grid"),
        Prop("steps", "int", 300, min=10, max=3000, group=G_DATA, help="Maximum points per line"),
        Prop("color", "color", "teal", group=G_LOOK),
        Prop("color_by_strength", "bool", False, group=G_LOOK),
        Prop("colormap", "enum", "viridis", options=COLORMAPS, group=G_LOOK),
        Prop("width", "number", 2.0, min=0.3, max=10, step=0.1, group=G_LOOK),
        Prop("flow_speed", "number", 0.0, min=0, step=10, group=G_LOOK,
             help="Pixels per second the dashes travel (0 = solid lines)"),
        Prop("dash", "number", 18, min=2, max=200, step=1, group=G_LOOK, help="Dash length when flowing"),
        Prop("glow", "number", 0.7, min=0, max=4, step=0.05, group=G_LOOK),
    ]
    TIME_DEPENDENT = False

    def depends_on_time(self):
        return float(self.props.get("flow_speed", 0) or 0) > 0 or super().depends_on_time()

    def _lines(self, ctx, v, tr):
        n = int(v.seeds)
        aspect = tr.w / max(tr.h, 1e-9)
        ny = max(1, int(round(math.sqrt(n / aspect))))
        nx = max(1, int(math.ceil(n / ny)))
        rng = np.random.default_rng(23)
        gx, gy = np.meshgrid((np.arange(nx) + 0.5) / nx, (np.arange(ny) + 0.5) / ny)
        fx = np.clip(gx.ravel()[:n] + (rng.random(min(n, gx.size)) - 0.5) / nx * 0.8, 0, 1)
        fy = np.clip(gy.ravel()[:n] + (rng.random(min(n, gy.size)) - 0.5) / ny * 0.8, 0, 1)
        sx = tr.x0 + fx * tr.w
        sy = tr.y0 + (1 - fy) * tr.h
        h = 2.0                               # pixels per step
        kx = ((tr.xmax - tr.xmin) or 1e-12) / tr.w
        ky = ((tr.ymax - tr.ymin) or 1e-12) / tr.h

        def vel(px, py):
            x = tr.xmin + (px - tr.x0) * kx
            y = tr.ymin + (tr.y0 + tr.h - py) * ky
            U, V = self.field(ctx, v, x, y)
            du, dv = U / kx, -V / ky
            m = np.hypot(du, dv)
            with np.errstate(all="ignore"):
                return np.where(m > 0, du / m, 0), np.where(m > 0, dv / m, 0), np.hypot(U, V)

        def trace(sign):
            px, py = sx.copy(), sy.copy()
            alive = np.ones(len(px), bool)
            out_x, out_y, out_m = [px.copy()], [py.copy()], []
            for _ in range(int(v.steps) // 2):
                k1x, k1y, m1 = vel(px, py)
                k2x, k2y, _ = vel(px + sign * h / 2 * k1x, py + sign * h / 2 * k1y)
                k3x, k3y, _ = vel(px + sign * h / 2 * k2x, py + sign * h / 2 * k2y)
                k4x, k4y, _ = vel(px + sign * h * k3x, py + sign * h * k3y)
                nx_ = px + sign * h / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
                ny_ = py + sign * h / 6 * (k1y + 2 * k2y + 2 * k3y + k4y)
                still = np.hypot(nx_ - px, ny_ - py) < 1e-3
                inside = (nx_ >= tr.x0) & (nx_ <= tr.x0 + tr.w) & (ny_ >= tr.y0) & (ny_ <= tr.y0 + tr.h)
                alive &= inside & ~still & np.isfinite(nx_) & np.isfinite(ny_)
                px = np.where(alive, nx_, px)
                py = np.where(alive, ny_, py)
                out_x.append(np.where(alive, px, np.nan))
                out_y.append(np.where(alive, py, np.nan))
                out_m.append(m1)
                if not alive.any():
                    break
            return np.array(out_x), np.array(out_y), np.array(out_m) if out_m else np.zeros((0, len(px)))
        fx_, fy_, fm = trace(1.0)
        bx, by, bm = trace(-1.0)
        lines = []
        for i in range(len(sx)):
            back = np.stack([bx[1:, i], by[1:, i]], 1)[::-1]
            fwd = np.stack([fx_[:, i], fy_[:, i]], 1)
            pts = np.vstack([back, fwd])
            pts = pts[np.isfinite(pts).all(axis=1)]
            if len(pts) >= 3:
                strength = float(np.nanmean(np.concatenate([fm[:, i], bm[:, i]]))) if fm.size else 0.0
                lines.append((pts, strength))
        return lines

    def draw(self, cv, ctx, v, st):
        tr = self.axes_or_warn(ctx, v)
        if tr is None:
            return None
        try:
            lines = self._lines(ctx, v, tr)
        except ExpressionError as exc:
            ctx.warn(f"{self.name}: {exc}", "u")
            return None
        a = v.opacity * st.opacity
        s = ctx.s
        speed = float(v.flow_speed)
        if v.color_by_strength and lines:
            ms = np.array([m for _, m in lines])
            cols = apply_colormap(ms[:, None], v.colormap)[:, 0]
        else:
            cols = [None] * len(lines)
        self.clip_to(cv, ctx, tr, st)
        try:
            for (pts, _), c in zip(lines, cols):
                p = (pts + (st.dx, st.dy)) * s
                color = v.color if c is None else c
                if speed > 0:
                    from ..engine.surface import truncate_path
                    p2 = truncate_path(p, st.progress) if st.progress < 1 else p
                    if len(p2) < 2:
                        continue
                    d = float(v.dash) * s
                    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p2, axis=0), axis=1))])
                    on = ((cum - ctx.t * speed * s) % (2 * d)) < d
                    edges = np.flatnonzero(np.diff(on.astype(np.int8))) + 1
                    bounds = np.concatenate([[0], edges, [len(on)]])
                    runs = [p2[b0:b1] for b0, b1 in zip(bounds[:-1], bounds[1:]) if on[b0] and b1 - b0 >= 2]
                    cv.lines(runs, color, a, v.width * s, v.glow)
                else:
                    cv.polyline(p, color, a, v.width * s, v.glow, progress=st.progress)
        finally:
            cv.pop_clip()
        x0, y0, x1, y1 = tr.rect
        return (x0 * s, y0 * s, x1 * s, y1 * s)
