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
`linear`, `smooth` (default), `smoother`, `in`, `out`, `in_out`, `overshoot`, `sine`, `hold`, and `bezier`
for a curve of your own, given like CSS `cubic-bezier()`:

```python
dot.key("x", 7.0, 4.0, ease="bezier", bez=(0.3, 1.5, 0.6, 1.0))   # overshoots, then settles
```

## Groups

```python
panel = film.add("panel", position=(80, 170), size=(520, 650), title="Gray level")
ax = film.add("axes", position=(170, 270), size=(380, 420))
step = film.group([panel, ax], name="Step 1", pivot=(80, 170))
step.key("opacity", 6.0, 1.0).key("opacity", 7.0, 0.45)            # fade the whole step back
step.key("scale", 8.0, 1.0).key("scale", 9.0, 0.6)                 # and shrink it about its corner

rig = film.group([source, sample, detector], name="Beamline")      # 3D objects
rig.key("rotation", 0, (0, 0, 0)).key("rotation", 10, (0, 0, 90))  # turn the whole instrument
```

A group moves 2D members by `offset` and scales them by `scale` about `pivot` (pixels); it rotates 3D
members by `rotation` (degrees about x, then y, then z) and scales them about `pivot3d`, then moves them by
`position` (scene units). Its opacity, enter/exit effects and `start`/`end` apply to every member. Groups
nest. `film.ungroup(group)` dissolves one; `film.remove(group)` removes it with its members
(`members=False` keeps them); `film.children(g)`, `film.descendants(g)` and `film.ancestors(obj)` walk the
tree. Membership is the `parent` attribute of each object, which you can also set yourself.

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

## Uncertainty, fits and spectra

```python
ax = film.add("axes", position=(510, 280), size=(900, 520), x_range=(0, 10), y_range=(0, 1.2))  # top-left corner
film.add("scatter", axes=ax, data="assets/decay.csv", x_column="t", y_column="I")
film.add("errorbars", axes=ax, data="assets/decay.csv", x_column="t", y_column="I", y_error="dI")
fit = film.add("fit", axes=ax, data="assets/decay.csv", x_column="t", y_column="I", model="exponential",
               label="I = {formula},  R² = {r2:.3f}")
fit.enter_duration = 2.0                                  # the fitted curve draws itself as it enters
film.add("band", axes=ax, center="exp(-x/3)", spread="0.05 + 0.02*x")    # or source="data" with columns
spec_ax = film.add("axes", x_range=(10, 80), y_range=(0, 100), start=5)
film.add("spectrum", axes=spec_ax, data="assets/xrd.csv", x_column="two_theta", y_column="counts",
         start=5)                                          # peaks found and labelled automatically
```

Fits use SciPy's `curve_fit` when it is installed and a NumPy fallback otherwise. `heatmap` draws an
expression of `x`, `y` and `t` or a grid from a file, `colorbar` shows the scale of a heatmap, image or volume
(ticks with SI prefixes when you give a `unit`), and `hist2d` bins two columns.

## Fields and optics

```python
ax = film.add("axes", x_range=(-2, 2), y_range=(-2, 2))
film.add("vectorfield", axes=ax, u="-y", v="x")                   # expressions of x, y and t
film.add("streamlines", axes=ax, u="-y", v="x", flow_speed=40)    # dashes flow, 40 px per second

film.add("lens", position=(620, 470), focal=260, height=300)
film.add("mirror", position=(1640, 470), angle=180, radius=900)   # radius 0 = flat, kind="splitter" splits
rays = film.add("rays", source=(120, 470), spread=220, count=9, bounces=4)
rays.key("travel", 3, 0).key("travel", 6, 1)                      # light runs along the rays
film.add("wavefront", source=(120, 470), kind="circular", wavelength=40)
```

Rays are traced in the paraxial (thin lens) approximation through every lens and mirror in the film.

## Volumes and tomography

```python
np.save("assets/scan.npy", volume)          # (z, y, x) array; TIFF stacks and HDF5 files work too
vol = film.add("volume", data="assets/scan.npy", size=50, spacing=(1, 1, 2.5), colormap="ice")
vol.key("slice_z", 2, 0.05).key("slice_z", 6, 0.95)             # sweep a plane through the sample
film.add("volume", data="assets/scan.npy", mode="mip")          # maximum-intensity projection
film.add("volume", data="assets/scan.npy", mode="isosurface", threshold=0.5)   # needs scikit-image
film.add("scalebar3d", origin=(-28, -36, -16), length=20, unit="0.5 mm")

sino = film.add("sinogram", source="phantom", angles=180)        # or source="image", image=...
sino.key("progress", 2, 0, "linear").key("progress", 8, 1, "linear")
film.add("backprojection", sinogram=sino.id, filter="ramp")      # follows the sinogram angle by angle
```

Large volumes are reduced to `max_size` voxels per side for drawing. Install the extras with
`pip install "sciview[science]"` (scikit-image, SciPy, tifffile, h5py).

## Points that fly into a chart

```python
img = film.add("image", image="assets/slice.png", position=(400, 540), width=500)
ax = film.add("axes", position=(1000, 300), size=(760, 480), x_range=(0, 1), y_range=(0, 400))
m = film.add("morph", source=img.id, axes=ax.id, target="histogram", bins=30)
m.key("progress", 3, 0).key("progress", 6, 1, "in_out")
```

Pixels of the image (or points of a scatter) leave their place and fall into histogram bins, or into a joint
scatter of two images (`target="joint"`, `image_b=...`).

## Molecules

```python
mol = film.add("molecule", model="assets/1crn.pdb", style="ribbon", color_by="chain")
mol.key("rotation", 0, (0, 0, 0)).key("rotation", 10, (0, 0, 360), "linear")
```

PDB and XYZ files are read with their bonds (CONECT records, otherwise guessed from distances). Styles:
`ball_and_stick`, `spacefill`, `sticks`, `wire` and `ribbon` (ligands stay ball-and-stick).

## Data tracks and file sequences

Any number or vector property can follow a column of a table over time:

```python
temp = film.add("text", text="T = {value:.0f} K", position=(120, 120))
temp.track("value", "assets/furnace_log.csv", column="temperature", time="seconds", time_scale=60)
cam_target = film.camera.track("target", "assets/path.csv", column="x, y, z")
```

At film time `t` the table time is `(t - time_offset) * time_scale`, so a one-hour log can play in one minute.
Tracks override keyframes of the same property. A file pattern plays one file per step, for image series and
simulation outputs:

```python
film.add("image", image="assets/frames/step_*.tif", steps_per_second=10)   # natural order: 2 before 10
sim = film.add("scatter", axes=ax, data="assets/sim/out_*.csv", x_column="x", y_column="y")
sim.key("step", 0, 0, "linear").key("step", 8, 2, "linear")                 # file 1 to file 3 over 8 s
```

`steps_per_second` plays the files from the moment the object appears; keyframing `step` controls it exactly. Tables with
the same number of rows are interpolated between files, so particles move smoothly.

## Matplotlib figures

When a plot needs something SciView does not have, draw it with matplotlib. The function runs at every frame:

```python
def growth(fig, t):
    ax = fig.subplots()
    x = np.linspace(0, 10, 200)
    ax.plot(x, np.exp(-x / 3) * np.cos(2 * x - t))
    ax.set_xlabel("time (s)")

film.add_figure(growth, position=(1400, 540), size=(800, 520))
film.save("film.sciview.json")        # also saves a snapshot of the figure in assets/figures/
film.render("film.mp4")
```

The project file stores only the function's name, never code, so the figure is redrawn only when your
script runs. In the editor, and for anyone opening the file without the script, it shows the snapshot.
Rendering with script figures uses a single process.

## Scale bars and units

```python
film.add("scalebar", reference=img.id, pixel_size="6.5 µm", length="1 mm")   # on an image
film.add("text", text="{value:si:Pa}", value=2.5e5)                            # 250 kPa
```

`{value:si:m}` writes a number with an SI prefix (2.5 mm, 12 nm), `{value:.2si:A}` sets the digits, and
`{t:.1f}` shows the film time. In Python, `sciview.engine.units.si(0.0025, "m")` gives the same text.

## Letting an AI assistant help

`sciview mcp film.sciview.json` lets an AI assistant build and edit the film with a small set of checked tools;
see [AI assistants](agent.md). The same tools are available in Python:

```python
from sciview.agent import FilmTools
tools = FilmTools(film)
tools.call("add_object", {"type": "caption", "props": {"text": "Hello"}, "start": 1})
```

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
