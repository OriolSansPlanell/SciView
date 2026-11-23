import json

import numpy as np
import pytest

import sciview as sv
from sciview.model.base import REGISTRY, Prop, parse_array


def test_registry_has_all_types():
    expected = {"box", "cylinder", "sphere", "screen", "beam", "arrow3d", "grid3d", "pointcloud", "mesh", "label3d",
                "title", "caption", "text", "equation", "legend", "panel", "rect", "ellipse", "arrow", "image",
                "axes", "curve", "scatter", "bars", "histogram", "marker", "guide"}
    assert expected <= set(REGISTRY)


def test_every_schema_is_complete():
    for cls in REGISTRY.values():
        sc = cls.schema()
        assert sc["label"] and sc["category"] and sc["icon"] and sc["description"], cls
        names = [p["name"] for p in sc["props"]]
        assert len(names) == len(set(names)), f"duplicate props in {cls.TYPE}"
        assert "opacity" in names or cls.TYPE == "voice"    # a voice clip is heard, not drawn
        # property names must not collide with timing keywords of Project.add
        assert not {"start", "end", "enter", "exit", "id", "name"} & set(names), cls.TYPE


def test_prop_coercion():
    assert Prop("a", "number", 0).coerce("2.5") == 2.5
    assert Prop("a", "int", 0).coerce(2.6) == 3
    assert Prop("a", "bool", False).coerce("yes") is True
    assert Prop("a", "vec3", [0, 0, 0]).coerce((1, 2)) == [1.0, 2.0, 0.0]
    assert Prop("a", "enum", "x", options=("x", "y")).coerce("z") == "x"
    assert Prop("a", "color", "teal").coerce([255, 0, 0]) == "#ff0000"
    assert Prop("a", "array", "").coerce(np.arange(3)) == [0.0, 1.0, 2.0]
    assert Prop("a", "number", 1.0).coerce("not a number") == 1.0
    assert list(parse_array("1, 2 3;4")) == [1, 2, 3, 4]


def test_keyframes_interpolate_with_easing():
    p = sv.Project()
    b = p.add("box")
    b.key("glow", 0, 0.0, "linear").key("glow", 2, 2.0, "linear")
    assert b.value_at("glow", 1.0) == pytest.approx(1.0)
    assert b.value_at("glow", -1) == 0 and b.value_at("glow", 9) == 2
    b.key("center", 0, (0, 0, 0)).key("center", 1, (10, 0, 0), "smooth")
    assert b.value_at("center", 0.5)[0] == pytest.approx(5.0)
    b.key("edge_color", 0, "#000000", "linear").key("edge_color", 1, "#ffffff", "linear")
    assert np.allclose(b.value_at("edge_color", 0.5), [0.5, 0.5, 0.5])
    with pytest.raises(ValueError):
        b.key("label_position", 0, "below")  # enums are not animatable
    with pytest.raises(KeyError):
        b.key("nope", 0, 1)


def test_replacing_a_keyframe_at_the_same_time():
    b = sv.Project().add("box")
    b.key("glow", 1.0, 0.5).key("glow", 1.0, 0.8)
    assert len(b.keys["glow"]) == 1 and b.keys["glow"][0]["v"] == 0.8


def test_enter_exit_effects():
    p = sv.Project(duration=10)
    t = p.add("text", start=2, end=6)
    t.appear(effect="fade", duration=1).disappear(effect="slide_up", duration=1)
    assert t.state(1.9, 10) is None
    assert t.state(2.5, 10).opacity == pytest.approx(0.5)
    assert t.state(4, 10).opacity == 1
    st = t.state(5.5, 10)
    assert st.opacity == pytest.approx(0.5) and st.dy < 0
    assert t.state(6.1, 10) is None
    c = p.add("curve", start=0)
    c.appear(effect="draw", duration=2)
    assert c.state(1, 10).progress == pytest.approx(0.5)


def test_exit_needs_an_end_time():
    t = sv.Project(duration=5).add("text")
    assert t.state(4.99, 5).opacity == 1


def test_project_json_roundtrip(tmp_path):
    p = sv.Project(duration=4, title="Round trip")
    ax = p.add("axes", name="Chart")
    p.add("curve", axes=ax, expression="sin(x)")
    b = p.add("box", label="source", start=1, end=3)
    b.key("glow", 1, 0).key("glow", 2, 1.5)
    p.camera.key("azimuth", 0, -50).key("azimuth", 4, -20)
    path = p.save(tmp_path / "rt.sciview.json")
    q = sv.load(path)
    assert q.to_json() == p.to_json()
    assert q.find("curve1").get("axes") == ax.id
    data = json.loads(path.read_text())
    assert data["sciview"] == "1.0"
    assert "label" in data["objects"][2]["props"]
    assert "edge_color" not in data["objects"][2]["props"]  # defaults are not written


def test_unknown_things_become_warnings():
    data = {"sciview": "1.0", "settings": {"duration": 3, "bogus": 1},
            "objects": [{"type": "spaceship"}, {"type": "box", "props": {"wings": 2}}]}
    p = sv.Project.from_json(data)
    assert len(p.objects) == 2 and p.objects[0].TYPE == "spaceship"     # kept, not drawn
    issues = p.validate()
    assert any("spaceship" in i for i in issues)
    assert any("wings" in i for i in issues)
    assert any("bogus" in i for i in issues)


def test_validate_finds_problems(tmp_project):
    p = tmp_project
    p.add("image", image="assets/missing.png")
    p.add("curve", expression="import os")
    p.add("scatter")
    p.add("marker", axes="nowhere")
    issues = "\n".join(p.validate())
    assert "missing.png" in issues
    assert "not allowed" in issues or "cannot read" in issues
    assert "choose a chart" in issues
    assert "missing object" in issues


def test_add_rejects_unknown_type_and_property():
    p = sv.Project()
    with pytest.raises(ValueError):
        p.add("spaceship")
    with pytest.raises(KeyError):
        p.add("box", wings=2)


def test_unique_ids_and_copy():
    p = sv.Project()
    a, b = p.add("box"), p.add("box")
    assert a.id != b.id
    c = p.add(a.copy())
    assert c.id not in (a.id, b.id)


def test_captions_to_srt():
    p = sv.Project(duration=10)
    p.add("caption", text="First H_2O", start=0, end=2.5)
    p.add("caption", text="Second", start=3)
    srt = p.captions_srt()
    assert "00:00:00,000 --> 00:00:02,500\nFirst H2O" in srt
    assert "00:00:03,000 --> 00:00:07,000" in srt  # default caption duration


def test_light_theme():
    p = sv.Project().use_light_theme()
    assert p.settings["background"] == "#ffffff" and p.settings["stars"] == 0
