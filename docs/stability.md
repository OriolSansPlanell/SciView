# Stability

From 1.0, SciView follows [semantic versioning](https://semver.org/). Within 1.x, films, scripts and plugins
written for an earlier 1.x release keep working; anything that would break them waits for 2.0.

## What is promised

| Part | Promise within 1.x |
| --- | --- |
| **Project files** | Every 1.x release opens files from every earlier release, 0.1 included. New releases only add settings, object types and properties. Parts a release does not know (from a newer release or a missing plugin) are kept and written back unchanged. |
| **Python API** | `sciview.Project` and its documented methods, `sciview.load`, `sciview.preview`, scenes (`add_scene` and the `Scene` methods), the object methods (`set`, `key`, `appear`, `disappear`, `track`), `sciview.export.export`, `join`, `TARGETS`, `sciview.theme`, `sciview.narration`, `sciview.audio`, `sciview.checks`, `sciview.jupyter`, `sciview.schema` and `sciview.agent.FilmTools`, as described in the [Python guide](python-api.md). |
| **Plugin API** | The entry-point groups, `sciview.register`, `Prop`, `SceneObject`, `Object2D`, `Object3D` and the `draw(cv, ctx, v, st)` arguments described in [Plugins](plugins.md). |
| **Command line** | Commands and options keep their meaning; new options may be added. |
| **Object types** | Types and properties are not removed or renamed. Their look may improve; the [visual tests](https://github.com/OriolSansPlanell/SciView/tree/main/tests/golden/frames) make every such change deliberate. |
| **AI tools** | The MCP and assistant tools keep their names and arguments. |

Not covered: the editor's internal web API and JavaScript, module paths not listed above (such as
`sciview.engine` or `sciview.render` internals) and the exact pixels of a frame.

## Changes that are not additive

If a change cannot be additive, it comes with a [migration](file-format.md#versions-and-migrations): older
files are converted when they are opened, and the editor says what was converted. Python functions that are
replaced keep working with a `DeprecationWarning` for at least one minor release before 2.0 removes them.

## How this is checked

* Template files from every release since 0.1 (`tests/golden/0.1` …) are opened, saved, compared and
  rendered by the test suite on Windows, macOS and Linux with Python 3.10 to 3.14.
* Every file this version writes is checked against the published [JSON Schema](schema/sciview-1.json).
* Reference frames of every template catch unintended changes to how films look.
* The editor's interpolation is checked against Python's on the same cases, in Node.
* Damaged files and odd expressions are fuzzed: SciView opens what it can and says what it could not read.
