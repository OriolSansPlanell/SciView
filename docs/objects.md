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
- [Molecule](#molecule) (`molecule`): Atoms and bonds from a PDB or XYZ file, as ball-and-stick, space-filling, sticks, wire, or a ribbon along a protein's backbone with its ligands. The draw effect builds it atom by atom.
- [Volume (3D image)](#volume) (`volume`): A 3D image from tomography, MRI or a simulation, shown as sweeping slice planes, a maximum-intensity projection, a radiograph-like projection or an isosurface.
- [3D scale bar](#scalebar3d) (`scalebar3d`): A ruler in the 3D scene with end ticks and a label in real units (one scene unit = Unit).

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
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
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
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
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

<a id="molecule"></a>
### Molecule (`molecule`)

Atoms and bonds from a PDB or XYZ file, as ball-and-stick, space-filling, sticks, wire, or a ribbon along a protein's backbone with its ligands. The draw effect builds it atom by atom.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `model` | file | empty |  | PDB or XYZ file |
| `style` | choice | ball_and_stick |  | ribbon: a smooth tube through the backbone, with ligands as ball-and-stick Options: `ball_and_stick`, `spacefill`, `sticks`, `wire`, `ribbon`. |
| `color_by` | choice | element |  | rainbow runs along each chain from start to end Options: `element`, `chain`, `rainbow`, `single`. |
| `color` | colour | teal | yes | Used when colouring by single |
| `hydrogens` | on/off | on |  |  |
| `center` | x, y, z | (0, 0, 0) | yes | Where the molecule's centre goes |
| `scale` | number (0.01..) | 2 | yes | Scene units per ångström |
| `rotation` | x, y, z | (0, 0, 0) | yes | Animate it to turn the molecule |
| `atom_scale` | number (0.05..1.5) | 0.3 | yes | Ball size as a fraction of the van der Waals radius (ball-and-stick) |
| `bond_radius` | number (0.02..1) | 0.16 | yes | In ångström |
| `ribbon_radius` | number (0.05..3) | 0.5 | yes | In ångström |
| `glow` | number (0..3) | 0.15 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="volume"></a>
### Volume (3D image) (`volume`)

A 3D image from tomography, MRI or a simulation, shown as sweeping slice planes, a maximum-intensity projection, a radiograph-like projection or an isosurface.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `data` | file | empty |  | .npy array (z, y, x), multi-page TIFF, HDF5 (.h5), or a pattern of slices such as slices/*.png |
| `dataset` | text | empty |  | HDF5 only: the dataset inside the file (empty = the first 3D one) |
| `mode` | choice | slices |  | slices: up to three planes; mip: brightest value along each line of sight; projection: the average, like a radiograph; isosurface: the surface at Threshold Options: `slices`, `mip`, `projection`, `isosurface`. |
| `max_size` | whole number (16..1024) | 192 | yes | Voxels along the longest side used for drawing: larger is sharper and slower |
| `samples` | whole number (8..512) | 128 | yes | Planes sampled for mip and projection |
| `center` | x, y, z | (0, 0, 0) | yes |  |
| `size` | number (0.01..) | 40 | yes | Length of the longest side, in scene units |
| `spacing` | x, y, z | (1, 1, 1) | yes | Voxel size along x, y and z, for scans with thicker slices |
| `rotation` | x, y, z | (0, 0, 0) | yes |  |
| `slice_x` | number (0..1) | 0.5 | yes | Where the slice across x sits (0 to 1). Animate it to sweep through the sample |
| `slice_y` | number (0..1) | 0.5 | yes |  |
| `slice_z` | number (0..1) | 0.5 | yes |  |
| `show_x` | on/off | on |  |  |
| `show_y` | on/off | on |  |  |
| `show_z` | on/off | on |  |  |
| `slice_opacity` | number (0..1) | 1 | yes |  |
| `colormap` | choice | gray |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `vmin` | number | 0 | yes | Value shown darkest; vmin = vmax uses the 1st to 99.5th percentile |
| `vmax` | number | 0 | yes |  |
| `gamma` | number (0.1..5) | 1 | yes |  |
| `clear_below` | number (0..1) | 0 | yes | Values below this fraction of the range become see-through (air around a sample) |
| `threshold` | number (0..1) | 0.5 | yes | Isosurface level as a fraction of vmin..vmax. Animate it to peel layers away |
| `iso_color` | colour | teal | yes |  |
| `iso_opacity` | number (0..1) | 0.95 | yes |  |
| `smoothness` | whole number (1..6) | 1 | yes | Marching-cubes step: larger gives fewer, smoother triangles |
| `outline` | on/off | on |  |  |
| `outline_color` | colour | teal | yes |  |
| `outline_width` | number (0..10) | 1.5 | yes |  |
| `glow` | number (0..4) | 0.3 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |
| `label` | text | empty |  | Text shown next to the object. Markup: H_2O, ^6Li, \alpha |
| `label_color` | colour | cream | yes |  |
| `label_size` | number (6..120) | 20 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `left`, `right`, `center`. |
| `label_offset` | x, y | (0, 0) | yes | Extra shift in pixels |

<a id="scalebar3d"></a>
### 3D scale bar (`scalebar3d`)

A ruler in the 3D scene with end ticks and a label in real units (one scene unit = Unit).

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `origin` | x, y, z | (-20, -20, 0) | yes | Where the bar starts |
| `direction` | x, y, z | (1, 0, 0) | yes | Direction of the bar (normalised) |
| `length` | number (0..) | 10 | yes | In scene units |
| `unit` | text | 1 mm |  | What one scene unit is in reality, such as 1 mm or 0.1 nm |
| `color` | colour | white | yes |  |
| `width` | number (0.5..20) | 3 | yes |  |
| `tick_size` | number (0..) | 2 | yes | End ticks, in scene units |
| `label_size` | number (6..80) | 20 | yes |  |
| `digits` | whole number (1..6) | 3 | yes |  |
| `glow` | number (0..4) | 0.6 | yes |  |
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
| `text` | text (lines) | Text |  | Markup: H_2O, ^6Li, x_{max}, \alpha, **bold**. {value:.2f} shows the Value below, {value:si:m} with an SI prefix (2.5 mm), {t:.1f} the film time |
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
- [Matplotlib figure](#figure) (`figure`): A matplotlib figure drawn by your Python function at every frame (film.add_figure in a script). The editor shows the snapshot saved with the project.
- [Heatmap](#heatmap) (`heatmap`): A map of values on a chart, from an expression z(x, y, t) or a 2D array, image or CSV grid.
- [Colour bar](#colorbar) (`colorbar`): The key to a colormap. Point it at a heatmap, image, volume or 2D histogram to follow its range.
- [Error bars](#errorbars) (`errorbars`): Data points with vertical (and optionally horizontal) error bars from columns or typed values.
- [Uncertainty band](#band) (`band`): A shaded band around a curve: centre ± spread from expressions, or lower and upper columns.
- [Fitted curve](#fit) (`fit`): A model fitted to data (linear, polynomial, exponential, Gaussian, power, logistic), with an optional label showing the fitted parameters and R².
- [Spectrum](#spectrum) (`spectrum`): A spectrum (data or expression) with its peaks found automatically or listed, each with a label.
- [2D histogram](#hist2d) (`hist2d`): Counts of (x, y) pairs in a grid of bins, coloured by a colormap: joint histograms, density maps.
- [Vector field](#vectorfield) (`vectorfield`): Arrows on a grid showing a field u(x, y), v(x, y): flows, forces, gradients. Animate with t.
- [Streamlines](#streamlines) (`streamlines`): Lines that follow a field u(x, y), v(x, y), drawn on with the draw effect; Flow speed moves dashes along them like tracer particles.

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
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
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
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
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

<a id="figure"></a>
### Matplotlib figure (`figure`)

A matplotlib figure drawn by your Python function at every frame (film.add_figure in a script). The editor shows the snapshot saved with the project.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `callback` | text | empty |  | Name of the Python function (set by film.add_figure) |
| `snapshot` | file | empty |  | Picture shown where the function is not available (saved automatically) |
| `still` | on/off | off |  | The figure does not change with time: draw it once |
| `style` | choice | sciview |  | sciview: transparent background and light text; matplotlib: your own style Options: `sciview`, `matplotlib`. |
| `position` | x, y | (960, 540) | yes | Centre |
| `size` | x, y | (800, 500) | yes | Width and height in pixels |
| `dpi` | number (20..600) | 100 | yes | Pixels per inch at full size: larger makes text and lines smaller |
| `glow` | number (0..3) | 0 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="heatmap"></a>
### Heatmap (`heatmap`)

A map of values on a chart, from an expression z(x, y, t) or a 2D array, image or CSV grid.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `source` | choice | expression |  | Options: `expression`, `data`. |
| `expression` | text | exp(-((x-5)^2 + (y-0.5)^2*100)/6) |  | z as a function of x, y (and time t) |
| `data` | file | empty |  | 2D .npy array, image or CSV grid; the top row is the highest y |
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `x_extent` | x, y | (0, 0) | yes | x range the data covers (equal values = the chart's) |
| `y_extent` | x, y | (0, 0) | yes |  |
| `resolution` | whole number (8..1200) | 160 | yes | Samples across, for an expression |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `vmin` | number | 0 | yes | Equal vmin and vmax use the data range |
| `vmax` | number | 0 | yes |  |
| `log_color` | on/off | off |  |  |
| `clear_below` | number (0..1) | 0 | yes | Values below this fraction of the range are see-through |
| `smooth` | on/off | on |  | Blend between cells (off = sharp cells) |
| `glow` | number (0..3) | 0.2 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="colorbar"></a>
### Colour bar (`colorbar`)

The key to a colormap. Point it at a heatmap, image, volume or 2D histogram to follow its range.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | object | empty |  | Copy colormap and range from this object |
| `colormap` | choice | viridis |  | Used without a source Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `vmin` | number | 0 | yes |  |
| `vmax` | number | 1 | yes |  |
| `label` | text | empty |  |  |
| `unit` | text | empty |  | With a unit, tick labels use SI prefixes: 2 mm, 500 µm |
| `position` | x, y | (1780, 260) | yes | Top-left corner |
| `size` | x, y | (26, 420) | yes | Thickness and length |
| `orientation` | choice | vertical |  | Options: `vertical`, `horizontal`. |
| `ticks` | whole number (0..20) | 5 | yes |  |
| `font_size` | number (6..60) | 18 | yes |  |
| `label_color` | colour | cream | yes |  |
| `border_color` | colour | gray | yes |  |
| `glow` | number (0..3) | 0.2 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="errorbars"></a>
### Error bars (`errorbars`)

Data points with vertical (and optionally horizontal) error bars from columns or typed values.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `y_error` | text | empty |  | Column with the y uncertainty, or one number for all points |
| `y_error_values` | numbers | empty |  | Or type them: 0.1, 0.2, 0.15 |
| `x_error` | text | empty |  | Optional x uncertainty: a column or one number |
| `color` | colour | gold | yes |  |
| `width` | number (0.3..12) | 2 | yes |  |
| `cap` | number (0..40) | 8 | yes | Cap width in pixels |
| `points` | on/off | on |  | Draw the data points |
| `point_size` | number (0.5..30) | 5 | yes |  |
| `glow` | number (0..4) | 0.5 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="band"></a>
### Uncertainty band (`band`)

A shaded band around a curve: centre ± spread from expressions, or lower and upper columns.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `source` | choice | expression |  | Options: `expression`, `data`. |
| `center` | text | exp(-x/3) |  | Centre as a function of x (and t) |
| `spread` | text | 0.05 + 0.02*x |  | Half-width of the band, a function of x (and t) |
| `domain` | x, y | (0, 0) | yes | x range (equal values = the whole chart) |
| `data` | file | empty |  |  |
| `x_column` | text | x |  |  |
| `lower_column` | text | lower |  |  |
| `upper_column` | text | upper |  |  |
| `color` | colour | teal | yes |  |
| `fill_opacity` | number (0..1) | 0.25 | yes |  |
| `center_line` | on/off | on |  | Draw the centre (expression) or mid line (data) |
| `edges` | on/off | off |  | Thin lines along the band's edges |
| `width` | number (0..20) | 2.5 | yes |  |
| `glow` | number (0..4) | 0.6 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="fit"></a>
### Fitted curve (`fit`)

A model fitted to data (linear, polynomial, exponential, Gaussian, power, logistic), with an optional label showing the fitted parameters and R².

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `model` | choice | linear |  | Options: `linear`, `quadratic`, `cubic`, `exponential`, `gaussian`, `power`, `logistic`. |
| `extend` | on/off | off |  | Draw across the whole chart, not just the data's x range |
| `color` | colour | red | yes |  |
| `width` | number (0.3..20) | 2.5 | yes |  |
| `style` | choice | dashed |  | Options: `solid`, `dashed`, `dotted`. |
| `glow` | number (0..4) | 0.6 | yes |  |
| `label` | text | empty |  | Shows the fit: {formula}, {a:.3g}, {b:.3g}, {c:.3g}, {d:.3g}, {r2:.4f} |
| `label_at` | x, y | (0.04, 0.06) | yes | Where the label goes, as fractions of the chart |
| `label_size` | number (6..60) | 18 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="spectrum"></a>
### Spectrum (`spectrum`)

A spectrum (data or expression) with its peaks found automatically or listed, each with a label.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `source` | choice | data |  | Options: `data`, `expression`. |
| `expression` | text | gauss(x, 3, 0.2) + 0.6*gauss(x, 6.4, ... |  | Intensity as a function of x |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `peaks` | numbers | empty |  | x of the peaks to label (empty = found automatically) |
| `prominence` | number (0.001..1) | 0.1 | yes | Automatic peaks must stand this fraction of the y range above their surroundings |
| `max_peaks` | whole number (0..50) | 8 | yes |  |
| `peak_labels` | text | empty |  | Comma-separated names, one per peak (else the x value) |
| `label_format` | text | {x:.3g} |  | Label of peaks without a name |
| `label_size` | number (6..60) | 16 | yes |  |
| `label_color` | colour | cream | yes |  |
| `marker_color` | colour | gold | yes |  |
| `color` | colour | teal | yes |  |
| `width` | number (0..20) | 2 | yes |  |
| `fill_opacity` | number (0..1) | 0.15 | yes |  |
| `glow` | number (0..4) | 0.8 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="hist2d"></a>
### 2D histogram (`hist2d`)

Counts of (x, y) pairs in a grid of bins, coloured by a colormap: joint histograms, density maps.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `data` | file | empty |  | CSV/TSV/NPY/NPZ table |
| `x_column` | text | x |  | Column name or number |
| `y_column` | text | y |  |  |
| `x_values` | numbers | empty |  | Or type numbers: 0, 1, 2, 3 |
| `y_values` | numbers | empty |  |  |
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `bins` | x, y | (60, 60) | yes | Bins along x and y; the range is the chart's |
| `colormap` | choice | magma |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `log_color` | on/off | on |  | Colour by log(count): faint populations stay visible |
| `clear_empty` | on/off | on |  | Empty bins are see-through |
| `smooth` | on/off | off |  |  |
| `glow` | number (0..3) | 0.3 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="vectorfield"></a>
### Vector field (`vectorfield`)

Arrows on a grid showing a field u(x, y), v(x, y): flows, forces, gradients. Animate with t.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `u` | text | -y + 0.5 |  | x component of the field, a function of x, y (and t) |
| `v` | text | x - 5 |  | y component |
| `grid` | x, y | (18, 12) | yes | Arrows across and up |
| `length` | number (0.05..5) | 0.9 | yes | Longest arrow as a fraction of the grid spacing |
| `normalize` | on/off | off |  | All arrows the same length; colour shows the strength |
| `color` | colour | ice | yes |  |
| `color_by_strength` | on/off | on |  |  |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `width` | number (0.3..10) | 2 | yes |  |
| `head_size` | number (0..40) | 8 | yes |  |
| `glow` | number (0..4) | 0.5 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="streamlines"></a>
### Streamlines (`streamlines`)

Lines that follow a field u(x, y), v(x, y), drawn on with the draw effect; Flow speed moves dashes along them like tracer particles.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `axes` | object | empty |  | The chart this series is drawn in |
| `u` | text | -y + 0.5 |  | x component of the field, a function of x, y (and t) |
| `v` | text | x - 5 |  | y component |
| `seeds` | whole number (1..1000) | 40 | yes | Number of lines, started on a jittered grid |
| `steps` | whole number (10..3000) | 300 | yes | Maximum points per line |
| `color` | colour | teal | yes |  |
| `color_by_strength` | on/off | off |  |  |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `width` | number (0.3..10) | 2 | yes |  |
| `flow_speed` | number (0..) | 0 | yes | Pixels per second the dashes travel (0 = solid lines) |
| `dash` | number (2..200) | 18 | yes | Dash length when flowing |
| `glow` | number (0..4) | 0.7 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Imaging

- [Sinogram](#sinogram) (`sinogram`): A tomography scan recorded projection by projection: animate Progress from 0 to 1 while the sample turns. Pair it with Back-projection to rebuild the slice.
- [Back-projection](#backprojection) (`backprojection`): The slice rebuilt from a sinogram, one projection at a time (filtered back-projection). Choose no filter to show why the filter is needed.
- [Scale bar](#scalebar) (`scalebar`): A bar of known length for an image (from its pixel size) or a chart (from its data units), labelled with SI prefixes: 100 µm, 2.5 mm.
- [Points into a chart](#morph) (`morph`): Points that fly from an image's pixels (or a scatter plot) into a chart: a scatter of two images' values, a joint histogram, or a stack of histogram bins. Animate Progress.

<a id="sinogram"></a>
### Sinogram (`sinogram`)

A tomography scan recorded projection by projection: animate Progress from 0 to 1 while the sample turns. Pair it with Back-projection to rebuild the slice.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | choice | phantom |  | phantom: the Shepp-Logan test head; image: your own slice (made square) Options: `phantom`, `image`. |
| `image` | file | empty |  | The slice to scan when Source is image |
| `resolution` | whole number (32..512) | 192 | yes | Pixels across the slice |
| `angles` | whole number (2..720) | 180 | yes | Number of projections in the scan |
| `angle_range` | number (1..360) | 180 | yes | Degrees covered by the scan |
| `progress` | number (0..1) | 1 | yes | Fraction of the scan recorded so far. Animate it from 0 to 1 |
| `position` | x, y | (1300, 540) | yes | Centre |
| `size` | x, y | (420, 420) | yes | Width (detector) and height (angle) |
| `colormap` | choice | gray |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `show_current` | on/off | on |  | Highlight the projection being recorded |
| `current_color` | colour | gold | yes |  |
| `profile` | on/off | off |  | Plot the current projection above the sinogram |
| `labels` | on/off | on |  | Name the axes: detector position and angle |
| `label_size` | number (6..60) | 18 | yes |  |
| `label_color` | colour | cream | yes |  |
| `border_color` | colour | teal | yes |  |
| `border_width` | number (0..10) | 1.5 | yes |  |
| `glow` | number (0..3) | 0.2 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="backprojection"></a>
### Back-projection (`backprojection`)

The slice rebuilt from a sinogram, one projection at a time (filtered back-projection). Choose no filter to show why the filter is needed.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `sinogram` | object | empty |  | The scan to rebuild |
| `follow` | on/off | on |  | Rebuild as far as the sinogram has recorded |
| `progress` | number (0..1) | 1 | yes | Fraction of the projections used, when not following the sinogram |
| `filter` | choice | ramp |  | 'none' gives the blurred plain back-projection Options: `ramp`, `shepp-logan`, `cosine`, `hann`, `none`. |
| `position` | x, y | (1300, 540) | yes | Centre |
| `size` | x, y | (420, 420) | yes |  |
| `colormap` | choice | gray |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `show_angle` | on/off | on |  | Draw the direction of the latest projection |
| `angle_color` | colour | gold | yes |  |
| `border_color` | colour | teal | yes |  |
| `border_width` | number (0..10) | 1.5 | yes |  |
| `glow` | number (0..3) | 0.2 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="scalebar"></a>
### Scale bar (`scalebar`)

A bar of known length for an image (from its pixel size) or a chart (from its data units), labelled with SI prefixes: 100 µm, 2.5 mm.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `reference` | object | empty |  | The image or chart the bar measures |
| `pixel_size` | text | 1 µm |  | Image: the size of one image pixel (0.65 µm). Chart: what one data unit is (1 mm) |
| `length` | text | empty |  | Bar length such as 100 µm (empty = a round length near 20% of the width) |
| `position` | x, y | (1700, 960) | yes | Centre of the bar |
| `thickness` | number (1..40) | 6 | yes |  |
| `color` | colour | white | yes |  |
| `label_size` | number (6..80) | 22 | yes |  |
| `label_position` | choice | above |  | Options: `above`, `below`, `none`. |
| `digits` | whole number (1..6) | 3 | yes | Significant digits of the label |
| `glow` | number (0..4) | 0.6 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="morph"></a>
### Points into a chart (`morph`)

Points that fly from an image's pixels (or a scatter plot) into a chart: a scatter of two images' values, a joint histogram, or a stack of histogram bins. Animate Progress.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | object | empty |  | An image (its pixels) or a scatter plot (its points) already in the film |
| `image_b` | file | empty |  | A second image of the same size: its values give y in a joint scatter |
| `max_points` | whole number (10..200000) | 3000 | yes | Pixels are sampled on a grid |
| `axes` | object | empty |  | The chart the points land in |
| `target` | choice | joint |  | joint: x = value in the image, y = value in Image b (or the scatter's own points); histogram: points stack up in bins of their value Options: `joint`, `histogram`. |
| `value` | choice | x |  | For a scatter source: which value to bin Options: `x`, `y`. |
| `bins` | whole number (1..400) | 30 | yes |  |
| `height` | number (0.05..1) | 0.9 | yes | Tallest bin, as a fraction of the chart |
| `progress` | number (0..1) | 0 | yes | 0 = on the source, 1 = in the chart. Animate it from 0 to 1 |
| `stagger` | number (0..0.95) | 0.5 | yes | How spread out the departures are (0 = all together) |
| `order` | choice | random |  | Which points leave first Options: `random`, `left_to_right`, `top_to_bottom`, `by_value`. |
| `arc` | number | 0 | yes | Bend of the flight path, in pixels |
| `color_mode` | choice | value |  | value: colormap of the source value; image: the pixel's own colour Options: `value`, `single`, `image`. |
| `color` | colour | ice | yes |  |
| `colormap` | choice | viridis |  | Options: `gray`, `gold`, `ice`, `teal`, `viridis`, `magma`, `inferno`, `plasma`, `cividis`, `coolwarm`. |
| `size` | number (0.3..30) | 2.5 | yes | Point radius in pixels |
| `style` | choice | solid |  | Options: `solid`, `glow`. |
| `glow` | number (0..4) | 0.4 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Optics

- [Lens](#lens) (`lens`): A thin lens. Rays objects bend through it: positive focal length converges, negative diverges.
- [Mirror](#mirror) (`mirror`): A flat or curved mirror (or a beam splitter, or an absorbing screen) that Rays objects reflect from or stop at.
- [Light rays](#rays) (`rays`): A bundle of rays from a point or a parallel beam, traced through every lens and mirror in the film. The draw effect (or Travel) sends the light on its way.
- [Wavefronts](#wavefront) (`wavefront`): Circular or plane wave crests moving out from a source at a set wavelength and speed.

<a id="lens"></a>
### Lens (`lens`)

A thin lens. Rays objects bend through it: positive focal length converges, negative diverges.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `position` | x, y | (960, 540) | yes | Centre of the lens |
| `height` | number (10..) | 300 | yes | Aperture in pixels |
| `angle` | number | 0 | yes | Direction of the optical axis (0 = left to right) |
| `focal` | number | 250 | yes | Focal length in pixels; negative for a diverging lens |
| `color` | colour | ice | yes |  |
| `fill_opacity` | number (0..1) | 0.18 | yes |  |
| `width` | number (0..10) | 2 | yes |  |
| `show_focus` | on/off | on |  | Mark both focal points on the axis |
| `glow` | number (0..4) | 0.6 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="mirror"></a>
### Mirror (`mirror`)

A flat or curved mirror (or a beam splitter, or an absorbing screen) that Rays objects reflect from or stop at.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `position` | x, y | (1300, 540) | yes | Centre of the mirror surface |
| `height` | number (10..) | 300 | yes |  |
| `angle` | number | 180 | yes | The way the mirror faces (180 = facing left, towards light coming from the left) |
| `radius` | number | 0 | yes | Radius of curvature in pixels: 0 = flat, positive = concave (focuses), negative = convex |
| `kind` | choice | mirror |  | splitter: half reflected, half passes; absorber: rays stop here (a detector or screen) Options: `mirror`, `splitter`, `absorber`. |
| `color` | colour | cream | yes |  |
| `width` | number (0.5..20) | 4 | yes |  |
| `hatch` | on/off | on |  | Short lines on the back of a mirror |
| `glow` | number (0..4) | 0.4 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="rays"></a>
### Light rays (`rays`)

A bundle of rays from a point or a parallel beam, traced through every lens and mirror in the film. The draw effect (or Travel) sends the light on its way.

Default enter effect: `draw`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`, `draw`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | x, y | (300, 540) | yes | Where the light starts |
| `angle` | number | 0 | yes | Direction of travel (0 = to the right) |
| `kind` | choice | parallel |  | parallel: a beam of width Spread; point: a cone of Spread degrees Options: `parallel`, `point`. |
| `spread` | number (0..) | 200 | yes | Beam width in pixels, or cone angle in degrees |
| `count` | whole number (1..200) | 7 | yes |  |
| `length` | number (10..) | 2400 | yes | Longest path of a ray, in pixels |
| `bounces` | whole number (0..50) | 8 | yes | Most reflections and refractions per ray |
| `travel` | number (0..1) | 1 | yes | How far the light has got along its path. Animate it from 0 to 1 |
| `color` | colour | gold | yes |  |
| `width` | number (0.3..12) | 2 | yes |  |
| `glow` | number (0..4) | 1 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="wavefront"></a>
### Wavefronts (`wavefront`)

Circular or plane wave crests moving out from a source at a set wavelength and speed.

Default enter effect: `fade`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `source` | x, y | (500, 540) | yes | Point source, or a point on the first plane crest |
| `kind` | choice | circular |  | Options: `circular`, `plane`. |
| `angle` | number | 0 | yes | Direction of travel (plane), or the centre of the arc |
| `arc` | number (1..360) | 360 | yes | Circular waves: the opening angle |
| `wavelength` | number (2..) | 60 | yes | Crest spacing in pixels |
| `speed` | number | 120 | yes | Pixels per second (0 = frozen) |
| `extent` | number (10..) | 700 | yes | Farthest crest from the source (circular) or crest length (plane) |
| `range` | number (10..) | 900 | yes | Plane waves: how far they travel |
| `color` | colour | blue | yes |  |
| `width` | number (0.3..12) | 2 | yes |  |
| `fade` | on/off | on |  | Crests fade with distance |
| `glow` | number (0..4) | 0.7 | yes |  |
| `opacity` | number (0..1) | 1 | yes |  |

## Shapes & media

- [Panel / card](#panel) (`panel`): Rounded card with a header and a numbered badge, for step-by-step explanations.
- [Rectangle](#rect) (`rect`): Rectangle or rounded box: highlights, regions, frames.
- [Circle / ellipse](#ellipse) (`ellipse`): Circle or ellipse: highlight a cluster, a region of interest, a spot.
- [Arrow](#arrow) (`arrow`): Straight or curved arrow pointing at something.
- [Image](#image) (`image`): A picture or data array (radiograph, slice, micrograph, logo) placed in the frame.
- [Group](#group) (`group`): Moves, scales, fades and times its members together. Select objects and press Ctrl+G.

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
| `step` | number (0..) | 0 | yes | For a file pattern such as assets/scan/*.tif: which file to show (0 = first). Animate it, or set Steps per second |
| `steps_per_second` | number (0..) | 0 | yes | Play a file pattern by itself: files per second since the object appeared (0 = use Step) |
| `position` | x, y | (960, 540) | yes | Centre of the image |
| `width` | number (1..) | 420 | yes | Pixels; height follows the aspect ratio |
| `rotation` | number | 0 | yes | Degrees, clockwise (a sample turning on its stage) |
| `mask` | choice | none |  | Options: `none`, `circle`, `rounded`. |
| `border_color` | colour | cream | yes |  |
| `border_width` | number (0..30) | 0 | yes |  |
| `glow` | number (0..3) | 0.3 | yes | Glow of the image itself |
| `opacity` | number (0..1) | 1 | yes |  |

<a id="group"></a>
### Group (`group`)

Moves, scales, fades and times its members together. Select objects and press Ctrl+G.

Default enter effect: `none`. Effects: `none`, `fade`, `slide_up`, `slide_down`, `slide_left`, `slide_right`, `pop`.

| Property | Type | Default | Animatable | Notes |
| --- | --- | --- | --- | --- |
| `offset` | x, y | (0, 0) | yes | Shift of the members on screen, in pixels |
| `scale` | number (0..) | 1 | yes | Scale of the members |
| `pivot` | x, y | (960, 540) | yes | Point that 2D members scale about, in pixels |
| `position` | x, y, z | (0, 0, 0) | yes | Shift of 3D members, in scene units |
| `rotation` | x, y, z | (0, 0, 0) | yes | Rotation of 3D members, degrees about x, y, z |
| `pivot3d` | x, y, z | (0, 0, 0) | yes | Point that 3D members rotate and scale about |
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
