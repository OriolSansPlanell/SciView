"""File sequences (one file per step) for images, volumes and tables."""
from __future__ import annotations

import numpy as np

from ..engine.assets import is_sequence
from .base import Prop


def seq_props(group: str) -> list[Prop]:
    return [
        Prop("step", "number", 0.0, min=0, step=1, group=group,
             help="For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, "
                  "or set Steps per second"),
        Prop("steps_per_second", "number", 0.0, min=0, step=0.5, group=group,
             help="Play a file pattern by itself: files per second since the object appeared (0 = use Step)"),
    ]


def step_index(v) -> float:
    return float(v.get("step", 0.0)) + float(v.get("steps_per_second", 0.0)) * max(0.0, float(v.get("_local_t", 0.0)))


def plays_by_itself(obj, prop: str) -> bool:
    """True when a sequence advances with time on its own (so the object is never static)."""
    return is_sequence(obj.props.get(prop, "")) and float(obj.props.get("steps_per_second", 0) or 0) > 0


def current_file(ctx, v, prop: str = "image") -> str:
    """The file a (possibly patterned) asset property points at, at this step: the nearest one."""
    rel = v[prop]
    if not is_sequence(rel):
        return rel
    lo, hi, f = ctx.assets.sequence_file(rel, step_index(v))
    return hi if f >= 0.5 else lo


def column(ctx, v, col, prop: str = "data") -> np.ndarray:
    """A table column; for a file pattern, interpolated between the two nearest files when they have
    the same number of rows (particles move smoothly), else taken from the nearest file."""
    rel = v[prop]
    if not is_sequence(rel):
        return ctx.assets.column(rel, col)
    lo, hi, f = ctx.assets.sequence_file(rel, step_index(v))
    a = ctx.assets.column(lo, col)
    if f <= 1e-9 or lo == hi:
        return a
    b = ctx.assets.column(hi, col)
    if len(a) != len(b):
        return b if f >= 0.5 else a
    return a + (b - a) * f
