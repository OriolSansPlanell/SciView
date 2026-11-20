# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [semantic versioning](https://semver.org/).

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
