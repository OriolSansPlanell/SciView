"""The file format's promises for 1.x: films from every release open, nothing unknown is lost on saving,
older formats are migrated, and the published JSON Schema matches what SciView writes."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

import sciview as sv
from sciview.model import migrate as M
from sciview.model.base import MissingObject

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = sorted((ROOT / "tests" / "golden").glob("*/*.sciview.json"))
TEMPLATES = ROOT / "src" / "sciview" / "templates"


def test_there_are_golden_files_from_every_release():
    assert {p.parent.name for p in GOLDEN} >= {"0.1", "0.2", "0.3", "0.4"}


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: f"{p.parent.name}/{p.stem.split('.')[0]}")
def test_films_from_every_release_open_unchanged(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    name = path.name.split(".")[0]
    p = sv.Project.from_json(data, TEMPLATES / name / "project.sciview.json")   # assets from the template folder
    assert p.warnings == [] and p.notes == []
    assert not any(isinstance(o, MissingObject) for o in p.objects)
    assert all(o.warnings == [] for o in p.objects)
    again = sv.Project.from_json(p.to_json()).to_json()
    assert again == p.to_json()                                 # saving is stable
    img = p.frame(p.duration * 0.5, 0.1)
    assert img.shape == (108, 192, 3) and img.max() > 20


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: f"{p.parent.name}/{p.stem.split('.')[0]}")
def test_golden_files_match_the_schema(path):
    pytest.importorskip("jsonschema")
    from sciview import schema
    assert schema.validate(json.loads(path.read_text(encoding="utf-8")), strict=True) == []


def test_what_this_version_writes_matches_the_strict_schema(tmp_path):
    pytest.importorskip("jsonschema")
    from sciview import schema
    p = sv.Project(duration=4)
    box = p.add("box", size=(10, 10, 10))
    box.key("glow", 0, 0.5).key("glow", 2, 1.5, ease="bezier", bez=(0.2, 1.4, 0.6, 1))
    p.add("caption", text="Hi", style="box")
    s2 = p.add_scene("Two", 3, transition="crossfade")
    s2.camera.key("azimuth", 0, -20)
    g = p.group([p.add("rect", scene=s2), p.add("ellipse", scene=s2)])
    g.set("opacity", 0.5)
    p.apply_theme("light")
    assert schema.validate(p.to_json(), strict=True) == []


def test_the_published_schema_is_up_to_date():
    from sciview import schema
    published = json.loads((ROOT / "docs" / "schema" / "sciview-1.json").read_text(encoding="utf-8"))
    assert published == json.loads(schema.dumps()), "run: python tools/gen_docs.py"
    assert published["$id"] == schema.SCHEMA_ID


def test_the_schema_catches_mistakes():
    pytest.importorskip("jsonschema")
    from sciview import schema
    d = json.loads((ROOT / "tests" / "golden" / "0.4" / "explainer.sciview.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(d)
    bad["sciview"] = "2.0"
    bad["scenes"][1]["transition"] = "spin"
    bad["objects"][0]["props"]["text"] = 5
    bad["objects"][1]["props"]["unknown"] = 1
    found = " | ".join(schema.validate(bad))
    assert "sciview" in found and "spin" in found and "objects/0/props/text" in found
    assert "unknown" not in found                                    # allowed unless strict
    assert "unknown" in " | ".join(schema.validate(bad, strict=True))


# ---------------------------------------------------------------------------------------------- nothing is lost
FUTURE = {
    "sciview": "1.3",
    "made_with": {"app": "SciView 1.3"},
    "settings": {"duration": 5, "hologram_mode": True},
    "scenes": [{"id": "scene1", "name": "Intro", "duration": 3, "mood": "calm"},
               {"id": "scene2", "name": "Main", "duration": 2, "transition": "crossfade"}],
    "objects": [
        {"id": "g1", "type": "group", "name": "Panel"},
        {"id": "spec1", "type": "spectroscopy_pulse", "name": "Pulse", "parent": "g1", "scene": "scene2",
         "props": {"color": "gold", "rings": 4}, "keys": {"radius": [{"t": 0, "v": 10}, {"t": 1, "v": 90}]},
         "start": 0.2, "end": 1.8, "enter": {"effect": "fade", "duration": 0.3}, "future_field": [1, 2]},
        {"id": "caption1", "type": "caption", "name": "Words", "scene": "scene1",
         "props": {"text": "Hello", "shimmer": 0.4}, "keys": {"shimmer": [{"t": 0, "v": 0}, {"t": 2, "v": 1}]},
         "tracks": {"wobble": {"data": "assets/w.csv", "column": "w"}}, "notes": "new field"},
    ],
}


def test_unknown_parts_are_kept_when_saving(tmp_path):
    p = sv.Project.from_json(copy.deepcopy(FUTURE), tmp_path / "f.sciview.json")
    msgs = " | ".join(p.validate())
    assert "newer SciView (format 1.3)" in msgs and "spectroscopy_pulse" in msgs and "shimmer" in msgs
    assert "hologram_mode" in msgs
    pulse = p.find("spec1")
    assert isinstance(pulse, MissingObject) and pulse.TYPE == "spectroscopy_pulse" and pulse.parent == "g1"
    assert p.find("caption1").props["text"] == "Hello"
    pulse.start = 0.5                                                # timing can still be changed
    p.save()
    out = json.loads((tmp_path / "f.sciview.json").read_text())
    assert out["made_with"] == FUTURE["made_with"] and out["settings"]["hologram_mode"] is True
    assert out["scenes"][0]["mood"] == "calm"
    saved = {o["id"]: o for o in out["objects"]}
    want = dict(FUTURE["objects"][1], start=0.5)
    assert saved["spec1"] == want
    cap = saved["caption1"]
    assert cap["props"]["shimmer"] == 0.4 and cap["keys"]["shimmer"] == FUTURE["objects"][2]["keys"]["shimmer"]
    assert cap["tracks"]["wobble"]["column"] == "w" and cap["notes"] == "new field"
    assert out["sciview"] == M.FORMAT_VERSION
    img = p.frame(4.0, 0.1)                                          # unknown objects draw nothing
    assert np.isfinite(img).all()


def test_unknown_objects_cannot_be_edited_but_can_be_copied_and_grouped():
    p = sv.Project.from_json(copy.deepcopy(FUTURE))
    pulse = p.find("spec1")
    with pytest.raises(KeyError, match="does not know"):
        pulse.set("rings", 2)
    with pytest.raises(KeyError):
        pulse.key("radius", 0, 5)
    twin = pulse.copy("spec2")
    assert twin.TYPE == "spectroscopy_pulse" and twin.to_json()["props"] == {"color": "gold", "rings": 4}
    tools = __import__("sciview.agent", fromlist=["FilmTools"]).FilmTools(p)
    assert any(o["type"] == "spectroscopy_pulse" for o in tools.call("describe_film", {})["objects"])


def test_migrations_run_in_order(monkeypatch):
    def rename(d):
        for o in d.get("objects", []):
            if o.get("type") == "caption" and "words" in o.get("props", {}):
                o["props"]["text"] = o["props"].pop("words")
        return d
    monkeypatch.setattr(M, "MIGRATIONS", [("0.9", "1.0", rename, "caption 'words' is now 'text'")])
    old = {"sciview": "0.9", "objects": [{"type": "caption", "props": {"words": "Hi"}}]}
    p = sv.Project.from_json(old)
    assert p.warnings == [] and p.objects[0].props["text"] == "Hi"
    assert p.notes == ["converted from format 0.9 to 1.0: caption 'words' is now 'text'"]
    assert old["objects"][0]["props"] == {"words": "Hi"}                 # the caller's data is not changed


def test_format_versions():
    assert M.compatibility("1.0") is None and M.compatibility("1") is None
    assert "newer" in M.compatibility("1.7")
    assert "format 2.0" in M.compatibility("2.0")
    assert M.parse_version("1.12") == (1, 12) and M.parse_version("x") == (0, 0)


def test_schema_command(tmp_path, capsys):
    pytest.importorskip("jsonschema")
    from sciview.cli import main
    out = tmp_path / "s.json"
    assert main(["schema", "-o", str(out)]) == 0
    assert json.loads(out.read_text())["$id"].endswith("sciview-1.json")
    good = GOLDEN[0]
    bad = tmp_path / "bad.sciview.json"
    bad.write_text(json.dumps({"sciview": "1.0", "objects": [{"type": "box", "props": {"size": "big"}}]}))
    assert main(["schema", "--validate", str(good)]) == 0
    assert main(["schema", "--validate", str(bad)]) == 1
    assert "objects/0/props/size" in capsys.readouterr().out
