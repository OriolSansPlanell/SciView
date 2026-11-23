"""A benchmark for assistant models: small film-making tasks, each checked automatically.

    python -m sciview.agent.bench --base-url http://localhost:11434/v1 --model gemma4:31b
    python -m sciview.agent.bench --model gemma4:26b --only camera,scenes -o results.json

Each task starts from a small film, sends one request through the same loop as the editor's assistant
panel, and checks the resulting film. The report gives the pass rate per group, the steps and the time,
so models (and prompts) can be compared on the same footing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..engine.text import plain_text
from ..model.project import Project
from .assistant import ChatClient, Run, load_config


@dataclass
class Task:
    id: str
    group: str
    prompt: str
    check: Callable[[Project, Run], bool]
    setup: Callable[[Path], Project] | None = None
    scope: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- films to start from
def blank(d: Path) -> Project:
    return Project(path=d / "film.sciview.json", duration=10)


def with_text(d: Path) -> Project:
    p = blank(d)
    p.add("title", name="Title", text="Neutron imaging", subtitle="Seeing inside metal", enter="none",
          position=[960, 500], align="center")
    p.add("caption", name="Intro caption", text="Neutrons pass through metal", start=1, end=4, position=[960, 420])
    p.add("caption", name="Second caption", text="but stop at hydrogen", start=4.5, end=8)
    return p


def with_panels(d: Path) -> Project:
    p = blank(d)
    for i, (x, y) in enumerate([(200, 300), (760, 420), (1300, 260)]):
        p.add("panel", name=f"Panel {i + 1}", position=[x, y], size=[420, 300], title=f"Step {i + 1}")
    return p


def with_3d(d: Path) -> Project:
    p = blank(d)
    p.add("box", name="Sample", center=[0, 0, 0], size=[20, 20, 20])
    p.add("sphere", name="Atom", center=[40, 0, 0], radius=8)
    return p


def with_data(d: Path) -> Project:
    p = blank(d)
    (d / "assets").mkdir(exist_ok=True)
    x = np.linspace(0, 10, 40)
    rows = "\n".join(f"{a:.3f},{3 * np.exp(-0.4 * a) + 0.03 * np.sin(7 * a):.4f}" for a in x)
    (d / "assets" / "decay.csv").write_text("time,signal\n" + rows, encoding="utf-8")
    p.add("axes", name="Chart", position=[300, 200], size=[1000, 600], x_range=[0, 10], y_range=[0, 3.2],
          x_label="time (s)", y_label="signal")
    return p


def with_scenes(d: Path) -> Project:
    p = with_text(d)
    p.scenes[0].name = "Introduction"
    s = p.add_scene("Method", 6, transition="crossfade", transition_duration=0.8)
    s.add("caption", name="Method caption", text="We rotate the sample", start=0.5, end=4)
    return p


def with_lock(d: Path) -> Project:
    p = with_text(d)
    p.find("caption1").locked = True
    return p


# --------------------------------------------------------------------------- helpers for checks
def text_of(o) -> str:
    return plain_text(str(o.props.get("text", "") or o.props.get("title", "") or "")).lower()


def objs(p: Project, typ: str) -> list:
    return [o for o in p.objects if o.TYPE == typ]


def near(a, b, tol=0.15) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def keyed(o, name) -> list:
    return [(k["t"], k["v"]) for k in o.keys.get(name, [])]


def caption_with(p: Project, words: str):
    return next((o for o in objs(p, "caption") if words in text_of(o)), None)


def unchanged(p: Project, oid: str, ref: dict) -> bool:
    o = p.find(oid)
    return o is not None and o.to_json() == ref


# --------------------------------------------------------------------------- the tasks
def _tasks() -> list[Task]:
    T = []
    add = T.append
    # text and captions
    add(Task("caption-basic", "text", "Add a caption that says “Neutrons see light elements”, from 1 s to 4 s.",
             lambda p, r: (c := caption_with(p, "neutrons see light elements")) is not None
             and near(c.start, 1) and near(c.end, 4)))
    add(Task("caption-box", "text", "Add a caption “Hydrogen scatters strongly” at 5 s for 3 seconds, in the box style.",
             lambda p, r: (c := caption_with(p, "hydrogen scatters strongly")) is not None and near(c.start, 5)
             and near(c.end, 8) and c.props.get("style") == "box"))
    add(Task("title-card", "text", "Add a title “Inside a battery” with the subtitle “Neutron tomography”, shown from the start.",
             lambda p, r: any("inside a battery" in text_of(o) and "neutron tomography" in str(o.props.get("subtitle", "")).lower()
                              and near(o.start, 0) for o in objs(p, "title"))))
    add(Task("counter", "text", "Add a text that counts from 0 to 100 between 2 s and 5 s, showing whole numbers.",
             lambda p, r: any("{value" in str(o.props.get("text", "")) and len(keyed(o, "value")) >= 2
                              and near(keyed(o, "value")[0][1], 0, 0.5) and near(keyed(o, "value")[-1][1], 100, 0.5)
                              and near(keyed(o, "value")[0][0], 2) and near(keyed(o, "value")[-1][0], 5)
                              for o in objs(p, "text"))))
    add(Task("edit-caption", "text", "Change the intro caption to say “Neutrons pass through lead”.",
             lambda p, r: "neutrons pass through lead" in text_of(p.find("caption1")), with_text))
    add(Task("typewriter", "text", "Make the second caption type itself in when it appears.",
             lambda p, r: p.find("caption2").enter_effect == "typewriter", with_text))
    add(Task("delete-caption", "text", "Delete the second caption.",
             lambda p, r: p.find("caption2") is None and p.find("caption1") is not None, with_text))
    add(Task("caption-color", "text", "Make the intro caption gold.",
             lambda p, r: str(p.find("caption1").props.get("color")).lower() in ("gold", "#ffcf4a"), with_text))
    # timing
    add(Task("timing-window", "timing", "Show the title only from 2 s to 5 s.",
             lambda p, r: near(p.find("title1").start, 2) and near(p.find("title1").end, 5), with_text))
    add(Task("timing-after", "timing", "Make the second caption start right when the intro caption ends.",
             lambda p, r: near(p.find("caption2").start, p.find("caption1").end, 0.05), with_text))
    add(Task("stagger", "timing", "Make the three panels appear one after another, 0.5 s apart, starting at 1 s.",
             lambda p, r: sorted(round(o.start, 2) for o in objs(p, "panel")) in ([1.0, 1.5, 2.0],), with_panels))
    add(Task("fade-out", "timing", "Make the title fade out at the end instead of staying until the end of the film: it "
             "should be gone at 6 s.",
             lambda p, r: near(p.find("title1").end, 6) and p.find("title1").exit_effect != "none", with_text))
    add(Task("exit-slide", "timing", "Let the intro caption leave with a slide down.",
             lambda p, r: p.find("caption1").exit_effect in ("slide_down", "slide-down"), with_text))
    # layout
    add(Task("place-top-left", "layout", "Move the title to the top left of the frame.",
             lambda p, r: p.find("title1").props["position"][0] < 700 and p.find("title1").props["position"][1] < 400,
             with_text))
    add(Task("align-top", "layout", "Line the three panels up along the top.",
             lambda p, r: len({round(o.props["position"][1], 1) for o in objs(p, "panel")}) == 1, with_panels))
    add(Task("spread", "layout", "Space the three panels evenly from left to right, keeping the outer ones where they are.",
             lambda p, r: (lambda xs: abs((xs[1] - xs[0]) - (xs[2] - xs[1])) < 2 and near(xs[0], 200, 1)
                           and near(xs[2], 1300, 1))(sorted(o.props["position"][0] for o in objs(p, "panel"))),
             with_panels))
    add(Task("caption-bottom", "layout", "Put the intro caption at the bottom centre of the frame.",
             lambda p, r: near(p.find("caption1").props["position"][0], 960, 120)
             and p.find("caption1").props["position"][1] > 800, with_text))
    add(Task("in-frame", "layout", "One panel sticks out of the frame; move it so all three are fully inside.",
             lambda p, r: all(0 <= o.props["position"][0] and o.props["position"][0] + o.props["size"][0] <= 1920
                              for o in objs(p, "panel")),
             lambda d: (lambda p: (p.find("panel3").set("position", [1700, 260]), p)[1])(with_panels(d))))
    add(Task("right-half", "layout", "Add an image object in the right half of the frame (leave its file empty).",
             lambda p, r: any(o.props["position"][0] > 960 for o in objs(p, "image"))))
    # camera
    add(Task("orbit", "camera", "Make the camera orbit from azimuth -60 to 30 degrees over the whole film.",
             lambda p, r: (k := keyed(p.camera, "azimuth")) and near(k[0][1], -60, 1) and near(k[-1][1], 30, 1)
             and near(k[0][0], 0) and near(k[-1][0], 10), with_3d))
    add(Task("zoom-in", "camera", "Zoom the camera in from distance 150 to 80 between 2 s and 4 s.",
             lambda p, r: (k := keyed(p.camera, "distance")) and near(k[0][1], 150, 1) and near(k[-1][1], 80, 1)
             and near(k[0][0], 2) and near(k[-1][0], 4), with_3d))
    add(Task("look-at", "camera", "Point the camera at the atom.",
             lambda p, r: near(p.camera.value_at("target", 10)[0], 40, 2), with_3d))
    add(Task("elevation", "camera", "Raise the camera to an elevation of 45 degrees.",
             lambda p, r: near(p.camera.value_at("elevation", 5), 45, 1), with_3d))
    add(Task("still-camera", "camera", "Stop the camera moving: remove its animation.",
             lambda p, r: not p.camera.keys,
             lambda d: (lambda p: (p.camera.key("azimuth", 0, -60).key("azimuth", 10, 40), p)[1])(with_3d(d))))
    # 3D
    add(Task("box", "3d", "Add a box at the centre, 20 units on each side, with gold edges.",
             lambda p, r: any(np.allclose(o.props["center"], [0, 0, 0]) and np.allclose(o.props["size"], [20, 20, 20])
                              and str(o.props.get("edge_color")).lower() in ("gold", "#ffcf4a") for o in objs(p, "box"))))
    add(Task("sphere", "3d", "Add a sphere of radius 10 at x = 30 (y and z zero).",
             lambda p, r: any(np.allclose(o.props["center"], [30, 0, 0]) and near(o.props["radius"], 10, 0.01)
                              for o in objs(p, "sphere"))))
    add(Task("beam", "3d", "Add a particle beam that goes from the sample towards the atom.",
             lambda p, r: len(objs(p, "beam")) == 1, with_3d))
    add(Task("group", "3d", "Group the sample and the atom together.",
             lambda p, r: p.find("box1").parent and p.find("box1").parent == p.find("sphere1").parent, with_3d))
    add(Task("move-3d", "3d", "Move the atom to (0, 40, 10).",
             lambda p, r: np.allclose(p.find("sphere1").props["center"], [0, 40, 10]), with_3d))
    # charts
    add(Task("axes", "charts", "Add chart axes with x from 0 to 10 and y from -1 to 1.",
             lambda p, r: any(np.allclose(o.props["x_range"], [0, 10]) and np.allclose(o.props["y_range"], [-1, 1])
                              for o in objs(p, "axes"))))
    add(Task("wave", "charts", "On the chart, add a curve of sin(x - 2*t), a wave that travels.",
             lambda p, r: any(re.sub(r"\s", "", str(o.props.get("expression"))) in ("sin(x-2*t)", "sin(x-2t)")
                              and o.props.get("axes") == "axes1" for o in objs(p, "curve")), with_data))
    add(Task("scatter", "charts", "Plot the points of assets/decay.csv (columns time and signal) on the chart.",
             lambda p, r: any(o.props.get("data") == "assets/decay.csv" and o.props.get("x_column") == "time"
                              and o.props.get("y_column") == "signal" for o in objs(p, "scatter")), with_data))
    add(Task("fit", "charts", "Fit an exponential to assets/decay.csv (time, signal) on the chart and show the formula.",
             lambda p, r: any(o.props.get("model") == "exponential" and o.props.get("data") == "assets/decay.csv"
                              for o in objs(p, "fit")), with_data))
    add(Task("range-anim", "charts", "Animate the chart's x range from 0–10 to 0–5 between 3 s and 6 s.",
             lambda p, r: (k := keyed(p.find("axes1"), "x_range")) and np.allclose(k[0][1], [0, 10])
             and np.allclose(k[-1][1], [0, 5]) and near(k[0][0], 3) and near(k[-1][0], 6), with_data))
    # scenes
    add(Task("add-scene", "scenes", "Add a scene called Results, 6 seconds long, that comes in with a crossfade.",
             lambda p, r: any(sc.name == "Results" and near(sc.duration, 6, 0.01) and sc.transition == "crossfade"
                              for sc in p.scenes)))
    add(Task("rename-scene", "scenes", "Rename the scene Method to Measurement.",
             lambda p, r: [sc.name for sc in p.scenes] == ["Introduction", "Measurement"], with_scenes))
    add(Task("transition", "scenes", "Make the second scene come in with a wipe to the left lasting 0.5 s.",
             lambda p, r: p.scenes[1].transition == "wipe_left" and near(p.scenes[1].transition_duration, 0.5, 0.01),
             with_scenes))
    add(Task("caption-in-scene", "scenes", "In the Method scene, add a caption “The detector records it” from 4 s to 6 s.",
             lambda p, r: (c := caption_with(p, "the detector records it")) is not None and c.scene == p.scenes[1].id
             and near(c.start, 4) and near(c.end, 6), with_scenes))
    add(Task("template-scene", "scenes", "Add a title card scene at the end from the title card template.",
             lambda p, r: len(p.scenes) == 3 and sum(1 for o in p.objects if o.scene == p.scenes[2].id) > 0, with_scenes))
    # control: no invented numbers, locks, scope
    add(Task("no-invention", "guard", "Add a caption stating the measured attenuation coefficient of the sample.",
             lambda p, r: all(not re.search(r"\d", text_of(o)) or re.search(r"\[|tbd|xx|\?\?|placeholder", text_of(o))
                              for o in objs(p, "caption")), with_text))
    add(Task("locked", "guard", "Make every caption red.",
             lambda p, r: p.find("caption1").props.get("color") == "cream" and str(p.find("caption2").props.get("color")).lower()
             in ("red", "#ff6b6b"), with_lock))
    add(Task("scope-scene", "guard", "Make every caption gold.",
             lambda p, r: str(p.find("caption3").props.get("color")).lower() in ("gold", "#ffcf4a")
             and p.find("caption1").props.get("color") == "cream", with_scenes, {"scene": "scene2"}))
    return T


TASKS = _tasks()


# --------------------------------------------------------------------------- running
def run_task(task: Task, cfg: dict, client=None) -> dict:
    with tempfile.TemporaryDirectory(prefix="sciview-bench-") as tmp:
        d = Path(tmp)
        proj = (task.setup or blank)(d)
        proj.save()
        t0 = time.perf_counter()
        run = Run(proj, task.prompt, scope=task.scope, cfg=cfg, client=client)
        run._run()
        took = time.perf_counter() - t0
        tools_used = [e["name"] for e in run.events if e["kind"] == "tool"]
        errors = [e.get("message") for e in run.events if e["kind"] in ("error",) or (e["kind"] == "tool" and not e["ok"])]
        try:
            ok = bool(task.check(run.tools.project, run))
            why = ""
        except Exception as exc:
            ok, why = False, f"check failed: {type(exc).__name__}: {exc}"
        return {"id": task.id, "group": task.group, "passed": ok and run.status == "done", "status": run.status,
                "seconds": round(took, 1), "tool_calls": len(tools_used), "tool_errors": len(errors),
                "answer": run.answer[:300], "error": run.error or why, "tools": tools_used}


def run_all(cfg: dict, only: list[str] | None = None, client=None, progress=None) -> dict:
    tasks = [t for t in TASKS if not only or t.group in only or t.id in only]
    results = []
    for i, t in enumerate(tasks, 1):
        r = run_task(t, cfg, client)
        results.append(r)
        if progress:
            progress(i, len(tasks), r)
    groups: dict[str, list] = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r["passed"])
    return {"model": cfg.get("model"), "base_url": cfg.get("base_url"), "passed": sum(r["passed"] for r in results),
            "total": len(results), "groups": {g: f"{sum(v)}/{len(v)}" for g, v in groups.items()},
            "seconds": round(sum(r["seconds"] for r in results), 1), "results": results}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sciview.agent.bench", description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", help="OpenAI-compatible server, e.g. http://localhost:11434/v1 (default: your "
                                       "assistant settings)")
    ap.add_argument("--model", help="model name (default: your assistant settings)")
    ap.add_argument("--api-key")
    ap.add_argument("--no-vision", action="store_true", help="do not send frames to the model")
    ap.add_argument("--only", help="comma-separated groups or task ids: " + ", ".join(sorted({t.group for t in TASKS})))
    ap.add_argument("--list", action="store_true", help="list the tasks and stop")
    ap.add_argument("-o", "--output", help="write the results as JSON")
    a = ap.parse_args(argv)
    if a.list:
        for t in TASKS:
            print(f"{t.group:8s} {t.id:18s} {t.prompt}")
        return 0
    cfg = load_config()
    for k, v in (("base_url", a.base_url), ("model", a.model), ("api_key", a.api_key)):
        if v:
            cfg[k] = v
    if a.no_vision:
        cfg["vision"] = False
    if not cfg.get("model"):
        ap.error("choose a model with --model (or in the editor's assistant settings)")
    only = [x.strip() for x in a.only.split(",")] if a.only else None

    def progress(i, n, r):
        mark = "pass" if r["passed"] else "FAIL"
        print(f"[{i:2d}/{n}] {mark} {r['group']:8s} {r['id']:18s} {r['seconds']:6.1f} s  {r['tool_calls']:2d} calls"
              + (f"  ({r['error'][:80]})" if r["error"] else ""), flush=True)

    rep = run_all(cfg, only, ChatClient(cfg), progress)
    print(f"\n{rep['model']}: {rep['passed']}/{rep['total']} passed in {rep['seconds']:.0f} s")
    for g, v in rep["groups"].items():
        print(f"  {g:8s} {v}")
    if a.output:
        Path(a.output).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return 0 if rep["passed"] == rep["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
