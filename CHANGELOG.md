# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

## [0.3.0] - 2026-11-22

Science content: volumes, tomography, molecules, optics, uncertainty and fits, data that drives the film,
and AI assistants that can build it with you.

### Added
- **Volumes** (`volume`) from `.npy`, TIFF stacks and HDF5 files: slice planes that sweep through the sample,
  maximum-intensity and summed projections, and isosurfaces (scikit-image) with an animatable threshold.
  Large volumes are reduced for drawing; slices are depth-sorted against each other.
- **Tomography**: `sinogram` recorded angle by angle from a phantom or your image, and `backprojection` that
  rebuilds the slice as the sinogram fills (ramp, Shepp-Logan, cosine, Hann or no filter). Images can rotate.
- **Points into a chart** (`morph`): an image's pixels, or a scatter plot's points, fly into a joint scatter
  plot or fall into histogram bins.
- **Data tracks**: any number or vector property, the camera's included, can follow a table column over time
  (`obj.track(...)`, "Data tracks" in the editor), with time offset and scale.
- **File sequences**: a file field can hold a pattern (`assets/run/step_*.csv`) and shows one file per step,
  in natural order; tables with equal rows are blended between files. Uploading several files at once in the
  editor makes a sequence.
- **Charts**: `heatmap` (expression or grid) with `colorbar`, `errorbars`, uncertainty `band`, fitted curve
  (`fit`: linear, polynomial, exponential, Gaussian, power, logistic; formula and R² in the label),
  `spectrum` with automatic or listed peak labels, 2D histogram (`hist2d`), `vectorfield` and `streamlines`
  with flowing dashes.
- **Optics**: `lens`, `mirror` (flat or curved, beam splitter, absorber), `rays` traced through them in the
  paraxial approximation, and `wavefront`.
- **Molecules** from PDB and XYZ files with bonds from CONECT records or distances: ball-and-stick,
  space-filling, sticks, wire, and a ribbon along the backbone with ligands kept as balls and sticks.
- **Matplotlib figures** redrawn at every frame by a function in your script (`film.add_figure(func)`). The
  project file stores only the function's name, never code, plus a snapshot shown in the editor.
- **Scale bars and units**: `scalebar` for images (from the pixel size) and charts, `scalebar3d` in scene
  units, and `{value:si:m}` in text for SI prefixes (2.5 mm, 12 nm).
- **AI assistants**: `sciview mcp` is a Model Context Protocol server with checked tools (describe the film,
  get schemas, add objects, set values and keyframes, timing, grouping, placing, render a frame, validate,
  review). Locked objects are never touched, and `--time` and `--ids` limit the scope. With `--editor`, changes
  appear live in the open editor and Ctrl+Z takes them back like your own edits; edits you make at the
  same moment are kept.
  The same tools are available in Python (`sciview.agent.FilmTools`).
- Two templates: **Tomography** and **Lenses and mirrors**.
- `science` extra (scikit-image, SciPy, tifffile, h5py).

### Changed
- The object library has two new sections, Imaging and Optics.
- `Project.problems()` also checks file patterns, data-track files and columns, and expressions of x and y.
- Cached layers notice changes in the objects they refer to (a back-projection follows its sinogram).
- `Project.problems()` reports reference fields that point at the wrong kind of object.

### Fixed
- Problems found while an object's values are worked out (such as a data track) now name the object, so the
  editor marks its row and field.
- The editor's server no longer prints a traceback when the browser closes a connection early.

## [0.2.0] - 2026-11-20

Building a talk-length film in the editor is now comfortable: groups, direct manipulation in 3D, custom
easing curves, autosave and a faster preview.

### Added
- **Groups** (`group` object, `Project.group()` / `ungroup()`, `parent` on every object): move, scale and
  rotate 2D and 3D members together, and fade and time them as one. Groups nest. In the editor:
  <kbd>Ctrl</kbd>+<kbd>G</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd>, nested and foldable
  timeline rows, click selects the group and double-click the object inside, "In group" in the Timing
  section. The step-by-step template now groups each panel with its contents.
- **Dragging 3D objects** in the preview: they move in the plane facing the camera and stay under the mouse;
  <kbd>Shift</kbd> keeps to one axis; <kbd>Alt</kbd>-drag orbits the camera over an object.
- **Multiple selection**: <kbd>Shift</kbd>-click in the preview and the timeline, <kbd>Ctrl</kbd>-drag box
  selection, <kbd>Ctrl</kbd>+<kbd>A</kbd>. Several objects move together and can be aligned, distributed,
  staggered in time, duplicated, deleted or edited together when they are of one kind.
- **Copy, cut and paste** of objects (with their group members and references between them) and of
  keyframes, across films, keeping timing relative to the playhead.
- **Custom easing curves** (`ease="bezier"`, `bez=(x1, y1, x2, y2)`, as CSS `cubic-bezier()`), with a curve
  editor and presets in the keyframe list.
- **Autosave and recovery**: unsaved changes are kept next to the film every 30 seconds and when the editor
  stops, and offered back the next time the film is opened.
- **Problems in place**: a warning sign on the object's timeline row, the reason in its properties and the
  field to fix marked in gold. `Project.problems()` returns them with the object and property.

### Changed
- **Faster preview and export**: objects that do not change between frames are drawn once into cached
  layers (pixel-identical, checked against every template); glow, vignette and grid drawing are cheaper.
  Half-size preview frames of the templates take 35 to 60% less time than in 0.1.
- The editor receives frames as JPEG with the details in a header instead of base64 JSON, and renders the
  next frames in the background while you pause (half a second) or play (three seconds).
- Python 3.10 or newer is required (3.9 reached its end of life in October 2025); tested on 3.10, 3.12 and
  3.14 on Linux, macOS and Windows.

### Fixed
- Images, detector images and 3D models now redraw when their file changes on disk while a film is open.
- A curve drawn inside its axes no longer reports a selection box larger than the axes.
- Pressing <kbd>Enter</kbd> in the time field returns the keyboard to the editor, so shortcuts work again.
- Popovers stay inside the window.

## [0.1.0] - 2026-11-20

First public version.

### Added
- Renderer on NumPy, OpenCV and Pillow: pure `frame(t)`, anti-aliased drawing, multi-scale glow, particle
  accumulation with soft saturation, starfield and vignette backgrounds.
- 27 object types: box, cylinder, sphere, screen/detector, particle beam, 3D arrow, floor grid, point cloud,
  STL/OBJ model, 3D label, title, caption, text, equation, legend, panel, rectangle, ellipse, arrow, image,
  chart axes, curve, scatter, bars, histogram, marker and threshold line.
- Keyframes on any number, colour or position with nine easings; enter and exit effects (fade, slide, pop,
  draw on, type on).
- Browser-based editor (`sciview edit`): object library, live preview, inspector, timeline with draggable
  clips and keyframes, undo/redo, templates, asset upload by drag and drop, export dialog.
- Python API with the same project model; JSON project format (`.sciview.json`).
- Export to MP4, WebM, ProRes, GIF and PNG frames in parallel processes, with audio and `.srt` subtitles.
- Command line: `edit`, `render`, `still`, `new`, `templates`, `check`, `subtitles`, `info`.
- Six templates: imaging beamline, step-by-step analysis, scatter and thresholds, animated equations, 3D
  structure and title card.
- Text markup for sub/superscripts, symbols and bold; LaTeX equations through matplotlib mathtext.
