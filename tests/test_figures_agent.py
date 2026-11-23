"""Matplotlib figures from scripts, the agent tool layer, the MCP server and live editor changes."""
import base64
import io
import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import sciview as sv
from sciview import figures
from sciview.agent import TOOLS, FilmTools, ToolError
from sciview.agent.mcp import EditorBackend, FileBackend, Server, serve_stdio
from sciview.render import FrameInfo

pytest.importorskip("matplotlib")


def draw(p, t=1.0, scale=0.5):
    info = FrameInfo()
    img = p.renderer().frame(t, scale, info)
    return img, info


def wave(fig, t):
    ax = fig.subplots()
    x = np.linspace(0, 10, 100)
    ax.plot(x, np.sin(x - 3 * t), lw=4)


# ---------------------------------------------------------------------------------------------- figures
def test_figure_is_redrawn_per_frame_and_saved_as_a_snapshot(tmp_project):
    p = tmp_project
    p.set("stars", 0)
    fig = p.add_figure(wave, position=(960, 540), size=(800, 500), enter="none")
    assert fig.props["callback"].endswith(f":{fig.id}") and fig.depends_on_time()
    a, info = draw(p, 0.5)
    b, _ = draw(p, 1.5)
    assert info.issues == []
    assert (a.max(axis=2) > 80).sum() > 500
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.2      # the function sees the time
    p.save()
    snap = p.base_dir / "assets" / "figures" / f"{fig.id}.png"
    assert snap.exists() and Image.open(snap).size == (800, 500)
    saved = json.loads(p.path.read_text())["objects"][0]["props"]
    assert saved["snapshot"] == f"assets/figures/{fig.id}.png" and "def " not in json.dumps(saved)
    # someone without the script (or the editor) sees the snapshot, without warnings
    figures.unregister(fig.props["callback"])
    q = sv.load(p.path)
    img, info = draw(q, 1.0)
    assert info.issues == [] and (img.max(axis=2) > 80).sum() > 500
    assert not q.objects[0].depends_on_time()


def test_figure_without_function_or_snapshot_explains_itself(tmp_project):
    p = tmp_project
    p.add("figure", callback="someone_elses_script.plot:figure1")
    _, info = draw(p)
    assert any(i["prop"] == "callback" and "add_figure" in i["message"] for i in info.issues)


def test_a_failing_figure_function_is_reported_and_does_not_stop_saving(tmp_project, capsys):
    def broken(fig, t):
        raise RuntimeError("no data yet")
    p = tmp_project
    p.add_figure(broken)
    good = p.add_figure(wave)
    _, info = draw(p)
    assert any("no data yet" in i["message"] for i in info.issues)
    p.save()
    assert "no data yet" in capsys.readouterr().err
    assert (p.base_dir / "assets" / "figures" / f"{good.id}.png").exists()


def test_still_figures_are_cached_and_export_uses_one_process(tmp_project, monkeypatch):
    from sciview import export
    p = tmp_project
    calls = []

    def counted(fig, t):
        calls.append(t)
        wave(fig, 0)
    f = p.add_figure(counted, still=True, enter="none")
    assert not f.depends_on_time()
    for t in (0.5, 0.7, 0.9):
        p.renderer().frame(t, 0.25)
    assert len(calls) == 1
    assert export.uses_script_figures(p)
    seen = []
    real = export.iter_frames

    def spy(project, times, scale, workers, cancel=None, opts=None):
        seen.append(workers)
        return real(project, times, scale, workers, cancel, opts)
    monkeypatch.setattr(export, "iter_frames", spy)
    out = export.export(p, p.base_dir / "frames", start=0.5, end=0.6, scale=0.25, workers=4, fps=10)
    assert seen == [1]                                          # figure functions cannot go to other processes
    assert len(list(out.glob("frame_*.png"))) == 1


# ---------------------------------------------------------------------------------------------- tools
@pytest.fixture
def film(tmp_project):
    p = tmp_project
    p.add("title", text="Hello", name="Title")
    p.add("caption", text="Locked words", name="Fixed").locked = True
    return p


def test_tools_list_schemas_and_describe(film):
    tools = FilmTools(film)
    types = {t["type"] for t in tools.call("list_object_types")["types"]}
    assert {"volume", "sinogram", "molecule", "rays", "fit", "morph"} <= types
    sch = tools.call("get_schema", {"type": "volume"})
    assert sch["is3d"] and any(q["name"] == "mode" for q in sch["props"])
    assert "pixels" in tools.call("get_schema", {"type": "caption"})["coordinates"]
    assert tools.call("get_schema", {"type": "camera"})["type"] == "camera"
    d = tools.call("describe_film")
    assert [o["id"] for o in d["objects"]] == ["title1", "caption1"] and d["objects"][1]["locked"]
    for name, spec in TOOLS.items():
        assert spec["input"]["type"] == "object" and spec["description"], name


def test_tools_check_every_value(film):
    tools = FilmTools(film)
    bad = [
        ("add_object", {"type": "spaceship"}, "unknown type"),
        ("add_object", {"type": "caption", "props": {"colour": "red"}}, "no property 'colour'"),
        ("add_object", {"type": "caption", "props": {"start": 2}}, "own argument"),
        ("add_object", {"type": "caption", "props": {"size": "big"}}, "number"),
        ("add_object", {"type": "caption", "props": {"color": "not a colour"}}, "colour"),
        ("add_object", {"type": "volume", "props": {"mode": "hologram"}}, "one of"),
        ("add_object", {"type": "caption", "start": 3, "end": 2}, "after start"),
        ("add_object", {"type": "caption", "enter": "explode"}, "enter must be"),
        ("set_property", {"id": "nope", "name": "text", "value": "x"}, "no object"),
        ("add_keyframe", {"id": "title1", "name": "title_size", "time": 99, "value": 10}, "within its scene"),
        ("add_keyframe", {"id": "title1", "name": "title_size", "time": 1, "value": 10, "ease": "wobbly"}, "ease"),
        ("place", {"id": "title1", "region": "somewhere"}, "region must be"),
        ("add_object", {"type": "caption", "colour": "red"}, "does not take"),
        ("set_property", {"id": "title1"}, "needs 'name'"),
    ]
    for name, args, msg in bad:
        with pytest.raises(ToolError, match=msg):
            tools.call(name, args)
    with pytest.raises(ToolError, match="unknown tool"):
        tools.call("rm_rf", {})
    assert len(film.objects) == 2 and tools.changes == []     # nothing was half-applied


def test_tools_change_the_film(film):
    tools = FilmTools(film)
    oid = tools.call("add_object", {"type": "caption", "props": {"text": "The beam hardens", "size": 30},
                                    "start": 1, "end": 1.8, "enter": "slide_up"})["id"]
    obj = film.find(oid)
    assert obj.props["text"] == "The beam hardens" and obj.end == 1.8 and obj.enter_effect == "slide_up"
    tools.call("add_keyframe", {"id": oid, "name": "opacity", "time": 1.2, "value": 0.5})
    tools.call("set_property", {"id": oid, "name": "opacity", "value": 1.0, "time": 1.6})
    assert len(obj.keys["opacity"]) == 2
    with pytest.raises(ToolError, match="animated"):
        tools.call("set_property", {"id": oid, "name": "opacity", "value": 0.2})
    tools.call("remove_keyframe", {"id": oid, "name": "opacity", "time": 1.2})
    tools.call("place", {"id": "title1", "region": "top-left"})
    assert film.find("title1").props["position"] == pytest.approx([480, 216])
    tools.call("set_timing", {"id": "title1", "start": 0.2, "exit": "fade", "exit_duration": 0.3})
    g = tools.call("group", {"ids": ["title1", oid], "name": "Intro"})["id"]
    assert film.find(oid).parent == g
    out = tools.call("render_frame", {"time": 1.5, "scale": 0.25})
    assert Image.open(io.BytesIO(out["png"])).size == (480, 270) and oid in out["objects_visible"]
    assert tools.call("validate")["problems"] == []
    assert [c["action"] for c in tools.call("review")["changes"]][:2] == ["add", "key"]
    tools.call("delete", {"id": g})
    assert film.find(oid) is None and film.find("title1") is None


def test_locked_objects_and_scope_are_respected(film):
    tools = FilmTools(film)
    for name, args in (("set_property", {"id": "caption1", "name": "text", "value": "changed"}),
                       ("delete", {"id": "caption1"}), ("group", {"ids": ["title1", "caption1"]}),
                       ("place", {"id": "caption1", "region": "center"}),
                       ("set_timing", {"id": "caption1", "start": 1})):
        with pytest.raises(ToolError, match="locked"):
            tools.call(name, args)
    g = film.group([film.find("title1")])
    film.find("caption1").parent = g.id
    with pytest.raises(ToolError, match="locked"):
        tools.call("delete", {"id": g.id})
    assert film.find("caption1").props.get("text", "Locked words") == "Locked words"

    scoped = FilmTools(film, scope={"ids": ["title1"], "time": [0.5, 1.5]})
    with pytest.raises(ToolError, match="outside your scope"):
        scoped.call("set_property", {"id": g.id, "name": "opacity", "value": 0.5})
    with pytest.raises(ToolError, match="time window"):
        scoped.call("add_keyframe", {"id": "title1", "name": "title_size", "time": 1.9, "value": 50})
    with pytest.raises(ToolError, match="time window"):
        scoped.call("add_object", {"type": "caption", "start": 0.1})
    new = scoped.call("add_object", {"type": "caption", "start": 0.6})["id"]
    assert film.find(new).end == 1.5                            # kept inside the window
    scoped.call("set_property", {"id": new, "name": "text", "value": "mine"})   # objects it added are in scope


# ---------------------------------------------------------------------------------------------- MCP
def run_stdio(backend, messages):
    out = io.StringIO()
    serve_stdio(backend, io.StringIO("\n".join(m if isinstance(m, str) else json.dumps(m) for m in messages) + "\n"),
                out)
    return [json.loads(x) for x in out.getvalue().splitlines()]


def test_mcp_protocol_over_stdio(film):
    film.save()
    backend = FileBackend(film.path)
    replies = run_stdio(backend, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "add_object", "arguments": {"type": "caption", "props": {"text": "From the assistant"}}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "add_object", "arguments": {"type": "x"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "render_frame", "arguments": {"time": 1}}},
        {"jsonrpc": "2.0", "id": 6, "method": "ping"},
        {"jsonrpc": "2.0", "id": 7, "method": "resources/list"},
        "{not json",
        {"jsonrpc": "1.0", "id": 8, "method": "ping"},
    ])
    by_id = {r.get("id"): r for r in replies}
    assert len(replies) == 9                                    # the notification gets no reply
    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "sciview"
    assert "tools" in init["capabilities"] and init["instructions"]
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert {"describe_film", "add_object", "render_frame", "validate"} <= names
    assert all("inputSchema" in t for t in by_id[2]["result"]["tools"])
    ok = by_id[3]["result"]
    assert ok["isError"] is False and json.loads(ok["content"][0]["text"])["id"].startswith("caption")
    assert by_id[4]["result"]["isError"] is True and "unknown type" in by_id[4]["result"]["content"][0]["text"]
    img = by_id[5]["result"]["content"][0]
    assert img["type"] == "image" and img["mimeType"] == "image/png"
    assert Image.open(io.BytesIO(base64.b64decode(img["data"]))).size == (960, 540)
    assert by_id[6]["result"] == {}
    assert by_id[7]["error"]["code"] == -32601
    assert by_id[None]["error"]["code"] in (-32700, -32600)
    assert any(r.get("error", {}).get("code") == -32700 for r in replies)
    saved = sv.load(film.path)                                  # saved after the change
    assert any(o.props.get("text") == "From the assistant" for o in saved.objects)


def test_unknown_protocol_versions_get_the_latest():
    s = Server(FileBackend.__new__(FileBackend))
    r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert r["result"]["protocolVersion"] == "2025-11-25"


def test_mcp_command_writes_only_json_to_stdout(film, tmp_path):
    film.save()
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
             "params": {"name": "describe_film", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "set_property", "arguments": {"id": "caption1", "name": "text", "value": "x"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "get_schema", "arguments": {"type": "caption"}}}]
    env = {**__import__("os").environ, "PYTHONPATH": str(Path(sv.__file__).parents[1])}
    r = subprocess.run([sys.executable, "-m", "sciview", "mcp", str(film.path)], input="\n".join(map(json.dumps, msgs)),
                       capture_output=True, text=True, encoding="utf-8", timeout=120, env=env)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert len(lines) == 4 and all(json.loads(x)["jsonrpc"] == "2.0" for x in lines)
    assert "ready" in r.stderr
    assert "\r" not in r.stdout
    assert "1920×1080" in json.loads(lines[3])["result"]["structuredContent"]["coordinates"]   # UTF-8 survives
    locked = json.loads(lines[2])["result"]
    assert locked["isError"] and "locked" in locked["content"][0]["text"]


# ---------------------------------------------------------------------------------------------- live editor
@pytest.fixture
def editor(tmp_project):
    from sciview.server import make_server
    tmp_project.add("title", text="Hello")
    tmp_project.save()
    srv = make_server(tmp_project, tmp_project.base_dir, port=0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", srv
    srv.session.stop.set()
    srv.shutdown()
    srv.server_close()


def http(url, method="GET", body=None):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"X-SciView": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_agent_changes_reach_the_open_editor(editor):
    url, srv = editor
    _, before = http(url + "/api/changes")
    backend = EditorBackend(url)
    oid = backend.call("add_object", {"type": "caption", "props": {"text": "Live"}})["id"]
    assert any(o.id == oid for o in srv.session.project.objects)
    _, after = http(url + "/api/changes")
    assert after["external_rev"] > before["external_rev"] and "added a caption" in after["note"]
    out = backend.call("render_frame", {"time": 1.0, "scale": 0.25})
    assert out["jpeg"][:2] == b"\xff\xd8"
    # the person edits at the same moment: a stale agent change is refused, the agent re-reads and retries
    _, st = http(url + "/api/project")
    stale = st["rev"]
    proj = st["project"]
    proj["objects"][0]["props"]["text"] = "Edited by the person"
    code, _ = http(url + f"/api/project?base={stale}", "PUT", proj)
    assert code == 200
    code, err = http(url + "/api/agent", "POST", {"project": proj, "base_rev": stale, "note": "late"})
    assert code == 409 and "changed" in err["error"]
    backend.call("set_property", {"id": oid, "name": "size", "value": 40})
    texts = {o.id: o.props.get("text") for o in srv.session.project.objects}
    assert texts["title1"] == "Edited by the person" and srv.session.project.find(oid).props["size"] == 40


def test_editor_refuses_a_stale_save_after_an_agent_change(editor):
    url, srv = editor
    _, st = http(url + "/api/project")
    EditorBackend(url).call("add_object", {"type": "caption"})
    code, body = http(url + f"/api/project?base={st['rev']}", "PUT", st["project"])
    assert code == 409                                         # the editor pulls the agent's change first
    assert len(srv.session.project.objects) == 2


def test_editor_backend_reports_an_unreachable_editor():
    with pytest.raises(ToolError, match="cannot reach"):
        EditorBackend("http://127.0.0.1:9").call("describe_film", {})


def test_scene_scope_by_name_in_files_and_the_editor(editor, tmp_path):
    url, srv = editor
    film = srv.session.project
    method = film.add_scene("Method", 5)
    method.add("caption", text="In the method")
    film.save()
    backend = EditorBackend(url, {"scene": "Method"})
    oid = backend.call("add_object", {"type": "caption", "props": {"text": "Scoped"}})["id"]
    assert srv.session.project.find(oid).scene == method.id
    with pytest.raises(ToolError, match="another scene"):
        backend.call("set_property", {"id": "title1", "name": "size", "value": 50})
    tools = FilmTools(sv.load(film.path), {"scene": "Method"})
    assert tools.scope["scene"] == method.id
    with pytest.raises(ToolError, match="does not exist"):
        FilmTools(sv.load(film.path), {"scene": "Nope"})
