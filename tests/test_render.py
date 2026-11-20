import tempfile
from pathlib import Path

import numpy as np
import pytest

import sciview as sv
from sciview.render import FrameInfo, Renderer, out_size
from sciview.server import instantiate_template, list_templates


def full_scene(p):
    """One of every object type, all visible at t = 1."""
    p.add("grid3d")
    p.add("box", label="box")
    p.add("cylinder", center=(20, 0, 0), lines=3, label="cyl")
    p.add("sphere", center=(0, 20, 0))
    p.add("screen", center=(40, 0, 0), thickness=2, image="assets/ramp.png", colormap="gold", counts=20, buildup=0.5)
    p.add("beam", source=(-40, 0, 0), target=(40, 0, 0), scatter_fraction=0.2)
    p.add("arrow3d", dashed=True)
    p.add("pointcloud", data="assets/data.csv", color_by="z", style="solid")
    p.add("label3d", text="pin \\alpha")
    ax = p.add("axes", x_range=(0, 3), y_range=(0, 10))
    p.add("curve", axes=ax, expression="x^2", fill_opacity=0.2, style="dashed")
    p.add("curve", axes=ax, source="data", data="assets/data.csv")
    p.add("scatter", axes=ax, data="assets/data.csv", color_by="z")
    p.add("bars", axes=ax, values="1, 5, 3", labels="a, b, c", value_labels=True, colors="red, teal")
    p.add("histogram", axes=ax, values="1 1 2 2 2 3", bins=3)
    p.add("histogram", axes=ax, values="1 2 5 6", orientation="horizontal")
    p.add("marker", axes=ax, x=2, follow="x^2", label="{x:.1f}, {y:.1f}")
    p.add("guide", axes=ax, value=1.5, label="thr", dashed=True)
    p.add("title", text="Title", subtitle="Sub")
    p.add("caption", text="A caption", start=0, end=2)
    p.add("text", text="{value:.0f} %", value=42, rotation=30)
    p.add("equation", tex=r"\frac{a}{b}")
    p.add("legend")
    p.add("panel", title="Step", badge=1)
    p.add("rect", radius=8, fill_opacity=0.3, dashed=True)
    p.add("ellipse", axes=ax, center=(1, 5), radii=(0.5, 2))
    p.add("arrow", bend=50, heads="both")
    p.add("image", image="assets/ramp.png", mask="circle", border_width=2, pixelated=True)
    return p


def test_every_object_renders_without_warnings(tmp_project):
    p = full_scene(tmp_project)
    info = FrameInfo()
    img = Renderer(p).frame(1.0, 0.5, info)
    assert img.shape == (540, 960, 3) and img.dtype == np.uint8
    assert info.warnings == []
    drawn = {b["id"] for b in info.boxes}
    missing = {o.id for o in p.objects if o.TYPE not in ("mesh",)} - drawn
    assert not missing, f"objects without a bounding box: {missing}"
    assert img.mean() > 5


def test_rendering_is_deterministic(tmp_project):
    p = full_scene(tmp_project)
    a = Renderer(p).frame(1.3, 0.25)
    b = Renderer(p).frame(1.3, 0.25)
    assert np.array_equal(a, b)


def test_effects_change_the_picture(tmp_project):
    p = tmp_project
    p.add("text", text="Hello", size=120, start=0.5).appear(effect="fade", duration=1.0)
    r = Renderer(p)
    before, mid, after = (r.frame(t, 0.25).astype(float).sum() for t in (0.2, 1.0, 1.8))
    assert before < mid < after


def test_mesh_loading_and_render(tmp_path):
    stl = tmp_path / "tet.stl"
    stl.write_text("""solid t
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 10 0
 endloop
endfacet
facet normal 0 1 0
 outer loop
  vertex 0 0 0
  vertex 0 0 10
  vertex 10 0 0
 endloop
endfacet
endsolid t
""")
    p = sv.Project(path=tmp_path / "m.sciview.json", duration=1)
    p.add("mesh", model="tet.stl", style="solid+edges")
    info = FrameInfo()
    Renderer(p).frame(0.5, 0.25, info)
    assert info.warnings == [] and info.boxes


def test_bad_values_warn_instead_of_crashing(tmp_project):
    p = tmp_project
    ax = p.add("axes")
    p.add("curve", axes=ax, expression="nonsense(x)")
    p.add("image", image="assets/nope.png")
    p.add("scatter", axes=ax, data="assets/data.csv", x_column="missing")
    info = FrameInfo()
    Renderer(p).frame(0.5, 0.25, info)
    assert len(info.warnings) >= 3


def test_out_size_is_even():
    p = sv.Project(width=1001, height=777)
    w, h = out_size(p, 0.33)
    assert w % 2 == 0 and h % 2 == 0


@pytest.mark.parametrize("name", [t["name"] for t in list_templates()])
def test_templates_render_cleanly(name):
    with tempfile.TemporaryDirectory() as tmp:
        p = instantiate_template(name, Path(tmp))
        assert p.validate() == []
        info = FrameInfo()
        r = Renderer(p, Path(tmp))
        for t in (0.0, p.duration * 0.5, p.duration - 0.01):
            r.frame(t, 0.25, info)
            assert info.warnings == [], (name, t, info.warnings)
