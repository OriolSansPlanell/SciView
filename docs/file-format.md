# Project file format

A film is one UTF-8 JSON file, by convention `<name>.sciview.json`, plus the files it refers to (usually in an
`assets/` folder next to it). Paths inside the file are relative to the project file. The format is plain
enough to diff in git and to generate from other programs.

```json
{
  "sciview": "1.0",
  "settings": {
    "title": "Neutron imaging", "author": "", "width": 1920, "height": 1080, "fps": 30, "duration": 16.0,
    "background": "#03070e", "background2": "#111a2c", "background_style": "radial",
    "stars": 0.4, "vignette": 0.35, "bloom": 0.7, "font": "Poppins",
    "audio": "", "audio_offset": 0.0, "audio_volume": 1.0
  },
  "palette": { "teal": "#4fd1c5", "gold": "#ffcf4a", "...": "..." },
  "camera": {
    "props": { "target": [-20, 0, 0], "fov": 28, "offset": [0, -10] },
    "keys": { "azimuth": [ { "t": 0, "v": -130, "ease": "smooth" }, { "t": 9, "v": -116, "ease": "in_out" } ] }
  },
  "objects": [
    {
      "id": "screen1", "type": "screen", "name": "Detector",
      "props": { "center": [34, 0, 0], "size": [22, 22], "image": "assets/radiograph.png", "colormap": "gold" },
      "keys": { "buildup": [ { "t": 4, "v": 0, "ease": "linear" }, { "t": 11, "v": 1, "ease": "linear" } ] },
      "start": 1.6, "end": null,
      "enter": { "effect": "fade", "duration": 0.6 },
      "exit": { "effect": "fade", "duration": 0.6 }
    }
  ]
}
```

## Fields

* `sciview`: format version (see [Versions and migrations](#versions-and-migrations)).
* `settings`: film settings (see the [reference](objects.md#film-settings)). Missing values take defaults.
* `palette`: colour names usable in any colour property.
* `camera`: `props` and `keys` of the camera.
* `objects`: in drawing order (later objects are drawn on top; 3D objects are always drawn before 2D ones and
  sorted by distance to the camera). Each object has:
  * `id` (unique, used by references such as a curve's `axes`), `type`, `name`;
  * `props`: only values that differ from the defaults are written;
  * `keys`: per property, a list of `{"t": seconds, "v": value, "ease": name}` sorted by time. The ease
    says how the value moves into that keyframe; `"ease": "bezier"` comes with `"bez": [x1, y1, x2, y2]`,
    a curve as in CSS `cubic-bezier()` (x1 and x2 between 0 and 1, y1 and y2 may leave that range to
    overshoot);
  * `start`, `end` (`null` = until the end), `enter` and `exit` effects;
  * optional `parent`: the id of the group the object belongs to (an object of type `group`). Groups add
    their transform, opacity, effects and visible span to their members. Members usually sit next to their
    group in the list, but drawing order is still the list order;
  * optional `visible: false` and `locked: true`;
  * optional `tracks`: properties that follow table columns over time (see below).

A data track, here a counter that follows a temperature log recorded in minutes:

```json
{ "id": "text1", "type": "text", "props": { "text": "T = {value:.0f} K" },
  "tracks": { "value": { "data": "assets/furnace.csv", "time": "minutes", "column": "temperature",
                         "time_scale": 60.0, "time_offset": 2.0, "scale": 1.0, "offset": 0.0, "smooth": true } } }
```

At film time `t` the table is read at `(t - time_offset) * time_scale` in units of the time column, the value
is interpolated (`smooth: false` holds each row) and becomes `value * scale + offset`. Vector properties name
two or three columns, `"column": "x, y, z"`. The camera can have `tracks` too.

A file field may hold a pattern (`*`, `?` or `[...]`) instead of one path, such as `"assets/run/out_*.csv"`:
the object shows one file per step, in natural order. The step shown is `step + steps_per_second × (time since
the object appeared)`, so either property can drive it.

A **Matplotlib figure** stores only the name of the Python function that draws it (`"callback"`), never code,
and a `snapshot` picture used when that function is not available.

### Scenes

A film with more than one scene lists them under `"scenes"`, in order, and every object says which scene it
belongs to:

```json
{
  "sciview": "1.0",
  "settings": { "duration": 19.0, "...": "..." },
  "camera": { "props": { "azimuth": -130 } },
  "scenes": [
    { "id": "scene1", "name": "Question", "duration": 6 },
    { "id": "scene2", "name": "Method", "duration": 8, "transition": "crossfade", "transition_duration": 1.0,
      "notes": "Explain the beamline",
      "camera": { "props": { "azimuth": -130 }, "keys": { "azimuth": [ { "t": 8, "v": -100 } ] } } },
    { "id": "scene3", "name": "Result", "duration": 7, "transition": "wipe_left", "chapter": true }
  ],
  "objects": [
    { "id": "title1", "type": "title", "scene": "scene1", "props": { "text": "Why neutrons see water" } },
    { "id": "box1", "type": "box", "scene": "scene2", "start": 0.5 }
  ]
}
```

* A scene has an `id`, a `name`, a `duration` in seconds, the `transition` into it (`cut`, `crossfade`, `dip`,
  `wipe_left`, `wipe_right`, `wipe_up`, `wipe_down`, `push_left`, `push_right`, `push_up`, `push_down`,
  `zoom`) with its `transition_duration`, `chapter` (default `true`) and `notes`. Defaults are left out.
* The first scene's camera is the top-level `camera`; later scenes carry their own `camera`.
* Objects' `start`, `end` and keyframe times count from the start of their scene.
* `settings.duration` is written as the length of the whole film (scenes minus the transition overlaps), for
  programs that do not know about scenes.
* A film with a single scene has no `"scenes"` list and no `"scene"` on its objects, exactly as in 0.3.
  An object whose scene does not exist is put in the first scene with a warning.

### Styles

`"styles"` holds the look a theme gives to new objects, per type:

```json
"styles": { "caption": { "style": "box", "size": 34 }, "title": { "color": "gold" } }
```

`settings` also has `theme` (the name of the theme last applied), the logo (`logo`, `logo_position`,
`logo_size`, `logo_margin`, `logo_opacity`, `logo_scenes`) and `crop_x`, the centre of square and vertical
exports (`-1` = the middle).

A theme file (`.sciview-theme.json`) holds `"sciview_theme": 1`, a `name` and `description`, a `palette`,
the `settings` it changes (background, font, glow ...), `styles` and an optional `logo` with its image as a
path next to the theme file or as a `data:` URI.

### Groups

A group in the list:

```json
{ "id": "group1", "type": "group", "name": "Step 1",
  "props": { "offset": [0, 0], "scale": 1.0, "pivot": [80, 170] },
  "keys": { "opacity": [ { "t": 6, "v": 1 }, { "t": 7, "v": 0.45 } ] } },
{ "id": "panel1", "type": "panel", "parent": "group1", "props": { "title": "Gray level" } }
```

Files from SciView 0.1 open unchanged; files using groups or custom curves open in 0.1 with warnings about the
unknown `group` type and fall back to smooth easing.

Files from SciView 0.2 open unchanged in 0.3. Files using the new object types, data tracks or file patterns
open in 0.2 with warnings about what it does not know.

Files from every release open unchanged in 1.0, and films with one scene are saved in the 0.3 form.
Files from SciView 0.3 open unchanged in 0.4. In 0.3, a
0.4 file opens with notes about the settings and object types it does not know (logo, theme, voice clips);
the objects of later scenes all start from 0 s there, because 0.3 does not shift them by their scene.

Values: numbers, booleans, strings; colours as `"#rrggbb"` or a palette name; vectors as lists; `array`
properties as lists of numbers or as text (`"1, 2, 3"`).

## Versions and migrations

`"sciview": "1.0"` is the format version. Within format 1.x, new releases only add things, so every 1.x
release reads every earlier file (see [Stability](stability.md)). Parts a release does not know are **kept**:

* an object of an unknown type (a plugin that is not installed, an object from a newer release) stays in the
  file as it is, is listed in the timeline with a warning, can still be moved in time or grouped, and is not
  drawn;
* unknown properties, keyframes and data tracks of known objects, unknown settings, unknown scene fields and
  unknown top-level fields are written back unchanged.

So a film made with a newer SciView or with a plugin can be opened, edited and saved without losing anything.
A file from a newer format (1.3, say) opens with a note saying so.

If a later release has to change something in a way that is not additive, it adds a migration: a function
that converts files of the older format when they are opened (`sciview.model.migrate`). The editor and
`sciview check` say what was converted. Template files from every release since 0.1 are kept in the tests
(`tests/golden`) and must open, save and render in every new release.

## Checking files against the schema

The format is described by a JSON Schema, published at
[`schema/sciview-1.json`](schema/sciview-1.json) (`https://oriolsansplanell.github.io/SciView/schema/sciview-1.json`),
for programs that write SciView files and for editors that complete and check JSON.

```bash
sciview schema --validate film.sciview.json             # needs: pip install jsonschema
sciview schema --validate film.sciview.json --strict    # also reject what this version does not know
sciview schema -o sciview-1.json                         # the schema, with the types of installed plugins
```

By default the schema accepts what format 1.x readers must accept (unknown settings, properties and types);
`--strict` describes exactly what this version writes.

## Robustness

Problems in a file produce warnings (shown by `sciview check` and in the editor) instead of errors. A part
that cannot be read (a property of the wrong kind, a scene without a usable length, a damaged object) is
reported and replaced by a default, or kept unchanged when it is a whole object. A `parent` that is missing,
is not a group or makes groups contain each other in a circle is reported and ignored. Expressions are parsed
and checked, never executed as Python, so opening a project from someone else is safe; the test suite fuzzes
both the loader and the expression parser.
