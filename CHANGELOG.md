# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

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
