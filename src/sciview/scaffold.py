"""``sciview plugin new NAME``: a ready-to-install plugin package with one object type, one template and tests."""
from __future__ import annotations

import json
import re
from pathlib import Path

PYPROJECT = '''[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "{dist}"
version = "0.1.0"
description = "{title} for SciView"
readme = "README.md"
requires-python = ">=3.10"
dependencies = ["sciview>=1.0,<2"]

[project.optional-dependencies]
test = ["pytest>=7"]

# SciView finds plugins through these entry points
[project.entry-points."sciview.objects"]
{name} = "{module}.objects"

[project.entry-points."sciview.templates"]
{name} = "{module}:TEMPLATES"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
{module} = ["templates/*/*.json", "templates/*/assets/*"]
'''

INIT = '''"""{title}: a SciView plugin."""
from pathlib import Path

#: Templates of this plugin, one folder each with a project.sciview.json (and an assets folder if needed).
TEMPLATES = Path(__file__).parent / "templates"
'''

OBJECTS = '''"""Object types of this plugin. Importing the module registers them; SciView imports it at start-up."""
import numpy as np

import sciview as sv
from sciview import Object2D, Prop


@sv.register
class Pulse(Object2D):
    """Rings that grow from a point and fade: a signal, a source, a detection event."""

    TYPE = "{name}_pulse"                 # unique: start it with the plugin's name
    LABEL = "Pulse"
    CATEGORY = "{title}"                  # a section of the editor's library
    ICON = "ellipse"
    DESCRIPTION = "Rings that grow from a point and fade out, again and again."
    TIME_DEPENDENT = True                 # looks different at every instant
    PROPS = [
        Prop("center", "vec2", [960, 540], group="Position"),
        Prop("radius", "number", 160.0, min=1, max=2000, step=1, group="Position", help="Largest ring, in pixels"),
        Prop("rings", "int", 3, min=1, max=12, step=1, group="Look"),
        Prop("period", "number", 2.0, min=0.1, max=60, step=0.1, group="Look", help="Seconds per ring",
             animatable=False),
        Prop("color", "color", "teal", group="Look"),
        Prop("width", "number", 3.0, min=0.5, max=40, step=0.5, group="Look"),
        Prop("glow", "number", 1.0, min=0, max=3, step=0.1, group="Look"),
    ]

    def draw(self, cv, ctx, v, st):
        # v: values at this instant (colours as RGB); st: enter/exit state; ctx.s: design px -> output px
        cx, cy = (np.asarray(v.center) * st.scale + (st.dx, st.dy)) * ctx.s
        r_max = v.radius * st.scale * ctx.s
        phase = (st.local_t / max(v.period, 1e-3)) % 1.0
        for i in range(v.rings):
            f = (phase + i / v.rings) % 1.0                       # 0 -> 1 as a ring grows
            alpha = v.opacity * st.opacity * (1 - f) ** 1.5
            if alpha > 0.01:
                cv.circle(cx, cy, max(1.0, f * r_max), stroke=v.color, stroke_alpha=alpha,
                          width=v.width * ctx.s, glow=v.glow)
        return cx - r_max, cy - r_max, cx + r_max, cy + r_max   # bounding box, for selecting in the editor
'''

TEST = '''"""Run with: pip install -e ".[test]" && pytest"""
import numpy as np

import sciview as sv


def test_the_plugin_is_found():
    assert "{name}_pulse" in sv.object_types()
    assert any(r["name"] == "{name}" and r["ok"] for r in sv.plugins.info())


def test_the_object_draws_and_saves(tmp_path):
    film = sv.Project(duration=2, stars=0, path=tmp_path / "f.sciview.json")
    film.add("{name}_pulse", color="gold")
    a, b = film.frame(0.8, 0.25), film.frame(1.3, 0.25)       # after the 0.6 s fade-in
    assert a.max() > 60 and not np.array_equal(a, b)            # visible, and moving
    film.save()
    assert sv.load(film.path).objects[0].TYPE == "{name}_pulse"


def test_the_template_is_listed():
    from sciview.server import list_templates
    assert any(t["plugin"] == "{name}" for t in list_templates())
'''

README = '''# {dist}

{title} for [SciView](https://github.com/OriolSansPlanell/SciView): adds the **Pulse** object (rings that grow and
fade) and a demo template.

```bash
pip install -e .          # then: sciview edit   (Pulse is in the "{title}" section of the library)
sciview info              # lists the plugins SciView found
pytest                    # pip install -e ".[test]" first
```

Rename `Pulse`, change its properties and `draw`, add more classes with `@sv.register`, and put more template
folders in `src/{module}/templates`. See the plugin guide:
https://github.com/OriolSansPlanell/SciView/blob/main/docs/plugins.md
'''


def template_json(name: str, title: str) -> dict:
    return {
        "sciview": "1.0",
        "template": {"title": f"{title} demo", "description": "Pulses around a source.", "order": 80,
                     "thumb_time": 2.0},
        "settings": {"title": f"{title} demo", "duration": 6.0},
        "objects": [
            {"id": "title1", "type": "title", "name": "Title", "props": {"text": f"{title}"}},
            {"id": "pulse1", "type": f"{name}_pulse", "name": "Pulse", "props": {"color": "gold"}, "start": 0.5},
            {"id": "caption1", "type": "caption", "name": "Caption",
             "props": {"text": "Each ring is one detected event."}, "start": 1.5, "end": 5.5},
        ],
    }


def new_plugin(name: str, folder: str | Path = ".") -> Path:
    """Write a plugin package called ``sciview-<name>`` in ``folder``. Returns its directory."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if not slug or not slug[0].isalpha():
        raise ValueError("a plugin name starts with a letter, e.g. spectroscopy or my_lab")
    title = slug.replace("_", " ").capitalize()
    dist = f"sciview-{slug.replace('_', '-')}"
    module = f"sciview_{slug}"
    root = Path(folder) / dist
    if root.exists():
        raise FileExistsError(f"{root} already exists")
    fmt = {"name": slug, "title": title, "dist": dist, "module": module}
    files = {
        "pyproject.toml": PYPROJECT.format(**fmt),
        "README.md": README.format(**fmt),
        f"src/{module}/__init__.py": INIT.format(**fmt),
        f"src/{module}/objects.py": OBJECTS.replace("{name}", slug).replace("{title}", title),
        f"src/{module}/templates/{slug}_demo/project.sciview.json":
            json.dumps(template_json(slug, title), indent=2) + "\n",
        "tests/test_plugin.py": TEST.replace("{name}", slug),
    }
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root
