"""SciView: make clear, beautiful scientific explainer videos.

Quick start::

    import sciview as sv

    film = sv.Project(duration=8, title="Neutron imaging")
    src = film.add("box", name="Source", center=(-60, 0, 0), size=(14, 14, 14), edge_color="gold",
                   fill_color="gold", label="neutron source")
    film.add("beam", source=(-53, 0, 0), target=(0, 0, 0), start=1.0)
    film.add("title", text="Neutron imaging", subtitle="How a radiograph is made")
    film.camera.key("azimuth", 0, -70).key("azimuth", 8, -40)
    film.render("neutrons.mp4")

Open the graphical editor with ``sciview edit`` in a terminal.
"""
from .model import REGISTRY, CameraRig, Project, Prop, SceneObject, all_schemas
from .model.base import register
from .model.objects2d import Object2D
from .model.objects3d import Object3D
from .render import Renderer

__version__ = "1.0.0"

__all__ = ["Project", "SceneObject", "Object2D", "Object3D", "Prop", "register", "CameraRig", "Renderer",
           "REGISTRY", "all_schemas", "object_types", "load", "preview", "__version__"]


def object_types() -> list[str]:
    """Names of all object types that ``Project.add`` accepts."""
    return sorted(REGISTRY)


def load(path) -> Project:
    """Open a project file."""
    return Project.load(path)


def preview(project: Project, **kw):
    """A scrubbable preview of a film in a Jupyter notebook; see :func:`sciview.jupyter.preview`."""
    from .jupyter import preview as _preview
    return _preview(project, **kw)


def load_ipython_extension(ipython) -> None:
    """``%load_ext sciview`` in Jupyter: the ``%sciview`` magic (see :mod:`sciview.jupyter`)."""
    from .jupyter import load_ipython_extension as _load
    _load(ipython)


# object types, templates and speech engines from installed plugin packages (last: plugins import sciview)
from . import plugins as _plugins  # noqa: E402

_plugins.load()
