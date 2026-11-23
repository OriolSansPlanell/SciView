"""Notebook support: the HTML preview with a scrubber, stills, the inline editor and the %sciview magic."""
import base64
import json
import urllib.request

import pytest

import sciview as sv
from sciview import jupyter


@pytest.fixture
def film(tmp_path):
    p = sv.Project(path=tmp_path / "nb.sciview.json", duration=2, stars=0)
    p.add("rect", position=(0, 0), size=(1920, 1080), fill_color="#ff0000", fill_opacity=1, enter="none")
    s2 = p.add_scene("Second", 1, transition="crossfade", transition_duration=0.5)
    s2.add("caption", text="Two")
    return p


def test_preview_holds_every_frame_and_the_chapters(film):
    pv = film.preview(fps=4, scale=0.1)
    assert len(pv) == int(round(film.duration * 4)) + 1 and pv.times[0] == 0 and pv.times[-1] == film.duration
    first = base64.b64decode(pv.frames[0])
    assert first[:2] == b"\xff\xd8"
    html = pv._repr_html_()
    assert html.count("<script>") == 1 and 'aria-label="Time"' in html and '"Second"' in html
    assert pv._repr_html_().split('id="')[1] != html.split('id="')[1]          # each view has its own ids
    one = sv.preview(film, fps=2, scale=0.1, scene="Second")
    assert one.times[-1] == pytest.approx(1.0) and one.chapters == []
    part = jupyter.preview(film, fps=1000, scale=0.05, start=0.5, end=1.0)
    assert len(part) == 501 and part.times[0] == 0.5
    capped = jupyter.preview(sv.Project(duration=100), fps=30, scale=0.05)
    assert len(capped) == jupyter.MAX_FRAMES


def test_still_is_a_png(film):
    png = jupyter.Still(film, 1.0, 0.1)._repr_png_()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_inline_editor(film):
    ed = jupyter.edit(film)
    try:
        assert f"localhost:{ed.port}" in ed._repr_html_() and "<iframe" in ed._repr_html_()
        req = urllib.request.Request(ed.url + "api/state", headers={"Host": f"localhost:{ed.port}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            st = json.loads(r.read())
        assert len(st["project"]["scenes"]) == 2
        assert ed.film is ed.srv.session.project
    finally:
        ed.stop()


class FakeIPython:
    def __init__(self, ns):
        self.user_ns = ns
        self.magics = {}

    def register_magic_function(self, func, magic_kind, magic_name):
        self.magics[(magic_kind, magic_name)] = func


def test_the_sciview_magic(film, tmp_path):
    ip = FakeIPython({"film": film, "n": 3})
    sv.load_ipython_extension(ip)
    magic = ip.magics[("line", "sciview")]
    assert isinstance(magic("preview film --fps 2 --scale 0.1"), jupyter.Preview)
    assert isinstance(magic("still film 1.5 --scale 0.1"), jupyter.Still)
    film.save()
    assert isinstance(magic(f"still {film.path} --scale 0.1"), jupyter.Still)
    ed = magic("edit film")
    try:
        assert ip.user_ns["_sciview_editor"] is ed
    finally:
        ed.stop()
    with pytest.raises(NameError):
        magic("preview nothing")
    with pytest.raises(TypeError):
        magic("preview n")
    with pytest.raises(ValueError, match="usage"):
        magic("dance film")
