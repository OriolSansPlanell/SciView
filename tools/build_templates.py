"""Build the templates shipped with SciView (and show how to script films with the Python API).

Run from the repository root:  python tools/build_templates.py
Each template is written to src/sciview/templates/<name>/project.sciview.json with its assets.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import sciview as sv  # noqa: E402

OUT = ROOT / "src" / "sciview" / "templates"


def save_template(proj: sv.Project, name: str, title: str, description: str, order: int, thumb_time: float,
                  assets: dict[str, object] | None = None) -> Path:
    d = OUT / name
    if d.exists():
        shutil.rmtree(d)
    (d / "assets").mkdir(parents=True)
    for fname, data in (assets or {}).items():
        target = d / "assets" / fname
        if isinstance(data, Image.Image):
            data.save(target)
        elif isinstance(data, str):
            target.write_text(data, encoding="utf-8")
        else:
            np.save(target, data)
    if not any((d / "assets").iterdir()):
        (d / "assets").rmdir()
    data = proj.to_json()
    data["template"] = {"title": title, "description": description, "order": order, "thumb_time": thumb_time}
    (d / "project.sciview.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return d


# --------------------------------------------------------------------------- assets
def radiograph(n=256, seed=3) -> Image.Image:
    """Synthetic neutron radiograph of a soil column with three water-filled tubes."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float64)
    u = (x - n / 2) / (n * 0.36)                      # column radius ~0.36 of the frame
    inside = np.abs(u) < 1
    chord = np.where(inside, 2 * np.sqrt(np.clip(1 - u ** 2, 0, 1)), 0.0)
    mu_l = 0.45 * chord
    for cx, r, mu in ((-0.45, 0.13, 9.0), (0.05, 0.11, 6.0), (0.5, 0.12, 3.0)):
        v = (u - cx) / r
        mu_l += mu * np.where(np.abs(v) < 1, 2 * r * np.sqrt(np.clip(1 - v ** 2, 0, 1)), 0)
    vert = np.clip(1 - np.abs((y - n / 2) / (n * 0.46)) ** 12, 0, 1)
    T = np.exp(-mu_l * vert)
    T = T * (0.92 + 0.08 * rng.random((n, n)))
    return Image.fromarray((np.clip(T, 0, 1) * 255).astype(np.uint8))


MATERIALS = [("Plastic (polyethylene)", "teal", 0.18, 0.80), ("Aluminium", "gray", 0.25, 0.15),
             ("Lead", "red", 0.82, 0.22), ("Hydride (ZrH_2)", "violet", 0.78, 0.85)]


def slice_images(n=120, seed=5):
    """Two co-registered slices (x-ray and neutron gray values) of a sample with four inclusions."""
    rng = np.random.default_rng(seed)
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n * 2 - 1
    label = np.zeros((n, n), int)
    for i, (cx, cy, r) in enumerate([(-0.35, -0.3, 0.28), (0.4, -0.35, 0.22), (-0.25, 0.42, 0.18), (0.3, 0.35, 0.3)], 1):
        label[(x - cx) ** 2 + (y - cy) ** 2 < r ** 2] = i
    disk = x ** 2 + y ** 2 < 0.95 ** 2
    xr = np.full((n, n), 0.25)      # matrix: aluminium-like
    ne = np.full((n, n), 0.15)
    for i, (_, _, gx, gn) in enumerate(MATERIALS, 1):
        if i == 2:
            continue
        xr[label == i] = gx
        ne[label == i] = gn
    # labels: 1 plastic, 2 aluminium (same as the matrix), 3 lead, 4 hydride
    xr += rng.normal(0, 0.05, (n, n))
    ne += rng.normal(0, 0.05, (n, n))
    xr[~disk] = 0
    ne[~disk] = 0
    pts = []
    sel = np.flatnonzero(disk.ravel())
    pick = rng.choice(sel, 1400, replace=False)
    for k in pick:
        pts.append((xr.ravel()[k], ne.ravel()[k], label.ravel()[k] if label.ravel()[k] != 2 else 0))
    table = "xray,neutron,label\n" + "\n".join(f"{a:.4f},{b:.4f},{c}" for a, b, c in pts)
    def to_img(a):
        return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return to_img(xr), to_img(ne), table


def lattice_table(n=4, a=6.0):
    rows = ["x,y,z,species"]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                s = (i + j + k) % 2
                rows.append(f"{(i - (n - 1) / 2) * a:.3f},{(j - (n - 1) / 2) * a:.3f},{(k - (n - 1) / 2) * a:.3f},{s}")
    return "\n".join(rows)


# --------------------------------------------------------------------------- templates
def neutron_imaging() -> sv.Project:
    p = sv.Project(title="Neutron imaging", duration=16.0)
    cam = p.camera
    cam.set("target", (-20, 0, 0)).set("fov", 28).set("offset", (0, -10))
    cam.key("azimuth", 0, -130).key("azimuth", 9, -116, "in_out").key("azimuth", 16, -109, "in_out")
    cam.key("elevation", 0, 22).key("elevation", 9, 14, "in_out")
    cam.key("distance", 0, 235).key("distance", 9, 192, "in_out").key("distance", 16, 180, "in_out")
    p.add("grid3d", name="Floor", center=(0, 0, -16), size=(220, 120), divisions=22, start=0)
    p.add("box", name="Neutron source", center=(-75, 0, 0), size=(18, 18, 18), edge_color="gold",
          fill_color="gold", label="neutron source", label_position="below", label_color="gold", start=0.3)
    p.add("cylinder", name="Sample", center=(0, 0, 0), radius=5, height=16, rings=3, lines=4,
          label="sample", label_color="cream", start=1.0)
    scr = p.add("screen", name="Detector", center=(34, 0, 0), size=(22, 22), thickness=3,
                image="assets/radiograph.png", colormap="gold", counts=40, label="detector",
                label_color="teal", start=1.6)
    scr.key("buildup", 4.0, 0.0, "linear").key("buildup", 11.0, 1.0, "linear")
    p.add("beam", name="Neutrons", source=(-66, 0, 0), target=(32, 0, 0), source_radius=2.5, target_radius=9,
          rate=260, speed=34, streak=5, scatter_fraction=0.12, scatter_at=0.67, start=2.5)
    p.add("title", text="Neutron imaging", subtitle="How a radiograph is made, one neutron at a time", start=0.2)
    p.add("caption", text="A beam of neutrons leaves the source and crosses the sample.", start=1.5, end=5.5)
    p.add("caption", text="Each neutron that gets through lands on one pixel of the detector.", start=5.5, end=10.0)
    p.add("caption", text="Counted neutron by neutron, the radiograph builds up: water stops neutrons.", start=10.0, end=15.5)
    return p


def data_story() -> sv.Project:
    p = sv.Project(title="From gray level to concentration", duration=18.0, stars=0.15)
    p.add("title", text="From gray level to concentration", subtitle="Three steps from a pixel to a number", start=0.2)
    p1 = p.add("panel", name="Panel 1", position=(80, 170), size=(520, 650), title="Gray level", badge=1, start=0.6)
    p2 = p.add("panel", name="Panel 2", position=(700, 170), size=(520, 650), title="Attenuation", badge=2, start=0.6)
    p3 = p.add("panel", name="Panel 3", position=(1320, 170), size=(520, 650), title="Concentration", badge=3, start=0.6)
    ax1 = p.add("axes", name="Counts", position=(170, 270), size=(380, 420), x_range=(0.4, 2.6), y_range=(0, 2400),
                x_label="", y_label="counts", x_ticks=0, y_ticks=4, grid=True, start=1.2)
    p.add("bars", name="Open beam and sample", axes=ax1.id, values="2000, 642", labels="I_0, I", colors="gray, teal",
          value_labels=True, label_size=18, start=2.0)
    p.add("text", name="Transmission", text="T = I / I_0 = {value:.3f}", value=0.321, position=(110, 770), size=24,
          color="cream", start=4.0)
    ax2 = p.add("axes", name="Beer-Lambert", position=(790, 270), size=(380, 400), x_range=(0, 1), y_range=(0, 2.5),
                x_label="T", y_label="-ln T", start=6.6)
    p.add("curve", name="-ln T", axes=ax2.id, expression="-log(x)", domain=(0.02, 1.0), color="cream", start=7.2)
    m = p.add("marker", name="This pixel", axes=ax2.id, x=0.321, follow="-log(x)", label="-ln T = {y:.2f}", start=8.6)
    m.key("x", 9.6, 0.321).key("x", 11.0, 0.28)
    p.add("equation", name="mu", tex=r"\mu = -\frac{\ln T}{d}", position=(960, 785), size=34, start=8.0)
    ax3 = p.add("axes", name="Calibration", position=(1410, 270), size=(380, 420), x_range=(0, 6), y_range=(0, 100),
                x_label="\\mu (cm^{-1})", y_label="D_2O (%)", start=12.6)
    p.add("curve", name="Calibration line", axes=ax3.id, expression="100*(5.56 - x)/(5.56 - 0.674)",
          domain=(0.674, 5.56), color="teal", start=13.2)
    p.add("marker", name="Result", axes=ax3.id, x=3.79, follow="100*(5.56 - x)/(5.56 - 0.674)", color="gold",
          label="{y:.0f} %", start=14.4)
    c = p.add("text", name="Counter", text="**{value:.0f} %** D_2O", value=0, position=(1580, 770), size=40,
              color="gold", align="center", start=14.6)
    c.key("value", 14.6, 0.0, "linear").key("value", 16.0, 36.0, "out")
    # each panel and what is drawn on it form a group, so a step fades back as a whole
    objs = p.objects
    first = {o.name: i for i, o in enumerate(objs)}
    steps = (("Step 1", p1, ("Counts", "Open beam and sample", "Transmission"), 6.0),
             ("Step 2", p2, ("Beer-Lambert", "-ln T", "This pixel", "mu"), 12.0),
             ("Step 3", p3, ("Calibration", "Calibration line", "Result", "Counter"), None))
    for name, panel, members, dim in steps:
        g = p.group([panel, *(objs[first[n]] for n in members)], name=name, pivot=tuple(panel.props["position"]))
        if dim is not None:
            g.key("opacity", dim, 1.0).key("opacity", dim + 1.0, 0.45)
    p.add("caption", text="Subtract the dark signal and divide by the open beam: the transmission T.", start=1.5, end=6.5)
    p.add("caption", text="Beer–Lambert turns the transmission into an attenuation coefficient.", start=6.5, end=12.5)
    p.add("caption", text="A calibration line between pure H_2O and pure D_2O turns \\mu into a concentration.", start=12.5, end=17.6)
    return p


def clusters() -> sv.Project:
    p = sv.Project(title="Two signals, one plot", duration=16.0, stars=0.2)
    p.add("title", text="Both beams together", subtitle="The joint (2D) histogram", start=0.2)
    p.add("image", name="X-ray slice", image="assets/slice_xray.png", colormap="ice", position=(330, 380), width=300,
          mask="circle", border_width=2, border_color="blue", pixelated=True, start=0.6)
    p.add("text", name="X-ray label", text="X-ray slice", position=(330, 205), size=22, color="blue", align="center", start=0.6)
    p.add("image", name="Neutron slice", image="assets/slice_neutron.png", colormap="gold", position=(330, 790),
          width=300, mask="circle", border_width=2, border_color="amber", pixelated=True, start=1.2)
    p.add("text", name="Neutron label", text="Neutron slice", position=(330, 615), size=22, color="amber", align="center", start=1.2)
    ax = p.add("axes", name="Joint histogram", position=(900, 230), size=(700, 640), x_range=(0, 1), y_range=(0, 1),
               x_label="x-ray gray value", y_label="neutron gray value", x_ticks=4, y_ticks=4, frame="box", start=2.0)
    p.add("scatter", name="Voxels", axes=ax.id, data="assets/voxels.csv", x_column="xray", y_column="neutron",
          color="cream", size=2.6, start=3.0, enter="draw")
    p.objects[-1].enter_duration = 3.0
    p.add("histogram", name="X-ray histogram", axes=ax.id, data="assets/voxels.csv", column="xray", bins=50,
          color="blue", height=0.18, start=7.0)
    p.add("histogram", name="Neutron histogram", axes=ax.id, data="assets/voxels.csv", column="neutron", bins=50,
          orientation="horizontal", color="amber", height=0.18, start=7.6)
    g1 = p.add("guide", name="X-ray threshold", axes=ax.id, value=0.5, label="x-ray threshold", start=10.0)
    g1.key("value", 10.0, 0.2).key("value", 11.5, 0.52, "in_out")
    p.add("guide", name="Neutron threshold", axes=ax.id, value=0.5, orientation="horizontal", label="neutron threshold", start=12.0)
    for name, color, gx, gn in MATERIALS:
        p.add("ellipse", name=name.split(" (")[0], axes=ax.id, center=(gx, gn), radii=(0.12, 0.13), stroke_color=color,
              stroke_width=2, glow=0.8, start=13.0, enter="draw")
    p.add("legend", entries="\n".join(f"{c} | {n}" for n, c, _, _ in MATERIALS), position=(1640, 700), start=13.2)
    p.add("caption", text="Every voxel of the slice becomes a point: its x-ray value across, its neutron value up.", start=2.5, end=7.0)
    p.add("caption", text="Each 1D histogram is this cloud seen from one side, where clusters overlap.", start=7.0, end=12.0)
    p.add("caption", text="Two thresholds split the plane into four materials.", start=12.0, end=15.8)
    return p


def waves() -> sv.Project:
    p = sv.Project(title="Interference", duration=12.0, stars=0.25)
    p.add("title", text="Interference", subtitle="Two waves add up", start=0.2)
    ax = p.add("axes", name="Waves", position=(200, 260), size=(1520, 520), x_range=(0, 20), y_range=(-2.4, 2.4),
               x_label="position x", y_label="amplitude", x_ticks=5, y_ticks=4, start=0.5)
    p.add("curve", name="Wave 1", axes=ax.id, expression="sin(1.0*x - 3*t)", color="blue", width=2.5, start=1.0)
    p.add("curve", name="Wave 2", axes=ax.id, expression="sin(1.15*x - 3.3*t)", color="amber", width=2.5, start=2.5)
    s = p.add("curve", name="Sum", axes=ax.id, expression="sin(1.0*x - 3*t) + sin(1.15*x - 3.3*t)", color="cream",
              width=3.5, glow=1.4, start=5.0)
    s.enter_duration = 1.5
    p.add("curve", name="Envelope", axes=ax.id, expression="2*abs(cos(0.075*x - 0.15*t))", color="teal",
          style="dashed", width=2, start=8.0)
    p.add("equation", tex=r"y = \sin(k_1 x - \omega_1 t) + \sin(k_2 x - \omega_2 t)", position=(960, 900), size=36,
          start=5.5)
    p.add("caption", text="Where the crests meet, the waves reinforce; where a crest meets a trough, they cancel.",
          position=(960, 1010), start=8.5, end=11.8)
    return p


def lattice() -> sv.Project:
    p = sv.Project(title="Rock-salt lattice", duration=12.0)
    cam = p.camera
    cam.set("distance", 95).set("fov", 32).set("elevation", 24)
    cam.key("azimuth", 0, -40, "linear").key("azimuth", 12, 50, "linear")
    p.add("pointcloud", name="Ions", data="assets/lattice.csv", color_by="species", colormap="coolwarm", size=9,
          style="glow", glow=1.0, start=0.4, enter="draw")
    p.objects[-1].enter_duration = 2.5
    p.add("box", name="Unit cell", center=(3, 3, 3), size=(12, 12, 12), edge_color="cream", fill_opacity=0.03,
          edge_width=1.5, glow=0.6, label="unit cell", label_position="right", start=4.0, enter="draw")
    p.objects[-1].enter_duration = 1.5
    p.add("arrow3d", name="a", tail=(-9, -9, -9), tip=(3, -9, -9), color="gold", label="a = 5.64 \\AA",
          label_color="gold", start=6.0)
    p.add("title", text="Rock-salt structure", subtitle="Na^+ and Cl^- on two interleaved cubic lattices", start=0.2)
    p.add("legend", entries="#3b4cc0 | Na^+\n#b40426 | Cl^-", swatch="circle", position=(80, 900), size=22, start=1.0)
    return p


def title_card() -> sv.Project:
    p = sv.Project(title="Title card", duration=7.0, stars=0.6)
    p.add("text", name="Title", text="Imaging water in soil", position=(960, 440), size=84, weight="bold", color="gold",
          align="center", valign="middle", glow=0.25, start=0.4, enter="slide_up")
    p.objects[-1].enter_duration = 1.0
    p.add("text", name="Subtitle", text="Neutron radiography of a living root system", position=(960, 545), size=34,
          color="cream", align="center", valign="middle", start=1.2, enter="fade")
    p.add("arrow", name="Rule", tail=(860, 610), tip=(1060, 610), heads="none", color="teal", width=2.5,
          start=1.8, enter="draw")
    p.add("text", name="Authors", text="A. Author, B. Author and C. Author", position=(960, 680), size=26,
          color="cream", align="center", valign="middle", start=2.4)
    p.add("text", name="Affiliation", text="Your institute, your city", position=(960, 724), size=22, color="gray",
          align="center", valign="middle", start=2.6)
    return p


def sample_volume(seed: int = 7) -> np.ndarray:
    """A porous cylinder with a dense inclusion, as a CT scan would give it (uint8, z, y, x)."""
    rng = np.random.default_rng(seed)
    nz, ny, nx = 64, 88, 88
    z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float32)
    vol = np.where(np.hypot(x - nx / 2, y - ny / 2) < 34, 0.55, 0.0).astype(np.float32)
    for _ in range(22):
        c = rng.random(3) * [nz, ny, nx]
        r = rng.random() * 5 + 2.5
        vol[(z - c[0]) ** 2 + (y - c[1]) ** 2 + (x - c[2]) ** 2 < r * r] = 0.04
    vol[(z - 30) ** 2 + (y - 38) ** 2 + (x - 56) ** 2 < 9 ** 2] = 1.0
    vol += rng.normal(0, 0.025, vol.shape).astype(np.float32)
    return np.clip(vol * 220 + 20, 0, 255).astype(np.uint8)


def tomography() -> sv.Project:
    from sciview.science import phantom  # noqa: F401  (the slice image is saved by main)
    p = sv.Project(title="How a tomograph sees inside", duration=22.0, stars=0.2)
    p.add("title", text="How a tomograph sees inside", subtitle="Projections, a sinogram, and the slice rebuilt",
          start=0.2, end=3.6)
    sample = p.add("image", name="Sample slice", image="assets/slice.png", position=(330, 520), width=330,
                   mask="circle", border_width=2, border_color="teal", start=3.0, end=11.0)
    sample.key("rotation", 4.0, 0, "linear").key("rotation", 10.0, 180, "linear")
    p.add("text", name="Sample label", text="the sample turns", position=(330, 300), size=22, color="teal",
          align="center", start=3.0, end=11.0)
    sino = p.add("sinogram", name="Sinogram", position=(960, 560), size=(360, 360), resolution=160, angles=180,
                 profile=True, start=3.4, end=11.0)
    sino.key("progress", 4.0, 0.0, "linear").key("progress", 10.0, 1.0, "linear")
    p.add("backprojection", name="Rebuilt slice", sinogram=sino.id, position=(1590, 560), size=(360, 360),
          start=3.8, end=11.0)
    p.add("text", name="Rebuilt label", text="filtered back-projection", position=(1590, 330), size=22, color="gold",
          align="center", start=3.8, end=11.0)
    p.add("caption", text="Each angle gives one projection: a row of the sinogram.", start=4.0, end=7.5)
    p.add("caption", text="Smearing every row back across the slice, after a ramp filter, rebuilds it.",
          start=7.5, end=11.0)
    p.camera.props.update(distance=150, azimuth=-62, elevation=24)
    p.camera.key("azimuth", 11.0, -62).key("azimuth", 22.0, -10, "in_out")
    vol = p.add("volume", name="Scan (slices)", data="assets/sample.npy", size=56, spacing=(1, 1, 1),
                clear_below=0.15, colormap="ice", start=11.2, end=16.6)
    vol.key("slice_z", 11.5, 0.05).key("slice_z", 15.5, 0.95, "in_out")
    iso = p.add("volume", name="Scan (surface)", data="assets/sample.npy", size=56, mode="isosurface",
                threshold=0.5, iso_color="teal", smoothness=1, start=16.2)
    iso.key("threshold", 17.5, 0.42).key("threshold", 20.5, 0.86, "in_out")
    p.add("scalebar3d", name="Scale", origin=(-28, -36, -16), length=20, unit="0.5 mm", start=11.6)
    p.add("caption", text="Stack the slices and you have the whole sample: sweep through it…", start=11.4, end=16.4)
    p.add("caption", text="…or show one grey level as a surface: raise it to reveal the dense inclusion.",
          start=16.4, end=21.8)
    return p


def optics() -> sv.Project:
    p = sv.Project(title="Lenses and mirrors", duration=14.0, stars=0.15)
    p.add("title", text="Lenses and mirrors", subtitle="Rays traced through thin lenses and curved mirrors",
          start=0.2, end=3.2)
    axis = p.add("arrow", name="Optical axis", tail=(80, 470), tip=(1840, 470), heads="none", color="gray",
                 width=1.2, dashed=True, start=2.6)
    del axis
    p.add("lens", name="Converging lens", position=(620, 470), focal=260, height=300, start=2.8)
    beam = p.add("rays", name="Parallel beam", source=(120, 470), spread=180, count=9, color="gold", start=3.4)
    beam.enter_duration = 3.0
    p.add("caption", text="A converging lens sends a parallel beam through its focal point F.", start=3.4, end=7.6)
    p.add("mirror", name="Concave mirror", position=(1640, 470), angle=180, radius=900, height=600, start=7.4)
    p.add("caption", text="A concave mirror turns the light back and brings it together again.", start=7.6, end=13.8)
    p.add("wavefront", name="Wavefronts", source=(120, 470), kind="plane", angle=0, wavelength=36, extent=260,
          range=470, color="blue", start=3.4, end=7.4)
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    xr, ne, table = slice_images()
    save_template(neutron_imaging(), "neutron_imaging", "Imaging beamline",
                  "A particle beam crosses a sample; the detector image builds up count by count.", 10, 12.5,
                  {"radiograph.png": radiograph()})
    save_template(data_story(), "data_story", "Step-by-step analysis",
                  "Three numbered panels: bars, a curve with a moving marker and a counter.", 20, 16.5)
    save_template(clusters(), "clusters", "Scatter and thresholds",
                  "Two images, a joint scatter plot, marginal histograms and threshold lines.", 30, 14.5,
                  {"slice_xray.png": xr, "slice_neutron.png": ne, "voxels.csv": table})
    save_template(waves(), "waves", "Animated equations",
                  "Curves from expressions with time t: travelling waves that add up.", 40, 9.5)
    save_template(lattice(), "lattice", "3D structure",
                  "A point cloud from a table, a unit cell and an orbiting camera.", 50, 8.0,
                  {"lattice.csv": lattice_table()})
    save_template(title_card(), "title_card", "Title card",
                  "Title, subtitle, authors and affiliation for the start of a talk.", 60, 5.0)
    from sciview.science import phantom
    slice_img = Image.fromarray((phantom(200) * 255).astype(np.uint8))
    save_template(tomography(), "tomography", "Tomography",
                  "A turning sample, its sinogram, the rebuilt slice, then the scanned volume.", 25, 8.5,
                  {"slice.png": slice_img, "sample.npy": sample_volume()})
    save_template(optics(), "optics", "Lenses and mirrors",
                  "A parallel beam focused by a lens and a concave mirror, with wavefronts.", 45, 10.0)
    print("templates written to", OUT)


if __name__ == "__main__":
    main()
