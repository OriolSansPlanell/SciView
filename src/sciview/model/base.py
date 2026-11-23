"""Property schema, keyframes, enter/exit effects and the SceneObject base class.

Every object type declares its properties as a list of :class:`Prop`. The same
schema drives JSON validation, the Python API and the editor's inspector, so a
new object type only needs its ``PROPS`` and a ``draw`` method.
"""
from __future__ import annotations

import copy
import itertools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from ..engine.color import rgb_to_hex
from ..engine.easing import EASING_NAMES, ease

if TYPE_CHECKING:  # pragma: no cover
    from ..engine.surface import Canvas
    from .context import RenderContext

ANIMATABLE_KINDS = {"number", "int", "color", "vec2", "vec3"}
KINDS = {"number", "int", "bool", "text", "longtext", "color", "vec2", "vec3", "enum",
         "asset", "array", "ref", "font"}


@dataclass
class Prop:
    """One editable property of an object type."""

    name: str
    kind: str
    default: Any
    label: str = ""
    group: str = "Main"
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple = ()
    animatable: bool | None = None
    help: str = ""
    accept: str = ""   # asset kind filter for kind='asset': image, table, mesh, audio, volume, molecule
    ref: str = ""      # referenced object type for kind='ref'
    expr: bool | str = False  # a math expression, checked by Project.problems(); "x,y,t" names its variables

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown property kind {self.kind!r}")
        if not self.label:
            self.label = self.name.replace("_", " ").capitalize()
        if self.animatable is None:
            self.animatable = self.kind in ANIMATABLE_KINDS

    def schema(self) -> dict:
        d = {"name": self.name, "kind": self.kind, "default": self.default, "label": self.label,
             "group": self.group, "animatable": self.animatable}
        for k in ("min", "max", "step", "help", "accept", "ref"):
            v = getattr(self, k)
            if v not in (None, ""):
                d[k] = v
        if self.expr:
            d["expr"] = self.expr if isinstance(self.expr, str) else "x,t"
        if self.options:
            d["options"] = list(self.options)
        return d

    def coerce(self, value: Any) -> Any:
        """Normalise a value from JSON or Python to this property's storage type."""
        k = self.kind
        if value is None:
            return copy.deepcopy(self.default)
        try:
            if k == "number":
                return float(value)
            if k == "int":
                return int(round(float(value)))
            if k == "bool":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if k in ("text", "longtext", "asset", "ref", "font"):
                return "" if value is None else str(value)
            if k == "color":
                if isinstance(value, (list, tuple, np.ndarray)):
                    return rgb_to_hex(np.asarray(value, np.float64) / (255.0 if max(value) > 1 else 1.0))
                return str(value).strip()
            if k in ("vec2", "vec3"):
                n = 2 if k == "vec2" else 3
                seq = list(np.asarray(value, np.float64).ravel()[:n])
                if len(seq) < n:
                    seq += list(self.default[len(seq):n])
                return [float(x) for x in seq]
            if k == "enum":
                s = str(value)
                return s if (not self.options or s in self.options) else self.default
            if k == "array":
                if isinstance(value, np.ndarray):
                    return [float(x) for x in value.ravel()]
                if isinstance(value, (list, tuple)):
                    return [float(x) for x in value]
                return str(value)
        except (TypeError, ValueError):
            return copy.deepcopy(self.default)
        return value


def parse_array(value: Any) -> np.ndarray:
    """Numbers from a list, or from text like ``"1, 2.5, 3"`` / ``"1 2 3"``."""
    if isinstance(value, np.ndarray):
        return value.astype(np.float64).ravel()
    if isinstance(value, (list, tuple)):
        return np.asarray(value, np.float64).ravel()
    s = str(value or "").strip()
    if not s:
        return np.zeros(0)
    toks = [t for t in re.split(r"[,\s;]+", s) if t]
    out = []
    for t in toks:
        try:
            out.append(float(t))
        except ValueError:
            out.append(np.nan)
    return np.asarray(out, np.float64)


# --------------------------------------------------------------------------- effects
ENTER_EFFECTS = ("none", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "pop")
SLIDE_PX = 40.0


@dataclass
class State:
    """How an object looks at time t because of its enter/exit effects."""

    opacity: float = 1.0
    dx: float = 0.0          # design pixels
    dy: float = 0.0
    scale: float = 1.0
    progress: float = 1.0    # draw-on / typewriter fraction
    local_t: float = 0.0     # seconds since the object appeared


def _apply_effect(st: State, effect: str, k: float, entering: bool, has_progress: bool) -> None:
    if effect == "none" or k >= 1:
        return
    sign = 1.0 if entering else -1.0
    if effect == "fade":
        st.opacity *= k
    elif effect.startswith("slide_"):
        st.opacity *= k
        d = SLIDE_PX * (1 - k)
        if effect == "slide_up":
            st.dy += sign * d
        elif effect == "slide_down":
            st.dy -= sign * d
        elif effect == "slide_left":
            st.dx += sign * d
        elif effect == "slide_right":
            st.dx -= sign * d
    elif effect == "pop":
        st.opacity *= min(1.0, k * 2.5)
        st.scale *= 0.6 + 0.4 * ease("overshoot", k)
    elif effect in ("draw", "typewriter", "grow"):
        if has_progress:
            st.progress *= k
            st.opacity *= min(1.0, k * 6)
        else:
            st.opacity *= k


# --------------------------------------------------------------------------- registry
REGISTRY: dict[str, type[SceneObject]] = {}
_id_counter = itertools.count(1)


def register(cls: type[SceneObject]) -> type[SceneObject]:
    REGISTRY[cls.TYPE] = cls
    return cls


OPACITY = Prop("opacity", "number", 1.0, min=0, max=1, step=0.01, group="Appearance")
LABEL_PROPS = [
    Prop("label", "text", "", group="Label", help="Text shown next to the object. Markup: H_2O, ^6Li, \\alpha"),
    Prop("label_color", "color", "cream", group="Label"),
    Prop("label_size", "number", 20, min=6, max=120, step=1, group="Label"),
    Prop("label_position", "enum", "above", options=("above", "below", "left", "right", "center"), group="Label"),
    Prop("label_offset", "vec2", [0, 0], group="Label", help="Extra shift in pixels"),
]


class SceneObject:
    """Base class for everything that can be placed in a film."""

    TYPE: ClassVar[str] = "object"
    LABEL: ClassVar[str] = "Object"
    CATEGORY: ClassVar[str] = "Shapes"
    ICON: ClassVar[str] = "square"
    DESCRIPTION: ClassVar[str] = ""
    IS_3D: ClassVar[bool] = False
    HAS_LABEL: ClassVar[bool] = True        # 3D objects get the Label property group
    HAS_PROGRESS: ClassVar[bool] = False    # supports the 'draw' effect
    REQUIRED_REFS: ClassVar[tuple[str, ...]] = ()   # reference properties that must point at an object
    TEXTUAL: ClassVar[bool] = False         # supports the 'typewriter' effect
    PROPS: ClassVar[list[Prop]] = []
    DEFAULT_ENTER: ClassVar[str] = "fade"
    DEFAULT_EXIT: ClassVar[str] = "fade"
    DEFAULT_DURATION: ClassVar[float | None] = None  # seconds; None = until the end
    TIME_DEPENDENT: ClassVar[bool] = False  # looks different at every instant (particles ...)
    IS_GROUP: ClassVar[bool] = False

    def __init__(self, id: str | None = None, name: str | None = None, props: dict | None = None,
                 keys: dict | None = None, start: float = 0.0, end: float | None = None,
                 enter: dict | None = None, exit: dict | None = None, visible: bool = True,
                 locked: bool = False, parent: str | None = None, tracks: dict | None = None,
                 scene: str | None = None, **kwargs):
        self.id = id or f"{self.TYPE}{next(_id_counter)}"
        self.name = name or self.LABEL
        self.parent: str | None = parent or None
        self.scene: str | None = scene or None      # the scene it belongs to (its times are scene times)
        self.props: dict[str, Any] = {p.name: copy.deepcopy(p.default) for p in self.all_props()}
        self.keys: dict[str, list[dict]] = {}
        self.start = float(start or 0.0)
        self.end = None if end is None else float(end)
        enter = enter or {}
        exit = exit or {}
        self.enter_effect = enter.get("effect", self.DEFAULT_ENTER)
        self.enter_duration = float(enter.get("duration", 0.6))
        self.exit_effect = exit.get("effect", self.DEFAULT_EXIT)
        self.exit_duration = float(exit.get("duration", 0.6))
        self.visible = bool(visible)
        self.locked = bool(locked)
        self.warnings: list[str] = []
        self.tracks: dict[str, dict] = {}
        for k, v in (props or {}).items():
            self.set(k, v, strict=False)
        for k, tr in (tracks or {}).items():
            try:
                self.track(k, **tr)
            except (KeyError, ValueError, TypeError) as exc:
                self.warnings.append(f"{self.name}: ignored the data track of {k!r} ({exc})")
        for k, ks in (keys or {}).items():
            for kf in ks:
                try:
                    self.key(k, kf.get("t", 0), kf.get("v"), kf.get("ease", "smooth"), kf.get("bez"))
                except (KeyError, ValueError) as exc:
                    self.warnings.append(f"{self.name}: ignored keyframes of {k!r} ({exc})")
        for k, v in kwargs.items():
            self.set(k, v)

    # ------------------------------------------------------------------ schema
    @classmethod
    def all_props(cls) -> list[Prop]:
        cache = cls.__dict__.get("_all_props")
        if cache is None:
            names = {p.name for p in cls.PROPS}
            extra = [OPACITY] if "opacity" not in names else []
            if cls.IS_3D and cls.HAS_LABEL:
                extra += [p for p in LABEL_PROPS if p.name not in names]
            cache = list(cls.PROPS) + extra
            cls._all_props = cache
        return cache

    @classmethod
    def prop_map(cls) -> dict[str, Prop]:
        cache = cls.__dict__.get("_prop_map")
        if cache is None:
            cache = {p.name: p for p in cls.all_props()}
            cls._prop_map = cache
        return cache

    @classmethod
    def effects(cls) -> list[str]:
        out = list(ENTER_EFFECTS)
        if cls.IS_GROUP:
            return out
        if cls.HAS_PROGRESS:
            out.append("draw")
        if cls.TEXTUAL:
            out.append("typewriter")
        return out

    @classmethod
    def schema(cls) -> dict:
        return {"type": cls.TYPE, "label": cls.LABEL, "category": cls.CATEGORY, "icon": cls.ICON,
                "description": cls.DESCRIPTION, "is3d": cls.IS_3D, "effects": cls.effects(),
                "default_enter": cls.DEFAULT_ENTER, "default_exit": cls.DEFAULT_EXIT,
                "default_duration": cls.DEFAULT_DURATION,
                "props": [p.schema() for p in cls.all_props()]}

    # ------------------------------------------------------------------ values
    def set(self, name: str, value: Any, strict: bool = True) -> SceneObject:
        p = self.prop_map().get(name)
        if p is None:
            if strict:
                raise KeyError(f"{self.TYPE} has no property {name!r}. "
                               f"Available: {', '.join(self.prop_map())}")
            self.warnings.append(f"{self.name}: ignored unknown property {name!r}")
            return self
        self.props[name] = p.coerce(value)
        return self

    def get(self, name: str) -> Any:
        return self.props[name]

    def __getitem__(self, name: str) -> Any:
        return self.get(name)

    def __setitem__(self, name: str, value: Any) -> None:
        self.set(name, value)

    def key(self, name: str, t: float, value: Any = None, ease: str = "smooth", bez=None) -> SceneObject:
        """Add (or replace) a keyframe. ``value=None`` keys the current static value.

        ``ease`` names how the value eases INTO this keyframe; ``ease="bezier"`` with
        ``bez=(x1, y1, x2, y2)`` gives a custom curve, as CSS cubic-bezier.
        """
        p = self.prop_map().get(name)
        if p is None:
            raise KeyError(f"{self.TYPE} has no property {name!r}")
        if not p.animatable:
            raise ValueError(f"property {name!r} cannot be animated")
        v = p.coerce(self.props[name] if value is None else value)
        e = ease if ease in EASING_NAMES else "smooth"
        kf: dict[str, Any] = {"t": float(t), "v": v, "ease": e}
        if e == "bezier":
            try:
                b = [float(x) for x in (bez or ())]
            except (TypeError, ValueError):
                b = []
            if len(b) != 4:
                kf["ease"] = "smooth"
            else:
                kf["bez"] = [min(max(b[0], 0.0), 1.0), b[1], min(max(b[2], 0.0), 1.0), b[3]]
        ks = [k for k in self.keys.get(name, []) if abs(k["t"] - float(t)) > 1e-6]
        ks.append(kf)
        ks.sort(key=lambda k: k["t"])
        self.keys[name] = ks
        return self

    def clear_keys(self, name: str | None = None) -> SceneObject:
        if name is None:
            self.keys.clear()
        else:
            self.keys.pop(name, None)
        return self

    def track(self, name: str, data: str, column: str = "", time: str = "t", scale: float = 1.0,
              offset: float = 0.0, time_scale: float = 1.0, time_offset: float = 0.0,
              smooth: bool = True) -> SceneObject:
        """Drive a property from table columns over time.

        At film time ``t`` the table time is ``(t - time_offset) * time_scale``; the value is the
        ``column`` interpolated there (``smooth=False`` holds each row's value), times ``scale``
        plus ``offset``. A vec2/vec3 property takes two or three comma-separated columns.
        Tracks override keyframes of the same property.
        """
        p = self.prop_map().get(name)
        if p is None:
            raise KeyError(f"{self.TYPE} has no property {name!r}")
        if p.kind not in ("number", "int", "vec2", "vec3"):
            raise ValueError(f"property {name!r} ({p.kind}) cannot follow a data column")
        cols = [c.strip() for c in str(column).split(",") if c.strip()]
        need = {"vec2": 2, "vec3": 3}.get(p.kind, 1)
        if len(cols) != need:
            raise ValueError(f"{name!r} needs {need} column{'s' if need > 1 else ''}, got {column!r}")
        self.tracks[name] = {"data": str(data), "column": ", ".join(cols), "time": str(time or "t"),
                             "scale": float(scale), "offset": float(offset), "time_scale": float(time_scale),
                             "time_offset": float(time_offset), "smooth": bool(smooth)}
        return self

    def untrack(self, name: str) -> SceneObject:
        self.tracks.pop(name, None)
        return self

    def track_value(self, name: str, t: float, assets) -> Any:
        """The value a data track gives at film time t (raises AssetError if the file is unusable)."""
        tr = self.tracks[name]
        p = self.prop_map()[name]
        tt = assets.column(tr["data"], tr["time"])
        tq = (float(t) - tr["time_offset"]) * tr["time_scale"]
        order = np.argsort(tt, kind="stable")
        tt = tt[order]
        out = []
        for c in tr["column"].split(","):
            col = assets.column(tr["data"], c.strip())[order]
            ok = np.isfinite(tt) & np.isfinite(col)
            if not ok.any():
                raise ValueError(f"column {c.strip()!r} of {tr['data']} has no numbers")
            if tr.get("smooth", True):
                val = float(np.interp(tq, tt[ok], col[ok]))
            else:
                i = int(np.searchsorted(tt[ok], tq, side="right")) - 1
                val = float(col[ok][min(max(i, 0), int(ok.sum()) - 1)])
            out.append(val * tr["scale"] + tr["offset"])
        if p.kind == "int":
            return int(round(out[0]))
        return out[0] if p.kind == "number" else out

    def value_at(self, name: str, t: float, color_fn=None) -> Any:
        ks = self.keys.get(name)
        if not ks:
            return self.props[name]
        p = self.prop_map()[name]
        if t <= ks[0]["t"]:
            return ks[0]["v"]
        if t >= ks[-1]["t"]:
            return ks[-1]["v"]
        for a, b in zip(ks, ks[1:]):
            if a["t"] <= t < b["t"]:
                u = ease(b.get("ease", "smooth"), (t - a["t"]) / max(b["t"] - a["t"], 1e-9), b.get("bez"))
                return _lerp(p.kind, a["v"], b["v"], u, color_fn)
        return ks[-1]["v"]

    def resolve(self, t: float, ctx: RenderContext) -> Values:
        """All property values at time t, with colours as RGB arrays and vectors as arrays."""
        out = Values()
        out["_local_t"] = float(t) - self.start
        for p in self.all_props():
            v = self.value_at(p.name, t, ctx.color)
            if p.name in self.tracks:
                try:
                    v = self.track_value(p.name, t, ctx.assets)
                except (ValueError, KeyError, OSError) as exc:
                    ctx.warn(f"{self.name}: data track of {p.label}: {exc}", p.name)
            if p.kind == "color":
                v = ctx.color(v)
            elif p.kind in ("vec2", "vec3"):
                v = np.asarray(v, np.float64)
            out[p.name] = v
        return out

    # ------------------------------------------------------------------ timing
    def appear(self, at: float | None = None, effect: str | None = None, duration: float | None = None) -> SceneObject:
        if at is not None:
            self.start = float(at)
        if effect is not None:
            self.enter_effect = effect
        if duration is not None:
            self.enter_duration = float(duration)
        return self

    def disappear(self, at: float | None = None, effect: str | None = None, duration: float | None = None) -> SceneObject:
        if at is not None:
            self.end = float(at)
        if effect is not None:
            self.exit_effect = effect
        if duration is not None:
            self.exit_duration = float(duration)
        return self

    def span(self, film_duration: float) -> tuple[float, float]:
        return self.start, film_duration if self.end is None else self.end

    def steady(self, t: float, film_duration: float) -> bool:
        """True when no enter or exit effect is running at t (the object looks the same nearby)."""
        start, end = self.span(film_duration)
        if self.enter_effect != "none" and self.enter_duration > 0 and t < start + self.enter_duration:
            return False
        if self.end is not None and self.exit_effect != "none" and self.exit_duration > 0 and t > end - self.exit_duration:
            return False
        return True

    def held(self, t: float) -> bool:
        """True when every keyframed property keeps its value around t (before the first key,
        after the last, or between two equal keys)."""
        for ks in self.keys.values():
            if not ks or t <= ks[0]["t"] or t >= ks[-1]["t"]:
                continue
            for a, b in zip(ks, ks[1:]):
                if a["t"] <= t <= b["t"]:
                    if a["v"] != b["v"]:
                        return False
                    break
        return True

    def keyed_values(self, t: float) -> dict:
        return {name: self.value_at(name, t) for name in self.keys}

    def depends_on_time(self) -> bool:
        """True when the drawing changes with time even without keyframes (particles, waves, data tracks)."""
        return self.TIME_DEPENDENT or bool(self.tracks)

    def refs(self) -> list[str]:
        """Ids of other objects this one is drawn from (a series' chart)."""
        return [self.props[p.name] for p in self.all_props() if p.kind == "ref" and self.props.get(p.name)]

    def state(self, t: float, film_duration: float) -> State | None:
        if not self.visible:
            return None
        start, end = self.span(film_duration)
        if t < start - 1e-9 or t > end + 1e-9:
            return None
        st = State(local_t=t - start)
        has_prog = self.HAS_PROGRESS or self.TEXTUAL
        if self.enter_effect != "none" and self.enter_duration > 0:
            k = ease("smooth", (t - start) / self.enter_duration)
            if self.enter_effect in ("draw", "typewriter"):
                k = ease("in_out", (t - start) / self.enter_duration)
            _apply_effect(st, self.enter_effect, k, True, has_prog)
        if self.end is not None and self.exit_effect != "none" and self.exit_duration > 0:
            k = ease("smooth", (end - t) / self.exit_duration)
            _apply_effect(st, self.exit_effect, k, False, has_prog)
        if st.opacity <= 1e-4:
            return None
        return st

    # ------------------------------------------------------------------ drawing
    def depth(self, ctx: RenderContext, v: Values) -> float:
        """Distance from the camera, for back-to-front sorting of 3D objects."""
        return 0.0

    def draw(self, cv: Canvas, ctx: RenderContext, v: Values, st: State):
        """Draw the object; return its bounding box in output pixels (x0, y0, x1, y1) or None."""
        raise NotImplementedError

    def label_anchor(self, ctx: RenderContext, v: Values) -> np.ndarray | None:
        """3D points whose projected bounding box positions the label (3D objects)."""
        return None

    # ------------------------------------------------------------------ serialisation
    def to_json(self) -> dict:
        d: dict[str, Any] = {"id": self.id, "type": self.TYPE, "name": self.name}
        defaults = {p.name: p.default for p in self.all_props()}
        d["props"] = {k: v for k, v in self.props.items() if v != defaults.get(k)}
        if self.keys:
            d["keys"] = copy.deepcopy(self.keys)
        d["start"] = self.start
        d["end"] = self.end
        d["enter"] = {"effect": self.enter_effect, "duration": self.enter_duration}
        d["exit"] = {"effect": self.exit_effect, "duration": self.exit_duration}
        if not self.visible:
            d["visible"] = False
        if self.locked:
            d["locked"] = True
        if self.parent:
            d["parent"] = self.parent
        if self.tracks:
            d["tracks"] = copy.deepcopy(self.tracks)
        if self.scene:
            d["scene"] = self.scene
        return d

    @classmethod
    def from_json(cls, d: dict) -> SceneObject:
        typ = d.get("type")
        klass = REGISTRY.get(typ)
        if klass is None:
            raise ValueError(f"unknown object type {typ!r}. Known types: {', '.join(sorted(REGISTRY))}")
        return klass(id=d.get("id"), name=d.get("name"), props=d.get("props"), keys=d.get("keys"),
                     start=d.get("start", 0.0), end=d.get("end"), enter=d.get("enter"), exit=d.get("exit"),
                     visible=d.get("visible", True), locked=d.get("locked", False), parent=d.get("parent"),
                     tracks=d.get("tracks"), scene=d.get("scene"))

    def copy(self, new_id: str | None = None) -> SceneObject:
        d = self.to_json()
        d["id"] = new_id
        return self.from_json(d)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.id!r} {self.name!r}>"


class Values:
    """Resolved property values with attribute access (``v.color``) and item access (``v["color"]``).

    Not a dict subclass on purpose: properties called ``values`` or ``items`` must not
    collide with dict methods.
    """

    __slots__ = ("_d",)

    def __init__(self) -> None:
        object.__setattr__(self, "_d", {})

    def __getattr__(self, name: str) -> Any:
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name) from None

    def __getitem__(self, name: str) -> Any:
        return self._d[name]

    def __setitem__(self, name: str, value: Any) -> None:
        self._d[name] = value

    def __contains__(self, name: str) -> bool:
        return name in self._d

    def get(self, name: str, default: Any = None) -> Any:
        return self._d.get(name, default)


def _lerp(kind: str, a: Any, b: Any, u: float, color_fn=None) -> Any:
    if kind == "number":
        return float(a) + (float(b) - float(a)) * u
    if kind == "int":
        return int(round(float(a) + (float(b) - float(a)) * u))
    if kind in ("vec2", "vec3"):
        return list(np.asarray(a, np.float64) + (np.asarray(b, np.float64) - np.asarray(a, np.float64)) * u)
    if kind == "color":
        from ..engine.color import parse_color
        fn = color_fn or parse_color
        try:
            ca, cb = np.asarray(fn(a), np.float64), np.asarray(fn(b), np.float64)
        except ValueError:
            return a if u < 1 else b
        return list(ca + (cb - ca) * u)
    return a if u < 1 else b
