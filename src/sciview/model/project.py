"""A project: film settings, palette, camera and the list of objects. Saved as JSON."""
from __future__ import annotations

import copy
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np

from ..engine.assets import AssetStore, is_sequence
from ..engine.camera import Camera
from ..engine.color import DEFAULT_PALETTE, LIGHT_PALETTE
from ..engine.text import FAMILIES, plain_text
from ..engine.transitions import TRANSITIONS
from .base import REGISTRY, MissingObject, Prop, SceneObject
from .migrate import FORMAT_VERSION, compatibility, migrate
from .scene import Scene, SceneView, camera_json

PROJECT_FIELDS = frozenset({"sciview", "settings", "palette", "camera", "objects", "scenes", "styles"})

SETTINGS_PROPS: list[Prop] = [
    Prop("title", "text", "Untitled film", group="Film"),
    Prop("author", "text", "", group="Film"),
    Prop("width", "int", 1920, min=16, max=7680, group="Film", help="Pixels. Layout is in these units"),
    Prop("height", "int", 1080, min=16, max=4320, group="Film"),
    Prop("fps", "int", 30, label="Frames per second", min=1, max=120, group="Film"),
    Prop("duration", "number", 10.0, min=0.1, max=3600, step=0.1, group="Film",
         help="Seconds. With several scenes this is their total; set the length of each scene instead"),
    Prop("background", "color", "#03070e", group="Look", help="Edge colour"),
    Prop("background2", "color", "#111a2c", label="Background 2", group="Look",
         help="Centre (radial) or bottom (vertical) colour"),
    Prop("background_style", "enum", "radial", options=("radial", "vertical", "solid"), group="Look"),
    Prop("stars", "number", 0.4, min=0, max=3, step=0.05, group="Look", help="Starfield density (0 = none)"),
    Prop("vignette", "number", 0.35, min=0, max=1, step=0.05, group="Look"),
    Prop("bloom", "number", 0.7, min=0, max=3, step=0.05, group="Look", help="Strength of the glow"),
    Prop("font", "font", "Poppins", group="Look", help="Poppins, Inter, or a path to a .ttf/.otf file"),
    Prop("theme", "text", "", group="Look", help="Name of the theme last applied"),
    Prop("logo", "asset", "", accept="image", group="Logo", help="Shown on top of the film (PNG with transparency)"),
    Prop("logo_position", "enum", "bottom-right", options=("top-left", "top-right", "bottom-left", "bottom-right"),
         group="Logo"),
    Prop("logo_size", "number", 160.0, min=8, max=1920, step=1, group="Logo", help="Width in pixels"),
    Prop("logo_margin", "number", 40.0, min=0, max=500, step=1, group="Logo"),
    Prop("logo_opacity", "number", 0.9, min=0, max=1, step=0.05, group="Logo"),
    Prop("logo_scenes", "enum", "all", options=("all", "first", "last", "first_and_last"), group="Logo",
         help="Which scenes show the logo"),
    Prop("audio", "asset", "", accept="audio", group="Sound", help="Narration or music mixed into the export"),
    Prop("audio_offset", "number", 0.0, step=0.1, group="Sound", help="Seconds into the film where the audio starts"),
    Prop("audio_volume", "number", 1.0, min=0, max=4, step=0.05, group="Sound"),
    Prop("crop_x", "number", -1.0, min=-1, step=1, label="Crop centre", group="Export",
         help="Horizontal centre of square and vertical exports, in pixels (-1 = the middle)"),
]
SETTINGS_MAP = {p.name: p for p in SETTINGS_PROPS}


class CameraRig(SceneObject):
    """The scene camera. It orbits ``target``; animate azimuth/elevation/distance for camera moves."""

    TYPE, LABEL, ICON, CATEGORY = "camera", "Camera", "camera", "Camera"
    DEFAULT_ENTER = DEFAULT_EXIT = "none"
    PROPS = [
        Prop("target", "vec3", [0, 0, 0], group="Camera", help="Point the camera looks at"),
        Prop("distance", "number", 150.0, min=0.1, step=1, group="Camera"),
        Prop("azimuth", "number", -60.0, min=-720, max=720, step=1, group="Camera", help="Degrees around the vertical axis"),
        Prop("elevation", "number", 22.0, min=-89, max=89, step=1, group="Camera", help="Degrees above the floor"),
        Prop("fov", "number", 30.0, min=1, max=150, step=0.5, group="Camera", help="Field of view in degrees"),
        Prop("offset", "vec2", [0, 0], group="Camera", help="Shift the 3D scene on screen, in pixels"),
    ]

    @classmethod
    def all_props(cls):
        return list(cls.PROPS)


def _exists(p: Path) -> bool:
    """Path.exists that says False for names the system cannot even look up (too long, bad characters)."""
    try:
        return p.exists()
    except (OSError, ValueError):
        return False


def _short(text, n: int = 120) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def _camera(cam: dict, proj=None) -> CameraRig:
    """A camera from its JSON; damaged parts are reported on ``proj`` and replaced by defaults."""
    def d(v):
        return v if isinstance(v, dict) else None
    try:
        return CameraRig(id="camera", name="Camera", props=d(cam.get("props")), keys=d(cam.get("keys")),
                         tracks=d(cam.get("tracks")))
    except (TypeError, ValueError, AttributeError, KeyError, IndexError) as exc:
        if proj is not None:
            proj.warnings.append(f"the camera could not be read ({exc}); using the default camera")
        return CameraRig(id="camera", name="Camera")


class Project:
    """A SciView film.

    >>> import sciview as sv
    >>> p = sv.Project(duration=6)
    >>> box = p.add("box", name="Source", center=(-40, 0, 0), edge_color="gold")
    >>> box.appear(at=0.5, effect="fade", duration=1.0)  # doctest: +ELLIPSIS
    <Box ...>
    >>> p.camera.key("azimuth", 0, -70).key("azimuth", 6, -40)  # doctest: +ELLIPSIS
    <CameraRig ...>
    """

    def __init__(self, path: str | os.PathLike | None = None, palette: dict | None = None, **settings):
        self.settings: dict[str, Any] = {p.name: copy.deepcopy(p.default) for p in SETTINGS_PROPS}
        self.palette: dict[str, str] = dict(palette or DEFAULT_PALETTE)
        self.scenes: list[Scene] = [Scene("scene1", "Scene 1", float(self.settings["duration"]), project=self)]
        self._current = "scene1"
        self.styles: dict[str, dict] = {}          # default properties per object type (from a theme)
        self.objects: list[SceneObject] = []
        self.path: Path | None = Path(path) if path else None
        self.warnings: list[str] = []
        self.notes: list[str] = []                  # what happened when the file was opened (conversions)
        self.extra: dict[str, Any] = {}             # top-level parts of the file this version does not know
        self.extra_settings: dict[str, Any] = {}    # settings this version does not know (kept, not used)
        self._renderer = None
        self._check_assets = None
        for k, v in settings.items():
            self.set(k, v)

    # ------------------------------------------------------------------ settings
    def set(self, name: str, value: Any) -> Project:
        p = SETTINGS_MAP.get(name)
        if p is None:
            raise KeyError(f"unknown setting {name!r}. Settings: {', '.join(SETTINGS_MAP)}")
        value = p.coerce(value)
        if name == "duration":
            # one scene: its length; several: the last one takes up the difference
            last = self.scenes[-1]
            last.duration = max(0.1, last.duration + float(value) - self.duration)
            value = self.duration
        self.settings[name] = value
        return self

    @property
    def duration(self) -> float:
        """Length of the film: the scenes one after the other, minus where transitions overlap."""
        total = self.scene_start(self.scenes[-1]) + self.scenes[-1].duration
        self.settings["duration"] = total
        return total

    @property
    def fps(self) -> int:
        return int(self.settings["fps"])

    @property
    def size(self) -> tuple[int, int]:
        return int(self.settings["width"]), int(self.settings["height"])

    @property
    def base_dir(self) -> Path:
        return self.path.parent if self.path else Path.cwd()

    def use_light_theme(self) -> Project:
        """White background and darker palette, for figures in papers and posters."""
        self.palette = dict(LIGHT_PALETTE)
        self.settings.update(background="#ffffff", background2="#f4f6fa", background_style="vertical",
                             stars=0.0, vignette=0.0, bloom=0.15)
        return self

    def apply_theme(self, theme, restyle: bool = True) -> list[str]:
        """Apply a theme: a built-in name (``"dark"``, ``"light"``, ``"contrast"``), a ``.sciview-theme.json``
        file or a dict. Returns notes about anything it could not use. See :mod:`sciview.theme`."""
        from .. import theme as th
        return th.apply(self, theme, restyle)

    def save_theme(self, path, name: str = "", description: str = "") -> Path:
        """Save this film's look (palette, background, font, logo, styles) as a shareable theme file."""
        from .. import theme as th
        return th.save(self, path, name, description)

    # ------------------------------------------------------------------ scenes
    @property
    def current_scene(self) -> Scene:
        """The scene that :meth:`add` and :attr:`camera` refer to: the last one added, unless set."""
        for sc in self.scenes:
            if sc.id == self._current:
                return sc
        self._current = self.scenes[-1].id
        return self.scenes[-1]

    @current_scene.setter
    def current_scene(self, scene: Scene | str) -> None:
        self._current = self.get_scene(scene).id

    @property
    def camera(self) -> CameraRig:
        """The camera of the current scene (with one scene: the camera)."""
        return self.current_scene.camera

    @camera.setter
    def camera(self, rig: CameraRig) -> None:
        self.current_scene.camera = rig

    def get_scene(self, scene: Scene | str | int | None) -> Scene:
        """A scene by object, id, name or position; None gives the current scene."""
        if scene is None:
            return self.current_scene
        if isinstance(scene, Scene):
            if scene not in self.scenes:
                raise KeyError(f"scene {scene.name!r} is not part of this film")
            return scene
        if isinstance(scene, int):
            return self.scenes[scene]
        for sc in self.scenes:
            if sc.id == scene:
                return sc
        for sc in self.scenes:
            if sc.name == scene:
                return sc
        raise KeyError(f"no scene {scene!r}. Scenes: {', '.join(sc.name for sc in self.scenes)}")

    def add_scene(self, name: str | None = None, duration: float = 10.0, *, transition: str = "cut",
                  transition_duration: float = 1.0, after: Scene | str | None = None, chapter: bool = True,
                  notes: str = "", id: str | None = None) -> Scene:
        """Add a scene (after the last one, or after ``after``) and make it the current scene.

        Its camera starts where the camera of the scene before it ends.
        """
        used = {sc.id for sc in self.scenes}
        i = len(self.scenes) + 1
        while f"scene{i}" in used:
            i += 1
        sid = id or f"scene{i}"
        if sid in used:
            raise ValueError(f"there is already a scene {sid!r}")
        idx = len(self.scenes) if after is None else self.scenes.index(self.get_scene(after)) + 1
        prev = self.scenes[idx - 1]
        cam = CameraRig(id="camera", name="Camera")
        for k in cam.props:
            cam.props[k] = copy.deepcopy(prev.camera.value_at(k, prev.duration))
        sc = Scene(sid, name or f"Scene {idx + 1}", duration, transition, transition_duration, chapter, notes,
                   cam, project=self)
        self.scenes.insert(idx, sc)
        self._current = sc.id
        return sc

    def remove_scene(self, scene: Scene | str) -> None:
        """Remove a scene and everything in it."""
        sc = self.get_scene(scene)
        if len(self.scenes) == 1:
            raise ValueError("a film needs at least one scene")
        self.objects = [o for o in self.objects if o.scene != sc.id]
        self.scenes.remove(sc)
        if self._current == sc.id:
            self._current = self.scenes[-1].id

    def move_scene(self, scene: Scene | str, index: int) -> None:
        sc = self.get_scene(scene)
        self.scenes.remove(sc)
        self.scenes.insert(max(0, min(len(self.scenes), int(index))), sc)

    def overlap(self, scene: Scene) -> float:
        """Seconds that ``scene``'s transition overlaps the scene before it (0 for a cut or the first scene)."""
        i = self.scenes.index(scene)
        if i == 0 or scene.transition == "cut":
            return 0.0
        prev = self.scenes[i - 1]
        return max(0.0, min(scene.transition_duration, prev.duration * 0.95, scene.duration * 0.95))

    def scene_start(self, scene: Scene | str) -> float:
        """Film time at which ``scene`` starts (its transition begins)."""
        sc = self.get_scene(scene)
        t = 0.0
        for x in self.scenes:
            if x is sc:
                return t - self.overlap(x)
            t += x.duration - self.overlap(x)
        raise KeyError(sc.id)  # pragma: no cover

    def timeline(self) -> list[tuple[Scene, float, float]]:
        """(scene, start, end) in film time, in order."""
        out = []
        t = 0.0
        for sc in self.scenes:
            t -= self.overlap(sc)
            out.append((sc, t, t + sc.duration))
            t += sc.duration
        return out

    def scenes_at(self, t: float) -> list[tuple[Scene, float]]:
        """The scene (or, during a transition, the two scenes) showing at film time ``t``, with their own
        times. The last one listed is the one coming in."""
        line = self.timeline()
        out = [(sc, t - a) for sc, a, b in line if a <= t < b]
        if not out:                                     # before the start or at the very end
            sc, a, b = line[0] if t < line[0][1] else line[-1]
            out = [(sc, min(max(t - a, 0.0), sc.duration))]
        return out[-2:]

    def scene_of(self, obj: SceneObject | str) -> Scene:
        o = self.find(obj) if isinstance(obj, str) else obj
        if o is None:
            raise KeyError(obj)
        return self.get_scene(o.scene) if o.scene else self.scenes[0]

    def film_time(self, obj: SceneObject, t: float) -> float:
        """Film time of the instant ``t`` of ``obj``'s scene."""
        return self.scene_start(self.scene_of(obj)) + t

    def view(self, scene: Scene | str | None = None) -> SceneView:
        return SceneView(self, self.get_scene(scene))

    def chapters(self) -> list[tuple[float, float, str]]:
        """(start, end, title) of every scene marked as a chapter, in film time."""
        line = self.timeline()
        out = []
        for sc, a, _b in line:
            if not sc.chapter:
                continue
            # the chapter starts halfway through its transition and runs to the next chapter
            start = a + self.overlap(sc) / 2
            out.append([start, None, sc.name])
        total = self.duration
        for i, ch in enumerate(out):
            ch[1] = out[i + 1][0] if i + 1 < len(out) else total
        return [tuple(c) for c in out]

    # ------------------------------------------------------------------ objects
    def _unique_id(self, base: str) -> str:
        used = {o.id for o in self.objects} | {"camera"}
        base = re.sub(r"[^A-Za-z0-9_]+", "_", base) or "obj"
        i = 1
        while f"{base}{i}" in used:
            i += 1
        return f"{base}{i}"

    def add(self, type: str | SceneObject, name: str | None = None, *, start: float | None = None,
            end: float | None = None, enter: str | None = None, exit: str | None = None,
            id: str | None = None, parent: str | SceneObject | None = None, scene: Scene | str | None = None,
            **props) -> SceneObject:
        """Add an object by type name (``"box"``, ``"curve"`` ...) or instance; returns it.

        ``parent`` puts it in a group (the group object or its id). ``scene`` chooses the scene
        (default: the current scene, normally the last one added); times count from its start.
        """
        if isinstance(type, SceneObject):
            obj = type
            if any(o.id == obj.id for o in self.objects):
                obj.id = self._unique_id(obj.TYPE)
        else:
            klass = REGISTRY.get(type)
            if klass is None:
                raise ValueError(f"unknown object type {type!r}. Types: {', '.join(sorted(REGISTRY))}")
            obj = klass(id=id or self._unique_id(type), name=name)
            for k, v in self.styles.get(type, {}).items():
                if k not in props:
                    obj.set(k, v, strict=False)
            for k, v in props.items():
                if isinstance(v, SceneObject):  # allow axes=<Axes object>
                    v = v.id
                obj.set(k, v)
            if klass.DEFAULT_DURATION and end is None and start is not None:
                end = start + klass.DEFAULT_DURATION
        if start is not None:
            obj.start = float(start)
        if end is not None:
            obj.end = float(end)
        if enter is not None:
            obj.enter_effect = enter
        if exit is not None:
            obj.exit_effect = exit
        if parent is not None:
            obj.parent = parent.id if isinstance(parent, SceneObject) else str(parent)
            g = self.find(obj.parent)
            if g is not None and scene is None:
                scene = g.scene or self.scenes[0].id       # a group's members live in its scene
        if scene is not None or not obj.scene or obj.scene not in {sc.id for sc in self.scenes}:
            obj.scene = self.get_scene(scene).id
        self.objects.append(obj)
        return obj

    def find(self, ref: str) -> SceneObject | None:
        if ref == "camera":
            return self.camera
        for o in self.objects:
            if o.id == ref:
                return o
        return None

    def __getitem__(self, ref: str) -> SceneObject:
        obj = self.find(ref)
        if obj is None:
            raise KeyError(ref)
        return obj

    def remove(self, ref: str | SceneObject, members: bool = True) -> None:
        """Remove an object. Removing a group also removes its members, unless ``members=False``
        (then they move up to the group's own parent)."""
        rid = ref.id if isinstance(ref, SceneObject) else ref
        obj = self.find(rid)
        gone = {rid}
        if obj is not None and obj.IS_GROUP:
            if members:
                gone |= {o.id for o in self.descendants(rid)}
            else:
                for o in self.children(rid):
                    o.parent = obj.parent
        self.objects = [o for o in self.objects if o.id not in gone]

    # ------------------------------------------------------------------ groups
    def children(self, group: str | SceneObject) -> list[SceneObject]:
        gid = group.id if isinstance(group, SceneObject) else group
        return [o for o in self.objects if o.parent == gid]

    def descendants(self, group: str | SceneObject) -> list[SceneObject]:
        gid = group.id if isinstance(group, SceneObject) else group
        out, todo, seen = [], [gid], {gid}
        while todo:
            g = todo.pop()
            for o in self.objects:
                if o.parent == g and o.id not in seen:
                    seen.add(o.id)
                    out.append(o)
                    if o.IS_GROUP:
                        todo.append(o.id)
        return out

    def ancestors(self, obj: str | SceneObject) -> list[SceneObject]:
        """Groups that contain ``obj``, nearest first. Broken or circular chains stop safely."""
        o = self.find(obj) if isinstance(obj, str) else obj
        out: list[SceneObject] = []
        seen = {o.id} if o is not None else set()
        while o is not None and o.parent:
            g = self.find(o.parent)
            if g is None or not g.IS_GROUP or g.id in seen:
                break
            seen.add(g.id)
            out.append(g)
            o = g
        return out

    def group(self, objects, name: str | None = None, **props) -> SceneObject:
        """Put ``objects`` (objects or ids) in a new group and return it.

        The members become neighbours in the drawing order, at the place of the top-most one.
        """
        members = [o if isinstance(o, SceneObject) else self[o] for o in objects]
        if not members:
            raise ValueError("group() needs at least one object")
        scenes = {m.scene for m in members}
        if len(scenes) > 1:
            raise ValueError("a group can only hold objects of one scene")
        ids = {m.id for m in members}
        parents = {m.parent for m in members}
        g = self.add("group", name=name or "Group", scene=scenes.pop(), **props)
        g.parent = parents.pop() if len(parents) == 1 else None
        if g.parent in ids:
            g.parent = None
        top = max(i for i, o in enumerate(self.objects) if o.id in ids)
        before = sum(1 for o in self.objects[:top] if o.id not in ids)
        rest = [o for o in self.objects if o.id not in ids and o is not g]
        ordered = [o for o in self.objects if o.id in ids]
        self.objects = rest[:before] + ordered + [g] + rest[before:]
        for m in members:
            m.parent = g.id
        return g

    def ungroup(self, group: str | SceneObject) -> list[SceneObject]:
        """Dissolve a group; its members keep their place and move up one level."""
        g = group if isinstance(group, SceneObject) else self[group]
        kids = self.children(g.id)
        self.remove(g, members=False)
        return kids

    def of_type(self, *types: str) -> list[SceneObject]:
        return [o for o in self.objects if o.TYPE in types]

    # ------------------------------------------------------------------ camera
    def camera_at(self, t: float, width: int, height: int, scale: float = 1.0, assets=None,
                  rig: CameraRig | None = None) -> Camera:
        """The camera of the current scene (or ``rig``) at the scene time ``t``."""
        c = rig or self.camera

        def val(name):
            if assets is not None and name in c.tracks:
                try:
                    return c.track_value(name, t, assets)
                except (ValueError, KeyError, OSError):
                    pass                          # reported by problems(); fall back to the keyframes
            return c.value_at(name, t)

        off = np.asarray(val("offset"), np.float64) * scale
        return Camera.orbit(np.asarray(val("target"), np.float64), float(val("distance")),
                            float(val("azimuth")), float(val("elevation")),
                            float(val("fov")), width, height, (float(off[0]), float(off[1])))

    # ------------------------------------------------------------------ rendering
    def renderer(self):
        from ..render import Renderer
        if self._renderer is None or self._renderer.project is not self:
            self._renderer = Renderer(self)
        return self._renderer

    def frame(self, t: float, scale: float = 1.0) -> np.ndarray:
        """Render one frame as a (h, w, 3) uint8 RGB array."""
        return self.renderer().frame(t, scale)

    def still(self, t: float, path: str | os.PathLike, scale: float = 1.0) -> Path:
        """Save one frame as PNG/JPG."""
        from PIL import Image
        img = self.frame(t, scale)
        Image.fromarray(img).save(path)
        return Path(path)

    def preview(self, fps: float = 10.0, scale: float = 0.25, start: float = 0.0, end: float | None = None,
                scene=None):
        """A preview to scrub through in a Jupyter notebook (see :func:`sciview.jupyter.preview`)."""
        from ..jupyter import preview
        return preview(self, fps=fps, scale=scale, start=start, end=end, scene=scene)

    def render(self, output: str | os.PathLike, **options) -> Path:
        """Render the film. See :func:`sciview.export.export` for options (fps, scale, crf, workers ...)."""
        from ..export import export
        return export(self, output, **options)

    # ------------------------------------------------------------------ captions
    def captions(self, scene: Scene | str | None = None) -> list[tuple[float, float, str]]:
        """(start, end, text) of every caption in film time, in order; with ``scene``, that scene's
        captions in its own time."""
        out = []
        only = self.get_scene(scene) if scene is not None else None
        for sc, a, _b in self.timeline():
            if only is not None:
                if sc is not only:
                    continue
                a = 0.0
            for o in self.objects:
                if o.TYPE == "caption" and o.visible and o.scene == sc.id:
                    s, e = o.span(sc.duration)
                    e = min(e, sc.duration)
                    if e > s:
                        out.append((a + s, a + e, plain_text(o.get("text"))))
        return sorted(out)

    def captions_srt(self) -> str:
        def ts(x: float) -> str:
            ms = int(round(x * 1000))
            h, ms = divmod(ms, 3600000)
            m, ms = divmod(ms, 60000)
            s, ms = divmod(ms, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        blocks = [f"{i}\n{ts(s)} --> {ts(e)}\n{text}\n" for i, (s, e, text) in enumerate(self.captions(), 1)]
        return "\n".join(blocks)

    # ------------------------------------------------------------------ checks
    def validate(self) -> list[str]:
        """Problems a user should fix: missing files, dangling chart references, bad expressions."""
        return [p["message"] for p in self.problems()]

    def problems(self) -> list[dict]:
        """Like :meth:`validate`, as dicts ``{"id", "prop", "message"}`` so the editor can point at the field."""
        from ..engine.mathexpr import ExpressionError, compile_expression
        out: list[dict] = []

        def add(msg: str, obj: SceneObject | None = None, prop: str | None = None) -> None:
            out.append({"id": obj.id if obj is not None else None, "prop": prop, "message": msg})

        for w in self.warnings:
            add(w)
        if self._check_assets is None:
            self._check_assets = AssetStore(self.base_dir)
        track_assets = self._check_assets              # reused between checks; keyed by file stamps
        track_assets.base_dir = self.base_dir
        ids = {o.id for o in self.objects}
        for o in self.objects:
            for w in o.warnings:
                add(w, o)
            if o.parent:
                g = self.find(o.parent)
                if g is None:
                    add(f"{o.name}: its group {o.parent!r} does not exist", o, "parent")
                elif not g.IS_GROUP:
                    add(f"{o.name}: {g.name} is not a group", o, "parent")
                elif o.parent == o.id or (o.IS_GROUP and any(a.id == o.id for a in self.ancestors(g))):
                    add(f"{o.name}: groups inside each other in a circle", o, "parent")
            for p in o.all_props():
                val = o.props.get(p.name)
                if p.kind == "asset" and val:
                    if is_sequence(val):
                        if not track_assets.sequence(val):
                            add(f"{o.name}: no files match {val}", o, p.name)
                    else:
                        f = Path(val) if Path(val).is_absolute() else self.base_dir / val
                        if not _exists(f):
                            add(f"{o.name}: file not found: {_short(val)}", o, p.name)
                if p.kind == "ref" and val and val not in ids:
                    add(f"{o.name}: {p.label} points to a missing object {val!r}", o, p.name)
                elif p.kind == "ref" and val and p.ref and self.find(val).TYPE != p.ref:
                    want = REGISTRY[p.ref].LABEL if p.ref in REGISTRY else p.ref
                    add(f"{o.name}: {p.label} must be a {want}, not {self.find(val).name}", o, p.name)
                elif p.kind == "ref" and not val and p.name == "axes" and o.CATEGORY == "Charts":
                    add(f"{o.name}: choose a chart in 'Axes'", o, p.name)
                elif p.kind == "ref" and not val and p.name in o.REQUIRED_REFS:
                    add(f"{o.name}: choose an object in '{p.label}'", o, p.name)
            for p in o.all_props():
                expr = o.props.get(p.name)
                if not (p.expr and isinstance(expr, str) and expr.strip()):
                    continue
                if p.name == "expression" and o.props.get("source", "expression") != "expression":
                    continue
                names = tuple(sorted(set(p.expr.split(",")) | {"x", "t"})) if isinstance(p.expr, str) else ("t", "x")
                try:
                    compile_expression(expr, names)
                except ExpressionError as exc:
                    add(f"{o.name}: {exc}", o, p.name)
        scene_ids = {sc.id for sc in self.scenes}
        for o in self.objects:
            if o.scene not in scene_ids:
                add(f"{o.name}: its scene {o.scene!r} does not exist", o, None)
                continue
            if o.parent and (g := self.find(o.parent)) is not None and g.scene != o.scene:
                add(f"{o.name}: it is in another scene than its group {g.name}", o, "parent")
            for p in o.all_props():
                ref = o.props.get(p.name)
                if p.kind == "ref" and ref and (r := self.find(ref)) is not None and r.scene != o.scene:
                    add(f"{o.name}: {p.label} points to {r.name}, which is in another scene", o, p.name)
            dur = self.get_scene(o.scene).duration
            if o.start >= dur:
                add(f"{o.name}: starts at {o.start:g} s, after its scene ends ({dur:g} s)", o, None)
        for sc in self.scenes[1:]:
            if sc.transition != "cut" and self.overlap(sc) < sc.transition_duration - 1e-6:
                add(f"scene {sc.name}: the {sc.transition} is longer than a scene it joins; it is shortened "
                    f"to {self.overlap(sc):.2g} s", None, None)
        for o in [*(sc.camera for sc in self.scenes), *self.objects]:
            for name, tr in o.tracks.items():
                label = o.prop_map()[name].label if name in o.prop_map() else name
                if not tr.get("data"):
                    add(f"{o.name}: choose a table for the data track of {label}", o, name)
                    continue
                f = Path(tr["data"]) if Path(tr["data"]).is_absolute() else self.base_dir / tr["data"]
                if not _exists(f):
                    add(f"{o.name}: the data track of {label} needs a missing file: {tr['data']}", o, name)
                    continue
                try:
                    o.track_value(name, 0.0, track_assets)
                except (ValueError, KeyError, OSError) as exc:
                    add(f"{o.name}: data track of {label}: {exc}", o, name)
        a = self.settings.get("audio")
        if a and not _exists(self.base_dir / a) and not _exists(Path(a)):
            add(f"audio file not found: {a}", None, "audio")
        font = self.settings.get("font")
        if font not in FAMILIES and not _exists(Path(font)):
            add(f"font {font!r} is neither a bundled family ({', '.join(FAMILIES)}) nor a font file", None, "font")
        return out

    # ------------------------------------------------------------------ JSON
    def to_json(self) -> dict:
        self.settings["duration"] = self.duration               # the scenes' total
        one = len(self.scenes) == 1
        objects = []
        for o in self.objects:
            d = o.to_json()
            if one:
                d.pop("scene", None)                          # single-scene files read like before scenes
            objects.append(d)
        out = {
            "sciview": FORMAT_VERSION,
            "settings": {**copy.deepcopy(self.extra_settings), **self.settings},
            "palette": dict(self.palette),
            "camera": camera_json(self.scenes[0].camera),       # the first scene's camera
            "objects": objects,
        }
        if self.styles:
            out["styles"] = copy.deepcopy(self.styles)
        first = self.scenes[0]
        if not one or first.name != "Scene 1" or first.notes or not first.chapter or first.id != "scene1":
            out["scenes"] = [sc.to_json(with_camera=i > 0) for i, sc in enumerate(self.scenes)]
        for k, v in self.extra.items():
            out.setdefault(k, copy.deepcopy(v))
        return out

    @classmethod
    def from_json(cls, data: dict, path: str | os.PathLike | None = None) -> Project:
        if not isinstance(data, dict):
            raise ValueError("a SciView project is a JSON object")
        proj = cls(path=path)
        data, proj.notes = migrate(data)
        warn = compatibility(data.get("sciview", FORMAT_VERSION))
        if warn:
            proj.warnings.append(warn)
        proj.extra = {k: copy.deepcopy(v) for k, v in data.items() if k not in PROJECT_FIELDS}

        def part(key, kind, what):
            value = data.get(key)
            if value is None or isinstance(value, kind):
                return value
            proj.warnings.append(f"the {what} in the file could not be read and were left out")
            return None

        for k, v in (part("settings", dict, "settings") or {}).items():
            if k in SETTINGS_MAP:
                sp = SETTINGS_MAP[k]
                value = sp.coerce(v)
                if sp.kind in ("number", "int") and not (sp.min is None or sp.min <= value) or \
                        sp.kind in ("number", "int") and not (sp.max is None or value <= sp.max):
                    proj.warnings.append(f"setting {k!r} = {_short(v, 40)} is out of range; using {sp.default}")
                    value = copy.deepcopy(sp.default)
                proj.settings[k] = value
            else:
                proj.extra_settings[k] = copy.deepcopy(v)
                proj.warnings.append(f"unknown setting {k!r} is kept in the file but not used")
        if not (isinstance(proj.settings["duration"], (int, float)) and 0.1 <= proj.settings["duration"] < 1e6):
            proj.warnings.append("the film's length could not be read; using 10 s")
            proj.settings["duration"] = 10.0
        palette = part("palette", dict, "palette colours")
        if palette:
            proj.palette = {str(k).lower(): str(v) for k, v in palette.items()}
        styles = part("styles", dict, "styles")
        if styles:
            proj.styles = {k: dict(v) for k, v in styles.items() if isinstance(v, dict)}
        cam = part("camera", dict, "camera settings") or {}
        first_cam = _camera(cam, proj)
        scenes = part("scenes", list, "scenes")
        if scenes:
            proj.scenes = []
            for i, sd in enumerate(scenes):
                try:
                    sc = Scene.from_json(sd if isinstance(sd, dict) else {}, proj, first_cam if i == 0 else None)
                except (TypeError, ValueError, AttributeError, OverflowError) as exc:
                    proj.warnings.append(f"scene {i + 1} could not be read ({exc}); it starts empty")
                    sc = Scene(f"scene{i + 1}", f"Scene {i + 1}", camera=first_cam if i == 0 else None, project=proj)
                if any(x.id == sc.id for x in proj.scenes):
                    proj.warnings.append(f"two scenes are called {sc.id!r}; the second was renamed")
                    sc.id = f"{sc.id}_{i + 1}"
                proj.scenes.append(sc)
        else:                                            # files from before scenes: one scene, the whole film
            proj.scenes = [Scene("scene1", "Scene 1", float(proj.settings["duration"]), camera=first_cam,
                                 project=proj)]
        proj._current = proj.scenes[-1].id
        scene_ids = {sc.id for sc in proj.scenes}
        seen: set[str] = set()
        for i, od in enumerate(part("objects", list, "objects") or []):
            try:
                obj = SceneObject.from_json(od)
            except ValueError as exc:
                proj.warnings.append(str(exc))
                continue
            except (TypeError, AttributeError, KeyError, IndexError, OverflowError) as exc:
                # a damaged object is kept as it is in the file (not drawn), so saving does not lose it
                try:
                    obj = MissingObject(od, damaged=f"{type(exc).__name__}: {exc}")
                except Exception:
                    proj.warnings.append(f"object {i + 1} could not be read and was left out")
                    continue
            if not isinstance(obj.id, str) or obj.id in seen or obj.id == "camera":
                obj.id = proj._unique_id(obj.TYPE)
            seen.add(obj.id)
            if not isinstance(obj.scene, str) or not obj.scene:
                obj.scene = proj.scenes[0].id
            elif obj.scene not in scene_ids:
                proj.warnings.append(f"{obj.name}: unknown scene {obj.scene!r}; moved to the first scene")
                obj.scene = proj.scenes[0].id
            if obj.parent is not None and not isinstance(obj.parent, str):
                obj.parent = None
            proj.objects.append(obj)
        proj.settings["duration"] = proj.duration            # the scenes' total
        return proj

    def add_figure(self, func, name: str | None = None, **props) -> SceneObject:
        """Add a matplotlib figure drawn by ``func(fig, t)`` at every frame.

        The function stays in your script: the project file stores only its name, and saving the
        project also saves a snapshot picture for the editor and for people without the script.
        """
        from .. import figures
        obj = self.add("figure", name=name or getattr(func, "__name__", "Figure"), **props)
        key = f"{getattr(func, '__module__', 'script')}.{getattr(func, '__qualname__', 'figure')}:{obj.id}"
        figures.register(key, func)
        obj.set("callback", key)
        return obj

    def save_snapshots(self) -> list[Path]:
        """Save a picture of every figure whose function is available (done by :meth:`save`)."""
        from PIL import Image

        from .. import figures
        out = []
        for o in self.objects:
            func = figures.get(o.props.get("callback", "")) if o.TYPE == "figure" else None
            if func is None:
                continue
            start, end = o.span(self.duration)
            t = (start + end) / 2
            W, H = (int(round(float(x))) for x in o.props["size"])
            try:
                buf = figures.render(func, t, W, H, float(o.props["dpi"]), o.props.get("style", "sciview"))
            except Exception as exc:  # the user's function; the other figures still get their snapshot
                import sys
                sys.stderr.write(f"sciview: could not save a snapshot of {o.name}: {exc}\n")
                continue
            rel = f"assets/figures/{o.id}.png"
            f = self.base_dir / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray((np.clip(buf, 0, 1) * 255).astype(np.uint8), "RGBA").save(f)
            o.props["snapshot"] = rel
            out.append(f)
        return out

    def save(self, path: str | os.PathLike | None = None) -> Path:
        if path is not None:
            self.path = Path(path)
        if self.path is None:
            raise ValueError("no path given")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.save_snapshots()
        except Exception as exc:  # a failing figure function must not stop the save
            import sys
            sys.stderr.write(f"sciview: could not save a figure snapshot: {exc}\n")
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_json(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        return self.path

    @classmethod
    def load(cls, path: str | os.PathLike) -> Project:
        p = Path(path)
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_json(data, p.resolve())

    def copy(self) -> Project:
        return Project.from_json(self.to_json(), self.path)

    def __repr__(self) -> str:
        w, h = self.size
        return f"<Project {self.settings['title']!r} {w}x{h} {self.duration:g}s, {len(self.objects)} objects>"


def all_schemas() -> dict:
    """Everything the editor needs to build its library, inspector and settings dialog."""
    order = ["3D scene", "Text", "Charts", "Imaging", "Optics", "Shapes & media", "Sound"]
    order += sorted({c.CATEGORY for c in REGISTRY.values()} - set(order))     # categories from plugins
    types = sorted(REGISTRY.values(), key=lambda c: order.index(c.CATEGORY))
    return {
        "types": [c.schema() for c in types],
        "camera": CameraRig.schema(),
        "settings": [p.schema() for p in SETTINGS_PROPS],
        "categories": order,
        "fonts": list(FAMILIES),
        "palette": dict(DEFAULT_PALETTE),
        "light_palette": dict(LIGHT_PALETTE),
        "version": FORMAT_VERSION,
        "transitions": dict(TRANSITIONS),
    }


def iter_assets(project: Project) -> Iterable[str]:
    for o in project.objects:
        for p in o.all_props():
            if p.kind == "asset" and o.props.get(p.name):
                yield o.props[p.name]
    for key in ("audio", "logo"):
        if project.settings.get(key):
            yield project.settings[key]
