# Python guide

Everything the editor does is available from Python, and both read and write the same project files. A
common workflow is to generate a film from your data in a script, then fine-tune timing in the editor.

## Projects and objects

```python
import sciview as sv

film = sv.Project(title="My film", duration=12, fps=30)       # settings as keyword arguments
src = film.add("box", name="Source", center=(-60, 0, 0), size=(14, 14, 14),
               edge_color="gold", fill_color="gold", label="neutron source")
```

`film.add(type, **properties)` returns the object. Types are listed by `sv.object_types()`; properties are in
the [object reference](objects.md). Unknown names raise a `KeyError` that lists the valid ones.

```python
src.set("glow", 1.5)                 # or src["glow"] = 1.5
film.find("box1")                    # objects by id
film.remove(src)
```

## Timing

```python
cap = film.add("caption", text="Neutrons cross the sample.", start=2, end=6)
cap.appear(effect="slide_up", duration=0.8)         # fade, slide_*, pop, draw, typewriter, none
cap.disappear(effect="fade", duration=0.5)
```

`start`/`end` are seconds; `end=None` keeps the object until the end of the film. The exit effect plays only
when `end` is set.

## Keyframes

```python
dot = film.add("marker", axes=ax, x=0.0, follow="exp(-x)")
dot.key("x", 2.0, 0.0).key("x", 5.0, 3.0, ease="in_out")
film.camera.key("azimuth", 0, -70).key("azimuth", 12, -20, ease="linear")
```

`key(property, time, value, ease)` adds or replaces a keyframe. `value=None` keys the current value. Eases:
`linear`, `smooth` (default), `smoother`, `in`, `out`, `in_out`, `overshoot`, `sine`, `hold`.

## Charts from data

Series refer to an Axes object; pass the object or its id.

```python
import numpy as np

ax = film.add("axes", position=(1000, 200), size=(760, 480), x_range=(0, 10), y_range=(0, 1),
              x_label="time (h)", y_label="water content")
t = np.linspace(0, 10, 200)
film.add("curve", axes=ax, source="data", x_values=t, y_values=1 - np.exp(-t / 3))
film.add("curve", axes=ax, expression="1 - exp(-x/3)", style="dashed")        # same, as an expression
film.add("scatter", axes=ax, data="assets/measurements.csv", x_column="t", y_column="theta")
film.add("histogram", axes=ax, data="assets/measurements.csv", column="theta", bins=30)
```

NumPy arrays are stored inline in the project file. For large data, save a table next to the project
(`np.savetxt("assets/data.csv", ..., delimiter=",", header="x,y", comments="")`) and point `data` at it.

Expressions are evaluated safely (no arbitrary code): `x`, the film time `t`, numbers, `pi`, `e` and functions
such as `sin`, `cos`, `exp`, `log`, `sqrt`, `abs`, `gauss(x, mu, sigma)`, `step`, `where`, `clip`. `x^2` means
x squared.

## Images and detectors

```python
from PIL import Image
Image.fromarray(radiograph_uint8).save("assets/radiograph.png")   # or np.save("assets/r.npy", float_array)

det = film.add("screen", center=(35, 0, 0), size=(22, 22), thickness=3,
               image="assets/radiograph.png", colormap="gold", counts=40)
det.key("buildup", 3, 0.0, "linear").key("buildup", 10, 1.0, "linear")    # builds up count by count
```

Single-channel images (8/16-bit PNG and TIFF, float `.npy`) go through a colormap with optional `vmin`/`vmax`.
Paths are relative to the project file.

## Rendering

```python
film.save("film.sciview.json")
film.render("film.mp4")                       # parallel, all cores but one
film.render("preview.mp4", scale=0.5, end=4)  # quick check of the first 4 s at half size
film.render("film.gif", scale=0.4, fps=12)
film.still(6.5, "figure.png", scale=2)        # 3840 x 2160 PNG for a paper or poster
frame = film.frame(6.5, scale=0.5)            # NumPy array, e.g. to show in a notebook
```

In Jupyter, `PIL.Image.fromarray(film.frame(t, 0.5))` shows a frame inline. `render` accepts `fps`, `scale`,
`crf` (quality, lower is sharper), `preset`, `start`, `end`, `workers`, `audio`, `subtitles` and a
`progress(done, total, eta)` callback.

## Reading and changing existing films

```python
film = sv.load("talk.sciview.json")
for obj in film.of_type("caption"):
    obj.set("size", 34)
print(film.validate())                 # missing files, broken chart references, bad expressions
film.save()
```

## Writing a new object type

An object type is a class with a list of `Prop`s and a `draw` method. Register it and it appears in the
editor's library and inspector, in project files and in the reference.

```python
import numpy as np
from sciview.model.base import Prop, SceneObject, register

@register
class Star(SceneObject):
    TYPE, LABEL, ICON, CATEGORY = "star", "Star", "sphere", "Shapes & media"
    DESCRIPTION = "A five-pointed star."
    HAS_PROGRESS = True                                  # supports the 'draw on' effect
    PROPS = [
        Prop("center", "vec2", [960, 540], group="Position"),
        Prop("radius", "number", 80, min=1, group="Position"),
        Prop("color", "color", "gold", group="Appearance"),
    ]

    def draw(self, cv, ctx, v, st):
        a = np.radians(np.arange(11) * 36 - 90)
        r = np.where(np.arange(11) % 2, 0.45, 1.0) * v.radius * st.scale
        pts = (np.stack([np.cos(a) * r, np.sin(a) * r], 1) + v.center + (st.dx, st.dy)) * ctx.s
        cv.polyline(pts, v.color, v.opacity * st.opacity, 3 * ctx.s, glow=1.0, progress=st.progress)
        return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()
```

`v` holds the property values at the current time (colours as RGB arrays), `st` the enter/exit state
(opacity, slide offset, pop scale, draw progress), `ctx` the frame context (camera, scale `ctx.s` from design
pixels to output pixels, text helpers, assets) and `cv` the canvas with anti-aliased primitives and a glow
buffer. To load it in the editor, put the class in a module and import it before starting the server, for
example with a small launcher script that imports your module and calls `sciview.server.serve()`.
