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

* `sciview`: format version. Files with the same major version load; newer minor versions may add properties.
* `settings`: film settings (see the [reference](objects.md#film-settings)). Missing values take defaults.
* `palette`: colour names usable in any colour property.
* `camera`: `props` and `keys` of the camera.
* `objects`: in drawing order (later objects are drawn on top; 3D objects are always drawn before 2D ones and
  sorted by distance to the camera). Each object has:
  * `id` (unique, used by references such as a curve's `axes`), `type`, `name`;
  * `props`: only values that differ from the defaults are written;
  * `keys`: per property, a list of `{"t": seconds, "v": value, "ease": name}` sorted by time;
  * `start`, `end` (`null` = until the end), `enter` and `exit` effects;
  * optional `visible: false` and `locked: true`.

Values: numbers, booleans, strings; colours as `"#rrggbb"` or a palette name; vectors as lists; `array`
properties as lists of numbers or as text (`"1, 2, 3"`).

## Robustness

Unknown object types and properties produce warnings (shown by `sciview check` and in the editor) instead of
errors, so files written by a newer SciView still open. Expressions are parsed and checked, never executed as
Python, so opening a project from someone else is safe.
