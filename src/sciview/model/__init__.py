"""Scene model: object types, project files and the per-frame context."""
from . import (  # noqa: F401  (registers the object types)
    charts,
    figure,
    group,
    molecule,
    objects2d,
    objects3d,
    optics,
    plots,
    science,
)
from .base import REGISTRY, Prop, SceneObject, State
from .project import SETTINGS_PROPS, CameraRig, Project, all_schemas

__all__ = ["Project", "SceneObject", "Prop", "State", "REGISTRY", "CameraRig", "SETTINGS_PROPS", "all_schemas"]
