"""The assistant panel's engine: a chat with a language model served by any OpenAI-compatible server
(Ollama, LM Studio, llama.cpp, vLLM ...) that builds the film through the tool layer.

One request runs on a copy of the film. Every change is shown in the editor as it happens; when the
request ends the editor records it as one undo step. After each round of changes SciView checks the
film (missing files, bad expressions, overlapping text, objects outside the frame) and tells the model,
so it can fix what it got wrong. Values the model chose itself (numbers the person never gave, wording
it wrote) are listed for review.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .mcp import INSTRUCTIONS, describe_change
from .tools import MUTATING, TOOLS, FilmTools, ToolError

DEFAULTS: dict[str, Any] = {"base_url": "http://localhost:11434/v1", "model": "", "api_key": "", "temperature": 0.2,
                            "max_steps": 24, "vision": True, "timeout": 300}
PRESETS = [
    {"name": "Ollama", "base_url": "http://localhost:11434/v1"},
    {"name": "LM Studio", "base_url": "http://localhost:1234/v1"},
    {"name": "llama.cpp server", "base_url": "http://localhost:8080/v1"},
    {"name": "vLLM", "base_url": "http://localhost:8000/v1"},
]
LAYOUT_PROPS = {"position", "center", "size", "width", "height", "offset", "pivot", "pivot3d", "rotation", "opacity",
                "glow", "max_width", "title_size", "subtitle_size", "label_size", "label_offset", "thickness", "margin",
                "line_width", "edge_width", "border_width", "font_size", "corner_radius", "spacing", "gap", "padding",
                "fill_opacity", "background_opacity", "scale", "distance", "azimuth", "elevation", "fov", "target",
                "label_position", "align", "weight", "style", "marker_size", "dot_size", "point_size", "badge"}
SYSTEM = INSTRUCTIONS + """
You work inside the SciView editor: the person sees every change at once and can undo the whole request.
Keep to what was asked. Use the tools; do not describe tool calls in prose. When you are done, answer in
one or two short sentences saying what you did and anything the person should check."""


class AssistantError(RuntimeError):
    pass


# --------------------------------------------------------------------------- settings
def config_dir() -> Path:
    env = os.environ.get("SCIVIEW_CONFIG_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "SciView"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SciView"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sciview"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    f = config_dir() / "assistant.json"
    try:
        cfg.update({k: v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save_config(new: dict) -> dict:
    cfg = load_config()
    for k, v in new.items():
        if k not in DEFAULTS or (k == "api_key" and v == "••••"):
            continue
        cfg[k] = type(DEFAULTS[k])(v) if DEFAULTS[k] is not None and not isinstance(DEFAULTS[k], bool) else bool(v)
    cfg["max_steps"] = max(1, min(int(cfg["max_steps"]), 100))
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "assistant.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def public_config(cfg: dict) -> dict:
    out = dict(cfg)
    out["api_key"] = "••••" if cfg.get("api_key") else ""
    return out


# --------------------------------------------------------------------------- the model server
class ChatClient:
    """POST /chat/completions on an OpenAI-compatible server, with tools."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = str(cfg.get("base_url") or DEFAULTS["base_url"]).rstrip("/")

    def _req(self, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if self.cfg.get("api_key"):
            headers["Authorization"] = f"Bearer {self.cfg['api_key']}"
        req = urllib.request.Request(self.base + path, data=data, headers=headers,
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout or float(self.cfg.get("timeout", 300))) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="ignore")[:400]
            hint = ""
            if exc.code == 404:
                hint = " Check the server address (it usually ends in /v1) and the model name."
            elif exc.code in (400, 422) and "tool" in text.lower():
                hint = " This model or server may not support tool calls; choose a model that does."
            raise AssistantError(f"the model server answered {exc.code}: {text}{hint}") from None
        except urllib.error.URLError as exc:
            raise AssistantError(f"cannot reach the model server at {self.base} ({exc.reason}). Is Ollama, LM Studio "
                                 "or your server running?") from None
        except (TimeoutError, OSError) as exc:
            raise AssistantError(f"the model server did not answer in time: {exc}") from None

    def models(self) -> list[str]:
        data = self._req("/models", timeout=10)
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        body = {"model": self.cfg.get("model") or "", "messages": messages, "tools": tools, "tool_choice": "auto",
                "temperature": float(self.cfg.get("temperature", 0.2)), "stream": False}
        data = self._req("/chat/completions", body)
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise AssistantError(f"unexpected answer from the model server: {str(data)[:300]}") from None


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": k, "description": v["description"], "parameters": v["input"]}}
            for k, v in TOOLS.items()]


# --------------------------------------------------------------------------- review flags
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?(?:e-?\d+)?", re.I)


def numbers_in(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(text or ""):
        try:
            out.add(round(float(m.replace(",", ".")), 6))
        except ValueError:
            pass
    return out


def flag_values(changes: list[dict], said: str, project) -> list[dict]:
    """Values the assistant chose that the person should check: numbers they never gave (outside layout and
    look) and text it wrote."""
    given = numbers_in(said)
    flags = []

    def prop_of(oid, name):
        o = project.find(oid) if oid else None
        klass = type(o) if o is not None else None
        if klass is None:
            return None
        return klass.prop_map().get(name)

    def check(oid, name, value, where):
        p = prop_of(oid, name)
        if p is None or name in LAYOUT_PROPS or p.kind in ("color", "bool", "enum", "ref", "asset", "font"):
            return
        if p.kind in ("text", "longtext"):
            norm = lambda x: " ".join(x.lower().split())  # noqa: E731
            if isinstance(value, str) and value.strip() and norm(value).strip(" .") not in norm(said):
                kind = "expression" if p.expr else "text"
                flags.append({"id": oid, "prop": name, "value": value, "where": where,
                              "reason": f"{kind} written by the assistant"})
            return
        vals = value if isinstance(value, (list, tuple)) else [value]
        new = [v for v in vals if isinstance(v, (int, float)) and round(float(v), 6) not in given
               and float(v) not in (0.0, 1.0)]
        if new:
            flags.append({"id": oid, "prop": name, "value": value, "where": where,
                          "reason": "a number you did not give"})

    for c in changes:
        if c.get("action") == "add" and not c.get("template"):
            for k, v in (c.get("props") or {}).items():
                check(c["id"], k, v, "added")
        elif c.get("action") in ("set", "key") and not c.get("layout"):
            check(c["id"], c.get("prop"), c.get("value"), "keyframe" if c["action"] == "key" else "set")
    return flags


def summarise(changes: list[dict], project) -> list[dict]:
    """One line per object touched, for the panel."""
    seen: dict[str, dict] = {}
    for c in changes:
        oid = c.get("id")
        if not oid:
            continue
        o = project.find(oid)
        name = o.name if o is not None else oid
        e = seen.setdefault(oid, {"id": oid if o is not None else None, "name": name, "what": []})
        word = {"add": "added", "set": f"set {c.get('prop')}", "key": f"animated {c.get('prop')}",
                "unkey": f"removed a keyframe of {c.get('prop')}", "timing": "retimed", "delete": "deleted",
                "add_scene": "new scene", "scene": "changed the scene"}.get(c.get("action"), c.get("action"))
        if word not in e["what"]:
            e["what"].append(word)
    return list(seen.values())


# --------------------------------------------------------------------------- a request
class Run:
    """One request to the assistant, run in a thread. ``apply(project, note)`` shows a change in the editor."""

    def __init__(self, project, prompt: str, history: list[dict] | None = None, scope: dict | None = None,
                 cfg: dict | None = None, apply: Callable | None = None, client=None):
        self.id = uuid.uuid4().hex[:12]
        self.cfg = dict(cfg or load_config())
        self.client = client or ChatClient(self.cfg)
        self.prompt = prompt
        self.history = [m for m in (history or []) if m.get("role") in ("user", "assistant") and m.get("content")]
        self.scope = {k: v for k, v in (scope or {}).items() if v}
        self.tools = FilmTools(project, self.scope)
        self.apply = apply
        self.events: list[dict] = []
        self.status = "running"
        self.answer = ""
        self.error = ""
        self.stop = threading.Event()
        self.started = time.time()
        self.changed = False
        self._lock = threading.Lock()

    def emit(self, kind: str, **data) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events), "kind": kind, "t": round(time.time() - self.started, 2), **data})

    def since(self, seq: int) -> list[dict]:
        with self._lock:
            return self.events[seq:]

    def start(self) -> Run:
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _scope_note(self) -> str:
        s = self.scope
        parts = []
        if s.get("scene"):
            parts.append(f"only scene {s['scene']!r}")
        if s.get("time"):
            parts.append(f"only between {s['time'][0]:g} and {s['time'][1]:g} s")
        if s.get("ids"):
            parts.append("only these objects and the ones you add: " + ", ".join(s["ids"]))
        return f"\n\n(Scope: {'; '.join(parts)}.)" if parts else ""

    def _run(self) -> None:
        try:
            self._loop()
            if self.stop.is_set() and self.status == "running":
                self.status = "stopped"
            elif self.status == "running":
                self.status = "done"
        except AssistantError as exc:
            self.error = str(exc)
            self.status = "error"
            self.emit("error", message=str(exc))
        except Exception as exc:  # pragma: no cover - defensive: the editor must hear about it
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = "error"
            self.emit("error", message=self.error)
        proj = self.tools.project
        said = " ".join([self.prompt] + [m["content"] for m in self.history if m["role"] == "user"])
        self.emit("done", status=self.status, answer=self.answer, changes=summarise(self.tools.changes, proj),
                  flags=flag_values(self.tools.changes, said, proj))

    def _loop(self) -> None:
        tools = openai_tools()
        film = self.tools.describe_film()
        messages: list[dict] = [{"role": "system", "content": SYSTEM}]
        messages += [{"role": m["role"], "content": str(m["content"])} for m in self.history[-12:]]
        messages.append({"role": "user", "content": self.prompt + self._scope_note()
                         + "\n\nThe film now (describe_film):\n" + json.dumps(_compact(film))[:24000]})
        steps = int(self.cfg.get("max_steps", 24))
        for _step in range(steps):
            if self.stop.is_set():
                return
            self.emit("thinking")
            msg = self.client.complete(messages, tools)
            calls = msg.get("tool_calls") or []
            text = (msg.get("content") or "").strip()
            entry = {"role": "assistant", "content": msg.get("content") or ""}
            if calls:
                entry["tool_calls"] = calls
            messages.append(entry)
            if not calls:
                self.answer = text or "Done."
                self.emit("answer", text=self.answer)
                return
            if text:
                self.emit("say", text=text)
            changed = []
            images = []
            for c in calls:
                if self.stop.is_set():
                    return
                fn = c.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) \
                        else dict(fn.get("arguments") or {})
                except json.JSONDecodeError:
                    args = None
                if args is None:
                    result: dict = {"error": "the arguments were not valid JSON"}
                    self.emit("tool", name=name, ok=False, message=result["error"])
                else:
                    try:
                        out = self.tools.call(name, args)
                        result = self._result_for_model(name, out, images)
                        self.emit("tool", name=name, ok=True, note=describe_change(name, args)
                                  if name in MUTATING else name.replace("_", " "))
                        if name in MUTATING:
                            changed.append(describe_change(name, args))
                    except ToolError as exc:
                        result = {"error": str(exc)}
                        self.emit("tool", name=name, ok=False, message=str(exc))
                messages.append({"role": "tool", "tool_call_id": c.get("id") or name,
                                 "content": json.dumps(result, default=str)[:12000]})
            if changed:
                self.changed = True
                if self.apply is not None:
                    self.apply(self.tools.project, changed[-1] if len(changed) == 1 else
                               f"Assistant: {len(changed)} changes")
                notes = self._checks()
                if notes:
                    self.emit("check", messages=notes[:6])
                    messages[-1]["content"] = messages[-1]["content"][:11000] + json.dumps(
                        {"automatic_checks": notes[:12],
                         "hint": "fix these if they come from your changes, then continue"})
            if images and self.cfg.get("vision", True):
                messages.append({"role": "user", "content": [
                    {"type": "text", "text": "The frame you asked for:"},
                    *({"type": "image_url", "image_url": {"url": "data:image/png;base64," + b}} for b in images)]})
        self.answer = "I stopped after the maximum number of steps; the film has what I did so far."
        self.emit("answer", text=self.answer)

    def _result_for_model(self, name: str, out: dict, images: list[str]) -> dict:
        if name == "render_frame":
            png = out.get("png", b"")
            if self.cfg.get("vision", True) and png:
                images.append(base64.b64encode(png).decode())
            return {"issues": out.get("issues"), "objects_visible": out.get("objects_visible"),
                    "image": "attached in the next message" if self.cfg.get("vision", True) else
                    "not sent (vision is off): use the list of visible objects and the issues"}
        return out

    def _checks(self) -> list[str]:
        from .. import checks
        proj = self.tools.project
        notes = [p["message"] for p in proj.problems()]
        try:
            notes += [p["message"] for p in checks.layout_issues(proj)]
        except Exception as exc:  # a check must never stop the request
            notes.append(f"(layout check failed: {exc})")
        return notes


def _compact(film: dict) -> dict:
    """describe_film without the noise a model does not need in its first look."""
    out = copy.deepcopy(film)
    out.pop("palette", None)
    if not out.get("problems"):
        out.pop("problems", None)
    return out
