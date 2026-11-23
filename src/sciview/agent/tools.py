"""The tools a language model (or any agent) uses to build a film.

Every tool takes plain JSON arguments, checks them against the object schemas, and either changes
the project or explains clearly why it did not. Locked objects are never changed, and a scope can
limit an agent to a time window or to some objects, so the user keeps control of the rest.

    >>> import sciview as sv
    >>> from sciview.agent import FilmTools
    >>> tools = FilmTools(sv.Project(duration=10))
    >>> r = tools.call("add_object", {"type": "caption", "props": {"text": "Hello"}, "start": 1})
    >>> r["id"]
    'caption1'
"""
from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np

from ..engine.easing import EASING_NAMES
from ..model.base import REGISTRY, Prop, SceneObject
from ..model.project import Project

ALIGN = ("left", "center", "right", "top", "middle", "bottom", "spread_x", "spread_y")
REGIONS = {
    "center": (0.5, 0.5), "left": (0.25, 0.5), "right": (0.75, 0.5), "top": (0.5, 0.2), "bottom": (0.5, 0.82),
    "top-left": (0.25, 0.2), "top-right": (0.75, 0.2), "bottom-left": (0.25, 0.8), "bottom-right": (0.75, 0.8),
    "left-third": (1 / 6, 0.5), "middle-third": (0.5, 0.5), "right-third": (5 / 6, 0.5),
}
RESERVED = {"type", "name", "start", "end", "enter", "exit", "parent", "id"}


class ToolError(ValueError):
    """A tool call that cannot be done as asked; the message says why and what to do instead."""


def _num(x, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
        raise ToolError(f"{what} must be a number, got {x!r}")
    return float(x)


def check_value(prop: Prop, value: Any, project: Project | None = None) -> Any:
    """Validate a value for a property strictly (no silent conversion of wrong types) and normalise it."""
    k = prop.kind
    if k in ("number", "int"):
        v = _num(value, prop.name)
        if prop.min is not None and v < prop.min or prop.max is not None and v > prop.max:
            raise ToolError(f"{prop.name} must be between {prop.min} and {prop.max}, got {v:g}")
        return int(round(v)) if k == "int" else v
    if k == "bool":
        if not isinstance(value, bool):
            raise ToolError(f"{prop.name} must be true or false, got {value!r}")
        return value
    if k in ("vec2", "vec3"):
        n = 2 if k == "vec2" else 3
        if not isinstance(value, (list, tuple)) or len(value) != n:
            raise ToolError(f"{prop.name} must be a list of {n} numbers, got {value!r}")
        return [_num(x, prop.name) for x in value]
    if k == "enum":
        if value not in prop.options:
            raise ToolError(f"{prop.name} must be one of {', '.join(map(str, prop.options))}; got {value!r}")
        return value
    if k == "color":
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return prop.coerce(value)
        if not isinstance(value, str):
            raise ToolError(f"{prop.name} must be a colour name (teal, gold ...) or #rrggbb, got {value!r}")
        from ..engine.color import parse_color
        try:
            parse_color(value, project.palette if project is not None else None)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return value
    if k == "array":
        if isinstance(value, (list, tuple)):
            return [_num(x, prop.name) for x in value]
        if isinstance(value, str):
            return value
        raise ToolError(f"{prop.name} must be a list of numbers, got {value!r}")
    if k == "ref":
        if not isinstance(value, str):
            raise ToolError(f"{prop.name} must be an object id, got {value!r}")
        if value and project is not None:
            target = project.find(value)
            if target is None:
                raise ToolError(f"{prop.name}: there is no object {value!r}")
            if prop.ref and target.TYPE != prop.ref:
                raise ToolError(f"{prop.name} must point to a {prop.ref}, but {value!r} is a {target.TYPE}")
        return value
    if not isinstance(value, str):
        raise ToolError(f"{prop.name} must be text, got {value!r}")
    if prop.expr and value.strip():
        from ..engine.mathexpr import ExpressionError, compile_expression
        names = tuple(sorted(set(prop.expr.split(",")) | {"x", "t"})) if isinstance(prop.expr, str) else ("t", "x")
        try:
            compile_expression(value, names)
        except ExpressionError as exc:
            raise ToolError(f"{prop.name}: {exc}") from None
    return value


class FilmTools:
    """Tool calls on a project. ``scope`` may hold ``{"time": [t0, t1], "ids": [...], "scene": "scene2"}``.

    Times are in the time of an object's scene (the film's time when it has one scene). ``changes``
    lists what the agent changed (object, property, value), so the person can review the values the
    model wrote itself.
    """

    def __init__(self, project: Project, scope: dict | None = None):
        self.project = project
        self.scope = dict(scope or {})
        self.changes: list[dict] = []
        if self.scope.get("scene"):
            try:
                self.project.current_scene = self.scope["scene"]
            except KeyError:
                raise ToolError(f"the scope names a scene that does not exist: {self.scope['scene']!r}") from None
            self.scope["scene"] = self.project.current_scene.id        # a name works too

    # ------------------------------------------------------------------ dispatch
    def call(self, name: str, args: dict | None = None) -> dict:
        spec = TOOLS.get(name)
        if spec is None:
            raise ToolError(f"unknown tool {name!r}. Tools: {', '.join(TOOLS)}")
        args = dict(args or {})
        schema = spec["input"]
        for req in schema.get("required", []):
            if req not in args:
                raise ToolError(f"{name} needs {req!r}")
        extra = set(args) - set(schema.get("properties", {}))
        if extra:
            raise ToolError(f"{name} does not take {', '.join(sorted(extra))}")
        return getattr(self, name)(**args)

    # ------------------------------------------------------------------ scope
    def _obj(self, oid: str, change: bool = True) -> SceneObject:
        if oid == "camera" or oid.startswith("camera@"):
            sid = oid.split("@", 1)[1] if "@" in oid else None
            try:
                obj = self.project.get_scene(sid).camera
            except KeyError:
                raise ToolError(f"there is no scene {sid!r}; describe_film lists the scenes") from None
            scene = self.project.get_scene(sid).id
        else:
            obj = self.project.find(oid)
            scene = obj.scene if obj is not None else None
        if obj is None:
            raise ToolError(f"there is no object {oid!r}; describe_film lists the ids")
        if change:
            if getattr(obj, "locked", False):
                raise ToolError(f"{oid!r} is locked by the user and must not be changed")
            ids = self.scope.get("ids")
            if ids and oid not in ids and oid not in self._created:
                raise ToolError(f"{oid!r} is outside your scope; you may change: {', '.join(ids)} and objects you add")
            if self.scope.get("scene") and scene != self.scope["scene"]:
                raise ToolError(f"{oid!r} is in another scene; you may only change scene {self.scope['scene']!r}")
        return obj

    def _scene_of(self, obj) -> Any:
        if obj.TYPE == "camera":
            return next((sc for sc in self.project.scenes if sc.camera is obj), self.project.current_scene)
        return self.project.scene_of(obj)

    @property
    def _created(self) -> set:
        return {c["id"] for c in self.changes if c.get("action") == "add"}

    def _in_time(self, t: float | None, what: str) -> None:
        win = self.scope.get("time")
        if t is None or not win:
            return
        if not (float(win[0]) - 1e-9 <= t <= float(win[1]) + 1e-9):
            raise ToolError(f"{what} at {t:g} s is outside your time window {win[0]:g}–{win[1]:g} s")

    def _log(self, **entry) -> None:
        self.changes.append(entry)

    # ------------------------------------------------------------------ reading
    def list_object_types(self) -> dict:
        return {"types": [{"type": c.TYPE, "label": c.LABEL, "category": c.CATEGORY, "is3d": c.IS_3D,
                           "description": c.DESCRIPTION} for c in REGISTRY.values()]}

    def get_schema(self, type: str) -> dict:
        klass = REGISTRY.get(type)
        if klass is None and type != "camera":
            raise ToolError(f"unknown type {type!r}; list_object_types gives them")
        if type == "camera":
            props = self.project.camera.all_props()
            return {"type": "camera", "props": [p.schema() for p in props],
                    "note": "The camera orbits its target: animate azimuth, elevation and distance."}
        sc = klass.schema()
        return {"type": type, "label": sc["label"], "description": sc["description"], "is3d": sc["is3d"],
                "effects": sc["effects"], "props": sc["props"],
                "coordinates": ("scene units, z up; the camera orbits the target" if klass.IS_3D else
                                f"pixels on a {self.project.size[0]}×{self.project.size[1]} frame, (0, 0) top-left")}

    def describe_film(self) -> dict:
        p = self.project
        objs = []
        multi = len(p.scenes) > 1
        for o in p.objects:
            defaults = {q.name: q.default for q in o.all_props()}
            d = {"id": o.id, "type": o.TYPE, "name": o.name, "start": o.start, "end": o.end,
                 "props": {k: v for k, v in o.props.items() if v != defaults.get(k)}}
            if multi:
                d["scene"] = o.scene
            if o.keys:
                d["keyframes"] = {k: [{"t": kf["t"], "v": kf["v"], "ease": kf.get("ease", "smooth")} for kf in ks]
                                  for k, ks in o.keys.items()}
            if o.parent:
                d["parent"] = o.parent
            if o.locked:
                d["locked"] = True
            if o.enter_effect != o.DEFAULT_ENTER or o.exit_effect != o.DEFAULT_EXIT:
                d["enter"], d["exit"] = o.enter_effect, o.exit_effect
            objs.append(d)
        cam = {k: v for k, v in p.camera.props.items()}
        out = {"settings": {"width": p.size[0], "height": p.size[1], "duration": p.duration, "fps": p.fps,
                            "title": p.settings.get("title", "")},
               "camera": {"props": cam, "keyframes": copy.deepcopy(p.camera.keys)},
               "objects": objs, "problems": p.problems(), "scope": self.scope or None,
               "palette": sorted(p.palette)}
        if multi:
            out["scenes"] = [{"id": sc.id, "name": sc.name, "starts_at": round(a, 3), "duration": sc.duration,
                              "transition": sc.transition, "transition_duration": sc.transition_duration,
                              "notes": sc.notes, "camera": {"id": f"camera@{sc.id}", "props": dict(sc.camera.props),
                                                            "keyframes": copy.deepcopy(sc.camera.keys)}}
                             for sc, a, _b in p.timeline()]
            out["note"] = ("Object times count from the start of their scene. 'camera' is the camera of scene "
                           f"{p.current_scene.id!r}; use camera@<scene id> for another scene's camera.")
            del out["camera"]
        return out

    def validate(self) -> dict:
        return {"problems": self.project.problems()}

    # ------------------------------------------------------------------ changing
    def _props(self, klass, props: dict) -> dict:
        pm = klass.prop_map()
        out = {}
        for k, v in (props or {}).items():
            if k in RESERVED:
                raise ToolError(f"{k!r} is set with its own argument, not inside props")
            p = pm.get(k)
            if p is None:
                raise ToolError(f"{klass.TYPE} has no property {k!r}; get_schema lists them")
            out[k] = check_value(p, v, self.project)
        return out

    def add_object(self, type: str, props: dict | None = None, name: str | None = None, start: float | None = None,
                   end: float | None = None, enter: str | None = None, exit: str | None = None,
                   parent: str | None = None, scene: str | None = None) -> dict:
        klass = REGISTRY.get(type)
        if klass is None:
            raise ToolError(f"unknown type {type!r}; list_object_types gives them")
        if scene is not None:
            try:
                scene = self.project.get_scene(scene).id
            except KeyError:
                raise ToolError(f"there is no scene {scene!r}; describe_film lists the scenes") from None
            if self.scope.get("scene") and scene != self.scope["scene"]:
                raise ToolError(f"you may only add objects to scene {self.scope['scene']!r}")
        else:
            scene = self.scope.get("scene") or self.project.current_scene.id
        if parent is not None and self.project.find(parent) is not None:
            scene = self.project.find(parent).scene or scene
        clean = self._props(klass, props or {})
        start = 0.0 if start is None else _num(start, "start")
        self._in_time(start, "the start")
        if end is not None:
            end = _num(end, "end")
            if end <= start:
                raise ToolError("end must be after start")
            self._in_time(end, "the end")
        if self.scope.get("time") and end is None:
            end = float(self.scope["time"][1])
        for eff, label in ((enter, "enter"), (exit, "exit")):
            if eff is not None and eff not in klass.effects():
                raise ToolError(f"{label} must be one of {', '.join(klass.effects())}")
        if parent is not None:
            g = self._obj(parent, change=False)
            if not g.IS_GROUP:
                raise ToolError(f"{parent!r} is not a group")
        dur = self.project.get_scene(scene).duration
        if start >= dur:
            raise ToolError(f"start {start:g} s is after the end of its scene ({dur:g} s)")
        obj = self.project.add(type, name=name, start=start, end=end, enter=enter, exit=exit, parent=parent,
                               scene=scene, **clean)
        self._log(action="add", id=obj.id, type=type, props=clean, scene=scene)
        return {"id": obj.id}

    def set_property(self, id: str, name: str, value: Any, time: float | None = None, ease: str = "smooth") -> dict:
        obj = self._obj(id)
        p = obj.prop_map().get(name)
        if p is None:
            raise ToolError(f"{obj.TYPE} has no property {name!r}; get_schema lists them")
        v = check_value(p, value, self.project)
        if time is not None:
            return self.add_keyframe(id, name, time, value, ease)
        if obj.keys.get(name):
            raise ToolError(f"{name!r} of {id!r} is animated; give a time to add a keyframe, or remove its keyframes")
        obj.set(name, v)
        self._log(action="set", id=id, prop=name, value=v)
        return {"ok": True, "value": obj.props[name]}

    def add_keyframe(self, id: str, name: str, time: float, value: Any, ease: str = "smooth") -> dict:
        obj = self._obj(id)
        p = obj.prop_map().get(name)
        if p is None:
            raise ToolError(f"{obj.TYPE} has no property {name!r}")
        if not p.animatable:
            raise ToolError(f"{name!r} cannot be animated; set it with set_property")
        t = _num(time, "time")
        dur = self._scene_of(obj).duration
        if not (0 <= t <= dur):
            raise ToolError(f"time must be within its scene (0–{dur:g} s)")
        self._in_time(t, "the keyframe")
        if ease not in EASING_NAMES or ease == "bezier":
            raise ToolError(f"ease must be one of {', '.join(e for e in EASING_NAMES if e != 'bezier')}")
        v = check_value(p, value, self.project)
        obj.key(name, t, v, ease)
        self._log(action="key", id=id, prop=name, time=t, value=v)
        return {"ok": True, "keyframes": [{"t": k["t"], "v": k["v"]} for k in obj.keys[name]]}

    def remove_keyframe(self, id: str, name: str, time: float) -> dict:
        obj = self._obj(id)
        t = _num(time, "time")
        self._in_time(t, "the keyframe")
        ks = obj.keys.get(name, [])
        keep = [k for k in ks if abs(k["t"] - t) > 1e-6]
        if len(keep) == len(ks):
            raise ToolError(f"{id!r} has no keyframe of {name!r} at {t:g} s")
        if keep:
            obj.keys[name] = keep
        else:
            obj.keys.pop(name, None)
        self._log(action="unkey", id=id, prop=name, time=t)
        return {"ok": True}

    def set_timing(self, id: str, start: float | None = None, end: float | None = None, enter: str | None = None,
                   exit: str | None = None, enter_duration: float | None = None,
                   exit_duration: float | None = None) -> dict:
        obj = self._obj(id)
        if obj.TYPE == "camera":
            raise ToolError("the camera has no timing; animate its properties instead")
        s = obj.start if start is None else _num(start, "start")
        e = obj.end if end is None else _num(end, "end")
        if e is not None and e <= s:
            raise ToolError("end must be after start")
        self._in_time(s, "the start")
        if e is not None:
            self._in_time(e, "the end")
        for eff, label in ((enter, "enter"), (exit, "exit")):
            if eff is not None and eff not in obj.effects():
                raise ToolError(f"{label} must be one of {', '.join(obj.effects())}")
        obj.start, obj.end = s, e
        if enter is not None:
            obj.enter_effect = enter
        if exit is not None:
            obj.exit_effect = exit
        if enter_duration is not None:
            obj.enter_duration = max(0.0, _num(enter_duration, "enter_duration"))
        if exit_duration is not None:
            obj.exit_duration = max(0.0, _num(exit_duration, "exit_duration"))
        self._log(action="timing", id=id, start=s, end=e)
        return {"ok": True, "start": obj.start, "end": obj.end}

    def delete(self, id: str) -> dict:
        obj = self._obj(id)
        if obj.TYPE == "camera":
            raise ToolError("the camera cannot be deleted")
        for d in self.project.descendants(obj) if obj.IS_GROUP else []:
            if d.locked:
                raise ToolError(f"{id!r} contains {d.id!r}, which is locked by the user")
        self.project.remove(obj)
        self._log(action="delete", id=id)
        return {"ok": True}

    def group(self, ids: list, name: str | None = None) -> dict:
        objs = [self._obj(i) for i in ids]
        if not objs:
            raise ToolError("give the ids to group")
        g = self.project.group(objs, name=name)
        self._log(action="add", id=g.id, type="group", props={})
        return {"id": g.id}

    def place(self, id: str, region: str, time: float | None = None) -> dict:
        """Move a 2D object to a named region of the frame, so the model need not compute pixels."""
        obj = self._obj(id)
        if obj.IS_3D:
            raise ToolError("place works on 2D objects; set a 3D object's centre in scene units")
        if region not in REGIONS:
            raise ToolError(f"region must be one of {', '.join(REGIONS)}")
        fx, fy = REGIONS[region]
        W, H = self.project.size
        target = [fx * W, fy * H]
        pm = obj.prop_map()
        name = next((n for n in ("position", "center") if n in pm and pm[n].kind == "vec2"), None)
        if name is None:
            raise ToolError(f"{obj.TYPE} has no position to set")
        if obj.TYPE in ("axes", "panel", "rect"):
            size = obj.props.get("size", [0, 0])
            target = [target[0] - size[0] / 2, target[1] - size[1] / 2]
        if time is not None:
            return self.add_keyframe(id, name, time, target)
        return self.set_property(id, name, target)

    def render_frame(self, time: float, scale: float = 0.5, scene: str | None = None) -> dict:
        """The frame at ``time`` as PNG bytes (key ``png``), plus the problems seen while drawing it.

        With ``scene``, that scene alone at its own time; otherwise the film at film time."""
        from io import BytesIO

        from PIL import Image

        from ..render import FrameInfo
        t = _num(time, "time")
        sc = min(max(_num(scale, "scale"), 0.1), 1.0)
        info = FrameInfo()
        if scene is not None:
            try:
                s_obj = self.project.get_scene(scene)
            except KeyError:
                raise ToolError(f"there is no scene {scene!r}") from None
            img = self.project.renderer().frame(min(max(t, 0.0), s_obj.duration), sc, info, scene=s_obj.id)
        else:
            img = self.project.renderer().frame(min(max(t, 0.0), self.project.duration), sc, info)
        buf = BytesIO()
        Image.fromarray(np.asarray(img)).save(buf, "PNG")
        return {"png": buf.getvalue(), "issues": info.issues,
                "objects_visible": [b["id"] for b in info.boxes if not b.get("group")]}

    def check_frames(self) -> dict:
        """Look at frames for text that overlaps text, objects reaching outside the frame and text that is hard
        to read against what is behind it."""
        from .. import checks
        return {"layout": checks.layout_issues(self.project), "contrast": checks.contrast_issues(self.project, 0.35)}

    def align(self, ids: list, how: str) -> dict:
        """Line 2D objects up (left, center, right, top, middle, bottom) or space them evenly (spread_x, spread_y)."""
        if how not in ALIGN:
            raise ToolError(f"how must be one of {', '.join(ALIGN)}")
        objs = [self._obj(i) for i in ids]
        if len(objs) < 2:
            raise ToolError("give two or more ids")
        if any(o.IS_3D for o in objs):
            raise ToolError("align works on 2D objects")
        names = []
        for o in objs:
            n = next((x for x in ("position", "center") if x in o.prop_map() and o.prop_map()[x].kind == "vec2"), None)
            if n is None:
                raise ToolError(f"{o.id!r} has no position")
            if o.keys.get(n):
                raise ToolError(f"{o.id!r} moves (its {n} is animated); align its keyframes one by one")
            names.append(n)
        pts = [list(map(float, o.props[n])) for o, n in zip(objs, names)]
        axis = 0 if how in ("left", "center", "right", "spread_x") else 1
        vals = [p[axis] for p in pts]
        if how.startswith("spread"):
            order = sorted(range(len(objs)), key=lambda i: vals[i])
            lo, hi = vals[order[0]], vals[order[-1]]
            for k, i in enumerate(order):
                pts[i][axis] = lo + (hi - lo) * k / (len(order) - 1)
        else:
            target = {"left": min, "top": min, "right": max, "bottom": max}.get(how, lambda v: sum(v) / len(v))(vals)
            for p in pts:
                p[axis] = target
        for o, n, p in zip(objs, names, pts):
            o.set(n, p)
            self._log(action="set", id=o.id, prop=n, value=p, layout=True)
        return {"ok": True, "positions": {o.id: p for o, p in zip(objs, pts)}}

    def add_scene(self, name: str, duration: float, transition: str = "crossfade", transition_duration: float = 0.8,
                  after: str | None = None, template: str | None = None, notes: str = "") -> dict:
        """A new scene (after the last one, or after ``after``). ``template`` fills it from a template."""
        if self.scope.get("scene") or self.scope.get("ids") or self.scope.get("time"):
            raise ToolError("your scope does not allow adding scenes")
        from ..engine.transitions import TRANSITIONS
        if transition not in TRANSITIONS:
            raise ToolError(f"transition must be one of {', '.join(TRANSITIONS)}")
        d = _num(duration, "duration")
        if not 0.5 <= d <= 3600:
            raise ToolError("duration must be between 0.5 and 3600 seconds")
        try:
            sc = self.project.add_scene(name, d, transition=transition,
                                        transition_duration=_num(transition_duration, "transition_duration"),
                                        after=after, notes=notes)
        except KeyError:
            raise ToolError(f"there is no scene {after!r}") from None
        made = []
        if template:
            from ..server import instantiate_template
            try:
                tp = instantiate_template(template, self.project.base_dir)
            except ValueError as exc:
                raise ToolError(str(exc)) from None
            sc.duration = max(d, tp.duration)
            sc.camera = tp.scenes[0].camera
            remap = {}
            for o in tp.objects:
                new_id = self.project._unique_id(o.TYPE)
                remap[o.id] = new_id
            for o in tp.objects:
                c = o.copy(remap[o.id])
                c.scene = sc.id
                if c.parent:
                    c.parent = remap.get(c.parent)
                for p in c.all_props():
                    if p.kind == "ref" and c.props.get(p.name) in remap:
                        c.props[p.name] = remap[c.props[p.name]]
                self.project.objects.append(c)
                made.append(c.id)
        self._log(action="add_scene", id=sc.id, name=sc.name)
        for oid in made:
            self._log(action="add", id=oid, type=self.project.find(oid).TYPE, props={}, scene=sc.id, template=True)
        return {"id": sc.id, "starts_at": round(sc.start, 3), "objects": made}

    def set_scene(self, scene: str, name: str | None = None, duration: float | None = None,
                  transition: str | None = None, transition_duration: float | None = None, notes: str | None = None,
                  chapter: bool | None = None) -> dict:
        """Change a scene: its name, length, how it comes in, its notes and whether it is a chapter."""
        try:
            sc = self.project.get_scene(scene)
        except KeyError:
            raise ToolError(f"there is no scene {scene!r}; describe_film lists them") from None
        if self.scope.get("scene") and sc.id != self.scope["scene"]:
            raise ToolError(f"you may only change scene {self.scope['scene']!r}")
        if self.scope.get("ids") or self.scope.get("time"):
            raise ToolError("your scope does not allow changing scenes")
        if duration is not None:
            d = _num(duration, "duration")
            if not 0.5 <= d <= 3600:
                raise ToolError("duration must be between 0.5 and 3600 seconds")
            sc.duration = d
        if transition is not None:
            try:
                sc.set_transition(transition)
            except ValueError as exc:
                raise ToolError(str(exc)) from None
        if transition_duration is not None:
            sc.transition_duration = max(0.0, _num(transition_duration, "transition_duration"))
        if name:
            sc.name = str(name)
        if notes is not None:
            sc.notes = str(notes)
        if chapter is not None:
            sc.chapter = bool(chapter)
        self._log(action="scene", id=sc.id, duration=sc.duration, transition=sc.transition)
        return {"ok": True, "starts_at": round(sc.start, 3), "film_duration": self.project.duration}

    def review(self) -> dict:
        """What the agent changed in this session: values the person should check."""
        return {"changes": self.changes}


def _schema(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


_ID = {"type": "string", "description": "Object id from describe_film (or 'camera')"}
_ANY = {"description": "Value of the right kind: number, true/false, [x, y], [x, y, z], text, colour name or #rrggbb"}
TOOLS: dict[str, dict] = {
    "list_object_types": {"description": "List every object type SciView can add, with what it is for.",
                          "input": _schema({})},
    "get_schema": {"description": "The properties of one object type (or 'camera'): kinds, defaults, ranges, choices "
                                  "and help. Read it before adding or changing an object of that type.",
                   "input": _schema({"type": {"type": "string"}}, ["type"])},
    "describe_film": {"description": "The film as it is now: settings, camera, every object with its non-default "
                                     "properties, keyframes and timing, the problems found, and your scope.",
                      "input": _schema({})},
    "add_object": {"description": "Add an object. props uses the names from get_schema. Times are in seconds. "
                                  "2D positions are pixels on the frame; 3D positions are scene units.",
                   "input": _schema({"type": {"type": "string"}, "props": {"type": "object"},
                                     "name": {"type": "string"}, "start": {"type": "number"},
                                     "end": {"type": "number"}, "enter": {"type": "string"},
                                     "exit": {"type": "string"}, "parent": {"type": "string"},
                                     "scene": {"type": "string", "description": "Scene id or name (default: "
                                               "the current scene)"}}, ["type"])},
    "set_property": {"description": "Set one property. With a time, adds a keyframe instead (the property animates).",
                     "input": _schema({"id": _ID, "name": {"type": "string"}, "value": _ANY,
                                       "time": {"type": "number"}, "ease": {"type": "string"}}, ["id", "name", "value"])},
    "add_keyframe": {"description": "Animate a property: its value at a time. Eases: smooth, linear, in, out, in_out, "
                                    "overshoot, sine, smoother, hold.",
                     "input": _schema({"id": _ID, "name": {"type": "string"}, "time": {"type": "number"},
                                       "value": _ANY, "ease": {"type": "string"}}, ["id", "name", "time", "value"])},
    "remove_keyframe": {"description": "Remove the keyframe of a property at a time.",
                        "input": _schema({"id": _ID, "name": {"type": "string"}, "time": {"type": "number"}},
                                         ["id", "name", "time"])},
    "set_timing": {"description": "When an object appears and disappears (seconds; end null = until the film ends), "
                                  "and its enter/exit effects.",
                   "input": _schema({"id": _ID, "start": {"type": "number"}, "end": {"type": ["number", "null"]},
                                     "enter": {"type": "string"}, "exit": {"type": "string"},
                                     "enter_duration": {"type": "number"}, "exit_duration": {"type": "number"}}, ["id"])},
    "delete": {"description": "Delete an object (a group goes with its members).",
               "input": _schema({"id": _ID}, ["id"])},
    "group": {"description": "Put objects in a group so they move, fade and time together.",
              "input": _schema({"ids": {"type": "array", "items": {"type": "string"}}, "name": {"type": "string"}},
                               ["ids"])},
    "place": {"description": "Move a 2D object to a region of the frame: " + ", ".join(REGIONS) + ".",
              "input": _schema({"id": _ID, "region": {"type": "string", "enum": list(REGIONS)},
                                "time": {"type": "number"}}, ["id", "region"])},
    "render_frame": {"description": "Look at the film: the picture at a time (seconds), and any drawing problems. "
                                    "With scene, that scene alone at its own time.",
                     "input": _schema({"time": {"type": "number"}, "scale": {"type": "number"},
                                       "scene": {"type": "string"}}, ["time"])},
    "check_frames": {"description": "Look at frames for text overlapping text, objects outside the frame, and text "
                                    "that is hard to read against what is behind it. Use it after building a layout.",
                     "input": _schema({})},
    "align": {"description": "Line up 2D objects (left, center, right, top, middle, bottom) or space them evenly "
                             "(spread_x, spread_y).",
              "input": _schema({"ids": {"type": "array", "items": {"type": "string"}},
                                "how": {"type": "string", "enum": list(ALIGN)}}, ["ids", "how"])},
    "add_scene": {"description": "Add a scene to the film (a part with its own objects, camera and clock). template "
                                 "fills it from a template (tomography, optics, neutron_imaging, data_story, clusters, "
                                 "waves, lattice, title_card).",
                  "input": _schema({"name": {"type": "string"}, "duration": {"type": "number"},
                                    "transition": {"type": "string"}, "transition_duration": {"type": "number"},
                                    "after": {"type": "string"}, "template": {"type": "string"},
                                    "notes": {"type": "string"}}, ["name", "duration"])},
    "set_scene": {"description": "Change a scene: name, duration, transition into it (cut, crossfade, dip, wipe_left, "
                                 "wipe_right, wipe_up, wipe_down, push_left, push_right, push_up, push_down, zoom), "
                                 "its notes (speaker notes) and whether it is a chapter.",
                  "input": _schema({"scene": {"type": "string"}, "name": {"type": "string"},
                                    "duration": {"type": "number"}, "transition": {"type": "string"},
                                    "transition_duration": {"type": "number"}, "notes": {"type": "string"},
                                    "chapter": {"type": "boolean"}}, ["scene"])},
    "validate": {"description": "Problems in the film: missing files, unreadable expressions, broken references.",
                 "input": _schema({})},
    "review": {"description": "Everything you changed in this session, for the person to check.",
               "input": _schema({})},
}
MUTATING = {"add_object", "set_property", "add_keyframe", "remove_keyframe", "set_timing", "delete", "group", "place",
            "align", "add_scene", "set_scene"}
