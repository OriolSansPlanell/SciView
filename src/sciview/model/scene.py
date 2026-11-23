"""Scenes: the parts of a film, each with its own objects, camera and clock.

Objects belong to one scene and their times (start, end, keyframes) count from the start of that
scene, so scenes can be reordered or lengthened without retiming anything inside the others. A
scene's transition overlaps the end of the scene before it.
"""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from ..engine.transitions import TRANSITIONS

if TYPE_CHECKING:  # pragma: no cover
    from .base import SceneObject
    from .project import CameraRig, Project


class Scene:
    """A part of the film.

    ``transition`` is how this scene comes in after the previous one (ignored for the first scene),
    ``transition_duration`` how long the two overlap. ``chapter`` adds a chapter marker with the
    scene's name to the exported video; ``notes`` become speaker notes in PowerPoint.
    """

    def __init__(self, id: str, name: str | None = None, duration: float = 10.0, transition: str = "cut",
                 transition_duration: float = 1.0, chapter: bool = True, notes: str = "",
                 camera: CameraRig | None = None, project: Project | None = None):
        from .project import CameraRig
        self.id = str(id)
        self.name = name or self.id
        self.duration = max(0.1, float(duration))
        if not self.duration < 1e6:
            raise ValueError(f"a scene of {duration} s")
        self.transition = "cut"
        self.transition_duration = 1.0
        self.set_transition(transition, transition_duration)
        self.chapter = bool(chapter)
        self.notes = str(notes or "")
        self.camera = camera or CameraRig(id="camera", name="Camera")
        self._project = project
        self.extra: dict[str, Any] = {}          # parts of the file this version does not know (kept)

    def set_transition(self, kind: str, duration: float | None = None) -> Scene:
        if kind not in TRANSITIONS:
            raise ValueError(f"unknown transition {kind!r}. Transitions: {', '.join(TRANSITIONS)}")
        self.transition = kind
        if duration is not None:
            self.transition_duration = max(0.0, float(duration))
        return self

    # ------------------------------------------------------------------ objects
    @property
    def project(self) -> Project:
        if self._project is None:
            raise RuntimeError("this scene is not part of a film")
        return self._project

    def add(self, type: str | SceneObject, name: str | None = None, **kw) -> SceneObject:
        """Add an object to this scene (see :meth:`Project.add`); times count from the scene's start."""
        return self.project.add(type, name, scene=self, **kw)

    @property
    def objects(self) -> list[SceneObject]:
        return [o for o in self.project.objects if o.scene == self.id]

    @property
    def start(self) -> float:
        """When the scene starts in the film, in seconds (its transition begins here)."""
        return self.project.scene_start(self)

    def frame(self, t: float, scale: float = 1.0):
        """This scene alone at its own time ``t`` (no transition), as a uint8 RGB array."""
        return self.project.renderer().frame(t, scale, scene=self.id)

    # ------------------------------------------------------------------ JSON
    def to_json(self, with_camera: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "name": self.name, "duration": self.duration,
                             "transition": self.transition, "transition_duration": self.transition_duration}
        if not self.chapter:
            d["chapter"] = False
        if self.notes:
            d["notes"] = self.notes
        if with_camera:
            d["camera"] = camera_json(self.camera)
        for k, v in self.extra.items():
            d.setdefault(k, copy.deepcopy(v))
        return d

    @classmethod
    def from_json(cls, d: dict, project: Project | None = None, camera: CameraRig | None = None) -> Scene:
        from .project import CameraRig
        trans = d.get("transition", "cut")
        sc = cls(id=d.get("id") or "scene1", name=d.get("name"), duration=d.get("duration", 10.0),
                 transition=trans if trans in TRANSITIONS else "cut",
                 transition_duration=d.get("transition_duration", 1.0), chapter=d.get("chapter", True),
                 notes=d.get("notes", ""), project=project)
        cam = d.get("camera")
        if camera is not None:
            sc.camera = camera
        elif isinstance(cam, dict):
            sc.camera = CameraRig(id="camera", name="Camera", props=cam.get("props"), keys=cam.get("keys"),
                                  tracks=cam.get("tracks"))
        if trans not in TRANSITIONS and project is not None:
            project.warnings.append(f"scene {sc.name!r}: unknown transition {trans!r}, using a cut")
        sc.extra = {k: copy.deepcopy(v) for k, v in d.items() if k not in SCENE_FIELDS}
        return sc

    def __repr__(self) -> str:
        return f"<Scene {self.id!r} {self.name!r} {self.duration:g}s>"


SCENE_FIELDS = frozenset({"id", "name", "duration", "transition", "transition_duration", "chapter", "notes",
                          "camera"})


def camera_json(cam: CameraRig) -> dict:
    return {"props": dict(cam.props), "keys": copy.deepcopy(cam.keys),
            **({"tracks": copy.deepcopy(cam.tracks)} if cam.tracks else {})}


class SceneView:
    """One scene seen as a film of its own: its objects, its camera and its duration.

    The renderer draws a scene through this view; everything it does not override comes from the
    project (settings, palette, size, assets folder ...).
    """

    def __init__(self, project: Project, scene: Scene):
        self._project = project
        self.scene = scene
        self.objects = [o for o in project.objects if o.scene == scene.id]
        self.camera = scene.camera
        self.duration = scene.duration

    def find(self, ref: str):
        if ref == "camera":
            return self.camera
        return self._project.find(ref)

    def camera_at(self, t: float, width: int, height: int, scale: float = 1.0, assets=None):
        return self._project.camera_at(t, width, height, scale, assets, rig=self.camera)

    def __getattr__(self, name: str):
        return getattr(self._project, name)
