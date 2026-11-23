---
title: 'SciView: scientific explainer videos from a visual editor or Python'
tags:
  - Python
  - scientific visualization
  - science communication
  - animation
  - neutron imaging
authors:
  - name: Oriol Sans Planell
    # Replace with your ORCID before submission
    orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  # Replace with your institution before submission
  - name: Your institution, City, Country
    index: 1
date: 23 November 2026
bibliography: paper.bib
---

# Summary

SciView is an open-source tool for making short explainer videos about scientific methods and results. A film
is built from objects that scientists already think in (particle beams, samples, detectors, images, charts,
equations and captions) placed in a 2D frame or a 3D scene, timed on a timeline and animated with keyframes.
Films can be made in a browser-based editor that needs no programming, or generated from Python so that the
content follows the data. Both routes share one human-readable project format, and the same renderer
produces the editor preview and the final video, so what the author sees is exactly what is exported.

SciView is written in Python on NumPy [@harris2020array], OpenCV [@opencv] and Pillow [@pillow]. Frames are
rendered as pure functions of time, which makes any instant reproducible on its own and lets exports run in
parallel on all processor cores. Videos are encoded with FFmpeg [@ffmpeg] to MP4, WebM, ProRes, GIF or PNG
sequences, with narration recorded in the editor, chapter markers, subtitle tracks, transparent video for
compositing, and as a self-contained web page or a PowerPoint deck with one slide per scene.

# Statement of need

Talks, lectures, video abstracts and outreach increasingly rely on animation to explain how an experiment or
an analysis works: how a beam forms an image, how a calibration turns a gray level into a concentration, how a
joint histogram separates materials that single measurements confuse. Most researchers still explain these
ideas with static slides, because the available tools are designed for other users. Manim [@manim] produces
excellent mathematical animations but requires writing Python for every scene and installing LaTeX and Cairo.
Blender [@blender] can render anything but takes considerable time to learn and has no notion of charts or
data. General motion-graphics software is commercial and not reproducible. Plotting libraries such as
Matplotlib [@hunter2007matplotlib] can animate figures but not compose a narrated film, and visualization
applications such as ParaView [@ahrens2005paraview] target large 3D datasets rather than explanation.

SciView addresses researchers who want results comparable to hand-crafted explainer films without becoming
animators or graphics programmers. Its object library is specific to science communication: particle beams
with scattering, detector screens whose image builds up count by count with Poisson statistics, chart axes
with animatable ranges, curves defined by expressions that may depend on time, markers that follow a curve
with live value labels, marginal histograms, threshold lines, LaTeX equations rendered through Matplotlib's
mathtext, and a text markup for subscripts, superscripts and symbols in every label. Data enter the films
directly from CSV, NumPy and image files, including 16-bit TIFF radiographs.

Several design choices aim at the wider scientific community rather than at programmers. Installation is a
single `pip install` with no system dependencies, as FFmpeg is provided by the `imageio-ffmpeg` package. The
editor runs in any modern browser and is served by a local Python process, which also allows it to run on a
remote analysis machine through an SSH tunnel. Project files are plain JSON that can be versioned and
reviewed. Expressions in project files are parsed and validated rather than executed, so films can be shared
safely. Captions can be exported as subtitles, which makes the resulting videos more accessible.

Beyond imaging, SciView includes volumes with slice planes and isosurfaces, tomographic sinograms and
back-projection that builds up angle by angle, molecules from PDB and XYZ files, ray optics through lenses and
mirrors, charts with error bars, uncertainty bands and fitted curves, and properties driven by measured time
series. Longer films are organised in scenes with transitions, and narration recorded in the browser can be
turned into captions that follow the speaker's phrases. Films can be previewed and edited inside Jupyter
notebooks, extended by plugins that add object types and templates, and built with the help of a local
language model that works through the same checked operations as the editor.

SciView grew out of the renderer written for two explainer films on neutron imaging, and its templates
reproduce the main patterns of such films: an imaging beamline, an explainer in scenes, a step-by-step
quantitative analysis, tomography, a scatter plot with thresholds, animated equations, ray optics, a 3D
structure and a title card.

# Design

A project contains film settings, a colour palette, an orbiting camera and an ordered list of objects. Each
object type declares its properties once as a schema; the schema drives validation of project files, the
Python API and the automatically generated property inspector of the editor, so a new object type requires
only its property list and a drawing method. Any numeric, vector or colour property can be keyframed with one
of several easing functions, and every object has enter and exit effects (fade, slide, pop, draw-on and
type-on).

The renderer composites anti-aliased geometry drawn with OpenCV into a floating-point canvas. Objects also
emit light into a separate buffer that is blurred at several scales and added back, producing a glow that
keeps thin lines legible on dark backgrounds. Particles are accumulated into density maps and compressed with
$1 - e^{-x}$, so dense beams saturate smoothly instead of clipping. 3D objects are projected by a pinhole
camera and sorted back to front, and 2D overlays are positioned in pixels of the design frame, so a film can
be exported at any resolution without changing its layout. Objects that do not change between frames are
cached as layers, which never changes a pixel but makes the preview interactive.

The file format is versioned and documented by a JSON Schema. Readers keep the parts of a file they do not
know, so films made with newer versions or with plugins survive being opened and saved by older ones, and the
test suite loads the files of every release, compares rendered frames with references on all platforms, and
fuzzes the loader and the expression parser.

# Acknowledgements

We acknowledge the developers of NumPy, OpenCV, Pillow, Matplotlib and FFmpeg, on which SciView is built, and
the authors of the Poppins and Inter typefaces bundled with it.

# References
