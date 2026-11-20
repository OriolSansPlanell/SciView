# Object reference

Generated from the code by `tools/gen_docs.py`. Every property can be set in the editor's inspector, in a project file under `props`, or from Python with `film.add(type, **props)` / `obj.set(name, value)`.
Animatable properties can be keyframed: `obj.key(name, time, value, ease)`.

Positions of 2D objects are in pixels of the film frame (1920 x 1080 by default, origin at the top-left). 3D objects use scene units (centimetres in the examples) with z pointing up.

Every object also has timing: `start`, `end` (empty = until the end of the film), an enter effect and an exit effect with durations. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`; objects that can be drawn on also accept `draw`, text objects accept `typewriter`.

## 3D scene

- [Box](#box) (`box`): Wireframe box with see-through faces: sources, detectors, instruments.
- [Cylinder](#cylinder) (`cylinder`): Wireframe cylinder: samples, tubes, vessels, pipes.
- [Sphere](#sphere) (`sphere`): Wireframe sphere: atoms, nuclei, droplets, planets.
- [Screen / detector](#screen) (`screen`): A flat panel that can show an image: detectors, scintillators, samples, slides.
- [Particle beam](#beam) (`beam`): Particles streaking from a source to a target, with optional scattering on the way.
- [3D arrow / line](#arrow3d) (`arrow3d`): A straight line or arrow between two points in the scene: axes, vectors, rays.
- [Floor grid](#grid3d) (`grid3d`): A grid in a horizontal plane that gives the scene a floor.
- [Point cloud](#pointcloud) (`pointcloud`): 3D points from a table (x, y, z columns): atoms, simulation particles, scans.
- [3D model (STL/OBJ)](#mesh) (`mesh`): Import an STL or OBJ model of an instrument or sample, drawn as wireframe or solid.
- [3D label](#label3d) (`label3d`): Text pinned to a point in the scene, with an optional leader line.

<a id="box"></a>
### Box (`box`)

Wireframe box with see-through faces: sources, detectors, instruments.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `size` | x, y, z | (10, 10, 10) | yes |  |
| `rotation` | x, y, z | (0, 0, 0) | yes | Degrees about x, y and z |
| `edge_color` | colour | teal | yes |  |
| `edge_width` | number (0..20) | 2 | yes |  |
| `fill_color` | colour | teal | yes |  |
| `fill_opacity` | number (0..1) | 0.08 | yes |  |
| `glow` | number (0..4) | 1 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="cylinder"></a>
### Cylinder (`cylinder`)

Wireframe cylinder: samples, tubes, vessels, pipes.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `radius` | number (0..) | 5 | yes |  |
| `height` | number (0..) | 12 | yes |  |
| `rotation` | x, y, z | (0, 0, 0) | yes | Degrees; the axis is z before rotation |
| `rings` | whole number (2..40) | 2 | yes | Circles along the height |
| `lines` | whole number (0..64) | 0 | yes | Extra lines along the length |
| `edge_color` | colour | cream | yes |  |
| `edge_width` | number (0..20) | 1.5 | yes |  |
| `fill_color` | colour | cream | yes |  |
| `fill_opacity` | number (0..1) | 0.06 | yes |  |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="sphere"></a>
### Sphere (`sphere`)

Wireframe sphere: atoms, nuclei, droplets, planets.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `radius` | number (0..) | 6 | yes |  |
| `rotation` | x, y, z | (0, 0, 0) | yes |  |
| `meridians` | whole number (0..48) | 6 | yes |  |
| `parallels` | whole number (0..48) | 5 | yes |  |
| `edge_color` | colour | blue | yes |  |
| `edge_width` | number (0..20) | 1.2 | yes |  |
| `fill_color` | colour | blue | yes |  |
| `fill_opacity` | number (0..1) | 0.12 | yes |  |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="screen"></a>
### Screen / detector (`screen`)

A flat panel that can show an image: detectors, scintillators, samples, slides.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `size` | x, y | (20, 20) | yes | Width and height |
| `rotation` | x, y, z | (0, 0, 0) | yes | Degrees. At 0 the panel faces along x |
| `thickness` | number (0..) | 0 | yes | Depth of a housing behind the panel |
| `frame_color` | colour | teal | yes |  |
| `frame_width` | number (0..20) | 2 | yes |  |
| `fill_color` | colour | navy | yes |  |
| `fill_opacity` | number (0..1) | 0.35 | yes |  |
| `glow` | number (0..4) | 1 | yes |  |
| `image_opacity` | number (0..1) | 1 | yes |  |
| `image` | file | empty |  | PNG, JPG, TIFF (16-bit is fine) or .npy array |
| `colormap` | choice | gray |  | Used for single-channel images Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `vmin` | number | 0 | yes | Data value shown black. vmin = vmax uses the data range |
| `vmax` | number | 0 | yes |  |
| `gamma` | number (0.1..5) | 1 | yes |  |
| `buildup` | number (0..1) | 1 | yes | Animate from 0 to 1 to build the image up count by count |
| `counts` | number (0..) | 0 | yes | Counts per bright pixel for the build-up noise. 0 = smooth fade |
| `pixelated` | on/off | off |  | Show pixels as sharp squares |
| `image_glow` | number (0..3) | 0.35 | yes |  |
| `flip` | on/off | off |  | Mirror the image left-right |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="beam"></a>
### Particle beam (`beam`)

Particles streaking from a source to a target, with optional scattering on the way.

Default enter effect: `none`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | x, y, z | (-60, 0, 0) | yes |  |
| `target` | x, y, z | (0, 0, 0) | yes |  |
| `source_radius` | number (0..) | 1.5 | yes | Beam radius at the source |
| `target_radius` | number (0..) | 4 | yes | Beam radius at the target (cone) |
| `rate` | number (0..5000) | 220 |  | Particles per second |
| `speed` | number (0.01..) | 30 |  | Scene units per second |
| `streak` | number (0..) | 4 | yes | Streak length in scene units |
| `color` | colour | gold | yes |  |
| `brightness` | number (0..4) | 1 | yes |  |
| `size` | number (0.3..8) | 1.1 | yes | Streak softness in pixels |
| `glow` | number (0..4) | 1.2 | yes |  |
| `scatter_fraction` | number (0..1) | 0 | yes | Share of particles that scatter |
| `scatter_at` | number (0..1) | 0.5 | yes | Where along the path they scatter (0 = source, 1 = target) |
| `scatter_range` | number (0..) | 25 | yes | How far scattered particles travel |
| `scatter_color` | colour | amber | yes |  |
| `seed` | whole number (0..100000) | 1 |  |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="arrow3d"></a>
### 3D arrow / line (`arrow3d`)

A straight line or arrow between two points in the scene: axes, vectors, rays.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `tail` | x, y, z | (0, 0, 0) | yes |  |
| `tip` | x, y, z | (20, 0, 0) | yes |  |
| `color` | colour | cream | yes |  |
| `width` | number (0..20) | 2 | yes |  |
| `head_size` | number (0..80) | 14 | yes | Pixels; 0 for a plain line |
| `dashed` | on/off | off |  |  |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="grid3d"></a>
### Floor grid (`grid3d`)

A grid in a horizontal plane that gives the scene a floor.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y, z | (0, 0, -15) | yes |  |
| `size` | x, y | (160, 100) | yes |  |
| `divisions` | whole number (1..200) | 16 | yes |  |
| `color` | colour | blue | yes |  |
| `line_opacity` | number (0..1) | 0.18 | yes |  |
| `width` | number (0..10) | 1 | yes |  |
| `fade_edges` | on/off | on |  |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="pointcloud"></a>
### Point cloud (`pointcloud`)

3D points from a table (x, y, z columns): atoms, simulation particles, scans.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ with x, y, z columns |
| `x_column` | text | x |  |  |
| `y_column` | text | y |  |  |
| `z_column` | text | z |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `z_values` | numbers | empty |  |  |
| `center` | x, y, z | (0, 0, 0) | yes | Where the data origin goes |
| `scale` | number (0..) | 1 | yes |  |
| `rotation` | x, y, z | (0, 0, 0) | yes |  |
| `color` | colour | ice | yes |  |
| `color_by` | text | empty |  | Column used for colour (with a colormap) |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `size` | number (0.3..40) | 3 | yes | Point radius in pixels |
| `style` | choice | glow |  | Options: `glow`, `solid`. |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="mesh"></a>
### 3D model (STL/OBJ) (`mesh`)

Import an STL or OBJ model of an instrument or sample, drawn as wireframe or solid.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `model` | file | empty |  | STL or OBJ file |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `scale` | number (0..) | 1 | yes |  |
| `rotation` | x, y, z | (0, 0, 0) | yes |  |
| `style` | choice | solid+edges |  | 'edges' shows only sharp creases, which reads well for CAD parts Options: `wire`, `solid`, `solid+edges`, `edges`. |
| `color` | colour | teal | yes |  |
| `fill_opacity` | number (0..1) | 0.35 | yes |  |
| `edge_color` | colour | teal | yes |  |
| `edge_width` | number (0..10) | 1.2 | yes |  |
| `feature_angle` | number (0..180) | 30 | yes |  |
| `glow` | number (0..4) | 0.6 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="label3d"></a>
### 3D label (`label3d`)

Text pinned to a point in the scene, with an optional leader line.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `typewriter`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `point` | x, y, z | (0, 0, 0) | yes |  |
| `text` | text | Label |  |  |
| `size` | number (6..160) | 20 | yes |  |
| `color` | colour | cream | yes |  |
| `weight` | choice | regular |  | Options: `light`, `regular`, `medium`, `bold`. |
| `offset` | x, y | (30, -40) | yes | Text position relative to the point, in pixels |
| `leader` | on/off | on |  | Line from the point to the text |
| `dot` | on/off | on |  |  |
| `line_color` | colour | gray | yes |  |
| `glow` | number (0..4) | 0.3 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Text

- [Title](#title) (`title`): Section title with an optional subtitle, top-left.
- [Caption](#caption) (`caption`): Narration line at the bottom of the frame. Also exported as subtitles (.srt).
- [Text](#text) (`text`): Free text. Use {value} or {value:.1f} to show an animated number (counters).
- [Equation (LaTeX)](#equation) (`equation`): A formula in LaTeX syntax, rendered with matplotlib's mathtext (no LaTeX install needed).
- [Legend](#legend) (`legend`): Colour key. One entry per line: colour | label.

<a id="title"></a>
### Title (`title`)

Section title with an optional subtitle, top-left.

Default enter effect: `slide_up`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `typewriter`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `text` | text | Title |  |  |
| `subtitle` | text | empty |  |  |
| `position` | x, y | (80, 60) | yes |  |
| `title_size` | number (8..200) | 46 | yes |  |
| `subtitle_size` | number (6..120) | 22 | yes |  |
| `title_color` | colour | gold | yes |  |
| `subtitle_color` | colour | cream | yes |  |
| `weight` | choice | bold |  | Options: `light`, `regular`, `medium`, `bold`. |
| `align` | choice | left |  | Options: `left`, `center`, `right`. |
| `glow` | number (0..3) | 0.15 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="caption"></a>
### Caption (`caption`)

Narration line at the bottom of the frame. Also exported as subtitles (.srt).

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `typewriter`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `text` | text (lines) | A caption explains what is happening. |  |  |
| `position` | x, y | (960, 1000) | yes | Centre of the text |
| `size` | number (8..120) | 30 | yes |  |
| `color` | colour | cream | yes |  |
| `weight` | choice | regular |  | Options: `light`, `regular`, `medium`, `bold`. |
| `max_width` | number (0..) | 1500 | yes | Wrap width in pixels (0 = no wrap) |
| `background_color` | colour | navy | yes |  |
| `background_opacity` | number (0..1) | 0 | yes |  |
| `glow` | number (0..3) | 0 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="text"></a>
### Text (`text`)

Free text. Use {value} or {value:.1f} to show an animated number (counters).

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `typewriter`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `text` | text (lines) | Text |  | Markup: H_2O, ^6Li, x_{max}, \alpha, **bold**. {value:.2f} shows the Value below |
| `value` | number | 0 | yes | Animate it to make a counter |
| `position` | x, y | (960, 540) | yes |  |
| `size` | number (4..300) | 36 | yes |  |
| `color` | colour | cream | yes |  |
| `weight` | choice | regular |  | Options: `light`, `regular`, `medium`, `bold`. |
| `align` | choice | left |  | Options: `left`, `center`, `right`. |
| `valign` | choice | top |  | Options: `top`, `middle`, `bottom`, `baseline`. |
| `line_spacing` | number (0.6..3) | 1.25 | yes |  |
| `max_width` | number (0..) | 0 | yes | Wrap width in pixels (0 = no wrap) |
| `rotation` | number (-360..360) | 0 | yes | Degrees |
| `background_color` | colour | navy | yes |  |
| `background_opacity` | number (0..1) | 0 | yes |  |
| `glow` | number (0..3) | 0 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="equation"></a>
### Equation (LaTeX) (`equation`)

A formula in LaTeX syntax, rendered with matplotlib's mathtext (no LaTeX install needed).

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `tex` | text (lines) | \mu = -\frac{\ln T}{d} |  | LaTeX math, e.g. E = mc^2 or \frac{a}{b} |
| `position` | x, y | (960, 540) | yes |  |
| `size` | number (6..300) | 44 | yes |  |
| `color` | colour | cream | yes |  |
| `align` | choice | center |  | Options: `left`, `center`, `right`. |
| `valign` | choice | middle |  | Options: `top`, `middle`, `bottom`. |
| `font` | choice | dejavusans |  | Options: `dejavusans`, `cm`, `stix`, `stixsans`, `dejavuserif`. |
| `glow` | number (0..3) | 0.1 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="legend"></a>
### Legend (`legend`)

Colour key. One entry per line: colour | label.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `typewriter`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `entries` | text (lines) | teal \| Plastic (polyethylene) / gray... |  | One per line: colour \| label |
| `position` | x, y | (1500, 300) | yes |  |
| `size` | number (6..80) | 18 | yes |  |
| `text_color` | colour | cream | yes |  |
| `swatch` | choice | square |  | Options: `square`, `circle`, `line`. |
| `spacing` | number (1..4) | 1.6 | yes |  |
| `glow` | number (0..3) | 0.3 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Charts

- [Chart axes](#axes) (`axes`): A coordinate frame. Add curves, scatter, bars and markers that point to it.
- [Curve](#curve) (`curve`): A line from an expression like exp(-x/2) (t is time, for moving waves) or from data.
- [Scatter](#scatter) (`scatter`): Points from a table or typed values. The draw effect makes them appear one by one.
- [Bar chart](#bars) (`bars`): Bars from typed values; the draw effect grows them from the baseline.
- [Histogram](#histogram) (`histogram`): Histogram of a data column, vertical or along the y axis (for marginal histograms).
- [Marker](#marker) (`marker`): A dot at (x, y) in a chart, with guide lines and a live label. Animate x to move it along a curve.
- [Threshold line](#guide) (`guide`): A vertical or horizontal line across a chart at a data value (thresholds, references).

<a id="axes"></a>
### Chart axes (`axes`)

A coordinate frame. Add curves, scatter, bars and markers that point to it.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `position` | x, y | (1020, 220) | yes | Top-left corner of the plot area |
| `size` | x, y | (720, 460) | yes |  |
| `x_range` | x, y | (0, 10) | yes | Animate to zoom or pan |
| `y_range` | x, y | (0, 1) | yes |  |
| `log_x` | on/off | off |  |  |
| `log_y` | on/off | off |  |  |
| `x_label` | text | x |  |  |
| `y_label` | text | y |  |  |
| `title` | text | empty |  |  |
| `x_ticks` | whole number (0..30) | 5 | yes | About how many ticks (0 = none) |
| `y_ticks` | whole number (0..30) | 4 | yes |  |
| `tick_labels` | on/off | on |  |  |
| `font_size` | number (6..60) | 18 | yes |  |
| `label_color` | colour | cream | yes |  |
| `frame` | choice | L |  | Options: `L`, `box`, `none`. |
| `grid` | on/off | on |  |  |
| `color` | colour | gray | yes |  |
| `line_width` | number (0..10) | 1.5 | yes |  |
| `grid_opacity` | number (0..1) | 0.12 | yes |  |
| `background_opacity` | number (0..1) | 0 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="curve"></a>
### Curve (`curve`)

A line from an expression like exp(-x/2) (t is time, for moving waves) or from data.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `source` | choice | expression |  | Options: `expression`, `data`. |
| `expression` | text | exp(-x/3) |  | y as a function of x (and time t): sin(x - 2*t), gauss(x, 5, 1), x^2 ... |
| `domain` | x, y | (0, 0) | yes | x range of the expression (equal values = whole axis) |
| `samples` | whole number (2..20000) | 400 | yes |  |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `color` | colour | teal | yes |  |
| `width` | number (0..30) | 3 | yes |  |
| `style` | choice | solid |  | Options: `solid`, `dashed`, `dotted`. |
| `fill_opacity` | number (0..1) | 0 | yes | Shade under the curve |
| `glow` | number (0..4) | 1 | yes |  |
| `clip` | on/off | on |  | Hide what falls outside the axes |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="scatter"></a>
### Scatter (`scatter`)

Points from a table or typed values. The draw effect makes them appear one by one.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `color` | colour | ice | yes |  |
| `color_by` | text | empty |  | Column (from the data file) used for colour |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `size` | number (0.3..40) | 3 | yes | Radius in pixels |
| `style` | choice | glow |  | Options: `glow`, `solid`. |
| `glow` | number (0..4) | 0.6 | yes |  |
| `clip` | on/off | on |  |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="bars"></a>
### Bar chart (`bars`)

Bars from typed values; the draw effect grows them from the baseline.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `values` | numbers | 3, 5, 2, 4 |  |  |
| `positions` | numbers | empty |  | x of each bar (default 1, 2, 3 ...) |
| `labels` | text | empty |  | Comma-separated names under the bars |
| `baseline` | number | 0 | yes |  |
| `height_scale` | number (0..) | 1 | yes | Animate to change all heights |
| `color` | colour | teal | yes |  |
| `colors` | text | empty |  | Optional comma-separated colours, one per bar |
| `bar_width` | number (0.05..1) | 0.7 | yes | Fraction of the spacing |
| `fill_opacity` | number (0..1) | 0.85 | yes |  |
| `value_labels` | on/off | off |  |  |
| `value_format` | text | {value:.0f} |  |  |
| `label_size` | number (6..60) | 16 | yes |  |
| `glow` | number (0..4) | 0.4 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="histogram"></a>
### Histogram (`histogram`)

Histogram of a data column, vertical or along the y axis (for marginal histograms).

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `data` | file | empty |  |  |
| `column` | text | 0 |  |  |
| `values` | numbers | empty |  | Or type numbers |
| `bins` | whole number (1..2000) | 40 | yes |  |
| `range` | x, y | (0, 0) | yes | Bin range (equal values = axis range) |
| `orientation` | choice | vertical |  | Horizontal bars grow from the y axis Options: `vertical`, `horizontal`. |
| `normalize` | choice | max |  | 'max' scales the tallest bar to Height (a fraction of the axis) Options: `max`, `count`, `density`. |
| `height` | number (0..1) | 0.9 | yes |  |
| `color` | colour | blue | yes |  |
| `fill_opacity` | number (0..1) | 0.8 | yes |  |
| `glow` | number (0..4) | 0.5 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="marker"></a>
### Marker (`marker`)

A dot at (x, y) in a chart, with guide lines and a live label. Animate x to move it along a curve.

Default enter effect: `pop`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `x` | number | 5 | yes |  |
| `y` | number | 0.5 | yes |  |
| `follow` | text | empty |  | Optional expression: y follows f(x), e.g. exp(-x/3) |
| `size` | number (1..60) | 7 | yes |  |
| `color` | colour | white | yes |  |
| `guides` | choice | both |  | Dashed lines down to the x axis and/or across to the y axis Options: `none`, `x`, `y`, `both`. |
| `guide_color` | colour | cream | yes |  |
| `label` | text | empty |  | Can show live values: x = {x:.2f}, y = {y:.3f} |
| `label_size` | number (6..80) | 18 | yes |  |
| `label_offset` | x, y | (14, -14) | yes |  |
| `glow` | number (0..4) | 1 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="guide"></a>
### Threshold line (`guide`)

A vertical or horizontal line across a chart at a data value (thresholds, references).

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `orientation` | choice | vertical |  | Options: `vertical`, `horizontal`. |
| `value` | number | 5 | yes | Animate it to sweep the threshold |
| `color` | colour | white | yes |  |
| `width` | number (0..20) | 2.5 | yes |  |
| `dashed` | on/off | off |  |  |
| `label` | text | empty |  |  |
| `label_size` | number (6..60) | 16 | yes |  |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Shapes & media

- [Panel / card](#panel) (`panel`): Rounded card with a header and a numbered badge, for step-by-step explanations.
- [Rectangle](#rect) (`rect`): Rectangle or rounded box: highlights, regions, frames.
- [Circle / ellipse](#ellipse) (`ellipse`): Circle or ellipse: highlight a cluster, a region of interest, a spot.
- [Arrow](#arrow) (`arrow`): Straight or curved arrow pointing at something.
- [Image](#image) (`image`): A picture or data array (radiograph, slice, micrograph, logo) placed in the frame.

<a id="panel"></a>
### Panel / card (`panel`)

Rounded card with a header and a numbered badge, for step-by-step explanations.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `position` | x, y | (100, 160) | yes | Top-left corner |
| `size` | x, y | (520, 640) | yes |  |
| `radius` | number (0..200) | 16 | yes |  |
| `fill_color` | colour | navy | yes |  |
| `fill_opacity` | number (0..1) | 0.55 | yes |  |
| `border_color` | colour | gray | yes |  |
| `border_opacity` | number (0..1) | 0.35 | yes |  |
| `border_width` | number (0..20) | 1.5 | yes |  |
| `title` | text | empty |  |  |
| `title_size` | number (6..100) | 22 | yes |  |
| `title_color` | colour | cream | yes |  |
| `badge` | whole number (0..99) | 0 | yes | Number in a circle before the title (0 = none) |
| `accent` | colour | cream | yes | Badge colour |
| `glow` | number (0..3) | 0 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="rect"></a>
### Rectangle (`rect`)

Rectangle or rounded box: highlights, regions, frames.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `position` | x, y | (760, 400) | yes | Top-left corner |
| `size` | x, y | (400, 280) | yes |  |
| `radius` | number (0..500) | 0 | yes |  |
| `fill_color` | colour | teal | yes |  |
| `fill_opacity` | number (0..1) | 0 | yes |  |
| `stroke_color` | colour | cream | yes |  |
| `stroke_width` | number (0..40) | 2 | yes |  |
| `dashed` | on/off | off |  |  |
| `glow` | number (0..4) | 0.6 | yes |  |
| `axes` | object | empty |  | Pick a chart to place the shape in data coordinates |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="ellipse"></a>
### Circle / ellipse (`ellipse`)

Circle or ellipse: highlight a cluster, a region of interest, a spot.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `center` | x, y | (960, 540) | yes |  |
| `radii` | x, y | (120, 80) | yes |  |
| `rotation` | number (-360..360) | 0 | yes | Degrees |
| `fill_color` | colour | teal | yes |  |
| `fill_opacity` | number (0..1) | 0 | yes |  |
| `stroke_color` | colour | cream | yes |  |
| `stroke_width` | number (0..40) | 2 | yes |  |
| `dashed` | on/off | off |  |  |
| `glow` | number (0..4) | 0.6 | yes |  |
| `axes` | object | empty |  | Pick a chart to place the shape in data coordinates |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="arrow"></a>
### Arrow (`arrow`)

Straight or curved arrow pointing at something.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `tail` | x, y | (760, 540) | yes |  |
| `tip` | x, y | (1160, 540) | yes |  |
| `bend` | number (-800..800) | 0 | yes | Curvature in pixels |
| `color` | colour | cream | yes |  |
| `width` | number (0..40) | 3 | yes |  |
| `heads` | choice | end |  | Options: `end`, `start`, `both`, `none`. |
| `head_size` | number (0..120) | 18 | yes |  |
| `dashed` | on/off | off |  |  |
| `glow` | number (0..4) | 0.6 | yes |  |
| `axes` | object | empty |  | Pick a chart to place the arrow in data coordinates |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="image"></a>
### Image (`image`)

A picture or data array (radiograph, slice, micrograph, logo) placed in the frame.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `image` | file | empty |  | PNG, JPG, TIFF (16-bit is fine) or .npy array |
| `colormap` | choice | gray |  | Used for single-channel images Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `vmin` | number | 0 | yes | Data value shown black. vmin = vmax uses the data range |
| `vmax` | number | 0 | yes |  |
| `gamma` | number (0.1..5) | 1 | yes |  |
| `buildup` | number (0..1) | 1 | yes | Animate from 0 to 1 to build the image up count by count |
| `counts` | number (0..) | 0 | yes | Counts per bright pixel for the build-up noise. 0 = smooth fade |
| `pixelated` | on/off | off |  | Show pixels as sharp squares |
| `position` | x, y | (960, 540) | yes | Centre of the image |
| `width` | number (1..) | 420 | yes | Pixels; height follows the aspect ratio |
| `mask` | choice | none |  | Options: `none`, `circle`, `rounded`. |
| `border_color` | colour | cream | yes |  |
| `border_width` | number (0..30) | 0 | yes |  |
| `glow` | number (0..3) | 0.3 | yes | Glow of the image itself |
| `opacity` | number (0..1) | 1 | yes |  |

## Camera (`camera`)

There is one camera per film. It orbits its target point.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `target` | x, y, z | (0, 0, 0) | yes | Point the camera looks at |
| `distance` | number (0.1..) | 150 | yes |  |
| `azimuth` | number (-720..720) | -60 | yes | Degrees around the vertical axis |
| `elevation` | number (-89..89) | 22 | yes | Degrees above the floor |
| `fov` | number (1..150) | 30 | yes | Field of view in degrees |
| `offset` | x, y | (0, 0) | yes | Shift the 3D scene on screen, in pixels |

## Film settings

Stored under `settings` in the project file.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `title` | text | Untitled film |  |  |
| `author` | text | empty |  |  |
| `width` | whole number (16..7680) | 1920 | yes | Pixels. Layout is in these units |
| `height` | whole number (16..4320) | 1080 | yes |  |
| `fps` | whole number (1..120) | 30 | yes |  |
| `duration` | number (0.1..3600) | 10 | yes | Seconds |
| `background` | colour | #03070e | yes | Edge colour |
| `background2` | colour | #111a2c | yes | Centre (radial) or bottom (vertical) colour |
| `background_style` | choice | radial |  | Options: `radial`, `vertical`, `solid`. |
| `stars` | number (0..3) | 0.4 | yes | Starfield density (0 = none) |
| `vignette` | number (0..1) | 0.35 | yes |  |
| `bloom` | number (0..3) | 0.7 | yes | Strength of the glow |
| `font` | font | Poppins |  | Poppins, Inter, or a path to a .ttf/.otf file |
| `audio` | file | empty |  | Narration or music mixed into the export |
| `audio_offset` | number | 0 | yes | Seconds into the film where the audio starts |
| `audio_volume` | number (0..4) | 1 | yes |  |

## Default palette

| Name | Colour |
| --- | --- |
| `teal` | `#4fd1c5` |
| `gold` | `#ffcf4a` |
| `amber` | `#f5a23c` |
| `blue` | `#6cb4fc` |
| `ice` | `#a5e4fc` |
| `cream` | `#f3ead8` |
| `red` | `#ff6b6b` |
| `violet` | `#c38cff` |
| `green` | `#7ee08a` |
| `white` | `#ffffff` |
| `gray` | `#8b95a7` |
| `navy` | `#10182a` |
