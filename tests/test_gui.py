"""End-to-end editor test in a headless browser. Run with: pytest -m gui (needs `pip install playwright`
and `playwright install chromium`)."""
import threading

import pytest

import sciview as sv
from sciview.server import make_server

pytestmark = pytest.mark.gui
playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def editor(tmp_path):
    p = sv.Project(path=None)
    srv = make_server(p, tmp_path, port=18900)
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    th.start()
    yield f"http://localhost:{srv.server_address[1]}/", srv, tmp_path
    srv.shutdown()
    srv.server_close()


def test_editor_flow(editor):
    url, srv, folder = editor
    with playwright.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # browsers not installed
            pytest.skip(f"chromium not available: {exc}")
        page = browser.new_page(viewport={"width": 1500, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("dialog", lambda d: d.accept())
        page.goto(url)
        page.get_by_text("Animated equations").click()
        page.wait_for_selector(".tl-label >> text=Sum")
        # select and keyframe a value
        page.locator(".tl-label", has_text="Sum").click()
        page.fill("#timeInput", "6")
        page.press("#timeInput", "Enter")
        row = page.locator(".row", has=page.locator(".lbl", has_text="Width")).first
        row.locator(".kf").click()
        page.wait_for_timeout(300)
        assert "animated" in row.get_attribute("class")
        # add an object from the library, then undo it
        n = len(srv.session.project.objects)
        page.locator(".lib-item", has_text="Sphere").click()
        page.wait_for_timeout(600)
        assert len(srv.session.project.objects) == n + 1
        page.keyboard.press("Control+z")
        page.wait_for_timeout(600)
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
        page.wait_for_timeout(600)
        assert (folder / "gui_test.sciview.json").exists()
        browser.close()
    assert not errors, errors
