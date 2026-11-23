"""The assistant panel's engine: the agent loop, review flags, settings, the HTTP client and the benchmark."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import sciview as sv
from sciview.agent import assistant as A
from sciview.agent import bench


class Script:
    """A stand-in for a model: answers each request with the next list of tool calls, then a sentence."""

    def __init__(self, steps, final="Done."):
        self.steps = list(steps)
        self.final = final
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append(json.loads(json.dumps(messages, default=str)))
        if not self.steps:
            return {"role": "assistant", "content": self.final}
        calls = self.steps.pop(0)
        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
            for i, (n, a) in enumerate(calls)]}


def run(project, steps, prompt="do it", scope=None, cfg=None, **kw):
    r = A.Run(project, prompt, scope=scope, cfg={**A.DEFAULTS, "model": "test", **(cfg or {})},
              client=Script(steps, **kw))
    r._run()
    return r


# ---------------------------------------------------------------------------------------------- the loop
def test_a_request_changes_the_film_and_reports_back():
    p = sv.Project(duration=6)
    applied = []
    r = A.Run(p, "Add a caption: Neutrons see hydrogen", cfg={**A.DEFAULTS, "model": "m"},
              client=Script([[("add_object", {"type": "caption", "props": {"text": "Neutrons see hydrogen"},
                                              "start": 1, "end": 3})],
                             [("render_frame", {"time": 2})]], final="Added the caption."),
              apply=lambda proj, note: applied.append(note))
    r._run()
    assert r.status == "done" and r.answer == "Added the caption."
    assert [o.props["text"] for o in p.objects] == ["Neutrons see hydrogen"]
    assert applied == ["Assistant added a caption"]
    done = [e for e in r.events if e["kind"] == "done"][0]
    assert done["changes"][0]["what"] == ["added"] and done["flags"] == []     # the text came from the person
    kinds = [e["kind"] for e in r.events]
    assert kinds.count("tool") == 2 and "answer" in kinds
    # the frame was shown to the model as an image after the tool result
    last = r.client.seen[-1]
    assert last[-1]["role"] == "user" and last[-1]["content"][1]["type"] == "image_url"
    assert last[-2]["role"] == "tool"


def test_the_model_hears_about_its_mistakes_and_problems():
    p = sv.Project(duration=6)
    r = run(p, [[("add_object", {"type": "spaceship"})],
                [("add_object", {"type": "text", "props": {"text": "Far away", "position": [1880, 500], "size": 80}})]])
    tool_msgs = [m for m in r.client.seen[1] if m["role"] == "tool"]
    assert "unknown type" in tool_msgs[0]["content"]
    after = [m for m in r.client.seen[2] if m["role"] == "tool"][-1]["content"]
    assert "automatic_checks" in after and "outside the frame" in after
    assert any(e["kind"] == "check" for e in r.events)


def test_values_the_assistant_chose_are_flagged():
    p = sv.Project(duration=6)
    r = run(p, [[("add_object", {"type": "caption", "props": {"text": "Attenuation is 0.62 per cm"}}),
                 ("add_object", {"type": "curve", "props": {"expression": "exp(-0.4*x)"}}),
                 ("add_object", {"type": "box", "props": {"size": [12, 12, 12], "center": [5, 0, 0]}})]],
            prompt="add a caption about attenuation and a decay curve")
    flags = [e for e in r.events if e["kind"] == "done"][0]["flags"]
    reasons = {(f["prop"], f["reason"]) for f in flags}
    assert ("text", "text written by the assistant") in reasons
    assert ("expression", "expression written by the assistant") in reasons
    assert all(f["prop"] not in ("center", "position") for f in flags)        # layout is not science
    r2 = run(sv.Project(duration=6), [[("add_object", {"type": "box", "props": {"edge_width": 2.5}}),
                                       ("add_object", {"type": "sphere", "props": {"radius": 7.5}})]],
             prompt="a sphere of radius 7.5")
    flags = [e for e in r2.events if e["kind"] == "done"][0]["flags"]
    assert [f["prop"] for f in flags] == []                                   # 7.5 was given; edge width is look


def test_scope_and_locks_hold_during_a_request():
    p = sv.Project(duration=6)
    c = p.add("caption", text="Locked")
    c.locked = True
    s2 = p.add_scene("Two", 4)
    other = s2.add("caption", text="Other scene")
    r = run(p, [[("set_property", {"id": c.id, "name": "text", "value": "changed"}),
                 ("set_property", {"id": other.id, "name": "text", "value": "changed"})]],
            scope={"scene": "scene1"})
    assert c.props["text"] == "Locked" and other.props["text"] == "Other scene"
    msgs = [e["message"] for e in r.events if e["kind"] == "tool" and not e["ok"]]
    assert any("locked" in m for m in msgs) and any("another scene" in m for m in msgs)


def test_stop_and_step_limit():
    p = sv.Project(duration=6)
    steps = [[("validate", {})]] * 30
    r = run(p, steps, cfg={"max_steps": 3})
    assert r.status == "done" and "maximum number of steps" in r.answer
    r = A.Run(p, "x", cfg={**A.DEFAULTS, "model": "m"}, client=Script(steps))
    r.stop.set()
    r._run()
    assert r.status == "stopped"


def test_bad_arguments_and_server_errors_are_reported():
    p = sv.Project(duration=6)

    class Broken(Script):
        def complete(self, messages, tools):
            if len(self.seen) == 0:
                self.seen.append(messages)
                return {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "x", "function": {"name": "add_object", "arguments": "{not json"}}]}
            raise A.AssistantError("the model server answered 500: boom")
    r = A.Run(p, "x", cfg={**A.DEFAULTS, "model": "m"}, client=Broken([]))
    r._run()
    assert r.status == "error" and "500" in r.error
    assert any(e["kind"] == "tool" and "valid JSON" in e["message"] for e in r.events)


# ---------------------------------------------------------------------------------------------- settings
def test_settings_are_kept_per_user(tmp_path, monkeypatch):
    monkeypatch.setenv("SCIVIEW_CONFIG_DIR", str(tmp_path))
    assert A.load_config()["base_url"].startswith("http://localhost:11434")
    A.save_config({"base_url": "http://localhost:1234/v1", "model": "gemma4:31b", "api_key": "secret", "max_steps": 500,
                   "unknown": 1})
    cfg = A.load_config()
    assert cfg["model"] == "gemma4:31b" and cfg["max_steps"] == 100 and "unknown" not in cfg
    pub = A.public_config(cfg)
    assert pub["api_key"] == "••••"
    A.save_config({"api_key": "••••", "model": "other"})           # the masked key does not overwrite the real one
    assert A.load_config()["api_key"] == "secret"


# ---------------------------------------------------------------------------------------------- HTTP client
@pytest.fixture
def fake_server():
    state = {"requests": [], "answers": [], "code": 200}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._send({"data": [{"id": "b-model"}, {"id": "a-model"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append({"body": body, "auth": self.headers.get("Authorization")})
            if state["code"] != 200:
                return self._send({"error": "tools are not supported by this model"}, state["code"])
            msg = state["answers"].pop(0) if state["answers"] else {"role": "assistant", "content": "ok"}
            self._send({"choices": [{"message": msg}]})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    yield state
    srv.shutdown()
    srv.server_close()


def test_openai_compatible_client(fake_server):
    c = A.ChatClient({**A.DEFAULTS, "base_url": fake_server["url"], "model": "m", "api_key": "k"})
    assert c.models() == ["a-model", "b-model"]
    fake_server["answers"].append({"role": "assistant", "content": "", "tool_calls": [
        {"id": "1", "type": "function", "function": {"name": "validate", "arguments": "{}"}}]})
    msg = c.complete([{"role": "user", "content": "hi"}], A.openai_tools())
    assert msg["tool_calls"][0]["function"]["name"] == "validate"
    req = fake_server["requests"][-1]
    assert req["auth"] == "Bearer k" and req["body"]["model"] == "m"
    names = {t["function"]["name"] for t in req["body"]["tools"]}
    assert {"add_object", "add_scene", "align", "check_frames", "render_frame"} <= names
    fake_server["code"] = 400
    with pytest.raises(A.AssistantError, match="may not support tool calls"):
        c.complete([{"role": "user", "content": "hi"}], A.openai_tools())


def test_unreachable_server_says_what_to_start():
    c = A.ChatClient({**A.DEFAULTS, "base_url": "http://127.0.0.1:9/v1", "timeout": 5})
    with pytest.raises(A.AssistantError, match="Is Ollama, LM Studio"):
        c.models()


# ---------------------------------------------------------------------------------------------- benchmark
SOLUTIONS = {
    "caption-basic": [[("add_object", {"type": "caption", "props": {"text": "Neutrons see light elements"}, "start": 1, "end": 4})]],
    "caption-box": [[("add_object", {"type": "caption", "props": {"text": "Hydrogen scatters strongly", "style": "box"},
                                     "start": 5, "end": 8})]],
    "title-card": [[("add_object", {"type": "title", "props": {"text": "Inside a battery", "subtitle": "Neutron tomography"},
                                    "start": 0})]],
    "counter": [[("add_object", {"type": "text", "props": {"text": "{value:.0f}"}})],
                [("add_keyframe", {"id": "text1", "name": "value", "time": 2, "value": 0}),
                 ("add_keyframe", {"id": "text1", "name": "value", "time": 5, "value": 100})]],
    "edit-caption": [[("set_property", {"id": "caption1", "name": "text", "value": "Neutrons pass through lead"})]],
    "typewriter": [[("set_timing", {"id": "caption2", "enter": "typewriter"})]],
    "delete-caption": [[("delete", {"id": "caption2"})]],
    "caption-color": [[("set_property", {"id": "caption1", "name": "color", "value": "gold"})]],
    "timing-window": [[("set_timing", {"id": "title1", "start": 2, "end": 5})]],
    "timing-after": [[("set_timing", {"id": "caption2", "start": 4})]],
    "stagger": [[("set_timing", {"id": f"panel{i + 1}", "start": 1 + 0.5 * i}) for i in range(3)]],
    "fade-out": [[("set_timing", {"id": "title1", "end": 6, "exit": "fade"})]],
    "exit-slide": [[("set_timing", {"id": "caption1", "exit": "slide_down"})]],
    "place-top-left": [[("place", {"id": "title1", "region": "top-left"})]],
    "align-top": [[("align", {"ids": ["panel1", "panel2", "panel3"], "how": "top"})]],
    "spread": [[("align", {"ids": ["panel1", "panel2", "panel3"], "how": "spread_x"})]],
    "caption-bottom": [[("place", {"id": "caption1", "region": "bottom"})]],
    "in-frame": [[("set_property", {"id": "panel3", "name": "position", "value": [1400, 260]})]],
    "right-half": [[("add_object", {"type": "image", "props": {"position": [1440, 540]}})]],
    "orbit": [[("add_keyframe", {"id": "camera", "name": "azimuth", "time": 0, "value": -60}),
               ("add_keyframe", {"id": "camera", "name": "azimuth", "time": 10, "value": 30})]],
    "zoom-in": [[("add_keyframe", {"id": "camera", "name": "distance", "time": 2, "value": 150}),
                 ("add_keyframe", {"id": "camera", "name": "distance", "time": 4, "value": 80})]],
    "look-at": [[("set_property", {"id": "camera", "name": "target", "value": [40, 0, 0]})]],
    "elevation": [[("set_property", {"id": "camera", "name": "elevation", "value": 45})]],
    "still-camera": [[("remove_keyframe", {"id": "camera", "name": "azimuth", "time": 0}),
                      ("remove_keyframe", {"id": "camera", "name": "azimuth", "time": 10})]],
    "box": [[("add_object", {"type": "box", "props": {"center": [0, 0, 0], "size": [20, 20, 20], "edge_color": "gold"}})]],
    "sphere": [[("add_object", {"type": "sphere", "props": {"center": [30, 0, 0], "radius": 10}})]],
    "beam": [[("add_object", {"type": "beam", "props": {}})]],
    "group": [[("group", {"ids": ["box1", "sphere1"]})]],
    "move-3d": [[("set_property", {"id": "sphere1", "name": "center", "value": [0, 40, 10]})]],
    "axes": [[("add_object", {"type": "axes", "props": {"x_range": [0, 10], "y_range": [-1, 1]}})]],
    "wave": [[("add_object", {"type": "curve", "props": {"axes": "axes1", "expression": "sin(x - 2*t)"}})]],
    "scatter": [[("add_object", {"type": "scatter", "props": {"axes": "axes1", "data": "assets/decay.csv",
                                                              "x_column": "time", "y_column": "signal"}})]],
    "fit": [[("add_object", {"type": "fit", "props": {"axes": "axes1", "data": "assets/decay.csv", "x_column": "time",
                                                      "y_column": "signal", "model": "exponential"}})]],
    "range-anim": [[("add_keyframe", {"id": "axes1", "name": "x_range", "time": 3, "value": [0, 10]}),
                    ("add_keyframe", {"id": "axes1", "name": "x_range", "time": 6, "value": [0, 5]})]],
    "add-scene": [[("add_scene", {"name": "Results", "duration": 6, "transition": "crossfade"})]],
    "rename-scene": [[("set_scene", {"scene": "Method", "name": "Measurement"})]],
    "transition": [[("set_scene", {"scene": "scene2", "transition": "wipe_left", "transition_duration": 0.5})]],
    "caption-in-scene": [[("add_object", {"type": "caption", "props": {"text": "The detector records it"}, "start": 4,
                                          "end": 6, "scene": "Method"})]],
    "template-scene": [[("add_scene", {"name": "Title", "duration": 5, "template": "title_card"})]],
    "no-invention": [[("add_object", {"type": "caption", "props": {"text": "Attenuation coefficient: [value from your measurement]"}})]],
    "locked": [[("set_property", {"id": "caption1", "name": "color", "value": "red"}),
                ("set_property", {"id": "caption2", "name": "color", "value": "red"})]],
    "scope-scene": [[("set_property", {"id": "caption1", "name": "color", "value": "gold"}),
                     ("set_property", {"id": "caption3", "name": "color", "value": "gold"})]],
}


def test_benchmark_has_enough_tasks_and_a_solution_for_each():
    assert 30 <= len(bench.TASKS) <= 50
    assert len({t.id for t in bench.TASKS}) == len(bench.TASKS)
    assert set(SOLUTIONS) == {t.id for t in bench.TASKS}


@pytest.mark.parametrize("task", bench.TASKS, ids=lambda t: t.id)
def test_every_benchmark_task_is_solvable_and_checked(task):
    good = bench.run_task(task, {**A.DEFAULTS, "model": "reference", "vision": False}, Script(SOLUTIONS[task.id]))
    assert good["passed"], good
    # doing nothing must not pass (except where doing nothing is the right answer)
    idle = bench.run_task(task, {**A.DEFAULTS, "model": "idle", "vision": False}, Script([]))
    assert not idle["passed"] or task.group == "guard", task.id


def test_benchmark_report_and_command(tmp_path, capsys):
    rep = bench.run_all({**A.DEFAULTS, "model": "m", "vision": False}, only=["camera"], client=Script([]))
    assert rep["total"] == 5 and rep["groups"] == {"camera": "0/5"} and rep["passed"] == 0
    assert bench.main(["--list"]) == 0
    assert "caption-basic" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------- editor server
def test_assistant_requests_through_the_editor_server(tmp_project, monkeypatch, tmp_path):
    monkeypatch.setenv("SCIVIEW_CONFIG_DIR", str(tmp_path / "cfg"))
    from sciview.server import make_server
    tmp_project.add("caption", text="Hello")
    tmp_project.save()
    srv = make_server(tmp_project, tmp_project.base_dir, port=0)
    srv.session.assistant_client = Script([[("add_object", {"type": "caption", "props": {"text": "From the model"}})]],
                                          final="Added it.")
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    import urllib.request

    def req(method, path, body=None):
        r = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                   headers={"X-SciView": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read())
    try:
        cfg = req("POST", "/api/assistant/config", {"model": "gemma4:26b"})["config"]
        assert cfg["model"] == "gemma4:26b"
        assert req("GET", "/api/assistant/config")["presets"][0]["name"] == "Ollama"
        start = req("POST", "/api/assistant", {"prompt": "add a caption", "project": srv.session.project.to_json()})
        for _ in range(100):
            st = req("GET", f"/api/assistant?id={start['id']}&since=0")
            if st["status"] != "running":
                break
            time.sleep(0.05)
        assert st["status"] == "done" and st["changed"]
        assert any(e["kind"] == "answer" and e["text"] == "Added it." for e in st["events"])
        assert [o.props["text"] for o in srv.session.project.objects] == ["Hello", "From the model"]
        assert srv.session.external_note.startswith("Assistant")
    finally:
        srv.session.stop.set()
        srv.shutdown()
        srv.server_close()
