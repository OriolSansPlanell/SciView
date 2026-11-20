import base64
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

import sciview as sv
from sciview.server import make_server


@pytest.fixture
def server(tmp_project):
    tmp_project.add("box", label="hello")
    tmp_project.save()
    srv = make_server(tmp_project, tmp_project.base_dir, port=18765)
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    th.start()
    host, port = srv.server_address[:2]
    yield f"http://127.0.0.1:{port}", srv
    srv.session.stop.set()
    srv.shutdown()
    srv.server_close()


def call(url, method="GET", body=None, headers=None, raw=False):
    hdrs = {"X-SciView": "1"} if method != "GET" else {}
    hdrs.update(headers or {})
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = r.read()
        return payload if raw else json.loads(payload)


def frame(base, t, scale=0.25, play=False):
    """GET /api/frame: JPEG bytes plus the decoded X-Frame-Info header."""
    url = f"{base}/api/frame?t={t:.4f}&scale={scale}" + ("&play=1" if play else "")
    with urllib.request.urlopen(url, timeout=30) as r:
        assert r.headers["Content-Type"] == "image/jpeg"
        meta = json.loads(base64.b64decode(r.headers["X-Frame-Info"]))
        return r.read(), meta


def test_state_and_frame(server):
    base, _ = server
    st = call(base + "/api/state")
    assert st["project"]["objects"][0]["type"] == "box"
    assert {t["type"] for t in st["schema"]["types"]} >= {"box", "curve", "caption", "group"}
    assert st["problems"] == [] and st["recovery"] is None
    jpeg, meta = frame(base, 0.5)
    assert jpeg[:2] == b"\xff\xd8" and meta["boxes"] and meta["boxes"][0]["id"] == "box1"
    assert {"warnings", "issues", "ms", "rev", "t", "cached"} <= set(meta)


def test_frames_are_cached_until_the_project_changes(server):
    base, srv = server
    a, m1 = frame(base, 0.5)
    b, m2 = frame(base, 0.5)
    assert a == b and m1["rev"] == m2["rev"]
    assert len(srv.session.cache) >= 1
    proj = call(base + "/api/state")["project"]
    proj["objects"][0]["props"]["edge_color"] = "red"
    rev = call(base + "/api/project", "PUT", proj)["rev"]
    c, m3 = frame(base, 0.5)
    assert m3["rev"] == rev > m1["rev"] and c != a


def test_problems_point_at_objects_and_fields(server):
    base, _ = server
    proj = call(base + "/api/state")["project"]
    proj["objects"] += [
        {"type": "axes", "id": "ax", "props": {}},
        {"type": "curve", "id": "bad", "props": {"axes": "ax", "expression": "x +* 2"}},
        {"type": "title", "id": "orphan", "parent": "nowhere", "props": {"text": "Hi"}},
    ]
    r = call(base + "/api/project", "PUT", proj)
    assert any(p["id"] == "orphan" and "nowhere" in p["message"] for p in r["problems"])
    _, meta = frame(base, 1.0)
    assert any(i["id"] == "bad" and i["prop"] == "expression" for i in meta["issues"])


def test_prefetch_renders_ahead_of_the_playhead(server):
    base, srv = server
    srv.session.start_background(autosave_interval=0, prefetch=True)
    frame(base, 0.0, play=True)
    fps = srv.session.project.fps
    for _ in range(100):
        if len(srv.session.cache) >= 10:
            break
        time.sleep(0.05)
    idx = {k[1] for k in srv.session.cache}
    assert {1, 2, 3, 4, 5} <= idx and max(idx) <= int(srv.session.project.duration * fps)
    # a change drops the frames rendered for the old project
    call(base + "/api/project", "PUT", call(base + "/api/state")["project"])
    assert all(k[0] == srv.session.rev for k in srv.session.cache)


def test_autosave_and_recovery(server, tmp_project):
    base, srv = server
    s = srv.session
    assert not s.autosave_now()                      # nothing unsaved yet
    proj = call(base + "/api/state")["project"]
    proj["objects"].append({"type": "title", "id": "late", "props": {"text": "Not saved"}})
    call(base + "/api/project", "PUT", proj)
    assert s.autosave_now() and s.autosave_path.exists()
    assert s.autosave_path.name == ".film.sciview.json.autosave"
    assert not s.autosave_now()                      # same revision: no rewrite
    # a new editor on the same file finds the changes
    from sciview.server import EditorSession
    s2 = EditorSession(sv.Project.load(tmp_project.path), tmp_project.base_dir)
    assert s2.recovery and s2.recovery["path"].endswith(".autosave")
    s.set_project(sv.Project.load(tmp_project.path), mark_saved=True)
    s.check_recovery()
    st = call(base + "/api/state")
    assert st["recovery"] is not None
    st = call(base + "/api/recover", "POST", {"action": "restore"})
    assert any(o["id"] == "late" for o in st["project"]["objects"])
    assert st["saved"] is False and st["recovery"] is None and st["path"].endswith("film.sciview.json")
    # saving removes the autosave
    call(base + "/api/save", "POST", {})
    assert not s.autosave_path.exists()
    # discard deletes it
    s.autosave_path.write_text(json.dumps(sv.Project().to_json()), encoding="utf-8")
    s.check_recovery()
    st = call(base + "/api/recover", "POST", {"action": "discard"})
    assert st["recovery"] is None and not s.autosave_path.exists()
    assert any(o["id"] == "late" for o in st["project"]["objects"])


def test_older_autosave_is_ignored(tmp_project):
    import os

    from sciview.server import EditorSession
    tmp_project.save()
    a = tmp_project.path.with_name("." + tmp_project.path.name + ".autosave")
    a.write_text(json.dumps(tmp_project.to_json()), encoding="utf-8")
    old = tmp_project.path.stat().st_mtime - 60
    os.utime(a, (old, old))
    assert EditorSession(tmp_project, tmp_project.base_dir).recovery is None


def test_put_project_updates_preview(server):
    base, srv = server
    st = call(base + "/api/state")
    proj = st["project"]
    proj["objects"].append({"type": "title", "id": "t1", "props": {"text": "Hi"}})
    r = call(base + "/api/project", "PUT", proj)
    assert r["rev"] > st["rev"]
    assert srv.session.project.find("t1") is not None


def test_mutations_need_the_custom_header(server):
    base, _ = server
    req = urllib.request.Request(base + "/api/project", data=b"{}", method="PUT")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403


def test_foreign_host_header_is_rejected(server):
    base, _ = server
    req = urllib.request.Request(base + "/api/state", headers={"Host": "evil.example:80"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403


def test_no_path_traversal(server):
    base, _ = server
    for path in ("/files/../../etc/passwd", "/gui/../../../etc/passwd", "/files/%2e%2e/%2e%2e/etc/passwd"):
        with pytest.raises(urllib.error.HTTPError) as e:
            call(base + path, raw=True)
        assert e.value.code == 404


def test_upload_save_open_and_templates(server, tmp_project):
    base, srv = server
    info = call(base + "/api/assets", "POST", b"a,b\n1,2\n", {"X-Filename": "my%20data.csv"})
    assert info["path"] == "assets/my data.csv" and info["columns"] == ["a", "b"]
    assert (tmp_project.base_dir / "assets" / "my data.csv").exists()
    r = call(base + "/api/save", "POST", {"path": "copy"})
    assert r["name"] == "copy.sciview.json"
    st = call(base + "/api/new", "POST", {"template": "neutron_imaging"})
    assert st["untitled"] and len(st["project"]["objects"]) > 3
    assert (tmp_project.base_dir / "assets" / "radiograph.png").exists()
    st = call(base + "/api/open", "POST", {"path": "copy.sciview.json"})
    assert st["name"] == "copy.sciview.json"
    thumb = call(base + "/api/template-thumb?name=waves", raw=True)
    assert thumb[:2] == b"\xff\xd8"


def test_export_job(server, has_ffmpeg):
    import time
    base, srv = server
    call(base + "/api/export", "POST", {"format": "mp4", "filename": "out.mp4", "scale": 0.2, "workers": 1})
    for _ in range(120):
        st = call(base + "/api/export")
        if st["state"] != "running":
            break
        time.sleep(0.25)
    assert st["state"] == "done", st
    data = call(base + "/api/download?path=out.mp4", raw=True)
    assert len(data) > 1000
