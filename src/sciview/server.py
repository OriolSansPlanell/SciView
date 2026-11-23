"""Local web server behind the editor (``sciview edit``).

Python renders; the browser shows the interface. The server binds to
127.0.0.1 by default, checks the Host header (against DNS rebinding) and
requires a custom header on every request that changes something (so other
web pages cannot drive it).
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import traceback
import urllib.parse
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from . import __version__
from .engine.assets import asset_kind
from .model.project import Project, all_schemas, iter_assets
from .render import FrameInfo, Renderer

PKG = Path(__file__).resolve().parent
GUI_DIR = PKG / "gui"
FONT_DIR = PKG / "fonts"
TEMPLATE_DIR = PKG / "templates"
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB


# --------------------------------------------------------------------------- templates
def list_templates() -> list[dict]:
    out = []
    if not TEMPLATE_DIR.exists():
        return out
    for d in sorted(TEMPLATE_DIR.iterdir()):
        f = d / "project.sciview.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = data.get("template") or {}
        out.append({"name": d.name, "title": meta.get("title", d.name.replace("_", " ").title()),
                    "description": meta.get("description", ""), "order": meta.get("order", 50),
                    "duration": (data.get("settings") or {}).get("duration", 10),
                    "thumb_time": meta.get("thumb_time")})
    return sorted(out, key=lambda m: (m["order"], m["title"]))


def instantiate_template(name: str, base_dir: Path) -> Project:
    """Load a template and copy its asset files into ``base_dir/assets``."""
    tdir = TEMPLATE_DIR / name
    f = tdir / "project.sciview.json"
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", name) or not f.exists():
        raise ValueError(f"no template called {name!r}")
    data = json.loads(f.read_text(encoding="utf-8"))
    data.pop("template", None)
    mapping: dict[str, str] = {}
    src_assets = tdir / "assets"
    if src_assets.exists():
        dst = base_dir / "assets"
        dst.mkdir(parents=True, exist_ok=True)
        for src in src_assets.iterdir():
            if not src.is_file():
                continue
            target = dst / src.name
            if target.exists() and target.read_bytes() != src.read_bytes():
                stem, ext = src.stem, src.suffix
                k = 2
                while (dst / f"{stem}_{k}{ext}").exists():
                    k += 1
                target = dst / f"{stem}_{k}{ext}"
            if not target.exists():
                shutil.copy2(src, target)
            mapping[f"assets/{src.name}"] = target.relative_to(base_dir).as_posix()

    def remap(obj):
        if isinstance(obj, dict):
            return {k: remap(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [remap(v) for v in obj]
        if isinstance(obj, str) and obj in mapping:
            return mapping[obj]
        return obj
    return Project.from_json(remap(data), base_dir / "untitled.sciview.json")


# --------------------------------------------------------------------------- session
class EditorSession:
    """State shared by all requests: the project being edited, preview cache and export job."""

    def __init__(self, project: Project, base_dir: Path, untitled: bool | None = None):
        self.base_dir = base_dir.resolve()
        if project.path is None:
            project.path = self.base_dir / "untitled.sciview.json"
        self.project = project
        self.untitled = (not Path(project.path).exists()) if untitled is None else untitled
        self.rev = 1
        self.saved_rev = 1
        self.lock = threading.RLock()
        self.render_lock = threading.Lock()
        self.renderer = Renderer(project, self.base_dir)
        self.cache: OrderedDict = OrderedDict()
        self.thumbs: dict[str, bytes] = {}
        self.export_state: dict = {"state": "idle"}
        self.mix_cache: dict = {}
        self.runs: dict = {}                       # assistant requests by id
        self.export_cancel = threading.Event()
        self.export_thread: threading.Thread | None = None
        # prefetch: frames ahead of the playhead, rendered while the editor is idle
        self.prefetch_target: tuple | None = None
        self.prefetch_event = threading.Event()
        self.fg_waiting = 0
        self.stop = threading.Event()
        self.prefetch_thread: threading.Thread | None = None
        # autosave
        self.autosaved_rev = self.rev
        self.recovery: dict | None = None
        self.external_rev = 0          # revision of the last change made by an agent
        self.external_note = ""
        self.check_recovery()

    # ------------------------------------------------------------------ autosave
    @property
    def autosave_path(self) -> Path:
        return self.path.with_name("." + self.path.name + ".autosave")

    def check_recovery(self) -> None:
        a = self.autosave_path
        self.recovery = None
        try:
            if a.exists():
                newer = (not self.path.exists()) or a.stat().st_mtime > self.path.stat().st_mtime
                if newer:
                    self.recovery = {"path": str(a), "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(a.stat().st_mtime))}
        except OSError:
            self.recovery = None

    def autosave_now(self) -> bool:
        """Write unsaved changes next to the project file; True if something was written."""
        with self.lock:
            if self.rev == self.saved_rev or self.rev == self.autosaved_rev:
                return False
            data = json.dumps(self.project.to_json(), indent=1, ensure_ascii=False)
            rev = self.rev
        try:
            a = self.autosave_path
            tmp = a.with_name(a.name + ".tmp")
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, a)
        except OSError:
            return False
        self.autosaved_rev = rev
        return True

    def drop_autosave(self) -> None:
        try:
            self.autosave_path.unlink()
        except OSError:
            pass
        self.recovery = None

    def recover(self, action: str) -> None:
        if action == "restore" and self.recovery:
            path = self.path
            proj = Project.load(self.autosave_path)
            proj.path = path
            self.set_project(proj)          # unsaved: the user decides when to save
            self.recovery = None
        else:
            self.drop_autosave()

    def start_background(self, autosave_interval: float = 30.0, prefetch: bool = True) -> None:
        if prefetch and self.prefetch_thread is None:
            self.prefetch_thread = threading.Thread(target=self._prefetch_loop, daemon=True)
            self.prefetch_thread.start()
        if autosave_interval and autosave_interval > 0:
            def loop():
                while not self.stop.wait(autosave_interval):
                    self.autosave_now()
            threading.Thread(target=loop, daemon=True).start()

    # ------------------------------------------------------------------ prefetch
    def _prefetch_loop(self) -> None:
        while not self.stop.is_set():
            self.prefetch_event.wait(0.5)
            self.prefetch_event.clear()
            target = self.prefetch_target
            if target is None:
                continue
            rev, first, last, scale = target
            for idx in range(first, last + 1):
                if self.stop.is_set() or self.prefetch_target is not target or self.rev != rev:
                    break
                if self.export_thread is not None and self.export_thread.is_alive():
                    break
                while self.fg_waiting > 0 and not self.stop.is_set():
                    time.sleep(0.005)
                with self.lock:
                    if (rev, idx, round(scale, 3)) in self.cache:
                        continue
                self._render(idx, scale, rev)

    @property
    def path(self) -> Path:
        return Path(self.project.path)

    def set_project(self, proj: Project, mark_saved: bool = False, expect_rev: int | None = None,
                    external_note: str | None = None) -> None:
        """Replace the project. With ``expect_rev``, only if the revision is still that one (else
        ValueError('conflict')); ``external_note`` marks the change as made by an agent."""
        # wait for a frame being drawn to finish, so it never sees two projects (lock order:
        # render_lock, then lock; _render never holds both)
        with self.render_lock, self.lock:
            if expect_rev is not None and int(expect_rev) != self.rev:
                raise ValueError("conflict")
            if proj.path is None:
                proj.path = self.path
            self.project = proj
            self.renderer.project = proj
            self.renderer.assets.base_dir = proj.base_dir
            self.rev += 1
            if mark_saved:
                self.saved_rev = self.rev
            if external_note is not None:
                self.external_rev = self.rev
                self.external_note = str(external_note)[:300]
            self.cache.clear()

    def assets(self) -> list[dict]:
        seen: dict[str, dict] = {}
        root = self.project.base_dir
        adir = root / "assets"
        if adir.exists():
            for f in sorted(adir.rglob("*")):
                if f.is_file() and not f.name.startswith("."):
                    rel = f.relative_to(root).as_posix()
                    seen[rel] = {"path": rel, "kind": asset_kind(rel), "size": f.stat().st_size}
        for rel in iter_assets(self.project):
            if rel not in seen:
                f = Path(rel) if Path(rel).is_absolute() else root / rel
                seen[rel] = {"path": rel, "kind": asset_kind(rel), "size": f.stat().st_size if f.exists() else None,
                             "missing": not f.exists()}
        return list(seen.values())

    def apply_external(self, data: dict, base_rev: int, note: str = "") -> int:
        """A change from an agent (MCP server): applied only if nobody changed the film since base_rev.
        Raises ValueError('conflict') otherwise. Returns the new revision."""
        proj = Project.from_json(data, self.project.path)
        self.set_project(proj, expect_rev=base_rev, external_note=note or "")
        return self.rev

    def state(self) -> dict:
        from .export import FORMATS, TARGETS, find_ffmpeg
        try:
            find_ffmpeg()
            ff = True
        except Exception:
            ff = False
        return {"project": self.project.to_json(), "path": str(self.path), "name": self.path.name,
                "base_dir": str(self.project.base_dir), "saved": self.rev == self.saved_rev,
                "untitled": self.untitled,
                "assets": self.assets(), "schema": all_schemas(), "templates": list_templates(),
                "version": __version__, "ffmpeg": ff, "rev": self.rev,
                "formats": {**FORMATS, "html": "Web page - the video with captions, chapters and the project",
                            "pptx": "PowerPoint - one slide per scene with its clip"},
                "targets": {k: {kk: vv for kk, vv in v.items()} for k, v in TARGETS.items()},
                "issues": self.project.validate(), "problems": self.project.problems(),
                "recovery": self.recovery}

    def frame(self, t: float, scale: float, playing: bool = False) -> tuple[bytes, dict]:
        """JPEG bytes and info for the frame nearest to t (frames are cached by index)."""
        fps = self.project.fps
        idx = max(0, int(round(t * fps)))
        key = (self.rev, idx, round(scale, 3))
        with self.lock:
            hit = self.cache.get(key)
            if hit is not None:
                self.cache.move_to_end(key)
            rev = self.rev
        if hit is None:
            self.fg_waiting += 1
            try:
                hit = self._render(idx, scale, rev)
            finally:
                self.fg_waiting -= 1
        ahead = int(fps * (3 if playing else 0.5))
        last = min(int(round(self.project.duration * fps)), idx + ahead)
        if ahead and last > idx:
            self.prefetch_target = (rev, idx + 1, last, scale)
            self.prefetch_event.set()
        return hit

    def _render(self, idx: int, scale: float, rev: int) -> tuple[bytes, dict]:
        info = FrameInfo()
        with self.render_lock:
            if rev != self.rev:          # the project changed while waiting
                rev = self.rev
            img = self.renderer.frame(idx / self.project.fps, scale, info)
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG", quality=88 if scale < 0.75 else 92)
        meta = {"boxes": info.boxes, "warnings": info.warnings, "issues": info.issues, "ms": round(info.ms, 1),
                "rev": rev, "t": idx / self.project.fps, "cached": info.cached}
        out = (buf.getvalue(), meta)
        with self.lock:
            if rev == self.rev:
                self.cache[(rev, idx, round(scale, 3))] = out
                while len(self.cache) > 600:
                    self.cache.popitem(last=False)
        return out

    # ------------------------------------------------------------------ sound and transforms
    def mix_wav(self) -> bytes:
        """The film's whole sound as WAV for the preview (cached until a clip or the scenes change)."""
        from . import audio
        proj = self.project
        clips = audio.clips(proj)
        key = json.dumps([[str(c["path"]), c["at"], c["trim"], c["length"], c["volume"], c["fade_in"], c["fade_out"],
                           c["path"].stat().st_mtime_ns if c["path"].exists() else 0] for c in clips]
                         + [round(proj.duration, 3)], default=str)
        hit = self.mix_cache.get(key)
        if hit is None:
            pcm = audio.mix(proj, 0.0, proj.duration, rate=44100)
            hit = audio.wav_bytes(pcm, 44100)
            self.mix_cache = {key: hit}
        return hit

    def transform(self, body: dict) -> dict:
        """Work out a change on a copy of the editor's film and send the new film back (one undo step there)."""
        from . import narration
        op = body.get("op")
        proj = Project.from_json(body.get("project") or self.project.to_json(), self.project.path)
        before = {o.id for o in proj.objects}
        out: dict = {}
        if op == "apply_theme":
            from . import theme
            name = body.get("theme")
            src = name
            if isinstance(name, str) and name not in theme.builtin():
                f = self._safe_path(name)
                if f is None:
                    raise ValueError("the theme file must be inside the project folder")
                src = f
            out["notes"] = theme.apply(proj, src, bool(body.get("restyle", True)))
        elif op == "script_captions":
            sc = proj.get_scene(body.get("scene")) if body.get("scene") else proj.current_scene
            narration.captions_from_script(proj, body.get("text", ""), sc, body.get("voice") or None,
                                           float(body.get("start", 0.0)), **(body.get("props") or {}))
        elif op == "read_aloud":
            ids = body.get("ids") or []
            caps = [proj.find(i) for i in ids] if ids else None
            narration.read_aloud(proj, [c for c in caps if c is not None] if caps else None)
        else:
            raise ValueError(f"unknown change {op!r}")
        out["project"] = proj.to_json()
        out["added"] = len({o.id for o in proj.objects} - before)
        return out

    # ------------------------------------------------------------------ assistant panel
    def start_assistant(self, body: dict) -> dict:
        from .agent.assistant import Run
        if any(r.status == "running" for r in self.runs.values()):
            raise ValueError("the assistant is still working on the last request")
        if body.get("project"):
            self.set_project(Project.from_json(body["project"], self.project.path))
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("ask the assistant something")
        proj = self.project.copy()
        if body.get("scene"):
            try:
                proj.current_scene = body["scene"]          # new objects go into the scene in view
            except KeyError:
                pass

        def apply(p, note):
            self.set_project(p.copy(), external_note=note)

        run = Run(proj, prompt, body.get("history"), body.get("scope"), apply=apply,
                  client=getattr(self, "assistant_client", None))
        self.runs = {k: v for k, v in self.runs.items() if v.status == "running"}
        self.runs[run.id] = run
        run.start()
        return {"id": run.id, "rev": self.rev}

    def _safe_path(self, rel: str) -> Path | None:
        base = self.project.base_dir.resolve()
        p = (base / rel).resolve()
        return p if (p == base or base in p.parents) and p.is_file() else None

    # ------------------------------------------------------------------ export
    def start_export(self, opts: dict) -> dict:
        from .export import TARGETS, Cancelled, detect_format, export
        if self.export_thread and self.export_thread.is_alive():
            raise ValueError("an export is already running")
        target = opts.get("target") or None
        if target and target not in TARGETS:
            raise ValueError(f"unknown preset {target!r}")
        fmt = opts.get("format") or (TARGETS[target]["ext"] if target else "mp4")
        stem = "film" if self.untitled else self.path.name.split(".")[0]
        default = stem + ("_frames" if fmt == "png" and not (target and TARGETS[target].get("still"))
                          else (f"_{target}" if target else "") + f".{fmt}")
        name = (opts.get("filename") or "").strip() or default
        out = Path(name)
        if not out.is_absolute():
            out = self.project.base_dir / out
        still = bool(target and TARGETS[target].get("still"))
        if (fmt != "png" or still) and out.suffix.lower() != f".{fmt}":
            out = out.with_suffix(f".{fmt}")
        if fmt not in ("html", "pptx") and not still:
            detect_format(out)
        proj = self.project.copy()
        self.export_cancel.clear()
        self.export_state = {"state": "running", "done": 0, "total": 0, "eta": None, "output": str(out),
                             "started": time.time(), "format": fmt}

        def progress(done, total, eta):
            self.export_state.update(done=done, total=total, eta=eta)

        def run():
            try:
                subs = opts.get("subtitles", False)
                export(proj, out, scale=float(opts["scale"]) if opts.get("scale") else None,
                       crf=int(opts["crf"]) if opts.get("crf") else None,
                       fps=float(opts["fps"]) if opts.get("fps") else None,
                       workers=int(opts["workers"]) if opts.get("workers") else None,
                       subtitles=subs if isinstance(subs, str) else bool(subs),
                       transparent=bool(opts.get("transparent")), target=target,
                       chapters=bool(opts.get("chapters", True)),
                       time=float(opts["time"]) if opts.get("time") is not None else None,
                       progress=progress, cancel=self.export_cancel)
                size = out.stat().st_size if out.is_file() else None
                self.export_state.update(state="done", finished=time.time(), size=size)
            except Cancelled:
                self.export_state.update(state="cancelled")
            except Exception as exc:
                self.export_state.update(state="error", error=str(exc), trace=traceback.format_exc()[-2000:])

        self.export_thread = threading.Thread(target=run, daemon=True)
        self.export_thread.start()
        return self.export_state


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = f"SciView/{__version__}"
    session: EditorSession = None  # set by make_server
    allowed_hosts: set[str] = set()

    def log_message(self, fmt, *args):  # quiet
        if os.environ.get("SCIVIEW_DEBUG"):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------------ helpers
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in self.allowed_hosts

    def _send(self, code: int, body: bytes, ctype: str = "application/json", extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode())

    def _error(self, msg: str, code: int = 400) -> None:
        self._json({"error": msg}, code)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ValueError("upload too large")
        return self.rfile.read(n) if n else b""

    def _body_json(self) -> dict:
        raw = self._body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _file(self, path: Path, download: bool = False) -> None:
        if not path.is_file():
            return self._error("not found", 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in (".js", ".mjs"):
            ctype = "text/javascript"
        extra = {"Content-Disposition": f'attachment; filename="{path.name}"'} if download else None
        self._send(200, path.read_bytes(), ctype, extra)

    def _inside(self, root: Path, rel: str) -> Path | None:
        p = (root / urllib.parse.unquote(rel)).resolve()
        try:
            p.relative_to(root.resolve())
        except ValueError:
            return None
        return p

    # ------------------------------------------------------------------ routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._error("bad host", 403)
        url = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        path = url.path
        s = self.session
        try:
            if path in ("/", "/index.html"):
                return self._file(GUI_DIR / "index.html")
            if path.startswith("/gui/"):
                p = self._inside(GUI_DIR, path[5:])
                return self._file(p) if p else self._error("not found", 404)
            if path.startswith("/fonts/"):
                p = self._inside(FONT_DIR, path[7:])
                return self._file(p) if p else self._error("not found", 404)
            if path.startswith("/files/"):
                p = self._inside(s.project.base_dir, path[7:])
                return self._file(p) if p else self._error("not found", 404)
            if path == "/api/state":
                return self._json(s.state())
            if path == "/api/project":
                return self._json({"project": s.project.to_json(), "rev": s.rev, "path": str(s.path),
                                   "base_dir": str(s.project.base_dir)})
            if path == "/api/changes":
                return self._json({"rev": s.rev, "external_rev": s.external_rev, "note": s.external_note})
            if path == "/api/frame" and q.get("scene"):
                t = float(q.get("t", 0))
                scale = min(2.0, max(0.1, float(q.get("scale", 0.5))))
                info = FrameInfo()
                with s.render_lock:
                    img = s.renderer.frame(t, scale, info, scene=q["scene"])
                buf = io.BytesIO()
                Image.fromarray(img).save(buf, "JPEG", quality=88)
                meta = {"boxes": info.boxes, "warnings": info.warnings, "issues": info.issues, "ms": round(info.ms, 1),
                        "rev": s.rev, "t": t}
                return self._send(200, buf.getvalue(), "image/jpeg",
                                  {"X-Frame-Info": base64.b64encode(json.dumps(meta).encode()).decode()})
            if path == "/api/frame":
                t = float(q.get("t", 0))
                scale = min(2.0, max(0.1, float(q.get("scale", 0.5))))
                jpeg, meta = s.frame(t, scale, playing=q.get("play") == "1")
                info = base64.b64encode(json.dumps(meta).encode()).decode()
                return self._send(200, jpeg, "image/jpeg", {"X-Frame-Info": info})
            if path == "/api/still":
                t = float(q.get("t", 0))
                scale = min(4.0, max(0.1, float(q.get("scale", 1.0))))
                with s.render_lock:
                    img = s.renderer.frame(t, scale)
                buf = io.BytesIO()
                Image.fromarray(img).save(buf, "PNG")
                name = f"{s.path.name.split('.')[0]}_{t:06.2f}s.png"
                return self._send(200, buf.getvalue(), "image/png",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            if path == "/api/templates":
                return self._json(list_templates())
            if path == "/api/template-thumb":
                name = q.get("name", "")
                if name not in s.thumbs:
                    import tempfile
                    with tempfile.TemporaryDirectory() as tmp, s.render_lock:
                        proj = instantiate_template(name, Path(tmp))
                        meta = next((m for m in list_templates() if m["name"] == name), {})
                        tt = meta.get("thumb_time") or proj.duration * 0.6
                        img = Renderer(proj, Path(tmp)).frame(float(tt), 0.25)
                    buf = io.BytesIO()
                    Image.fromarray(img).save(buf, "JPEG", quality=85)
                    s.thumbs[name] = buf.getvalue()
                return self._send(200, s.thumbs[name], "image/jpeg")
            if path == "/api/export":
                return self._json(s.export_state)
            if path == "/api/download":
                p = self._inside(s.project.base_dir, q.get("path", ""))
                if p is None and q.get("path"):
                    cand = Path(q["path"]).resolve()
                    out = s.export_state.get("output")
                    p = cand if out and cand == Path(out).resolve() else None
                return self._file(p, download=True) if p else self._error("not found", 404)
            if path == "/api/files":
                root = s.project.base_dir
                files = sorted(f.relative_to(root).as_posix() for f in root.glob("**/*.sciview.json")
                               if "node_modules" not in f.parts and len(f.relative_to(root).parts) <= 3)
                return self._json({"base_dir": str(root), "files": files[:200]})
            if path == "/api/waveform":
                from . import audio
                rel = q.get("path", "")
                f = self._inside(s.project.base_dir, rel)
                if f is None:
                    return self._error("not found", 404)
                trim = float(q.get("trim", 0) or 0)
                length = float(q["length"]) if q.get("length") else None
                w = audio.waveform(f, int(q.get("bins", 600)), trim, length)
                w["segments"] = audio.speech_segments(f, trim=trim, length=length)
                return self._json(w)
            if path == "/api/mix":
                return self._send(200, s.mix_wav(), "audio/wav", {"Cache-Control": "no-store"})
            if path == "/api/themes":
                from . import theme
                items = [{"name": k, "label": d.get("name", k), "description": d.get("description", ""),
                          "palette": d.get("palette", {}), "settings": d.get("settings", {})}
                         for k, d in theme.builtin().items()]
                return self._json({"themes": items, "current": s.project.settings.get("theme", "")})
            if path == "/api/theme.json":
                from . import theme
                d = theme.from_project(s.project, q.get("name", ""))
                d = theme.embed_files(s.project, d)
                name = (q.get("name") or "theme").strip().replace(" ", "-").lower()
                return self._send(200, json.dumps(d, indent=2).encode(), "application/json",
                                  {"Content-Disposition": f'attachment; filename="{name}.sciview-theme.json"'})
            if path == "/api/tts":
                from . import narration
                eng = narration.engines()
                return self._json({"engines": eng, "hint": "" if eng else
                                   "No text-to-speech engine here: pip install pyttsx3, or install espeak-ng on Linux."})
            if path == "/api/checks":
                from . import checks
                with s.render_lock:
                    proj = s.project.copy()
                    found = checks.layout_issues(proj) + checks.contrast_issues(proj)
                return self._json({"issues": found})
            if path == "/api/assistant":
                run = s.runs.get(q.get("id", ""))
                if run is None:
                    return self._error("no such request", 404)
                return self._json({"status": run.status, "events": run.since(int(q.get("since", 0))),
                                   "rev": s.rev, "changed": run.changed})
            if path == "/api/assistant/config":
                from .agent import assistant
                return self._json({"config": assistant.public_config(assistant.load_config()),
                                   "presets": assistant.PRESETS})
            if path == "/api/assistant/models":
                from .agent import assistant
                cfg = assistant.load_config()
                if q.get("base_url"):
                    cfg["base_url"] = q["base_url"]
                try:
                    return self._json({"models": assistant.ChatClient(cfg).models()})
                except assistant.AssistantError as exc:
                    return self._json({"models": [], "error": str(exc)})
            if path == "/api/captions.srt":
                return self._send(200, s.project.captions_srt().encode(), "text/plain; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="captions.srt"'})
            return self._error("not found", 404)
        except (BrokenPipeError, ConnectionResetError):
            return None                       # the browser went away (closed tab, newer frame asked for)
        except Exception as exc:
            return self._error(f"{type(exc).__name__}: {exc}", 500)

    def _mutating_ok(self) -> bool:
        return self._host_ok() and self.headers.get("X-SciView") == "1"

    def do_PUT(self):
        if not self._mutating_ok():
            return self._error("forbidden", 403)
        s = self.session
        try:
            url = urllib.parse.urlparse(self.path)
            q = dict(urllib.parse.parse_qsl(url.query))
            if url.path == "/api/project":
                data = self._body_json()
                if "base" in q and s.external_rev > int(q["base"]):
                    # an agent changed the film after this editor last saw it: do not overwrite that
                    return self._json({"error": "conflict", "rev": s.rev, "external_rev": s.external_rev,
                                       "note": s.external_note}, 409)
                proj = Project.from_json(data, s.project.path)
                s.set_project(proj)
                problems = proj.problems()
                return self._json({"rev": s.rev, "issues": [p["message"] for p in problems], "problems": problems})
            return self._error("not found", 404)
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as exc:
            return self._error(f"{exc}", 400)

    def do_POST(self):
        if not self._mutating_ok():
            return self._error("forbidden", 403)
        url = urllib.parse.urlparse(self.path)
        path = url.path
        s = self.session
        try:
            if path == "/api/save":
                body = self._body_json()
                target = body.get("path")
                if body.get("project"):
                    s.set_project(Project.from_json(body["project"], s.project.path))
                if target:
                    p = Path(target)
                    if not p.is_absolute():
                        p = s.project.base_dir / p
                    if not p.name.endswith(".json"):
                        p = p.with_name(p.name + ".sciview.json")
                    s.project.path = p.resolve()
                old_autosave = s.autosave_path
                saved = s.project.save()
                with s.lock:
                    s.saved_rev = s.rev
                    s.untitled = False
                for a in {old_autosave, s.autosave_path}:
                    try:
                        a.unlink()
                    except OSError:
                        pass
                s.recovery = None
                return self._json({"path": str(saved), "name": saved.name, "base_dir": str(saved.parent)})
            if path == "/api/open":
                body = self._body_json()
                p = Path(body.get("path", ""))
                if not p.is_absolute():
                    p = s.project.base_dir / p
                proj = Project.load(p)
                s.set_project(proj, mark_saved=True)
                s.untitled = False
                s.check_recovery()
                return self._json(s.state())
            if path == "/api/new":
                body = self._body_json()
                name = body.get("template") or "blank"
                root = s.project.base_dir
                proj = instantiate_template(name, root) if name != "blank" else Project()
                proj.path = root / "untitled.sciview.json"
                s.set_project(proj)
                s.untitled = True
                s.recovery = None
                return self._json(s.state())
            if path == "/api/recover":
                body = self._body_json()
                s.recover(body.get("action", "discard"))
                return self._json(s.state())
            if path == "/api/agent":
                body = self._body_json()
                try:
                    rev = s.apply_external(body["project"], int(body.get("base_rev", -1)), body.get("note", ""))
                except ValueError as exc:
                    if str(exc) == "conflict":
                        return self._json({"error": "the film changed meanwhile; read it again", "rev": s.rev}, 409)
                    raise
                return self._json({"rev": rev})
            if path == "/api/assets":
                fname = Path(urllib.parse.unquote(self.headers.get("X-Filename", "upload.bin"))).name
                fname = re.sub(r"[^A-Za-z0-9._\- ]+", "_", fname).strip() or "upload.bin"
                data = self._body()
                adir = s.project.base_dir / "assets"
                adir.mkdir(parents=True, exist_ok=True)
                target = adir / fname
                if target.exists() and target.read_bytes() != data:
                    stem, ext = target.stem, target.suffix
                    k = 2
                    while (adir / f"{stem}_{k}{ext}").exists():
                        k += 1
                    target = adir / f"{stem}_{k}{ext}"
                target.write_bytes(data)
                rel = target.relative_to(s.project.base_dir).as_posix()
                info = {"path": rel, "kind": asset_kind(rel), "size": len(data)}
                if info["kind"] == "table":
                    try:
                        info["columns"] = list(s.renderer.assets.table(rel).keys())
                    except Exception:
                        pass
                return self._json(info)
            if path == "/api/transform":
                return self._json(s.transform(self._body_json()))
            if path == "/api/assistant":
                return self._json(s.start_assistant(self._body_json()))
            if path == "/api/assistant/stop":
                run = s.runs.get(self._body_json().get("id", ""))
                if run is not None:
                    run.stop.set()
                return self._json({"ok": True})
            if path == "/api/assistant/config":
                from .agent import assistant
                return self._json({"config": assistant.public_config(assistant.save_config(self._body_json()))})
            if path == "/api/export":
                return self._json(s.start_export(self._body_json()))
            if path == "/api/export/cancel":
                s.export_cancel.set()
                return self._json({"ok": True})
            if path == "/api/columns":
                body = self._body_json()
                return self._json({"columns": list(s.renderer.assets.table(body.get("path", "")).keys())})
            return self._error("not found", 404)
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as exc:
            return self._error(f"{exc}", 400)


def make_server(project: Project, base_dir: Path, host: str = "127.0.0.1", port: int = 8765,
                untitled: bool | None = None) -> ThreadingHTTPServer:
    session = EditorSession(project, base_dir, untitled)
    allowed = {"localhost", "127.0.0.1", "::1", host.lower()}
    if host in ("0.0.0.0", "::"):
        import socket
        allowed |= {socket.gethostname().lower(), socket.getfqdn().lower()}
        allowed |= {a.lower() for a in os.environ.get("SCIVIEW_ALLOWED_HOSTS", "").split(",") if a}
    handler = type("SciViewHandler", (Handler,), {"session": session, "allowed_hosts": allowed})
    last_err = None
    for p in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer((host, p), handler)
            srv.daemon_threads = True
            srv.session = session
            return srv
        except OSError as exc:
            last_err = exc
    raise OSError(f"no free port from {port} to {port + 19}: {last_err}")


def serve(project_path: str | None = None, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True,
          template: str | None = None) -> None:
    """Start the editor and block until Ctrl+C."""
    untitled = False
    if project_path:
        p = Path(project_path).resolve()
        if not p.exists() and not p.name.endswith(".json"):
            p = p.with_name(p.name + ".sciview.json")
        if p.exists():
            project = Project.load(p)
        else:
            project = instantiate_template(template, p.parent) if template else Project()
            project.path = p
            project.save()  # create the file so the name the user typed is kept
        base = p.parent
    else:
        base = Path.cwd()
        project = instantiate_template(template, base) if template else Project()
        project.path = base / "untitled.sciview.json"
        untitled = True
    srv = make_server(project, base, host, port, untitled=untitled)
    if not untitled:
        srv.session.saved_rev = srv.session.rev
    h, prt = srv.server_address[:2]
    shown = "localhost" if h in ("127.0.0.1", "0.0.0.0") else h
    url = f"http://{shown}:{prt}/"
    print(f"SciView {__version__} editor running at {url}")
    print(f"Project folder: {base}")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: the editor is reachable from other machines. Anyone who can reach it can read and write files in the project folder.")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    srv.session.start_background()
    try:
        srv.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if srv.session.autosave_now():
            print(f"Unsaved changes kept in {srv.session.autosave_path.name}; the editor offers them next time.")
        srv.session.stop.set()
        srv.server_close()
