"""End-to-end editor tests in a headless browser. Run with: pytest -m gui (needs `pip install playwright`
and `playwright install chromium`)."""
import json
import threading
import time

import numpy as np
import pytest

import sciview as sv
from sciview.server import make_server

pytestmark = pytest.mark.gui
playwright = pytest.importorskip("playwright.sync_api")

STATE = "() => import('/gui/js/state.js').then(m => ({sel: m.S.selection, primary: m.S.selected, " \
        "boxes: m.S.boxes, time: m.S.time, saved: m.S.saved}))"


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as pw:
        try:
            # a fake microphone, already allowed, for recording narration
            b = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        except Exception as exc:  # browsers not installed
            pytest.skip(f"chromium not available: {exc}")
        yield b
        b.close()


class Editor:
    """A running editor server plus a browser page on it; collects page errors."""

    def __init__(self, browser, project, folder, recovery=False):
        self.srv = make_server(project, folder, port=18900)
        if recovery:
            self.srv.session.check_recovery()
        self.srv.session.start_background(autosave_interval=0, prefetch=True)
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.url = f"http://localhost:{self.srv.server_address[1]}/"
        self.folder = folder
        self.errors = []
        self.page = browser.new_page(viewport={"width": 1500, "height": 900})
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.on("dialog", lambda d: d.accept())
        self.page.goto(self.url)

    @property
    def project(self):
        return self.srv.session.project

    def state(self):
        return self.page.evaluate(STATE)

    def settle(self, ms=600):
        self.page.wait_for_timeout(ms)

    def seek(self, t):
        self.page.fill("#timeInput", str(t))
        self.page.press("#timeInput", "Enter")
        self.wait_frame(t)

    def wait_frame(self, t=None):
        for _ in range(100):
            st = self.state()
            if st["boxes"] and (t is None or abs(st["time"] - t) < 1e-6):
                break
            self.page.wait_for_timeout(50)
        self.settle(300)

    def design_to_page(self, x, y):
        bb = self.page.locator("#overlay").bounding_box()
        k = bb["width"] / 1920
        return bb["x"] + x * k, bb["y"] + y * k

    def box_center(self, oid):
        b = next(b for b in self.state()["boxes"] if b["id"] == oid and not b.get("group"))
        return self.design_to_page((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2)

    def drag(self, x, y, dx, dy, modifiers=()):
        for m in modifiers:
            self.page.keyboard.down(m)
        self.page.mouse.move(x, y)
        self.page.mouse.down()
        self.page.mouse.move(x + dx / 2, y + dy / 2, steps=4)
        self.page.mouse.move(x + dx, y + dy, steps=4)
        self.page.mouse.up()
        for m in modifiers:
            self.page.keyboard.up(m)
        self.settle()

    def row(self, name):
        return self.page.locator(".tl-label", has_text=name).first

    def close(self):
        self.page.close()
        self.srv.session.stop.set()
        self.srv.shutdown()
        self.srv.server_close()
        assert not self.errors, self.errors


@pytest.fixture
def open_editor(browser, tmp_path):
    made = []

    def make(project=None, recovery=False):
        e = Editor(browser, project or sv.Project(path=None), tmp_path, recovery)
        made.append(e)
        return e
    yield make
    for e in made:
        e.close()


def boxes_project(folder):
    p = sv.Project(path=folder / "film.sciview.json", duration=6)
    for i, x in enumerate((300, 700, 1300)):
        p.add("rect", name=f"Box {i}", position=(x, 750), size=(120, 80), enter="none")
    ax = p.add("axes", name="Plot", position=(200, 150), size=(600, 400), enter="none")
    c = p.add("curve", name="Wave", axes=ax.id, expression="0.5 + 0.4*sin(x)", enter="none")
    c.key("width", 1.0, 2).key("width", 3.0, 8)
    p.group([ax, c], name="Chart")
    p.save()
    return p


# ------------------------------------------------------------------ basic flow
def test_editor_flow(open_editor):
    ed = open_editor()
    page, srv = ed.page, ed.srv
    page.get_by_text("Animated equations").click()
    page.wait_for_selector(".tl-label >> text=Sum")
    # select and keyframe a value
    ed.row("Sum").click()
    ed.seek(6)
    row = page.locator(".row", has=page.locator(".lbl", has_text="Width")).first
    row.locator(".kf").click()
    ed.settle(300)
    assert "animated" in row.get_attribute("class")
    # add an object from the library, then undo it
    n = len(srv.session.project.objects)
    page.locator(".lib-item", has_text="Sphere").click()
    ed.settle()
    assert len(srv.session.project.objects) == n + 1
    page.keyboard.press("Control+z")
    ed.settle()
    assert len(srv.session.project.objects) == n
    # play for a moment
    page.keyboard.press("Space")
    page.wait_for_timeout(800)
    page.keyboard.press("Space")
    assert float(page.input_value("#timeInput")) > 6
    # save
    page.keyboard.press("Control+s")
    page.locator(".modal input[type=text]").fill("gui_test")
    page.get_by_role("button", name="Save", exact=True).last.click()
    ed.settle()
    assert (ed.folder / "gui_test.sciview.json").exists()


# ------------------------------------------------------------------ groups in the preview
def test_click_selects_the_group_drag_moves_it_double_click_goes_inside(open_editor, tmp_path):
    ed = open_editor(boxes_project(tmp_path))
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Chart")
    ed.seek(2)
    gid = next(o.id for o in ed.project.objects if o.TYPE == "group")
    x, y = ed.box_center("axes1")
    page.mouse.click(x, y)
    ed.settle(200)
    assert ed.state()["sel"] == [gid]
    ed.drag(x, y, 100 * page.locator("#overlay").bounding_box()["width"] / 1920, 0)
    assert ed.project.find(gid).props["offset"] == pytest.approx([100, 0], abs=1)
    assert ed.project.find("axes1").props["position"] == [200, 150]        # members keep their values
    page.mouse.dblclick(x + 50, y)
    ed.settle(200)
    assert ed.state()["sel"] in (["axes1"], ["curve1"])
    page.keyboard.press("Escape")
    assert ed.state()["sel"] == [gid]
    page.keyboard.press("Escape")
    assert ed.state()["sel"] == []
    # the timeline shows the group with its members indented under it, and can fold it
    names = page.locator(".tl-row .nm").all_text_contents()
    assert names.index("Chart") < names.index("Wave") < names.index("Plot")
    page.locator(".tl-row.is-group .twist").click()
    assert "Wave" not in page.locator(".tl-row .nm").all_text_contents()


def test_multi_select_group_align_distribute_stagger(open_editor, tmp_path):
    ed = open_editor(boxes_project(tmp_path))
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Box 0")
    ed.seek(2)
    ed.row("Box 0").click()
    ed.row("Box 1").click(modifiers=["Shift"])
    ed.row("Box 2").click(modifiers=["Shift"])
    assert sorted(ed.state()["sel"]) == ["rect1", "rect2", "rect3"]
    insp = page.locator("#inspector")
    assert "3 objects selected" in insp.text_content()
    # edit all three at once
    size = insp.locator(".row", has=page.locator(".lbl", has_text="Size")).first
    size.locator("input").first.fill("200")
    ed.settle()
    assert [o.props["size"][0] for o in ed.project.objects if o.TYPE == "rect"] == [200, 200, 200]
    # spread across: equal gaps
    insp.get_by_role("button", name="Spread across").click()
    ed.wait_frame()
    xs = sorted(o.props["position"][0] for o in ed.project.objects if o.TYPE == "rect")
    assert xs[1] - xs[0] == pytest.approx(xs[2] - xs[1], abs=1)
    insp.get_by_role("button", name="Top").click()
    ed.settle()
    assert len({o.props["position"][1] for o in ed.project.objects if o.TYPE == "rect"}) == 1
    insp.locator("input[aria-label='Delay between objects (s)']").fill("0.5")
    insp.get_by_role("button", name="Stagger").click()
    ed.settle()
    assert [o.start for o in ed.project.objects if o.TYPE == "rect"] == [0, 0.5, 1.0]
    # group with Ctrl+G, ungroup with Ctrl+Shift+G, undo
    page.keyboard.press("Control+g")
    ed.settle()
    g = [o for o in ed.project.objects if o.TYPE == "group" and o.name != "Chart"]
    assert len(g) == 1 and all(ed.project.find(f"rect{i}").parent == g[0].id for i in (1, 2, 3))
    assert ed.state()["sel"] == [g[0].id]
    page.keyboard.press("Control+Shift+g")
    ed.settle()
    assert all(ed.project.find(f"rect{i}").parent is None for i in (1, 2, 3))
    assert sorted(ed.state()["sel"]) == ["rect1", "rect2", "rect3"]
    # box selection with Ctrl-drag on empty space
    page.keyboard.press("Escape")
    x0, y0 = ed.design_to_page(1700, 1000)
    x1, y1 = ed.design_to_page(100, 600)
    ed.drag(x0, y0, x1 - x0, y1 - y0, modifiers=["Control"])
    assert {"rect1", "rect2", "rect3"} <= set(ed.state()["sel"])


def test_copy_paste_objects_groups_and_keyframes(open_editor, tmp_path):
    ed = open_editor(boxes_project(tmp_path))
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Chart")
    ed.seek(1)
    ed.row("Chart").click()
    page.keyboard.press("Control+c")
    ed.seek(2)
    page.keyboard.press("Control+v")
    ed.settle()
    objs = {o.name: o for o in ed.project.objects}
    assert {"Chart copy", "Plot copy", "Wave copy"} <= set(objs)
    gc, wc, pc = objs["Chart copy"], objs["Wave copy"], objs["Plot copy"]
    assert wc.parent == gc.id and pc.parent == gc.id
    assert wc.props["axes"] == pc.id                         # the copy draws in the copied chart
    assert wc.keys["width"][0]["t"] == pytest.approx(2.0)     # timing kept relative to the playhead
    assert ed.state()["sel"] == [gc.id]
    # cut and paste an object
    n = len(ed.project.objects)
    ed.row("Box 0").click()
    page.keyboard.press("Control+x")
    ed.settle()
    assert len(ed.project.objects) == n - 1
    page.keyboard.press("Control+v")
    ed.settle()
    assert len(ed.project.objects) == n and any(o.name == "Box 0" for o in ed.project.objects)
    # copy a keyframe from the timeline and paste it on another object at the playhead
    wave = ed.page.locator(".tl-row", has=page.locator(".nm", has_text="Wave")).last
    wave.locator(".diamond-k").last.click()
    page.keyboard.press("Control+c")
    ed.row("Wave copy").click()
    ed.seek(4)
    page.keyboard.press("Control+v")
    ed.settle()
    keys = ed.project.find(wc.id).keys["width"]
    assert keys[-1]["t"] == pytest.approx(4.0) and keys[-1]["v"] == 8
    # Delete removes a group with its members; undo brings them back
    n = len(ed.project.objects)
    ed.row("Chart copy").click()
    page.keyboard.press("Delete")
    ed.settle()
    assert len(ed.project.objects) == n - 3
    page.keyboard.press("Control+z")
    ed.settle()
    assert len(ed.project.objects) == n


# ------------------------------------------------------------------ 3D
def test_drag_3d_objects_in_the_camera_plane(open_editor, tmp_path):
    p = sv.Project(path=tmp_path / "s.sciview.json", duration=4)
    p.camera.props.update(target=[0, 0, 0], distance=220, azimuth=-60, elevation=25)
    p.add("grid3d", enter="none")
    p.add("cylinder", name="Sample", radius=10, height=30, enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Sample")
    ed.seek(1)
    x, y = ed.box_center("cylinder1")
    k = page.locator("#overlay").bounding_box()["width"] / 1920
    ed.drag(x, y, 60 * k, 40 * k)
    ed.wait_frame()
    x2, y2 = ed.box_center("cylinder1")
    assert (x2 - x) / k == pytest.approx(60, abs=2) and (y2 - y) / k == pytest.approx(40, abs=2)
    c1 = np.array(ed.project.find("cylinder1").props["center"])
    # Shift: along one axis only
    ed.drag(x2, y2, 80 * k, 5 * k, modifiers=["Shift"])
    d = np.array(ed.project.find("cylinder1").props["center"]) - c1
    assert np.count_nonzero(np.abs(d) > 1e-6) == 1
    assert ed.state()["sel"] == ["cylinder1"]                # Shift-drag does not toggle the selection
    # Alt-drag orbits the camera even over the object
    az = ed.project.camera.value_at("azimuth", 1.0)
    c2 = list(ed.project.find("cylinder1").props["center"])
    x3, y3 = ed.box_center("cylinder1")
    ed.drag(x3, y3, -60, 0, modifiers=["Alt"])
    assert ed.project.camera.value_at("azimuth", 1.0) != az
    assert ed.project.find("cylinder1").props["center"] == c2


# ------------------------------------------------------------------ keyframe curves
def test_bezier_editor_and_js_python_agree(open_editor, tmp_path):
    from sciview.engine.easing import cubic_bezier
    p = sv.Project(path=tmp_path / "b.sciview.json", duration=4)
    t = p.add("text", name="Mover", text="hi", position=(200, 300), enter="none")
    t.key("position", 1.0, (200, 300)).key("position", 3.0, (900, 300))
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Mover")
    cases = [(0.25, 0.1, 0.25, 1), (0.42, 0, 0.58, 1), (0.3, 1.6, 0.7, 1.4), (0, 0, 1, 1), (1, 0, 0, 1), (-1, 0.5, 2, 0.5)]
    us = [0, 0.01, 0.1, 0.33, 0.5, 0.77, 0.99, 1]
    js = page.evaluate("([cases, us]) => import('/gui/js/state.js').then(m => cases.map(c => us.map(u => m.cubicBezier(...c, u))))",
                       [cases, us])
    for c, row in zip(cases, js):
        for u, v in zip(us, row):
            assert v == pytest.approx(cubic_bezier(*c, u), abs=2e-5), (c, u)
    # the editor: pick "custom", drag a handle, pick a preset
    ed.row("Mover").click()
    page.locator(".kfrow select").nth(1).select_option("bezier")
    ed.settle(300)
    k = ed.project.find("text1").keys["position"][1]
    assert k["ease"] == "bezier" and k["bez"] == [0.25, 0.1, 0.25, 1]
    cv = page.locator(".curve-canvas").bounding_box()
    W, PAD, Y0, Y1 = 220, 30, -0.5, 1.5
    hx = cv["x"] + PAD + 0.25 * (W - 2 * PAD)
    hy = cv["y"] + PAD + (Y1 - 0.1) / (Y1 - Y0) * (W - 2 * PAD)
    ed.drag(hx, hy, 0, -40)
    k = ed.project.find("text1").keys["position"][1]
    assert k["bez"][0] == pytest.approx(0.25, abs=0.01) and k["bez"][1] == pytest.approx(0.6, abs=0.02)
    page.locator(".curve-presets .chip", has_text="ease in").first.click()
    ed.settle()
    assert ed.project.find("text1").keys["position"][1]["bez"] == [0.42, 0, 1, 1]
    # the renderer uses the same curve
    mid = ed.project.find("text1").value_at("position", 2.0)[0]
    assert mid == pytest.approx(200 + 700 * cubic_bezier(0.42, 0, 1, 1, 0.5), abs=0.01)


# ------------------------------------------------------------------ problems, recovery
def test_warnings_show_on_the_row_and_the_field(open_editor, tmp_path):
    p = sv.Project(path=tmp_path / "w.sciview.json", duration=4)
    ax = p.add("axes", name="Plot", enter="none")
    p.add("curve", name="Bad curve", axes=ax.id, expression="sin(x) +* 2", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Bad curve")
    page.wait_for_selector(".tl-row .warn-badge")
    badge_rows = page.locator(".tl-row", has=page.locator(".warn-badge")).locator(".nm").all_text_contents()
    assert badge_rows == ["Bad curve"]
    ed.row("Bad curve").click()
    page.wait_for_selector(".insp-issues .issue")
    assert page.locator(".row.has-issue .lbl").all_text_contents() == ["Expression"]
    page.locator(".row.has-issue input").fill("sin(x) * 0.4 + 0.5")
    for _ in range(40):
        if page.locator(".tl-row .warn-badge").count() == 0 and page.locator(".insp-issues .issue").count() == 0:
            break
        ed.settle(100)
    assert page.locator(".row.has-issue").count() == 0
    assert page.locator("#issues").is_hidden()


def test_recovery_dialog_restores_unsaved_changes(open_editor, tmp_path):
    p = boxes_project(tmp_path)
    late = sv.Project.load(p.path)
    late.add("title", name="Unsaved title", text="Not saved")
    time.sleep(0.05)
    (tmp_path / ".film.sciview.json.autosave").write_text(json.dumps(late.to_json()), encoding="utf-8")
    ed = open_editor(sv.Project.load(p.path), recovery=True)
    page = ed.page
    page.wait_for_selector(".modal h2 >> text=Restore unsaved changes?")
    page.get_by_role("button", name="Restore changes").click()
    page.wait_for_selector(".tl-label >> text=Unsaved title")
    assert ed.state()["saved"] is False
    page.keyboard.press("Control+s")
    ed.settle()
    assert not (tmp_path / ".film.sciview.json.autosave").exists()
    assert any(o.name == "Unsaved title" for o in sv.Project.load(p.path).objects)


@pytest.mark.parametrize("template", ["Step-by-step analysis", "Imaging beamline", "3D structure", "Tomography",
                                      "Lenses and mirrors"])
def test_templates_open_without_errors(open_editor, template):
    ed = open_editor()
    ed.page.get_by_text(template).click()
    ed.page.wait_for_selector(".tl-row:nth-child(3)")
    ed.seek(5)
    assert ed.state()["boxes"]
    ed.page.locator(".tl-row:nth-child(3) .tl-label").click()
    assert ed.page.locator("#inspector .insp-name").count() == 1


def test_broken_groups_still_show_every_object(open_editor, tmp_path):
    p = sv.Project(path=tmp_path / "c.sciview.json", duration=4)
    r = p.add("rect", name="Inside", position=(300, 300), enter="none")
    g1 = p.group([r], name="Outer")
    g2 = p.group([g1], name="Inner")
    g2.parent = g1.id                                   # circular
    p.add("text", name="Lost", text="x", parent="nowhere", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-label >> text=Lost")
    names = page.locator(".tl-row .nm").all_text_contents()
    assert {"Inside", "Outer", "Inner", "Lost"} <= set(names)
    assert page.locator(".tl-row .warn-badge").count() >= 3
    ed.row("Lost").click()
    assert page.locator("#inspector .cell.has-issue").count() == 1      # "In group" is marked


# ------------------------------------------------------------------ 0.3: science objects, data, agents
NEW_TYPES = ["Volume (3D image)", "Molecule", "3D scale bar", "Heatmap", "Colour bar", "Error bars", "Uncertainty band",
             "Fitted curve", "Spectrum", "2D histogram", "Vector field", "Streamlines", "Matplotlib figure", "Sinogram",
             "Back-projection", "Scale bar", "Points into a chart", "Lens", "Mirror", "Light rays", "Wavefronts"]


def test_new_object_types_add_from_the_library(open_editor, tmp_path):
    p = sv.Project(path=tmp_path / "n.sciview.json", duration=4)
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".lib-item")
    assert {"Imaging", "Optics"} <= set(page.locator(".lib-group h3, .lib-cat, .lib-head").all_text_contents())
    import re
    for label in NEW_TYPES:
        page.locator(".lib-item", has_text=re.compile(f"^\\s*{re.escape(label)}\\s*$")).first.click()
        ed.settle(150)
        assert page.locator("#inspector .row").count() > 5, label
    ed.settle(800)
    assert sorted(o.LABEL for o in ed.project.objects) == sorted(NEW_TYPES)
    # a reference to any object lists them with their kind; the scale bar can point at the sinogram
    page.locator(".tl-label", has=page.locator(".nm", has_text=re.compile("^Scale bar$"))).first.click()
    sel = page.locator("#inspector select[aria-label='Reference']")
    options = sel.locator("option").all_text_contents()
    assert any("(Sinogram)" in o for o in options) and not any(o.startswith("Scale bar") for o in options)


def test_data_tracks_and_file_sequences_in_the_inspector(open_editor, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "log.csv").write_text("t,T\n0,0\n4,1\n", encoding="utf-8")
    frames = []
    for i in range(3):
        f = tmp_path / f"step_{i + 1}.png"
        from PIL import Image
        Image.fromarray(np.full((8, 8), 80 * i, np.uint8)).save(f)
        frames.append(str(f))
    p = sv.Project(path=tmp_path / "d.sciview.json", duration=4)
    p.add("text", name="Counter", text="{value:.2f}", enter="none")
    p.add("image", name="Scan", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-row")
    ed.row("Counter").click()
    page.locator("#inspector .track-add select").select_option("value")
    page.locator("#inspector .track-add button").click()
    ed.settle(300)
    page.locator("#inspector .track select").first.select_option("assets/log.csv")
    ed.settle(300)
    col = page.locator("#inspector .track input[aria-label^='Value column']")
    col.fill("T")
    col.press("Enter")
    ed.settle(500)
    obj = ed.project.find("text1")
    assert obj.tracks["value"]["data"] == "assets/log.csv" and obj.tracks["value"]["column"] == "T"
    assert page.locator("#inspector .row.tracked").count() == 1
    assert obj.track_value("value", 2.0, ed.srv.session.renderer.assets) == pytest.approx(0.5)
    page.locator("#inspector .track .icon-btn").click()        # remove it again
    ed.settle(400)
    assert not ed.project.find("text1").tracks
    # several files uploaded at once become a sequence
    ed.row("Scan").click()
    with page.expect_file_chooser() as fc:
        page.locator("#inspector .row", has_text="Image").locator(".icon-btn[title^='Upload']").first.click()
    fc.value.set_files(frames)
    ed.settle(1200)
    assert ed.project.find("image1").props["image"] == "assets/step_*.png"
    assert page.locator("#inspector .ctl .pattern").first.is_visible()


def test_agent_changes_appear_live_and_undo_in_one_step(open_editor, tmp_path):
    from sciview.agent.mcp import EditorBackend
    p = sv.Project(path=tmp_path / "a.sciview.json", duration=4)
    p.add("title", name="Title", text="Hello", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-row")
    agent = EditorBackend(ed.url)
    oid = agent.call("add_object", {"type": "caption", "name": "From the assistant", "props": {"text": "Hi"}})["id"]
    page.wait_for_selector(".tl-label >> text=From the assistant", timeout=5000)
    page.wait_for_selector(".toast >> text=Ctrl+Z", timeout=5000)
    agent.call("set_property", {"id": oid, "name": "size", "value": 44})
    ed.settle(1800)                                            # the editor checks for changes every 1.2 s
    page.keyboard.press("Control+z")                           # the size change
    ed.settle(600)
    assert ed.project.find(oid).props["size"] != 44
    page.keyboard.press("Control+z")                           # the new caption
    ed.settle(600)
    assert ed.project.find(oid) is None
    assert page.locator(".tl-label >> text=From the assistant").count() == 0
    # the person's own edits keep working afterwards and the agent sees them
    page.keyboard.press("Control+Shift+z")
    ed.settle(600)
    assert ed.project.find(oid) is not None
    agent.call("set_timing", {"id": oid, "start": 1.0})
    ed.settle(1800)
    assert ed.project.find(oid).start == 1.0


# ------------------------------------------------------------------ 0.4: scenes, sound, presets, themes, assistant
SCENE = "() => import('/gui/js/state.js').then(m => ({id: m.currentScene().id, time: m.S.time, " \
        "film: m.filmTime(), n: m.S.project.scenes.length}))"


def scenes_project(folder):
    p = sv.Project(path=folder / "talk.sciview.json", duration=3)
    p.add("title", name="Opening title", text="Question", enter="none")
    s2 = p.add_scene("Answer", 2, transition="crossfade", transition_duration=0.5)
    s2.add("caption", name="Answer caption", text="Because of hydrogen", enter="none")
    p.save()
    return p


def test_scenes_strip_switching_inspector_and_undo(open_editor, tmp_path):
    ed = open_editor(scenes_project(tmp_path))
    page = ed.page
    page.wait_for_selector(".scene-chip")
    assert page.locator(".scene-chip").count() == 2
    assert page.locator(".tl-label", has_text="Opening title").count() == 1
    assert page.locator(".tl-label", has_text="Answer caption").count() == 0   # rows show the current scene only
    page.locator(".scene-chip", has_text="Answer").click()
    ed.wait_frame()
    st = page.evaluate(SCENE)
    assert st["id"] == "scene2" and st["film"] == pytest.approx(2.5 + st["time"])
    assert page.locator(".tl-label", has_text="Answer caption").count() == 1
    assert page.locator(".insp-title", has_text="Answer").count() == 1        # the scene's own inspector
    dur = page.locator("input[aria-label='Scene length in seconds']")
    dur.fill("4")
    dur.press("Enter")
    page.select_option("select[aria-label='Transition into this scene']", "wipe_left")
    ed.settle(900)
    sc = ed.project.scenes[1]
    assert sc.duration == 4 and sc.transition == "wipe_left" and ed.project.duration == pytest.approx(6.5)
    page.locator(".scene-add").click()
    ed.settle(900)
    assert page.locator(".scene-chip").count() == 3 and len(ed.project.scenes) == 3
    assert page.evaluate(SCENE)["id"] == ed.project.scenes[2].id                 # the new scene is current
    page.keyboard.press("Control+z")
    ed.settle(900)
    assert page.locator(".scene-chip").count() == 2 and len(ed.project.scenes) == 2
    # playing crosses from one scene into the next
    page.locator(".scene-chip", has_text="Scene 1").click()
    ed.seek(2.2)
    page.click("#btnPlay")
    page.wait_for_function("() => import('/gui/js/state.js').then(m => m.currentScene().id === 'scene2')",
                           timeout=8000)
    page.click("#btnPlay")


def test_export_presets_crop_and_guides(open_editor, tmp_path, has_ffmpeg):
    from _media import media_info, video
    p = scenes_project(tmp_path)
    for sc in p.scenes:
        sc.duration = 1
    p.scenes[1].transition_duration = 0.2
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".scene-chip")
    page.click("#btnExport")
    page.locator(".preset", has_text="Vertical").click()
    assert page.evaluate("() => import('/gui/js/state.js').then(m => m.S.guides)") == "vertical"
    assert page.input_value("#guides") == "vertical"
    size = page.locator("select[aria-label='Size']")
    assert "1080 × 1920" in size.locator("option:checked").inner_text()
    size.select_option("0.25")
    page.locator(".modal .btn.primary", has_text="Export").click()
    page.wait_for_selector(".export-status >> text=Exported", timeout=60000)
    out = tmp_path / "talk_vertical.mp4"
    info = media_info(out)
    assert video(info)["size"] == (270, 480) and len(info["chapters"]) == 2
    page.locator(".preset", has_text="Vertical").click()                         # off again: film sizes
    assert "1920 × 1080" in size.locator("option:checked").inner_text()
    page.keyboard.press("Escape")
    ed.settle(300)
    shot = ed.page.locator("#overlay").screenshot()
    assert shot                                                                   # the guide is drawn over the frame


def test_recording_narration_then_captions_from_the_script(open_editor, tmp_path, has_ffmpeg):
    p = sv.Project(path=tmp_path / "rec.sciview.json", duration=6)
    p.add("title", text="Narrated", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".tl-row")
    page.click("#btnRecord")
    page.wait_for_selector("#btnRecord.on", timeout=5000)
    page.wait_for_timeout(2200)
    page.click("#btnRecord")
    page.wait_for_selector(".toast >> text=Recorded", timeout=15000)
    ed.settle(900)
    voice = next(o for o in ed.project.objects if o.TYPE == "voice")
    assert voice.props["audio"].startswith("assets/narration-") and (tmp_path / voice.props["audio"]).exists()
    assert 1.5 < voice.end - voice.start < 4
    page.wait_for_selector("canvas.wave", timeout=10000)                           # the waveform on its row
    page.locator(".insp-actions .btn", has_text="Captions from the script").click()
    page.fill(".modal textarea.script", "First we look.\nThen we measure.")
    page.locator(".modal .btn.primary", has_text="Add captions").click()
    page.wait_for_selector(".modal", state="detached", timeout=5000)
    ed.settle(1200)
    caps = [o for o in ed.project.objects if o.TYPE == "caption"]
    assert [c.props["text"] for c in caps] == ["First we look.", "Then we measure."]
    assert caps[0].start >= voice.start - 1e-6 and caps[1].start > caps[0].start
    assert ed.project.find(voice.id).props["script"] == "First we look.\nThen we measure."
    page.locator("#overlay").click(position={"x": 5, "y": 5})
    page.keyboard.press("Control+z")                                              # one step for the script
    ed.settle(900)
    assert not any(o.TYPE == "caption" for o in ed.project.objects)
    assert not ed.project.find(voice.id).props.get("script")


def test_theme_picker_restyles_and_undoes(open_editor, tmp_path):
    p = sv.Project(path=tmp_path / "th.sciview.json", duration=3)
    p.add("caption", text="Words", enter="none")
    p.save()
    ed = open_editor(p)
    page = ed.page
    page.wait_for_selector(".theme-btn")
    page.locator(".theme-btn", has_text="High contrast").click()
    page.wait_for_selector(".theme-btn.current >> text=High contrast", timeout=5000)
    ed.settle(900)
    assert ed.project.settings["theme"] == "High contrast" and ed.project.objects[0].props["style"] == "box"
    page.keyboard.press("Control+z")
    ed.settle(900)
    assert ed.project.settings["theme"] != "High contrast"
    assert ed.project.objects[0].props.get("style", "plain") == "plain"


def test_assistant_panel_runs_a_request_as_one_undo_step(open_editor, tmp_path, monkeypatch):
    from test_assistant import Script

    from sciview.agent import assistant as A
    monkeypatch.setenv("SCIVIEW_CONFIG_DIR", str(tmp_path / "cfg"))
    A.save_config({"model": "scripted"})
    p = scenes_project(tmp_path)
    ed = open_editor(p)
    ed.srv.session.assistant_client = Script([
        [("add_object", {"type": "caption", "name": "Model caption", "props": {"text": "Neutrons see water"}})],
        [("set_property", {"id": "caption2", "name": "size", "value": 40})],
    ], final="Added a caption to this scene.")
    page = ed.page
    page.wait_for_selector(".scene-chip")
    page.locator(".scene-chip", has_text="Answer").click()
    ed.settle(400)
    page.click("#btnAssistant")
    page.wait_for_selector("#assistant:not([hidden]) .as-input textarea")
    assert page.locator(".as-scope select option", has_text="Only Answer").count() == 1
    page.fill(".as-input textarea", "Add a caption that says neutrons see water")
    page.keyboard.press("Enter")
    page.wait_for_selector(".as-msg.assistant >> text=Added a caption", timeout=15000)
    page.wait_for_selector(".as-changes >> text=Model caption", timeout=5000)
    ed.settle(800)
    new = ed.project.find("caption2")
    assert new is not None and new.scene == "scene2" and new.props["size"] == 40
    assert page.locator(".tl-label", has_text="Model caption").count() == 1
    page.locator("#overlay").click(position={"x": 5, "y": 5})
    page.keyboard.press("Control+z")                                              # the whole request at once
    ed.settle(900)
    assert ed.project.find("caption2") is None
    page.keyboard.press("Control+Shift+z")
    ed.settle(900)
    assert ed.project.find("caption2").props["size"] == 40
