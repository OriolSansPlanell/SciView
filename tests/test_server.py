import json
import threading
import urllib.error
import urllib.request

import pytest

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


def test_state_and_frame(server):
    base, _ = server
    st = call(base + "/api/state")
    assert st["project"]["objects"][0]["type"] == "box"
    assert {t["type"] for t in st["schema"]["types"]} >= {"box", "curve", "caption"}
    fr = call(base + "/api/frame?t=0.5&scale=0.25")
    assert fr["image"].startswith("data:image/jpeg;base64,") and fr["boxes"]


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
