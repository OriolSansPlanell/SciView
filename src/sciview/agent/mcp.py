"""SciView as an MCP server, so AI assistants (Claude Desktop, LM Studio, Ollama front-ends, any MCP
client) can build films with the tools in :mod:`sciview.agent.tools`.

It speaks JSON-RPC 2.0 over standard input and output, one message per line, as the Model Context
Protocol's stdio transport describes; nothing else is written to standard output.

    sciview mcp film.sciview.json                  # edit the file; it is saved after every change
    sciview mcp --editor http://localhost:8765     # drive a running editor: changes appear live,
                                                   # and Ctrl+Z there takes them back
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import IO

from .. import __version__
from ..model.project import Project
from .tools import MUTATING, TOOLS, FilmTools, ToolError

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = """You are building a scientific explainer video in SciView.
Start with describe_film, and get_schema for any type before you use it. Times are seconds.
2D objects use pixels on the frame ((0, 0) is the top-left); 3D objects use scene units, z up.
A film can have several scenes (describe_film lists them); object times count from the start of their
scene, and add_scene starts a new part, from a template if one fits.
Prefer place() and align() and the user's own numbers and expressions; never invent scientific values:
ask, or use clearly marked placeholders. Locked objects and anything outside your scope are off limits.
After changing something, look at it with render_frame or check_frames and fix what overlaps or leaves
the frame."""


class FileBackend:
    """Tools on a project file; saved after every change (unless autosave is off)."""

    def __init__(self, path: str | Path, scope: dict | None = None, autosave: bool = True):
        self.path = Path(path)
        project = Project.load(self.path) if self.path.exists() else Project(path=self.path)
        self.tools = FilmTools(project, scope)
        self.autosave = autosave

    def call(self, name: str, args: dict) -> dict:
        out = self.tools.call(name, args)
        if name in MUTATING and self.autosave:
            self.tools.project.save(self.path)
        return out


class EditorBackend:
    """Tools on the film open in a running SciView editor (sciview edit), through its local API."""

    def __init__(self, url: str, scope: dict | None = None):
        self.url = url.rstrip("/")
        self.tools = FilmTools(Project())
        self.tools.scope = dict(scope or {})          # checked against the editor's film when it is loaded

    def _req(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"X-SciView": "1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read()
        except urllib.error.URLError as exc:
            raise ToolError(f"cannot reach the SciView editor at {self.url}: {exc.reason}. Is 'sciview edit' running?") from None

    def _load(self) -> int:
        code, _, raw = self._req("GET", "/api/project")
        if code != 200:
            raise ToolError(f"the editor answered {code}")
        st = json.loads(raw)
        self.tools.project = Project.from_json(st["project"], st.get("path"))
        if self.tools.scope.get("scene"):
            try:
                self.tools.project.current_scene = self.tools.scope["scene"]
            except KeyError:
                raise ToolError(f"the scene in your scope no longer exists: {self.tools.scope['scene']!r}") from None
            self.tools.scope["scene"] = self.tools.project.current_scene.id
        return int(st["rev"])

    def call(self, name: str, args: dict) -> dict:
        if name == "render_frame":
            t = float(args.get("time", 0))
            scale = float(args.get("scale", 0.5))
            scene = args.get("scene")
            extra = f"&scene={urllib.parse.quote(str(scene))}" if scene else ""
            code, ctype, raw = self._req("GET", f"/api/frame?t={t:.4f}&scale={min(max(scale, 0.1), 1.0)}{extra}")
            if code != 200:
                raise ToolError(f"the editor could not render: {raw[:200]!r}")
            return {"jpeg": raw}
        for _attempt in range(4):
            rev = self._load()
            before = len(self.tools.changes)
            out = self.tools.call(name, args)
            if name not in MUTATING:
                return out
            note = describe_change(name, args)
            code, _, raw = self._req("POST", "/api/agent", {"project": self.tools.project.to_json(),
                                                            "base_rev": rev, "note": note})
            if code == 200:
                return out
            del self.tools.changes[before:]          # not applied: forget it, read the film again, retry
            if code != 409:
                raise ToolError(f"the editor refused the change ({code}): {raw[:200]!r}")
        raise ToolError("the film keeps changing in the editor; try again in a moment")


def describe_change(name: str, args: dict) -> str:
    what = {"add_object": "added a {type}", "set_property": "set {name} of {id}", "add_keyframe": "animated {name} of {id}",
            "remove_keyframe": "removed a keyframe of {id}", "set_timing": "changed the timing of {id}",
            "delete": "deleted {id}", "group": "grouped objects", "place": "moved {id}", "align": "lined up objects",
            "add_scene": "added the scene {name}", "set_scene": "changed the scene {scene}"}.get(name, name)
    try:
        return "Assistant " + what.format(**{k: v for k, v in args.items() if isinstance(v, (str, int, float))})
    except (KeyError, IndexError):
        return "Assistant: " + name


class Server:
    """JSON-RPC 2.0 message handling for the MCP tools (transport-independent)."""

    def __init__(self, backend):
        self.backend = backend
        self.initialized = False

    def tool_list(self) -> list[dict]:
        return [{"name": n, "description": spec["description"], "inputSchema": spec["input"]} for n, spec in TOOLS.items()]

    def handle(self, msg) -> dict | list | None:
        if isinstance(msg, list):
            out = [r for r in (self.handle(m) for m in msg) if r is not None]
            return out or None
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
        method, mid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        is_note = "id" not in msg
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                self.initialized = True
                return _result(mid, {"protocolVersion": version,
                                     "capabilities": {"tools": {"listChanged": False}},
                                     "serverInfo": {"name": "sciview", "title": "SciView", "version": __version__},
                                     "instructions": INSTRUCTIONS})
            if method.startswith("notifications/"):
                return None
            if method == "ping":
                return _result(mid, {})
            if method == "tools/list":
                return _result(mid, {"tools": self.tool_list()})
            if method == "tools/call":
                return _result(mid, self.call_tool(params.get("name", ""), params.get("arguments") or {}))
            if is_note:
                return None
            return _error(mid, -32601, f"method not found: {method}")
        except Exception as exc:  # never let one bad message stop the server
            return None if is_note else _error(mid, -32603, f"internal error: {exc}")

    def call_tool(self, name: str, args: dict) -> dict:
        if name not in TOOLS:
            return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
        try:
            out = self.backend.call(name, args)
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except (ValueError, KeyError, TypeError, OSError) as exc:
            return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
        content = []
        if "png" in out or "jpeg" in out:
            mime, raw = ("image/png", out.pop("png")) if "png" in out else ("image/jpeg", out.pop("jpeg"))
            content.append({"type": "image", "data": base64.b64encode(raw).decode(), "mimeType": mime})
        content.append({"type": "text", "text": json.dumps(out, ensure_ascii=False, default=str)})
        return {"content": content, "isError": False, "structuredContent": out}


def _result(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve_stdio(backend, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
    """Read JSON-RPC messages line by line until standard input closes."""
    if stdin is None:
        stdin = sys.stdin
        if hasattr(stdin, "reconfigure"):
            stdin.reconfigure(encoding="utf-8", errors="replace")     # MCP messages are UTF-8 on every OS
    if stdout is None:
        stdout = sys.stdout
        if hasattr(stdout, "reconfigure"):
            stdout.reconfigure(encoding="utf-8", newline="\n")        # no \r\n on Windows
    server = Server(backend)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = _error(None, -32700, "parse error")
        else:
            reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()
