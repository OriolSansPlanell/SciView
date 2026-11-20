# The editor

Start it with `sciview edit` (an untitled film in the current folder) or `sciview edit film.sciview.json`.
The editor is a web page served by Python on your own computer; nothing is uploaded anywhere.

<img src="images/editor_charts.png" alt="The editor with a chart template open and a marker selected" width="900">

## Layout

| Area | What it is for |
| --- | --- |
| **Add** (left) | The object library. Click an object to add it at the playhead. Type in the search box to filter. |
| **Preview** (centre) | The frame at the playhead, rendered by the same code as the export. |
| **Transport** (under the preview) | Play, step frames, loop, type a time, choose the preview quality, save the frame as PNG. |
| **Properties** (right) | The selected object's timing and properties. With nothing selected: film settings and palette. |
| **Timeline** (bottom) | One row per object, the top row drawn on top. Clips show when objects are visible, diamonds are keyframes. |

## Selecting and moving

* Click an object in the preview or its row in the timeline to select it. <kbd>Esc</kbd> selects nothing.
* Drag text, charts and shapes in the preview to move them. Hold <kbd>Shift</kbd> to move along one axis.
* Drag empty space (or a 3D object) to orbit the camera; <kbd>Shift</kbd>+drag shifts the 3D scene on screen;
  scroll to zoom. If the camera is animated, these changes add a camera keyframe at the playhead.
* Drag a value's label left or right to change a number (<kbd>Shift</kbd> for big steps, <kbd>Alt</kbd> for
  fine ones). Arrow keys in a number field do the same.

## Timing

Each object has a clip on the timeline:

* Drag the clip to move it in time; its keyframes move with it.
* Drag its left or right edge to change when it appears or disappears.
* The shaded ends of a clip are the enter and exit effects. Choose them in **Timing** in the properties panel:
  fade, slide (four directions), pop, **draw on** (lines, shapes, charts, 3D wireframes) and **type on**
  (text). An exit effect plays only when the object has a disappear time.
* Drag the grip at the left of a row to change the drawing order.

Clips snap to frames, to the playhead and to the start and end of the film.

## Keyframes

Any number, colour or position can change over time:

1. Move the playhead and click the diamond next to a value. The label turns gold: the value is animated.
2. Move the playhead elsewhere and change the value. A new keyframe is added there automatically.
3. Gold diamonds appear on the object's clip. Drag them to retime, click one to jump to it, press
   <kbd>Del</kbd> to delete the selected one.
4. The **Keyframes** group lists them all; choose how each one eases in (smooth, linear, in, out, in-out,
   overshoot, hold ...).

<kbd>K</kbd> keyframes every animatable value of the selection at once, which is handy before a camera move.

The **camera** is the first timeline row. Keyframe its azimuth, elevation and distance for orbits and zooms,
its target to pan, and its offset to slide the 3D scene sideways when 2D panels share the frame.

## Text markup

Every text field understands:

| Type | You get |
| --- | --- |
| `H_2O`, `^6LiF` | H₂O, ⁶LiF (one character lowered / raised) |
| `x_{max}`, `e^{-x/2}` | groups |
| `\alpha \mu \Delta \AA \deg \to \pm \times \approx` | α μ Δ Å ° → ± × ≈ |
| `**bold**` | bold |
| `{value:.1f}` | in a Text object, its animated *Value* (counters) |

Equations use full LaTeX math syntax through the **Equation** object, e.g. `\mu = -\frac{\ln T}{d}`.

## Data and images

Upload files with the arrow button next to any file field, or drop them on the preview: images become Image
objects, 3D models become 3D models and audio becomes the film's soundtrack. Tables (CSV, TSV, whitespace
text, `.npy`, `.npz`) are used by scatter plots, curves, histograms and point clouds; the column fields suggest
the names found in the file.

## Film settings

Select nothing to edit the size, frame rate, duration, background, starfield, vignette, glow strength, font
and soundtrack. **Light for papers** switches to a white background and darker palette. The **palette** names
colours used across the film: change `teal` once and everything teal follows.

## Shortcuts

| Keys | Action |
| --- | --- |
| <kbd>Space</kbd> | play / pause |
| <kbd>←</kbd> <kbd>→</kbd> | previous / next frame (<kbd>Shift</kbd>: one second) |
| <kbd>Home</kbd> <kbd>End</kbd> | start / end |
| <kbd>K</kbd> | keyframe all values of the selection |
| <kbd>Del</kbd> | delete the selected keyframe, or the selected object |
| <kbd>Ctrl</kbd>+<kbd>D</kbd> | duplicate |
| <kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> | undo / redo |
| <kbd>Ctrl</kbd>+<kbd>S</kbd> | save (<kbd>Shift</kbd>: save as) |
| <kbd>Ctrl</kbd>+scroll on the timeline | zoom the timeline |
| <kbd>?</kbd> | help |

## Using the editor on a remote machine

The editor listens only on your own computer. To use it on a beamline or cluster machine, start it there and
forward the port over SSH:

```bash
ssh -L 8765:localhost:8765 user@analysis-machine
sciview edit film.sciview.json --no-browser
```

Then open `http://localhost:8765` in your local browser. Export downloads come back through the same tunnel.
