"""Groups: transforms, opacity, timing, nesting and the project operations around them."""
import json

import numpy as np
import pytest

import sciview as sv
from sciview.render import FrameInfo, Renderer


def render(p, t=1.0, scale=0.5):
    info = FrameInfo()
    img = Renderer(p, cache=False).frame(t, scale, info)
    return img.astype(int), info


def box_of(info, oid):
    return next((b for b in info.boxes if b["id"] == oid and not b.get("group")), None)


def plain():
    return sv.Project(duration=4.0, stars=0, vignette=0)


# ------------------------------------------------------------------ 2D
def test_2d_offset_equals_moving_the_members():
    a = plain()
    a.add("rect", position=(600, 550), size=(200, 120), fill_color="teal", enter="none")
    a.add("text", text="Hello", position=(900, 650), size=40, enter="none")
    b = plain()
    r = b.add("rect", position=(500, 500), size=(200, 120), fill_color="teal", enter="none")
    t = b.add("text", text="Hello", position=(800, 600), size=40, enter="none")
    b.group([r, t], offset=(100, 50))
    ia, _ = render(a)
    ib, info = render(b)
    assert np.abs(ia - ib).max() <= 1
    bx = box_of(info, r.id)
    assert bx["x0"] == pytest.approx(600, abs=0.5) and bx["y0"] == pytest.approx(550, abs=0.5)
    g = next(x for x in info.boxes if x.get("group"))
    assert g["x0"] <= bx["x0"] and g["x1"] >= box_of(info, t.id)["x1"]


def test_2d_scale_about_the_pivot():
    p = plain()
    r = p.add("rect", position=(100, 100), size=(50, 40), enter="none")
    p.group([r], scale=2.0, pivot=(0, 0))
    _, info = render(p)
    bx = box_of(info, r.id)
    assert (bx["x0"], bx["y0"]) == pytest.approx((200, 200), abs=2)
    assert (bx["x1"] - bx["x0"], bx["y1"] - bx["y0"]) == pytest.approx((100, 80), abs=4)


def test_group_opacity_fades_members():
    a = plain()
    a.add("rect", position=(500, 500), size=(300, 200), fill_color="teal", fill_opacity=1, opacity=0.4, enter="none")
    b = plain()
    r = b.add("rect", position=(500, 500), size=(300, 200), fill_color="teal", fill_opacity=1, enter="none")
    b.group([r], opacity=0.4)
    assert np.abs(render(a)[0] - render(b)[0]).max() <= 1


def test_group_timing_and_effects_apply_to_members():
    p = plain()
    r = p.add("rect", position=(500, 500), size=(300, 200), enter="none", exit="none")
    g = p.group([r], start=1.0, end=2.0, enter="none", exit="none")
    assert box_of(render(p, 0.5)[1], r.id) is None
    assert box_of(render(p, 1.5)[1], r.id) is not None
    assert box_of(render(p, 2.5)[1], r.id) is None
    # an enter effect on the group fades the member in
    g.enter_effect, g.enter_duration = "fade", 0.5
    early, late = render(p, 1.05)[0], render(p, 1.6)[0]
    assert early.max() < late.max()


def test_nested_groups_add_up():
    p = plain()
    r = p.add("rect", position=(100, 100), size=(40, 40), enter="none")
    inner = p.group([r], offset=(10, 0))
    p.group([inner], offset=(0, 20), scale=2.0, pivot=(0, 0))
    bx = box_of(render(p)[1], r.id)
    assert (bx["x0"], bx["y0"]) == pytest.approx((220, 220), abs=2)


def test_keyframed_group_moves_members():
    p = plain()
    r = p.add("rect", position=(100, 100), size=(40, 40), enter="none")
    g = p.group([r])
    g.key("offset", 0.0, (0, 0), "linear").key("offset", 2.0, (200, 0), "linear")
    assert box_of(render(p, 1.0)[1], r.id)["x0"] == pytest.approx(200, abs=1)


# ------------------------------------------------------------------ 3D
def scene3d():
    p = plain()
    p.camera.props.update(target=[0, 0, 0], distance=200, azimuth=-60, elevation=25, fov=40)
    return p


def test_3d_rotation_and_position_match_moving_the_object():
    a = scene3d()
    a.add("box", center=(5, 10, 0), size=(20, 10, 6), rotation=(0, 0, 90), enter="none")
    b = scene3d()
    x = b.add("box", center=(10, 0, 0), size=(20, 10, 6), enter="none")
    b.group([x], rotation=(0, 0, 90), position=(5, 0, 0))
    ia, ib = render(a)[0], render(b)[0]
    assert np.abs(ia - ib).max() <= 2
    assert np.mean(ia != ib) < 0.002


def test_3d_scale_about_pivot():
    a = scene3d()
    a.add("sphere", center=(20, 0, 0), radius=10, enter="none")
    b = scene3d()
    s = b.add("sphere", center=(10, 0, 0), radius=5, enter="none")
    b.group([s], scale=2.0, pivot3d=(0, 0, 0))
    ia, ib = render(a)[0], render(b)[0]
    assert np.mean(np.abs(ia - ib) > 2) < 0.003


def test_3d_members_sort_by_world_depth():
    p = scene3d()
    near = p.add("box", center=(0, 0, 0), size=(10, 10, 10), fill_color="red", fill_opacity=1, enter="none")
    far = p.add("box", center=(0, 0, 0), size=(10, 10, 10), fill_color="teal", fill_opacity=1, enter="none")
    # move "far" towards the camera through a group: it must then be drawn in front
    cam = p.camera_at(1.0, 1920, 1080)
    toward = (cam.eye - cam.target) / np.linalg.norm(cam.eye - cam.target) * 40
    p.group([far], position=tuple(toward))
    p.group([near], position=(0, 0, 0))
    img = render(p)[0]
    cx, cy = img.shape[1] // 2, img.shape[0] // 2
    px = img[cy - 3:cy + 3, cx - 3:cx + 3].reshape(-1, 3).mean(0)
    assert px[1] > px[0]            # greenish (teal) in front, not red


# ------------------------------------------------------------------ project operations
def test_group_ungroup_and_order():
    p = plain()
    a, b, c = (p.add("rect", name=n) for n in "abc")
    g = p.group([a, c], name="G")
    ids = [o.id for o in p.objects]
    assert ids.index(a.id) < ids.index(c.id) < ids.index(g.id)
    assert ids.index(b.id) < ids.index(a.id)          # the block sits at the top-most member's place
    assert a.parent == c.parent == g.id and b.parent is None
    assert p.children(g) == [a, c] and p.descendants(g.id) == [a, c]
    assert p.ancestors(a) == [g]
    kids = p.ungroup(g)
    assert kids == [a, c] and a.parent is None and p.find(g.id) is None


def test_nested_group_and_remove():
    p = plain()
    a, b = p.add("rect"), p.add("ellipse")
    inner = p.group([a])
    outer = p.group([inner, b])
    assert inner.parent == outer.id and p.ancestors(a) == [inner, outer]
    assert {o.id for o in p.descendants(outer)} == {a.id, b.id, inner.id}
    p.remove(inner, members=False)
    assert a.parent == outer.id and p.find(inner.id) is None
    p.remove(outer)
    assert p.objects == []


def test_json_round_trip_and_problems(tmp_path):
    p = plain()
    a = p.add("rect")
    g = p.group([a], offset=(5, 6))
    p.add("text", text="x", parent="missing")
    t2 = p.add("rect")
    t2.parent = a.id                                   # not a group
    f = p.save(tmp_path / "g.sciview.json")
    data = json.loads(f.read_text())
    assert data["objects"][0]["parent"] == g.id
    q = sv.Project.load(f)
    assert q.find(a.id).parent == g.id and q.find(g.id).props["offset"] == [5, 6]
    msgs = [x for x in q.problems() if x["prop"] == "parent"]
    assert {x["id"] for x in msgs} == {q.objects[2].id, t2.id}


def test_circular_groups_do_not_hang():
    p = plain()
    r = p.add("rect", position=(100, 100), size=(40, 40), enter="none")
    g1 = p.group([r])
    g2 = p.group([g1])
    g2.parent = g1.id                                  # g1 -> g2 -> g1
    assert any("circle" in x["message"] and x["prop"] == "parent" for x in p.problems())
    img, info = render(p)
    assert img.shape[0] > 0
    assert p.ancestors(r) in ([g1, g2], [g1])
