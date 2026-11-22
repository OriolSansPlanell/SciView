"""Data tracks, file sequences, and checks that apply to every object type."""
import json

import numpy as np
import pytest
from PIL import Image

import sciview as sv
from sciview.engine import assets as A
from sciview.model import REGISTRY
from sciview.render import FrameInfo


def write_csv(path, header, rows):
    path.write_text(header + "\n" + "\n".join(",".join(f"{x:g}" for x in r) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture
def logged(tmp_project):
    write_csv(tmp_project.base_dir / "assets" / "log.csv", "minutes,temp,x,y",
              [(0, 300, 100, 200), (1, 400, 300, 200), (2, 400, 300, 600)])
    return tmp_project


# ---------------------------------------------------------------------------------------------- tracks
def test_track_interpolates_scales_and_shifts(logged):
    p = logged
    t = p.add("text", text="{value:.0f} K")
    t.track("value", "assets/log.csv", column="temp", time="minutes", time_scale=0.5, time_offset=1.0,
            scale=2.0, offset=-100)
    a = p.renderer().assets
    # film time 2 s -> table time (2 - 1) * 0.5 = 0.5 min -> 350 K -> 2 * 350 - 100
    assert t.track_value("value", 2.0, a) == pytest.approx(600)
    assert t.track_value("value", 0.0, a) == pytest.approx(500)        # before the table: first row
    assert t.track_value("value", 99.0, a) == pytest.approx(700)       # after it: last row
    t.track("value", "assets/log.csv", column="temp", time="minutes", smooth=False)
    assert t.track_value("value", 0.9, a) == pytest.approx(300)        # held until the next row


def test_vector_tracks_take_several_columns(logged):
    p = logged
    c = p.add("ellipse", center=(0, 0))
    c.track("center", "assets/log.csv", column="x, y", time="minutes")
    a = p.renderer().assets
    assert np.allclose(c.track_value("center", 1.5, a), [300, 400])
    with pytest.raises(ValueError):
        c.track("center", "assets/log.csv", column="x", time="minutes")     # one column for two values
    with pytest.raises(KeyError):
        c.track("no_such_property", "assets/log.csv", column="x")


def test_tracks_override_keyframes_move_the_object_and_round_trip(logged):
    p = logged
    p.set("stars", 0)
    c = p.add("ellipse", center=(100, 200), radii=(20, 20), fill_color="white", fill_opacity=1, enter="none")
    c.key("opacity", 0.0, 1.0).key("opacity", 2.0, 1.0)
    c.key("center", 0.0, (900, 900)).key("center", 2.0, (900, 900))
    c.track("center", "assets/log.csv", column="x, y", time="minutes", time_scale=1.0)
    assert c.depends_on_time()
    img0 = p.frame(0.0, 1.0)
    img1 = p.frame(2.0, 1.0)
    assert img0[200, 100].max() > 200 and img1[600, 300].max() > 200     # follows the table, not the keys
    assert img0[900, 900].max() < 60
    p.save()
    q = sv.load(p.path)
    assert q.objects[-1].tracks["center"]["column"] == "x, y"
    assert json.loads(p.path.read_text())["objects"][-1]["tracks"]["center"]["time"] == "minutes"
    c.untrack("center")
    assert not c.tracks


def test_track_problems_name_the_file_and_column(logged):
    p = logged
    t = p.add("text")
    t.track("value", "assets/log.csv", column="pressure", time="minutes")
    u = p.add("text")
    u.track("value", "assets/gone.csv", column="temp")
    w = p.add("text")
    w.tracks["value"] = {"data": "", "column": "", "time": "t", "scale": 1.0, "offset": 0.0,
                         "time_scale": 1.0, "time_offset": 0.0, "smooth": True}
    msgs = {(q["id"], q["prop"]): q["message"] for q in p.problems()}
    assert "pressure" in msgs[(t.id, "value")] and "temp" in msgs[(t.id, "value")]   # lists the columns
    assert "gone.csv" in msgs[(u.id, "value")]
    assert "choose a table" in msgs[(w.id, "value")]
    info = FrameInfo()
    p.renderer().frame(1.0, 0.25, info)                      # draws, with the keyframed/default value
    assert any(i["id"] == t.id and i["prop"] == "value" for i in info.issues)


def test_camera_follows_a_data_track(logged):
    p = logged
    p.set("stars", 0)
    p.add("box", center=(0, 0, 0), size=(10, 30, 5))
    p.camera.track("azimuth", "assets/log.csv", column="temp", time="minutes", scale=0.2)
    a, b = p.frame(0.0, 0.25), p.frame(1.0, 0.25)
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.3
    p.save()
    q = sv.load(p.path)
    assert "azimuth" in q.camera.tracks
    assert np.array_equal(q.frame(1.0, 0.25), b)


def test_cached_layers_respect_tracks(logged):
    p = logged
    t = p.add("text", text="{value:.0f}", size=60)
    t.track("value", "assets/log.csv", column="temp", time="minutes")
    r = p.renderer()
    for tt in (0.0, 0.5, 1.0):
        cached = r.frame(tt, 0.25)                            # reuses layers from the frames before
        plain = sv.Project.from_json(p.to_json(), p.path).frame(tt, 0.25)   # a fresh renderer
        assert np.array_equal(cached, plain)


# ---------------------------------------------------------------------------------------------- sequences
def test_natural_order_and_kinds(tmp_path):
    for n in (10, 2, 1):
        write_csv(tmp_path / f"out_{n}.csv", "x,y", [(n, n)])
    store = A.AssetStore(tmp_path)
    assert store.sequence("out_*.csv") == ["out_1.csv", "out_2.csv", "out_10.csv"]
    assert A.is_sequence("a/*.tif") and A.is_sequence("a/b?.png") and A.is_sequence("a/[ab].png")
    assert not A.is_sequence("a/b.png")
    assert A.asset_kind("scan/*.tif") == "sequence"
    assert A.asset_kind("x.h5") == "volume" and A.asset_kind("1crn.pdb") == "molecule"
    assert store.sequence_file("out_*.csv", 1.25) == ("out_2.csv", "out_10.csv", 0.25)
    assert store.sequence_file("out_*.csv", 99)[0] == "out_10.csv"
    before = store.stamp("out_*.csv")
    write_csv(tmp_path / "out_11.csv", "x,y", [(11, 11)])
    assert store.stamp("out_*.csv") != before                 # a new file changes the cache key


def test_image_sequence_plays_and_steps(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    d = p.base_dir / "assets" / "frames"
    d.mkdir()
    for i, level in enumerate((0, 255, 120)):
        Image.fromarray(np.full((16, 16), level, np.uint8)).save(d / f"f_{i + 1}.png")
    img = p.add("image", image="assets/frames/f_*.png", position=(960, 540), width=400, colormap="gray",
                vmin=0, vmax=1)
    assert p.problems() == []

    def centre(t):
        return int(p.frame(t, 0.5)[270, 480].max())
    assert centre(0.5) < 40                                   # step 0: the dark file
    img.set("step", 1)
    assert centre(0.5) > 200
    img.set("step", 0)
    img.set("steps_per_second", 1.0)                          # plays by itself: file 2 after 1 s
    assert img.depends_on_time()
    assert centre(1.0) > 200 and 80 < centre(1.9) < 180


def test_table_sequence_blends_between_files(tmp_project):
    p = tmp_project
    d = p.base_dir / "assets" / "sim"
    d.mkdir()
    write_csv(d / "s_1.csv", "x,y", [(0, 0), (1, 1)])
    write_csv(d / "s_2.csv", "x,y", [(2, 0), (3, 1)])
    write_csv(d / "s_3.csv", "x,y", [(5, 5)])                 # a different number of rows
    ax = p.add("axes", x_range=(0, 6), y_range=(0, 6))
    sc = p.add("scatter", axes=ax, data="assets/sim/s_*.csv", x_column="x", y_column="y")
    from sciview.model import data as seq
    from sciview.render import RenderContext
    r = p.renderer()
    ctx = RenderContext(p, r.assets, 1.0, 1.0, 1920, 1080, p.camera_at(1.0, 1920, 1080))
    v = sc.resolve(1.0, ctx)
    v["step"] = 0.5
    assert np.allclose(seq.column(ctx, v, "x"), [1, 2])       # halfway between the first two files
    v["step"] = 1.4
    assert np.allclose(seq.column(ctx, v, "x"), [2, 3])       # unequal rows: the nearest file
    v["step"] = 1.6
    assert np.allclose(seq.column(ctx, v, "x"), [5])
    info = FrameInfo()
    r.frame(1.0, 0.25, info)
    assert info.issues == []


def test_patterns_without_files_are_reported(tmp_project):
    p = tmp_project
    p.add("image", image="assets/none/*.png")
    p.add("scatter", data="assets/none_*.csv")
    msgs = [q for q in p.problems() if "no files match" in q["message"]]
    assert {q["prop"] for q in msgs} == {"image", "data"}


# ---------------------------------------------------------------------------------------------- all types
RESERVED = {"name", "start", "end", "enter", "exit", "id", "parent", "type"}


def test_no_property_clashes_with_project_add_arguments():
    for t, klass in REGISTRY.items():
        clash = {p.name for p in klass.all_props()} & RESERVED
        assert not clash, f"{t} has properties {clash} that Project.add() cannot set"


def test_expression_properties_are_marked():
    for t, klass in REGISTRY.items():
        for p in klass.all_props():
            if p.name in ("expression", "u", "v", "center", "spread", "lower", "upper") and p.kind == "text":
                assert p.expr, f"{t}.{p.name} holds an expression but is not checked as one"


def test_every_type_adds_draws_saves_and_loads(tmp_project):
    p = tmp_project
    for t in REGISTRY:
        p.add(t)
    for q in p.problems():                                    # only missing choices, never crashes
        assert q["prop"] in ("axes", "sinogram", "reference", "source", None) or "choose" in q["message"], q
    info = FrameInfo()
    img = p.renderer().frame(1.0, 0.25, info)
    assert img.shape == (270, 480, 3)
    p.save()
    q = sv.load(p.path)
    assert [o.TYPE for o in q.objects] == [o.TYPE for o in p.objects]
    assert q.warnings == []


def test_bad_expressions_in_new_types_are_reported(tmp_project):
    p = tmp_project
    ax = p.add("axes")
    p.add("heatmap", axes=ax, expression="sin(x*y) + q")
    p.add("vectorfield", axes=ax, u="-y", v="x +")
    p.add("band", axes=ax, center="exp(-x)", spread="z")
    msgs = {q["prop"]: q["message"] for q in p.problems()}
    assert "q" in msgs["expression"] and "v" in msgs and "spread" in msgs
    p.objects[1].set("expression", "sin(x*y - t)")
    assert "expression" not in {q["prop"] for q in p.problems()}
