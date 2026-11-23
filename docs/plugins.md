# Plugins

A plugin adds object types, templates or speech engines to SciView. It is an ordinary Python package: once
it is installed, SciView finds it by itself, and its objects appear in the editor's library, in Python, in
project files and in the [JSON Schema](file-format.md#checking-files-against-the-schema).

```bash
pip install sciview-spectroscopy     # a plugin someone published
sciview plugin list                  # what SciView found, and anything that failed to load
```

## Start one

```bash
sciview plugin new spectroscopy
pip install -e sciview-spectroscopy
sciview edit                         # the "Spectroscopy" section of the library has a Pulse object
cd sciview-spectroscopy && pytest    # its tests (pip install -e ".[test]" first)
```

`sciview plugin new` writes a package with one object type (`spectroscopy_pulse`, rings that grow and fade),
one template, tests and a README:

```text
sciview-spectroscopy/
  pyproject.toml                         the entry points SciView looks for
  src/sciview_spectroscopy/__init__.py   TEMPLATES = the templates folder
  src/sciview_spectroscopy/objects.py    the object types
  src/sciview_spectroscopy/templates/spectroscopy_demo/project.sciview.json
  tests/test_plugin.py
```

Rename the object, change its properties and its `draw` method, add more classes, and publish the package on
PyPI like any other.

## Entry points

SciView reads three entry-point groups from the installed packages:

| Group | Value | What it adds |
| --- | --- | --- |
| `sciview.objects` | a module (imported at start-up), or a function that registers types when called | object types |
| `sciview.templates` | a folder (a `Path` or a string), or a function returning one; each sub-folder with a `project.sciview.json` (and an `assets` folder if needed) is a template | templates |
| `sciview.tts` | `speak(text, path, voice=None, rate=None) -> path`, which writes a WAV file | voices for **Read aloud** |

```toml
[project.entry-points."sciview.objects"]
spectroscopy = "sciview_spectroscopy.objects"

[project.entry-points."sciview.templates"]
spectroscopy = "sciview_spectroscopy:TEMPLATES"
```

A plugin that fails to load is reported by `sciview plugin list` and `sciview info` and skipped; SciView
keeps working. A template whose name is already taken is listed as `<plugin>-<name>`. Set
`SCIVIEW_NO_PLUGINS=1` to start without any plugin, for example to tell whether a problem comes from one.

## Writing an object type

An object type is a class with a list of properties and a `draw` method:

```python
import numpy as np
import sciview as sv
from sciview import Object2D, Prop


@sv.register
class Star(Object2D):
    TYPE = "mylab_star"                 # unique: start it with the plugin's name
    LABEL = "Star"
    CATEGORY = "My lab"                 # a section of the editor's library (new sections are added)
    ICON = "ellipse"                    # one of the editor's icons
    DESCRIPTION = "A five-pointed star."
    HAS_PROGRESS = True                 # supports the "draw on" effect (st.progress)
    PROPS = [
        Prop("center", "vec2", [960, 540], group="Position"),
        Prop("radius", "number", 80, min=1, group="Position"),
        Prop("color", "color", "gold", group="Look"),
    ]

    def draw(self, cv, ctx, v, st):
        a = np.radians(np.arange(11) * 36 - 90)
        r = np.where(np.arange(11) % 2, 0.45, 1.0) * v.radius * st.scale
        pts = (np.stack([np.cos(a) * r, np.sin(a) * r], 1) + v.center + (st.dx, st.dy)) * ctx.s
        cv.polyline(pts, v.color, v.opacity * st.opacity, 3 * ctx.s, glow=1.0, progress=st.progress)
        return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()
```

* **Properties** (`Prop(name, kind, default, ...)`): kinds are `number`, `int`, `bool`, `text`, `longtext`,
  `color`, `vec2`, `vec3`, `enum` (with `options`), `asset` (a file, with `accept`: image, table, mesh, audio,
  volume, molecule), `array`, `ref` (another object, with `ref` = its type) and `font`. Numbers, colours and
  vectors can be keyframed and driven by data tracks; `min`, `max`, `step`, `help` and `group` shape the
  inspector. `expr="x,t"` marks a math expression that `sciview check` verifies.
* **`draw(cv, ctx, v, st)`** is called for every frame the object is visible:
  * `v` holds the property values at this instant (colours as RGB arrays), plus `opacity`;
  * `st` is the enter/exit state: `opacity`, `dx`, `dy` (slides), `scale` (pop), `progress` (draw on) and
    `local_t`, the seconds since the object appeared;
  * `ctx.s` converts design pixels (1920 × 1080) to output pixels; `ctx.camera` projects 3D points for
    `Object3D` types; `ctx.assets` loads files; `ctx.warn(message, prop)` reports a problem in the editor;
  * `cv` draws anti-aliased shapes with optional glow: `polyline`, `polygon`, `circle`, `dots`, `splat`
    (particles), `blit` (a mask or an image), `triangles`, `warp` (an image onto a quadrilateral).
  * Return the bounding box in output pixels, so the object can be selected and dragged in the preview.
* `frame(t)` stays pure: draw from `t` and the values only, never from what was drawn before, so frames can
  render in any order and in parallel. Mark types that change with time on their own `TIME_DEPENDENT = True`
  (they are then never cached).
* 3D types derive from `sciview.Object3D` and draw through `ctx.camera` (`ctx.camera.project(points)` gives screen
  positions and depths).

The built-in types in `sciview/model/` are complete examples, from the simple `ellipse` to `beam` and
`volume`.

## What stays stable

`sciview.register`, `Prop`, `SceneObject`, `Object2D`, `Object3D`, the `draw` arguments listed above and the
entry-point groups are part of SciView's [stable interface](stability.md): plugins written for 1.0 keep
working in every 1.x release.

Films made with a plugin open without it: its objects are kept in the file, shown as missing in the
timeline and not drawn, and saving writes them back unchanged.
