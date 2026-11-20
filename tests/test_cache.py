"""The layer cache must never change a pixel, and must notice every change."""
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest

import sciview as sv
from sciview.render import FrameInfo, Renderer
from sciview.server import instantiate_template, list_templates


def frames(p, base, times, scale, cache):
    r = Renderer(p, base, cache=cache)
    return [r.frame(t, scale).astype(int) for t in times], r


@pytest.mark.parametrize("name", [t["name"] for t in list_templates()])
def test_cache_gives_the_same_pixels_on_every_template(name):
    with tempfile.TemporaryDirectory() as tmp:
        p = instantiate_template(name, Path(tmp))
        dur, fps = p.duration, p.fps
        # runs of consecutive frames at a few places, so the cache fills and is reused
        times = [t0 + k / fps for t0 in (0.3 * dur, 0.62 * dur, 0.9 * dur) for k in range(4)]
        a, r = frames(p, Path(tmp), times, 0.4, cache=True)
        b, _ = frames(p, Path(tmp), times, 0.4, cache=False)
        worst = max(int(np.abs(x - y).max()) for x, y in zip(a, b))
        assert worst <= 1, f"{name}: cached frames differ by {worst}"


def static_scene():
    p = sv.Project(duration=4.0)
    p.add("title", text="Static title", enter="none")
    ax = p.add("axes", x_range=(0, 10), y_range=(-1, 1), enter="none")
    p.add("curve", axes=ax, expression="sin(x)", enter="none")
    p.add("grid3d", enter="none")
    return p


def test_static_objects_come_from_the_cache():
    p = static_scene()
    r = Renderer(p)
    info = FrameInfo()
    r.frame(1.0, 0.25)
    first = r.frame(1.1, 0.25, info)
    assert r.stats["hits"] > 0 and info.cached > 0
    # a time-dependent curve is never cached, but the rest still is
    p.add("curve", axes=p.objects[1].id, expression="sin(x - t)", enter="none")
    info2 = FrameInfo()
    r.frame(1.2, 0.25)
    r.frame(1.3, 0.25, info2)
    assert info2.cached >= 1
    ref = Renderer(p, cache=False).frame(1.3, 0.25).astype(int)
    assert np.abs(r.frame(1.3, 0.25).astype(int) - ref).max() <= 1
    assert first.shape == ref.shape


def test_cache_notices_changes():
    p = static_scene()
    r = Renderer(p)
    a = r.frame(1.0, 0.25)
    r.frame(1.0, 0.25)
    p.objects[0].props["text"] = "Another title"
    b = r.frame(1.0, 0.25)
    assert np.abs(a.astype(int) - b.astype(int)).max() > 20
    # settings and palette changes too
    p.palette["gold"] = "#ff0000"
    c = r.frame(1.0, 0.25)
    assert np.abs(b.astype(int) - c.astype(int)).max() > 20
    # and a moving camera re-draws 3D objects
    p.add("box", size=(40, 30, 20), enter="none")
    p.camera.key("azimuth", 0.0, -60).key("azimuth", 4.0, 60)
    d1, d2 = r.frame(1.0, 0.25), r.frame(2.0, 0.25)
    assert np.abs(d1.astype(int) - d2.astype(int)).max() > 20


def test_held_keyframes_are_static_between_equal_keys():
    p = sv.Project(duration=6.0)
    t = p.add("title", text="Hold", enter="none")
    t.key("opacity", 1.0, 1.0).key("opacity", 3.0, 1.0).key("opacity", 4.0, 0.2)
    assert t.held(2.0) and not t.held(3.5)
    r = Renderer(p)
    r.frame(2.0, 0.25)
    info = FrameInfo()
    r.frame(2.1, 0.25, info)
    assert info.cached >= 1
    info = FrameInfo()
    r.frame(3.5, 0.25, info)
    ref = Renderer(p, cache=False).frame(3.5, 0.25).astype(int)
    assert np.abs(r.frame(3.5, 0.25).astype(int) - ref).max() <= 1


def test_asset_changes_invalidate_the_cache(tmp_project):
    from PIL import Image
    p = tmp_project
    p.add("image", image="assets/ramp.png", width=400, enter="none")
    r = Renderer(p, p.base_dir)
    a = r.frame(1.0, 0.25)
    r.frame(1.0, 0.25)
    f = p.base_dir / "assets" / "ramp.png"
    Image.fromarray(np.zeros((64, 64), np.uint8)).save(f)
    later = time.time() + 5
    os.utime(f, (later, later))
    b = r.frame(1.0, 0.25)
    assert np.abs(a.astype(int) - b.astype(int)).max() > 20


def test_cache_respects_its_memory_budget():
    p = static_scene()
    r = Renderer(p)
    r.LAYER_BUDGET = 1                     # nothing fits: frames are still right, nothing is kept
    a = r.frame(1.0, 0.5)
    b = r.frame(1.1, 0.5)
    assert r._layer_bytes <= 1 and r.stats["hits"] == 0
    ref = Renderer(p, cache=False).frame(1.1, 0.5)
    assert np.abs(b.astype(int) - ref.astype(int)).max() <= 1 and a.shape == b.shape
