"""Scenes: their own objects, camera and clock; transitions; chapters; files from before scenes."""
import json

import numpy as np
import pytest

import sciview as sv
from sciview.engine.transitions import TRANSITIONS, blend
from sciview.render import FrameInfo, Renderer


def two_scenes(**kw):
    p = sv.Project(duration=4, stars=0, **kw)
    p.add("rect", name="Red", position=(0, 0), size=(1920, 1080), fill_color="#ff0000", fill_opacity=1, enter="none")
    s2 = p.add_scene("Blue", 3, transition="crossfade", transition_duration=1.0)
    s2.add("rect", name="Blue", position=(0, 0), size=(1920, 1080), fill_color="#0000ff", fill_opacity=1, enter="none")
    return p


def mean_rgb(img):
    return img.reshape(-1, 3).mean(axis=0)


def test_scenes_are_laid_end_to_end_with_overlapping_transitions():
    p = two_scenes()
    s3 = p.add_scene("Cut", 2)                        # a cut does not overlap
    assert [round(a, 3) for _sc, a, _b in p.timeline()] == [0.0, 3.0, 6.0]
    assert p.duration == pytest.approx(8.0) and p.settings["duration"] == pytest.approx(8.0)
    assert [sc.name for sc, _t in p.scenes_at(3.5)] == ["Scene 1", "Blue"]
    assert p.scenes_at(3.5)[-1][1] == pytest.approx(0.5)
    assert p.scenes_at(99)[-1][0] is s3 and p.scenes_at(-1)[0][0] is p.scenes[0]
    p.scenes[1].transition_duration = 10                   # longer than the scenes: shortened
    assert p.overlap(p.scenes[1]) == pytest.approx(2.85)
    assert any("shortened" in q["message"] for q in p.problems())


def test_objects_belong_to_scenes_and_use_scene_time():
    p = two_scenes()
    blue = p.find("rect2")
    assert p.find("rect1").scene == "scene1" and blue.scene == "scene2"
    assert p.scene_of(blue).name == "Blue" and p.film_time(blue, 0.5) == pytest.approx(3.5)
    assert [o.name for o in p.scenes[1].objects] == ["Blue"]
    assert p.current_scene.name == "Blue"                 # add() goes to the last scene added
    c = p.add("caption", text="Into the current scene")
    assert c.scene == "scene2"
    p.current_scene = "scene1"
    assert p.add("caption").scene == "scene1" and p.camera is p.scenes[0].camera
    with pytest.raises(KeyError):
        p.current_scene = "nope"
    late = p.scenes[1].add("caption", start=5)
    assert any(q["id"] == late.id and "after its scene ends" in q["message"] for q in p.problems())


def test_frames_follow_scenes_and_crossfade():
    p = two_scenes()
    r = p.renderer()
    a, mid, b = (mean_rgb(r.frame(t, 0.1)) for t in (1.0, 3.5, 5.0))
    assert a[0] > 200 and a[2] < 30
    assert b[2] > 200 and b[0] < 30
    assert 70 < mid[0] < 185 and 70 < mid[2] < 185            # halfway through the crossfade
    alone = mean_rgb(r.frame(0.5, 0.1, scene="scene2"))        # a scene on its own, at its own time
    assert alone[2] > 200 and alone[0] < 30


@pytest.mark.parametrize("kind", [k for k in TRANSITIONS if k != "cut"])
def test_every_transition_goes_from_a_to_b(kind):
    a = np.zeros((40, 64, 3), np.float32)
    a[..., 0] = 1
    b = np.zeros_like(a)
    b[..., 2] = 1
    assert np.allclose(blend(a, b, kind, 0.0), a, atol=1e-3)
    assert np.allclose(blend(a, b, kind, 1.0), b, atol=1e-3)
    half = blend(a, b, kind, 0.5)
    assert half.shape == a.shape and np.isfinite(half).all()
    if kind == "dip":
        assert half.max() < 0.05                                # passes through the background
    elif kind.startswith(("wipe", "push")):
        assert half[..., 0].mean() == pytest.approx(0.5, abs=0.08)
    with pytest.raises(ValueError):
        blend(a, b, "explode", 0.5)


def test_cut_and_scene_cameras():
    p = sv.Project(duration=2, stars=0)
    p.add("box", size=(30, 30, 30), enter="none")
    s2 = p.add_scene("Other angle", 2)
    s2.add("box", size=(30, 30, 30), enter="none")
    assert s2.camera is not p.scenes[0].camera
    assert s2.camera.props["azimuth"] == p.scenes[0].camera.props["azimuth"]   # starts where scene 1 ended
    s2.camera.set("azimuth", 40)
    a = p.frame(1.9, 0.25)
    b = p.frame(2.1, 0.25)
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 1      # a cut to a new camera
    p.current_scene = "scene1"
    assert not np.allclose(p.camera_at(0.5, 192, 108, rig=s2.camera).eye, p.camera_at(0.5, 192, 108).eye)


def test_scenes_round_trip_and_single_scene_files_stay_as_before(tmp_path):
    p = two_scenes()
    p.scenes[1].notes = "Say it slowly"
    p.scenes[0].chapter = False
    p.scenes[1].camera.key("azimuth", 0, -40).key("azimuth", 3, 10)
    p.save(tmp_path / "f.sciview.json")
    d = json.loads((tmp_path / "f.sciview.json").read_text())
    assert [s["id"] for s in d["scenes"]] == ["scene1", "scene2"] and "camera" not in d["scenes"][0]
    assert d["objects"][1]["scene"] == "scene2" and d["settings"]["duration"] == pytest.approx(6.0)
    q = sv.load(tmp_path / "f.sciview.json")
    assert [sc.name for sc in q.scenes] == ["Scene 1", "Blue"] and q.scenes[1].notes == "Say it slowly"
    assert not q.scenes[0].chapter and q.scenes[1].camera.keys["azimuth"][1]["v"] == 10
    assert np.array_equal(q.frame(3.5, 0.1), p.frame(3.5, 0.1))
    one = sv.Project(duration=5)
    one.add("caption")
    d1 = one.to_json()
    assert "scenes" not in d1 and "scene" not in d1["objects"][0]


def test_files_from_before_scenes_load_as_one_scene():
    old = {"sciview": "1.0", "settings": {"duration": 7}, "camera": {"props": {"azimuth": 12}},
           "objects": [{"id": "caption1", "type": "caption", "props": {"text": "Hi"}, "start": 1}]}
    p = sv.Project.from_json(old)
    assert len(p.scenes) == 1 and p.scenes[0].duration == 7 and p.camera.props["azimuth"] == 12
    assert p.objects[0].scene == "scene1" and p.warnings == []
    bad = dict(old, scenes=[{"id": "a", "transition": "spin"}, {"id": "a"}],
               objects=[{"id": "x", "type": "caption", "scene": "missing"}])
    q = sv.Project.from_json(bad)
    assert [sc.id for sc in q.scenes] == ["a", "a_2"] and q.scenes[0].transition == "cut"
    assert q.objects[0].scene == "a" and len(q.warnings) == 3


def test_scene_management():
    p = two_scenes()
    s3 = p.add_scene("Three", 2, after="scene1")
    assert [sc.name for sc in p.scenes] == ["Scene 1", "Three", "Blue"]
    p.move_scene(s3, 2)
    assert [sc.name for sc in p.scenes] == ["Scene 1", "Blue", "Three"]
    p.remove_scene("Blue")
    assert [sc.name for sc in p.scenes] == ["Scene 1", "Three"] and p.find("rect2") is None
    with pytest.raises(ValueError):
        sv.Project().remove_scene("scene1")
    with pytest.raises(ValueError):
        p.add_scene("x", id="scene1")
    with pytest.raises(ValueError):
        p.scenes[0].set_transition("spin")
    g_err = p.add("caption", scene="scene1")
    other = p.add("caption", scene=s3)
    with pytest.raises(ValueError, match="one scene"):
        p.group([g_err, other])


def test_chapters_and_captions_use_film_time():
    p = two_scenes()
    p.find("rect1").scene = "scene1"
    p.add("caption", text="One", start=0.5, end=1.5, scene="scene1")
    p.add("caption", text="Two", start=0.5, end=2.0, scene="scene2")
    assert p.chapters() == [(0.0, 3.5, "Scene 1"), (3.5, 6.0, "Blue")]
    assert p.captions() == [(0.5, 1.5, "One"), (3.5, 5.0, "Two")]
    assert p.captions("scene2") == [(0.5, 2.0, "Two")]
    p.scenes[1].chapter = False
    assert p.chapters() == [(0.0, 6.0, "Scene 1")]


def test_cache_is_exact_across_scenes():
    p = two_scenes()
    p.add("caption", text="Words", start=0.2, scene="scene1")
    p.add("box", size=(20, 20, 20), scene="scene2")
    cached = Renderer(p)
    plain = Renderer(p, cache=False)
    for t in (0.5, 1.0, 3.2, 3.6, 4.5, 5.5, 1.0, 3.6):
        assert np.array_equal(cached.frame(t, 0.25), plain.frame(t, 0.25)), t
    assert cached.stats["hits"] > 0


def test_frame_info_names_objects_of_both_scenes_in_a_transition():
    p = two_scenes()
    info = FrameInfo()
    p.renderer().frame(3.5, 0.1, info)
    assert {b["id"] for b in info.boxes} == {"rect1", "rect2"}
