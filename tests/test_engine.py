import math

import numpy as np
import pytest

from sciview.engine.camera import Camera, rotation_matrix
from sciview.engine.color import apply_colormap, colormap_lut, parse_color, rgb_to_hex
from sciview.engine.easing import EASINGS, ease, smooth
from sciview.engine.mathexpr import ExpressionError, evaluate
from sciview.engine.surface import Canvas, dash_path, rounded_rect, truncate_path
from sciview.engine.text import parse_markup, plain_text, render_text


# ------------------------------------------------------------------ colours
def test_parse_color_forms():
    assert np.allclose(parse_color("#ff0000"), [1, 0, 0])
    assert np.allclose(parse_color("#0f0"), [0, 1, 0])
    assert np.allclose(parse_color([0, 0, 255]), [0, 0, 1])
    assert np.allclose(parse_color("teal"), parse_color("#4fd1c5"))
    assert np.allclose(parse_color("teal", {"teal": "#000000"}), [0, 0, 0])
    with pytest.raises(ValueError):
        parse_color("not-a-colour")


def test_rgb_hex_roundtrip():
    assert rgb_to_hex(parse_color("#12abef")) == "#12abef"


def test_colormaps_shape_and_range():
    for name in ("gray", "gold", "ice", "viridis", "magma"):
        lut = colormap_lut(name)
        assert lut.shape == (256, 3)
        assert lut.min() >= 0 and lut.max() <= 1
    rgb = apply_colormap(np.array([[0.0, 0.5, 1.0]]), "gray")
    assert np.allclose(rgb[0, 0], 0) and np.allclose(rgb[0, 2], 1)


# ------------------------------------------------------------------ easing
def test_easings_endpoints():
    for name in EASINGS:
        if name == "hold":
            continue
        assert ease(name, 0) == pytest.approx(0, abs=1e-9)
        assert ease(name, 1) == pytest.approx(1, abs=1e-9)
    assert smooth(0.5, 0, 1) == pytest.approx(0.5)
    assert smooth(-1, 0, 1) == 0 and smooth(2, 0, 1) == 1


# ------------------------------------------------------------------ camera
def test_camera_projects_target_to_centre():
    cam = Camera.orbit((1, 2, 3), 50, -60, 20, 30, 1920, 1080)
    xy, z = cam.project([(1, 2, 3)])
    assert np.allclose(xy[0], [960, 540], atol=1e-6)
    assert z[0] == pytest.approx(50)


def test_camera_offset_and_axes():
    cam = Camera.orbit((0, 0, 0), 100, -90, 0, 30, 1000, 500, offset=(100, 0))
    # camera on -y looking +y: +x is to the right, +z is up
    (p,), _ = cam.project([(10, 0, 0)])
    (q,), _ = cam.project([(0, 0, 10)])
    assert p[0] > 600 and q[1] < 250


def test_rotation_matrix_orthonormal():
    R = rotation_matrix(10, 20, 30)
    assert np.allclose(R @ R.T, np.eye(3))
    assert np.allclose(rotation_matrix(0, 0, 90) @ [1, 0, 0], [0, 1, 0], atol=1e-12)


# ------------------------------------------------------------------ paths and canvas
def test_truncate_and_dash():
    pts = np.array([[0, 0], [10, 0], [10, 10]], float)
    half = truncate_path(pts, 0.5)
    assert np.allclose(half[-1], [10, 0])
    dashes = dash_path(np.array([[0, 0], [100, 0]], float), 10, 10)
    assert len(dashes) == 5


def test_canvas_draws_inside_and_clips():
    cv = Canvas(100, 60)
    cv.polygon(rounded_rect(10, 10, 30, 20, 4), fill=(1, 0, 0))
    assert cv.rgb[20, 25, 0] > 0.9
    cv.push_clip(50, 0, 100, 60)
    cv.polygon([[0, 0], [40, 0], [40, 40]], fill=(0, 1, 0))
    cv.pop_clip()
    assert cv.rgb[5, 30, 1] == 0  # outside the clip: untouched
    img = cv.finish(bloom=0)
    assert img.dtype == np.uint8 and img.shape == (60, 100, 3)


def test_canvas_ignores_nan_polygons():
    cv = Canvas(50, 50)
    cv.polygon([[0, 0], [np.nan, 5], [10, 10]], fill=(1, 1, 1))
    assert cv.rgb.max() == 0


def test_splat_saturates_softly():
    cv = Canvas(64, 64)
    cv.splat(np.full((500, 2), 32.0), 1.0, (1, 1, 1), sigma=1.0)
    assert 0.9 < cv.rgb[32, 32, 0] <= 1.0


# ------------------------------------------------------------------ text
def test_markup_parsing():
    lines = parse_markup("H_2O and ^6Li, x_{max}, \\alpha **bold**")
    runs = lines[0]
    assert any(r.level == -1 and r.text == "2" for r in runs)
    assert any(r.level == 1 and r.text == "6" for r in runs)
    assert any(r.level == -1 and r.text == "max" for r in runs)
    assert any("α" in r.text for r in runs)
    assert any(r.bold and r.text == "bold" for r in runs)
    assert plain_text("H_2O \\to D_2O") == "H2O → D2O"
    assert plain_text("a\\_b") == "a_b"


def test_render_text_has_ink_and_fallback_glyphs():
    t = render_text("Å α µ → H_2O", 24)
    assert t.mask.max() > 0.9
    assert t.width > 40 and t.height > 20


# ------------------------------------------------------------------ expressions
def test_expression_evaluates_with_numpy():
    x = np.linspace(0, 1, 5)
    assert np.allclose(evaluate("exp(-x) * 2", x=x), 2 * np.exp(-x))
    assert np.allclose(evaluate("x^2 + t", x=x, t=1.0), x ** 2 + 1)
    assert evaluate("gauss(0, 0, 1)") == pytest.approx(1)


@pytest.mark.parametrize("bad", [
    "__import__('os').system('echo hi')", "x.__class__", "open('f')", "[i for i in x]",
    "lambda: 1", "x if x else y", "'text'", "exec('1')",
])
def test_expression_rejects_unsafe_code(bad):
    with pytest.raises(ExpressionError):
        evaluate(bad, x=np.arange(3))


def test_nice_ticks():
    from sciview.model.charts import fmt_tick, nice_ticks
    ticks, step = nice_ticks(0, 10, 5)
    assert step == 2 and list(ticks) == [0, 2, 4, 6, 8, 10]
    assert fmt_tick(0.25, 0.25) == "0.25"
    assert math.isclose(nice_ticks(0, 1, 4)[1], 0.25)


# ------------------------------------------------------------------ Bézier easing
def test_cubic_bezier_matches_css():
    from sciview.engine.easing import BEZIER_PRESETS, cubic_bezier
    for u in np.linspace(0, 1, 11):
        assert cubic_bezier(0, 0, 1, 1, u) == pytest.approx(u, abs=1e-6)
    # CSS "ease" at half time is about 0.8024
    assert cubic_bezier(*BEZIER_PRESETS["ease"], 0.5) == pytest.approx(0.8024, abs=1e-3)
    assert cubic_bezier(0.25, 0.1, 0.25, 1, 0) == 0 and cubic_bezier(0.25, 0.1, 0.25, 1, 1) == 1
    ys = [cubic_bezier(0.42, 0, 0.58, 1, u) for u in np.linspace(0, 1, 101)]
    assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:]))           # monotonic
    assert ys[50] == pytest.approx(0.5, abs=1e-6)                   # symmetric curve
    # overshoot above 1, and x outside [0, 1] is clamped instead of running time backwards
    assert max(cubic_bezier(0.3, 1.6, 0.7, 1.4, u) for u in np.linspace(0, 1, 50)) > 1.05
    assert cubic_bezier(-2, 0, 3, 1, 0.3) == pytest.approx(cubic_bezier(0, 0, 1, 1, 0.3), abs=1e-6)
    # degenerate flat handles still give a value for every time
    assert 0 <= cubic_bezier(1, 0, 0, 1, 0.5) <= 1
    assert ease("bezier", 0.5, (0, 0, 1, 1)) == pytest.approx(0.5)
    assert ease("bezier", 0.3) == pytest.approx(ease("smooth", 0.3))   # no curve given: smooth


def test_bezier_keyframes():
    import sciview as sv
    p = sv.Project()
    o = p.add("rect")
    o.key("opacity", 0.0, 0.0).key("opacity", 1.0, 1.0, "bezier", (0.42, 0, 0.58, 1))
    assert o.keys["opacity"][1]["bez"] == [0.42, 0, 0.58, 1]
    assert o.value_at("opacity", 0.5) == pytest.approx(0.5, abs=1e-6)
    assert o.value_at("opacity", 0.25) < 0.25
    o.key("opacity", 2.0, 0.0, "bezier", (2, 0, 9, 1))          # x outside [0, 1] is clamped
    assert o.keys["opacity"][2]["bez"] == [1.0, 0.0, 1.0, 1.0]
    o.key("opacity", 3.0, 1.0, "bezier", "nonsense")            # unreadable: falls back to smooth
    assert o.keys["opacity"][3]["ease"] == "smooth" and "bez" not in o.keys["opacity"][3]
    # survives a save/load round trip
    q = sv.Project.from_json(p.to_json())
    assert q.objects[0].keys["opacity"][1] == {"t": 1.0, "v": 1.0, "ease": "bezier", "bez": [0.42, 0, 0.58, 1]}
