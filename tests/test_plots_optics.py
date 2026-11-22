"""Charts with uncertainty, fits, spectra and fields; ray optics and wavefronts."""
import builtins

import numpy as np
import pytest

import sciview as sv
from sciview.model import plots
from sciview.render import FrameInfo, RenderContext


def draw(p, t=1.0, scale=0.5):
    info = FrameInfo()
    img = p.renderer().frame(t, scale, info)
    return img, info


def no_scipy(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("scipy"):
            raise ImportError("No module named 'scipy'")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)


# ---------------------------------------------------------------------------------------------- fits
X = np.linspace(0.5, 10, 40)
CASES = {
    "linear": ([2.0, -1.0], lambda x: 2 * x - 1),
    "quadratic": ([0.5, -2.0, 3.0], lambda x: 0.5 * x ** 2 - 2 * x + 3),
    "cubic": ([0.1, -1.0, 2.0, 4.0], lambda x: 0.1 * x ** 3 - x ** 2 + 2 * x + 4),
    "exponential": ([3.0, -0.4], lambda x: 3 * np.exp(-0.4 * x)),
    "gaussian": ([5.0, 4.0, 1.2], lambda x: 5 * np.exp(-((x - 4) ** 2) / (2 * 1.2 ** 2))),
    "power": ([2.0, 1.5], lambda x: 2 * x ** 1.5),
    "logistic": ([8.0, 1.5, 5.0], lambda x: 8 / (1 + np.exp(-1.5 * (x - 5)))),
}


@pytest.mark.parametrize("model", list(CASES))
def test_fits_recover_their_parameters(model):
    pytest.importorskip("scipy")
    want, f = CASES[model]
    p, r2 = plots.fit_curve(X, f(X), model)
    assert np.allclose(p, want, rtol=1e-3, atol=1e-3)
    assert r2 > 0.9999
    assert np.allclose(plots.eval_fit(model, p, X), f(X), rtol=1e-3, atol=1e-3)


@pytest.mark.parametrize("model", ["linear", "exponential", "power"])
def test_fits_work_without_scipy(model, monkeypatch):
    no_scipy(monkeypatch)
    want, f = CASES[model]
    p, r2 = plots.fit_curve(X, f(X), model)                   # linearised fits are exact on clean data
    assert np.allclose(p, want, rtol=1e-6) and r2 > 0.9999


def test_fit_errors_are_clear():
    with pytest.raises(ValueError, match="positive"):
        plots.fit_curve(X, -np.ones_like(X), "exponential")
    with pytest.raises(ValueError, match="at least 4"):
        plots.fit_curve([1, 2, 3], [1, 2, 3], "cubic")
    with pytest.raises(ValueError, match="unknown model"):
        plots.fit_curve(X, X, "sinusoidal")


def test_fit_object_draws_with_its_label(tmp_project):
    p = tmp_project
    p.base_dir.joinpath("assets", "decay.csv").write_text(
        "t,I\n" + "\n".join(f"{x:g},{3 * np.exp(-0.4 * x):g}" for x in X), encoding="utf-8")
    ax = p.add("axes", position=(300, 200), size=(900, 500), x_range=(0, 10), y_range=(0, 3))
    fit = p.add("fit", axes=ax, data="assets/decay.csv", x_column="t", y_column="I", model="exponential",
                label="I = {formula}, b = {b:.2f}, R² = {r2:.3f}")
    assert p.problems() == []
    img, info = draw(p)
    assert info.issues == []
    assert plots._format_named("b = {b:.2f}, R² = {r2:.3f}, {formula}", {"b": -0.4, "r2": 1.0}) == \
        "b = -0.40, R² = 1.000, {formula}"
    fit.set("model", "power")                                 # fine; a bad column is reported on the field
    fit.set("y_column", "nope")
    _, info = draw(p)
    assert info.issues and info.issues[0]["id"] == fit.id


# ---------------------------------------------------------------------------------------------- spectra
def spectrum_data():
    x = np.linspace(10, 80, 701)
    y = 50 * np.exp(-(x - 30) ** 2 / 2) + 80 * np.exp(-(x - 55) ** 2 / 1.5) + 20 * np.exp(-(x - 70) ** 2) + 5
    return x, y


@pytest.mark.parametrize("scipy", [True, False])
def test_peaks_are_found(monkeypatch, scipy):
    if scipy:
        pytest.importorskip("scipy")
    else:
        no_scipy(monkeypatch)
    x, y = spectrum_data()
    idx = plots.find_peaks(x, y, 0.1)
    assert np.allclose(x[idx], [30, 55, 70], atol=0.15)
    assert np.allclose(x[plots.find_peaks(x, y, 0.1, max_peaks=2)], [30, 55], atol=0.15)   # the largest two
    assert len(plots.find_peaks(x, y, 0.5)) == 2


def test_spectrum_objects_label_peaks(tmp_project):
    p = tmp_project
    x, y = spectrum_data()
    ax = p.add("axes", x_range=(10, 80), y_range=(0, 100))
    p.add("spectrum", axes=ax, source="data", x_values=list(x), y_values=list(y), label_format="{x:.1f}°")
    p.add("spectrum", axes=ax, source="data", x_values=list(x), y_values=list(y), peaks="30, 55")
    p.add("spectrum", axes=ax, expression="gauss(x, 40, 2)*100")
    img, info = draw(p)
    assert info.issues == [] and p.problems() == []


# ---------------------------------------------------------------------------------------------- other charts
def test_error_bars_band_heatmap_colorbar_hist2d(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    rng = np.random.default_rng(0)
    rows = "\n".join(f"{a:.4f},{b:.4f},{0.05:g}" for a, b in zip(rng.random(200), rng.random(200)))
    p.base_dir.joinpath("assets", "pts.csv").write_text("x,y,e\n" + rows, encoding="utf-8")
    ax = p.add("axes", position=(200, 150), size=(700, 500), x_range=(0, 1), y_range=(0, 1))
    p.add("errorbars", axes=ax, data="assets/pts.csv", x_column="x", y_column="y", y_error="e")
    p.add("errorbars", axes=ax, data="assets/pts.csv", x_column="x", y_column="y", y_error="0.1", x_error="0.02")
    p.add("band", axes=ax, center="0.5 + 0.2*sin(6*x - t)", spread="0.05")
    hm = p.add("heatmap", axes=ax, expression="sin(6*x)*cos(6*y)", resolution=64)
    cb = p.add("colorbar", source=hm.id, label="field", unit="T")
    h2 = p.add("hist2d", axes=ax, data="assets/pts.csv", x_column="x", y_column="y", bins=(8, 8))
    assert p.problems() == []
    img, info = draw(p, 1.0, 1.0)
    assert info.issues == []
    r = p.renderer()
    ctx = RenderContext(p, r.assets, 1.0, 1.0, 1920, 1080, p.camera_at(1.0, 1920, 1080))
    lo, hi = hm.color_range(ctx, hm.resolve(1.0, ctx))
    assert lo == pytest.approx(-1, abs=0.05) and hi == pytest.approx(1, abs=0.05)
    assert cb._mapping(ctx, cb.resolve(1.0, ctx))[1:3] == pytest.approx((lo, hi))
    tr = ctx.axes(ax.id) if hasattr(ctx, "axes") else None
    counts = h2.counts(ctx, h2.resolve(1.0, ctx), tr)
    assert np.asarray(counts).sum() == 200


def test_heatmap_from_a_grid_file_and_bad_files(tmp_project):
    p = tmp_project
    np.savetxt(p.base_dir / "assets" / "grid.csv", np.outer(np.arange(5), np.arange(7)), delimiter=",")
    ax = p.add("axes", x_range=(0, 1), y_range=(0, 1))
    p.add("heatmap", axes=ax, source="data", data="assets/grid.csv")
    _, info = draw(p)
    assert info.issues == []
    p.add("heatmap", axes=ax, source="data", data="assets/data.csv")       # a table with a header: still a grid
    p.add("heatmap", axes=ax, source="data", data="assets/missing.csv")
    assert any(q["prop"] == "data" for q in p.problems())


def test_vector_fields_and_flowing_streamlines(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    ax = p.add("axes", position=(200, 150), size=(700, 700), x_range=(-2, 2), y_range=(-2, 2))
    p.add("vectorfield", axes=ax, u="-y", v="x", color_by_strength=True)
    sl = p.add("streamlines", axes=ax, u="-y", v="x", flow_speed=0.0)
    a, info = draw(p, 1.0)                                    # after the draw-on effects
    b, _ = draw(p, 1.9)
    assert info.issues == []
    assert np.array_equal(a, b)                               # a still field
    sl.set("flow_speed", 40)
    a, _ = draw(p, 1.0)
    b, _ = draw(p, 1.6)                                       # 12 px later: not a whole dash period
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.05   # dashes flow along the lines


# ---------------------------------------------------------------------------------------------- optics
def trace(p, rays, t=1.0):
    r = p.renderer()
    ctx = RenderContext(p, r.assets, t, 1.0, 1920, 1080, p.camera_at(t, 1920, 1080))
    return rays.trace(ctx, rays.resolve(t, ctx))


def crossing_x(a, b, y=540.0):
    """Where the line through a and b crosses the horizontal line y."""
    return a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])


def test_parallel_rays_meet_at_the_focus_of_a_converging_lens():
    p = sv.Project(duration=2)
    p.add("lens", position=(600, 540), focal=300)
    rays = p.add("rays", source=(100, 540), spread=200, count=5)
    paths = trace(p, rays)
    assert len(paths) == 5
    for path, inten in paths:
        assert inten == 1.0
        if abs(path[0][1] - 540) > 1:
            assert crossing_x(path[1], path[2]) == pytest.approx(900, abs=0.5)


def test_a_diverging_lens_has_a_virtual_focus():
    p = sv.Project(duration=2)
    p.add("lens", position=(600, 540), focal=-300)
    rays = p.add("rays", source=(100, 540), spread=200, count=5)
    for path, _ in trace(p, rays):
        if abs(path[0][1] - 540) > 1:
            assert crossing_x(path[1], path[2]) == pytest.approx(300, abs=0.5)   # traced backwards


def test_flat_mirror_at_45_degrees_turns_light_upwards():
    p = sv.Project(duration=2)
    p.add("mirror", position=(800, 540), angle=135, height=400)
    rays = p.add("rays", source=(100, 540), spread=0, count=1)
    (path, _), = trace(p, rays)
    assert np.allclose(path[1], [800, 540], atol=1e-6)
    d = path[2] - path[1]
    assert np.allclose(d / np.linalg.norm(d), [0, -1], atol=1e-6)


def test_concave_mirror_focuses_at_half_its_radius():
    p = sv.Project(duration=2)
    p.add("mirror", position=(1500, 540), angle=180, radius=800, height=300)
    rays = p.add("rays", source=(100, 540), spread=60, count=4)
    for path, _ in trace(p, rays):
        assert crossing_x(path[1], path[2]) == pytest.approx(1100, abs=2)    # paraxial: f = R / 2


def test_splitters_halve_and_absorbers_stop():
    p = sv.Project(duration=2)
    p.add("mirror", position=(800, 540), angle=135, height=400, kind="splitter")
    rays = p.add("rays", source=(100, 540), spread=0, count=1)
    paths = trace(p, rays)
    assert sorted(i for _, i in paths) == [0.5, 0.5]
    ends = sorted(tuple(np.round(path[-1] - path[1])) for path, _ in paths)
    assert ends[0][1] < 0 and ends[1][0] > 0                  # one goes up, one goes on
    p.objects[0].set("kind", "absorber")
    (path, _), = trace(p, rays)
    assert len(path) == 2 and np.allclose(path[-1], [800, 540])


def test_rays_travel_and_hidden_elements_are_ignored():
    p = sv.Project(duration=4, stars=0)
    lens = p.add("lens", position=(600, 540), focal=300, start=2.0)
    rays = p.add("rays", source=(100, 540), spread=200, count=5, enter="none")
    straight = trace(p, rays, 1.0)
    assert all(len(path) == 2 for path, _ in straight)        # the lens is not there yet
    assert all(len(path) == 3 for path, _ in trace(p, rays, 3.0))
    rays.key("travel", 0.0, 0.0, "linear").key("travel", 1.0, 1.0, "linear")
    a = p.frame(0.2, 0.5)
    b = p.frame(0.9, 0.5)
    assert (b.max(axis=2) > 120).sum() > (a.max(axis=2) > 120).sum()
    del lens


def test_wavefronts_move_and_optics_template_renders():
    p = sv.Project(duration=4, stars=0)
    p.add("wavefront", source=(500, 540), wavelength=60, speed=120)
    p.add("wavefront", source=(500, 540), kind="plane", angle=30, wavelength=40)
    a, info = draw(p, 1.0)
    b, _ = draw(p, 1.25)
    assert info.issues == []
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.2
