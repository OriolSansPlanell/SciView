"""Plugins: object types, templates and speech engines from other Python packages.

A plugin is an ordinary Python package that declares entry points in its ``pyproject.toml``:

.. code-block:: toml

    [project.entry-points."sciview.objects"]
    spectroscopy = "sciview_spectroscopy.objects"        # a module whose classes use @sciview.register

    [project.entry-points."sciview.templates"]
    spectroscopy = "sciview_spectroscopy:TEMPLATES"      # a folder of templates (or a function returning one)

    [project.entry-points."sciview.tts"]
    myvoice = "sciview_myvoice:speak"                    # speak(text, path, voice=None, rate=None) -> path

Once the package is installed (``pip install sciview-spectroscopy``) its object types appear in the editor's
library, in Python and in the file format, and its templates next to the built-in ones. ``sciview plugin
new NAME`` writes a starting point. Set ``SCIVIEW_NO_PLUGINS=1`` to start without any plugin.
"""
from __future__ import annotations

import importlib.metadata as md
import os
import warnings
from pathlib import Path

GROUPS = ("sciview.objects", "sciview.templates", "sciview.tts")

_loaded = False
_records: list[dict] = []
_template_dirs: list[tuple[str, Path]] = []


def _entry_points(group: str) -> list:
    try:
        return list(md.entry_points(group=group))
    except Exception:  # pragma: no cover - broken metadata in the environment
        return []


def _dist(ep) -> tuple[str, str]:
    d = getattr(ep, "dist", None)
    if d is None:
        return "", ""
    try:
        return d.metadata["Name"] or "", d.version or ""
    except Exception:  # pragma: no cover
        return "", ""


def enabled() -> bool:
    return os.environ.get("SCIVIEW_NO_PLUGINS", "").strip().lower() not in ("1", "true", "yes")


def load(force: bool = False) -> list[dict]:
    """Load every installed plugin once (again with ``force``). Returns what was found; a plugin that
    fails is reported (also as a warning) and skipped, so one broken plugin never stops SciView."""
    global _loaded
    if _loaded and not force:
        return list(_records)
    _loaded = True
    _records.clear()
    _template_dirs.clear()
    if not enabled():
        return []
    from .model.base import REGISTRY
    for group in GROUPS:
        for ep in _entry_points(group):
            name, version = _dist(ep)
            rec = {"group": group, "name": ep.name, "value": ep.value, "package": name, "version": version,
                   "ok": True, "provides": [], "error": ""}
            try:
                if group == "sciview.objects":
                    before = set(REGISTRY)
                    obj = ep.load()
                    if callable(obj) and not isinstance(obj, type):
                        obj()                                    # a function that registers the types
                    rec["provides"] = sorted(set(REGISTRY) - before)
                elif group == "sciview.templates":
                    obj = ep.load()
                    if callable(obj):
                        obj = obj()
                    folder = Path(obj if not hasattr(obj, "__file__") else Path(obj.__file__).parent / "templates")
                    if not folder.is_dir():
                        raise FileNotFoundError(f"template folder {folder} does not exist")
                    _template_dirs.append((ep.name, folder))
                    rec["provides"] = sorted(d.name for d in folder.iterdir()
                                             if (d / "project.sciview.json").is_file())
                else:                                            # speech engines load when used
                    rec["provides"] = [ep.name]
            except Exception as exc:
                rec.update(ok=False, error=f"{type(exc).__name__}: {exc}")
                warnings.warn(f"SciView plugin {ep.name!r} ({group}) could not be loaded: {exc}", stacklevel=2)
            _records.append(rec)
    return list(_records)


def info() -> list[dict]:
    """What :func:`load` found: group, entry-point name, package, version, ok, what it provides, error."""
    load()
    return list(_records)


def template_dirs() -> list[tuple[str, Path]]:
    """(plugin name, folder) for every template pack that loaded."""
    load()
    return list(_template_dirs)


def describe() -> str:
    """A few readable lines for ``sciview info``."""
    recs = info()
    if not enabled():
        return "plugins: off (SCIVIEW_NO_PLUGINS)"
    if not recs:
        return "plugins: none installed"
    lines = ["plugins:"]
    for r in recs:
        what = ", ".join(r["provides"]) or "-"
        pkg = f"{r['package']} {r['version']}".strip() or r["value"]
        state = "" if r["ok"] else f"  FAILED: {r['error']}"
        lines.append(f"  {r['group'].split('.')[1]:<9} {r['name']:<16} {pkg:<28} {what}{state}")
    return "\n".join(lines)
