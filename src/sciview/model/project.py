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

from ..engine.camera import Camera
from ..engine.color import DEFAULT_PALETTE, LIGHT_PALETTE
from ..engine.text import FAMILIES, plain_text
from .base import REGISTRY, Prop, SceneObject

FORMAT_VERSION = "1.0"

SETTINGS_PROPS: list[Prop] = [
    Prop("title", "text", "Untitled film", group="Film"),
    Prop("author", "text", "", group="Film"),
    Prop("width", "int", 1920, min=16, max=7680, group="Film", help="Pixels. Layout is in these units"),
    Prop("height", "int", 1080, min=16, max=4320, group="Film"),
    Prop("fps", "int", 30, label="Frames per second", min=1, max=120, group="Film"),
    Prop("duration", "number", 10.0, min=0.1, max=3600, step=0.1, group="Film", help="Seconds"),
    Prop("background", "color", "#03070e", group="Look", help="Edge colour"),
    Prop("background2", "color", "#111a2c", label="Background 2", group="Look",
         help="Centre (radial) or bottom (vertical) colour"),
    Prop("background_style", "enum", "radial", options=("radial", "vertical", "solid"), group="Look"),
    Prop("stars", "number", 0.4, min=0, max=3, step=0.05, group="Look", help="Starfield density (0 = none)"),
    Prop("vignette", "number", 0.35, min=0, max=1, step=0.05, group="Look"),
    Prop("bloom", "number", 0.7, min=0, max=3, step=0.05, group="Look", help="Strength of the glow"),
    Prop("font", "font", "Poppins", group="Look", help="Poppins, Inter, or a path to a .ttf/.otf file"),
    Prop("audio", "asset", "", accept="audio", group="Sound", help="Narration or music mixed into the export"),
    Prop("audio_offset", "number", 0.0, step=0.1, group="Sound", help="Seconds into the film where the audio starts"),
    Prop("audio_volume", "number", 1.0, min=0, max=4, step=0.05, group="Sound"),
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
        self.camera = CameraRig(id="camera", name="Camera")
        self.objects: list[SceneObject] = []
        self.path: Path | None = Path(path) if path else None
        self.warnings: list[str] = []
        self._renderer = None
        for k, v in settings.items():
            self.set(k, v)

    # ------------------------------------------------------------------ settings
    def set(self, name: str, value: Any) -> Project:
        p = SETTINGS_MAP.get(name)
        if p is None:
            raise KeyError(f"unknown setting {name!r}. Settings: {', '.join(SETTINGS_MAP)}")
        self.settings[name] = p.coerce(value)
        return self

    @property
    def duration(self) -> float:
        return float(self.settings["duration"])

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
            id: str | None = None, **props) -> SceneObject:
        """Add an object by type name (``"box"``, ``"curve"`` ...) or instance; returns it."""
        if isinstance(type, SceneObject):
            obj = type
            if any(o.id == obj.id for o in self.objects):
                obj.id = self._unique_id(obj.TYPE)
        else:
            klass = REGISTRY.get(type)
            if klass is None:
                raise ValueError(f"unknown object type {type!r}. Types: {', '.join(sorted(REGISTRY))}")
            obj = klass(id=id or self._unique_id(type), name=name)
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

    def remove(self, ref: str | SceneObject) -> None:
        rid = ref.id if isinstance(ref, SceneObject) else ref
        self.objects = [o for o in self.objects if o.id != rid]

    def of_type(self, *types: str) -> list[SceneObject]:
        return [o for o in self.objects if o.TYPE in types]

    # ------------------------------------------------------------------ camera
    def camera_at(self, t: float, width: int, height: int, scale: float = 1.0) -> Camera:
        c = self.camera
        off = np.asarray(c.value_at("offset", t), np.float64) * scale
        return Camera.orbit(np.asarray(c.value_at("target", t), np.float64), float(c.value_at("distance", t)),
                            float(c.value_at("azimuth", t)), float(c.value_at("elevation", t)),
                            float(c.value_at("fov", t)), width, height, (float(off[0]), float(off[1])))

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

    def render(self, output: str | os.PathLike, **options) -> Path:
        """Render the film. See :func:`sciview.export.export` for options (fps, scale, crf, workers ...)."""
        from ..export import export
        return export(self, output, **options)

    # ------------------------------------------------------------------ captions
    def captions(self) -> list[tuple[float, float, str]]:
        out = []
        for o in self.objects:
            if o.TYPE == "caption" and o.visible:
                s, e = o.span(self.duration)
                out.append((s, e, plain_text(o.get("text"))))
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
        from ..engine.mathexpr import ExpressionError, compile_expression
        issues = list(self.warnings)
        ids = {o.id for o in self.objects}
        for o in self.objects:
            issues += o.warnings
            for p in o.all_props():
                val = o.props.get(p.name)
                if p.kind == "asset" and val:
                    f = Path(val) if Path(val).is_absolute() else self.base_dir / val
                    if not f.exists():
                        issues.append(f"{o.name}: file not found: {val}")
                if p.kind == "ref" and val and val not in ids:
                    issues.append(f"{o.name}: {p.label} points to a missing object {val!r}")
                if p.kind == "ref" and not val and p.name == "axes" and o.CATEGORY == "Charts":
                    issues.append(f"{o.name}: choose a chart in 'Axes'")
            for name in ("expression", "follow"):
                expr = o.props.get(name)
                if expr and (name != "expression" or o.props.get("source") == "expression"):
                    try:
                        compile_expression(expr)
                    except ExpressionError as exc:
                        issues.append(f"{o.name}: {exc}")
        a = self.settings.get("audio")
        if a and not (self.base_dir / a).exists() and not Path(a).exists():
            issues.append(f"audio file not found: {a}")
        font = self.settings.get("font")
        if font not in FAMILIES and not Path(font).is_file():
            issues.append(f"font {font!r} is neither a bundled family ({', '.join(FAMILIES)}) nor a font file")
        return issues

    # ------------------------------------------------------------------ JSON
    def to_json(self) -> dict:
        return {
            "sciview": FORMAT_VERSION,
            "settings": dict(self.settings),
            "palette": dict(self.palette),
            "camera": {"props": dict(self.camera.props), "keys": copy.deepcopy(self.camera.keys)},
            "objects": [o.to_json() for o in self.objects],
        }

    @classmethod
    def from_json(cls, data: dict, path: str | os.PathLike | None = None) -> Project:
        if not isinstance(data, dict):
            raise ValueError("a SciView project is a JSON object")
        ver = str(data.get("sciview", FORMAT_VERSION))
        proj = cls(path=path)
        if ver.split(".")[0] != FORMAT_VERSION.split(".")[0]:
            proj.warnings.append(f"project was written by format {ver}; this SciView reads {FORMAT_VERSION}")
        for k, v in (data.get("settings") or {}).items():
            if k in SETTINGS_MAP:
                proj.settings[k] = SETTINGS_MAP[k].coerce(v)
            else:
                proj.warnings.append(f"ignored unknown setting {k!r}")
        if data.get("palette"):
            proj.palette = {str(k).lower(): str(v) for k, v in data["palette"].items()}
        cam = data.get("camera") or {}
        proj.camera = CameraRig(id="camera", name="Camera", props=cam.get("props"), keys=cam.get("keys"))
        seen: set[str] = set()
        for od in data.get("objects") or []:
            try:
                obj = SceneObject.from_json(od)
            except ValueError as exc:
                proj.warnings.append(str(exc))
                continue
            if obj.id in seen or obj.id == "camera":
                obj.id = proj._unique_id(obj.TYPE)
            seen.add(obj.id)
            proj.objects.append(obj)
        return proj

    def save(self, path: str | os.PathLike | None = None) -> Path:
        if path is not None:
            self.path = Path(path)
        if self.path is None:
            raise ValueError("no path given")
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
    order = ["3D scene", "Text", "Charts", "Shapes & media"]
    types = sorted(REGISTRY.values(), key=lambda c: (order.index(c.CATEGORY) if c.CATEGORY in order else 9))
    return {
        "types": [c.schema() for c in types],
        "camera": CameraRig.schema(),
        "settings": [p.schema() for p in SETTINGS_PROPS],
        "categories": order,
        "fonts": list(FAMILIES),
        "palette": dict(DEFAULT_PALETTE),
        "light_palette": dict(LIGHT_PALETTE),
        "version": FORMAT_VERSION,
    }


def iter_assets(project: Project) -> Iterable[str]:
    for o in project.objects:
        for p in o.all_props():
            if p.kind == "asset" and o.props.get(p.name):
                yield o.props[p.name]
    if project.settings.get("audio"):
        yield project.settings["audio"]
