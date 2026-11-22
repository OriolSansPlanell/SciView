"""Matplotlib figures redrawn at every frame by a Python function.

Only Python scripts can register these functions; a project file stores just the function's name,
so a film shared with others never runs code when it is opened. Without the function (in the editor,
or on another computer) the figure shows the snapshot saved with the project.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

_CALLBACKS: dict[str, Callable] = {}

#: rcParams that match SciView's dark style: transparent background, light text, thin grey frame
DARK_STYLE = {
    "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none",
    "text.color": "#f3ead8", "axes.labelcolor": "#f3ead8", "xtick.color": "#c9cfdb", "ytick.color": "#c9cfdb",
    "axes.edgecolor": "#8b95a7", "grid.color": "#8b95a7", "grid.alpha": 0.25, "legend.frameon": False,
    "font.size": 12, "axes.titlesize": 14, "axes.labelsize": 13,
}


def register(name: str, func: Callable) -> str:
    """Make ``func(fig, t)`` available to figure objects under ``name``."""
    if not callable(func):
        raise TypeError("a figure callback must be callable: def draw(fig, t): ...")
    _CALLBACKS[str(name)] = func
    return str(name)


def get(name: str) -> Callable | None:
    return _CALLBACKS.get(name) if name else None


def unregister(name: str) -> None:
    _CALLBACKS.pop(name, None)


@lru_cache(maxsize=1)
def _bundled_font() -> str | None:
    """Register the film font (Poppins) with matplotlib once; returns its family name."""
    try:
        from matplotlib import font_manager

        from .engine.text import font_path
        for w in ("regular", "medium"):
            font_manager.fontManager.addfont(font_path("Poppins", w))
        return font_manager.FontProperties(fname=font_path("Poppins", "regular")).get_name()
    except Exception:
        return None


def dark_style() -> dict:
    from cycler import cycler

    style = dict(DARK_STYLE)
    fam = _bundled_font()
    if fam:
        style["font.family"] = fam
    style["axes.prop_cycle"] = cycler(color=["#4fd1c5", "#ffcf4a", "#6cb4fc", "#ff6b6b", "#c38cff", "#7ee08a"])
    return style


def render(func: Callable, t: float, width_px: int, height_px: int, dpi: float, style: str = "sciview"):
    """Call ``func(fig, t)`` on a fresh figure of the given pixel size; return float RGBA (h, w, 4) in 0..1."""
    import matplotlib
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    rc = dark_style() if style == "sciview" else {}
    with matplotlib.rc_context(rc):
        fig = Figure(figsize=(max(width_px, 1) / dpi, max(height_px, 1) / dpi), dpi=dpi)
        canvas = FigureCanvasAgg(fig)
        if style == "sciview":
            fig.patch.set_alpha(0.0)
        func(fig, float(t))
        canvas.draw()
        buf = np.asarray(canvas.buffer_rgba(), dtype=np.float32) / 255.0
    return buf
