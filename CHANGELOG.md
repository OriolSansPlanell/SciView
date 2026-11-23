# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

## [1.0.0] - 2026-11-23

The first stable release: a file format and plugin API that stay compatible through 1.x, notebooks,
documentation online with a gallery, and the checks that keep it that way.

### Added
- **Stable file format 1.x**: parts of a file this version does not know (objects of a plugin that is not
  installed, properties, keyframes, data tracks, settings, scene and top-level fields from a newer release)
  are kept and written back unchanged. Unknown objects show in the timeline as "Missing", can still be moved,
  grouped and deleted, and are not drawn.
- **JSON Schema** of project files, published at `docs/schema/sciview-1.json` and on the documentation site;
  `sciview schema` writes it (with plugin types) and `sciview schema --validate FILE [--strict]` checks files.
- **Migrations**: a registry of conversions for changes that are not additive, run when older files are
  opened, with a note of what was converted.
- **Plugins**: object types (`sciview.objects`), templates (`sciview.templates`) and voices (`sciview.tts`)
  from installed packages, listed in the editor's library and template picker. `sciview plugin list`,
  `sciview plugin new NAME` (a ready-to-install package with an object type, a template and tests),
  `SCIVIEW_NO_PLUGINS=1`. `sciview.register`, `Object2D` and `Object3D` are importable from `sciview`.
- **Notebooks**: `film.preview()` (plain HTML with play, scrubber and chapter buttons; works without
  extensions and stays in the notebook), `sciview.jupyter.edit(film)` (the editor inside the notebook) and
  `%load_ext sciview` with `%sciview preview|still|edit`.
- **Rendering on several computers**: `sciview render --part I/N` and `sciview join`, which puts the pieces
  together without re-encoding and adds the sound, chapters and subtitles (`export(..., part=)`, `join()`).
- **Bug reports without telemetry**: "Save a report for a bug" in the editor's help and
  `sciview info --report FILE [--assets]` write a zip with the film, its problems and the versions.
- **Keyboard**: Alt+arrows move the selected clips by a frame (Shift: a second), `[` and `]` start or end them
  at the playhead; timeline rows can be reached with Tab and the arrow keys and selected with Enter, and
  screen readers announce their name, type and timing.
- **Documentation site** on GitHub Pages, built by a workflow, with a **gallery** of every template rendered
  as a film with its project to download; new pages: Notebooks, Plugins, Gallery, Stability.
- GitHub Codespaces configuration: try the editor without installing anything.
- `GOVERNANCE.md`, `.zenodo.json`, a conda-forge recipe (`packaging/conda-forge/meta.yaml`), the `schema`
  extra, and an updated JOSS paper.
- Tests: template files from every release since 0.1 must open, save identically and render; reference frames
  of every template (visual regression); the editor's interpolation checked against Python's in Node; the
  loader and the expression parser fuzzed.

### Changed
- MP4 export picks an H.264 encoder that works: libx264, else OpenH264, the system's or a graphics card's
  encoder, else MPEG-4, so an LGPL-only ffmpeg (`SCIVIEW_FFMPEG`) works too.
- Export starts fewer render processes when large frames (4K and up) would need more than 60 % of the
  computer's memory.
- The editor accepts the host name of GitHub Codespaces and of proxies listed in `SCIVIEW_ALLOWED_HOSTS`.
- Expressions that cannot be evaluated (wrong number of arguments, a function without brackets) raise a clear
  `ExpressionError` instead of a Python error.
- Text is laid out with Pillow's basic engine on every platform, so a film looks the same, and its text takes
  the same room, on Windows, macOS and Linux (Pillow used raqm only where its build had it). Set
  `SCIVIEW_TEXT_LAYOUT=raqm` for scripts that need shaping, such as Arabic or Devanagari.

### Fixed
- Damaged project files no longer stop loading: unreadable settings, scenes, cameras and objects are reported
  and replaced by defaults (or kept as they are, for objects); file names the system cannot look up count as
  missing files.
- A scene with no transition length in its file could not be drawn.

## [0.4.0] - 2026-11-23

Storytelling and production: scenes, narration, captions that follow your voice, themes, export for every
destination, and an AI assistant panel in the editor.

### Added
- **Scenes**: a film is a list of scenes, each with its own objects, camera and clock, joined by transitions
  (cut, crossfade, dip to the background, wipe and push in four directions, zoom through). A strip above the
  timeline switches between them, adds, renames, reorders, duplicates and deletes them; playback crosses from
  one scene into the next. Scenes carry speaker notes and can be chapters. Python: `film.add_scene(...)`,
  `scene.add(...)`, `film.timeline()`, `film.chapters()`.
- **Chapter markers** in MP4, WebM and ProRes exports, one per chapter scene.
- **Narration**: voice clips (`voice`) with volume, trim and fades, recorded from the microphone in the editor
  (<kbd>R</kbd>) while the film plays, or uploaded. The timeline shows their waveforms and snaps clips to the
  phrases found in them. The preview plays the mixed sound in sync, and exports include the same mix.
- **Captions from a script**: paste what you said and the captions are laid onto the phrases of the
  recording, in order (or follow at reading speed). `sciview.narration.captions_from_script`.
- **Text to speech** for draft narration: **Read aloud** on captions, with pyttsx3 (`sciview[tts]`), espeak-ng,
  macOS `say` or the Windows voices, and engines from other packages through the `sciview.tts` entry point.
- **Caption styles**: plain, box, band, outline and shadow.
- **Readability and layout checks**: text whose contrast with what is behind it is below the WCAG ratio,
  text that overlaps text, objects outside the frame. In the editor (**Check readability and layout**), in
  `sciview check --frames` and in `sciview.checks`.
- **Subtitle modes**: drawn only, drawn plus `.srt`/`.vtt` files, a subtitle track viewers can switch off
  (not drawn), or both.
- **Transparent export**: ProRes 4444 `.mov`, WebM with alpha and RGBA PNG frames, glow included.
- **Export presets**: slides (1080p), conference (4K), poster still (4K PNG), square and vertical for social
  media (cropped around **Crop centre**, with matching guides in the preview, plus a title-safe guide),
  transparent overlay, web page and preview GIF. `sciview render --for ...`, `film.render(..., target=...)`;
  with a preset, `scale` is a factor of the preset's size.
- **Themes and brand kits**: `.sciview-theme.json` files with palette, background, font, logo and the look of
  new titles, captions and labels. Built in: Dark, Light paper and High contrast. Apply them from the film
  settings, `sciview theme --apply`, or `film.apply_theme(...)`; save your own with **Save as theme**,
  `sciview theme --save` or `film.save_theme(...)`.
- **Logo** on top of the film: corner, size, margin, opacity, and all scenes or only the first and last.
- **Web page export** (`.html`): one self-contained page with the video, captions, a chapter menu and the
  project with its files to download.
- **PowerPoint export** (`.pptx`, needs `sciview[pptx]`): one slide per scene with its clip, set to play when
  the slide appears, and the scene's notes, scripts or captions as speaker notes.
- **Assistant panel** in the editor: a chat with a language model served on your computer by Ollama,
  LM Studio, llama.cpp, vLLM or any OpenAI-compatible server. It works through the checked tools, limited to
  the whole film, the current scene or the selection; after each round SciView checks the film and the frames
  and tells the model what to fix; changes show live; values the model chose itself are listed for review;
  each request is one undo step.
- **Assistant benchmark**: 42 tasks checked automatically, `python -m sciview.agent.bench --model ...`.
- New assistant tools: `add_scene`, `set_scene`, `align`, `check_frames`, and a scene argument for
  `add_object` and `render_frame`. `sciview mcp --scene` limits an outside assistant to one scene.
- Template **Explainer in scenes**: question, method and result as three scenes with transitions and notes.
- `pptx` and `tts` extras.

### Changed
- Times of objects and keyframes count from the start of their scene. Films with one scene are saved exactly
  as in 0.3, and 0.3 files open as one scene.
- The film's length is the sum of its scenes minus the transition overlaps; set each scene's length in its
  own settings.
- The CLI reports export, theme and sound errors as short messages instead of tracebacks.
- The renderer draws each scene on its own and blends them during transitions; cached layers are kept per
  scene.

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
