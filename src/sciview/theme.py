"""Themes and brand kits: a shareable ``.sciview-theme.json`` with a palette, the film's look and font, a
logo, and default styles for object types (titles, captions ...).

A theme is applied to a project: its palette and look replace the project's, its logo is copied into
the project's assets, and its styles become the defaults of new objects (and, if asked, are applied to
the objects already there). Colours written as palette names (``"gold"``, ``"cream"``) follow the theme.
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

FORMAT = 1
BUILTIN_DIR = Path(__file__).parent / "themes"
LOOK_SETTINGS = ("background", "background2", "background_style", "stars", "vignette", "bloom", "font")
LOGO_SETTINGS = {"image": "logo", "position": "logo_position", "size": "logo_size", "margin": "logo_margin",
                 "opacity": "logo_opacity", "scenes": "logo_scenes"}


class ThemeError(ValueError):
    pass


def builtin() -> dict[str, dict]:
    """The themes that come with SciView, by short name (``dark``, ``light``, ``contrast``)."""
    out = {}
    files = sorted(BUILTIN_DIR.glob("*.sciview-theme.json"), key=lambda f: (f.name != "dark.sciview-theme.json", f.name))
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        d["_dir"] = str(f.parent)
        out[f.name.split(".")[0]] = d
    return out


def load(theme: str | Path | dict) -> dict:
    """A theme from a dict, a built-in name or a ``.sciview-theme.json`` file."""
    if isinstance(theme, dict):
        d = copy.deepcopy(theme)
    else:
        names = builtin()
        if str(theme) in names:
            return names[str(theme)]
        p = Path(theme)
        if not p.exists():
            raise ThemeError(f"no theme {str(theme)!r}: give a .sciview-theme.json file or one of "
                             f"{', '.join(names)}")
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ThemeError(f"{p.name} is not valid JSON: {exc}") from None
        d["_dir"] = str(p.parent.resolve())
    if not isinstance(d, dict) or int(d.get("sciview_theme", 0) or 0) < 1:
        raise ThemeError("not a SciView theme (it needs \"sciview_theme\": 1)")
    return d


def apply(project: Project, theme: str | Path | dict, restyle: bool = True) -> list[str]:
    """Apply a theme. Returns notes about anything that could not be used (unknown settings, missing files).

    ``restyle`` also sets the theme's styles on the objects already in the film (locked ones are left alone).
    """
    from .model.base import REGISTRY
    from .model.project import SETTINGS_MAP
    d = load(theme)
    notes: list[str] = []
    base = Path(d.get("_dir") or ".")
    for k, v in (d.get("palette") or {}).items():
        project.palette[str(k).lower()] = str(v)
    for k, v in (d.get("settings") or {}).items():
        if k not in SETTINGS_MAP or k in ("width", "height", "fps", "duration", "title", "author", "audio"):
            notes.append(f"ignored setting {k!r}")
            continue
        if k == "font" and isinstance(v, str) and (v.startswith("data:") or v.endswith((".ttf", ".otf"))):
            v = _bring(project, base, v, "assets/fonts", notes) or project.settings["font"]
        project.set(k, v)
    logo = d.get("logo") or {}
    if logo:
        for k, setting in LOGO_SETTINGS.items():
            if k not in logo:
                continue
            v = logo[k]
            if k == "image" and v:
                v = _bring(project, base, v, "assets/theme", notes) or ""
            project.set(setting, v)
    elif "logo" in d:
        project.set("logo", "")
    styles: dict[str, dict] = {}
    for typ, props in (d.get("styles") or {}).items():
        klass = REGISTRY.get(typ)
        if klass is None or not isinstance(props, dict):
            notes.append(f"ignored styles for unknown type {typ!r}")
            continue
        names = klass.prop_map() if hasattr(klass, "prop_map") else {p.name: p for p in klass.all_props()}
        good = {k: v for k, v in props.items() if k in names}
        notes += [f"{typ} has no property {k!r}" for k in props if k not in names]
        if good:
            styles[typ] = good
    project.styles = styles
    project.settings["theme"] = str(d.get("name") or "")
    if restyle:
        for o in project.objects:
            if o.locked or o.TYPE not in styles:
                continue
            for k, v in styles[o.TYPE].items():
                if k not in o.keys:
                    o.set(k, v)
    return notes


def _bring(project: Project, base: Path, value: str, folder: str, notes: list[str]) -> str | None:
    """A file named by a theme (next to the theme file, or inside it as a data URI) copied into the project."""
    if value.startswith("data:"):
        return _data_file(project, value, folder, notes)
    return _copy_file(project, base / value, folder, notes)


def _copy_file(project: Project, src: Path, folder: str, notes: list[str]) -> str | None:
    if not src.is_file():
        notes.append(f"theme file not found: {src.name}")
        return None
    dest_dir = project.base_dir / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return f"{folder}/{src.name}"


def from_project(project: Project, name: str = "", description: str = "") -> dict[str, Any]:
    """The project's look as a theme dict (palette, look settings, logo, styles)."""
    d: dict[str, Any] = {"sciview_theme": FORMAT, "name": name or project.settings.get("theme") or "My theme",
                         "description": description, "palette": dict(project.palette),
                         "settings": {k: project.settings[k] for k in LOOK_SETTINGS},
                         "styles": copy.deepcopy(project.styles)}
    if project.settings.get("logo"):
        d["logo"] = {k: project.settings[s] for k, s in LOGO_SETTINGS.items()}
    return d


def embed_files(project: Project, d: dict) -> dict:
    """Put the logo (and a font file) into the theme as data URIs, so one file carries the whole kit."""
    import base64
    import mimetypes
    d = copy.deepcopy(d)
    for key, holder in (("image", d.get("logo") or {}), ("font", d.get("settings") or {})):
        rel = holder.get(key)
        if rel and isinstance(rel, str) and not rel.startswith("data:") and (project.base_dir / rel).is_file():
            f = project.base_dir / rel
            mime = mimetypes.guess_type(f.name)[0] or ("font/ttf" if f.suffix.lower() == ".ttf" else "application/octet-stream")
            holder[key] = f"data:{mime};name={f.name};base64," + base64.b64encode(f.read_bytes()).decode()
    return d


def _data_file(project: Project, uri: str, folder: str, notes: list[str]) -> str | None:
    import base64
    try:
        head, b64 = uri.split(",", 1)
        name = next((p[5:] for p in head.split(";") if p.startswith("name=")), None)
        data = base64.b64decode(b64)
    except (ValueError, TypeError):
        notes.append("a file inside the theme could not be read")
        return None
    if not name:
        ext = ".png" if "png" in head else ".jpg" if "jpeg" in head else ".svg" if "svg" in head else ".ttf"
        name = f"theme{ext}"
    name = Path(name).name
    dest = project.base_dir / folder / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"{folder}/{name}"


def save(project: Project, path: str | Path, name: str = "", description: str = "") -> Path:
    """Write the project's look as a ``.sciview-theme.json``; the logo and a font file are copied beside it."""
    p = Path(path)
    if not p.name.endswith(".sciview-theme.json"):
        p = p.with_name(p.name.split(".")[0] + ".sciview-theme.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    d = from_project(project, name, description)
    for key, holder in (("image", d.get("logo") or {}), ("font", d["settings"])):
        rel = holder.get(key)
        if rel and isinstance(rel, str) and (project.base_dir / rel).is_file():
            src = project.base_dir / rel
            if src.parent.resolve() != p.parent.resolve():
                shutil.copy2(src, p.parent / src.name)
            holder[key] = src.name
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
