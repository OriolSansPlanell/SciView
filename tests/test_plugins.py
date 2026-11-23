"""Plugins found through entry points: object types, template packs, failures that do not stop SciView, and the
scaffold of a new plugin. An installed plugin is simulated with a package and a .dist-info folder on sys.path."""
import importlib
import json
import sys

import numpy as np
import pytest

import sciview as sv
from sciview import plugins
from sciview.model.base import REGISTRY

PLUGIN = '''
import sciview as sv
from sciview import Object2D, Prop


@sv.register
class Star(Object2D):
    TYPE, LABEL, CATEGORY, ICON = "fakeplug_star", "Star", "Fake plugin", "ellipse"
    PROPS = [Prop("center", "vec2", [960, 540]), Prop("color", "color", "gold")]

    def draw(self, cv, ctx, v, st):
        x, y = (v.center[0] + st.dx) * ctx.s, (v.center[1] + st.dy) * ctx.s
        cv.circle(x, y, 40 * ctx.s, fill=v.color, fill_alpha=v.opacity * st.opacity)
        return x - 40 * ctx.s, y - 40 * ctx.s, x + 40 * ctx.s, y + 40 * ctx.s
'''


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """A package 'fakeplug' with an object type, a template pack and a broken entry point, as if installed."""
    pkg = tmp_path / "site" / "sciview_fakeplug"
    (pkg / "templates" / "starry").mkdir(parents=True)
    (pkg / "__init__.py").write_text("from pathlib import Path\nTEMPLATES = Path(__file__).parent / 'templates'\n")
    (pkg / "objects.py").write_text(PLUGIN)
    (pkg / "broken.py").write_text("raise RuntimeError('this plugin is broken')\n")
    (pkg / "templates" / "starry" / "project.sciview.json").write_text(json.dumps({
        "sciview": "1.0", "template": {"title": "Starry", "description": "A star", "thumb_time": 1},
        "settings": {"duration": 3}, "objects": [{"id": "s1", "type": "fakeplug_star"}]}))
    (pkg / "templates" / "title_card").mkdir()                   # a name the built-ins already use
    (pkg / "templates" / "title_card" / "project.sciview.json").write_text('{"sciview": "1.0"}')
    info = tmp_path / "site" / "sciview_fakeplug-0.3.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: sciview-fakeplug\nVersion: 0.3\n")
    (info / "entry_points.txt").write_text(
        "[sciview.objects]\nfakeplug = sciview_fakeplug.objects\nbad = sciview_fakeplug.broken\n\n"
        "[sciview.templates]\nfakeplug = sciview_fakeplug:TEMPLATES\n")
    before = dict(REGISTRY)
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    importlib.invalidate_caches()
    yield tmp_path
    REGISTRY.clear()
    REGISTRY.update(before)
    for m in [m for m in sys.modules if m.startswith("sciview_fakeplug")]:
        del sys.modules[m]
    monkeypatch.undo()
    plugins.load(force=True)


def test_plugins_add_object_types_templates_and_report_failures(installed, tmp_path):
    with pytest.warns(UserWarning, match="this plugin is broken"):
        recs = plugins.load(force=True)
    by = {(r["group"], r["name"]): r for r in recs}
    ok = by[("sciview.objects", "fakeplug")]
    assert ok["ok"] and ok["provides"] == ["fakeplug_star"] and ok["package"] == "sciview-fakeplug"
    assert not by[("sciview.objects", "bad")]["ok"] and "broken" in by[("sciview.objects", "bad")]["error"]
    assert by[("sciview.templates", "fakeplug")]["provides"] == ["starry", "title_card"]
    assert "fakeplug_star" in sv.object_types()
    assert "Fake plugin" in sv.all_schemas()["categories"]
    text = plugins.describe()
    assert "fakeplug_star" in text and "FAILED" in text

    from sciview.server import instantiate_template, list_templates
    listed = {t["name"]: t for t in list_templates()}
    assert listed["starry"]["plugin"] == "fakeplug" and listed["title_card"]["plugin"] == ""
    assert listed["fakeplug-title_card"]["plugin"] == "fakeplug"       # renamed: the built-in keeps its name
    film = instantiate_template("starry", tmp_path / "film")
    assert film.objects[0].TYPE == "fakeplug_star"
    img = film.frame(1.5, 0.25)
    assert img[135, 240].max() > 150                                    # the plugin's star, in the middle


def test_plugins_can_be_switched_off(installed, monkeypatch):
    monkeypatch.setenv("SCIVIEW_NO_PLUGINS", "1")
    assert plugins.load(force=True) == [] and "fakeplug_star" not in sv.object_types()
    assert "off" in plugins.describe()


def test_a_film_made_with_a_plugin_opens_without_it(installed, tmp_path):
    with pytest.warns(UserWarning):
        plugins.load(force=True)
    film = sv.Project(path=tmp_path / "f.sciview.json", duration=2)
    film.add("fakeplug_star", color="teal", start=0.5)
    film.save()
    del REGISTRY["fakeplug_star"]                                       # the plugin is gone
    again = sv.load(film.path)
    assert again.objects[0].TYPE == "fakeplug_star" and "plugin" in again.validate()[0]
    again.save()
    REGISTRY["fakeplug_star"] = sys.modules["sciview_fakeplug.objects"].Star   # and back
    back = sv.load(film.path)
    assert back.objects[0].props["color"] == "teal" and back.objects[0].start == 0.5


def test_plugin_command_and_scaffold(tmp_path, capsys):
    from sciview.cli import main
    assert main(["plugin", "list"]) == 0
    assert main(["plugin", "new", "My Lab!", "--folder", str(tmp_path)]) == 0
    root = tmp_path / "sciview-my-lab"
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert {"pyproject.toml", "README.md", "src/sciview_my_lab/__init__.py", "src/sciview_my_lab/objects.py",
            "src/sciview_my_lab/templates/my_lab_demo/project.sciview.json", "tests/test_plugin.py"} <= files
    py = (root / "pyproject.toml").read_text()
    assert '[project.entry-points."sciview.objects"]\nmy_lab = "sciview_my_lab.objects"' in py
    tomllib = pytest.importorskip("tomllib")
    assert tomllib.loads(py)["project"]["entry-points"]["sciview.templates"]["my_lab"] == "sciview_my_lab:TEMPLATES"
    tpl = json.loads((root / "src/sciview_my_lab/templates/my_lab_demo/project.sciview.json").read_text())
    assert tpl["objects"][1]["type"] == "my_lab_pulse"
    compile((root / "src/sciview_my_lab/objects.py").read_text(), "objects.py", "exec")
    assert main(["plugin", "new", "My Lab!", "--folder", str(tmp_path)]) == 1          # exists already
    with pytest.raises(ValueError):
        from sciview.scaffold import new_plugin
        new_plugin("9lives", tmp_path)


def test_the_scaffolded_object_draws(tmp_path, monkeypatch):
    from sciview.scaffold import new_plugin
    root = new_plugin("demo_plug", tmp_path)
    monkeypatch.syspath_prepend(str(root / "src"))
    before = dict(REGISTRY)
    try:
        importlib.import_module("sciview_demo_plug.objects")
        film = sv.Project(duration=3, stars=0)
        film.add("demo_plug_pulse")
        a, b = film.frame(0.8, 0.25), film.frame(1.3, 0.25)
        assert a.max() > 60 and not np.array_equal(a, b)
    finally:
        REGISTRY.clear()
        REGISTRY.update(before)
        sys.modules.pop("sciview_demo_plug.objects", None)
        sys.modules.pop("sciview_demo_plug", None)
