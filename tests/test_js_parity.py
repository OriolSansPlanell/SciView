"""The editor previews values with its own JavaScript interpolation (state.js); it must agree with Python's,
which renders the frames. Runs the same cases through both, in Node."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

import sciview as sv
from sciview.engine.color import parse_color
from sciview.engine.easing import EASING_NAMES, ease

NODE = shutil.which("node")
STATE = Path(__file__).resolve().parents[1] / "src" / "sciview" / "gui" / "js" / "state.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def run_js(cases, tmp_path):
    p = sv.Project()
    data = {"types": {t["type"]: t for t in sv.all_schemas()["types"]}, "palette": p.palette, "cases": cases}
    f = tmp_path / "cases.json"
    f.write_text(json.dumps(data))
    r = subprocess.run([NODE, str(Path(__file__).parent / "js" / "parity.mjs"), STATE.as_uri(), str(f)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_easings_agree(tmp_path):
    bez = [[0.25, 0.1, 0.25, 1], [0.34, 1.56, 0.64, 1], [0.7, -0.4, 0.3, 1.3], [0, 0, 1, 1]]
    cases, want = [], []
    for name in EASING_NAMES:
        for u in np.linspace(0, 1, 23):
            for b in (bez if name == "bezier" else [None]):
                cases.append({"ease": name, "u": float(u), "bez": b})
                want.append(ease(name, float(u), b))
    got = run_js(cases, tmp_path)
    assert np.allclose(got, want, atol=1e-6)


def test_keyframed_values_agree(tmp_path):
    film = sv.Project()
    box = film.add("rect", position=(10, 20), size=(100, 50), fill_color="teal")
    box.key("position", 0, (0, 0)).key("position", 2, (300, -40), ease="overshoot")
    box.key("position", 3, (310, 10), ease="bezier", bez=(0.2, 1.5, 0.5, 1))
    box.key("fill_color", 0, "teal").key("fill_color", 2, "#ff8000", ease="sine").key("fill_color", 4, "gold",
                                                                                      ease="hold")
    box.key("opacity", 0.5, 0.0).key("opacity", 1.5, 1.0, ease="in_out")
    marker = film.add("text", value=0)
    marker.key("value", 0, 0).key("value", 4, 1000, ease="linear")
    cases, want = [], []
    obj_json = {o.id: o.to_json() for o in film.objects}
    for o, name in ((box, "position"), (box, "fill_color"), (box, "opacity"), (marker, "value")):
        for t in np.linspace(-0.5, 4.5, 41):
            cases.append({"obj": obj_json[o.id], "prop": name, "t": float(t)})
            want.append(o.value_at(name, float(t)))
    got = run_js(cases, tmp_path)
    for c, g, w in zip(cases, got, want):
        if c["prop"] == "fill_color":
            assert np.allclose(parse_color(g, film.palette), parse_color(w, film.palette), atol=1.5 / 255), (c["t"], g, w)
        else:
            assert np.allclose(np.asarray(g, float), np.asarray(w, float), atol=1e-6), (c["prop"], c["t"], g, w)
