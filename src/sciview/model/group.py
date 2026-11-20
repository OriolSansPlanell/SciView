"""Groups: move, scale, rotate, fade and time several objects together."""
from __future__ import annotations

from .base import Prop, SceneObject, register

G = "Group"


@register
class Group(SceneObject):
    """A container. Members keep their own properties; the group adds a transform and opacity.

    * 2D members are shifted by ``offset`` and scaled by ``scale`` about ``pivot`` (pixels).
    * 3D members are rotated by ``rotation`` and scaled by ``scale`` about ``pivot3d``, then
      moved by ``position`` (scene units); ``offset`` shifts them on screen.
    * The group's opacity, enter/exit effects and visible span apply to every member.
    """

    TYPE, LABEL, ICON, CATEGORY = "group", "Group", "group", "Shapes & media"
    DESCRIPTION = "Moves, scales, fades and times its members together. Select objects and press Ctrl+G."
    IS_GROUP = True
    DEFAULT_ENTER = "none"
    DEFAULT_EXIT = "none"
    PROPS = [
        Prop("offset", "vec2", [0, 0], group=G, help="Shift of the members on screen, in pixels"),
        Prop("scale", "number", 1.0, min=0, step=0.01, group=G, help="Scale of the members"),
        Prop("pivot", "vec2", [960, 540], group=G, help="Point that 2D members scale about, in pixels"),
        Prop("position", "vec3", [0, 0, 0], group="3D members", help="Shift of 3D members, in scene units"),
        Prop("rotation", "vec3", [0, 0, 0], group="3D members", help="Rotation of 3D members, degrees about x, y, z"),
        Prop("pivot3d", "vec3", [0, 0, 0], label="Pivot (3D)", group="3D members",
             help="Point that 3D members rotate and scale about"),
    ]

    def draw(self, cv, ctx, v, st):  # pragma: no cover - groups are never drawn themselves
        return None
