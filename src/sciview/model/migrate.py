"""Upgrading project files written by older SciView versions.

The file says which format wrote it (``"sciview": "1.0"``). Within a major version the format only grows:
new settings, object types and properties are added, nothing changes meaning, and parts a reader does not
know are kept and written back (see :class:`~sciview.model.base.MissingObject`). A change that is not
additive gets a migration here: a function from one format version's JSON to the next, run in order when
an older file is opened, so films made with any earlier release keep opening.

Golden files from every release live in ``tests/golden`` and are loaded by the test suite.
"""
from __future__ import annotations

import copy
from collections.abc import Callable

#: The format this SciView writes.
FORMAT_VERSION = "1.0"

#: (from_version, to_version, function, what it changes). Applied in order.
MIGRATIONS: list[tuple[str, str, Callable[[dict], dict], str]] = []


def parse_version(v) -> tuple[int, int]:
    try:
        major, _, minor = str(v).strip().partition(".")
        return int(major), int(minor or 0)
    except ValueError:
        return (0, 0)


def migrate(data: dict) -> tuple[dict, list[str]]:
    """Bring ``data`` up to :data:`FORMAT_VERSION`. Returns the new JSON and a note for each step taken.
    ``data`` itself is not changed."""
    version = str(data.get("sciview", FORMAT_VERSION))
    notes: list[str] = []
    steps = {src: (dst, fn, what) for src, dst, fn, what in MIGRATIONS}
    seen = set()
    while version in steps and version not in seen:
        seen.add(version)
        dst, fn, what = steps[version]
        data = fn(copy.deepcopy(data))
        data["sciview"] = dst
        notes.append(f"converted from format {version} to {dst}: {what}")
        version = dst
    return data, notes


def compatibility(version) -> str | None:
    """A warning when a file's format is not one this SciView fully reads, else None."""
    have, want = parse_version(version), parse_version(FORMAT_VERSION)
    if have[0] != want[0]:
        return (f"the file was written in format {version}; this SciView reads format {FORMAT_VERSION} "
                f"and may not show everything")
    if have > want:
        return (f"the file was written by a newer SciView (format {version}); parts this version does not "
                f"know are kept in the file but not shown")
    return None
