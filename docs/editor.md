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
| **Scenes** (above the timeline) | The film's scenes in order, with the transition between each pair. Click one to work on it. |
| **Timeline** (bottom) | One row per object of the current scene, the top row drawn on top. Clips show when objects are visible, diamonds are keyframes. |
| **Assistant** (right, when open) | A chat with a language model on your computer that builds or changes the film. |

## Selecting and moving

* Click an object in the preview or its row in the timeline to select it. <kbd>Esc</kbd> selects nothing.
* <kbd>Shift</kbd>-click adds an object to the selection or takes it out, in the preview and in the timeline.
  <kbd>Ctrl</kbd>-drag (<kbd>Cmd</kbd> on a Mac) on empty space in the preview selects everything inside a
  box; <kbd>Ctrl</kbd>+<kbd>A</kbd> selects every object.
* Drag objects in the preview to move them, 2D and 3D alike. A 3D object moves in the plane facing the camera,
  so it stays under the mouse; hold <kbd>Shift</kbd> to move along one axis only (the screen axis for 2D
  objects, the scene axis closest to the drag for 3D ones). Dragging one of several selected objects moves
  them all.
* Drag empty space to orbit the camera, or hold <kbd>Alt</kbd> to orbit even over an object;
  <kbd>Shift</kbd>+drag on empty space shifts the 3D scene on screen; scroll to zoom. If the camera is
  animated, these changes add a camera keyframe at the playhead.
* Drag a value's label left or right to change a number (<kbd>Shift</kbd> for big steps, <kbd>Alt</kbd> for
  fine ones). Arrow keys in a number field do the same.

### Several objects

With more than one object selected, the properties panel offers:

* **Arrange**: align left edges, centres or right edges, tops, middles or bottoms, and spread three or more
  objects so the gaps between them are equal. These use where the objects are in the picture at the
  playhead.
* **Stagger**: start each object a set delay after the one before, keyframes included. Objects that start
  earlier go first, then the order they were added.
* Values shared by all of them, when they are of one kind: a change applies to every selected object.
* **Group**, **Duplicate** and **Delete**.

### Groups

A group holds objects that belong together: a panel and the chart on it, the parts of an instrument.
Select them and press <kbd>Ctrl</kbd>+<kbd>G</kbd>; <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> takes
them out again. The group's members keep all their own values, and the group adds to them:

* **Offset** and **scale** (about the **pivot**) for 2D members, and **position**, **rotation** and
  **scale** (about the 3D pivot) for 3D members. These can be keyframed like anything else.
* **Opacity**, **enter and exit effects** and **when it is visible**: a group that fades out fades all its
  members; members show only while their group does.

Clicking a grouped object in the preview selects its group, so a drag moves the whole group. Double-click
to select the object inside it; <kbd>Esc</kbd> goes back up to the group. In the timeline, members sit
under their group's row and the arrow folds them away; moving the group's clip moves its members' clips
too. To put an object in a group, pick the group under **In group** in its **Timing** section, or drag its
row just below the group's row. Groups can contain groups.

### Copy and paste

<kbd>Ctrl</kbd>+<kbd>C</kbd>, <kbd>Ctrl</kbd>+<kbd>X</kbd> and <kbd>Ctrl</kbd>+<kbd>V</kbd> copy, cut and
paste the selection, between films too. A group comes with its members; a curve copied with its chart
keeps drawing in the copied chart. Pasted objects keep their timing relative to the playhead: an object
that started a second after the playhead when you copied it starts a second after the playhead where you
paste it. With a keyframe picked in the timeline, copy takes that keyframe instead, and paste adds it to the
selected objects at the playhead.

## Timing

Each object has a clip on the timeline:

* Drag the clip to move it in time; its keyframes move with it.
* Drag its left or right edge to change when it appears or disappears.
* The shaded ends of a clip are the enter and exit effects. Choose them in **Timing** in the properties panel:
  fade, slide (four directions), pop, **draw on** (lines, shapes, charts, 3D wireframes) and **type on**
  (text). An exit effect plays only when the object has a disappear time.
* Drag the grip at the left of a row to change the drawing order.

Clips snap to frames, to the playhead and to the start and end of the film.

## Scenes

A film is made of scenes laid end to end: the question, the method, the result. Each scene has its own
objects, its own camera and its own clock, so the timeline, the time box and the keyframes all count from
the start of the scene you are working on. That keeps a long film manageable: moving the second scene
does not shift anything in the third.

* Click a scene in the strip above the timeline to work on it; the preview and the timeline switch to it.
  Playing runs on into the next scene, through the transition.
* **+ Scene** adds a scene after the current one. It starts with the camera where the previous scene
  ended. Double-click a scene to rename it.
* Click the current scene again, or the transition before it, to see its settings in the properties panel:
  name, length, the **transition** into it (cut, crossfade, dip to the background, wipe or push in four
  directions, zoom through) and how long it takes, whether it is a **chapter**, and **notes** for what to
  say. There you can also move it earlier or later, duplicate it or delete it.
* A transition overlaps the end of the previous scene: with a one-second crossfade, the last second of
  scene 1 fades into the first second of scene 2. The total length of the film is shown at the end of the
  strip.

Chapters become chapter markers in MP4 files (video players list them), the chapter menu of the web page
export and one slide each in the PowerPoint export. Scene notes go into the speaker notes.

## Sound and narration

* Drop an audio file on the preview, or set **Audio** in the film settings, for music under the whole
  film. **Voice clips** (in the library under Sound) belong to a scene and play from their clip's start;
  each has a volume, a trim (where in the file to start) and fades.
* **Record narration**: press the microphone button on the timeline, or <kbd>R</kbd>. The film plays from
  the playhead while you speak; press it again to stop. The take is saved in the assets folder and placed as
  a voice clip where you started. The browser asks once for the microphone.
* Voice clips show their waveform on the timeline, and the phrases found in it become snapping points:
  drag any clip (a caption, say) near the start or end of a phrase and it snaps there.
* **Captions from a script**: select a voice clip and choose **Captions from the script…**, paste what you
  said (one caption per line; long lines are split at the ends of sentences) and the captions are laid onto
  the phrases of the recording, in order. Without a recording (select a caption and use the same button) they
  follow each other at reading speed from the playhead. The script is kept with the clip and becomes the
  speaker notes in PowerPoint.
* **Read aloud** on a caption makes a voice clip from its text with a text-to-speech engine, if one is
  installed (`pip install "sciview[tts]"`, or espeak-ng on Linux, or the voices built into macOS and
  Windows). It is meant for drafts: record your own voice for the final film.

The preview plays all of it mixed, in sync; exports include the same mix.

## Captions and readability

Captions have a **style**: plain, **box** (a panel behind the text), **band** (a strip across the frame),
**outline** or **shadow**. The box and band take a background colour and opacity. Use a box or band when
captions sit over busy images.

**Check readability and layout** in the film settings looks at frames of every scene and lists text that
does not stand out enough from what is behind it (a contrast ratio below 4.5, the level asked for by
accessibility guidelines), text that overlaps other text and objects that leave the frame. Click a line to
go to the object.

## Themes and logos

The **Look** section of the film settings starts with the themes: **Dark** (the default), **Light paper**
for printed figures and **High contrast** for projectors in bright rooms. A theme sets the palette, the
background, the font and how new titles, captions and labels look; with **Restyle objects** ticked it also
restyles the ones already in the film (locked objects are left alone). Applying a theme is one undo step.

**Save as theme** downloads the film's look, logo included, as a `.sciview-theme.json` file to share with
your group; **Load theme…** applies one. The **Logo** section places a picture (a PNG with transparency
works best) in a corner of every frame, of the first and last scenes or of only one of them.

## Guides

The **Guides** menu under the preview draws the **title-safe** area (the part every screen shows) or the
part kept by a **square** or **vertical** export. Set **Crop centre** in the film settings to move that part
sideways.

## Keyframes

Any number, colour or position can change over time:

1. Move the playhead and click the diamond next to a value. The label turns gold: the value is animated.
2. Move the playhead elsewhere and change the value. A new keyframe is added there automatically.
3. Gold diamonds appear on the object's clip. Drag them to retime, click one to jump to it, press
   <kbd>Del</kbd> to delete the selected one.
4. The **Keyframes** group lists them all; choose how each one eases in (smooth, linear, in, out, in-out,
   overshoot, hold ...). Choose **custom** to draw the curve yourself: drag its two handles, type the four
   numbers or start from a preset. Handles above the box overshoot. The numbers are those of CSS
   `cubic-bezier()`, so curves can be copied to and from web animation tools.

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
the names found in the file. Volumes (`.npy`, TIFF stacks, HDF5) go in a **Volume**, and PDB or XYZ files in a
**Molecule**.

### Series of files

Upload several files at once in a file field and they become a sequence, shown one file per step: a time
series of images, the outputs of a simulation. The field then holds a pattern such as
`assets/run/step_*.csv` (choose **File pattern…** to type one). Files are taken in natural order, so
`step_2` comes before `step_10`. Set **Steps per second** to play the files from the moment the object appears,
or keyframe **Step** to choose which file shows when (both can be combined). Tables with the same number of rows are blended between
files, so points move smoothly.

## Data tracks

A data track makes a property follow a column of a table over time instead of keyframes: a temperature log
that drives a counter, a measured trajectory, the intensity of a source. Under **Data tracks** in the
properties panel, choose the property and press **Add**, then pick the table, the **time column** (in seconds
of the film; shift it with **Starts at** and stretch it with **Time scale**) and the **value column**. For an
x, y or x, y, z property, give two or three columns separated by commas. **Scale** and **Offset** convert the
values. Properties driven by data are marked "⟵ data" in blue, and a track takes the place of the
property's keyframes. The camera's tracks can be set from Python (`film.camera.track(...)`).

## Problems

A warning sign on a timeline row means something stops that object from drawing as intended: a file that
is missing, an expression that cannot be read, a chart that no longer exists. Select the object: the
properties panel says what is wrong and marks the field to fix in gold. The count under the preview lists
every problem in the film; click one to jump to its object.

## The assistant panel

**Assistant** in the top bar opens a chat with a language model that builds and changes the film for you:
"add a title card for this scene", "make the captions bigger and put them in boxes", "line up the three
panels", "add a scene that zooms into the sample". The model runs on your own computer with
[Ollama](https://ollama.com), LM Studio, a llama.cpp server or vLLM (any server that speaks the OpenAI
chat API), so nothing leaves your computer unless you point it at a hosted server.

1. Start the server and download a model that can call tools, for example `ollama pull gemma4:31b`.
   Models around 30 billion parameters follow instructions much better than small ones.
2. Open the panel, press the settings button, choose the server and the model (**Find models** lists what
   the server has) and save. **Let the model see frames** sends it pictures of what it made; leave it on for
   models that read images.
3. Type a request and press <kbd>Enter</kbd>.

You see each step as it happens, and every change appears in the preview at once. After each round of
changes SciView looks at the film itself (missing files, expressions it cannot read, text that overlaps or
leaves the frame) and tells the model, which then fixes what it got wrong. When it is done:

* **What changed** lists the objects it added or changed; click one to select it.
* **Please check** lists numbers and wording the model chose itself rather than taking from your
  request or your data. Look at them before you show the film: the model is told not to invent scientific
  values, but it can.
* The whole request is **one undo step**: <kbd>Ctrl</kbd>+<kbd>Z</kbd> takes it all back.

**May change** under the input limits the request to the whole film, the current scene or the selected
objects. Locked objects are never touched, and you cannot edit the film while a request runs (press the stop
button to end it early).

## Working with an outside assistant

An AI assistant connected with `sciview mcp --editor http://localhost:8765` (see [AI assistants](agent.md))
changes the film in the open editor. Each of its changes appears within about a second, with a short note of
what it did. Press Ctrl+Z to take back a change you do not want: **Undo** treats it like your own edits
(changes that arrive within the same second are undone together). If you edit something at the same moment,
your edit is kept and the assistant's change is made again on top of it. Locked objects are never touched by
the assistant.

## Autosave

Every 30 seconds, and when the editor stops, unsaved changes are written next to the film as a hidden file
(`.film.sciview.json.autosave`). If the editor stops before you save, the next time you open the film it
offers to **restore** those changes or **discard** them. Restored changes are not saved until you press
Save, and saving removes the autosave.

## Film settings

Select nothing to edit the size, frame rate, background, starfield, vignette, glow strength, font, logo and
soundtrack, and to apply a theme. The length of the film is the sum of its scenes (set each scene's length
in its own settings). The **palette** names colours used across the film: change `teal` once and everything
teal follows.

## Exporting

**Export video** offers presets for the usual destinations, and the format, size and quality by hand:

| Preset | You get |
| --- | --- |
| Slides (1080p) | MP4, 1920 × 1080 |
| Conference (4K) | MP4, 3840 × 2160 |
| Poster still (4K) | one PNG frame at the playhead |
| Square (social) | MP4, 1080 × 1080, the sides cut (see the square guide) |
| Vertical (social) | MP4, 1080 × 1920, the sides cut (see the vertical guide) |
| Transparent overlay | ProRes 4444 with an alpha channel, to lay over slides or footage |
| Web page | one HTML page with the video, captions, chapters and the project |
| Preview GIF | 640 × 360 GIF |

With a preset chosen, **Size** is a fraction of the preset's size. The other choices: **Captions** drawn in
the picture, also as an `.srt`/`.vtt` file, as subtitles viewers can switch off, or both; a **transparent
background** (ProRes, WebM or PNG frames); **chapter markers** from the scenes; and **PowerPoint**, one slide
per scene (needs `pip install "sciview[pptx]"`). See [Rendering and sharing](rendering.md).

## Shortcuts

| Keys | Action |
| --- | --- |
| <kbd>Space</kbd> | play / pause |
| <kbd>←</kbd> <kbd>→</kbd> | previous / next frame (<kbd>Shift</kbd>: one second) |
| <kbd>Home</kbd> <kbd>End</kbd> | start / end |
| <kbd>K</kbd> | keyframe all values of the selection |
| <kbd>R</kbd> | record narration from the playhead / stop recording |
| <kbd>Del</kbd> | delete the selected keyframe, or the selected objects (a group with its members) |
| <kbd>Ctrl</kbd>+<kbd>D</kbd> | duplicate |
| <kbd>Ctrl</kbd>+<kbd>C</kbd> / <kbd>X</kbd> / <kbd>V</kbd> | copy, cut, paste objects or the picked keyframe |
| <kbd>Ctrl</kbd>+<kbd>G</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd> | group / ungroup |
| <kbd>Ctrl</kbd>+<kbd>A</kbd> | select every object |
| <kbd>Shift</kbd>+click | add to or take out of the selection |
| double-click | select an object inside its group |
| <kbd>Esc</kbd> | leave the group, then select nothing |
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
