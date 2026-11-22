"""Volumes, tomography, scale bars and units, morphs and molecules."""
import numpy as np
import pytest
from PIL import Image

import sciview as sv
from sciview.engine import assets as A
from sciview.engine.units import format_number, nice_length, parse_si, si
from sciview.render import FrameInfo
from sciview.science import tomo


def render_info(p, t, scale=0.5):
    info = FrameInfo()
    img = p.renderer().frame(t, scale, info)
    return img, info


def lit(img, box=None):
    """How many pixels are clearly brighter than the dark background."""
    a = np.asarray(img, np.float32)
    if box is not None:
        x0, y0, x1, y1 = box
        a = a[y0:y1, x0:x1]
    return int((a.max(axis=2) > 90).sum())


# ---------------------------------------------------------------------------------------------- tomography
def test_phantom_is_the_shepp_logan_head():
    ph = tomo.phantom(128)
    assert ph.shape == (128, 128) and ph.dtype == np.float32
    assert 0 <= ph.min() and ph.max() <= 1
    assert ph[64, 64] > 0 and ph[0, 0] == 0                 # inside the skull, outside the head


def test_radon_matches_scikit_image():
    transform = pytest.importorskip("skimage.transform")
    # odd size: scikit-image turns images about pixel n // 2, SciView about the true centre (n - 1) / 2,
    # which are the same pixel only when n is odd
    ph = tomo.phantom(97)
    ang = tomo.angles(60)
    ours = tomo.radon(ph, ang)
    ref = transform.radon(ph, theta=ang, circle=True).T      # (angles, detector)
    assert np.abs(ours - ref).max() < 1e-3 * ref.max()
    assert np.allclose(ours.sum(axis=1), ours.sum(axis=1).mean(), rtol=0.01)   # mass is conserved at every angle


def test_radon_of_a_disk_is_its_chord_length():
    n = 128
    c = np.arange(n) - (n - 1) / 2
    x, y = np.meshgrid(c, c)
    cx, cy, R = 20.0, -15.0, 18.0                             # right of and above the centre (y down)
    disk = (((x - cx) ** 2 + (y - cy) ** 2) <= R ** 2).astype(np.float32)
    for a in (0.0, 30.0, 90.0, 140.0):
        prof = tomo.radon(disk, [a])[0]
        th = np.radians(a)
        s0 = cx * np.cos(th) - cy * np.sin(th)                # the centre turned clockwise on screen
        s = c - s0
        chord = 2 * np.sqrt(np.clip(R ** 2 - s ** 2, 0, None))
        assert np.abs(prof - chord).max() < 3.5, a            # pixelated edges
        assert abs(np.sum(prof * c) / prof.sum() - s0) < 0.3


def test_radon_turns_about_the_image_centre():
    ph = tomo.phantom(96)
    s = tomo.radon(ph, [0.0, 180.0])
    assert np.allclose(s[1], s[0][::-1], atol=0.05 * s.max())


def test_sinogram_turns_clockwise_like_an_image_rotation():
    img = np.zeros((65, 65), np.float32)
    img[12, 32] = 1.0                                         # a point above the centre
    sino = tomo.radon(img, [0.0, 90.0])
    assert abs(int(np.argmax(sino[0])) - 32) <= 1             # straight below it at 0°
    assert int(np.argmax(sino[1])) > 45                       # turned 90° clockwise: it is on the right


@pytest.mark.parametrize("filt", ["ramp", "shepp-logan", "cosine", "hann"])
def test_filtered_back_projection_rebuilds_the_slice(filt):
    ph = tomo.phantom(128)
    ang = tomo.angles(180)
    rec = tomo.fbp(tomo.radon(ph, ang), ang, filt)
    inside = tomo._circle(128) > 0
    err = np.sqrt(np.mean((rec[inside] - ph[inside]) ** 2))
    assert err < 0.11, err
    assert np.corrcoef(rec[inside], ph[inside])[0, 1] > 0.9


def test_unfiltered_back_projection_is_blurred_and_cumulative_ends_at_the_full_image():
    ph = tomo.phantom(96)
    ang = tomo.angles(90)
    sino = tomo.radon(ph, ang)
    plain = tomo.fbp(sino, ang, "none")
    good = tomo.fbp(sino, ang, "ramp")
    inside = tomo._circle(96) > 0
    assert np.corrcoef(plain[inside], ph[inside])[0, 1] < np.corrcoef(good[inside], ph[inside])[0, 1]
    stack = tomo.fbp(sino, ang, "ramp", cumulative=True)
    assert stack.shape == (90, 96, 96)
    assert np.allclose(stack[-1], good, atol=1e-4)
    with pytest.raises(ValueError):
        tomo.filter_sinogram(sino, "wiener")


def test_sinogram_and_backprojection_objects_follow_progress(tmp_project):
    p = tmp_project
    sino = p.add("sinogram", position=(500, 540), size=(400, 400), resolution=96, angles=60)
    sino.key("progress", 0.0, 0.0, "linear").key("progress", 2.0, 1.0, "linear")
    p.add("backprojection", sinogram=sino.id, position=(1400, 540), size=(400, 400))
    assert p.problems() == []
    early, info = render_info(p, 0.3)
    late, _ = render_info(p, 1.9)
    assert info.issues == []
    box = (600, 120, 900, 420)                                # the back-projection, at half scale
    assert lit(late, box) > lit(early, box)
    # the image source works too, and a missing image is reported on its field
    p.add("sinogram", source="image", image="assets/ramp.png", resolution=64)
    p.add("sinogram", source="image", image="assets/nothing.png")
    probs = p.problems()
    assert any(q["prop"] == "image" and "nothing.png" in q["message"] for q in probs)


def test_empty_or_wrong_references_are_reported(tmp_project):
    p = tmp_project
    box = p.add("box")
    bp = p.add("backprojection")
    p.add("scalebar")
    p.add("morph")
    probs = {(q["id"], q["prop"]) for q in p.problems()}
    assert {(bp.id, "sinogram"), ("scalebar1", "reference"), ("morph1", "source"), ("morph1", "axes")} <= probs
    bp.set("sinogram", box.id)
    assert any(q["prop"] == "sinogram" and "must be a Sinogram" in q["message"] for q in p.problems())
    _, info = render_info(p, 1.0)                             # drawing reports them on the fields too
    assert {"sinogram", "reference", "axes"} <= {i["prop"] for i in info.issues}


# ---------------------------------------------------------------------------------------------- volumes
def blob_volume(nz=24, ny=28, nx=32):
    z, y, x = np.mgrid[:nz, :ny, :nx].astype(np.float32)
    r = np.sqrt(((z - nz / 2) / nz) ** 2 + ((y - ny / 2) / ny) ** 2 + ((x - nx / 2) / nx) ** 2)
    vol = np.clip(1 - 2.5 * r, 0, 1)
    vol[nz // 2 - 2:nz // 2 + 2, ny // 2 - 2:ny // 2 + 2, nx // 2 - 2:nx // 2 + 2] = 1.0
    return vol


def test_load_volume_from_npy_tiff_stack_and_image_sequence(tmp_path):
    vol = blob_volume()
    np.save(tmp_path / "v.npy", vol)
    got = A.load_volume(tmp_path / "v.npy")
    assert got.shape == vol.shape and got.dtype == np.float32 and got.flags.writeable
    tifffile = pytest.importorskip("tifffile")
    tifffile.imwrite(tmp_path / "v.tif", (vol * 1000).astype(np.uint16))
    assert A.load_volume(tmp_path / "v.tif").shape == vol.shape
    (tmp_path / "slices").mkdir()
    for i in range(5):
        Image.fromarray((vol[i] * 255).astype(np.uint8)).save(tmp_path / "slices" / f"s_{i + 1}.png")
    store = A.AssetStore(tmp_path)
    assert store.volume("slices/s_*.png", "").shape == (5,) + vol.shape[1:]
    with pytest.raises(A.AssetError):
        store.volume("slices/none_*.png", "")


def test_load_volume_from_hdf5(tmp_path):
    h5py = pytest.importorskip("h5py")
    vol = blob_volume()
    with h5py.File(tmp_path / "scan.h5", "w") as f:
        f.create_dataset("entry/flat", data=np.ones((4, 4)))
        f.create_dataset("entry/data/volume", data=vol)
        f.create_dataset("other", data=vol * 2)
    assert np.allclose(A.load_volume(tmp_path / "scan.h5"), vol)                # the first 3D dataset
    assert np.allclose(A.load_volume(tmp_path / "scan.h5", "other"), vol * 2)
    with pytest.raises(A.AssetError):
        A.load_volume(tmp_path / "scan.h5", "missing")


def test_block_reduce_keeps_the_mean():
    vol = np.random.default_rng(1).random((20, 21, 22)).astype(np.float32)
    red = A.block_reduce(vol, 2)
    assert red.shape == (10, 11, 11)                          # odd sides are padded, not cut
    assert abs(red.mean() - vol.mean()) < 0.02
    assert A.block_reduce(vol, 1) is vol


@pytest.mark.parametrize("mode", ["slices", "mip", "projection", "isosurface"])
def test_volume_modes_draw(tmp_project, mode):
    if mode == "isosurface":
        pytest.importorskip("skimage")
    p = tmp_project
    np.save(p.base_dir / "assets" / "vol.npy", blob_volume())
    p.add("volume", data="assets/vol.npy", mode=mode, size=60, threshold=0.5)
    assert p.problems() == []
    img, info = render_info(p, 1.0)
    assert info.issues == [], info.issues
    assert lit(img) > 500


def test_volume_modes_look_different_and_slices_move(tmp_project):
    pytest.importorskip("skimage")
    p = tmp_project
    np.save(p.base_dir / "assets" / "vol.npy", blob_volume())
    v = p.add("volume", data="assets/vol.npy", size=60, show_x=False, show_y=False)
    v.key("slice_z", 0.0, 0.1, "linear").key("slice_z", 2.0, 0.9, "linear")
    a, _ = render_info(p, 0.0)
    b, _ = render_info(p, 2.0)
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.3
    frames = []
    for mode in ("slices", "mip", "isosurface"):
        v.set("mode", mode)
        frames.append(render_info(p, 1.0)[0].astype(int))
    assert np.abs(frames[0] - frames[1]).mean() > 0.3 and np.abs(frames[1] - frames[2]).mean() > 0.3


def test_volume_problems_point_at_the_file(tmp_project):
    p = tmp_project
    p.add("volume", data="assets/missing.npy")
    p.add("volume")
    probs = p.problems()
    assert any(q["prop"] == "data" and "missing.npy" in q["message"] for q in probs)
    img, info = render_info(p, 1.0)                           # still renders, with the problem on the field
    assert img.shape[2] == 3


def test_isosurface_needs_scikit_image_or_says_so(tmp_project, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_skimage(name, *args, **kw):
        if name.startswith("skimage"):
            raise ImportError("No module named 'skimage'")
        return real_import(name, *args, **kw)

    p = tmp_project
    np.save(p.base_dir / "assets" / "vol.npy", blob_volume())
    p.add("volume", data="assets/vol.npy", mode="isosurface", threshold=0.42)
    monkeypatch.setattr(builtins, "__import__", no_skimage)
    _, info = render_info(p, 1.0)
    assert any("scikit-image" in i["message"] for i in info.issues)


# ---------------------------------------------------------------------------------------------- units
@pytest.mark.parametrize("value,unit,text", [
    (0.0025, "m", "2.5 mm"), (1.2e-8, "m", "12 nm"), (2.5e5, "Pa", "250 kPa"), (0, "s", "0 s"),
    (1500, "", "1.5k"), (-3.3e-6, "A", "-3.3 µA"), (999.96, "m", "1 km"), (1, "mol", "1 mol"),
])
def test_si_prefixes(value, unit, text):
    assert si(value, unit) == text


def test_parse_si_and_nice_lengths():
    assert parse_si("6.5 µm") == pytest.approx((6.5e-6, "m"))
    assert parse_si("6.5 um") == pytest.approx((6.5e-6, "m"))
    assert parse_si("1 mm") == pytest.approx((1e-3, "m"))
    assert parse_si("2 mol")[1] == "mol" and parse_si("2 mol")[0] == pytest.approx(2)
    assert parse_si("3") == (3.0, "")
    with pytest.raises(ValueError):
        parse_si("lots")
    assert [nice_length(x) for x in (0.7, 1.4, 3.1, 4.4, 8.0, 0.031)] == pytest.approx([0.5, 1, 2, 2, 5, 0.02])


def test_number_formats_in_text():
    from sciview.model.objects2d import format_values
    assert format_number(0.0012345, "si:m") == "1.23 mm"
    assert format_number(0.0012345, ".2si:m") == "1.2 mm"
    assert format_number(3.14159, ".2f") == "3.14"
    assert format_values("{value:si:Pa} at {t:.1f} s, x_{max}", value=2.5e5, t=1.25) == "250 kPa at 1.2 s, x_{max}"
    assert format_values("{value:bogus}", value=3) == "3"                  # a bad format shows the number
    p = sv.Project(duration=4)
    p.add("text", text="{value:si:Pa} at {t:.1f} s", value=2.5e5)
    assert p.problems() == []
    _, info = render_info(p, 1.5)
    assert info.issues == []


def bar_length(img, row):
    """Length in pixels of the bright run on one row (the scale bar)."""
    on = np.nonzero(np.asarray(img)[row].max(axis=1) > 200)[0]
    return int(on[-1] - on[0] + 1) if len(on) else 0


def test_scalebar_on_an_image_has_the_right_length(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    img = p.add("image", image="assets/ramp.png", position=(500, 400), width=640)      # 64 px shown 10x
    p.add("scalebar", reference=img.id, pixel_size="10 µm", length="200 µm", position=(960, 900), glow=0,
          label_position="none")
    assert p.problems() == []
    frame, info = render_info(p, 1.0, 1.0)
    assert info.issues == []
    assert bar_length(frame, 900) == pytest.approx(200, abs=3)  # 20 image pixels x 10 = 200 px


def test_scalebar_on_a_chart_and_automatic_length(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    ax = p.add("axes", position=(200, 200), size=(800, 400), x_range=(0, 10), y_range=(0, 1))
    p.add("scalebar", reference=ax.id, pixel_size="1 mm", length="2.5 mm", position=(960, 900), glow=0,
          label_position="none")
    frame, info = render_info(p, 1.0, 1.0)
    assert info.issues == []
    assert bar_length(frame, 900) == pytest.approx(200, abs=3)  # 2.5 of 10 units over 800 px
    p.objects[-1].set("length", "")                           # a round length near 20% of the chart: 2 mm
    frame, _ = render_info(p, 1.0, 1.0)
    assert bar_length(frame, 900) == pytest.approx(160, abs=3)
    p.objects[-1].set("length", "3 s")
    _, info = render_info(p, 1.0, 1.0)
    assert any(i["prop"] == "length" for i in info.issues)


def test_scalebar3d_and_bad_units(tmp_project):
    p = tmp_project
    p.add("scalebar3d", origin=(0, 0, 0), length=20, unit="0.5 mm")
    img, info = render_info(p, 1.0)
    assert info.issues == [] and lit(img) > 50
    p.add("scalebar3d", unit="half a banana")
    _, info = render_info(p, 1.0)
    assert any(i["prop"] == "unit" for i in info.issues)


# ---------------------------------------------------------------------------------------------- morph
def test_morph_moves_pixels_into_histogram_bins(tmp_project):
    p = tmp_project
    img = p.add("image", image="assets/ramp.png", position=(400, 540), width=500)
    ax = p.add("axes", position=(1000, 300), size=(760, 480), x_range=(0, 1), y_range=(0, 400))
    m = p.add("morph", source=img.id, axes=ax.id, target="histogram", bins=20, max_points=800)
    m.key("progress", 0.0, 0.0, "linear").key("progress", 2.0, 1.0, "linear")
    assert p.problems() == []
    start, info0 = render_info(p, 0.0)
    end, info1 = render_info(p, 2.0)
    assert info0.issues == [] and info1.issues == []
    chart = (500, 150, 880, 390)                              # the axes at half scale
    assert lit(end, chart) > lit(start, chart) + 50
    m.set("target", "joint")
    m.set("image_b", "assets/ramp.png")
    _, info = render_info(p, 2.0)
    assert info.issues == []


def test_morph_without_source_or_axes_is_reported(tmp_project):
    p = tmp_project
    p.add("morph", source="nothing")
    props = {q["prop"] for q in p.problems()}
    assert {"source", "axes"} <= props


# ---------------------------------------------------------------------------------------------- molecules
WATER_XYZ = """3
water
O 0.000 0.000 0.117
H 0.000 0.757 -0.467
H 0.000 -0.757 -0.467
"""

MINI_PDB = """HEADER    TEST
ATOM      1  N   GLY A   1      -1.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  GLY A   1       0.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   GLY A   1       1.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   GLY A   1       0.300   2.420   0.000  1.00  0.00           O
ATOM      5  N   ALA A   2       2.330   1.540   0.000  1.00  0.00           N
ATOM      6  CA AALA A   2       2.950   2.860   0.000  0.60  0.00           C
ATOM      7  CA BALA A   2       2.990   2.900   0.300  0.40  0.00           C
ATOM      8  C   ALA A   2       4.470   2.760   0.000  1.00  0.00           C
ATOM      9  CA  GLY B   1      10.000   0.000   0.000  1.00  0.00           C
ATOM     10  CA  GLY B   2      13.800   0.000   0.000  1.00  0.00           C
HETATM   11 FE   HEM A 101       5.000   5.000   5.000  1.00  0.00          FE
HETATM   12  O   HOH A 201       8.000   8.000   8.000  1.00  0.00           O
CONECT   11    4
END
"""


def test_xyz_water_has_two_bonds(tmp_path):
    (tmp_path / "w.xyz").write_text(WATER_XYZ)
    m = A.load_molecule(tmp_path / "w.xyz")
    assert m.elements == ["O", "H", "H"]
    pairs = {tuple(sorted(map(int, b))) for b in np.asarray(m.bonds)}
    assert pairs == {(0, 1), (0, 2)}


def test_pdb_altlocs_conect_hetero_and_backbone(tmp_path):
    (tmp_path / "m.pdb").write_text(MINI_PDB)
    m = A.load_molecule(tmp_path / "m.pdb")
    assert len(m.elements) == 11                               # the B altloc is dropped
    assert "Fe" in m.elements or "FE" in [e.upper() for e in m.elements]
    pairs = {tuple(sorted(map(int, b))) for b in np.asarray(m.bonds)}
    fe = [i for i, e in enumerate(m.elements) if e.upper() == "FE"][0]
    assert (3, fe) in pairs or (fe, 3) in pairs               # the CONECT record
    assert m.hetero[fe] and not m.hetero[0]
    chains = {c: idx for c, idx in m.backbone()}
    assert set(chains) == {"A", "B"} and len(chains["B"]) == 2
    assert all(not m.hetero[i] for idx in chains.values() for i in idx)


def test_guess_bonds_ignores_far_atoms():
    xyz = np.array([[0, 0, 0], [1.1, 0, 0], [5, 0, 0]], np.float64)
    b = A.guess_bonds(["C", "H", "C"], xyz)
    assert {tuple(sorted(map(int, x))) for x in np.asarray(b)} == {(0, 1)}


def test_bad_molecule_files_are_reported(tmp_path):
    (tmp_path / "bad.xyz").write_text("not a molecule\n")
    with pytest.raises(A.AssetError):
        A.load_molecule(tmp_path / "bad.xyz")


@pytest.mark.parametrize("style", ["ball_and_stick", "spacefill", "sticks", "wire", "ribbon"])
def test_molecule_styles_draw(tmp_project, style):
    p = tmp_project
    (p.base_dir / "assets" / "m.pdb").write_text(MINI_PDB)
    p.add("molecule", model="assets/m.pdb", style=style, scale=6)
    assert p.problems() == []
    img, info = render_info(p, 1.0)
    assert info.issues == [], info.issues
    assert lit(img) > 100


def test_molecule_draw_effect_builds_it_up(tmp_project):
    p = tmp_project
    (p.base_dir / "assets" / "w.xyz").write_text(WATER_XYZ)
    m = p.add("molecule", model="assets/w.xyz", scale=30, enter="draw")
    m.enter_duration = 1.0
    early, _ = render_info(p, 0.2)
    late, _ = render_info(p, 1.5)
    assert lit(late) > lit(early)
